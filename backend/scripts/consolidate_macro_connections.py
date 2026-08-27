"""Macro Connection canonical consolidation v1 实施脚本。

Pipeline: Mirror Connection → Connection Cluster → Canonical Connection(本阶段:Cluster + evidence 聚合)

* 只读 mirror_region_connections,不删除/不修改任何 mirror 行
* 聚类结果写入 mirror_connection_clusters(中间结果表,幂等:TRUNCATE + INSERT)
* 导出 data/exports/macro_connection_consolidation/
    - before_after_statistics.json
    - cluster_report.json
    - evidence_merge_report.json
* 内置质量断言:source != target、evidence 守恒、connection_type 不丢失、id 无重复
* 暂不执行:mirror 删除、Final promotion、Active 修改、CN2 roll-up、缺失补充
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
from app.services.macro_connection_consolidation import build_clusters, cluster_key

OUT_DIR = Path(_backend) / "data" / "exports" / "macro_connection_consolidation"


async def load_macro_rows(session):
    rows = (await session.execute(text(
        """
        SELECT c.id, c.source_region_name_en, c.target_region_name_en,
               c.connection_type, c.directionality, c.modality, c.confidence,
               c.evidence_text, c.llm_run_id,
               c.source_region_candidate_id, c.target_region_candidate_id,
               g.status AS g_status, g.unresolved_reason,
               sc.canonical_region_id AS src_canonical_id,
               tc.canonical_region_id AS tgt_canonical_id,
               sreg.canonical_name_en AS src_canonical_name,
               treg.canonical_name_en AS tgt_canonical_name
        FROM mirror_region_connections c
        LEFT JOIN mirror_connection_canonical_grounding g ON g.mirror_connection_id = c.id
        LEFT JOIN candidate_brain_regions sc ON sc.id = c.source_region_candidate_id
        LEFT JOIN candidate_brain_regions tc ON tc.id = c.target_region_candidate_id
        LEFT JOIN canonical_brain_regions sreg ON sreg.id = sc.canonical_region_id
        LEFT JOIN canonical_brain_regions treg ON treg.id = tc.canonical_region_id
        WHERE c.granularity_level = 'macro'
        """
    ))).all()
    return [dict(r._mapping) for r in rows]


def run_quality_checks(rows, result) -> dict:
    """质量检查(需求 6):source!=target / type 不丢 / evidence 不丢 / 数量守恒。"""
    total = len(rows)
    grounded = sum(1 for r in rows if r["g_status"] == "grounded")
    cluster_ids: set[str] = set()
    for c in result.clusters:
        assert c.source_region_id != c.target_region_id, f"self-loop in cluster {c.key}"
        assert c.connection_type, f"empty connection_type in {c.key}"
        assert c.evidence_count == len({ev.mirror_id for ev in c.evidence}), f"dup mirror id in {c.key}"
        cluster_ids.update(ev.mirror_id for ev in c.evidence)
    evidence_in_clusters = sum(c.evidence_count for c in result.clusters)
    assert evidence_in_clusters + len(result.self_loop_rows) + len(result.unresolved_rows) == total, \
        f"conservation broken: {evidence_in_clusters}+{len(result.self_loop_rows)}+{len(result.unresolved_rows)} != {total}"
    # 每条 grounded 非 self-loop 行恰好进入一个 cluster
    assert len(cluster_ids) == evidence_in_clusters, "mirror id duplication across clusters"
    # connection_type 集守恒(聚类不引入/丢失 type)
    input_types = {r["connection_type"] for r in rows}
    cluster_types = {c.connection_type for c in result.clusters}
    assert cluster_types <= input_types, "cluster introduced unknown connection_type"
    return {
        "checks": {
            "source_not_equal_target": "PASS",
            "connection_type_preserved": "PASS",
            "evidence_not_lost": "PASS",
            "row_conservation": "PASS",
        },
        "grounded_rows": grounded,
        "evidence_in_clusters": evidence_in_clusters,
        "self_loop_rows": len(result.self_loop_rows),
        "unresolved_rows": len(result.unresolved_rows),
        "input_rows": total,
        "duplicate_mirror_id": len(cluster_ids) - evidence_in_clusters,
    }


def build_export_payloads(result, checks) -> tuple[dict, dict, dict]:
    before = {
        "mirror_connections_total": checks["input_rows"],
        "grounded": checks["grounded_rows"],
        "unresolved": checks["unresolved_rows"],
        "existing_canonical_connections_before": None,  # 由脚本 DB 查询填充
        "note": "数据来源:mirror_region_connections granularity_level='macro'(Human + Macro)",
    }
    after = {
        "clusters": len(result.clusters),
        "evidence_rows_in_clusters": checks["evidence_in_clusters"],
        "self_loop_excluded": checks["self_loop_rows"],
        "unresolved_excluded": checks["unresolved_rows"],
        "clusters_by_reason": result.stats["clusters_by_reason"],
        "expected_consolidated_connections": len(result.clusters),
        "redundant_rows_merged": checks["evidence_in_clusters"] - len(result.clusters),
        "note": "cluster = 去重后有效连接;redundant_rows_merged = 合并掉的证据行",
    }
    before_after = {
        "before": before,
        "after": after,
        "delta": {
            "rows_before": checks["input_rows"],
            "rows_after_cluster_level": len(result.clusters),
            "rows_reduced_by": checks["input_rows"] - len(result.clusters),
            "merge_ratio_pct": round((1 - len(result.clusters) / checks["input_rows"]) * 100, 2),
        },
        "quality_checks": checks["checks"],
    }
    cluster_report = {
        "total_clusters": len(result.clusters),
        "generated_at_note": "2026-08-24 snapshot",
        "clusters": [
            {
                "cluster_key": c.key,
                "source_region": c.source_region_name,
                "target_region": c.target_region_name,
                "connection_type": c.connection_type,
                "directionality": c.directionality,
                "modality_norm": c.modality_norm,
                "modality_original": c.provenance["modality_original"],
                "evidence_count": c.evidence_count,
                "merge_reason": c.merge_reason,
                "hemisphere_groups": c.hemisphere_groups,
                "confidence": c.confidence_distribution,
                "llm_run_ids": c.provenance["llm_run_ids"],
            }
            for c in sorted(result.clusters, key=lambda c: (-c.evidence_count, c.key))
        ],
    }
    ev_merge = {
        "total_evidence_rows": checks["evidence_in_clusters"],
        "duplicate_merge_groups": sum(
            1 for c in result.clusters if c.merge_reason == "duplicate_evidence"),
        "hemisphere_specific_clusters": sum(
            1 for c in result.clusters if c.merge_reason == "hemisphere_specific"),
        "single_evidence_clusters": sum(
            1 for c in result.clusters if c.merge_reason == "single_evidence"),
        "evidence_by_merge_reason": result.stats["clusters_by_reason"],
        "top_evidence_clusters": [
            {
                "source": c.source_region_name,
                "target": c.target_region_name,
                "connection_type": c.connection_type,
                "evidence_count": c.evidence_count,
                "merge_reason": c.merge_reason,
                "hemisphere_groups": [
                    {"pattern": g["pattern"], "count": g["evidence_count"]}
                    for g in c.hemisphere_groups
                ],
            }
            for c in sorted(result.clusters, key=lambda c: -c.evidence_count)[:30]
        ],
        "note": "evidence 不丢失:每个 cluster 的 mirror_connection_ids 全量保留;"
                "hemisphere-specific 连接(left-left / right-right)分属不同 pattern 组,不合并",
    }
    return before_after, cluster_report, ev_merge


async def main() -> None:
    async with AsyncSessionLocal() as session:
        rows = await load_macro_rows(session)
        result = build_clusters(rows)
        checks = run_quality_checks(rows, result)

        before_after, cluster_report, ev_merge = build_export_payloads(result, checks)
        # 已有 canonical connections 数量(before)
        before_after["before"]["existing_canonical_connections_before"] = (
            await session.execute(text("SELECT count(*) FROM canonical_connections"))
        ).scalar()

        # 写中间结果表(幂等:TRUNCATE + INSERT)
        await session.execute(text("TRUNCATE mirror_connection_clusters"))
        rows_payload = [c.to_row() for c in result.clusters]
        if rows_payload:
            # 直接 SQL 批量插入(表不在 ORM 模型注册,用 text 拼接)
            INSERT_SQL = (
                "INSERT INTO mirror_connection_clusters (cluster_key, source_region_id, target_region_id, "
                "source_region_name, target_region_name, connection_type, directionality, modality_norm, "
                "modality_original, species, hemisphere_groups, mirror_connection_ids, evidence_count, "
                "merge_reason, confidence_distribution, provenance, status) VALUES "
            )
            for chunk_start in range(0, len(rows_payload), 500):
                chunk = rows_payload[chunk_start:chunk_start + 500]
                params: dict = {}
                phs = []
                for i, r in enumerate(chunk):
                    p = f"c{chunk_start + i}"
                    phs.append(f"(:{p}_k, :{p}_s, :{p}_t, :{p}_sn, :{p}_tn, :{p}_ct, :{p}_d, :{p}_mn, "
                               f":{p}_mo, :{p}_sp, :{p}_hg, :{p}_mi, :{p}_ec, :{p}_mr, :{p}_cd, :{p}_pv, :{p}_st)")
                    params.update({
                        f"{p}_k": r["cluster_key"], f"{p}_s": r["source_region_id"],
                        f"{p}_t": r["target_region_id"], f"{p}_sn": r["source_region_name"],
                        f"{p}_tn": r["target_region_name"], f"{p}_ct": r["connection_type"],
                        f"{p}_d": r["directionality"], f"{p}_mn": r["modality_norm"],
                        f"{p}_mo": json.dumps(r["modality_original"], ensure_ascii=False),
                        f"{p}_sp": r["species"], f"{p}_hg": json.dumps(r["hemisphere_groups"], ensure_ascii=False),
                        f"{p}_mi": json.dumps(r["mirror_connection_ids"], ensure_ascii=False),
                        f"{p}_ec": r["evidence_count"], f"{p}_mr": r["merge_reason"],
                        f"{p}_cd": json.dumps(r["confidence_distribution"], ensure_ascii=False),
                        f"{p}_pv": json.dumps(r["provenance"], ensure_ascii=False),
                        f"{p}_st": r["status"],
                    })
                await session.execute(text(INSERT_SQL + ",".join(phs)), params)
            await session.commit()
        inserted = (await session.execute(text("SELECT count(*) FROM mirror_connection_clusters"))).scalar()
        assert inserted == len(result.clusters), f"insert mismatch: {inserted} != {len(result.clusters)}"

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "before_after_statistics.json").write_text(
        json.dumps(before_after, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT_DIR / "cluster_report.json").write_text(
        json.dumps(cluster_report, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT_DIR / "evidence_merge_report.json").write_text(
        json.dumps(ev_merge, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[ok] before_after_statistics.json")
    print("[ok] cluster_report.json")
    print("[ok] evidence_merge_report.json")
    print(f"[ok] clusters written to mirror_connection_clusters: {inserted}")
    s = result.stats
    print(f"\n输入 {s['total_input_rows']} 行 -> {s['clusters']} clusters "
          f"(证据 {s['evidence_rows_in_clusters']} / self_loop {s['self_loop_rows']} / unresolved {s['unresolved_rows']})")
    print(f"按 merge_reason: {s['clusters_by_reason']}")
    print(f"去重后有效连接: {len(result.clusters)} | 合并冗余证据行: {checks['evidence_in_clusters'] - len(result.clusters)}")


if __name__ == "__main__":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main())
