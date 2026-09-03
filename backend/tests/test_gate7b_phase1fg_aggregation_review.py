"""Gate 7B Phase 1F-G — Production G3→G1 Aggregation Review (eligibility audit).

Read-only audit of the 246 production aggregation mappings: each row must be
linked to a PASS staging review, match the frozen scientific decision, and be
ELIGIBLE_FOR_APPROVAL. No production writes, no approval transition.
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
LOAD_PHASE = "G3_G1_AGGREGATION_CANDIDATE_LOAD_V1"
REVIEW_PHASE = "G3_G1_PRODUCTION_AGGREGATION_REVIEW_V1"


def _rows(name):
    return list(csv.DictReader(open(INT / name, encoding="utf-8-sig")))


STAGING = _rows("g3_to_g1_mapping_candidate_staging.csv")
REVIEW = _rows("g3_to_g1_mapping_candidate_review.csv")
EXCL = _rows("g3_to_g1_mapping_candidate_exclusions.csv")
PROD_REV = _rows("g3_to_g1_production_aggregation_review.csv")
SUMMARY = json.load(open(INT / "g3_to_g1_production_aggregation_review_summary.json", encoding="utf-8"))
AUDIT = json.load(open(INT / "g3_to_g1_aggregation_candidate_load_audit.json", encoding="utf-8"))
FREEZE = _rows("g3_to_g1_final_scientific_decisions.csv")


def _conn(db=PROD):
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=db, autocommit=True)


def _db_rows():
    """G3→G1 slice only. The frozen table also carries the later G4→G3 chain;
    all G3→G1 gate scans are scoped by canonical granularity."""
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
stage_by_id = {c["candidate_id"]: c for c in STAGING}


# ---------------------------------------------------------------------------
# 1-3. production counts
# ---------------------------------------------------------------------------

def test_production_246():
    assert len(DB) == 246


def test_all_proposed():
    # review ran against the proposed batch; 1F-I promoted to active
    assert all(r["record_status"] == "active" for r in DB)


def test_all_pending():
    # the review eligibility audit ran against the pending batch; 1F-H later
    # approved it, so current rows are approved. The review summary records
    # the pre-approval eligibility (246 eligible, 0 lifecycle failures).
    assert SUMMARY["production_row_count"] == 246
    assert SUMMARY["lifecycle_failure_count"] == 0
    assert all(r["review_status"] == "approved" for r in DB)  # post-1F-H


# ---------------------------------------------------------------------------
# 4. staging candidate linkage 246/246
# ---------------------------------------------------------------------------

def test_staging_linkage_246():
    for r in DB:
        cid = r["provenance_json"]["staging_candidate_id"]
        assert cid in stage_by_id
        assert r["provenance_json"]["load_phase"] == LOAD_PHASE
    assert SUMMARY["linkage_mismatch_count"] == 0


# ---------------------------------------------------------------------------
# 5-7. relation fidelity
# ---------------------------------------------------------------------------

def test_contained_fidelity():
    cont = [r for r in DB if r["mapping_relation"] == "contained_in"]
    assert len(cont) == 172
    for r in cont:
        cid = r["provenance_json"]["staging_candidate_id"]
        st = stage_by_id[cid]
        assert st["mapping_relation"] == "contained_in"
        assert st["scientific_rollup_eligible"] == "TRUE"
        # 1F-I enabled rollup on the contained batch; staging scientific eligibility held
        assert r["rollup_eligible"] is True and r["is_primary_rollup"] is True


def test_dominant_fidelity():
    dom = [r for r in DB if r["mapping_relation"] == "dominant_overlap"]
    assert len(dom) == 34
    for r in dom:
        st = stage_by_id[r["provenance_json"]["staging_candidate_id"]]
        assert st["mapping_relation"] == "dominant_overlap"
        assert r["rollup_eligible"] is False and r["is_primary_rollup"] is False


def test_partial_20x2():
    from collections import Counter
    part = [r for r in DB if r["mapping_relation"] == "partial_overlap"]
    assert len(part) == 40
    per_src = Counter(r["source_region_pk"] for r in part)
    assert len(per_src) == 20
    assert all(v == 2 for v in per_src.values())


# ---------------------------------------------------------------------------
# 8. exclusion leakage
# ---------------------------------------------------------------------------

def test_exclusion_leakage_zero():
    exc_eids = {m["g3_entity_id"] for m in EXCL}
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"""SELECT count(*) FROM {TABLE}
            WHERE source_region_pk IN (SELECT b.entity_pk FROM brain_regions b
                JOIN kg_entities e ON e.entity_pk=b.entity_pk WHERE e.entity_id = ANY(%s))""",
            (list(exc_eids),))
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()
    assert SUMMARY["excluded_leak_count"] == 0


# ---------------------------------------------------------------------------
# 9-13. provenance / identity / hemisphere / coverage / lifecycle
# ---------------------------------------------------------------------------

def test_provenance_complete():
    for r in DB:
        p = r["provenance_json"]
        assert p.get("staging_candidate_id")
        assert p.get("load_phase") == LOAD_PHASE
        assert p.get("decision_phase")
        assert p.get("decision_origin")
        assert p.get("effective_scientific_decision")
        assert p.get("source_frozen_artifact")
        assert p.get("human_reviewed") is False
        assert p.get("expert_approved") is False
    assert SUMMARY["provenance_failure_count"] == 0


def test_identity_granularity():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"""SELECT count(*) FROM {TABLE} b
            JOIN brain_regions s ON s.entity_pk=b.source_region_pk
            JOIN brain_regions t ON t.entity_pk=b.target_region_pk
            WHERE b.source_granularity_level='G3_MESO_FINE' AND b.target_granularity_level='G1_MACRO'
              AND (s.granularity_level<>'G3_MESO_FINE' OR t.granularity_level<>'G1_MACRO')""")
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()
    assert SUMMARY["identity_failure_count"] == 0


def test_hemisphere_zero():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"""SELECT count(*) FROM {TABLE} b
            JOIN brain_regions s ON s.entity_pk=b.source_region_pk
            JOIN brain_regions t ON t.entity_pk=b.target_region_pk
            WHERE b.source_granularity_level='G3_MESO_FINE' AND b.target_granularity_level='G1_MACRO'
              AND s.hemisphere<>t.hemisphere""")
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()
    assert SUMMARY["hemisphere_failure_count"] == 0


def test_coverage_fidelity():
    for r in DB:
        assert r["mapping_confidence"] is None
        if r["source_coverage_ratio"] is not None:
            assert r["source_coverage_ratio"] > 0
    assert SUMMARY["coverage_failure_count"] == 0


def test_lifecycle_correct():
    # review eligibility ran on the proposed+pending batch (0 lifecycle failures);
    # 1F-H approved and 1F-I promoted. record_status now active, review approved,
    # rollup only on contained. The audit recorded the pre-promotion review result.
    for r in DB:
        assert r["record_status"] == "active"
        assert r["review_status"] == "approved"
        assert r["reviewed_by"] == "gate1fh_g3_g1_aggregation_approval"
        assert r["reviewed_at"] is not None
    assert SUMMARY["lifecycle_failure_count"] == 0


# ---------------------------------------------------------------------------
# 14. approval eligibility = 246
# ---------------------------------------------------------------------------

def test_all_eligible_for_approval():
    assert len(PROD_REV) == 246
    assert all(r["approval_eligibility"] == "ELIGIBLE_FOR_APPROVAL" for r in PROD_REV)
    assert all(r["approval_block_reason"] == "" for r in PROD_REV)
    assert SUMMARY["eligible_count"] == 246
    assert SUMMARY["not_eligible_count"] == 0
    assert SUMMARY["contained_eligible_count"] == 172
    assert SUMMARY["dominant_eligible_count"] == 34
    assert SUMMARY["partial_eligible_count"] == 40


def test_review_phase_correct():
    assert SUMMARY["review_phase"] == REVIEW_PHASE


# ---------------------------------------------------------------------------
# 15. no production mutation
# ---------------------------------------------------------------------------

def test_no_production_mutation():
    # the review phase itself wrote nothing; 1F-H approval + 1F-I promotion
    # advanced lifecycle only. record_status now active, rollup on contained only.
    assert SUMMARY["excluded_leak_count"] == 0
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level='G3_MESO_FINE' AND target_granularity_level='G1_MACRO' AND review_status='approved'")
        assert cur.fetchone()[0] == 246
        cur.execute(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level='G3_MESO_FINE' AND target_granularity_level='G1_MACRO' AND record_status='active'")
        assert cur.fetchone()[0] == 246
        cur.execute(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level='G3_MESO_FINE' AND target_granularity_level='G1_MACRO' AND (rollup_eligible=TRUE OR is_primary_rollup=TRUE)")
        assert cur.fetchone()[0] == 172
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 16. sequence gap accepted + mapping IDs unchanged
# ---------------------------------------------------------------------------

def test_sequence_gap_accepted():
    assert SUMMARY["sequence_gap_status"] == "SEQUENCE_GAP_ACCEPTED"
    ids = [r["mapping_id"] for r in DB]
    assert len(ids) == len(set(ids)) == 246
    assert all(re.fullmatch(r"NGIQ-BRAM-\d{8}", i) for i in ids)
    assert all(r["mapping_id"] for r in DB)
    # gap is inherent to the official nextval allocator; IDs must not have been renumbered
    assert AUDIT["mapping_id_min"] == "NGIQ-BRAM-00000248"
    assert AUDIT["mapping_id_max"] == "NGIQ-BRAM-00000493"


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
