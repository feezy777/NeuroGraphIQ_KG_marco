"""Macro Evidence Provenance Backfill V1 实施脚本。

任务:将 Mirror 层已有来源信息(llm_run_id / batch_id / source_atlas /
extraction metadata)经 lineage(final↓canonical↓cluster↓mirror_connection_ids)
上卷,回填 final_canonical_connections.evidence_reference(JSONB),使每条
Final Connection 具备完整可追溯的证据来源引用。

输出 4 报告 → data/exports/macro_evidence_provenance/:
  1. before_audit.json            —— mirror 来源字段审计(任务 1)
  2. coverage_after_backfill.json —— 回填后覆盖率 / lineage / evidence_count 一致性(任务 4)
  3. source_distribution.json     —— 来源分布(任务 4)
  4. missing_reference_report.json —— 剩余缺口(任务 4)

流程:
  1. 基线快照:final active / canonical / mirror macro / lineage / clusters
  2. 只读加载:final 2485 + lineage 4087 + mirror 5720 + llm_extraction_runs
  3. before_audit.json(任务 1)
  4. plan_provenance_backfill(纯函数)→ 目标 references + 幂等差异
  5. 结构零写入断言:5 计数器不变(仅 evidence_reference 字段被更新,
     禁止创建/删除连接)
  6. 幂等回填:UPDATE ... SET evidence_reference=:ref
     WHERE id=:id AND evidence_reference IS DISTINCT FROM :ref
  7. 回填后验证:重载 final → validate_backfill_consistency → 覆盖率报告
  8. source_distribution / missing_reference 报告
  9. 幂等复核:重跑 plan → to_update 应为 0

不执行:创建/删除连接、修改 source/target/type/direction、promotion、
CN2 inference、LLM 调用、外部数据写入。
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
from app.services.macro_evidence_provenance_backfill_service import (
    audit_mirror_provenance_fields,
    plan_provenance_backfill,
    validate_backfill_consistency,
)

OUT_DIR = Path(_backend) / "data" / "exports" / "macro_evidence_provenance"

# 结构计数器(回填不得改变任何一条)
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
        print(f"baseline: {counters_before}")

    # ---- 2. 只读加载 ----
    async with AsyncSessionLocal() as session:
        # final active(含当前 evidence_reference 现值,幂等对比用)
        final_rows = (await session.execute(text(
            """SELECT id, canonical_connection_id, connection_code,
                      evidence_reference, evidence_summary
               FROM final_canonical_connections WHERE final_status='active'"""))).all()
        finals = [{
            "id": str(r[0]), "canonical_connection_id": str(r[1]),
            "connection_code": r[2], "evidence_reference": r[3] or [],
            "evidence_summary": r[4] or {},
        } for r in final_rows]
        print(f"final active: {len(finals)}")

        # lineage(4087,按 canonical_id 索引)
        lineage_rows = (await session.execute(text(
            """SELECT canonical_id, cluster_id, mirror_connection_ids
               FROM canonical_connection_lineage"""))).all()
        lineage_map: dict[str, list[dict]] = {}
        for r in lineage_rows:
            lineage_map.setdefault(str(r[0]), []).append({
                "cluster_id": str(r[1]),
                "mirror_connection_ids": r[2] or [],
            })
        print(f"lineage rows: {len(lineage_rows)} | traced canonical: {len(lineage_map)}")

        # mirror macro 全量(5720,id 索引;含 source_version 供 dataset 组拼)
        mirror_rows = (await session.execute(text(
            """SELECT id, llm_run_id, batch_id, source_atlas, source_version,
                      confidence, evidence_text
               FROM mirror_region_connections WHERE granularity_level='macro'"""))).all()
        mirror_map: dict[str, dict] = {}
        mirror_detail = []
        for r in mirror_rows:
            row = {
                "id": str(r[0]), "llm_run_id": str(r[1]) if r[1] else None,
                "batch_id": str(r[2]) if r[2] else None,
                "source_atlas": r[3], "source_version": r[4],
                "confidence": float(r[5]) if r[5] is not None else None,
                "evidence_text": r[6],
            }
            mirror_map[str(r[0])] = row
            mirror_detail.append(row)
        print(f"mirror macro: {len(mirror_map)}")

        # llm_extraction_runs(提取批次元数据)
        run_rows = (await session.execute(text(
            """SELECT id, task_type, provider, model_name, prompt_version,
                      prompt_template_key, status, source_atlas, source_version
               FROM llm_extraction_runs"""))).all()
        run_meta_map: dict[str, dict] = {}
        run_detail = []
        for r in run_rows:
            meta = {
                "id": str(r[0]), "task_type": r[1], "provider": r[2],
                "model_name": r[3], "prompt_version": r[4],
                "prompt_template_key": r[5], "status": r[6],
                "source_atlas": r[7], "source_version": r[8],
            }
            run_meta_map[str(r[0])] = meta
            run_detail.append(meta)
        print(f"llm_extraction_runs: {len(run_meta_map)}")

    # ---- 3. 任务 1:before_audit.json ----
    audit = audit_mirror_provenance_fields(mirror_detail, run_detail)
    _export("before_audit.json", {
        "analysis": "macro_evidence_provenance_backfill_v1",
        "task": 1,
        "scope": "mirror_region_connections (granularity_level='macro') 来源字段可用性",
        "audit": audit,
        "conclusion": {
            "has_structured_paper_doi_pmid": False,
            "available_source_info": (
                "llm_run_id / batch_id / source_atlas / source_version / "
                "provider / model / prompt_version —— 提取批次级来源,非文献级"),
            "literature_gap": "paper/DOI/PMID 需后续文献层补充(evidence_text 自然语言线索未结构化)",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    })
    print(f"[ok] before_audit.json (paper/DOI/PMID 结构化字段: 无; "
          f"llm_run_id 覆盖 {audit['field_coverage']['llm_run_id']}; "
          f"runs {audit['distinct']['llm_run_ids']})")

    # ---- 4. 回填规划(纯函数) ----
    plan = plan_provenance_backfill(finals, lineage_map, mirror_map, run_meta_map)
    c = plan["counts"]
    print(f"plan: total {c['total']} | to_update {c['to_update']} | "
          f"unchanged {c['unchanged']} | no_lineage {c['no_lineage']} | "
          f"count_mismatch {c['count_mismatch']}")

    # ---- 5. 结构零写入断言 ----
    async with AsyncSessionLocal() as session:
        counters_mid = await _counters(session)
        for name, before in counters_before.items():
            assert counters_mid[name] == before, \
                f"{name} 数量变化: {before} → {counters_mid[name]}(禁止创建/删除连接)"
        print("[ok] structural zero-write: 5 counters unchanged")

    # ---- 6. 幂等回填(仅 evidence_reference) ----
    updated_ids: list[str] = []
    async with AsyncSessionLocal() as session:
        for item in plan["items"]:
            if not item["will_update"]:
                continue
            res = await session.execute(
                text("""UPDATE final_canonical_connections
                        SET evidence_reference = :ref, updated_at = now()
                        WHERE id = :id
                          AND evidence_reference IS DISTINCT FROM :ref
                        RETURNING id"""),
                {"ref": json.dumps(item["references"], ensure_ascii=False),
                 "id": item["final_id"]})
            row = res.fetchone()
            if row:
                updated_ids.append(str(row[0]))
        await session.commit()
    print(f"[ok] backfilled {len(updated_ids)} finals (expected to_update {c['to_update']})")
    assert len(updated_ids) == c["to_update"], \
        f"回填行数与规划不符: {len(updated_ids)} vs {c['to_update']}"

    # ---- 7. 回填后验证 ----
    async with AsyncSessionLocal() as session:
        post_rows = (await session.execute(text(
            """SELECT id, canonical_connection_id, evidence_reference, evidence_summary
               FROM final_canonical_connections WHERE final_status='active'"""))).all()
        post_finals = [{
            "id": str(r[0]), "canonical_connection_id": str(r[1]),
            "evidence_reference": r[2] or [], "evidence_summary": r[3] or {},
        } for r in post_rows]
        counters_after = await _counters(session)
    for name, before in counters_before.items():
        assert counters_after[name] == before, f"{name} 回填后数量变化!"
    consistency = validate_backfill_consistency(plan["items"])

    # ---- 8. 幂等复核:回填后状态重跑规划 → 0 更新 ----
    re_plan = plan_provenance_backfill(post_finals, lineage_map, mirror_map, run_meta_map)
    print(f"[ok] idempotency recheck: to_update {re_plan['counts']['to_update']} "
          f"(must be 0)")

    # ---- 9. 报告导出 ----
    _export("coverage_after_backfill.json", {
        "analysis": "macro_evidence_provenance_backfill_v1",
        "task": 4,
        "scope": "final_canonical_connections (active) evidence_reference 回填结果",
        "backfilled_ids": updated_ids,
        "backfill_expected": c["to_update"],
        "consistency": consistency,
        "idempotency": {
            "replan_to_update_after_backfill": re_plan["counts"]["to_update"],
            "replan_unchanged": re_plan["counts"]["unchanged"],
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    })

    _export("source_distribution.json", {
        "analysis": "macro_evidence_provenance_backfill_v1",
        "task": 4,
        "source_types": _source_type_distribution(plan["items"]),
        "runs": _run_distribution(plan["items"]),
        "datasets": _dataset_distribution(plan["items"]),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    })

    _export("missing_reference_report.json", {
        "analysis": "macro_evidence_provenance_backfill_v1",
        "task": 4,
        "summary": {
            "final_total": len(plan["items"]),
            "missing_any_reference": sum(1 for i in plan["items"] if not i["references"]),
            "missing_lineage": c["no_lineage"],
            "evidence_count_mismatch": c["count_mismatch"],
            "paper_doi_pmid": "全部缺失 —— mirror 层无结构化文献字段,需 LLM/文献补充",
        },
        "items": [{
            "final_id": i["final_id"],
            "connection_code": i["connection_code"],
            "references": len(i["references"]),
            "traced_mirror_ids": len(i["traced_mirror_ids"]),
            "missing": i["missing"],
        } for i in plan["items"] if not i["references"] or not i["count_consistent"]],
        "recommendation": {
            "llm_literature_backfill": (
                "对 evidence_text 含文献线索(66 条 'et al')的 mirror 证据做"
                "文献解析回填 paper/DOI/PMID;或从外部文献库(PubMed)按脑区-连接"
                "组合补引用 —— 属后续阶段,不在本阶段范围"),
            "next_stage": "macro_evidence_literature_backfill",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    })

    print(f"[ok] 4 reports -> {OUT_DIR}")


# ---- 分布统计 ----

def _flatten_refs(items: list[dict]) -> list[dict]:
    return [r for i in items for r in i["references"]]


def _source_type_distribution(items: list[dict]) -> dict:
    from collections import Counter
    cnt = Counter(r["source_type"] for r in _flatten_refs(items))
    return {"llm_extraction": cnt.get("llm_extraction", 0),
            "unknown": cnt.get("unknown", 0),
            "total": sum(cnt.values())}


def _run_distribution(items: list[dict]) -> list[dict]:
    from collections import Counter, defaultdict
    runs: dict[str, dict] = {}
    for r in _flatten_refs(items):
        sid = r["source_id"]
        g = runs.setdefault(sid, {"source_id": sid, "source_type": r["source_type"],
                                  "count": 0, "mirror_connection_ids": 0,
                                  "confidence_mean": []})
        g["count"] += 1
        g["mirror_connection_ids"] += len(r.get("mirror_connection_ids") or [])
        if r.get("confidence"):
            g["confidence_mean"].append(float(r["confidence"]))
    out = []
    for sid in sorted(runs):
        g = runs[sid]
        g["confidence_mean"] = round(sum(g["confidence_mean"]) / len(g["confidence_mean"]), 4) \
            if g["confidence_mean"] else None
        out.append(g)
    return out


def _dataset_distribution(items: list[dict]) -> dict:
    from collections import Counter
    return dict(Counter(r["dataset"] for r in _flatten_refs(items) if r["dataset"]))


def _export(name: str, data: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / name).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[ok] {name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Macro Evidence Provenance Backfill V1")
    parser.parse_args()
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main(parser.parse_args()))
