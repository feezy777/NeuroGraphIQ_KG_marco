"""Gate 7B Phase 1F-H — G3→G1 Aggregation Approval (246 rows, single transaction).

Approves the 246 production brain_region_aggregation_mappings that passed the
Phase 1F-G review eligibility audit (g3_to_g1_production_aggregation_review.csv):
  review_status pending -> approved
  reviewed_by   NULL    -> 'gate1fh_g3_g1_aggregation_approval'
  reviewed_at   NULL    -> one transaction-level TIMESTAMPTZ

Strictly approval-only: record_status stays proposed; rollup flags stay FALSE.
Scientific payload (all columns except review_status/reviewed_by/reviewed_at)
is hashed before and after; the hashes must be identical.

Rerun safety: if all 246 rows are already approved with the correct reviewer,
this is a NOOP (updated_count=0, no timestamp overwrite). A partially-approved
batch fails closed.

Usage:
    python scripts/approve_g3_g1_aggregation_mappings.py [--plan]
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
AUDIT_JSON = DATA / "g3_to_g1_aggregation_approval_audit.json"

APPROVAL_PHASE = "G3_G1_AGGREGATION_APPROVAL_V1"
SOURCE_REVIEW_PHASE = "G3_G1_PRODUCTION_AGGREGATION_REVIEW_V1"
REVIEWER = "gate1fh_g3_g1_aggregation_approval"

# scientific payload columns (excluded: review lifecycle only)
SCIENTIFIC_COLS = [
    "mapping_id", "source_region_pk", "target_region_pk", "mapping_relation",
    "mapping_method", "source_granularity_level", "target_granularity_level",
    "source_coverage_ratio", "target_coverage_ratio", "spatial_overlap_ratio",
    "mapping_confidence", "rollup_eligible", "is_primary_rollup",
    "scientific_source_pk", "provenance_json", "record_status", "remark",
]


def _sha256(v: str) -> str:
    return hashlib.sha256(v.encode("utf-8")).hexdigest()


def _payload_hash(rows: list[tuple]) -> str:
    canon = []
    for r in rows:
        line = "|".join("" if v is None else str(v) for v in r)
        canon.append(line)
    return _sha256("\n".join(sorted(canon)))


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
    ts = datetime.now(timezone.utc)

    conn = psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=args.db, autocommit=False)
    cur = conn.cursor()

    # ---- preflight ----
    def q(sql, *a):
        cur.execute(sql, *a)
        return cur.fetchone()[0]

    rows = q("SELECT count(*) FROM brain_region_aggregation_mappings")
    proposed = q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE record_status='proposed'")
    pending = q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE review_status='pending'")
    approved = q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE review_status='approved'")
    active = q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE record_status='active'")
    rollup = q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE rollup_eligible=TRUE")
    primary = q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE is_primary_rollup=TRUE")
    rb_null = q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE reviewed_by IS NULL")
    ra_null = q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE reviewed_at IS NULL")

    # ---- rerun safety (before strict first-run preflight) ----
    if rows == 246 and approved == 246:
        # all already approved — check reviewer correctness; NOOP, do not overwrite timestamp
        cur.execute(f"SELECT count(*) FROM {TABLE} WHERE review_status='approved' AND reviewed_by=%s AND reviewed_at IS NOT NULL",
                    (REVIEWER,))
        correct = cur.fetchone()[0]
        if correct == 246:
            conn.rollback()
            print(f"RERUN NO-OP: all 246 already approved by {REVIEWER}; updated=0")
            # do NOT overwrite a committed approval audit; only write a noop audit if none exists
            if not AUDIT_JSON.exists() or AUDIT_JSON.stat().st_size == 0:
                _write_audit(cur, allowlist, ts, inserted=0, rows_after=246,
                             txn="NOOP_RERUN", payload_unchanged=True)
            else:
                _record_rerun(allowlist)
            conn.close()
            return 0
        # all approved but reviewer mismatch -> fail closed
        conn.rollback()
        print("FAIL CLOSED: 246 approved but reviewer mismatch; require human investigation")
        return 3
    if approved not in (0, 246):
        conn.rollback()
        print(f"FAIL CLOSED: partial approved state ({approved}/246); require human investigation")
        return 3

    # ---- strict first-run preflight (only reached when nothing approved yet) ----
    expected = {"rows": 246, "proposed": 246, "pending": 246, "approved": 0,
                "active": 0, "rollup": 0, "primary": 0, "rb_null": 246, "ra_null": 246}
    got = {"rows": rows, "proposed": proposed, "pending": pending, "approved": approved,
           "active": active, "rollup": rollup, "primary": primary, "rb_null": rb_null, "ra_null": ra_null}
    if got != expected:
        conn.rollback()
        print("FAIL CLOSED: preflight mismatch")
        for k in expected:
            if got[k] != expected[k]:
                print(f"  {k}: got {got[k]}, expected {expected[k]}")
        return 3

    # ---- scientific payload snapshot (before) ----
    cur.execute(f"SELECT {', '.join(SCIENTIFIC_COLS)} FROM {TABLE} ORDER BY mapping_id")
    payload_before = cur.fetchall()
    hash_before = _payload_hash(payload_before)

    # ---- allowlist-driven update in one transaction ----
    if args.plan:
        conn.rollback()
        print(f"[plan] would approve {len(allowlist)} rows with reviewer={REVIEWER}")
        conn.close()
        return 0

    cur.execute(f"""UPDATE {TABLE}
        SET review_status='approved', reviewed_by=%s, reviewed_at=%s
        WHERE mapping_id = ANY(%s)
          AND record_status='proposed'
          AND review_status='pending'
          AND reviewed_by IS NULL
          AND reviewed_at IS NULL""",
        (REVIEWER, ts, allowlist))
    updated = cur.rowcount
    if updated != 246:
        conn.rollback()
        print(f"FAIL CLOSED: updated {updated} != 246; rolled back")
        return 3

    # ---- verify before commit ----
    cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE review_status='approved'")
    if cur.fetchone()[0] != 246:
        conn.rollback()
        print("FAIL CLOSED: approved != 246 after update")
        return 3

    # ---- scientific payload snapshot (after) ----
    cur.execute(f"SELECT {', '.join(SCIENTIFIC_COLS)} FROM {TABLE} ORDER BY mapping_id")
    payload_after = cur.fetchall()
    hash_after = _payload_hash(payload_after)
    if hash_before != hash_after:
        conn.rollback()
        print("FAIL CLOSED: scientific payload changed during approval")
        return 3

    conn.commit()
    print(f"APPROVED {updated} rows (reviewer={REVIEWER})")

    # ---- post-commit audit ----
    cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings")
    rows_after = cur.fetchone()[0]
    _write_audit(cur, allowlist, ts, inserted=updated, rows_after=rows_after,
                 txn="COMMITTED", payload_unchanged=True)
    conn.close()
    return 0


def _record_rerun(allowlist: list[str]) -> None:
    """Record the fact that a NOOP rerun was observed without touching the committed audit."""
    with open(AUDIT_JSON, encoding="utf-8") as f:
        audit = json.load(f)
    audit.setdefault("rerun_observations", []).append({
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "updated_count": 0,
        "note": "RERUN NO-OP: all 246 already approved; committed audit preserved unchanged",
    })
    AUDIT_JSON.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_audit(cur, allowlist, ts, inserted, rows_after, txn, payload_unchanged):
    def q(sql, *a):
        cur.execute(sql, *a)
        return cur.fetchone()[0]

    contained = q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE mapping_relation='contained_in'")
    dominant = q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE mapping_relation='dominant_overlap'")
    partial = q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE mapping_relation='partial_overlap'")
    audit = {
        "approval_phase": APPROVAL_PHASE,
        "source_review_phase": SOURCE_REVIEW_PHASE,
        "reviewer_identifier": REVIEWER,
        "approval_timestamp": ts.isoformat(),
        "eligible_count": len(allowlist),
        "updated_count": inserted,
        "rows_before": 246, "rows_after": rows_after,
        "pending_before": 246, "pending_after": q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE review_status='pending'"),
        "approved_before": 0, "approved_after": q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE review_status='approved'"),
        "proposed_before": 246, "proposed_after": q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE record_status='proposed'"),
        "active_before": 0, "active_after": q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE record_status='active'"),
        "rollup_true_before": 0, "rollup_true_after": q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE rollup_eligible=TRUE"),
        "primary_true_before": 0, "primary_true_after": q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE is_primary_rollup=TRUE"),
        "contained_count": contained, "dominant_count": dominant, "partial_count": partial,
        "excluded_leak_count": 0,
        "scientific_payload_unchanged": payload_unchanged,
        "transaction_status": txn,
    }
    AUDIT_JSON.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
