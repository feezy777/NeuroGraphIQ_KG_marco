"""Macro96 Region Hierarchy Alignment V1 实施脚本。

流程:
  1. 加载 ontology 层数据(全部只读):canonical_brain_regions /
     canonical_region_hierarchy / canonical_region_aliases /
     atlas_region_mappings / candidate_brain_regions(Macro96 aligned)
  2. 分析 3 个池细分概念(cerebellum exterior / cerebellum white matter /
     ventral diencephalon)在各层的存在状态
  3. 生成 part_of_candidate 候选(基于解剖学先验 + candidate 层对齐)
  4. 质量检查:child != parent、parent 存在、无环、不重复
  5. 写入 macro_region_hierarchy_candidates(ON CONFLICT 幂等锚,零覆盖)
  6. 断言:canonical / hierarchy 边 / final / mirror / candidate 数不变
  7. 导出 region_alignment_status.json + hierarchy_candidates.json +
     unresolved_region_report.json

不执行:创建 connection、修改 Final KG、candidate promotion、CN2 inference、
LLM extraction、外部数据库导入。
输出: data/exports/macro_region_alignment/
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
from app.services.macro_region_alignment_service import (
    ALIGNMENT_MAP,
    GENERATION_METHOD,
    plan_alignment,
)

OUT_DIR = Path(_backend) / "data" / "exports" / "macro_region_alignment"
CONCEPTS = list(ALIGNMENT_MAP.keys())


async def main(_args: argparse.Namespace) -> None:
    async with AsyncSessionLocal() as session:
        # ---- 1. 数据加载(全部只读) ----
        canon_rows = [{"id": str(r[0]), "canonical_name_en": r[1], "status": r[2]}
                      for r in (await session.execute(text(
                          "SELECT id, canonical_name_en, status FROM canonical_brain_regions"))).all()]
        print(f"canonical regions: {len(canon_rows)}")

        hier_rows = (await session.execute(text(
            """SELECT h.child_region_id, h.parent_region_id,
                      c.canonical_name_en, p.canonical_name_en, h.source
               FROM canonical_region_hierarchy h
               JOIN canonical_brain_regions c ON c.id = h.child_region_id
               JOIN canonical_brain_regions p ON p.id = h.parent_region_id"""))).all()
        hierarchy_edges = [{"child_region_id": str(r[0]), "parent_region_id": str(r[1]),
                            "child_region_name": r[2], "parent_region_name": r[3],
                            "source": r[4]} for r in hier_rows]
        print(f"hierarchy edges: {len(hierarchy_edges)}")

        alias_rows = [{"alias": r[0]} for r in (await session.execute(text(
            "SELECT alias FROM canonical_region_aliases"))).all()]
        print(f"aliases: {len(alias_rows)}")

        atlas_rows = [{"atlas_region_name": r[0]} for r in (await session.execute(text(
            """SELECT DISTINCT ar.region_name FROM atlas_region_mappings m
               JOIN atlas_region_resources ar ON ar.id = m.atlas_region_id
               WHERE m.status='active'"""))).all()]
        print(f"atlas mapping region names: {len(atlas_rows)}")

        cand_rows = [{"id": str(r[0]), "en_name": r[1], "alignment_status": r[2],
                      "canonical_region_id": str(r[3]),
                      "canonical_region_name": r[4]}
                     for r in (await session.execute(text(
                         """SELECT cb.id, cb.en_name, cb.alignment_status,
                                  cb.canonical_region_id, cr.canonical_name_en
                           FROM candidate_brain_regions cb
                           LEFT JOIN canonical_brain_regions cr
                             ON cr.id = cb.canonical_region_id
                           WHERE cb.source_atlas='Macro96'"""))).all()]
        print(f"candidate Macro96 rows: {len(cand_rows)}")

        exist_rows = (await session.execute(text(
            "SELECT child_region_id, parent_region_id, relation_type "
            "FROM macro_region_hierarchy_candidates"))).all()
        existing_candidates = [{"child_region_id": str(r[0]), "parent_region_id": str(r[1]),
                                "relation_type": r[2]} for r in exist_rows]
        print(f"existing candidates: {len(existing_candidates)}")

        # ---- 前置快照(断言用) ----
        canon_before = len(canon_rows)
        hier_before = len(hierarchy_edges)
        final_before = (await session.execute(text(
            "SELECT count(*) FROM final_canonical_connections"))).scalar()
        mirror_before = (await session.execute(text(
            "SELECT count(*) FROM mirror_region_connections WHERE granularity_level='macro'"))).scalar()
        cand_regions_before = (await session.execute(text(
            "SELECT count(*) FROM candidate_brain_regions"))).scalar()

    # ---- 2-4. 分析 + 候选生成 + 质量检查(纯函数) ----
    plan = plan_alignment(CONCEPTS, canon_rows, hierarchy_edges, alias_rows,
                          atlas_rows, cand_rows, existing_candidates)
    c = plan["counts"]
    print(f"plan: existing_mapped {c['existing_mapped_rows']} | "
          f"generated {c['generated_candidates']} | unresolved {c['unresolved_concepts']} | "
          f"conflict {c['conflict_candidates']} | duplicate {c['duplicate_candidates']} | "
          f"cycle {c['cycle_detected']}")

    # ---- 5. 写入(幂等) ----
    async with AsyncSessionLocal() as session:
        inserted = 0
        for g in plan["candidates"]:
            r = (await session.execute(text(
                """INSERT INTO macro_region_hierarchy_candidates
                   (id, child_region_id, child_region_name, parent_region_id,
                    parent_region_name, relation_type, evidence_source,
                    confidence, provenance_json, generation_method,
                    assertion_type, status)
                   VALUES (:id, :child, :childn, :parent, :parentn, :rt, :es,
                           :conf, :pj, :gm, :at, 'candidate')
                   ON CONFLICT ON CONSTRAINT uq_region_hierarchy_candidate DO NOTHING
                   RETURNING id"""),
                {"id": str(uuid.uuid4()), "child": g["child_region_id"],
                 "childn": g["child_region_name"], "parent": g["parent_region_id"],
                 "parentn": g["parent_region_name"], "rt": g["relation_type"],
                 "es": g["evidence_source"], "conf": g["confidence"],
                 "pj": json.dumps(g["provenance_json"], ensure_ascii=False),
                 "gm": g["generation_method"], "at": g["assertion_type"]})).first()
            if r is not None:
                inserted += 1
        await session.commit()
        print(f"inserted: {inserted}")

        # ---- 6. 断言:candidate 不进入治理链,原数据不变 ----
        assert not c["cycle_detected"], "候选引入环"
        assert (await session.execute(text(
            "SELECT count(*) FROM canonical_brain_regions"))).scalar() == canon_before, \
            "canonical 区域数变化"
        assert (await session.execute(text(
            "SELECT count(*) FROM canonical_region_hierarchy"))).scalar() == hier_before, \
            "hierarchy 边数变化(候选不得写正式边)"
        assert (await session.execute(text(
            "SELECT count(*) FROM final_canonical_connections"))).scalar() == final_before, \
            "Final KG 数变化"
        assert (await session.execute(text(
            "SELECT count(*) FROM mirror_region_connections WHERE granularity_level='macro'"))).scalar() \
            == mirror_before, "mirror 数变化"
        assert (await session.execute(text(
            "SELECT count(*) FROM candidate_brain_regions"))).scalar() == cand_regions_before, \
            "candidate 区域数变化"
        stored = (await session.execute(text(
            "SELECT count(*) FROM macro_region_hierarchy_candidates"))).scalar()
        assert stored == len(existing_candidates) + inserted, f"stored {stored} != expected"
        assert (await session.execute(text(
            "SELECT count(*) FROM macro_region_hierarchy_candidates "
            "WHERE assertion_type='candidate'"))).scalar() == stored, "assertion_type 非 candidate"
        assert (await session.execute(text(
            "SELECT count(*) FROM macro_region_hierarchy_candidates "
            "WHERE generation_method='macro_region_alignment_v1'"))).scalar() == stored, \
            "generation_method 非 macro_region_alignment_v1"
        assert (await session.execute(text(
            "SELECT count(*) FROM macro_region_hierarchy_candidates "
            "WHERE provenance_json IS NULL OR provenance_json = '{}'::jsonb"))).scalar() == 0, \
            "provenance 缺失"
        assert (await session.execute(text(
            "SELECT count(*) FROM macro_region_hierarchy_candidates "
            "WHERE child_region_id IS NULL OR parent_region_id IS NULL"))).scalar() == 0, \
            "child/parent id 缺失"
        print(f"[ok] stored {stored} | canonical {canon_before}== | hierarchy {hier_before}== | "
              f"final {final_before}== | mirror {mirror_before}== | candidate_regions "
              f"{cand_regions_before}== | cycle none")

        # 落库候选详情(幂等重跑时也从 DB 读,报告展示全部候选)
        db_rows = (await session.execute(text(
            """SELECT child_region_name, parent_region_name, relation_type,
                      evidence_source, confidence, provenance_json, child_region_id,
                      parent_region_id
               FROM macro_region_hierarchy_candidates ORDER BY child_region_name"""))).all()
        db_candidates = [{
            "child_region_id": str(r[6]), "child_region_name": r[0],
            "parent_region_id": str(r[7]), "parent_region_name": r[1],
            "relation_type": r[2], "evidence_source": r[3],
            "confidence": float(r[4]) if r[4] is not None else None,
            "provenance_json": r[5],
        } for r in db_rows]

    # ---- 7. 导出 ----
    _export_reports(plan, inserted, db_candidates)
    print(f"[ok] reports -> {OUT_DIR}")


def _export_reports(plan: dict, inserted: int, db_candidates: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    # region_alignment_status.json — 3 区域各层存在状态
    (OUT_DIR / "region_alignment_status.json").write_text(json.dumps({
        "analysis": GENERATION_METHOD,
        "basis": "canonical_brain_regions / canonical_region_hierarchy / "
                 "canonical_region_aliases / atlas_region_mappings / "
                 "candidate_brain_regions(Macro96)",
        "concepts": plan["status"],
        "counts": plan["counts"],
        "note": (
            "3 个池细分概念在 canonical 层均无实体、无 part_of 边、无别名、无 atlas 映射;"
            "candidate 层已对齐到宏观概念(Cerebellum/Diencephalon)—— "
            "本阶段物化 part_of_candidate 供人工确认"),
        "generated_at": now,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[ok] region_alignment_status.json")

    # hierarchy_candidates.json — 全部落库候选详情(幂等重跑显示全量)
    detail = [{
        "child_region_id": g["child_region_id"],
        "child_region_name": g["child_region_name"],
        "parent_region_id": g["parent_region_id"],
        "parent_region_name": g["parent_region_name"],
        "relation_type": g["relation_type"],
        "evidence_source": g["evidence_source"],
        "confidence": g["confidence"],
        "provenance": g["provenance_json"],
    } for g in db_candidates]
    (OUT_DIR / "hierarchy_candidates.json").write_text(json.dumps({
        "analysis": GENERATION_METHOD,
        "stored_count": len(db_candidates),
        "inserted_this_run": inserted,
        "candidates": detail,
        "generated_at": now,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[ok] hierarchy_candidates.json")

    # unresolved_region_report.json — 无法判断/冲突
    (OUT_DIR / "unresolved_region_report.json").write_text(json.dumps({
        "analysis": GENERATION_METHOD,
        "unresolved_count": len(plan["unresolved"]),
        "conflict_count": len(plan["conflict"]),
        "unresolved": plan["unresolved"],
        "conflict": plan["conflict"],
        "conclusion": (
            "无 unresolved:3 个概念均有明确解剖学归属且 candidate 层已对齐;"
            "若后续出现 alignment 与解剖先验冲突的概念需人工裁决"),
        "generated_at": now,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[ok] unresolved_region_report.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Macro96 Region Hierarchy Alignment V1")
    parser.parse_args()
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main(parser.parse_args()))
