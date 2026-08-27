"""Macro Connection Validation V1 实施脚本。

对 2500 条 Macro Human Canonical Connection 执行第一版验证:
* 结构规则(7)/ Evidence 规则(4)/ 质量规则(2)
* 结果写入 canonical_connection_validation_runs + results
  (entity_type / entity_id / validation_status / failed_rules /
   validation_timestamp / validator_version)
* 幂等:重跑 = 删除同一 validator_key 的旧 run(级联 results)后重建

不执行:active 状态修改、promotion、Final KG 写入、CN2 inference、外部数据导入。
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services.macro_connection_validation_service import (
    VALIDATOR_KEY,
    VALIDATOR_VERSION,
    build_validation_context,
    summarize_results,
    validate_connection,
)

OUT_DIR = Path(_backend) / "data" / "exports" / "macro_connection_validation"


async def main() -> None:
    async with AsyncSessionLocal() as session:
        mirror_before = (await session.execute(text(
            "SELECT count(*) FROM mirror_region_connections WHERE granularity_level='macro'"))).scalar()
        canon_before = (await session.execute(text(
            "SELECT count(*) FROM canonical_connections"))).scalar()

        # ---- 加载 ----
        canonicals = (await session.execute(text(
            """SELECT id, source_region_id, target_region_id, connection_type,
                      directionality_policy, species, granularity_level,
                      evidence_count, provenance_json, confidence_statistics
               FROM canonical_connections ORDER BY id"""  # noqa: E501
        ))).all()
        canon_rows = [{
            "id": str(r.id), "source_region_id": str(r.source_region_id),
            "target_region_id": str(r.target_region_id),
            "connection_type": r.connection_type,
            "directionality_policy": r.directionality_policy,
            "species": r.species, "granularity_level": r.granularity_level,
            "evidence_count": r.evidence_count or 0,
            "provenance_json": r.provenance_json,
            "confidence_statistics": r.confidence_statistics or {},
        } for r in canonicals]
        print(f"canonicals: {len(canon_rows)}")

        region_ids = {str(x[0]) for x in (await session.execute(text(
            "SELECT id FROM canonical_brain_regions"))).all()}

        lineage_by_canonical: dict[str, list[dict]] = defaultdict(list)
        for r in (await session.execute(text(
            "SELECT canonical_id, cluster_size, mirror_connection_ids "
            "FROM canonical_connection_lineage"))).all():
            lineage_by_canonical[str(r.canonical_id)].append({
                "cluster_size": r.cluster_size,
                "mirror_connection_ids": [str(m) for m in (r.mirror_connection_ids or [])],
            })

        mirror_ids = {str(x[0]) for x in (await session.execute(text(
            "SELECT id FROM mirror_region_connections WHERE granularity_level='macro'"))).all()}

        dup_keys = {tuple(k) for k in (await session.execute(text(
            """SELECT source_region_id, target_region_id, connection_type
               FROM canonical_connections
               GROUP BY 1, 2, 3 HAVING count(*) > 1"""))).all()}

        ctx = build_validation_context(region_ids, lineage_by_canonical, dup_keys, mirror_ids)

        # ---- 验证 ----
        results = []
        for c in canon_rows:
            status, failed = validate_connection(c, ctx)
            results.append({
                "entity_type": "canonical_connection",
                "entity_id": c["id"],
                "validation_status": status,
                "failed_rules": failed,
            })
        summary = summarize_results(results)
        print(f"status: pass {summary['pass']} | fail {summary['fail']} | "
              f"review_required {summary['review_required']}")
        print("failed rules:", summary["failed_rule_counts"])

        # ---- 幂等清理 + 写入 ----
        await session.execute(text(
            "DELETE FROM canonical_connection_validation_runs WHERE validator_key = :k"),
            {"k": VALIDATOR_KEY})
        run_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        await session.execute(text(
            """INSERT INTO canonical_connection_validation_runs
               (id, validator_key, validator_version, scope_json, status,
                object_count, passed_count, failed_count, review_count,
                started_at, finished_at)
               VALUES (:id, :k, :v, :scope, :status, :obj, :pass, :fail, :review, :st, :ft)"""),
            {"id": run_id, "k": VALIDATOR_KEY, "v": VALIDATOR_VERSION,
             "scope": json.dumps({"entity_type": "canonical_connection",
                                  "granularity": "macro", "count": len(results)}),
             "status": "completed",
             "obj": summary["total"], "pass": summary["pass"],
             "fail": summary["fail"], "review": summary["review_required"],
             "st": now, "ft": now})
        await session.execute(text(
            """INSERT INTO canonical_connection_validation_results
               (id, run_id, entity_type, entity_id, validation_status,
                failed_rules, validator_version, validation_timestamp)
               VALUES (:id, :run, :et, :eid, :vs, :fr, :v, :ts)"""),
            [{"id": str(uuid.uuid4()), "run": run_id, "et": r["entity_type"],
              "eid": r["entity_id"], "vs": r["validation_status"],
              "fr": json.dumps(r["failed_rules"], ensure_ascii=False),
              "v": VALIDATOR_VERSION, "ts": now} for r in results])
        await session.commit()
        print(f"validation run {run_id}: {summary['total']} results written")

        # ---- 断言 ----
        stored = (await session.execute(text(
            "SELECT count(*) FROM canonical_connection_validation_results WHERE run_id = :rid"),
            {"rid": run_id})).scalar()
        assert stored == summary["total"], f"stored {stored} != {summary['total']}"
        db_counts = dict((await session.execute(text(
            "SELECT validation_status, count(*) FROM canonical_connection_validation_results "
            "WHERE run_id = :rid GROUP BY 1"), {"rid": run_id})).all())
        assert db_counts.get("PASS", 0) == summary["pass"], "PASS mismatch"
        assert db_counts.get("FAIL", 0) == summary["fail"], "FAIL mismatch"
        assert db_counts.get("REVIEW_REQUIRED", 0) == summary["review_required"], "REVIEW mismatch"
        mirror_after = (await session.execute(text(
            "SELECT count(*) FROM mirror_region_connections WHERE granularity_level='macro'"))).scalar()
        canon_after = (await session.execute(text("SELECT count(*) FROM canonical_connections"))).scalar()
        assert mirror_before == mirror_after and canon_before == canon_after, "data tables modified!"
        print(f"[ok] stored {stored} | mirror {mirror_before}=={mirror_after} | "
              f"canonical {canon_before}=={canon_after}")

        # ---- 导出报告 ----
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        _export_reports(summary, canon_rows, results)
        print(f"\n[ok] reports -> {OUT_DIR}")


def _export_reports(summary: dict, canon_rows: list[dict], results: list[dict]) -> None:
    canon_by_id = {c["id"]: c for c in canon_rows}

    # 1) validation_summary.json
    (OUT_DIR / "validation_summary.json").write_text(json.dumps({
        "validator_key": VALIDATOR_KEY,
        "validator_version": VALIDATOR_VERSION,
        "entity_type": "canonical_connection",
        "total": summary["total"],
        "pass": summary["pass"],
        "fail": summary["fail"],
        "review_required": summary["review_required"],
        "pass_pct": summary["pass_pct"],
        "status_rules": "FAIL = any structural rule failed; "
                        "REVIEW_REQUIRED = structural ok but evidence/quality failed",
        "failed_rule_counts": summary["failed_rule_counts"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[ok] validation_summary.json")

    # 2) failed_connections.json
    failed = [{
        "canonical_connection_id": r["entity_id"],
        "validation_status": r["validation_status"],
        "failed_rules": r["failed_rules"],
    } for r in results if r["validation_status"] == "FAIL"]
    (OUT_DIR / "failed_connections.json").write_text(json.dumps({
        "count": len(failed), "connections": failed,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[ok] failed_connections.json")

    # 3) review_candidates.json
    review = []
    for r in results:
        if r["validation_status"] != "REVIEW_REQUIRED":
            continue
        c = canon_by_id[r["entity_id"]]
        review.append({
            "canonical_connection_id": r["entity_id"],
            "source_region_id": c["source_region_id"],
            "target_region_id": c["target_region_id"],
            "connection_type": c["connection_type"],
            "evidence_count": c["evidence_count"],
            "failed_rules": r["failed_rules"],
        })
    (OUT_DIR / "review_candidates.json").write_text(json.dumps({
        "count": len(review), "candidates": review,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[ok] review_candidates.json")


if __name__ == "__main__":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main())
