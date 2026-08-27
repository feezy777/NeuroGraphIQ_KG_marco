"""Macro Paper Full Text Availability Audit V1 审计脚本(零写入)。

任务:评估 46 篇 Macro Connection literature papers 的全文可用性,
用于后续正文级证据抽取(Full Text Evidence Extraction)。

审计对象:paper_sources 中 source=PubMed + metadata_json.mode=literature
的 46 篇论文(已有 PMID/DOI/abstract)。

数据来源(全部只读):
* paper_sources(DB 只读):paper_id / title / pmid / doi
* europepmc_cache.json(enrichment 阶段缓存):pmcid / inPMC /
  isOpenAccess / fullTextUrlList / hasTextMinedTerms —— 0 新增 API
* Europe PMC fullTextXML REST(仅对 11 篇有 PMC 的论文):
  GET https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML

分类(用户定义):
* A = 有全文 XML(fullTextXML 200 + XML 内容)
* B = 有 PMC 但无法解析(PMC ID 存在但 fullTextXML 不可用/为空)
* C = 只有摘要(无 PMC 收录)

约束(用户要求):
* 禁止创建全文表 —— 已确认无 paper_content/fulltext 表,本阶段不建
* 不修改任何数据库:paper_sources / connection / evidence_reference
  全不动 —— 仅生成 fulltext_availability_report.json

验证:运行前后 DB 状态指纹(paper_sources count + updated_at max)一致。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

import httpx
from sqlalchemy import text

from app.database import AsyncSessionLocal

OUT_DIR = Path(_backend) / "data" / "exports" / "macro_paper_fulltext_audit"
CACHE = Path(_backend) / "data" / "exports" / "macro_paper_enrichment" \
    / "europepmc_cache.json"

FULLTEXT_XML_URL = ("https://www.ebi.ac.uk/europepmc/webservices/rest/"
                    "{pmcid}/fullTextXML")
RATE_INTERVAL = 1.0 / 3.0  # 3 请求/秒
MAX_ATTEMPTS = 3
RETRY_BACKOFF = (1.0, 2.0)

STATUS_A = "A_full_text_xml"
STATUS_B = "B_pmc_but_unparsable"
STATUS_C = "C_abstract_only"


async def _db_fingerprint(session) -> tuple[int, str | None]:
    return (await session.execute(
        text("SELECT count(*) FROM paper_sources"))).scalar(), \
        (await session.execute(
            text("SELECT max(updated_at)::text FROM paper_sources"))).scalar()


class _RateLimiter:
    def __init__(self, interval: float):
        self.interval = interval
        self._last = 0.0

    async def wait(self) -> None:
        now = time.monotonic()
        wait = self._last + self.interval - now
        if wait > 0:
            await asyncio.sleep(wait)
        self._last = time.monotonic()


async def _check_fulltext_xml(client: httpx.AsyncClient, pmcid: str,
                              limiter: _RateLimiter) -> tuple[bool, str]:
    """验证 fullTextXML 可用性 → (available, reason)。"""
    url = FULLTEXT_XML_URL.format(pmcid=pmcid)
    last_err = ""
    for attempt in range(MAX_ATTEMPTS):
        try:
            await limiter.wait()
            r = await client.get(url, follow_redirects=True,
                                 timeout=httpx.Timeout(30.0))
            if r.status_code == 200 and r.text.strip().lstrip().startswith("<"):
                return True, f"fullTextXML HTTP 200 ({len(r.content)} bytes)"
            return False, f"fullTextXML HTTP {r.status_code}"
        except (httpx.HTTPError, asyncio.TimeoutError) as e:
            last_err = f"{type(e).__name__}: {e}"
            if attempt < MAX_ATTEMPTS - 1:
                await asyncio.sleep(RETRY_BACKOFF[attempt])
    return False, f"request failed after retries ({last_err})"


async def main(_args: argparse.Namespace) -> None:
    # ---- 0. 基线指纹(零写入验证) ----
    async with AsyncSessionLocal() as session:
        papers_before = await _db_fingerprint(session)

    # ---- 1. 加载 46 篇论文(只读) ----
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(text("""
            SELECT id, title, pmid, doi FROM paper_sources
            WHERE source='PubMed' AND metadata_json->>'mode'='literature'
            ORDER BY pmid"""))).all()
    papers = [{"paper_id": str(r[0]), "title": r[1] or "",
               "pmid": str(r[2]), "doi": r[3] or ""} for r in rows]
    assert len(papers) == 46, f"应为 46 篇,实际 {len(papers)}"
    print(f"papers={len(papers)}")

    # ---- 2. 合并 Europe PMC 缓存(0 新增 API) ----
    cache = json.loads(CACHE.read_text(encoding="utf-8"))
    results = cache.get("results", {})
    for p in papers:
        core = results.get(p["pmid"]) or {}
        p["pmc_id"] = core.get("pmcid") or ""
        p["in_pmc"] = core.get("inPMC") == "Y"
        p["is_open_access"] = core.get("isOpenAccess") == "Y"
        p["has_text_mined"] = core.get("hasTextMinedTerms") == "Y"
        urls = (core.get("fullTextUrlList") or {}).get("fullTextUrl") or []
        p["pdf_links"] = [u.get("url", "") for u in urls
                          if u.get("documentStyle") == "pdf" and u.get("url")]
    n_pmc = sum(1 for p in papers if p["pmc_id"])
    print(f"pmc_id={n_pmc} (fullTextXML 验证范围)")

    # ---- 3. fullTextXML 验证(仅 PMC 论文) ----
    async with httpx.AsyncClient(headers={"User-Agent":
                                          "NeuroGraphIQ-KG/1.0 (fulltext audit)"}) as client:
        limiter = _RateLimiter(RATE_INTERVAL)
        for p in papers:
            if not p["pmc_id"]:
                p["availability_status"] = STATUS_C
                p["reason"] = ("no PMC ID in Europe PMC"
                               f" ({len(p['pdf_links'])} external PDF links"
                               ", not XML)")
                continue
            available, reason = await _check_fulltext_xml(client, p["pmc_id"],
                                                          limiter)
            if available:
                p["availability_status"] = STATUS_A
                p["reason"] = reason
            else:
                p["availability_status"] = STATUS_B
                p["reason"] = reason
    print(f"A={sum(1 for p in papers if p['availability_status'] == STATUS_A)} "
          f"B={sum(1 for p in papers if p['availability_status'] == STATUS_B)} "
          f"C={sum(1 for p in papers if p['availability_status'] == STATUS_C)}")

    # ---- 4. 报告(唯一写入:报告文件) ----
    _export_report(papers)

    # ---- 5. 零写入验证 ----
    async with AsyncSessionLocal() as session:
        papers_after = await _db_fingerprint(session)
    assert papers_after == papers_before, "DB 状态变化(审计必须零写入)"
    print("[ok] zero-write verified: paper_sources count + updated_at 不变")


def _export_report(papers: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    counts = {STATUS_A: 0, STATUS_B: 0, STATUS_C: 0}
    for p in papers:
        counts[p["availability_status"]] += 1

    (OUT_DIR / "fulltext_availability_report.json").write_text(
        json.dumps({
            "analysis": "macro_paper_fulltext_availability_audit_v1",
            "task": "全文可用性审计报告(用于后续正文级证据抽取)",
            "scope": "46 篇 Macro Connection literature papers"
                     "(已有 PMID/DOI/abstract)",
            "classification": {
                "A_full_text_xml": "有全文 XML(Europe PMC fullTextXML 200)",
                "B_pmc_but_unparsable": "有 PMC 但无法解析",
                "C_abstract_only": "只有摘要(无 PMC 收录)",
            },
            "stats": {
                "total_papers": len(papers),
                "A_full_text_xml": counts[STATUS_A],
                "B_pmc_but_unparsable": counts[STATUS_B],
                "C_abstract_only": counts[STATUS_C],
                "with_pmc_id": sum(1 for p in papers if p["pmc_id"]),
                "with_external_pdf_links": sum(1 for p in papers
                                               if p["pdf_links"]),
                "open_access": sum(1 for p in papers if p["is_open_access"]),
            },
            "papers": [{
                "paper_id": p["paper_id"],
                "title": p["title"],
                "pmid": p["pmid"],
                "doi": p["doi"],
                "pmc_id": p["pmc_id"],
                "availability_status": p["availability_status"],
                "reason": p["reason"],
                "is_open_access": p["is_open_access"],
                "external_pdf_links": p["pdf_links"],
            } for p in papers],
            "next_step_note": "A 类论文可直接进入正文级证据抽取"
                              "(fullTextXML 为数据源);B/C 类需其他来源",
            "generated_at": now,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[ok] fulltext_availability_report.json -> {OUT_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Macro Paper Full Text Availability Audit V1(零写入)")
    parser.parse_args()
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main(parser.parse_args()))
