"""Macro Evidence Lineage Recovery V1 实施脚本(只读预览,零写入)。

任务:沿 final ↓ canonical_connection_lineage ↓ mirror_connection_ids ↓
mirror_evidence_records / mirror_region_connections.evidence_text 恢复
结构化文献引用(paper/DOI/PMID),产出 preview —— 回填前不改 final 表。

输出 4 报告 → data/exports/macro_evidence_lineage_recovery/:
  1. coverage_before.json            —— 回填前现状(evidence_reference 覆盖率
      + 链路审计统计:evidence_records 分布/孤儿/仅 2 条 macro 结构化)
  2. coverage_after_preview.json     —— 恢复后预览(A/B/C/D 分级、覆盖率)
  3. literature_recovery_candidates.json —— 可恢复文献引用的 final 清单
  4. unresolved_evidence.json        —— 无法恢复的 final 清单(需 LLM 补证据)

流程:
  1. 基线快照:final / canonical / mirror / lineage / clusters + evidence_count
  2. 只读加载:final 2485 + lineage 4087 + mirror macro 5720(evidence_text)
     + evidence_records(仅 lineage 命中行,当前 2 条)+ paper_sources 570
  3. plan_lineage_recovery(纯函数)→ 恢复预览
  4. 零写入断言:5 计数器 + evidence_count 前后一致(仅只读)
  5. 导出 4 报告

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
from app.services.macro_evidence_lineage_recovery_service import (
    coverage_after_preview,
    coverage_before,
    literature_recovery_candidates,
    plan_lineage_recovery,
    unresolved_evidence,
)
from app.services.macro_evidence_literature_service import (
    build_local_paper_library,
)

OUT_DIR = Path(_backend) / "data" / "exports" / "macro_evidence_lineage_recovery"

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


async def _audit_evidence_records(session) -> dict:
    """链路审计统计(写入 coverage_before 附录)。"""
    total = (await session.execute(text(
        "SELECT count(*) FROM mirror_evidence_records"))).scalar()
    by_type = (await session.execute(text(
        "SELECT evidence_target_type, count(*) FROM mirror_evidence_records "
        "GROUP BY evidence_target_type ORDER BY count(*) DESC"))).all()
    join_macro = (await session.execute(text(
        """SELECT count(*) FROM mirror_evidence_records er
           JOIN mirror_region_connections mc ON er.evidence_target_id = mc.id
           WHERE mc.granularity_level='macro'"""))).scalar()
    orphan = (await session.execute(text(
        """SELECT count(*) FROM mirror_evidence_records er
           LEFT JOIN mirror_region_connections mc ON er.evidence_target_id = mc.id
           WHERE mc.id IS NULL"""))).scalar()
    structured = (await session.execute(text(
        """SELECT count(*) FILTER (WHERE paper_doi IS NOT NULL AND paper_doi<>''),
                  count(*) FILTER (WHERE paper_pmid IS NOT NULL AND paper_pmid<>''),
                  count(*) FILTER (WHERE citation_json IS NOT NULL)
           FROM mirror_evidence_records"""))).one()
    return {
        "total_evidence_records": total,
        "by_target_type": {t: c for t, c in by_type},
        "join_macro_connections": join_macro,
        "orphan_not_joined": orphan,
        "structured_field_coverage": {
            "paper_doi_nonempty": structured[0],
            "paper_pmid_nonempty": structured[1],
            "citation_json_present": structured[2],
        },
        "note": ("macro 粒度连接在 mirror_evidence_records 中仅 "
                 f"{join_macro} 条结构化文献证据(其余 94,558 条指向 "
                 "molecular_attr 等其它粒度) —— 文献恢复主通道是 "
                 "mirror evidence_text 自然语言 + 本地 paper_sources 库"),
    }


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
    async with AsyncSessionLocal() as session:
        audit = await _audit_evidence_records(session)
        print(f"audit: evidence_records={audit['total_evidence_records']} "
              f"join_macro={audit['join_macro_connections']} "
              f"orphan={audit['orphan_not_joined']}")

        final_rows = (await session.execute(text(
            """SELECT id, canonical_connection_id, connection_code,
                      evidence_reference, evidence_summary
               FROM final_canonical_connections WHERE final_status='active'"""))).all()
        finals = [{"id": str(r[0]), "canonical_connection_id": str(r[1]),
                   "connection_code": r[2],
                   "evidence_reference": r[3] or [],
                   "evidence_summary": r[4] or {}}
                  for r in final_rows]
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

        # evidence_records:仅 lineage 命中的(当前 2 条 macro)。
        # 先展开 lineage id 集合,再 IN 查询 —— 避免对 99,481 行跑相关子查询。
        er_rows = (await session.execute(text(
            """SELECT er.id, er.evidence_target_id, er.paper_doi, er.paper_pmid,
                      er.paper_year, er.paper_title, er.paper_journal,
                      er.citation_json, er.evidence_text, er.verification_status
               FROM mirror_evidence_records er
               WHERE er.evidence_target_id IN (
                 SELECT mid::uuid
                 FROM canonical_connection_lineage l
                 JOIN jsonb_array_elements_text(l.mirror_connection_ids) mid
                   ON true)"""))).all()
        evidence_map: dict[str, list[dict]] = {}
        for r in er_rows:
            evidence_map.setdefault(str(r[1]), []).append({
                "id": str(r[0]), "paper_doi": r[2], "paper_pmid": r[3],
                "paper_year": r[4], "paper_title": r[5],
                "paper_journal": r[6], "citation_json": r[7],
                "evidence_text": r[8], "verification_status": r[9]})
        print(f"lineage-hit evidence_records: {len(er_rows)}")

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

    # ---- 3. 恢复规划(纯函数) ----
    plan = plan_lineage_recovery(finals, lineage_map, mirror_map,
                                 evidence_map, library)
    c = plan["counts"]
    print(f"plan: total={c['total']} recovered={c['literature_recovered']} "
          f"unresolved={c['unresolved']} by_priority={c['by_priority']}")
    print(f"by_reason: {c['by_reason']}")

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

    # ---- 5. 导出 4 报告 ----
    _export_reports(finals, plan, audit, len(er_rows), counters_before)
    print(f"[ok] 4 reports -> {OUT_DIR}")


def _export_reports(finals: list[dict], plan: dict, audit: dict,
                    lineage_evidence_hit: int, counters_before: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    def _write(name: str, data: dict) -> None:
        (OUT_DIR / name).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[ok] {name}")

    # 1) coverage_before.json
    before = coverage_before(finals)
    _write("coverage_before.json", {
        "analysis": "macro_evidence_lineage_recovery_v1",
        "task": "审计 + 现状",
        "scope": "final → lineage → mirror_evidence_records / evidence_text "
                 "链路审计 + 回填前 evidence_reference 现状(仅只读)",
        "baseline_counters": counters_before,
        "coverage": before,
        "lineage_audit": {
            "final_total": len(finals),
            "lineage_mirror_ids_total": sum(len(i["traced_mirror_ids"])
                                            for i in plan["items"]),
            "lineage_hit_evidence_records": lineage_evidence_hit,
            "note": "canonical_connection_lineage.mirror_connection_ids "
                    "→ mirror_evidence_records 仅命中 "
                    f"{lineage_evidence_hit} 条(macro 结构化文献证据)",
            "evidence_records_full": audit,
        },
        "generated_at": now,
    })

    # 2) coverage_after_preview.json
    after = coverage_after_preview(plan, evidence_records_hit=lineage_evidence_hit)
    _write("coverage_after_preview.json", {
        "analysis": "macro_evidence_lineage_recovery_v1",
        "task": "恢复后预览",
        "scope": "preview only:未修改 final_canonical_connections",
        "preview": after,
        "generated_at": now,
    })

    # 3) literature_recovery_candidates.json
    _write("literature_recovery_candidates.json", {
        "analysis": "macro_evidence_lineage_recovery_v1",
        "task": "可恢复文献引用清单",
        "scope": "A paper_doi+paper_pmid / B citation_json / "
                 "C 作者+年份文本+本地库唯一匹配",
        "candidates": literature_recovery_candidates(plan),
        "generated_at": now,
    })

    # 4) unresolved_evidence.json
    _write("unresolved_evidence.json", {
        "analysis": "macro_evidence_lineage_recovery_v1",
        "task": "无法恢复清单",
        "scope": "无文献线索(仅 LLM 文本)或无证据文本 —— 需 LLM 证据增强",
        "unresolved": unresolved_evidence(plan),
        "generated_at": now,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Macro Evidence Lineage Recovery V1(只读预览)")
    parser.parse_args()
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main(parser.parse_args()))
