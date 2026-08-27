"""Macro Connection Coverage Gap Analysis V1 实施脚本(只读,零写入)。

基于 2485 条 verified Final Canonical Connection,重新分析 Macro96 连接覆盖:
  1. coverage_matrix_final.json        — Macro96 bilateral 池 × 全对覆盖矩阵
  2. region_degree_final.json          — 每区域 incoming/outgoing/total/structural/functional degree
  3. symmetry_gap_candidates.json      — 双侧对称性缺口(A1 高度可信 / A2 可能 / B 需文献)
  4. coverage_report.json              — 覆盖总结
  5. region_degree_report.json         — degree 总结
  6. symmetry_gap_report.json          — 对称性总结
  7. supplementation_candidates.json   — 汇总全部补缺候选

数据来源(全部只读):
* raw_macro96_region_rows(96 区)→ Macro96 池 52 个 bilateral 概念
* final_canonical_connections + canonical_brain_regions(2485 verified)
* mirror_region_connections granularity='macro'(5720,含 left/right → 对称性分析)
* mirror_region_functions granularity='macro'(142,功能候选)

不执行:创建 connection、修改 Final KG、CN2 inference、LLM extraction、外部数据库导入。
输出: data/exports/macro_connection_coverage_gap/
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
from app.services.macro_connection_coverage_gap_service import (
    analyze_symmetry,
    build_coverage_matrix,
    build_supplementation_candidates,
    compute_region_degree,
    find_functional_gap_candidates,
    normalize_region_name,
)

OUT_DIR = Path(_backend) / "data" / "exports" / "macro_connection_coverage_gap"


async def main(_args: argparse.Namespace) -> None:
    async with AsyncSessionLocal() as session:
        # ---- 1. Macro96 池(96 raw 行 → 52 bilateral 概念) ----
        raw_names = [r[0] for r in (await session.execute(text(
            "SELECT DISTINCT en_name FROM raw_macro96_region_rows ORDER BY 1"))).all()]
        pool = sorted({normalize_region_name(n) for n in raw_names})
        # 池内左右侧信息(用于报告:lateralized pairs vs midline)
        lateralized = sorted(n for n in pool if any(
            n == normalize_region_name(x) for x in raw_names
            if x.lower().startswith(("left ", "right "))))
        print(f"macro96 pool: {len(pool)} bilateral concepts "
              f"(raw {len(raw_names)} rows, {len(lateralized)} lateralized)")

        # ---- 2. Final canonical connections(2485 verified,带区域名) ----
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
        in_pool = sum(1 for f in finals
                      if normalize_region_name(f["src_name"]) in pool
                      and normalize_region_name(f["tgt_name"]) in pool)
        print(f"final connections: {len(finals)} | mapped to pool: {in_pool}")

        # ---- 3. mirror macro connections(5720,左右侧) ----
        mirror_rows = (await session.execute(text(
            """SELECT source_region_name_en, target_region_name_en, connection_type
               FROM mirror_region_connections WHERE granularity_level='macro'"""))).all()
        mirrors = [{"src_name": r[0], "tgt_name": r[1], "connection_type": r[2]}
                   for r in mirror_rows]
        print(f"mirror macro connections: {len(mirrors)}")

        # ---- 4. mirror macro functions(142) ----
        func_rows = (await session.execute(text(
            """SELECT region_name_en, function_term FROM mirror_region_functions
               WHERE granularity_level='macro'"""))).all()
        functions = [{"region_name": r[0], "function_term": r[1]} for r in func_rows]
        print(f"mirror macro functions: {len(functions)}")

    # ---- 分析(纯函数,无 DB 依赖) ----
    matrix = build_coverage_matrix(pool, finals)
    degree = compute_region_degree(pool, finals)
    symmetry = analyze_symmetry(pool, mirrors)
    functional = find_functional_gap_candidates(pool, finals, functions)
    supplement = build_supplementation_candidates(matrix, degree, symmetry, functional)

    # ---- 导出 ----
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    _write(OUT_DIR / "coverage_matrix_final.json", {**matrix, "generated_at": now})
    _write(OUT_DIR / "region_degree_final.json", {**degree, "generated_at": now})
    _write(OUT_DIR / "symmetry_gap_candidates.json", {**symmetry, "generated_at": now})
    _write(OUT_DIR / "coverage_report.json", _coverage_report(matrix, finals, pool, now))
    _write(OUT_DIR / "region_degree_report.json", _degree_report(degree, now))
    _write(OUT_DIR / "symmetry_gap_report.json", _symmetry_report(symmetry, now))
    _write(OUT_DIR / "supplementation_candidates.json",
           {**supplement, "functional_candidates": functional, "generated_at": now})

    print(f"[ok] 7 reports -> {OUT_DIR}")
    print(f"coverage: {matrix['covered_pairs']}/{matrix['total_pairs']} pairs "
          f"({matrix['coverage_pct']}%) | uncovered: {matrix['uncovered_regions']}")
    print(f"degree: zero {len(degree['zero_degree_regions'])} | "
          f"high {len(degree['high_connectivity_regions'])} | "
          f"low {len(degree['low_connectivity_regions'])}")
    print(f"symmetry: A1 {symmetry['counts']['A1']} | A2 {symmetry['counts']['A2']} | "
          f"B {symmetry['counts']['B']}")
    print(f"functional candidates: {len(functional)} | "
          f"total supplementation candidates: {supplement['total_candidates']}")


def _coverage_report(matrix: dict, finals: list[dict], pool: list[str], now: str) -> dict:
    # final 连接中未落入 Macro96 池的(超出池范围的连接,上下文参考)
    out_of_pool = sorted(
        ({normalize_region_name(f["src_name"]) for f in finals} |
         {normalize_region_name(f["tgt_name"]) for f in finals})
        - set(pool))
    return {
        "analysis": "macro_connection_coverage_gap_v1",
        "basis": "2485 verified final canonical connections",
        "pool_size": matrix["pool_size"],
        "total_pairs": matrix["total_pairs"],
        "covered_pairs": matrix["covered_pairs"],
        "coverage_pct": matrix["coverage_pct"],
        "covered_region_count": matrix["covered_region_count"],
        "uncovered_regions": matrix["uncovered_regions"],
        "uncovered_regions_explanation": (
            "Macro96 池细分区域(cerebellum exterior/white matter、ventral diencephalon)"
            "在 final 层无连接;final 层以宏观合并概念(Cerebellum/Diencephalon)覆盖小脑/间脑"),
        "out_of_pool_region_names": out_of_pool,
        "pair_type_distribution": _pair_type_dist(matrix),
        "generated_at": now,
    }


def _pair_type_dist(matrix: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    for e in matrix["pair_detail"]:
        for ctype, n in e["connection_types"].items():
            out[ctype] = out.get(ctype, 0) + n
    return dict(sorted(out.items()))


def _degree_report(degree: dict, now: str) -> dict:
    return {
        "analysis": "macro_connection_coverage_gap_v1",
        "basis": "2485 verified final canonical connections",
        "region_count": degree["region_count"],
        "mean_total_degree": degree["mean_total_degree"],
        "high_connectivity_regions": degree["high_connectivity_regions"],
        "low_connectivity_regions": degree["low_connectivity_regions"],
        "zero_degree_regions": degree["zero_degree_regions"],
        "zero_degree_note": "cerebellum exterior/white matter、ventral diencephalon "
                            "= final 层无连接的潜在缺失区域",
        "top_10_regions_by_degree": sorted(degree["regions"],
                                           key=lambda d: -d["total_degree"])[:10],
        "generated_at": now,
    }


def _symmetry_report(symmetry: dict, now: str) -> dict:
    counts = symmetry["counts"]
    return {
        "analysis": "macro_connection_coverage_gap_v1",
        "basis": "mirror layer macro connections (left/right naming, 5720)",
        "classification": {
            "A1": "high_confidence_missing - mirror (left->left vs right->right) missing, "
                  "bilateral anatomy is strong prior",
            "A2": "possible_missing - one side entirely lacks connections, other side has",
            "B": "requires_literature - both mirror sides exist but connection types differ",
        },
        "counts": counts,
        "candidates": symmetry,
        "generated_at": now,
    }


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[ok] {path.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Macro Connection Coverage Gap Analysis V1")
    parser.parse_args()
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main(parser.parse_args()))
