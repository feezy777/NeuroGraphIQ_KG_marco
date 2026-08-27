"""Macro Paper Full Text Evidence Extraction V1 实施脚本。

任务:基于 3 篇 Europe PMC fullTextXML 论文(审计 A 类)建立正文级
evidence segment 抽取 —— 从全文章节(Introduction/Methods/Results/
Discussion/Figure)按句抽取连接证据片段,写入
paper_connection_evidence_segments(evidence_source_type='paper_fulltext')。

约束(用户要求):
* 不修改已有摘要证据(摘要段 evidence_source_type='paper_abstract' 不动)
* 新增正文证据来源区分:evidence_source_type + section_name
* FullText XML 处理:解析 title/abstract/body sections,按段落切分
* 证据抽取规则:复用 region resolver;source+target region 同一句或
  相邻句出现 + connection/projection/connectivity/tract/pathway/
  connected/innervation 等连接语义
* 只保存论文原文真实文本(禁止 LLM 生成不存在的证据)
* 只允许关联已有 connection_paper_evidence 中的 connection
* 禁止修改 Final Connection / paper_sources / evidence_reference

流程:
  1. 应用迁移(IF NOT EXISTS 幂等)+ 基线快照(5 counters +
     evidence_count + papers 616 + links 104 + 摘要级 segments 104)
  2. 下载 3 篇 fullTextXML(缓存 data/exports/macro_paper_fulltext/xml/,
     复跑 0 API)
  3. 加载 104 关联,取属于 3 篇全文论文的 8 条 → JATS 解析 + 规则抽取
  4. 幂等写入 INSERT ON CONFLICT (paper_id, connection_id,
     evidence_source_type) DO NOTHING
  5. 断言:paper_sources / connection_paper_evidence / Final /
     evidence_reference / counters / 摘要级 segments 全不变
  6. 报告 → data/exports/macro_paper_fulltext_evidence/
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

import httpx
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services.macro_paper_fulltext_evidence_service import (
    EXTRACTION_METHOD,
    INSERT_FULLTEXT_SEGMENT_SQL,
    SOURCE_TYPE_ABSTRACT,
    SOURCE_TYPE_FULLTEXT,
    STATUS_EXTRACTED,
    STATUS_NO_DIRECT_EVIDENCE,
    build_fulltext_segment,
    parse_jats_xml,
)

OUT_DIR = Path(_backend) / "data" / "exports" / "macro_paper_fulltext_evidence"
XML_DIR = OUT_DIR / "xml"
MIGRATION = Path(_backend) / "migrations" / \
    "20260913_segments_fulltext_columns.sql"

# 审计 A 类 3 篇(pmid → pmcid,来自 fulltext_availability_report.json)
FULLTEXT_PAPERS = {
    "22917615": "PMC3480641",
    "23378834": "PMC3561664",
    "31267374": "PMC6867988",
}

FULLTEXT_XML_URL = ("https://www.ebi.ac.uk/europepmc/webservices/rest/"
                    "{pmcid}/fullTextXML")
RATE_INTERVAL = 1.0 / 3.0  # 3 请求/秒
MAX_ATTEMPTS = 3
RETRY_BACKOFF = (1.0, 2.0)

COUNTER_SQL = {
    "final_active": "SELECT count(*) FROM final_canonical_connections WHERE final_status='active'",
    "canonical": "SELECT count(*) FROM canonical_connections",
    "mirror_macro": "SELECT count(*) FROM mirror_region_connections WHERE granularity_level='macro'",
    "lineage": "SELECT count(*) FROM canonical_connection_lineage",
    "clusters": "SELECT count(*) FROM mirror_connection_clusters",
}

EVIDENCE_COUNT_SQL = """\
SELECT count(*), coalesce(sum(jsonb_array_length(
         coalesce(evidence_summary->'supporting_records','[]'::jsonb))), 0)
  FROM final_canonical_connections WHERE final_status='active'"""


async def _counters(session) -> dict[str, int]:
    out = {}
    for name, sql in COUNTER_SQL.items():
        out[name] = (await session.execute(text(sql))).scalar()
    return out


async def _evidence_count(session) -> tuple[int, int]:
    return (await session.execute(text(EVIDENCE_COUNT_SQL))).one()


async def _segment_counts(session) -> tuple[int, int]:
    row = (await session.execute(text(
        "SELECT count(*) FILTER (WHERE evidence_source_type='paper_abstract'),"
        "       count(*) FILTER (WHERE evidence_source_type='paper_fulltext')"
        "  FROM paper_connection_evidence_segments"))).one()
    return int(row[0]), int(row[1])


async def apply_migration() -> None:
    """幂等应用迁移(ADD COLUMN IF NOT EXISTS)。"""
    sql = MIGRATION.read_text(encoding="utf-8")
    async with AsyncSessionLocal() as session:
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                await session.execute(text(stmt))
        await session.commit()
    print(f"[ok] migration applied: {MIGRATION.name}")


async def _download_xmls() -> tuple[dict[str, str], int]:
    """下载 3 篇 fullTextXML → {pmid: xml_text} + 新增下载数(缓存命中 0)。"""
    XML_DIR.mkdir(parents=True, exist_ok=True)
    fetched = 0
    xmls: dict[str, str] = {}
    async with httpx.AsyncClient(headers={"User-Agent":
                                          "NeuroGraphIQ-KG/1.0 (fulltext evidence)"}) as client:
        for pmid, pmcid in FULLTEXT_PAPERS.items():
            cache = XML_DIR / f"{pmid}.xml"
            if cache.exists():
                xmls[pmid] = cache.read_text(encoding="utf-8")
                continue
            url = FULLTEXT_XML_URL.format(pmcid=pmcid)
            last_err = ""
            for attempt in range(MAX_ATTEMPTS):
                try:
                    await asyncio.sleep(RATE_INTERVAL)
                    r = await client.get(url, follow_redirects=True,
                                         timeout=httpx.Timeout(30.0))
                    if r.status_code == 200 and r.text.strip().startswith("<"):
                        cache.write_text(r.text, encoding="utf-8")
                        xmls[pmid] = r.text
                        fetched += 1
                        break
                    last_err = f"HTTP {r.status_code}"
                except (httpx.HTTPError, asyncio.TimeoutError) as e:
                    last_err = f"{type(e).__name__}: {e}"
                    if attempt < MAX_ATTEMPTS - 1:
                        await asyncio.sleep(RETRY_BACKOFF[attempt])
            if pmid not in xmls:
                print(f"[warn] {pmid} fullTextXML 获取失败({last_err}),"
                      "该论文关联将标记 no_fulltext_xml")
    print(f"xmls downloaded={fetched} (cache {len(xmls) - fetched})")
    return xmls, fetched


async def main(_args: argparse.Namespace) -> None:
    # ---- 0. 迁移 + 基线快照 ----
    await apply_migration()
    async with AsyncSessionLocal() as session:
        counters_before = await _counters(session)
        ev_before = await _evidence_count(session)
        papers_before = (await session.execute(
            text("SELECT count(*) FROM paper_sources"))).scalar()
        links_before = (await session.execute(
            text("SELECT count(*) FROM connection_paper_evidence"))).scalar()
        abs_before, ft_before = await _segment_counts(session)
    print(f"baseline: {counters_before} | evidence_count={ev_before[1]} "
          f"| papers={papers_before} | links={links_before} "
          f"| abstract_segments={abs_before} fulltext_segments={ft_before}")

    # ---- 1. 下载 fullTextXML(缓存复用) ----
    xmls, downloaded = await _download_xmls()

    # ---- 2. 加载关联 + 连接 + region(全 104,只处理 3 篇论文的 8 条) ----
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(text("""
            SELECT l.paper_id, l.connection_id, e.pmid,
                   fc.connection_type,
                   r1.canonical_name_en, r2.canonical_name_en,
                   r1.id, r2.id
            FROM connection_paper_evidence l
            JOIN paper_sources e ON e.id = l.paper_id
            JOIN final_canonical_connections fc ON fc.id = l.connection_id
            LEFT JOIN canonical_brain_regions r1 ON r1.id = fc.source_region_id
            LEFT JOIN canonical_brain_regions r2 ON r2.id = fc.target_region_id
            ORDER BY e.pmid, l.connection_id"""))).all()
        alias_rows = (await session.execute(text(
            "SELECT region_id, alias FROM canonical_region_aliases"))).all()
    aliases: dict[str, list[str]] = {}
    for rid, alias in alias_rows:
        if rid is not None and alias:
            aliases.setdefault(str(rid), []).append(alias)
    links = [{"paper_id": str(r[0]), "connection_id": str(r[1]),
              "pmid": str(r[2]), "connection_type": r[3],
              "source_name": r[4], "target_name": r[5],
              "source_region_id": str(r[6]) if r[6] else None,
              "target_region_id": str(r[7]) if r[7] else None}
             for r in rows]
    assert len(links) == 104, f"关联应为 104,实际 {len(links)}"

    ft_links = [l for l in links if l["pmid"] in FULLTEXT_PAPERS]
    print(f"links={len(links)} fulltext_papers=3 "
          f"ft_links={len(ft_links)} (aliases={len(aliases)})")

    # ---- 3. JATS 解析统计 + 规则抽取 ----
    parsed_stats: dict[str, dict] = {}
    segments = []
    for link in ft_links:
        xml_text = xmls.get(link["pmid"])
        if xml_text:
            try:
                parsed = parse_jats_xml(xml_text)
                n_sections = len(parsed["sections"])
                n_paras = sum(len(s["paragraphs"])
                              for s in parsed["sections"])
            except Exception:
                n_sections = n_paras = 0
            parsed_stats[link["pmid"]] = {"sections": n_sections,
                                          "paragraphs": n_paras}
        seg = build_fulltext_segment(
            link["paper_id"], link["connection_id"], link["pmid"],
            link["connection_type"], xml_text,
            link["source_name"] or "", link["target_name"] or "",
            aliases.get(link["source_region_id"] or "", []),
            aliases.get(link["target_region_id"] or "", []))
        seg["_pmid"] = link["pmid"]
        segments.append(seg)
    n_extracted = sum(1 for s in segments if s["status"] == STATUS_EXTRACTED)
    n_nde = sum(1 for s in segments if s["status"] == STATUS_NO_DIRECT_EVIDENCE)
    n_covered_conn = len({s["connection_id"] for s in segments
                          if s["status"] == STATUS_EXTRACTED})
    print(f"ft_links={len(segments)} extracted={n_extracted} "
          f"no_direct_evidence={n_nde} covered_connections={n_covered_conn}")

    # ---- 4. 幂等写入 ----
    inserted = 0
    async with AsyncSessionLocal() as session:
        for s in segments:
            result = (await session.execute(
                text(INSERT_FULLTEXT_SEGMENT_SQL),
                {"paper_id": s["paper_id"],
                 "connection_id": s["connection_id"],
                 "evidence_text": s["evidence_text"],
                 "evidence_location": s["evidence_location"],
                 "extraction_method": s["extraction_method"],
                 "confidence": s["confidence"],
                 "provenance_json": json.dumps(
                     s["provenance_json"], ensure_ascii=False),
                 "status": s["status"],
                 "evidence_source_type": s["evidence_source_type"],
                 "section_name": s["section_name"]})).first()
            if result:
                inserted += 1
        await session.commit()
    print(f"fulltext segments inserted={inserted}/{len(segments)}")

    # ---- 5. 断言:零副作用(含摘要级 segments 不变) ----
    async with AsyncSessionLocal() as session:
        counters_after = await _counters(session)
        ev_after = await _evidence_count(session)
        papers_after = (await session.execute(
            text("SELECT count(*) FROM paper_sources"))).scalar()
        links_after = (await session.execute(
            text("SELECT count(*) FROM connection_paper_evidence"))).scalar()
        abs_after, ft_after = await _segment_counts(session)
        for name, before in counters_before.items():
            assert counters_after[name] == before, \
                f"{name} 数量变化(禁止写入)"
        assert ev_after == ev_before, "evidence_count 变化(禁止写入)"
        assert papers_after == papers_before, "paper_sources 数量变化"
        assert links_after == links_before, "connection_paper_evidence 数量变化"
        assert abs_after == abs_before, "摘要级 segments 被修改(禁止)"
        assert ft_after == ft_before + inserted, "正文级 segments 净增 != 写入数"
    print("[ok] zero-side-effect: 5 counters + evidence_count + papers + "
          "links + abstract_segments 全不变")

    # ---- 6. 报告 + 验收 ----
    await _export_reports(counters_before, papers_before, links_before,
                          ev_before[1], abs_before, segments, inserted,
                          parsed_stats, downloaded)


async def _export_reports(counters: dict, papers_before: int,
                          links_before: int, evidence_count: int,
                          abs_segments: int, segments: list[dict],
                          inserted: int, parsed_stats: dict,
                          downloaded: int) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    extracted = [s for s in segments if s["status"] == STATUS_EXTRACTED]
    nde = [s for s in segments if s["status"] == STATUS_NO_DIRECT_EVIDENCE]

    # 每篇论文覆盖(只统计 3 篇全文论文)
    per_paper: dict[str, dict] = {}
    for pmid, pmcid in FULLTEXT_PAPERS.items():
        p = per_paper[pmid] = {"pmid": pmid, "pmc_id": pmcid,
                               "links": 0, "extracted": 0,
                               "no_direct_evidence": 0,
                               "sections": parsed_stats.get(pmid, {}).get(
                                   "sections", 0),
                               "paragraphs": parsed_stats.get(pmid, {}).get(
                                   "paragraphs", 0),
                               "segments": []}
    for s in segments:
        p = per_paper[s["_pmid"]]
        p["links"] += 1
        if s["status"] == STATUS_EXTRACTED:
            p["extracted"] += 1
            p["segments"].append({
                "connection_id": s["connection_id"],
                "section_name": s["section_name"],
                "evidence_text": s["evidence_text"],
                "evidence_location": s["evidence_location"],
                "confidence": s["confidence"],
                "matched": s.get("matched_regions", {}),
            })
        else:
            p["no_direct_evidence"] += 1

    conf_dist = Counter(s["confidence"] for s in extracted)
    sec_dist = Counter(s["section_name"] for s in extracted)
    per_conn = [{
        "connection_id": s["connection_id"],
        "pmid": s["_pmid"],
        "status": s["status"],
        "source_type": SOURCE_TYPE_FULLTEXT,
        "section_name": s["section_name"],
        "confidence": s["confidence"],
        "evidence_text": s["evidence_text"],
        "evidence_location": s["evidence_location"],
        "matched_terms": s.get("matched_regions", {}),
        "reason": s["provenance_json"].get("reason", ""),
    } for s in segments]

    def _write(name: str, data: dict) -> None:
        (OUT_DIR / name).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[ok] {name}")

    _write("fulltext_evidence_report.json", {
        "analysis": "macro_paper_fulltext_evidence_extraction_v1",
        "task": "正文级证据片段抽取报告(fullTextXML → segments)",
        "source": "Europe PMC fullTextXML(JATS)",
        "extraction_method": EXTRACTION_METHOD,
        "stats": {
            "fulltext_papers": len(FULLTEXT_PAPERS),
            "parsed_sections": sum(p["sections"] for p in per_paper.values()),
            "parsed_paragraphs": sum(p["paragraphs"]
                                     for p in per_paper.values()),
            "ft_links_processed": len(segments),
            "extracted": len(extracted),
            "no_direct_evidence": len(nde),
            "covered_connections": len({s["connection_id"] for s in extracted}),
            "papers_without_evidence": sum(
                1 for p in per_paper.values() if p["extracted"] == 0),
            "xml_downloaded_this_run": downloaded,
        },
        "confidence_distribution": {
            str(k): v for k, v in sorted(conf_dist.items(), reverse=True)},
        "section_distribution": dict(
            sorted(sec_dist.items(), key=lambda kv: -kv[1])),
        "per_paper_coverage": sorted(
            per_paper.values(), key=lambda p: p["pmid"]),
        "per_connection": per_conn,
        "generated_at": now,
    })
    _write("acceptance_report.json", {
        "analysis": "macro_paper_fulltext_evidence_extraction_v1",
        "stage": "Macro Paper Full Text Evidence Extraction V1 验收报告",
        "date": "2026-08-25",
        "execution": {
            "script": "scripts/run_macro_paper_fulltext_evidence.py",
            "service": "app/services/macro_paper_fulltext_evidence_service.py",
            "migration": "migrations/20260913_segments_fulltext_columns.sql",
            "tests": "test_macro_paper_fulltext_evidence.py (19)",
        },
        "answers": {
            "fulltext_papers": 3,
            "parsed_paragraphs": sum(p["paragraphs"]
                                     for p in per_paper.values()),
            "evidence_produced": len(extracted),
            "connections_covered": len({s["connection_id"]
                                        for s in extracted}),
            "papers_without_evidence": sum(
                1 for p in per_paper.values() if p["extracted"] == 0),
            "quality_report": {
                "confidence": dict(sorted(conf_dist.items(), reverse=True)),
                "sections": dict(sorted(sec_dist.items(),
                                        key=lambda kv: -kv[1])),
                "note": "evidence_text 均为论文原文逐字片段;"
                        "连接语义词是命中必要条件;无支持句不生成",
            },
        },
        "constraints_verified": {
            "abstract_segments_unchanged": f"{abs_segments} 摘要级 segments "
                                           "前后一致(未修改已有摘要证据)",
            "paper_sources_count_unchanged": f"{papers_before} 前后一致",
            "connection_paper_evidence_count_unchanged": f"{links_before} 前后一致",
            "final_active_unchanged": f"{counters['final_active']} 前后一致",
            "canonical_unchanged": f"{counters['canonical']} 前后一致",
            "mirror_macro_unchanged": f"{counters['mirror_macro']} 前后一致",
            "lineage_unchanged": f"{counters['lineage']} 前后一致",
            "clusters_unchanged": f"{counters['clusters']} 前后一致",
            "evidence_count_unchanged": f"{evidence_count} 前后一致",
            "evidence_reference_untouched": "本阶段未修改 evidence_reference",
            "evidence_text_verbatim": "片段逐字取自 fullTextXML 原文"
                                      "(解析自 JATS 段落,非生成)",
            "no_direct_evidence_marked": f"{len([s for s in segments if s['status'] == STATUS_NO_DIRECT_EVIDENCE])} "
                                         "条标记 status=no_direct_evidence",
            "provenance_recorded": "source=paper_fulltext/paper_id/pmid/"
                                   "extraction_method/section_name(每条)",
            "connection_association_restricted": "仅关联已有 "
                                                 "connection_paper_evidence "
                                                 "连接,未创建新连接",
            "idempotent": "INSERT ON CONFLICT (paper_id, connection_id, "
                          "evidence_source_type) DO NOTHING → 复跑 0 新增,"
                          "XML 缓存命中 0 下载",
            "no_final_connection_change": True,
            "no_paper_sources_change": True,
            "no_ontology_change": True,
            "no_new_connection": True,
            "no_llm_calls": True,
        },
        "conclusion": (
            f"{len(FULLTEXT_PAPERS)} 篇全文论文解析 "
            f"{sum(p['paragraphs'] for p in per_paper.values())} 段落,"
            f"{len(extracted)} 条正文级证据片段(覆盖 "
            f"{len({s['connection_id'] for s in extracted})} 连接,"
            f"{sum(1 for p in per_paper.values() if p['extracted'] == 0)} 篇"
            "无证据);摘要级证据未动,正文级证据来源已区分"
            "(evidence_source_type=paper_fulltext + section_name)。"
        ),
        "generated_at": now,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Macro Paper Full Text Evidence Extraction V1"
                    "(fullTextXML → 正文级连接证据片段,规则抽取,幂等)")
    parser.parse_args()
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main(parser.parse_args()))
