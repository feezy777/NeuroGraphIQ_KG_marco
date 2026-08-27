"""Macro Connection A1 Hemisphere Symmetry Candidate Generation V1 实施脚本。

流程:
  1. 读取 coverage 分析输出 symmetry_gap_candidates.json 的 A1 候选(266)
  2. 回查 mirror 层 macro 连接获取源连接(方向/类型/置信度/mirror id)
  3. 规划生成:generated / skipped / conflict / duplicate
  4. 写入 macro_connection_candidates(ON CONFLICT 幂等锚,零覆盖)
  5. 断言:canonical active 数不变、final 数不变、mirror 数不变
     (candidate 不进入治理链)、provenance / source_connection_id 完整
  6. 导出 candidate_summary.json + generated_candidates.json + skipped_candidates.json

不执行:promotion、validation PASS、Final KG 写入、CN2 inference、LLM、外部导入。
输出: data/exports/macro_connection_symmetry_candidates/
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services.macro_connection_symmetry_candidate_service import (
    GENERATION_METHOD,
    plan_generation,
)

OUT_DIR = Path(_backend) / "data" / "exports" / "macro_connection_symmetry_candidates"
A1_JSON = Path(_backend) / "data" / "exports" / "macro_connection_coverage_gap" / \
    "symmetry_gap_candidates.json"


async def main(_args: argparse.Namespace) -> None:
    # ---- 1. A1 候选 ----
    a1_items = json.loads(A1_JSON.read_text(encoding="utf-8"))["A1_high_confidence_missing"]
    print(f"A1 candidates: {len(a1_items)}")

    async with AsyncSessionLocal() as session:
        # ---- 2. 数据加载(全部只读) ----
        mirror_rows = (await session.execute(text(
            """SELECT id, source_region_name_en, target_region_name_en, connection_type,
                      directionality, modality, confidence
               FROM mirror_region_connections WHERE granularity_level='macro'"""))).all()
        mirror_conns = [{
            "id": str(r[0]), "src_name": r[1], "tgt_name": r[2],
            "connection_type": r[3], "directionality": r[4],
            "modality": r[5], "confidence": float(r[6]) if r[6] is not None else None,
        } for r in mirror_rows]
        print(f"mirror macro connections: {len(mirror_conns)}")

        canon_rows = [{"id": str(r[0]), "canonical_name_en": r[1], "laterality": r[2]}
                      for r in (await session.execute(text(
                          "SELECT id, canonical_name_en, laterality FROM canonical_brain_regions"))).all()]
        canon_conns = [{"source_region_id": str(r[0]), "target_region_id": str(r[1]),
                        "connection_type": r[2], "status": r[3]}
                       for r in (await session.execute(text(
                           "SELECT source_region_id, target_region_id, connection_type, status "
                           "FROM canonical_connections"))).all()]
        cand_rows = (await session.execute(text(
            "SELECT source_region_id, target_region_id, connection_type, "
            "source_connection_id FROM macro_connection_candidates"))).all()
        existing_candidates = [{"source_region_id": str(r[0]), "target_region_id": str(r[1]),
                                "connection_type": r[2],
                                "source_connection_id": str(r[3])}
                               for r in cand_rows]
        print(f"canonical: {len(canon_rows)} regions, {len(canon_conns)} connections | "
              f"existing candidates: {len(existing_candidates)}")

        # ---- 前置快照(断言用) ----
        canon_active_before = (await session.execute(text(
            "SELECT count(*) FROM canonical_connections WHERE status='active'"))).scalar()
        final_before = (await session.execute(text(
            "SELECT count(*) FROM final_canonical_connections"))).scalar()
        mirror_before = len(mirror_conns)

    # ---- 3. 规划(纯函数) ----
    plan = plan_generation(a1_items, mirror_conns, canon_rows, canon_conns,
                           existing_candidates)
    c = plan["counts"]
    print(f"plan: generated {c['generated']} | skipped {c['skipped']} "
          f"({plan['skip_reasons']}) | conflict {c['conflict']} | duplicate {c['duplicate']}")

    # ---- 4. 写入(幂等) ----
    async with AsyncSessionLocal() as session:
        inserted = 0
        for g in plan["generated"]:
            r = (await session.execute(text(
                """INSERT INTO macro_connection_candidates
                   (id, source_region_id, target_region_id, source_region_name,
                    target_region_name, connection_type, direction, modality,
                    source_connection_id, generation_method, assertion_type,
                    confidence, provenance_json, status)
                   VALUES (:id, :src, :tgt, :srcn, :tgtn, :ctype, :dir, :mod,
                           :sid, :gm, :at, :conf, :pj, 'candidate')
                   ON CONFLICT ON CONSTRAINT uq_macro_conn_candidate DO NOTHING
                   RETURNING id"""),
                {"id": str(uuid.uuid4()), "src": g["source_region_id"],
                 "tgt": g["target_region_id"], "srcn": g["source_region_name"],
                 "tgtn": g["target_region_name"], "ctype": g["connection_type"],
                 "dir": g["direction"], "mod": g["modality"], "sid": g["source_connection_id"],
                 "gm": g["generation_method"], "at": g["assertion_type"],
                 "conf": g["confidence"],
                 "pj": json.dumps(g["provenance_json"], ensure_ascii=False)})).first()
            if r is not None:
                inserted += 1
        await session.commit()
        print(f"inserted: {inserted}")

        # ---- 5. 断言:candidate 不进入治理链,原数据不变 ----
        assert (await session.execute(text(
            "SELECT count(*) FROM canonical_connections WHERE status='active'"))).scalar() \
            == canon_active_before, "canonical active 数变化(candidate 不得影响)"
        assert (await session.execute(text(
            "SELECT count(*) FROM final_canonical_connections"))).scalar() == final_before, \
            "Final KG 数变化"
        assert (await session.execute(text(
            "SELECT count(*) FROM mirror_region_connections WHERE granularity_level='macro'"))).scalar() \
            == mirror_before, "mirror 数变化"
        stored = (await session.execute(text(
            "SELECT count(*) FROM macro_connection_candidates"))).scalar()
        assert stored == len(existing_candidates) + inserted, f"stored {stored} != expected"
        assert (await session.execute(text(
            "SELECT count(*) FROM macro_connection_candidates "
            "WHERE assertion_type='candidate'"))).scalar() == stored, "assertion_type 非 candidate"
        assert (await session.execute(text(
            "SELECT count(*) FROM macro_connection_candidates "
            "WHERE generation_method='hemisphere_symmetry_v1'"))).scalar() == stored, \
            "generation_method 非 hemisphere_symmetry_v1"
        assert (await session.execute(text(
            "SELECT count(*) FROM macro_connection_candidates "
            "WHERE provenance_json IS NULL OR provenance_json = '{}'::jsonb"))).scalar() == 0, \
            "provenance 缺失"
        assert (await session.execute(text(
            "SELECT count(*) FROM macro_connection_candidates "
            "WHERE source_connection_id IS NULL"))).scalar() == 0, \
            "source_connection_id 缺失(必须以已有连接为依据)"
        print(f"[ok] stored {stored} | canonical active {canon_active_before}== | "
              f"final {final_before}== | mirror {mirror_before}== | provenance/source 完整")

    # ---- 6. 导出 ----
    _export_reports(plan, a1_items, inserted)
    print(f"[ok] reports -> {OUT_DIR}")


def _export_reports(plan: dict, a1_items: list[dict], inserted: int) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    # generated_candidates.json — 每条生成的 candidate 详情
    detail = []
    for g in plan["generated"]:
        p = g["provenance_json"]
        detail.append({
            "region_pair": list(g["region_pair"]),
            "missing_side": g["missing_side"],
            "source_region": g["source_region_name"],
            "target_region": g["target_region_name"],
            "connection_type": g["connection_type"],
            "mirror_connection_type": g["mirror_connection_type"],
            "direction": g["direction"],
            "modality": g["modality"],
            "confidence": g["confidence"],
            "source_connection_id": g["source_connection_id"],
            "region_unmapped": g["region_unmapped"],
            "suggested_mapping": g["suggested_mapping"],
            "provenance": p,
        })
    (OUT_DIR / "generated_candidates.json").write_text(json.dumps({
        "analysis": GENERATION_METHOD,
        "rule": "hemisphere_symmetry",
        "input_a1_total": len(a1_items),
        "generated_count": len(plan["generated"]),
        "candidates": detail,
        "generated_at": now,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[ok] generated_candidates.json")

    # candidate_summary.json — 统计
    (OUT_DIR / "candidate_summary.json").write_text(json.dumps({
        "analysis": GENERATION_METHOD,
        "basis": "symmetry_gap_candidates.json A1_high_confidence_missing",
        "input_a1_count": len(a1_items),
        "generated_count": len(plan["generated"]),
        "inserted_rows": inserted,
        "conflict_count": len(plan["conflict"]),
        "skipped_count": len(plan["skipped"]),
        "duplicate_count": len(plan["duplicate"]),
        "skip_reasons": plan["skip_reasons"],
        "conflict_detail": plan["conflict"],
        "type_distribution": _count_by(plan["generated"], "connection_type"),
        "missing_side_distribution": _count_by(plan["generated"], "missing_side"),
        "constraints": {
            "llm_generation": "disabled",
            "external_database": "disabled",
            "auto_promotion_to_final": "disabled",
            "canonical_active_write": "disabled",
            "basis_only_existing_connections": "enforced (source_connection_id required)",
        },
        "generated_at": now,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[ok] candidate_summary.json")

    # skipped_candidates.json — 未生成的候选及原因
    (OUT_DIR / "skipped_candidates.json").write_text(json.dumps({
        "analysis": GENERATION_METHOD,
        "skipped_count": len(plan["skipped"]),
        "duplicate_count": len(plan["duplicate"]),
        "skipped": plan["skipped"],
        "duplicate": plan["duplicate"],
        "generated_at": now,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[ok] skipped_candidates.json")


def _count_by(rows: list[dict], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        v = r.get(key) or "unknown"
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Macro Connection Symmetry Candidate Generation V1")
    parser.parse_args()
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main(parser.parse_args()))
