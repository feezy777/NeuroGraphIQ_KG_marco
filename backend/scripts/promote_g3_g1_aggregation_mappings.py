"""Gate 7B Phase 1F-I — G3→G1 Aggregation Promotion (246 rows, single transaction).

Promotes the 246 approved G3→G1 aggregation mappings to active knowledge:
  * all 246: record_status proposed -> active  (review_status stays approved)
  * 172 contained_in: rollup_eligible=TRUE, is_primary_rollup=TRUE
  * dominant_overlap / partial_overlap: stay rollup_eligible=FALSE, is_primary_rollup=FALSE

Scientific payload (excludes record_status / rollup_eligible / is_primary_rollup)
is hashed before and after; hashes must be identical.

Rerun safety: if all 246 are already active with correct rollup state, NOOP.
Any partial proposed/active mix fails closed.

Usage:
    python scripts/promote_g3_g1_aggregation_mappings.py [--plan]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import psycopg
except ImportError:  # pragma: no cover
    sys.exit("psycopg (psycopg3) required")

BACKEND = Path(__file__).resolve().parent.parent
DATA = BACKEND / "data" / "integration"
DB = "neurographiq_human_brain_v1"
TABLE = "brain_region_aggregation_mappings"
REVIEW_CSV = DATA / "g3_to_g1_production_aggregation_review.csv"
AUDIT_JSON = DATA / "g3_to_g1_aggregation_promotion_audit.json"

PROMOTION_PHASE = "G3_G1_AGGREGATION_PROMOTION_V1"
SOURCE_APPROVAL_PHASE = "G3_G1_AGGREGATION_APPROVAL_V1"
REVIEWER = "gate1fh_g3_g1_aggregation_approval"

# payload columns that must be UNCHANGED across promotion
# (excluded: record_status, rollup_eligible, is_primary_rollup — the promotion targets)
PAYLOAD_COLS = [
    "mapping_id", "source_region_pk", "target_region_pk", "mapping_relation",
    "mapping_method", "source_granularity_level", "target_granularity_level",
    "source_coverage_ratio", "target_coverage_ratio", "spatial_overlap_ratio",
    "mapping_confidence", "scientific_source_pk", "provenance_json",
    "review_status", "reviewed_by", "reviewed_at", "remark",
]


def _sha256(v: str) -> str:
    return hashlib.sha256(v.encode("utf-8")).hexdigest()


def _payload_hash(rows: list[tuple]) -> str:
    canon = sorted("|".join("" if v is None else str(v) for v in r) for r in rows)
    return _sha256("\n".join(canon))


def _read_allowlist() -> list[str]:
    with open(REVIEW_CSV, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    eligible = [r["mapping_id"] for r in rows if r["approval_eligibility"] == "ELIGIBLE_FOR_APPROVAL"]
    if len(eligible) != 246 or len(set(eligible)) != 246:
        raise SystemExit("FAIL: review allowlist must be exactly 246 unique ELIGIBLE mapping_ids")
    return eligible


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", action="store_true", help="dry-run: report, update nothing")
    parser.add_argument("--db", default=DB)
    args = parser.parse_args()

    allowlist = _read_allowlist()

    conn = psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=args.db, autocommit=False)
    cur = conn.cursor()

    def q(sql, *a):
        cur.execute(sql, *a)
        return cur.fetchone()[0]

    # ---- preflight (read-only) ----
    rows = q("SELECT count(*) FROM brain_region_aggregation_mappings")
    proposed = q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE record_status='proposed'")
    active = q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE record_status='active'")
    approved = q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE review_status='approved'")
    pending = q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE review_status='pending'")
    rollup = q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE rollup_eligible=TRUE")
    primary = q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE is_primary_rollup=TRUE")
    contained = q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE mapping_relation='contained_in'")
    dominant = q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE mapping_relation='dominant_overlap'")
    partial = q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE mapping_relation='partial_overlap'")
    rb_ok = q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE reviewed_by=%s", (REVIEWER,))
    ra_notnull = q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE reviewed_at IS NOT NULL")

    # ---- rerun safety: all already active with correct rollup -> NOOP ----
    if rows == 246 and active == 246 and proposed == 0 and approved == 246:
        # verify rollup state is exactly right (172 contained rollup, no dominant/partial rollup)
        ru_ok = q("""SELECT count(*) FROM brain_region_aggregation_mappings
            WHERE rollup_eligible=TRUE AND is_primary_rollup=TRUE
              AND mapping_relation='contained_in' AND record_status='active' AND review_status='approved'""")
        dom_leak = q("""SELECT count(*) FROM brain_region_aggregation_mappings
            WHERE (rollup_eligible=TRUE OR is_primary_rollup=TRUE)
              AND mapping_relation<>'contained_in'""")
        if ru_ok == 172 and dom_leak == 0:
            conn.rollback()
            print(f"RERUN NO-OP: 246 already active with correct rollup; promoted=0")
            if AUDIT_JSON.exists() and AUDIT_JSON.stat().st_size > 0:
                _record_rerun()
            else:
                _write_audit(cur, allowlist, promoted=0, rows_after=246, txn="NOOP_RERUN",
                             payload_unchanged=True, formal_counts=None)
            conn.close()
            return 0
        conn.rollback()
        print("FAIL CLOSED: 246 active but rollup state incorrect; require investigation")
        return 3
    if active not in (0, 246):
        conn.rollback()
        print(f"FAIL CLOSED: partial active state ({active}/246); require investigation")
        return 3

    # ---- strict first-run preflight ----
    expected = {"rows": 246, "proposed": 246, "active": 0, "approved": 246, "pending": 0,
                "rollup": 0, "primary": 0, "contained": 172, "dominant": 34, "partial": 40,
                "rb_ok": 246, "ra_notnull": 246}
    got = {"rows": rows, "proposed": proposed, "active": active, "approved": approved,
           "pending": pending, "rollup": rollup, "primary": primary, "contained": contained,
           "dominant": dominant, "partial": partial, "rb_ok": rb_ok, "ra_notnull": ra_notnull}
    if got != expected:
        conn.rollback()
        print("FAIL CLOSED: preflight mismatch")
        for k in expected:
            if got[k] != expected[k]:
                print(f"  {k}: got {got[k]}, expected {expected[k]}")
        return 3

    # ---- payload snapshot (before) ----
    cur.execute(f"SELECT {', '.join(PAYLOAD_COLS)} FROM {TABLE} ORDER BY mapping_id")
    payload_before = cur.fetchall()
    hash_before = _payload_hash(payload_before)

    if args.plan:
        conn.rollback()
        print(f"[plan] would promote 246 rows (172 contained rollup)")
        conn.close()
        return 0

    # ---- promote all 246 to active (locked to allowlist) ----
    cur.execute(f"""UPDATE {TABLE}
        SET record_status='active'
        WHERE mapping_id = ANY(%s)
          AND record_status='proposed'
          AND review_status='approved'""", (allowlist,))
    promoted = cur.rowcount
    if promoted != 246:
        conn.rollback()
        print(f"FAIL CLOSED: promoted {promoted} != 246; rolled back")
        return 3

    # ---- enable rollup on the 172 contained only ----
    cur.execute(f"""UPDATE {TABLE}
        SET rollup_eligible=TRUE, is_primary_rollup=TRUE
        WHERE mapping_id = ANY(%s)
          AND mapping_relation='contained_in'
          AND record_status='active'
          AND review_status='approved'""", (allowlist,))
    ru = cur.rowcount
    if ru != 172:
        conn.rollback()
        print(f"FAIL CLOSED: contained rollup updated {ru} != 172; rolled back")
        return 3

    # ---- verify rollup only on contained ----
    dom_leak = q("""SELECT count(*) FROM brain_region_aggregation_mappings
        WHERE (rollup_eligible=TRUE OR is_primary_rollup=TRUE) AND mapping_relation<>'contained_in'""")
    if dom_leak != 0:
        conn.rollback()
        print(f"FAIL CLOSED: rollup leak on non-contained ({dom_leak}); rolled back")
        return 3

    # ---- payload snapshot (after) ----
    cur.execute(f"SELECT {', '.join(PAYLOAD_COLS)} FROM {TABLE} ORDER BY mapping_id")
    payload_after = cur.fetchall()
    hash_after = _payload_hash(payload_after)
    if hash_before != hash_after:
        conn.rollback()
        print("FAIL CLOSED: scientific payload changed during promotion; rolled back")
        return 3

    # ---- primary parent QA ----
    cur.execute("""SELECT count(*) FROM (
        SELECT source_region_pk FROM brain_region_aggregation_mappings
        WHERE record_status='active' AND review_status='approved'
          AND mapping_relation='contained_in' AND rollup_eligible=TRUE AND is_primary_rollup=TRUE
        GROUP BY source_region_pk HAVING count(*)>1) t""")
    multi_primary = cur.fetchone()[0]
    if multi_primary != 0:
        conn.rollback()
        print(f"FAIL CLOSED: multi-primary sources ({multi_primary}); rolled back")
        return 3

    # ---- commit only after all QA ----
    conn.commit()
    print(f"PROMOTED {promoted} rows; {ru} contained rollup enabled")

    # ---- formal query smoke (post-commit) ----
    formal_primary = q("""SELECT count(*) FROM brain_region_aggregation_mappings
        WHERE mapping_relation='contained_in' AND record_status='active'
          AND review_status='approved' AND rollup_eligible=TRUE AND is_primary_rollup=TRUE""")
    formal_all = q("""SELECT count(*) FROM brain_region_aggregation_mappings
        WHERE record_status='active' AND review_status='approved'""")
    formal_overlap = q("""SELECT count(*) FROM brain_region_aggregation_mappings
        WHERE record_status='active' AND review_status='approved'
          AND mapping_relation IN ('dominant_overlap','partial_overlap')""")
    formal_counts = {"primary": formal_primary, "all": formal_all, "overlap": formal_overlap}
    rows_after = q("SELECT count(*) FROM brain_region_aggregation_mappings")

    _write_audit(cur, allowlist, promoted=promoted, rows_after=rows_after, txn="COMMITTED",
                 payload_unchanged=True, formal_counts=formal_counts)
    conn.close()
    return 0


def _record_rerun() -> None:
    """Record a NOOP rerun without touching the committed promotion audit."""
    with open(AUDIT_JSON, encoding="utf-8") as f:
        audit = json.load(f)
    audit.setdefault("rerun_observations", []).append({
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "promoted_count": 0,
        "note": "RERUN NO-OP: all 246 already active with correct rollup; committed audit preserved",
    })
    AUDIT_JSON.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_audit(cur, allowlist, promoted, rows_after, txn, payload_unchanged, formal_counts):
    def q(sql, *a):
        cur.execute(sql, *a)
        return cur.fetchone()[0]

    contained = q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE mapping_relation='contained_in'")
    dominant = q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE mapping_relation='dominant_overlap'")
    partial = q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE mapping_relation='partial_overlap'")
    ru = q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE rollup_eligible=TRUE")
    pt = q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE is_primary_rollup=TRUE")
    primary_src = q("""SELECT count(DISTINCT source_region_pk) FROM brain_region_aggregation_mappings
        WHERE record_status='active' AND review_status='approved'
          AND mapping_relation='contained_in' AND rollup_eligible=TRUE AND is_primary_rollup=TRUE""")
    dupe = q("""SELECT count(*) FROM (
        SELECT source_region_pk FROM brain_region_aggregation_mappings
        WHERE record_status='active' AND review_status='approved'
          AND mapping_relation='contained_in' AND rollup_eligible=TRUE AND is_primary_rollup=TRUE
        GROUP BY source_region_pk HAVING count(*)>1) t""")
    dom_leak = q("""SELECT count(*) FROM brain_region_aggregation_mappings
        WHERE (rollup_eligible=TRUE OR is_primary_rollup=TRUE) AND mapping_relation='dominant_overlap'""")
    part_leak = q("""SELECT count(*) FROM brain_region_aggregation_mappings
        WHERE (rollup_eligible=TRUE OR is_primary_rollup=TRUE) AND mapping_relation='partial_overlap'""")
    exc_eids = [r["g3_entity_id"] for r in
                csv.DictReader(open(DATA / "g3_to_g1_mapping_candidate_exclusions.csv", encoding="utf-8-sig"))]
    excl_leak = q("""SELECT count(*) FROM brain_region_aggregation_mappings
        WHERE source_region_pk IN (SELECT b.entity_pk FROM brain_regions b
            JOIN kg_entities e ON e.entity_pk=b.entity_pk WHERE e.entity_id = ANY(%s))""",
        (list(set(exc_eids)),))

    audit = {
        "promotion_phase": PROMOTION_PHASE,
        "source_approval_phase": SOURCE_APPROVAL_PHASE,
        "rows_before": 246, "rows_after": rows_after,
        "promoted_count": promoted,
        "proposed_before": 246, "proposed_after": q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE record_status='proposed'"),
        "active_before": 0, "active_after": q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE record_status='active'"),
        "approved_before": 246, "approved_after": q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE review_status='approved'"),
        "contained_count": contained, "dominant_count": dominant, "partial_count": partial,
        "rollup_true_before": 0, "rollup_true_after": ru,
        "primary_true_before": 0, "primary_true_after": pt,
        "primary_source_count": primary_src,
        "duplicate_primary_count": dupe,
        "dominant_rollup_leak": dom_leak,
        "partial_rollup_leak": part_leak,
        "excluded_source_leak": excl_leak,
        "scientific_payload_unchanged": payload_unchanged,
        "formal_primary_query_count": formal_counts["primary"] if formal_counts else 172,
        "formal_all_mapping_query_count": formal_counts["all"] if formal_counts else 246,
        "formal_overlap_query_count": formal_counts["overlap"] if formal_counts else 74,
        "rerun_promoted_count": 0,
        "transaction_status": txn,
    }
    AUDIT_JSON.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
