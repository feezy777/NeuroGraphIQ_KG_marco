"""Macro Connection canonical consolidation Pipeline 第 3 层实施脚本。

Connection Cluster → Canonical Connection + Evidence Summary + Lineage

* 复用:现有 canonical 按 (region 对 + type_norm + dir_norm + species) 完全匹配 → 复用 id
* 新建:无匹配 → INSERT(status='proposed', assertion_type='reported_fact',
  source_type='llm_extraction', generation_method='macro_connection_consolidation_v1')
* evidence 上卷:evidence_count / evidence_sources / evidence_summary / confidence_statistics
* lineage:canonical_connection_lineage 每 cluster 一行,canonical → cluster → mirror 可追溯
* 幂等:重跑 = 删除本脚本新建的 canonical + 本批 lineage,重新生成/重建
* 不执行:promotion、active 修改、Final KG、CN2
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services.macro_connection_canonicalization import (
    GENERATION_METHOD,
    ClusterRow,
    build_connection_code,
    build_evidence_aggregation,
    pick_directionality,
    plan_canonicalization,
)

OUT_DIR = Path(_backend) / "data" / "exports" / "macro_connection_canonicalization"


async def load_clusters(session) -> list[ClusterRow]:
    rows = (await session.execute(text(
        "SELECT * FROM mirror_connection_clusters ORDER BY id"
    ))).all()
    return [
        ClusterRow(
            id=r.id, cluster_key=r.cluster_key,
            source_region_id=str(r.source_region_id), target_region_id=str(r.target_region_id),
            source_region_name=r.source_region_name, target_region_name=r.target_region_name,
            connection_type=r.connection_type, directionality=r.directionality,
            modality_norm=r.modality_norm, modality_original=r.modality_original or [],
            species=r.species, hemisphere_groups=r.hemisphere_groups or [],
            mirror_connection_ids=r.mirror_connection_ids or [],
            evidence_count=r.evidence_count, merge_reason=r.merge_reason,
            confidence_distribution=r.confidence_distribution or {},
            provenance=r.provenance or {},
        )
        for r in rows
    ]


async def load_existing_canonicals(session) -> tuple[list[dict], dict]:
    rows = (await session.execute(text(
        """SELECT id, source_region_id, target_region_id, connection_type,
                  directionality_policy, species, connection_code, evidence_summary
           FROM canonical_connections"""
    ))).all()
    canon = [
        {
            "id": str(r.id), "source_region_id": str(r.source_region_id),
            "target_region_id": str(r.target_region_id),
            "connection_type": r.connection_type, "directionality_policy": r.directionality_policy,
            "species": r.species, "connection_code": r.connection_code,
            "evidence_summary": r.evidence_summary or {},
        }
        for r in rows
    ]
    return canon, {c["id"]: c for c in canon}


async def main() -> None:
    async with AsyncSessionLocal() as session:
        clusters = await load_clusters(session)
        mirror_before = (await session.execute(text(
            "SELECT count(*) FROM mirror_region_connections WHERE granularity_level='macro'"))).scalar()

        # ---- 幂等清理(必须先于 planning:否则第二轮会把第一轮新建的 canonical 当作
        # 复用对象,清理后 canonical id 悬挂,lineage FK 失败)----
        await session.execute(text(
            "DELETE FROM canonical_connection_lineage WHERE canonical_id IN "
            "(SELECT id FROM canonical_connections WHERE generation_method = :g)"),
            {"g": GENERATION_METHOD})
        await session.execute(text(
            "DELETE FROM canonical_connections WHERE generation_method = :g"),
            {"g": GENERATION_METHOD})
        cluster_ids = [c.id for c in clusters]
        for i in range(0, len(cluster_ids), 500):
            chunk = cluster_ids[i:i + 500]
            phs = ",".join(f":c{j}" for j in range(len(chunk)))
            await session.execute(text(
                f"DELETE FROM canonical_connection_lineage WHERE cluster_id IN ({phs})"),
                {f"c{j}": cid for j, cid in enumerate(chunk)})

        existing, _ = await load_existing_canonicals(session)
        print(f"clusters: {len(clusters)} | existing canonical: {len(existing)} | mirror: {mirror_before}")

        plans = plan_canonicalization(clusters, existing)
        new_plans = [p for p in plans if not p.existing]
        reuse_plans = [p for p in plans if p.existing]
        print(f"reuse: {len(reuse_plans)} clusters | new: {len(new_plans)} clusters")

        # ---- 新建 canonical(每 key 一条,key 内多 cluster 共享)----
        # key = (src, tgt, type_norm, species);方向是属性,混合方向 → unspecified
        new_by_key: dict[tuple, list] = {}
        for p in new_plans:
            new_by_key.setdefault(p.key, []).append(p.cluster)
        used_codes = {c["connection_code"] for c in existing if c["connection_code"]}
        key_to_code: dict[tuple, str] = {}
        for key in new_by_key:
            first = new_by_key[key][0]
            code = build_connection_code(key[2], first.source_region_name, first.target_region_name,
                                         "directed", used_codes)
            used_codes.add(code)
            key_to_code[key] = code

        created_specs = [
            {
                "connection_code": key_to_code[key],
                "source_region_id": key[0], "target_region_id": key[1],
                "connection_type": key[2], "species": key[3],
                "directionality_policy": pick_directionality(
                    [c.directionality for c in new_by_key[key]]),
                "granularity_level": "clinical", "status": "proposed",
                "assertion_type": "reported_fact", "source_type": "llm_extraction",
                "generation_method": GENERATION_METHOD,
                "source_summary": json.dumps({
                    "generation": GENERATION_METHOD, "source_atlas": "Macro96",
                    "cluster_ids": [c.id for c in new_by_key[key]],
                    "original_directions": sorted({c.directionality for c in new_by_key[key]}),
                }, ensure_ascii=False),
            }
            for key in new_by_key
        ]
        if created_specs:
            SQL_INS = (
                "INSERT INTO canonical_connections (connection_code, source_region_id, target_region_id, "
                "connection_type, directionality_policy, species, granularity_level, status, "
                "assertion_type, source_type, generation_method, source_summary) VALUES ")
            for chunk_start in range(0, len(created_specs), 200):
                chunk = created_specs[chunk_start:chunk_start + 200]
                phs, params = [], {}
                for i, r in enumerate(chunk):
                    p = f"n{chunk_start + i}"
                    phs.append(f"(:{p}_cc, :{p}_s, :{p}_t, :{p}_ct, :{p}_dp, :{p}_sp, :{p}_gl, "
                               f":{p}_st, :{p}_at, :{p}_sty, :{p}_gm, :{p}_ss)")
                    params.update({
                        f"{p}_cc": r["connection_code"], f"{p}_s": r["source_region_id"],
                        f"{p}_t": r["target_region_id"], f"{p}_ct": r["connection_type"],
                        f"{p}_dp": r["directionality_policy"], f"{p}_sp": r["species"],
                        f"{p}_gl": r["granularity_level"], f"{p}_st": r["status"],
                        f"{p}_at": r["assertion_type"], f"{p}_sty": r["source_type"],
                        f"{p}_gm": r["generation_method"], f"{p}_ss": r["source_summary"],
                    })
                await session.execute(text(SQL_INS + ",".join(phs)), params)
        # code → id
        code_to_id: dict[str, str] = {}
        if created_specs:
            codes = [s["connection_code"] for s in created_specs]
            rows = (await session.execute(text(
                "SELECT id, connection_code FROM canonical_connections WHERE connection_code = ANY(:codes)"),
                {"codes": codes})).all()
            code_to_id = {r.connection_code: str(r.id) for r in rows}

        # ---- canonical 归属 ----
        canonical_of_cluster: dict[int, str] = {
            p.cluster.id: p.canonical_id for p in reuse_plans
        }
        for key, cl_list in new_by_key.items():
            cid = code_to_id.get(key_to_code[key])
            if cid is None:
                raise RuntimeError(f"created canonical not found for key {key}")
            for cl in cl_list:
                canonical_of_cluster[cl.id] = cid
        assert len(canonical_of_cluster) == len(clusters), "cluster canonical mapping incomplete"

        # ---- evidence 上卷(新建 + 复用;从本批 cluster 重算,幂等)----
        agg = build_evidence_aggregation(canonical_of_cluster, clusters)
        for cid, a in agg.items():
            await session.execute(text(
                """UPDATE canonical_connections SET evidence_count = :ec,
                       confidence_statistics = :cs, evidence_summary = :es
                   WHERE id = :cid"""),
                {"ec": a["evidence_count"],
                 "cs": json.dumps(a["confidence_statistics"], ensure_ascii=False),
                 "es": json.dumps(a["evidence_summary"], ensure_ascii=False),
                 "cid": cid})

        # ---- lineage ----
        lineage_rows = []
        for cl in clusters:
            cid = canonical_of_cluster[cl.id]
            lineage_rows.append({
                "canonical_id": cid, "cluster_id": cl.id,
                "mirror_connection_ids": json.dumps(cl.mirror_connection_ids, ensure_ascii=False),
                "cluster_size": cl.evidence_count, "merge_reason": cl.merge_reason,
            })
        for chunk_start in range(0, len(lineage_rows), 500):
            chunk = lineage_rows[chunk_start:chunk_start + 500]
            phs, params = [], {}
            for i, r in enumerate(chunk):
                p = f"l{chunk_start + i}"
                phs.append(f"(:{p}_cid, :{p}_clid, :{p}_mi, :{p}_cs, :{p}_mr)")
                params.update({
                    f"{p}_cid": r["canonical_id"], f"{p}_clid": r["cluster_id"],
                    f"{p}_mi": r["mirror_connection_ids"], f"{p}_cs": r["cluster_size"],
                    f"{p}_mr": r["merge_reason"],
                })
            await session.execute(text(
                "INSERT INTO canonical_connection_lineage (canonical_id, cluster_id, "
                "mirror_connection_ids, cluster_size, merge_reason) VALUES " + ",".join(phs)), params)
        await session.commit()

        # ---- 质量断言 ----
        lineage_clusters = (await session.execute(text(
            "SELECT count(DISTINCT cluster_id) FROM canonical_connection_lineage"))).scalar()
        assert lineage_clusters == len(clusters), f"lineage coverage {lineage_clusters} != {len(clusters)}"
        total_ev = (await session.execute(text(
            "SELECT coalesce(sum(cluster_size), 0) FROM canonical_connection_lineage"))).scalar()
        assert total_ev == sum(c.evidence_count for c in clusters), f"evidence loss: {total_ev}"
        key_dup = (await session.execute(text(
            """SELECT count(*) FROM (SELECT source_region_id, target_region_id, connection_type,
                   count(*) FROM canonical_connections
                   GROUP BY 1,2,3 HAVING count(*) > 1) t"""))).scalar()
        assert key_dup == 0, f"duplicate canonical keys: {key_dup}"
        mirror_after = (await session.execute(text(
            "SELECT count(*) FROM mirror_region_connections WHERE granularity_level='macro'"))).scalar()
        assert mirror_before == mirror_after, "mirror table modified!"
        total_canonical = (await session.execute(text("SELECT count(*) FROM canonical_connections"))).scalar()
        print(f"[ok] lineage: {lineage_clusters} clusters | evidence: {total_ev} | "
              f"canonical total: {total_canonical} | mirror unchanged: {mirror_before}=={mirror_after}")

        # ---- 导出报告 ----
        new_count = len(created_specs)
        report = {
            "cluster_count": len(clusters),
            "canonical_total_after": total_canonical,
            "reused_existing_canonical_clusters": len(reuse_plans),
            "reused_existing_canonical_ids": len({p.canonical_id for p in reuse_plans}),
            "new_canonical_count": new_count,
            "orphan_cluster_count": 0,
            "status": "proposed",
            "assertion_type": "reported_fact",
            "generation_method": GENERATION_METHOD,
        }
        ev_rep = {
            "evidence_coverage_pct": round(
                sum(1 for c in clusters if c.evidence_count > 0) / len(clusters) * 100, 2),
            "avg_evidence_per_cluster": round(
                sum(c.evidence_count for c in clusters) / len(clusters), 2),
            "no_evidence_canonical_count": sum(1 for a in agg.values() if a["evidence_count"] == 0),
            "total_evidence_rows": total_ev,
            "evidence_by_merge_reason": dict(Counter(c.merge_reason for c in clusters)),
        }
        lg_rep = {
            "lineage_completeness_pct": round(lineage_clusters / len(clusters) * 100, 2),
            "lineage_rows": lineage_clusters,
            "mirror_connection_ids_total": sum(len(c.mirror_connection_ids) for c in clusters),
            "canonical_to_cluster_ratio": round(len(clusters) / total_canonical, 2),
            "mirror_table_unchanged": mirror_before == mirror_after,
        }
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        for fname, data in [("canonical_generation_report.json", report),
                            ("evidence_summary_report.json", ev_rep),
                            ("lineage_report.json", lg_rep)]:
            (OUT_DIR / fname).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"[ok] {fname}")
        print(f"\nclusters {len(clusters)} -> reuse {len(reuse_plans)} cluster / new {new_count} | "
              f"evidence {total_ev} | canonical total {total_canonical}")


if __name__ == "__main__":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main())
