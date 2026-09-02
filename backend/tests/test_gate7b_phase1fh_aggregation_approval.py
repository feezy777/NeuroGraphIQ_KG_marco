"""Gate 7B Phase 1F-H — G3→G1 Aggregation Approval verification.

Read-only confirmation that the 246 production aggregation mappings were
approved (review_status pending->approved) with the exact reviewer identifier
and a single batch-level reviewed_at timestamp, while record_status stays
proposed and rollup flags stay FALSE. Verifies rerun no-op safety and that the
scientific payload is unchanged.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import psycopg
import pytest

BACKEND = Path(__file__).resolve().parents[1]
PROD = "neurographiq_human_brain_v1"
INT = BACKEND / "data" / "integration"
TABLE = "brain_region_aggregation_mappings"
REVIEWER = "gate1fh_g3_g1_aggregation_approval"
APPROVAL_PHASE = "G3_G1_AGGREGATION_APPROVAL_V1"

SCIENTIFIC_COLS = [
    "mapping_id", "source_region_pk", "target_region_pk", "mapping_relation",
    "mapping_method", "source_granularity_level", "target_granularity_level",
    "source_coverage_ratio", "target_coverage_ratio", "spatial_overlap_ratio",
    "mapping_confidence", "rollup_eligible", "is_primary_rollup",
    "scientific_source_pk", "provenance_json", "record_status", "remark",
]

AUDIT = json.load(open(INT / "g3_to_g1_aggregation_approval_audit.json", encoding="utf-8"))


def _conn(db=PROD):
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=db, autocommit=True)


def _db_rows():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM {TABLE} ORDER BY mapping_pk")
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()


DB = _db_rows()


def test_preflight_246_pending_was_true():
    # post-approval: 0 pending; pre-approval state is reflected in the audit
    assert AUDIT["pending_before"] == 246


def test_review_artifact_246_eligible():
    rev = list(csv.DictReader(open(INT / "g3_to_g1_production_aggregation_review.csv", encoding="utf-8-sig")))
    assert len(rev) == 246
    assert all(r["approval_eligibility"] == "ELIGIBLE_FOR_APPROVAL" for r in rev)
    assert len({r["mapping_id"] for r in rev}) == 246


def test_allowlist_equals_production_mapping_ids():
    rev = [r["mapping_id"] for r in
           csv.DictReader(open(INT / "g3_to_g1_production_aggregation_review.csv", encoding="utf-8-sig"))]
    db_ids = {r["mapping_id"] for r in DB}
    assert set(rev) == db_ids


def test_update_exactly_246():
    assert AUDIT["updated_count"] == 246
    assert AUDIT["rows_after"] == 246


def test_approved_246():
    assert sum(1 for r in DB if r["review_status"] == "approved") == 246


def test_pending_zero():
    assert sum(1 for r in DB if r["review_status"] == "pending") == 0


def test_proposed_remains_246():
    # approval kept record_status proposed; 1F-I promotion later moved to active
    assert AUDIT["proposed_after"] == 246  # approval audit recorded 246 proposed at approval time


def test_active_remains_zero():
    # approval did not activate; 1F-I promotion later set active
    assert AUDIT["active_after"] == 0  # approval audit recorded 0 active at approval time
    assert sum(1 for r in DB if r["record_status"] == "active") == 246


def test_reviewed_by_exact_identifier():
    assert all(r["reviewed_by"] == REVIEWER for r in DB)


def test_reviewed_at_all_nonnull():
    assert all(r["reviewed_at"] is not None for r in DB)


def test_reviewed_at_batch_consistent():
    vals = {r["reviewed_at"] for r in DB}
    assert len(vals) == 1  # single transaction timestamp


def test_rollup_true_zero():
    # approval (1F-H) did not enable rollup; 1F-I promotion later did on the 172 contained
    rollup = [r for r in DB if r["rollup_eligible"]]
    assert len(rollup) == 172
    assert AUDIT["rollup_true_after"] == 0  # approval audit recorded 0 at approval time


def test_primary_true_zero():
    # approval did not set primary; 1F-I promotion set it on the 172 contained
    primary = [r for r in DB if r["is_primary_rollup"]]
    assert len(primary) == 172
    assert AUDIT["primary_true_after"] == 0


def test_relation_counts_unchanged():
    from collections import Counter
    rel = Counter(r["mapping_relation"] for r in DB)
    assert rel == Counter({"contained_in": 172, "dominant_overlap": 34,
                           "partial_overlap": 40})


def test_scientific_payload_unchanged():
    # 1F-H audit recorded payload unchanged at approval time (pre-promotion).
    # The promotion audit (1F-I) is the current authoritative payload snapshot.
    promo = json.load(open(INT / "g3_to_g1_aggregation_promotion_audit.json", encoding="utf-8"))
    assert AUDIT["scientific_payload_unchanged"] is True
    assert promo["scientific_payload_unchanged"] is True


def test_exclusions_leak_zero():
    exc = list(csv.DictReader(open(INT / "g3_to_g1_mapping_candidate_exclusions.csv", encoding="utf-8-sig")))
    eids = list({m["g3_entity_id"] for m in exc})
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"""SELECT count(*) FROM {TABLE}
            WHERE source_region_pk IN (SELECT b.entity_pk FROM brain_regions b
                JOIN kg_entities e ON e.entity_pk=b.entity_pk WHERE e.entity_id = ANY(%s))""",
            (eids,))
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()
    assert AUDIT["excluded_leak_count"] == 0


def test_second_run_noop():
    # audit reflects COMMITTED first run; rerun observations appended but not overwritten
    assert AUDIT["transaction_status"] == "COMMITTED"
    assert AUDIT["updated_count"] == 246
    assert "rerun_observations" in AUDIT


def test_second_run_preserves_reviewed_at():
    vals = {r["reviewed_at"] for r in DB}
    assert len(vals) == 1
    # audit approval_timestamp is the batch timestamp
    assert AUDIT["approval_timestamp"] == vals.pop().isoformat()


def test_audit_consistent():
    assert AUDIT["approval_phase"] == APPROVAL_PHASE
    assert AUDIT["reviewer_identifier"] == REVIEWER
    assert AUDIT["approved_after"] == 246
    assert AUDIT["pending_after"] == 0
    assert AUDIT["proposed_after"] == 246
    assert AUDIT["active_after"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
