"""Macro Connection Priority Classification V2 实施脚本(只读分析,零写入)。

基于最新 BrainRegion ontology(Macro96 Region Hierarchy Alignment 已完成:
3 细分概念纳入 canonical ontology + 正式 part_of 边),重新计算 Macro96
Connection 覆盖缺口并建立补充优先级列表。

流程:
  1. 加载数据(全部只读):Macro96 池 52 / final 2485 / mirror 5720 /
     functions 142 / A1 symmetry candidates 27(已 resolved)
  2. plan_priority_classification(纯函数):coverage matrix V2 + region degree
     + 缺失对三分类(A 高可信 / B 潜在 / C ignore)+ 27 条 A1 候选重评估
  3. 零写入断言:final / mirror / canonical connections / A1 candidates /
     candidate regions / canonical regions 数量在分析前后不变
  4. 导出 7 报告 → data/exports/macro_connection_priority_v2/

不执行:创建 connection、promotion、Final KG 修改、CN2 inference、外部数据库导入。
输出: data/exports/macro_connection_priority_v2/
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
from app.services.macro_connection_priority_classification_service import (
    V1_BASELINE,
    normalize_region_name,
    plan_priority_classification,
)

OUT_DIR = Path(_backend) / "data" / "exports" / "macro_connection_priority_v2"


async def main(_args: argparse.Namespace) -> None:
    # ---- 0. 零写入断言基线快照 ----
    async with AsyncSessionLocal() as session:
        final_before = (await session.execute(text(
            "SELECT count(*) FROM final_canonical_connections"))).scalar()
        mirror_before = (await session.execute(text(
            "SELECT count(*) FROM mirror_region_connections WHERE granularity_level='macro'"))).scalar()
        canon_conn_before = (await session.execute(text(
            "SELECT count(*) FROM canonical_connections"))).scalar()
        a1_before = (await session.execute(text(
            "SELECT count(*) FROM macro_connection_candidates WHERE generation_method='hemisphere_symmetry_v1'"))).scalar()
        cand_regions_before = (await session.execute(text(
            "SELECT count(*) FROM candidate_brain_regions"))).scalar()
        regions_before = (await session.execute(text(
            "SELECT count(*) FROM canonical_brain_regions"))).scalar()
        print(f"baseline: final {final_before} | mirror {mirror_before} | "
              f"canonical_conns {canon_conn_before} | A1 {a1_before} | "
              f"candidate_regions {cand_regions_before} | regions {regions_before}")

    # ---- 1. 数据加载(全部只读) ----
    async with AsyncSessionLocal() as session:
        # Macro96 池:96 raw 行 → 52 bilateral 概念(含 3 细分概念)
        raw_names = [r[0] for r in (await session.execute(text(
            "SELECT DISTINCT en_name FROM raw_macro96_region_rows ORDER BY 1"))).all()]
        pool = sorted({normalize_region_name(n) for n in raw_names})
        print(f"macro96 pool: {len(pool)} bilateral concepts "
              f"(raw {len(raw_names)} rows)")

        # final canonical connections(2485,带区域名)
        final_rows = (await session.execute(text(
            """SELECT f.source_region_id, f.target_region_id, f.connection_type,
                      f.evidence_summary
               FROM final_canonical_connections f
               JOIN canonical_brain_regions s ON s.id = f.source_region_id
               JOIN canonical_brain_regions t ON t.id = f.target_region_id"""))).all()
        src_names = {str(i): n for i, n in (await session.execute(text(
            "SELECT id, canonical_name_en FROM canonical_brain_regions"))).all()}
        finals = [{
            "src_name": src_names.get(str(r[0])) or "",
            "tgt_name": src_names.get(str(r[1])) or "",
            "connection_type": r[2],
            "evidence_count": (r[3] or {}).get("evidence_count", 0),
        } for r in final_rows]
        print(f"final connections: {len(finals)}")

        # mirror macro connections(5720,左右侧)
        mirror_rows = (await session.execute(text(
            """SELECT source_region_name_en, target_region_name_en, connection_type
               FROM mirror_region_connections WHERE granularity_level='macro'"""))).all()
        mirrors = [{"src_name": r[0], "tgt_name": r[1], "connection_type": r[2]}
                   for r in mirror_rows]
        print(f"mirror macro connections: {len(mirrors)}")

        # mirror macro functions(142)
        func_rows = (await session.execute(text(
            """SELECT region_name_en, function_term FROM mirror_region_functions
               WHERE granularity_level='macro'"""))).all()
        func_by_region: dict[str, set[str]] = {}
        for r in func_rows:
            key = normalize_region_name(r[0])
            if r[1]:
                func_by_region.setdefault(key, set()).add(str(r[1]).lower())
        print(f"mirror macro functions: {sum(len(v) for v in func_by_region.values())} "
              f"terms across {len(func_by_region)} regions")

        # A1 symmetry candidates(27,已 resolved)
        a1_rows = (await session.execute(text(
            """SELECT id, source_region_name, target_region_name, status
               FROM macro_connection_candidates
               WHERE generation_method='hemisphere_symmetry_v1'
               ORDER BY id"""))).all()
        a1_candidates = [{"id": str(r[0]), "source_region_name": r[1],
                          "target_region_name": r[2], "status": r[3]}
                         for r in a1_rows]
        print(f"A1 symmetry candidates: {len(a1_candidates)} "
              f"(resolved: {sum(1 for c in a1_candidates if c['status'] == 'canonical_region_resolved')})")

    # ---- 2. 分析(纯函数) ----
    plan = plan_priority_classification(pool, finals, mirrors, func_by_region,
                                        a1_candidates)
    m, d, cl = plan["matrix"], plan["degree"], plan["classification"]
    cc = cl["counts"]
    print(f"coverage v2: {m['covered_pairs']}/{m['total_pairs']} "
          f"({m['coverage_pct']}%) | uncovered {m['uncovered_regions']}")
    print(f"degree: isolated {len(d['isolated_regions'])} | high "
          f"{len(d['high_connectivity_regions'])} | low {len(d['low_connectivity_regions'])}")
    print(f"missing {cc['total']}: A {cc['A']} | B {cc['B']} | C {cc['C']}")
    print(f"A1 reassessment: keep {plan['reassessment_counts']['keep']} | "
          f"discard {plan['reassessment_counts']['discard']} "
          f"(ontology covered {plan['reassessment_counts']['discard_ontology_covered']})")

    # ---- 3. 零写入断言(分析前后数量一致) ----
    async with AsyncSessionLocal() as session:
        assert (await session.execute(text(
            "SELECT count(*) FROM final_canonical_connections"))).scalar() == final_before, \
            "Final KG 数变化(禁止写入)"
        assert (await session.execute(text(
            "SELECT count(*) FROM mirror_region_connections WHERE granularity_level='macro'"))).scalar() \
            == mirror_before, "mirror 数变化"
        assert (await session.execute(text(
            "SELECT count(*) FROM canonical_connections"))).scalar() == canon_conn_before, \
            "canonical connections 数变化"
        assert (await session.execute(text(
            "SELECT count(*) FROM macro_connection_candidates WHERE generation_method='hemisphere_symmetry_v1'"))).scalar() \
            == a1_before, "A1 candidate 数变化"
        assert (await session.execute(text(
            "SELECT count(*) FROM candidate_brain_regions"))).scalar() == cand_regions_before, \
            "candidate regions 数变化"
        assert (await session.execute(text(
            "SELECT count(*) FROM canonical_brain_regions"))).scalar() == regions_before, \
            "canonical regions 数变化"
        print("[ok] zero-write verified: 6 counters unchanged")

    # ---- 4. 导出 ----
    _export_reports(plan, a1_candidates)
    print(f"[ok] 7 reports -> {OUT_DIR}")


def _export_reports(plan: dict, a1_candidates: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    m, d, cl = plan["matrix"], plan["degree"], plan["classification"]
    cc = cl["counts"]

    def _write(name: str, data: dict) -> None:
        (OUT_DIR / name).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[ok] {name}")

    # 1) coverage_matrix_v2.json — 任务 1 输出
    _write("coverage_matrix_v2.json", {
        "analysis": "macro_connection_priority_v2",
        "basis": "2485 verified final canonical connections + 686 canonical "
                 "regions + 691 part_of edges (Macro96 Region Hierarchy Alignment 完成)",
        "pool_size": m["pool_size"],
        "total_pairs": m["total_pairs"],
        "covered_pairs": m["covered_pairs"],
        "missing_pairs": m["missing_pairs"],
        "coverage_pct": m["coverage_pct"],
        "covered_region_count": m["covered_region_count"],
        "uncovered_regions": m["uncovered_regions"],
        "region_degree": {
            "region_count": d["region_count"],
            "isolated_regions": d["isolated_regions"],
            "regions": d["regions"],
        },
        "generated_at": now,
    })

    # 2) coverage_report.json — 新旧对比 + 分类摘要
    _write("coverage_report.json", {
        "analysis": "macro_connection_priority_v2",
        "v1_baseline": V1_BASELINE,
        "v2": {
            "pool_size": m["pool_size"],
            "total_pairs": m["total_pairs"],
            "covered_pairs": m["covered_pairs"],
            "coverage_pct": m["coverage_pct"],
            "uncovered_regions": m["uncovered_regions"],
            "missing_pairs": len(m["missing_pairs"]),
        },
        "delta_v1_v2": plan["delta_v1_v2"],
        "missing_classification": cc,
        "a1_reassessment_counts": plan["reassessment_counts"],
        "generated_at": now,
    })

    # 3) priority_candidates.json — 全量候选(A+B,可补充;+C 供参考)
    _write("priority_candidates.json", {
        "analysis": "macro_connection_priority_v2",
        "counts": cc,
        "classification_semantics": {
            "A": "high_confidence_missing - mirror 层直接证据 + hemisphere symmetry 支持 + final 层缺失",
            "B": "potential_missing - 无 mirror 直接证据,需文献验证(附功能关联/共同邻居佐证)",
            "C": "ignore - 粒度假缺失(hierarchy 已覆盖)或非实质脑区(CSF/脑室)",
        },
        "candidates": cl["A"] + cl["B"] + cl["C"],
        "generated_at": now,
    })

    # 4-6) A/B/C 分类明细
    _write("A_class_candidates.json", {
        "analysis": "macro_connection_priority_v2",
        "class": "A",
        "count": cc["A"],
        "criteria": ("hemisphere symmetry 支持 + 已有对应 mirror evidence + "
                     "已有相关 canonical connection(final 层其他对)+ 解剖合理"),
        "candidates": cl["A"],
        "generated_at": now,
    })
    _write("B_class_candidates.json", {
        "analysis": "macro_connection_priority_v2",
        "class": "B",
        "count": cc["B"],
        "criteria": "功能关联 / 网络关系合理 / 需要文献验证",
        "candidates": cl["B"],
        "generated_at": now,
    })
    _write("C_class_candidates.json", {
        "analysis": "macro_connection_priority_v2",
        "class": "C",
        "count": cc["C"],
        "criteria": "非实质脑区(CSF/脑室)+ hierarchy 已覆盖 + 粒度造成的假缺失",
        "candidates": cl["C"],
        "generated_at": now,
    })

    # 7) A1_reassessment.json — 27 条候选最终状态
    _write("A1_reassessment.json", {
        "analysis": "macro_connection_priority_v2",
        "total": plan["reassessment_counts"]["total"],
        "keep": plan["reassessment_counts"]["keep"],
        "discard": plan["reassessment_counts"]["discard"],
        "discard_reasons": {
            "ontology_covered": plan["reassessment_counts"]["discard_ontology_covered"],
            "self_loop": plan["reassessment_counts"]["discard"]
                         - plan["reassessment_counts"]["discard_ontology_covered"],
        },
        "rule": (
            "每条候选的细分概念提升到父概念(Cerebellum/Diencephalon);"
            "父概念对在 final 层已覆盖 → discard(ontology 已覆盖);"
            "未覆盖 → keep(以父概念粒度补充)"),
        "candidates": plan["reassessment"],
        "generated_at": now,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Macro Connection Priority Classification V2(只读分析)")
    parser.parse_args()
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main(parser.parse_args()))
