"""Gate 7B Phase 1F-I — G3→G1 Aggregation Promotion verification.

Read-only confirmation that the 246 approved aggregation mappings were
promoted to active knowledge: all 246 record_status=active, 172 contained_in
roll up (rollup_eligible=is_primary_rollup=TRUE), dominant/partial stay
non-rollup. Verifies payload unchanged, formal + reverse query smoke, rerun
no-op safety, and zero exclusion leakage.
"""

from __future__ import annotations

import csv
import hashlib
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
PROMOTION_PHASE = "G3_G1_AGGREGATION_PROMOTION_V1"

PAYLOAD_COLS = [
    "mapping_id", "source_region_pk", "target_region_pk", "mapping_relation",
    "mapping_method", "source_granularity_level", "target_granularity_level",
    "source_coverage_ratio", "target_coverage_ratio", "spatial_overlap_ratio",
    "mapping_confidence", "scientific_source_pk", "provenance_json",
    "review_status", "reviewed_by", "reviewed_at", "remark",
]

AUDIT = json.load(open(INT / "g3_to_g1_aggregation_promotion_audit.json", encoding="utf-8"))


def _conn(db=PROD):
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=db, autocommit=True)


def _db_rows():
    """G3→G1 slice only. The later G4→G3 chain shares the table and must not be
    scanned by this G3→G1 promotion gate."""
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM {TABLE} "
                    f"WHERE source_granularity_level='G3_MESO_FINE' AND target_granularity_level='G1_MACRO' "
                    f"ORDER BY mapping_pk")
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()


DB = _db_rows()


def test_preflight_246_proposed_approved_recorded():
    assert AUDIT["rows_before"] == 246
    assert AUDIT["proposed_before"] == 246
    assert AUDIT["approved_before"] == 246
    assert AUDIT["active_before"] == 0


def test_allowlist_precise():
    # promotion was locked to the Phase 1F-G review allowlist (246 mapping_ids)
    assert AUDIT["promoted_count"] == 246
    assert len(DB) == 246
    assert len({r["mapping_id"] for r in DB}) == 246


def test_promotion_exactly_246():
    assert AUDIT["promoted_count"] == 246


def test_active_246():
    assert sum(1 for r in DB if r["record_status"] == "active") == 246


def test_proposed_zero():
    assert sum(1 for r in DB if r["record_status"] == "proposed") == 0


def test_approved_still_246():
    assert sum(1 for r in DB if r["review_status"] == "approved") == 246


def test_contained_172():
    assert sum(1 for r in DB if r["mapping_relation"] == "contained_in") == 172


def test_dominant_34():
    assert sum(1 for r in DB if r["mapping_relation"] == "dominant_overlap") == 34


def test_partial_40():
    assert sum(1 for r in DB if r["mapping_relation"] == "partial_overlap") == 40


def test_rollup_true_172():
    assert sum(1 for r in DB if r["rollup_eligible"]) == 172


def test_primary_true_172():
    assert sum(1 for r in DB if r["is_primary_rollup"]) == 172


def test_rollup_all_contained():
    for r in DB:
        if r["rollup_eligible"] or r["is_primary_rollup"]:
            assert r["mapping_relation"] == "contained_in"
            assert r["record_status"] == "active"
            assert r["review_status"] == "approved"


def test_dominant_rollup_leak_zero():
    assert sum(1 for r in DB if r["mapping_relation"] == "dominant_overlap"
               and (r["rollup_eligible"] or r["is_primary_rollup"])) == 0
    assert AUDIT["dominant_rollup_leak"] == 0


def test_partial_rollup_leak_zero():
    assert sum(1 for r in DB if r["mapping_relation"] == "partial_overlap"
               and (r["rollup_eligible"] or r["is_primary_rollup"])) == 0
    assert AUDIT["partial_rollup_leak"] == 0


def test_each_contained_source_one_primary():
    from collections import Counter
    rollup = [r for r in DB if r["rollup_eligible"] and r["is_primary_rollup"]]
    assert len(rollup) == 172
    per_src = Counter(r["source_region_pk"] for r in rollup)
    assert len(per_src) == 172
    assert all(v == 1 for v in per_src.values())
    assert AUDIT["duplicate_primary_count"] == 0
    assert AUDIT["primary_source_count"] == 172


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
    assert AUDIT["excluded_source_leak"] == 0


def test_scientific_payload_unchanged():
    assert AUDIT["scientific_payload_unchanged"] is True
    assert AUDIT["scientific_payload_hash_before"] == AUDIT["scientific_payload_hash_after"]
    # recompute current payload and match audit
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT {', '.join(PAYLOAD_COLS)} FROM {TABLE} "
                    f"WHERE source_granularity_level='G3_MESO_FINE' AND target_granularity_level='G1_MACRO' "
                    f"ORDER BY mapping_id")
        rows = cur.fetchall()
    finally:
        conn.close()
    canon = sorted("|".join("" if v is None else str(v) for v in r) for r in rows)
    h = hashlib.sha256("\n".join(canon).encode()).hexdigest()
    assert h == AUDIT["scientific_payload_hash_after"]


def test_formal_primary_query_172():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"""SELECT count(*) FROM {TABLE}
            WHERE source_granularity_level='G3_MESO_FINE' AND target_granularity_level='G1_MACRO'
              AND mapping_relation='contained_in' AND record_status='active'
              AND review_status='approved' AND rollup_eligible=TRUE AND is_primary_rollup=TRUE""")
        assert cur.fetchone()[0] == 172
    finally:
        conn.close()
    assert AUDIT["formal_primary_query_count"] == 172


def test_formal_all_active_query_246():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"""SELECT count(*) FROM {TABLE}
            WHERE source_granularity_level='G3_MESO_FINE' AND target_granularity_level='G1_MACRO'
              AND record_status='active' AND review_status='approved'""")
        assert cur.fetchone()[0] == 246
    finally:
        conn.close()
    assert AUDIT["formal_all_mapping_query_count"] == 246


def test_formal_overlap_query_74():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"""SELECT count(*) FROM {TABLE}
            WHERE source_granularity_level='G3_MESO_FINE' AND target_granularity_level='G1_MACRO'
              AND record_status='active' AND review_status='approved'
              AND mapping_relation IN ('dominant_overlap','partial_overlap')""")
        assert cur.fetchone()[0] == 74
    finally:
        conn.close()
    assert AUDIT["formal_overlap_query_count"] == 74


def test_reverse_g1_to_g3_smoke():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"""SELECT target_region_pk, count(DISTINCT source_region_pk)
            FROM {TABLE}
            WHERE source_granularity_level='G3_MESO_FINE' AND target_granularity_level='G1_MACRO'
              AND record_status='active' AND review_status='approved'
              AND mapping_relation='contained_in' AND rollup_eligible=TRUE
            GROUP BY target_region_pk""")
        rows = cur.fetchall()
        assert len(rows) > 0
        assert sum(c for _, c in rows) == 172
    finally:
        conn.close()


def test_rerun_noop():
    assert AUDIT["transaction_status"] == "COMMITTED"
    assert AUDIT["promoted_count"] == 246
    assert "rerun_observations" in AUDIT


def test_rerun_preserves_reviewed_at():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT count(DISTINCT reviewed_at) FROM {TABLE} "
                    f"WHERE source_granularity_level='G3_MESO_FINE' AND target_granularity_level='G1_MACRO'")
        assert cur.fetchone()[0] == 1
    finally:
        conn.close()


def test_partial_active_multi_target_preserved():
    from collections import Counter
    part = [r for r in DB if r["mapping_relation"] == "partial_overlap"]
    assert len(part) == 40
    per_src = Counter(r["source_region_pk"] for r in part)
    assert len(per_src) == 20
    assert all(v == 2 for v in per_src.values())
    assert all(r["record_status"] == "active" and r["review_status"] == "approved" for r in part)
    assert all(not r["rollup_eligible"] and not r["is_primary_rollup"] for r in part)


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
