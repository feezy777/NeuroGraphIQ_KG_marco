"""Macro Evidence Literature PubMed Backfill V1 实施脚本。

任务:对 Literature Backfill 解析出的 C_local_unmatched 254 条文献线索
(author+year),按 本地 paper_sources → PubMed API 匹配策略补充 DOI/PMID,
生成 macro_evidence_pubmed_candidates —— 只生成 candidate,不修改
final_canonical_connections。

匹配策略(用户要求,按优先级):
  1. 作者 + 年份(local paper_sources → PubMed esearch)
  2. 作者 + 年份 + brain region keywords(多篇时 region 词消歧)
  3. title similarity(多篇时标题相似度消歧)

PubMed 约束:rate limit 3/s + 指数退避重试 3 次 + 本地 JSON 缓存
(二次运行 0 API 调用,幂等)。

输出 4 报告 → data/exports/macro_evidence_pubmed/:
  1. match_summary.json        —— 统计:matched/ambiguous/not_found,
                                 DOI/PMID 冲突检测,API 调用/缓存命中
  2. matched_candidates.json   —— 成功匹配(含 DOI/PMID)
  3. ambiguous_candidates.json —— 需人工确认
  4. not_found.json            —— 无法匹配

流程:
  1. 基线快照:final / canonical / mirror / lineage / clusters + evidence_count
  2. 只读加载:literature_candidates.json + lineage + mirror + paper_sources
  3. 唯一查询集 → PubmedClient(缓存)逐 query esearch+esummary
  4. build_pubmed_candidates(纯函数)分级
  5. 零写入断言:5 计数器 + evidence_count 前后一致(仅只读)
  6. 导出 4 报告

不执行:创建/删除连接、修改任何字段、promotion、CN2 inference、LLM 调用、
建表、自动写入 final。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services.macro_evidence_literature_service import (
    build_local_paper_library,
)
from app.services.macro_evidence_pubmed_service import (
    build_pubmed_candidates,
    full_query,
    match_summary,
    split_by_status,
)
from app.services.pubmed_client import PubmedClient

OUT_DIR = Path(_backend) / "data" / "exports" / "macro_evidence_pubmed"
CACHE_FILE = OUT_DIR / "cache" / "pubmed_cache.json"
LIT_REPORT = Path(_backend) / "data" / "exports" / "macro_evidence_literature" \
    / "literature_candidates.json"

COUNTER_SQL = {
    "final_active": "SELECT count(*) FROM final_canonical_connections WHERE final_status='active'",
    "canonical": "SELECT count(*) FROM canonical_connections",
    "mirror_macro": "SELECT count(*) FROM mirror_region_connections WHERE granularity_level='macro'",
    "lineage": "SELECT count(*) FROM canonical_connection_lineage",
    "clusters": "SELECT count(*) FROM mirror_connection_clusters",
}


async def _counters(session) -> dict[str, int]:
    out = {}
    for name, sql in COUNTER_SQL.items():
        out[name] = (await session.execute(text(sql))).scalar()
    return out


async def main(_args: argparse.Namespace) -> None:
    # ---- 1. 基线快照 ----
    async with AsyncSessionLocal() as session:
        counters_before = await _counters(session)
        ev_before = (await session.execute(text(
            """SELECT count(*), coalesce(sum(jsonb_array_length(
                     coalesce(evidence_summary->'supporting_records','[]'::jsonb))), 0)
               FROM final_canonical_connections WHERE final_status='active'"""))).one()
        print(f"baseline: {counters_before} | evidence_records_total={ev_before[1]}")

    # ---- 2. 只读加载 ----
    lit = json.loads(LIT_REPORT.read_text(encoding="utf-8"))
    lit_cands = [c for c in lit["candidates"]
                 if c.get("match_status") != "A_unique"]
    print(f"literature candidates: {len(lit['candidates'])} → "
          f"pubmed scope {len(lit_cands)} (skip A_unique)")

    async with AsyncSessionLocal() as session:
        lineage_rows = (await session.execute(text(
            """SELECT canonical_id, cluster_id, mirror_connection_ids
               FROM canonical_connection_lineage"""))).all()
        lineage_map: dict[str, list[dict]] = {}
        for r in lineage_rows:
            lineage_map.setdefault(str(r[0]), []).append({
                "cluster_id": str(r[1]), "mirror_connection_ids": r[2] or []})
        print(f"lineage rows: {len(lineage_rows)}")

        mirror_rows = (await session.execute(text(
            """SELECT id, evidence_text FROM mirror_region_connections
               WHERE granularity_level='macro'"""))).all()
        mirror_map = {str(r[0]): {"evidence_text": r[1]} for r in mirror_rows}
        print(f"mirror macro: {len(mirror_map)}")

        paper_rows = (await session.execute(text(
            """SELECT publication_year, metadata_json, doi, pmid, title,
                      journal, source
               FROM paper_sources"""))).all()
        paper_dicts = [{"publication_year": r[0], "metadata_json": r[1],
                        "doi": r[2], "pmid": str(r[3]) if r[3] else "",
                        "title": r[4], "journal": r[5], "source": r[6]}
                       for r in paper_rows]
        library = build_local_paper_library(paper_dicts)
        print(f"paper_sources: {len(paper_dicts)} → library {len(library)}")

    # ---- 3. PubMed 查询(唯一查询集 + 缓存 + 限流 + 重试) ----
    queries = sorted({q for c in lit_cands
                      if (q := full_query(c.get("author") or "",
                                          c.get("year") or "", []))})
    print(f"unique pubmed queries: {len(queries)} "
          f"(rate limit 3/s, retry 3, cache {CACHE_FILE})")

    client = PubmedClient(cache_path=CACHE_FILE, rate_limit_per_sec=3.0)
    client.load_cache()
    hits_map: dict[str, list[dict]] = {}
    for i, q in enumerate(queries, 1):
        hits_map[q] = await client.lookup(q)
        if i % 50 == 0 or i == len(queries):
            print(f"  [{i}/{len(queries)}] cached={client.cache_hits} "
                  f"api={client.api_calls} retries={client.retries}")
    client.save_cache()
    print(f"pubmed done: api_calls={client.api_calls} "
          f"cache_hits={client.cache_hits} retries={client.retries}")
    await client.aclose()

    # ---- 4. 候选构建 + 分级(纯函数) ----
    def lookup(q: str) -> list[dict]:
        return hits_map.get(q, [])

    candidates = build_pubmed_candidates(lit_cands, lineage_map, mirror_map,
                                         library, lookup, do_pubmed=True)
    summary = match_summary(candidates)
    print(f"candidates: {summary['by_status']} "
          f"| connections: {summary['by_connection']} "
          f"| methods: {summary['by_match_method']}")

    # ---- 5. 零写入断言 ----
    async with AsyncSessionLocal() as session:
        counters_after = await _counters(session)
        ev_after = (await session.execute(text(
            """SELECT count(*), coalesce(sum(jsonb_array_length(
                     coalesce(evidence_summary->'supporting_records','[]'::jsonb))), 0)
               FROM final_canonical_connections WHERE final_status='active'"""))).one()
        for name, before in counters_before.items():
            assert counters_after[name] == before, f"{name} 数量变化(禁止写入)"
        assert ev_after[0] == ev_before[0] and ev_after[1] == ev_before[1], \
            "evidence_count 变化(禁止写入)"
        print("[ok] zero-write verified: 5 counters + evidence_count unchanged")

    # ---- 6. 导出 ----
    _export_reports(candidates, summary, client, len(queries), counters_before)
    print(f"[ok] 4 reports -> {OUT_DIR}")


def _export_reports(candidates: list[dict], summary: dict,
                    client: PubmedClient, query_count: int,
                    counters_before: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    groups = split_by_status(candidates)

    def _write(name: str, data: dict) -> None:
        (OUT_DIR / name).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[ok] {name}")

    _write("match_summary.json", {
        "analysis": "macro_evidence_pubmed_backfill_v1",
        "task": "匹配统计",
        "scope": "C_local_unmatched 254 条(author+year)文献线索 → "
                 "local paper_sources + PubMed API 匹配分级",
        "baseline_counters": counters_before,
        "pubmed_calls": {
            "unique_queries": query_count,
            "api_calls": client.api_calls,
            "cache_hits": client.cache_hits,
            "retries": client.retries,
            "rate_limit_per_sec": 3.0,
            "note": "二次运行全部命中缓存 → 0 API 调用(幂等)",
        },
        "summary": summary,
        "generated_at": now,
    })
    _write("matched_candidates.json", {
        "analysis": "macro_evidence_pubmed_backfill_v1",
        "task": "成功匹配",
        "candidates": groups["matched"],
        "generated_at": now,
    })
    _write("ambiguous_candidates.json", {
        "analysis": "macro_evidence_pubmed_backfill_v1",
        "task": "需人工确认(多篇候选无法消歧)",
        "candidates": groups["ambiguous"],
        "generated_at": now,
    })
    _write("not_found.json", {
        "analysis": "macro_evidence_pubmed_backfill_v1",
        "task": "无法匹配(本地+PubMed 均无)",
        "candidates": groups["not_found"],
        "generated_at": now,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Macro Evidence Literature PubMed Backfill V1"
                    "(只读 + PubMed 检索,不写 final)")
    parser.parse_args()
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main(parser.parse_args()))
