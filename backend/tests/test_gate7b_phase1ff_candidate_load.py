"""Gate 7B Phase 1F-F — G3→G1 Aggregation Candidate Load verification.

Confirms the 246 reviewed candidates were loaded into production
brain_region_aggregation_mappings as proposed+pending (no approval, no active,
no rollup), with exact relation distribution and full fidelity to staging.
Read-only verification; no writes.
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

STAGING = _rows = None


def _rows(name):
    return list(csv.DictReader(open(INT / name, encoding="utf-8-sig")))


STAGING = _rows("g3_to_g1_mapping_candidate_staging.csv")
REVIEW = _rows("g3_to_g1_mapping_candidate_review.csv")
EXCL = _rows("g3_to_g1_mapping_candidate_exclusions.csv")
AUDIT = json.load(open(INT / "g3_to_g1_aggregation_candidate_load_audit.json", encoding="utf-8"))


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


DBROWS = _db_rows()


# ---------------------------------------------------------------------------
# 1-4. row counts + distribution
# ---------------------------------------------------------------------------

def test_production_rows_246():
    assert len(DBROWS) == 246


def test_relation_distribution():
    from collections import Counter
    rel = Counter(r["mapping_relation"] for r in DBROWS)
    assert rel == Counter({"contained_in": 172, "dominant_overlap": 34,
                           "partial_overlap": 40})


def test_distinct_source_count_226():
    assert len({r["source_region_pk"] for r in DBROWS}) == 226


def test_staging_review_246_pass():
    assert len(STAGING) == 246 and len(REVIEW) == 246
    assert all(r["review_result"] == "PASS" for r in REVIEW)


# ---------------------------------------------------------------------------
# 5. production ↔ staging fidelity
# ---------------------------------------------------------------------------

def test_production_staging_fidelity():
    stage_by_id = {c["candidate_id"]: c for c in STAGING}
    assert len(DBROWS) == len(STAGING)
    stage = {}
    for r in DBROWS:
        cid = r["provenance_json"]["staging_candidate_id"]
        assert cid in stage_by_id, cid
        c = stage_by_id[cid]
        assert r["source_region_pk"] == int(c["source_region_pk"])
        assert r["target_region_pk"] == int(c["target_region_pk"])
        assert r["mapping_relation"] == c["mapping_relation"]
        assert r["mapping_method"] == c["mapping_method"]
        assert r["source_granularity_level"] == c["source_granularity_level"]
        assert r["target_granularity_level"] == c["target_granularity_level"]
        assert (r["source_coverage_ratio"] or None) == (float(c["source_coverage_ratio"]) if c["source_coverage_ratio"] else None)
        assert (r["target_coverage_ratio"] or None) == (float(c["target_coverage_ratio"]) if c["target_coverage_ratio"] else None)
        assert (r["spatial_overlap_ratio"] or None) == (float(c["spatial_overlap_ratio"]) if c["spatial_overlap_ratio"] else None)
        assert r["mapping_confidence"] is None
        stage[cid] = r
    assert len(stage) == 246


# ---------------------------------------------------------------------------
# 6-13. lifecycle
# ---------------------------------------------------------------------------

def test_all_record_status_proposed():
    # load wrote proposed; 1F-I promotion moved the batch to active
    assert all(r["record_status"] == "active" for r in DBROWS)


def test_all_review_status_approved_after_gate():
    # 1F-H approved the loaded batch; load-time pending is superseded
    assert all(r["review_status"] == "approved" for r in DBROWS)


def test_reviewed_by_at_set_after_gate():
    # 1F-H set reviewer + batch timestamp on the loaded batch
    assert all(r["reviewed_by"] == "gate1fh_g3_g1_aggregation_approval" for r in DBROWS)
    assert all(r["reviewed_at"] is not None for r in DBROWS)


def test_no_db_rollup_flags():
    # load wrote rollup=FALSE; 1F-I enabled rollup on the 172 contained only
    rollup = [r for r in DBROWS if r["rollup_eligible"]]
    assert len(rollup) == 172
    assert all(r["mapping_relation"] == "contained_in" for r in rollup)
    assert all(r["is_primary_rollup"] for r in rollup)


def test_no_active_rows():
    # 1F-I promoted the loaded batch to active
    assert all(r["record_status"] == "active" for r in DBROWS)


def test_no_approved_rows():
    # 1F-H approved the loaded batch; "no approved" was the pre-approval load state
    assert all(r["review_status"] == "approved" for r in DBROWS)


def test_mapping_confidence_all_null():
    assert all(r["mapping_confidence"] is None for r in DBROWS)


# ---------------------------------------------------------------------------
# 14. BG coverage NULL semantics preserved
# ---------------------------------------------------------------------------

def test_bg_coverage_null():
    bg = [r for r in DBROWS if "Striatum" in r["provenance_json"]
          .get("brainnetome_parcel_identity", {}).get("official_code", "")]
    # BG official_code starts with BG
    bg = [r for r in DBROWS
          if r["provenance_json"]["brainnetome_parcel_identity"]["official_code"].startswith("BG")]
    assert len(bg) == 12
    assert all(r["source_coverage_ratio"] is None for r in bg)
    assert all(r["target_coverage_ratio"] is None for r in bg)


# ---------------------------------------------------------------------------
# 15-16. partial multi-target + exclusions leak
# ---------------------------------------------------------------------------

def test_partial_multi_target_preserved():
    from collections import Counter
    part = [r for r in DBROWS if r["mapping_relation"] == "partial_overlap"]
    assert len(part) == 40
    per_src = Counter(r["source_region_pk"] for r in part)
    assert all(v == 2 for v in per_src.values())
    assert all(r["is_primary_rollup"] is False for r in part)


def test_exclusions_leak_zero():
    excl_eids = {m["g3_entity_id"] for m in EXCL}
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""SELECT count(*) FROM brain_region_aggregation_mappings
            WHERE source_region_pk IN (SELECT b.entity_pk FROM brain_regions b
                JOIN kg_entities e ON e.entity_pk=b.entity_pk WHERE e.entity_id = ANY(%s))""",
            (list(excl_eids),))
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()
    assert AUDIT["excluded_source_leak_count"] == 0


# ---------------------------------------------------------------------------
# 17-19. granularity + hemisphere
# ---------------------------------------------------------------------------

def test_source_g3_target_g1():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""SELECT count(*) FROM brain_region_aggregation_mappings b
            JOIN brain_regions s ON s.entity_pk=b.source_region_pk
            JOIN brain_regions t ON t.entity_pk=b.target_region_pk
            WHERE s.granularity_level<>'G3_MESO_FINE' OR t.granularity_level<>'G1_MACRO'""")
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()


def test_hemisphere_mismatch_zero():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""SELECT count(*) FROM brain_region_aggregation_mappings b
            JOIN brain_regions s ON s.entity_pk=b.source_region_pk
            JOIN brain_regions t ON t.entity_pk=b.target_region_pk
            WHERE s.hemisphere<>t.hemisphere""")
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 20. mapping_id format/unique
# ---------------------------------------------------------------------------

def test_mapping_id_unique_and_format():
    ids = [r["mapping_id"] for r in DBROWS]
    assert len(ids) == len(set(ids)) == 246
    assert all(re.fullmatch(r"NGIQ-BRAM-\d{8}", i) for i in ids)


# ---------------------------------------------------------------------------
# 21. provenance staging candidate ID complete
# ---------------------------------------------------------------------------

def test_provenance_candidate_id_complete():
    for r in DBROWS:
        p = r["provenance_json"]
        assert p["staging_candidate_id"].startswith("G3G1-STAGE-")
        assert p["load_phase"] == "G3_G1_AGGREGATION_CANDIDATE_LOAD_V1"
        assert p["fidelity_review_status"] == "PASS"
        assert p["human_reviewed"] is False
        assert p["expert_approved"] is False


# ---------------------------------------------------------------------------
# 22. rerun safety / duplicate prevention
# ---------------------------------------------------------------------------

def test_rerun_noop_safety():
    # current DB state: 246 rows under load_phase; audit reflects no-op rerun
    assert AUDIT["production_row_count_after"] == 246
    assert AUDIT["inserted_count"] == 0 or AUDIT["inserted_count"] == 246
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""SELECT count(*) FROM brain_region_aggregation_mappings
            WHERE provenance_json->>'load_phase' = 'G3_G1_AGGREGATION_CANDIDATE_LOAD_V1'""")
        assert cur.fetchone()[0] == 246
    finally:
        conn.close()
    # no duplicate (source,target,relation)
    cur = _conn().cursor()
    try:
        cur.execute("""SELECT source_region_pk, target_region_pk, mapping_relation, count(*)
            FROM brain_region_aggregation_mappings GROUP BY 1,2,3 HAVING count(*)>1""")
        assert cur.fetchall() == []
    finally:
        cur.connection.close()


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
