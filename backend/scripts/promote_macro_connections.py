"""Macro Connection Promotion 实施脚本。

治理闭环:Validation PASS / Review approved → Active Canonical Connection
→ Final Canonical Connection (Final KG)。

守卫(服务层强制):
* 仅 validation PASS 或 review approved 可进入 Final;rejected / needs_more_evidence /
  review_pending / validation_fail 一律 skipped_ineligible。
* final_canonical_connections.canonical_connection_id UNIQUE = 幂等锚:
  已存在 final 行 → skipped_duplicate,不重复写入、不覆盖既有 provenance/evidence。

Promotion 记录:reviewer / timestamp / validation_run_id / evidence_reference /
promotion_reason(任务要求逐条可追溯)。

不执行:CN2 inference、外部数据导入。不删除 mirror / cluster / lineage。
输出: data/exports/macro_connection_promotion/(promotion_report.json +
final_connection_statistics.json)。
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
from app.services.macro_connection_review_promotion_service import (
    PROMOTION_KEY,
    check_promotion_eligibility,
    final_connection_from_canonical,
    latest_review_decision,
    summarize_final,
    summarize_promotion,
)

OUT_DIR = Path(_backend) / "data" / "exports" / "macro_connection_promotion"


async def main(args: argparse.Namespace) -> None:
    async with AsyncSessionLocal() as session:
        # ---- 前置快照(断言用) ----
        mirror_before = (await session.execute(text(
            "SELECT count(*) FROM mirror_region_connections"))).scalar()
        lineage_before = (await session.execute(text(
            "SELECT count(*) FROM canonical_connection_lineage"))).scalar()
        cluster_before = (await session.execute(text(
            "SELECT count(*) FROM mirror_connection_clusters"))).scalar()
        canon_status_before = dict((await session.execute(text(
            "SELECT status, count(*) FROM canonical_connections GROUP BY 1"))).all())

        # ---- 加载 ----
        canon_rows = (await session.execute(text(
            """SELECT id, connection_code, source_region_id, target_region_id,
                      connection_type, directionality_policy, species, granularity_level,
                      confidence, evidence_summary, provenance_json, assertion_type,
                      source_type, generation_method, evidence_reference, status
               FROM canonical_connections ORDER BY id"""))).all()
        canon_by_id = {str(c.id): c for c in canon_rows}
        print(f"canonicals: {len(canon_by_id)}")

        val_run_id = (await session.execute(text(
            "SELECT id FROM canonical_connection_validation_runs "
            "WHERE validator_key='macro_connection_validation_v1' ORDER BY created_at DESC LIMIT 1"
        ))).scalar()
        val_results = {}
        if val_run_id:
            for r in (await session.execute(text(
                "SELECT entity_id, validation_status FROM canonical_connection_validation_results "
                "WHERE run_id=:rid"), {"rid": val_run_id})).all():
                val_results[str(r.entity_id)] = r.validation_status
        print(f"validation_run: {val_run_id} | results: {len(val_results)}")

        review_rows = (await session.execute(text(
            "SELECT id, canonical_connection_id, action, reviewer, created_at, reviewer_note "
            "FROM canonical_connection_review_records"))).all()
        reviews = [{"id": str(r.id), "canonical_connection_id": str(r.canonical_connection_id),
                    "action": r.action, "reviewer": r.reviewer, "created_at": r.created_at,
                    "note": r.reviewer_note} for r in review_rows]
        final_rows = (await session.execute(text(
            "SELECT canonical_connection_id, id, evidence_summary, provenance_json, "
            "final_status, granularity_level, connection_type "
            "FROM final_canonical_connections"))).all()
        final_by_canonical = {str(f.canonical_connection_id): f for f in final_rows}
        print(f"existing final rows: {len(final_by_canonical)}")

        # ---- 逐 canonical 判定 ----
        run_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        records: list[dict] = []
        for cid, c in canon_by_id.items():
            vs = val_results.get(cid)
            review = latest_review_decision(reviews, cid)
            eligible, reason = check_promotion_eligibility(vs, review)

            if c.status == "active" and cid in final_by_canonical:
                records.append({"cid": cid, "status": "skipped_duplicate",
                                "reason": "already_in_final", "vs": vs, "review": review})
                continue
            if not eligible:
                records.append({"cid": cid, "status": "skipped_ineligible", "reason": reason,
                                "vs": vs, "review": review})
                continue

            # ---- 写入 Final 行 ----
            final = final_connection_from_canonical(
                {**{k: getattr(c, k) for k in (
                    "id", "connection_code", "source_region_id", "target_region_id",
                    "connection_type", "directionality_policy", "species",
                    "granularity_level", "confidence", "evidence_summary",
                    "provenance_json", "assertion_type", "source_type",
                    "generation_method", "evidence_reference")}},
                str(val_run_id) if val_run_id else None,
                review["id"] if review else None,
            )
            inserted = (await session.execute(text(
                """INSERT INTO final_canonical_connections
                   (id, canonical_connection_id, connection_code, source_region_id,
                    target_region_id, connection_type, directionality_policy, species,
                    granularity_level, confidence, evidence_summary, provenance_json,
                    assertion_type, source_type, generation_method, evidence_reference,
                    validation_run_id, review_record_id, final_status)
                   VALUES (:id, :cid, :code, :src, :tgt, :ctype, :dir, :sp, :gran,
                           :conf, :es, :pj, :at, :st, :gm, :er, :vr, :rr, 'active')
                   ON CONFLICT (canonical_connection_id) DO NOTHING
                   RETURNING id"""),
                {"id": str(uuid.uuid4()), "cid": final["canonical_connection_id"],
                 "code": final["connection_code"], "src": final["source_region_id"],
                 "tgt": final["target_region_id"], "ctype": final["connection_type"],
                 "dir": final["directionality_policy"], "sp": final["species"],
                 "gran": final["granularity_level"], "conf": final["confidence"],
                 "es": json.dumps(final["evidence_summary"], ensure_ascii=False),
                 "pj": json.dumps(final["provenance_json"], ensure_ascii=False),
                 "at": final["assertion_type"], "st": final["source_type"],
                 "gm": final["generation_method"],
                 "er": json.dumps(final["evidence_reference"], ensure_ascii=False),
                 "vr": final["validation_run_id"], "rr": final["review_record_id"]})).first()
            if inserted is None:
                records.append({"status": "skipped_duplicate", "reason": "already_in_final"})
                continue
            final_id = str(inserted[0])
            await session.execute(text(
                "UPDATE canonical_connections SET status='active' WHERE id=:cid"),
                {"cid": cid})
            records.append({
                "cid": cid, "status": "promoted", "reason": reason,
                "final_id": final_id, "review": review,
                "evidence_reference": final["evidence_reference"],
                "before_status": c.status,
            })

        # ---- Promotion run + records ----
        promoted = [r for r in records if r["status"] == "promoted"]
        dup = [r for r in records if r["status"] == "skipped_duplicate"]
        ineligible = [r for r in records if r["status"] == "skipped_ineligible"]
        await session.execute(text(
            """INSERT INTO canonical_connection_promotion_runs
               (id, promotion_key, status, scope_json, eligible_count, promoted_count,
                skipped_count, rejected_count, reviewer, started_at, finished_at)
               VALUES (:id, :key, 'completed', :scope, :elig, :prom, :skip, :rej, :rev, :st, :ft)"""),
            {"id": run_id, "key": PROMOTION_KEY,
             "scope": json.dumps({"entity_type": "canonical_connection",
                                  "validation_run_id": str(val_run_id) if val_run_id else None,
                                  "count": len(records)}, ensure_ascii=False),
             "elig": len(promoted) + len(dup), "prom": len(promoted),
             "skip": len(dup), "rej": len(ineligible), "rev": args.reviewer,
             "st": now, "ft": now})
        await session.execute(text(
            """INSERT INTO canonical_connection_promotion_records
               (id, run_id, canonical_connection_id, final_canonical_connection_id,
                validation_run_id, review_record_id, reviewer, promotion_reason,
                evidence_reference, status, message, before_json, after_json)
               VALUES (:id, :run, :cid, :fid, :vr, :rr, :rev, :reason, :er, :status, :msg, :before, :after)"""),
            [{
                "id": str(uuid.uuid4()), "run": run_id,
                "cid": r["cid"], "fid": r.get("final_id"),
                "vr": str(val_run_id) if val_run_id else None,
                "rr": (r.get("review") or {}).get("id"),
                "rev": args.reviewer, "reason": r["reason"],
                "er": json.dumps(r.get("evidence_reference") or [], ensure_ascii=False),
                "status": r["status"],
                "msg": r.get("reason"),
                "before": json.dumps({"canonical_status": r.get("before_status")}, ensure_ascii=False),
                "after": json.dumps({"canonical_status": "active"}, ensure_ascii=False),
            } for r in records])
        await session.commit()
        summary = summarize_promotion(records)
        print(f"promotion: promoted {summary['promoted']} | skipped_dup "
              f"{summary['skipped_duplicate']} | ineligible {summary['skipped_ineligible']}")
        print("by_reason:", summary["by_reason"])

        # ---- 断言 ----
        stored = (await session.execute(text(
            "SELECT count(*) FROM canonical_connection_promotion_records WHERE run_id=:rid"),
            {"rid": run_id})).scalar()
        assert stored == len(records), f"stored {stored} != {len(records)}"
        final_count = (await session.execute(text(
            "SELECT count(*) FROM final_canonical_connections"))).scalar()
        assert final_count == len(final_by_canonical) + len(promoted), (
            f"final {final_count} != {len(final_by_canonical)} + {len(promoted)}")
        active_count = (await session.execute(text(
            "SELECT count(*) FROM canonical_connections WHERE status='active'"))).scalar()
        assert active_count == len(final_by_canonical) + len(promoted), (
            f"active {active_count} != final {final_count}")
        # 数据表未动
        assert (await session.execute(text(
            "SELECT count(*) FROM mirror_region_connections"))).scalar() == mirror_before
        assert (await session.execute(text(
            "SELECT count(*) FROM canonical_connection_lineage"))).scalar() == lineage_before
        assert (await session.execute(text(
            "SELECT count(*) FROM mirror_connection_clusters"))).scalar() == cluster_before
        # evidence / provenance 保留(final 行与 canonical 行一致)
        mismatch = (await session.execute(text(
            """SELECT count(*) FROM final_canonical_connections f
               JOIN canonical_connections c ON c.id = f.canonical_connection_id
               WHERE f.evidence_summary::text <> c.evidence_summary::text
                  OR f.provenance_json::text <> c.provenance_json::text"""))).scalar()
        assert mismatch == 0, f"evidence/provenance mismatch in {mismatch} final rows"
        print(f"[ok] stored {stored} | final {final_count} | active {active_count} | "
              f"mirror {mirror_before}== line lineage {lineage_before}== | "
              f"clusters {cluster_before}== | evidence/provenance preserved")

        # ---- 报告 ----
        _export_reports(summary, final_rows, promoted, ineligible, canon_by_id, val_run_id)
        print(f"[ok] reports -> {OUT_DIR}")


def _export_reports(summary: dict, existing_finals: list, promoted: list[dict],
                    ineligible: list[dict], canon_by_id, val_run_id) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1) promotion_report.json
    detail = []
    for r in promoted:
        c = canon_by_id.get(r["cid"])
        detail.append({
            "canonical_connection_id": r["cid"],
            "connection_code": getattr(c, "connection_code", None),
            "final_canonical_connection_id": r.get("final_id"),
            "validation_run_id": str(val_run_id) if val_run_id else None,
            "review_record_id": (r.get("review") or {}).get("id"),
            "promotion_reason": r.get("reason"),
            "status": "promoted",
        })
    (OUT_DIR / "promotion_report.json").write_text(json.dumps({
        "promotion_key": PROMOTION_KEY,
        "total_canonical": len(canon_by_id),
        "promoted": summary["promoted"],
        "skipped_duplicate": summary["skipped_duplicate"],
        "skipped_ineligible": summary["skipped_ineligible"],
        "by_reason": summary["by_reason"],
        "promoted_connections": detail,
        "ineligible": [{
            "canonical_connection_id": r["cid"],
            "reason": r.get("reason"),
        } for r in ineligible],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[ok] promotion_report.json")

    # 2) final_connection_statistics.json
    finals = [{"canonical_connection_id": str(f.canonical_connection_id),
               "evidence_summary": f.evidence_summary or {},
               "provenance_json": f.provenance_json or {},
               "final_status": f.final_status, "granularity_level": f.granularity_level,
               "connection_type": f.connection_type}
              for f in existing_finals]
    finals += [{"canonical_connection_id": r["cid"],
                "evidence_summary": canon_by_id[r["cid"]].evidence_summary or {},
                "provenance_json": canon_by_id[r["cid"]].provenance_json or {},
                "final_status": "active",
                "granularity_level": canon_by_id[r["cid"]].granularity_level,
                "connection_type": canon_by_id[r["cid"]].connection_type}
               for r in promoted if r["cid"] in canon_by_id]
    stats = summarize_final(finals, len(canon_by_id))
    (OUT_DIR / "final_connection_statistics.json").write_text(json.dumps({
        **stats, "generated_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[ok] final_connection_statistics.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Macro Connection Promotion to Final KG")
    parser.add_argument("--reviewer", default="promotion_operator")
    args = parser.parse_args()
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main(args))
