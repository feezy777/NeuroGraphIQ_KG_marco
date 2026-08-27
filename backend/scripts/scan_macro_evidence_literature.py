"""Macro Evidence Literature Backfill V1 实施脚本(只读分析,零写入)。

任务:将 Macro Final Connection 对应 mirror evidence_text 中的文献线索
(作者+年份)解析为结构化 candidate,并与本地 paper 库(paper_sources)
匹配分级(A/B/C),为后续 PubMed API 文献回填提供候选清单。

输出 3 报告 → data/exports/macro_evidence_literature/:
  1. literature_candidates.json    —— 任务 1+2:全部解析出的文献候选
  2. literature_match_report.json  —— 任务 3:A/B/C 质量分级统计
  3. priority_literature_analysis.json —— 任务 4:829 条低质量连接优先分析

流程:
  1. 基线快照:final / canonical / mirror / lineage / clusters + evidence_count 汇总
  2. 只读加载:final 2485 + lineage 4087 + mirror 5720(evidence_text)+
     paper_sources 570(本地匹配库)+ priority A 829(final ids,来自
     data/exports/macro_evidence_enrichment/priority_evidence_enrichment.json)
  3. scan_literature_candidates(纯函数)→ 候选 + 匹配分级
  4. literature_match_report / priority_literature_stats(纯函数)
  5. 零写入断言:5 计数器 + evidence_count 前后一致(仅只读)
  6. 导出 3 报告

不执行:创建/删除连接、修改任何字段(含 evidence_reference)、promotion、
CN2 inference、LLM/PubMed 调用、建表、自动写入 paper。
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
    literature_match_report,
    priority_literature_stats,
    scan_literature_candidates,
)

OUT_DIR = Path(_backend) / "data" / "exports" / "macro_evidence_literature"
PRIORITY_REPORT = Path(_backend) / "data" / "exports" / "macro_evidence_enrichment" \
    / "priority_evidence_enrichment.json"

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
    # ---- 1. 基线快照(含 evidence_count 汇总) ----
    async with AsyncSessionLocal() as session:
        counters_before = await _counters(session)
        ev_before = (await session.execute(text(
            """SELECT count(*), coalesce(sum(jsonb_array_length(
                     coalesce(evidence_summary->'supporting_records','[]'::jsonb))), 0)
               FROM final_canonical_connections WHERE final_status='active'"""))).one()
        print(f"baseline: {counters_before} | evidence_records_total={ev_before[1]}")

    # ---- 2. 只读加载 ----
    async with AsyncSessionLocal() as session:
        final_rows = (await session.execute(text(
            """SELECT id, canonical_connection_id, connection_code
               FROM final_canonical_connections WHERE final_status='active'"""))).all()
        finals = [{"id": str(r[0]), "canonical_connection_id": str(r[1]),
                   "connection_code": r[2]} for r in final_rows]
        print(f"final active: {len(finals)}")

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

    # 829 条优先连接(evidence enrichment A 类)
    priority_ids: set[str] = set()
    if PRIORITY_REPORT.exists():
        pr = json.loads(PRIORITY_REPORT.read_text(encoding="utf-8"))
        priority_ids = {p["connection_id"] for p in pr.get("A_high_priority", [])}
        print(f"priority A (低质量)连接: {len(priority_ids)}")
    else:
        print(f"[warn] 未找到 {PRIORITY_REPORT} —— 829 优先分析跳过")

    # ---- 3. 扫描 + 分级(纯函数) ----
    candidates = scan_literature_candidates(finals, lineage_map, mirror_map, library)
    report = literature_match_report(candidates)
    print(f"candidates: {report['by_candidate']}")
    print(f"by_connection: {report['by_connection']}")

    # ---- 4. 零写入断言(只读) ----
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

    # ---- 5. 导出 ----
    _export_reports(candidates, report, priority_ids, len(paper_dicts), counters_before)
    print(f"[ok] 3 reports -> {OUT_DIR}")


def _export_reports(candidates: list[dict], report: dict, priority_ids: set[str],
                    paper_count: int, counters_before: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    def _write(name: str, data: dict) -> None:
        (OUT_DIR / name).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[ok] {name}")

    # 1) literature_candidates.json — 任务 1+2
    _write("literature_candidates.json", {
        "analysis": "macro_evidence_literature_backfill_v1",
        "task": "1+2",
        "scope": "final → lineage → mirror evidence_text 文献线索扫描 + 本地库匹配",
        "local_paper_library": {
            "paper_sources_rows": paper_count,
            "note": "项目已有 paper_sources(570 行 europepmc,含 doi/pmid/publication_year/authors)、"
                    "paper_evidence_extraction_items(340 行)、mirror_evidence_records(99,481 行,"
                    "macro 连接层仅 2 行有 paper 关联) —— 不新增表",
        },
        "parsing_patterns": {
            "author_et_al_year": "Goldman-Rakic et al. (1984)",
            "paren_author_comma_year": "(Habas et al., 2009)",
            "ampersand_authors": "Petrides & Pandya (2002)",
            "initials_format": "Mesulam, M.M. (1995). Title. Journal.",
        },
        "candidates": candidates,
        "generated_at": now,
    })

    # 2) literature_match_report.json — 任务 3
    _write("literature_match_report.json", {
        "analysis": "macro_evidence_literature_backfill_v1",
        "task": 3,
        "grading": {
            "A_unique": "明确作者+年份,本地库唯一匹配(1 篇)",
            "B_multiple": "作者+年份,本地库多篇候选",
            "C_local_unmatched": "解析成功但本地库无匹配",
            "C_no_clue": "连接无文献线索(不计入 candidates,在连接级统计)",
        },
        "report": report,
        "generated_at": now,
    })

    # 3) priority_literature_analysis.json — 任务 4
    priority = priority_literature_stats(candidates, priority_ids,
                                         len(priority_ids))
    _write("priority_literature_analysis.json", {
        "analysis": "macro_evidence_literature_backfill_v1",
        "task": 4,
        "scope": "829 条低质量证据连接(evidence enrichment A 类)优先文献回填分析",
        "stats": {
            "priority_total": priority["priority_total"],
            "with_citation_clue": priority["with_citation_clue"],
            "no_citation_clue": priority["no_citation_clue"],
            "matchable": priority["matchable"],
            "matchable_unique": priority["matchable_unique"],
            "unmatchable": priority["unmatchable"],
            "by_candidate_status": priority["by_candidate_status"],
        },
        "priority_candidates": priority["priority_candidates"],
        "generated_at": now,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Macro Evidence Literature Backfill V1(只读分析)")
    parser.parse_args()
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main(parser.parse_args()))
