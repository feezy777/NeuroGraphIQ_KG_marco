"""Macro96 Region Hierarchy Alignment 收口实施脚本。

流程:
  1. 前置快照:final / mirror / canonical connections / A1 candidates /
     candidate regions / canonical regions / hierarchy 边 / aliases
  2. 加载 ontology(canonical_brain_regions / canonical_region_aliases /
     canonical_region_hierarchy)与 A1 symmetry candidates(27)
  3. plan_canonicalization:anchor 就绪检查(3 实体 + 9 别名 + 父概念)+
     候选重解析 + 全图环检查
  4. 回填 macro_connection_candidates:resolved_source_region_id /
     resolved_target_region_id + status='canonical_region_resolved'
     (UPDATE 幂等,不触碰 source_region_id/target_region_id 幂等锚列)
  5. 断言:治理链零变化(final/mirror/canonical/A1 数量不变);ontology 仅
     预期变化(regions 686 / hierarchy 691 / aliases 1030);无环;候选全解析
  6. 导出 data/exports/macro_region_alignment_final/ 3 报告

ontology 写入(migration 20260909_macro_region_canonicalization.sql 已应用):
  3 canonical region anchor + 3 正式 part_of 边 + 9 别名(manual_curated)。
本脚本不重复写入 ontology —— 只断言就绪 + 解析标注。

不执行:promotion、创建 connection、CN2 inference、外部数据库导入。
输出: data/exports/macro_region_alignment_final/
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
from app.services.macro_region_canonicalization_service import (
    CONFIDENCE,
    CONFIRMATION_METHOD,
    REGION_ANCHORS,
    RESOLVED_STATUS,
    SOURCE_METHOD,
    plan_canonicalization,
)

OUT_DIR = Path(_backend) / "data" / "exports" / "macro_region_alignment_final"


async def main(_args: argparse.Namespace) -> None:
    # ---- 1. 前置快照(断言基线) ----
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
        hier_before = (await session.execute(text(
            "SELECT count(*) FROM canonical_region_hierarchy"))).scalar()
        aliases_before = (await session.execute(text(
            "SELECT count(*) FROM canonical_region_aliases"))).scalar()
        print(f"snapshot: final {final_before} | mirror {mirror_before} | "
              f"canonical_conns {canon_conn_before} | A1 {a1_before} | "
              f"candidate_regions {cand_regions_before} | regions {regions_before} | "
              f"hierarchy {hier_before} | aliases {aliases_before}")

    # ---- 2. 加载 ontology + 候选(全部只读) ----
    async with AsyncSessionLocal() as session:
        canon_rows = [{"id": str(r[0]), "canonical_name_en": r[1]}
                      for r in (await session.execute(text(
                          "SELECT id, canonical_name_en FROM canonical_brain_regions"))).all()]
        alias_rows = [{"alias": r[0], "region_id": str(r[1])}
                      for r in (await session.execute(text(
                          "SELECT alias, region_id FROM canonical_region_aliases"))).all()]
        hier_rows = [{"child_region_id": str(r[0]), "parent_region_id": str(r[1])}
                     for r in (await session.execute(text(
                         "SELECT child_region_id, parent_region_id FROM canonical_region_hierarchy"))).all()]
        cand_rows = [{"id": str(r[0]), "source_region_id": str(r[1]) if r[1] else None,
                      "source_region_name": r[2], "target_region_id": str(r[3]) if r[3] else None,
                      "target_region_name": r[4], "connection_type": r[5],
                      "status": r[6]}
                     for r in (await session.execute(text(
                         """SELECT id, source_region_id, source_region_name,
                                   target_region_id, target_region_name,
                                   connection_type, status
                            FROM macro_connection_candidates
                            WHERE generation_method='hemisphere_symmetry_v1'
                            ORDER BY id"""))).all()]
        print(f"loaded: regions {len(canon_rows)} | aliases {len(alias_rows)} | "
              f"hierarchy {len(hier_rows)} | A1 candidates {len(cand_rows)}")

    # ---- 3. 规划(纯函数) ----
    plan = plan_canonicalization(cand_rows, alias_rows, canon_rows, hier_rows)
    c = plan["counts"]
    print(f"plan: anchors {c['anchor_ready']}/{c['anchor_total']} ready | "
          f"resolved {c['resolved_candidates']} | "
          f"unresolved {c['unresolved_candidates']} | cycle {c['hierarchy_cycle_detected']}")

    # anchor 就绪断言
    for a in plan["anchors"]:
        print(f"  anchor {a['concept']}: ready={a['ready']} "
              f"(region {'ok' if a['canonical_region_id'] else 'MISSING'}, "
              f"parent {'ok' if a['parent_region_id'] else 'MISSING'}, "
              f"aliases {a['alias_ready']}/{a['alias_total']})")
    assert c["anchor_ready"] == c["anchor_total"] == 3, "anchor 未全部就绪"
    assert not c["hierarchy_cycle_detected"], "hierarchy 存在环"
    assert c["resolved_candidates"] == a1_before == 27, \
        f"候选未全解析: {c['resolved_candidates']}/{a1_before}"

    # ---- 4. 回填(幂等 UPDATE,不动幂等锚列) ----
    async with AsyncSessionLocal() as session:
        updated = 0
        for r in plan["resolution"]["resolved"]:
            res = await session.execute(text(
                """UPDATE macro_connection_candidates
                   SET resolved_source_region_id = :rs,
                       resolved_target_region_id = :rt,
                       status = :st,
                       updated_at = now()
                   WHERE id = :cid
                     AND (resolved_source_region_id IS DISTINCT FROM :rs
                          OR resolved_target_region_id IS DISTINCT FROM :rt
                          OR status IS DISTINCT FROM :st)
                   RETURNING id"""),
                {"rs": r["resolved_source_region_id"], "rt": r["resolved_target_region_id"],
                 "st": RESOLVED_STATUS, "cid": r["candidate_id"]})
            if res.first() is not None:
                updated += 1
        await session.commit()
        print(f"backfilled candidates: {updated} updated this run")

        # ---- 5. 断言 ----
        # 治理链零变化
        assert (await session.execute(text(
            "SELECT count(*) FROM final_canonical_connections"))).scalar() == final_before, \
            "Final KG 数变化"
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
        # ontology 仅预期变化(3 实体 + 3 边 + 9 别名)
        assert (await session.execute(text(
            "SELECT count(*) FROM canonical_brain_regions"))).scalar() == regions_before, \
            f"canonical regions {regions_before} 未保持(幂等重跑应零变化)"
        assert (await session.execute(text(
            "SELECT count(*) FROM canonical_region_hierarchy"))).scalar() == hier_before, \
            "hierarchy 边数变化"
        assert (await session.execute(text(
            "SELECT count(*) FROM canonical_region_aliases"))).scalar() == aliases_before, \
            "aliases 数变化"
        # 回填完整性
        resolved_rows = (await session.execute(text(
            """SELECT count(*) FROM macro_connection_candidates
               WHERE generation_method='hemisphere_symmetry_v1'
                 AND status='canonical_region_resolved'
                 AND resolved_source_region_id IS NOT NULL
                 AND resolved_target_region_id IS NOT NULL"""))).scalar()
        assert resolved_rows == a1_before, f"回填不完整: {resolved_rows}/{a1_before}"
        # 幂等锚列未动(NULL 侧保持 NULL —— 原列语义不变)
        untouched = (await session.execute(text(
            """SELECT count(*) FROM macro_connection_candidates
               WHERE generation_method='hemisphere_symmetry_v1'
                 AND (source_region_id IS NULL OR target_region_id IS NULL)"""))).scalar()
        assert untouched == a1_before, "幂等锚列被修改"

        # 锚点详情(报告用)
        anchor_rows = (await session.execute(text(
            """SELECT cr.region_code, cr.canonical_name_en, p.canonical_name_en,
                      h.child_region_id, h.parent_region_id
               FROM canonical_brain_regions cr
               JOIN canonical_region_hierarchy h ON h.child_region_id = cr.id
               JOIN canonical_brain_regions p ON p.id = h.parent_region_id
               WHERE cr.created_by='macro_region_alignment_v1'
               ORDER BY cr.region_code"""))).all()
        anchor_detail = [{"region_code": r[0], "canonical_name_en": r[1],
                          "parent_name": r[2], "child_region_id": str(r[3]),
                          "parent_region_id": str(r[4])} for r in anchor_rows]
        # 报告用解析详情(从 DB 读,幂等重跑展示全量)
        db_resolved = (await session.execute(text(
            """SELECT id, source_region_name, target_region_name,
                      resolved_source_region_id, resolved_target_region_id
               FROM macro_connection_candidates
               WHERE generation_method='hemisphere_symmetry_v1'
               ORDER BY id"""))).all()
        resolved_detail = [{
            "candidate_id": str(r[0]), "source_region_name": r[1],
            "target_region_name": r[2],
            "resolved_source_region_id": str(r[3]),
            "resolved_target_region_id": str(r[4]),
        } for r in db_resolved]

    # ---- 6. 导出 ----
    _export_reports(plan, updated, anchor_detail, resolved_detail)
    print(f"[ok] reports -> {OUT_DIR}")


def _export_reports(plan: dict, updated: int, anchor_detail: list[dict],
                    resolved_detail: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    c = plan["counts"]

    # canonicalization_report.json — 3 anchor + 正式边 + 别名 + 统计
    (OUT_DIR / "canonicalization_report.json").write_text(json.dumps({
        "method": CONFIRMATION_METHOD,
        "source_method": SOURCE_METHOD,
        "confidence": CONFIDENCE,
        "basis": ("canonical_brain_regions / canonical_region_hierarchy / "
                  "canonical_region_aliases (migration "
                  "20260909_macro_region_canonicalization.sql)"),
        "anchors": [
            {**spec, "concept": a["concept"],
             "canonical_region_id": a["canonical_region_id"],
             "parent_region_id": a["parent_region_id"],
             "ready": a["ready"],
             "alias_ready": a["alias_ready"]}
            for a, spec in zip(plan["anchors"], REGION_ANCHORS.values())
        ],
        "formal_edges": anchor_detail,
        "counts": c,
        "alias_map_size": plan["alias_map_size"],
        "note": (
            "3 个 Macro96 池细分概念正式纳入 canonical ontology:child canonical "
            "region ↓ part_of ↓ parent canonical region(不 merge 到 parent);"
            "resolver 经 canonical_region_aliases(manual_curated 9 行)解析 "
            "left/right 名称;macro_region_hierarchy_candidates 6 条候选记录保留"),
        "generated_at": now,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[ok] canonicalization_report.json")

    # resolved_symmetry_candidates.json — 27 条解析结果
    (OUT_DIR / "resolved_symmetry_candidates.json").write_text(json.dumps({
        "method": CONFIRMATION_METHOD,
        "resolved_count": len(resolved_detail),
        "backfilled_this_run": updated,
        "status": RESOLVED_STATUS,
        "resolution_rule": (
            "已映射侧保留原 region_id;未映射侧(left/right 细分概念名)经 "
            "resolve_region_name(带侧别名 -> 剥侧别 -> canonical 名称)解析到 "
            "新 canonical anchor"),
        "candidates": resolved_detail,
        "generated_at": now,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[ok] resolved_symmetry_candidates.json")

    # unresolved_candidates.json — 预期 0
    (OUT_DIR / "unresolved_candidates.json").write_text(json.dumps({
        "method": CONFIRMATION_METHOD,
        "unresolved_count": c["unresolved_candidates"],
        "unresolved": plan["resolution"]["unresolved"],
        "conclusion": (
            "全部 27 条 A1 symmetry candidate 已解析到 canonical region;"
            "若后续出现新概念名称导致 unresolved,需先补 canonical_region_aliases"),
        "generated_at": now,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[ok] unresolved_candidates.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Macro96 Region Hierarchy Alignment 收口(正式纳入 ontology)")
    parser.parse_args()
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main(parser.parse_args()))
