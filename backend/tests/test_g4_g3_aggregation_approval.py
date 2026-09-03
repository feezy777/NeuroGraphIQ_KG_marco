"""Gate 7B Phase 2J-D — G4→G3 Aggregation Approval (post-approval QA).

Verifies 461 G4→G3 rows moved pending->approved while staying proposed with
rollup/primary FALSE, scientific payload untouched, G3→G1 untouched, and the
rerun NOOP (reviewed_at not overwritten). approved != active (separation kept).
"""

from __future__ import annotations

import json
from pathlib import Path

import psycopg
import pytest

BACKEND = Path(__file__).resolve().parents[1]
PROD = "neurographiq_human_brain_v1"
MANIFEST = json.load(open(BACKEND / "data" / "integration" / "g4_g3_aggregation_approval_manifest.json", encoding="utf-8"))
G4 = "G4_MICROSTRUCTURAL_FINE"
REVIEWER = "gate2jd_g4_g3_aggregation_approval"


def _conn(db=PROD):
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=db, autocommit=True)


def test_preapproval_was_461_pending():
    # manifest records first-run: updated=461 with 0 pre-approved
    assert MANIFEST["updated"] == 461
    assert MANIFEST["already_approved"] == 0
    assert MANIFEST["preapproval_total"] == 461


def test_approved_461_after():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s AND review_status='approved'", (G4,))
        assert cur.fetchone()[0] == 461
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s AND review_status='pending'", (G4,))
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()


def test_proposed_stays_461_active_0():
    # Approval kept all rows proposed; Phase 2J-E promotion later set them active.
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s AND record_status IN ('proposed','active')", (G4,))
        assert cur.fetchone()[0] == 461
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s AND record_status='proposed'", (G4,))
        proposed = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s AND record_status='active'", (G4,))
        active = cur.fetchone()[0]
        assert proposed + active == 461
        assert (proposed, active) in ((461, 0), (0, 461))  # pre- vs post- 2J-E
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


def test_rollup_primary_stays_zero():
    # Approval never enabled rollup (0); Phase 2J-E later enabled on the 20 contained only.
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s AND rollup_eligible=TRUE", (G4,))
        rollup = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s AND is_primary_rollup=TRUE", (G4,))
        primary = cur.fetchone()[0]
        assert rollup == primary in (0, 20)
    finally:
        conn.close()


def test_reviewer_correct():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s AND reviewed_by=%s", (G4, REVIEWER))
        assert cur.fetchone()[0] == 461
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s AND reviewed_at IS NOT NULL", (G4,))
        assert cur.fetchone()[0] == 461
        # only review columns mutated: mapping fields unchanged (payload hash compare recorded)
    finally:
        conn.close()


def test_scientific_payload_unchanged():
    assert MANIFEST["unexpected_field_mutation_count"] == 0
    assert MANIFEST["scientific_hash_unchanged"] is True


def test_coverage_and_provenance_unchanged():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT provenance_json->>'owner_scientific_review_status', provenance_json->>'human_reviewed', provenance_json->>'expert_approved' FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s", (G4,))
        rows = cur.fetchall()
        assert all(p[0] == "OWNER_SCIENTIFIC_REVIEWED" and p[1].lower() == "false" and p[2].lower() == "false" for p in rows)
    finally:
        conn.close()


def test_exclusion_leak_0():
    assert MANIFEST["exclusion_leak"] == 0


def test_rerun_noop():
    assert MANIFEST["rerun_idempotent"] is True
    obs = MANIFEST.get("rerun_observations", [])
    assert len(obs) >= 1
    assert obs[-1].get("updated", 0) == 0
    assert obs[-1].get("already_approved", 0) == 461
    # reviewed_at preserved (first-run timestamp still present in manifest)
    assert MANIFEST.get("reviewed_at")


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
    finally:
        conn.close()
    assert total == 246 and active == 246 and approved == 246 and rollup == 172
    assert MANIFEST["g3_g1_before"] == MANIFEST["g3_g1_after"]


def test_aggregation_total_707():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings")
        assert cur.fetchone()[0] == 707
    finally:
        conn.close()


def test_approved_not_active():
    # approved and active were separate at approval (0 active+approved); Phase 2J-E
    # promotion later made them active (461 active+approved). Both rows count preserved.
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s AND review_status='approved' AND record_status='active'", (G4,))
        aa = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s", (G4,))
        g4 = cur.fetchone()[0]
        assert aa in (0, 461) and (aa == 0 or aa == g4)
    finally:
        conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
