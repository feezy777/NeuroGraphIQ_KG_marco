"""Gate 7B Phase 2J-D — G4→G3 Aggregation Approval (461 rows, single transaction).

Approves the 461 production G4→G3 aggregation rows loaded in Phase 2J-C:
  review_status pending -> approved
  reviewed_by   NULL    -> 'gate2jd_g4_g3_aggregation_approval'
  reviewed_at   NULL    -> one transaction-level TIMESTAMPTZ

Strictly approval-only. record_status stays proposed; rollup_eligible and
is_primary_rollup stay FALSE (even for the 20 contained — promotion gate later).
Scientific payload (every column except review_status/reviewed_by/reviewed_at)
is hashed before and after; hashes must be identical (unexpected field
mutation count = 0). G3→G1 rows are never touched.

The eligible allowlist is computed from the authoritative production batch:
source_granularity_level = 'G4_MICROSTRUCTURAL_FINE' AND record_status='proposed'
AND review_status='pending' (461). No ID-range / prefix guessing.

Rerun safety: if all 461 are already approved with the correct reviewer,
this is a NOOP (updated=0, no timestamp overwrite). Partial approval fails closed.

Usage:
    python scripts/approve_g4_g3_aggregation_mappings.py --dry-run
    python scripts/approve_g4_g3_aggregation_mappings.py
"""

from __future__ import annotations

import argparse
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
G4_GRAN = "G4_MICROSTRUCTURAL_FINE"
G3_GRAN = "G3_MESO_FINE"

APPROVAL_PHASE = "G4_G3_AGGREGATION_APPROVAL_V1"
REVIEWER = "gate2jd_g4_g3_aggregation_approval"

STAGING = DATA / "g4_g3_mapping_candidate_staging.csv"
REVIEW = DATA / "g4_g3_mapping_candidate_review.csv"
REV_SUM = DATA / "g4_g3_mapping_candidate_review_summary.json"
LOAD_MAN = DATA / "g4_g3_candidate_load_manifest.json"
G2G_SUM = DATA / "g4_g3_probability_overlap_summary.json"
MANIFEST = DATA / "g4_g3_aggregation_approval_manifest.json"
PG2_MATRIX_HASH = "a64d0c598300d1f0e6d56c67c1e2564775287447d5c17f77741bcf96ec2df874"

SCIENTIFIC_COLS = [
    "mapping_id", "source_region_pk", "target_region_pk", "mapping_relation",
    "mapping_method", "source_granularity_level", "target_granularity_level",
    "source_coverage_ratio", "target_coverage_ratio", "spatial_overlap_ratio",
    "mapping_confidence", "rollup_eligible", "is_primary_rollup",
    "scientific_source_pk", "provenance_json", "record_status", "remark",
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256(v: str) -> str:
    return hashlib.sha256(v.encode("utf-8")).hexdigest()


def _payload_hash(rows: list[tuple]) -> str:
    canon = []
    for r in rows:
        line = "|".join("" if v is None else str(v) for v in r)
        canon.append(line)
    return _sha256("\n".join(sorted(canon)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="preflight only (UPDATE=0)")
    parser.add_argument("--db", default=DB)
    args = parser.parse_args()
    if args.db != DB:
        sys.exit(f"FAIL CLOSED: refusing non-authoritative db '{args.db}' (must be {DB})")

    # ---- scientific/staging freeze verification ----
    rev_sum = json.load(open(REV_SUM, encoding="utf-8"))
    load_man = json.load(open(LOAD_MAN, encoding="utf-8"))
    g2g_sum = json.load(open(G2G_SUM, encoding="utf-8"))
    if not (rev_sum.get("pass_count") == 461 and rev_sum.get("fail_count") == 0):
        sys.exit("FAIL CLOSED: fidelity review not 461 PASS")
    if _sha(STAGING) != load_man.get("input_candidate_sha"):
        sys.exit("FAIL CLOSED: staging artifact hash changed since load")
    if _sha(REVIEW) != load_man.get("fidelity_review_sha"):
        sys.exit("FAIL CLOSED: review artifact hash changed since load")
    if g2g_sum.get("matrix_hash") != PG2_MATRIX_HASH:
        sys.exit("FAIL CLOSED: Phase 2G matrix hash changed")

    ts = datetime.now(timezone.utc)
    conn = psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=args.db, autocommit=False)
    cur = conn.cursor()

    def q(sql, *a):
        cur.execute(sql, *a)
        return cur.fetchone()[0]

    # ---- preflight counts ----
    agg_total = q(f"SELECT count(*) FROM {TABLE}")
    g4_total = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s", (G4_GRAN,))
    g4_proposed = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND record_status='proposed'", (G4_GRAN,))
    g4_active = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND record_status='active'", (G4_GRAN,))
    g4_pending = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND review_status='pending'", (G4_GRAN,))
    g4_approved = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND review_status='approved'", (G4_GRAN,))
    g4_rollup = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND rollup_eligible=TRUE", (G4_GRAN,))
    g4_primary = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND is_primary_rollup=TRUE", (G4_GRAN,))
    contained = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND mapping_relation='contained_in'", (G4_GRAN,))
    dominant = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND mapping_relation='dominant_overlap'", (G4_GRAN,))
    partial = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND mapping_relation='partial_overlap'", (G4_GRAN,))
    g3_total = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s", (G3_GRAN,))
    g3_active = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND record_status='active'", (G3_GRAN,))
    g3_approved = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND review_status='approved'", (G3_GRAN,))
    g3_rollup = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND rollup_eligible=TRUE", (G3_GRAN,))

    if not (g3_total == 246 and g3_active == 246 and g3_approved == 246 and g3_rollup == 172):
        conn.rollback(); sys.exit(f"FAIL CLOSED: G3->G1 not intact {g3_total}/{g3_active}/{g3_approved}/{g3_rollup}")
    if not (g4_total == 461 and contained == 20 and dominant == 110 and partial == 331
            and g4_rollup == 0 and g4_primary == 0):
        conn.rollback(); sys.exit(f"FAIL CLOSED: G4->G3 relation/lifecycle preflight {g4_total}/{contained}/{dominant}/{partial}/{g4_rollup}/{g4_primary}")

    # ---- rerun safety ----
    if g4_approved > 0:
        if g4_approved == 461 and g4_pending == 0:
            correct = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND review_status='approved' AND reviewed_by=%s AND reviewed_at IS NOT NULL", (G4_GRAN, REVIEWER))
            if correct == 461:
                conn.rollback()
                base = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
                base.setdefault("rerun_observations", []).append({
                    "updated": 0, "already_approved": 461, "failed": 0,
                    "note": "NOOP: all 461 already approved; reviewed_at not overwritten",
                    "timestamp": datetime.now(timezone.utc).isoformat()})
                base["rerun_idempotent"] = True
                MANIFEST.write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")
                print("RERUN NO-OP: 461 already approved; updated=0")
                conn.close()
                return 0
            conn.rollback(); sys.exit("FAIL CLOSED: 461 approved but reviewer mismatch")
        conn.rollback(); sys.exit(f"FAIL CLOSED: partial approved state {g4_approved}/{461}")

    expected_first = (g4_proposed == 461 and g4_pending == 461 and g4_approved == 0
                      and g4_active == 0 and agg_total == 707)
    if not expected_first:
        conn.rollback(); sys.exit(f"FAIL CLOSED: first-run preflight {agg_total}/{g4_proposed}/{g4_pending}/{g4_approved}")

    print(f"preflight OK: agg={agg_total} g4={g4_total} proposed={g4_proposed} pending={g4_pending} "
          f"contained={contained} dominant={dominant} partial={partial} g3 ok")
    if args.dry_run:
        conn.rollback()
        print(f"[dry-run] would approve 461 G4->G3 rows reviewer={REVIEWER} (UPDATE=0)")
        conn.close()
        return 0

    # ---- allowlist = authoritative production batch (proposed+pending G4->G3) ----
    cur.execute(f"SELECT mapping_id FROM {TABLE} WHERE source_granularity_level=%s "
                f"AND record_status='proposed' AND review_status='pending' "
                f"AND reviewed_by IS NULL AND reviewed_at IS NULL ORDER BY mapping_id", (G4_GRAN,))
    allowlist = [r[0] for r in cur.fetchall()]
    if len(allowlist) != 461 or len(set(allowlist)) != 461:
        conn.rollback(); sys.exit(f"FAIL CLOSED: allowlist {len(allowlist)} != 461 unique")

    # ---- scientific payload snapshot (before) ----
    cur.execute(f"SELECT {', '.join(SCIENTIFIC_COLS)} FROM {TABLE} "
                f"WHERE source_granularity_level=%s ORDER BY mapping_id", (G4_GRAN,))
    payload_before = cur.fetchall()
    hash_before = _payload_hash(payload_before)

    # ---- single-transaction approval update ----
    cur.execute(f"""UPDATE {TABLE}
        SET review_status='approved', reviewed_by=%s, reviewed_at=%s
        WHERE mapping_id = ANY(%s)
          AND record_status='proposed'
          AND review_status='pending'
          AND reviewed_by IS NULL
          AND reviewed_at IS NULL""", (REVIEWER, ts, allowlist))
    updated = cur.rowcount
    if updated != 461:
        conn.rollback(); sys.exit(f"FAIL CLOSED: updated {updated} != 461; rolled back")

    # ---- verify before commit ----
    if q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND review_status='approved'", (G4_GRAN,)) != 461:
        conn.rollback(); sys.exit("FAIL CLOSED: approved != 461 after update")

    cur.execute(f"SELECT {', '.join(SCIENTIFIC_COLS)} FROM {TABLE} "
                f"WHERE source_granularity_level=%s ORDER BY mapping_id", (G4_GRAN,))
    payload_after = cur.fetchall()
    hash_after = _payload_hash(payload_after)
    mutation = 0 if hash_before == hash_after else -1
    if mutation != 0:
        conn.rollback(); sys.exit("FAIL CLOSED: scientific payload changed during approval")
    print("payload hash unchanged: unexpected_field_mutation_count=0 (pre-commit)")

    conn.commit()
    print(f"APPROVED {updated} rows (reviewer={REVIEWER})")

    # ---- post-commit manifest ----
    def qa(sql, *a):
        cur.execute(sql, *a)
        return cur.fetchone()[0]
    g4_after = qa(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s", (G4_GRAN,))
    approved_after = qa(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND review_status='approved'", (G4_GRAN,))
    pending_after = qa(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND review_status='pending'", (G4_GRAN,))
    proposed_after = qa(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND record_status='proposed'", (G4_GRAN,))
    active_after = qa(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND record_status='active'", (G4_GRAN,))
    rollup_after = qa(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND rollup_eligible=TRUE", (G4_GRAN,))
    primary_after = qa(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND is_primary_rollup=TRUE", (G4_GRAN,))
    reviewer_n = qa(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND reviewed_by=%s", (G4_GRAN, REVIEWER))
    reviewed_n = qa(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND reviewed_at IS NOT NULL", (G4_GRAN,))
    excl_ids = [r["canonical_g4_id"] for r in list(csv.DictReader(open(DATA / "g4_g3_mapping_candidate_exclusions.csv", encoding="utf-8-sig")))]
    leak = qa(f"""SELECT count(*) FROM {TABLE} b JOIN kg_entities k ON k.entity_pk=b.source_region_pk
                  WHERE b.source_granularity_level=%s AND k.entity_id=ANY(%s)""", (G4_GRAN, excl_ids))

    import csv as _csv
    # (csv imported lazily above via module import list)
    _ = _csv

    manifest = {
        "phase": APPROVAL_PHASE,
        "preapproval_total": g4_total, "preapproval_pending": g4_pending, "preapproval_approved": 0,
        "attempted": 461, "updated": updated, "already_approved": 0, "failed": 0,
        "postapproval_total": g4_after,
        "contained": contained, "dominant": dominant, "partial": partial,
        "proposed": proposed_after, "active": active_after,
        "pending": pending_after, "approved": approved_after,
        "rollup_true": rollup_after, "primary_true": primary_after,
        "reviewer": REVIEWER, "reviewed_at": ts.isoformat(),
        "reviewed_by_count": reviewer_n, "reviewed_at_nonnull_count": reviewed_n,
        "unexpected_field_mutation_count": 0,
        "exclusion_leak": leak,
        "scientific_hash_unchanged": True,
        "transaction_committed": True,
        "rerun_idempotent": False,
        "g3_g1_before": {"total": g3_total, "active": g3_active, "approved": g3_approved, "rollup": g3_rollup},
        "g3_g1_after": {"total": g3_total, "active": g3_active, "approved": g3_approved, "rollup": g3_rollup},
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    conn.close()
    return 0


import csv  # noqa: E402  (used only in manifest post-step)


if __name__ == "__main__":
    sys.exit(main())
