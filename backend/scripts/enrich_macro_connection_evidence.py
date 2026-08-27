"""Macro Connection Evidence Enrichment 实施脚本。

基于 canonical connection consolidation(第 3 层),为每条 canonical 生成:
1. 标准 Evidence Summary(evidence_count / sources[] / confidence min-max-mean /
   supporting_records[],canonical → cluster → mirror 三层可追溯)
2. Evidence Quality Score(high/medium/low,不改 confidence,依据落
   evidence_quality_factors)

幂等:全量重算 + UPDATE 覆盖(无需删除标记),重跑结果一致。
不执行:promotion、active 修改、Final KG、CN2 inference。
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services.macro_connection_evidence_service import (
    build_standard_evidence_summary,
    compute_evidence_quality,
)

OUT_DIR = Path(_backend) / "data" / "exports" / "macro_connection_evidence"

MIRROR_QUERY = """
SELECT m.id, m.llm_run_id, m.confidence, m.evidence_text, m.directionality,
       m.modality, m.source_atlas, l.canonical_id, l.cluster_id, l.cluster_size
FROM canonical_connection_lineage l
CROSS JOIN LATERAL jsonb_array_elements_text(l.mirror_connection_ids) mid
JOIN mirror_region_connections m ON m.id::text = mid
"""


def _num(v):
    return float(v) if v is not None else None


async def main() -> None:
    async with AsyncSessionLocal() as session:
        mirror_before = (await session.execute(text(
            "SELECT count(*) FROM mirror_region_connections WHERE granularity_level='macro'"))).scalar()

        # ---- 加载 ----
        canonicals = (await session.execute(text(
            """SELECT c.id, c.connection_code, c.source_region_id, c.target_region_id,
                      c.connection_type, c.directionality_policy, c.evidence_count,
                      c.confidence_statistics, c.evidence_summary,
                      rs.canonical_name_en AS source_region_name,
                      rt.canonical_name_en AS target_region_name
               FROM canonical_connections c
               LEFT JOIN canonical_brain_regions rs ON rs.id = c.source_region_id
               LEFT JOIN canonical_brain_regions rt ON rt.id = c.target_region_id
               ORDER BY c.id"""  # noqa: E501
        ))).all()
        canon = {str(r.id): {
            "id": str(r.id), "connection_code": r.connection_code,
            "source_region_id": str(r.source_region_id),
            "target_region_id": str(r.target_region_id),
            "connection_type": r.connection_type,
            "directionality_policy": r.directionality_policy,
            "evidence_count": r.evidence_count or 0,
            "confidence_statistics": r.confidence_statistics or {},
            "evidence_summary": r.evidence_summary or {},
            "source_region_name": r.source_region_name,
            "target_region_name": r.target_region_name,
        } for r in canonicals}
        print(f"canonicals: {len(canon)}")

        # canonical_id → lineage 行(cluster_id, cluster_size, mirror ids)
        lineage = defaultdict(list)
        for r in (await session.execute(text(
            "SELECT canonical_id, cluster_id, cluster_size, mirror_connection_ids "
            "FROM canonical_connection_lineage"))).all():
            lineage[str(r.canonical_id)].append({
                "cluster_id": r.cluster_id, "cluster_size": r.cluster_size,
                "mirror_connection_ids": r.mirror_connection_ids or [],
            })
        print(f"lineage rows: {sum(len(v) for v in lineage.values())}")

        # mirror 行(带 canonical/cluster 归属)
        mirror_rows_by_canonical: dict[str, list[dict]] = defaultdict(list)
        missing = 0
        total_linked = 0
        for r in (await session.execute(text(MIRROR_QUERY))).all():
            total_linked += 1
            mirror_rows_by_canonical[str(r.canonical_id)].append({
                "id": str(r.id), "llm_run_id": str(r.llm_run_id) if r.llm_run_id else None,
                "confidence": _num(r.confidence), "evidence_text": r.evidence_text or "",
                "directionality": r.directionality, "modality": r.modality,
                "source_atlas": r.source_atlas, "cluster_id": r.cluster_id,
            })
        # 缺失校验:lineage 内 mirror id 总数 vs join 到行数
        lineage_total = sum(len(l["mirror_connection_ids"])
                            for rows in lineage.values() for l in rows)
        missing = lineage_total - total_linked
        print(f"lineage mirror ids: {lineage_total} | resolved: {total_linked} | missing: {missing}")
        assert missing == 0, "unresolved mirror ids in lineage!"

        # ---- 生成标准 Evidence Summary + Quality Score ----
        updates = []
        global_confs: list[float] = []
        for cid, c in canon.items():
            rows = mirror_rows_by_canonical.get(cid, [])
            clusters = [l["cluster_id"] for l in lineage.get(cid, [])]
            cluster_meta = c["evidence_summary"]  # 第 3 层聚合统计(merge_reasons 等)
            summary = build_standard_evidence_summary(cid, clusters, rows, cluster_meta)
            score, factors = compute_evidence_quality(len(rows), rows)
            assert summary["evidence_count"] == len(rows)
            assert summary["evidence_count"] == c["evidence_count"], \
                f"evidence mismatch {cid}: summary {summary['evidence_count']} vs column {c['evidence_count']}"
            assert len(summary["supporting_records"]) == len(rows)
            # 每条 supporting record 可追溯 cluster
            assert all(rec["cluster_id"] is not None for rec in summary["supporting_records"]), \
                f"record without cluster {cid}"
            updates.append({
                "cid": cid, "es": json.dumps(summary, ensure_ascii=False),
                "qs": score, "qf": json.dumps(factors, ensure_ascii=False),
            })
            # 回填内存(报告用新标准结构)
            canon[cid]["evidence_summary"] = summary
            canon[cid]["evidence_quality_score"] = score
            canon[cid]["quality_factors"] = factors
            global_confs.extend(rec["confidence"] for rec in summary["supporting_records"]
                                if rec["confidence"] is not None)

        await session.execute(text(
            """UPDATE canonical_connections SET evidence_summary = :es,
                   evidence_quality_score = :qs, evidence_quality_factors = :qf
               WHERE id = :id"""),
            [{"id": u["cid"], "es": u["es"], "qs": u["qs"], "qf": u["qf"]}
             for u in updates])
        await session.commit()
        print(f"enriched {len(updates)} canonicals")

        # ---- 质量断言 ----
        total_ev = (await session.execute(text(
            "SELECT coalesce(sum(evidence_count), 0) FROM canonical_connections"))).scalar()
        lineage_ev = (await session.execute(text(
            "SELECT coalesce(sum(cluster_size), 0) FROM canonical_connection_lineage"))).scalar()
        assert total_ev == lineage_ev == len(global_confs) == total_linked, \
            f"evidence conservation: {total_ev} / {lineage_ev} / {len(global_confs)} / {total_linked}"
        qd = dict((await session.execute(text(
            "SELECT coalesce(evidence_quality_score, 'low'), count(*) FROM canonical_connections "
            "GROUP BY 1 ORDER BY 2 DESC"))).all())
        print(f"quality: {qd}")
        no_es = (await session.execute(text(
            "SELECT count(*) FROM canonical_connections WHERE evidence_summary::text = '{}' "
            "OR NOT evidence_summary ? 'sources'"))).scalar()
        assert no_es == 0, f"canonicals without standard evidence_summary: {no_es}"
        mirror_after = (await session.execute(text(
            "SELECT count(*) FROM mirror_region_connections WHERE granularity_level='macro'"))).scalar()
        assert mirror_before == mirror_after, "mirror table modified!"
        print(f"[ok] evidence {total_ev} conserved | quality {qd} | mirror {mirror_before}=={mirror_after}")

        # ---- 导出报告 ----
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        _export_reports(canon, lineage, mirror_rows_by_canonical, qd, global_confs, total_linked)
        print(f"\n[ok] reports -> {OUT_DIR}")


def _export_reports(canon, lineage, mirror_rows, qd, global_confs, total_linked) -> None:
    # 1) evidence_coverage.json
    with_ev = sum(1 for c in canon.values() if c["evidence_count"] > 0)
    _EV_BUCKETS = ["0", "1", "2-4", "5-9", "10+"]
    ev_dist = Counter()
    for c in canon.values():
        n = c["evidence_count"]
        ev_dist["0" if n == 0 else ("1" if n == 1 else ("2-4" if n <= 4 else ("5-9" if n <= 9 else "10+")))] += 1
    run_dist = Counter()
    for rows in mirror_rows.values():
        run_dist[min(len({r["llm_run_id"] for r in rows if r["llm_run_id"]}), 3)] += 1
    coverage = {
        "total_canonical": len(canon),
        "with_evidence": with_ev,
        "coverage_pct": round(with_ev / len(canon) * 100, 2),
        "no_source_count": len(canon) - with_ev,
        "no_source_reason": "canonical without cluster match (2026-08-20 pre-existing row, "
                            "no lineage)",
        "evidence_count_distribution": {k: ev_dist.get(k, 0) for k in _EV_BUCKETS},
        "source_type_dist": {"llm_extraction": with_ev},
        "distinct_llm_run_dist": {"1_run": run_dist.get(1, 0), "2_runs": run_dist.get(2, 0),
                                  "3+_runs": run_dist.get(3, 0)},
        "supporting_records_total": total_linked,
        "lineage_coverage_pct": 100.0,
        "cluster_count": sum(len(v) for v in lineage.values()),
        "global_confidence": {
            "min": round(min(global_confs), 4) if global_confs else None,
            "max": round(max(global_confs), 4) if global_confs else None,
            "mean": round(sum(global_confs) / len(global_confs), 4) if global_confs else None,
            "count": len(global_confs),
        },
    }
    (OUT_DIR / "evidence_coverage.json").write_text(
        json.dumps(coverage, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[ok] evidence_coverage.json")

    # 2) evidence_quality_report.json
    quality = {
        "quality_distribution": {k: {"count": qd.get(k, 0),
                                     "pct": round(qd.get(k, 0) / len(canon) * 100, 2)}
                                 for k in ("high", "medium", "low")},
        "scoring": {"weights": {"evidence": 0.45, "sources": 0.35, "consistency": 0.20},
                    "thresholds": {"high": ">= 0.7", "medium": ">= 0.45", "low": "< 0.45"},
                    "note": "analysis score only; canonical confidence untouched"},
        "no_evidence_canonicals": [{"connection_code": c["connection_code"],
                                    "source_region": c["source_region_name"],
                                    "target_region": c["target_region_name"]}
                                   for c in canon.values() if c["evidence_count"] == 0],
    }
    (OUT_DIR / "evidence_quality_report.json").write_text(
        json.dumps(quality, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[ok] evidence_quality_report.json")

    # 3) connection_evidence_examples.json
    buckets = {"high": [], "medium": [], "low": []}
    for c in canon.values():
        es = c["evidence_summary"]
        buckets.get(c.get("evidence_quality_score") or "low", []).append({
            "canonical_connection_id": c["id"],
            "connection_code": c["connection_code"],
            "source_region": c["source_region_name"],
            "target_region": c["target_region_name"],
            "connection_type": c["connection_type"],
            "directionality_policy": c["directionality_policy"],
            "evidence_count": c["evidence_count"],
            "sources": es.get("sources", []),
            "confidence": {"min": es.get("confidence_min"), "max": es.get("confidence_max"),
                           "mean": es.get("confidence_mean")},
            "quality_factors": c.get("quality_factors", {}),
        })
    examples = {k: v[:3] for k, v in buckets.items()}
    (OUT_DIR / "connection_evidence_examples.json").write_text(
        json.dumps(examples, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[ok] connection_evidence_examples.json")


if __name__ == "__main__":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main())
