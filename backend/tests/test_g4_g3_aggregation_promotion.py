"""Gate 7B Phase 2J-E — G4→G3 Aggregation Promotion + Rollup Activation QA.

Verifies the 461 G4→G3 rows are active+approved, exactly 20 contained carry
rollup/primary, dominant/partial never roll up, primary-parent uniqueness, and
G3→G1 stays intact. No promotion to Final-freeze (this gate only).
"""

from __future__ import annotations

import json
from pathlib import Path

import psycopg
import pytest

BACKEND = Path(__file__).resolve().parents[1]
PROD = "neurographiq_human_brain_v1"
MANIFEST = json.load(open(BACKEND / "data" / "integration" / "g4_g3_aggregation_promotion_manifest.json", encoding="utf-8"))
G4 = "G4_MICROSTRUCTURAL_FINE"


def _conn(db=PROD):
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=db, autocommit=True)


def test_prepromotion_was_461_proposed_approved():
    assert MANIFEST["prepromotion"]["total"] == 461
    assert MANIFEST["prepromotion"]["proposed"] == 461
    assert MANIFEST["prepromotion"]["active"] == 0
    assert MANIFEST["prepromotion"]["approved"] == 461
    assert MANIFEST["updated"] == 461


def test_active_461_proposed_0():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s AND record_status='active'", (G4,))
        assert cur.fetchone()[0] == 461
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s AND record_status='proposed'", (G4,))
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()


def test_approved_461_pending_0():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s AND review_status='approved'", (G4,))
        assert cur.fetchone()[0] == 461
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s AND review_status='pending'", (G4,))
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()


def test_relation_counts():
    conn = _conn()
    try:
        cur = conn.cursor()
        for rel, n in (("contained_in", 20), ("dominant_overlap", 110), ("partial_overlap", 331)):
            cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s AND mapping_relation=%s", (G4, rel))
            assert cur.fetchone()[0] == n
    finally:
        conn.close()


def test_rollup_primary_20_only():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s AND rollup_eligible=TRUE", (G4,))
        assert cur.fetchone()[0] == 20
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s AND is_primary_rollup=TRUE", (G4,))
        assert cur.fetchone()[0] == 20
        # rollup only on contained_in
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s AND mapping_relation='contained_in' AND rollup_eligible=TRUE AND is_primary_rollup=TRUE", (G4,))
        assert cur.fetchone()[0] == 20
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s AND mapping_relation='dominant_overlap' AND (rollup_eligible=TRUE OR is_primary_rollup=TRUE)", (G4,))
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s AND mapping_relation='partial_overlap' AND (rollup_eligible=TRUE OR is_primary_rollup=TRUE)", (G4,))
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()


def test_contained_semantic_gate_on_rollup():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""SELECT provenance_json->>'semantic_compatibility_status' FROM brain_region_aggregation_mappings
            WHERE source_granularity_level=%s AND mapping_relation='contained_in' AND rollup_eligible=TRUE""", (G4,))
        vals = [p for (p,) in cur.fetchall()]
        assert len(vals) == 20
        assert all(v in ("EXACT_FAMILY", "NESTED_COMPATIBLE_FAMILY") for v in vals)
    finally:
        conn.close()


def test_primary_source_unique_20():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""SELECT count(DISTINCT source_region_pk) FROM brain_region_aggregation_mappings
            WHERE source_granularity_level=%s AND record_status='active' AND review_status='approved'
              AND mapping_relation='contained_in' AND rollup_eligible=TRUE AND is_primary_rollup=TRUE""", (G4,))
        assert cur.fetchone()[0] == 20
        cur.execute("""SELECT count(*) FROM (
            SELECT source_region_pk FROM brain_region_aggregation_mappings
            WHERE source_granularity_level=%s AND record_status='active' AND review_status='approved'
              AND mapping_relation='contained_in' AND rollup_eligible=TRUE AND is_primary_rollup=TRUE
            GROUP BY source_region_pk HAVING count(*)>1) t""", (G4,))
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()


def test_partial_target_sets_unchanged():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT source_region_pk, count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s AND mapping_relation='partial_overlap' GROUP BY 1", (G4,))
        rows = cur.fetchall()
        assert len(rows) == 137
        assert all(c >= 2 for _, c in rows)
    finally:
        conn.close()


def test_unexpected_mutation_0():
    assert MANIFEST["unexpected_field_mutation_count"] == 0
    assert MANIFEST["scientific_hash_unchanged"] is True
    assert MANIFEST["review_metadata_unchanged"] is True


def test_exclusion_leak_0():
    assert MANIFEST["exclusion_leak"] == 0


def test_rerun_noop():
    assert MANIFEST["rerun_idempotent"] is True
    obs = MANIFEST.get("rerun_observations", [])
    assert len(obs) >= 1
    assert obs[-1].get("promoted", 0) == 0
    assert obs[-1].get("already_active", 0) == 461
    assert MANIFEST["updated"] == 461  # first-promotion numbers preserved


def test_g3_to_g1_unchanged():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G3_MESO_FINE'")
        total = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G3_MESO_FINE' AND record_status='active'")
        active = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G3_MESO_FINE' AND review_status='approved'")
        approved = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G3_MESO_FINE' AND rollup_eligible=TRUE")
        rollup = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G3_MESO_FINE' AND is_primary_rollup=TRUE")
        primary = cur.fetchone()[0]
    finally:
        conn.close()
    assert total == 246 and active == 246 and approved == 246 and rollup == 172 and primary == 172


def test_aggregation_total_707_whole_table():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings")
        assert cur.fetchone()[0] == 707
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE record_status='active'")
        assert cur.fetchone()[0] == 707
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE review_status='approved'")
        assert cur.fetchone()[0] == 707
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE rollup_eligible=TRUE")
        assert cur.fetchone()[0] == 192
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE is_primary_rollup=TRUE")
        assert cur.fetchone()[0] == 192
    finally:
        conn.close()


def test_no_reverse_duplicate_rows():
    # reverse lookup uses the same table; promotion must NOT create new rows
    assert MANIFEST["agg_table_total_after"] == 707


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
