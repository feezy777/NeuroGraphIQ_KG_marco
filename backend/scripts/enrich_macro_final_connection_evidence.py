"""Macro Final Connection Evidence Enrichment V1 实施脚本(只读分析,零写入)。

目标:增强 Final 层(final_canonical_connections,2485 active)证据质量,
输出 4 报告到 data/exports/macro_evidence_enrichment/:

  1. evidence_before_report.json      —— Evidence Coverage Audit(任务 1)
  2. quality_recalculated.json        —— Quality Score 重算 + 新旧对比(任务 2)
  3. summary_enrichment_plan.json     —— 新 summary 格式方案(任务 3)
  4. priority_evidence_enrichment.json—— A/B/C 优先级分类(任务 4)

流程:
  1. 数据加载(全部只读):final 2485(JON canonical 拿旧分)+ mirror 5720
     (macro,detail)+ validation 2500 + lineage 4087
  2. plan_final_evidence_enrichment(纯函数):audit + quality + summary + priority
  3. 零写入断言:final / canonical / mirror / lineage / clusters /
     validation 数量分析前后不变
  4. 导出报告

不执行:创建/删除连接、修改 source/target/type/direction、CN2 inference、
Final promotion、外部数据写入。
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
from app.services.macro_final_connection_evidence_service import (
    Q_WEIGHTS,
    plan_final_evidence_enrichment,
)

OUT_DIR = Path(_backend) / "data" / "exports" / "macro_evidence_enrichment"


async def main(_args: argparse.Namespace) -> None:
    # ---- 1. 零写入断言基线快照 ----
    async with AsyncSessionLocal() as session:
        counters_before = {
            "final_active": (await session.execute(text(
                "SELECT count(*) FROM final_canonical_connections WHERE final_status='active'"))).scalar(),
            "canonical": (await session.execute(text(
                "SELECT count(*) FROM canonical_connections"))).scalar(),
            "mirror_macro": (await session.execute(text(
                "SELECT count(*) FROM mirror_region_connections WHERE granularity_level='macro'"))).scalar(),
            "lineage": (await session.execute(text(
                "SELECT count(*) FROM canonical_connection_lineage"))).scalar(),
            "clusters": (await session.execute(text(
                "SELECT count(*) FROM mirror_connection_clusters"))).scalar(),
            "validation_results": (await session.execute(text(
                "SELECT count(*) FROM canonical_connection_validation_results"))).scalar(),
        }
        print(f"baseline: {counters_before}")

    # ---- 2. 数据加载(全部只读) ----
    async with AsyncSessionLocal() as session:
        # final 行 + canonical 旧分
        final_rows = (await session.execute(text(
            """SELECT f.id, f.canonical_connection_id, f.connection_code,
                      f.connection_type, f.confidence, f.evidence_summary,
                      f.provenance_json, f.evidence_reference,
                      rs.canonical_name_en AS src_name,
                      rt.canonical_name_en AS tgt_name,
                      c.evidence_quality_score
               FROM final_canonical_connections f
               JOIN canonical_connections c ON c.id = f.canonical_connection_id
               LEFT JOIN canonical_brain_regions rs ON rs.id = f.source_region_id
               LEFT JOIN canonical_brain_regions rt ON rt.id = f.target_region_id
               WHERE f.final_status='active'"""))).all()
        finals = [{
            "id": str(r[0]), "canonical_connection_id": str(r[1]),
            "connection_code": r[2], "connection_type": r[3],
            "confidence": float(r[4]) if r[4] is not None else None,
            "evidence_summary": r[5], "provenance_json": r[6],
            "evidence_reference": r[7], "source_region_name": r[8],
            "target_region_name": r[9],
            "canonical_quality": r[10],
        } for r in final_rows]
        print(f"final active: {len(finals)}")

        # mirror macro 全量 detail(5720,id 索引)
        mirror_rows = (await session.execute(text(
            """SELECT id, llm_run_id, source_atlas, connection_type,
                      directionality, modality, confidence, evidence_text
               FROM mirror_region_connections WHERE granularity_level='macro'"""))).all()
        mirror_map = {str(r[0]): {
            "id": str(r[0]), "llm_run_id": str(r[1]) if r[1] else None,
            "source_atlas": r[2], "source_type": "llm_extraction",
            "connection_type": r[3], "directionality": r[4],
            "modality": r[5],
            "confidence": float(r[6]) if r[6] is not None else None,
            "evidence_text": r[7],
        } for r in mirror_rows}
        print(f"mirror macro: {len(mirror_map)}")

        # validation 结果(2500,按 canonical entity_id 索引)
        val_rows = (await session.execute(text(
            """SELECT entity_id, validation_status, failed_rules
               FROM canonical_connection_validation_results"""))).all()
        validation_map = {str(r[0]): {
            "validation_status": r[1], "failed_rules": r[2] or [],
        } for r in val_rows}
        print(f"validation results: {len(validation_map)}")

        # lineage 覆盖(4087)
        lineage_count = (await session.execute(text(
            "SELECT count(*) FROM canonical_connection_lineage"))).scalar()
        print(f"lineage rows: {lineage_count}")

    # ---- 3. 分析(纯函数) ----
    plan = plan_final_evidence_enrichment(finals, mirror_map, validation_map)
    a = plan["audit"]
    q = plan["quality"]
    p = plan["priority"]
    print(f"audit: summary缺失 {a['missing']['no_evidence_summary']} | "
          f"count=0 {a['missing']['evidence_count_zero']} | "
          f"count=1 {a['missing']['evidence_count_one']} | "
          f"ref空 {a['missing']['missing_evidence_reference']}")
    print(f"quality: {q['distribution']} | 旧分 {q['previous_canonical_distribution']}")
    print(f"priority: A {p['counts']['A']} | B {p['counts']['B']} | C {p['counts']['C']}")

    # ---- 4. 零写入断言 ----
    async with AsyncSessionLocal() as session:
        checks = {
            "final_active": "SELECT count(*) FROM final_canonical_connections WHERE final_status='active'",
            "canonical": "SELECT count(*) FROM canonical_connections",
            "mirror_macro": "SELECT count(*) FROM mirror_region_connections WHERE granularity_level='macro'",
            "lineage": "SELECT count(*) FROM canonical_connection_lineage",
            "clusters": "SELECT count(*) FROM mirror_connection_clusters",
            "validation_results": "SELECT count(*) FROM canonical_connection_validation_results",
        }
        for name, sql in checks.items():
            now_count = (await session.execute(text(sql))).scalar()
            assert now_count == counters_before[name], \
                f"{name} 数量变化: {counters_before[name]} → {now_count}(禁止写入)"
        print("[ok] zero-write verified: 6 counters unchanged")

    # ---- 5. 导出 ----
    _export_reports(plan, finals, mirror_map, validation_map)
    print(f"[ok] 4 reports -> {OUT_DIR}")


def _export_reports(plan: dict, finals: list[dict], mirror_map: dict,
                    validation_map: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    def _write(name: str, data: dict) -> None:
        (OUT_DIR / name).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[ok] {name}")

    # 1) evidence_before_report.json — 任务 1:coverage audit
    _write("evidence_before_report.json", {
        "analysis": "macro_final_connection_evidence_v1",
        "scope": "final_canonical_connections (active)",
        "audit": plan["audit"],
        "conclusions": {
            "evidence_reference_fully_empty": (
                plan["audit"]["missing"]["missing_evidence_reference"]
                == plan["audit"]["total_active"]),
            "single_evidence_share_pct": round(
                100 * plan["audit"]["missing"]["evidence_count_one"]
                / plan["audit"]["total_active"], 2),
            "note": ("evidence_summary / provenance_json 全量已填充(canonical 层"
                     "enrichment 固化);evidence_reference(外部文献/参考)100% 空"
                     "为主缺口;41% 连接为单证据(supporting_records=1)"),
        },
        "generated_at": now,
    })

    # 2) quality_recalculated.json — 任务 2:五因素重算 + 新旧对比
    _write("quality_recalculated.json", {
        "analysis": "macro_final_connection_evidence_v1",
        "weights": dict(Q_WEIGHTS),
        "distribution": plan["quality"]["distribution"],
        "previous_canonical_distribution": plan["quality"]["previous_canonical_distribution"],
        "label_changes": plan["quality"]["label_changes"],
        "factors": {
            "evidence": "min(evidence_count,10)/10 × 0.30",
            "sources": "min(distinct llm_run,3)/3 × 0.20",
            "confidence": "mean confidence × 0.15",
            "provenance": "provenance_completeness × 0.15",
            "validation": "pass→1.0 / fail→0.3 / 无→0.5 × 0.20",
            "high": "score ≥ 0.70", "medium": "0.45 ≤ score < 0.70",
            "low": "score < 0.45",
        },
        "items": plan["quality"]["items"],
        "generated_at": now,
    })

    # 3) summary_enrichment_plan.json — 任务 3:新 summary 格式方案
    _write("summary_enrichment_plan.json", {
        "analysis": "macro_final_connection_evidence_v1",
        "format": {
            "connection_id": "final connection id",
            "evidence_count": "mirror 证据条数",
            "supporting_sources": "[{source_id, source_atlas, source_type, record_count}]",
            "extraction_runs": "[llm_run_id 去重]",
            "confidence": "{min, max, mean}",
            "modalities": "{modality: count}",
            "connection_types": "{type: count}",
            "summary_text": "自然语言摘要",
        },
        "summaries": plan["summaries"],
        "generated_at": now,
    })

    # 4) priority_evidence_enrichment.json — 任务 4:A/B/C 优先级
    p = plan["priority"]
    _write("priority_evidence_enrichment.json", {
        "analysis": "macro_final_connection_evidence_v1",
        "criteria": {
            "A": "evidence_count==1 AND confidence_mean<0.5 AND provenance<0.8",
            "B": "evidence_count==1(其余)或 quality==low",
            "C": "multi-evidence 且 quality medium/high",
        },
        "counts": p["counts"],
        "A_high_priority": p["A"],
        "B_medium_priority": p["B"],
        "C_no_action": p["C"],
        "generated_at": now,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Macro Final Connection Evidence Enrichment V1(只读分析)")
    parser.parse_args()
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main(parser.parse_args()))
