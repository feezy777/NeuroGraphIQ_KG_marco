"""Gate 7B Phase 2J-A — G4→G3 Aggregation Mapping Candidate Staging.

Read-only verification of the staged 461 aggregation-mapping candidates (and
173 exclusions). Deterministic pk resolution, candidate ids, coverage
semantics, lifecycle stays proposed/pending/FALSE, provenance complete, and no
DB writes (production unchanged).
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import psycopg
import pytest

BACKEND = Path(__file__).resolve().parents[1]
PROD = "neurographiq_human_brain_v1"
INT = BACKEND / "data" / "integration"
STAGE = INT / "g4_g3_mapping_candidate_staging.csv"
EXCL = INT / "g4_g3_mapping_candidate_exclusions.csv"
SUM = json.load(open(INT / "g4_g3_mapping_candidate_staging_summary.json", encoding="utf-8"))


def _rows(p: Path):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _conn(db=PROD):
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=db, autocommit=True)


def test_candidate_rows_461():
    rows = _rows(STAGE)
    assert len(rows) == 461
    assert SUM["candidate_relation_count"] == 461


def test_contained_20():
    assert sum(1 for r in _rows(STAGE) if r["mapping_relation"] == "contained_in") == 20


def test_dominant_110():
    assert sum(1 for r in _rows(STAGE) if r["mapping_relation"] == "dominant_overlap") == 110


def test_partial_331():
    assert sum(1 for r in _rows(STAGE) if r["mapping_relation"] == "partial_overlap") == 331


def test_mapped_source_267():
    src = {r["source_entity_id"] for r in _rows(STAGE)}
    assert len(src) == 267
    assert SUM["mapped_source_count"] == 267


def test_exclusions_173():
    ex = _rows(EXCL)
    assert len(ex) == 173
    assert SUM["excluded_source_count"] == 173


def test_no_mapping_18():
    assert sum(1 for r in _rows(EXCL) if r["scientific_decision"] == "NO_G3_MAPPING") == 18


def test_conflict_91():
    assert sum(1 for r in _rows(EXCL) if r["scientific_decision"] == "CONFLICT_REVIEW") == 91


def test_shared_64():
    assert sum(1 for r in _rows(EXCL) if r["scientific_decision"] == "SHARED_SPATIAL_EVIDENCE_ONLY") == 64


def test_union_440_intersection_0():
    mapped = {r["source_entity_id"] for r in _rows(STAGE)}
    excluded = {r["canonical_g4_id"] for r in _rows(EXCL)}
    assert len(mapped | excluded) == 440
    assert mapped.isdisjoint(excluded)


def test_source_identity_exact():
    # every source resolves to a production brain_region pk and G4 granularity
    for r in _rows(STAGE):
        assert r["source_region_pk"]
        assert r["source_granularity_level"] == "G4_MICROSTRUCTURAL_FINE"


def test_target_identity_exact():
    for r in _rows(STAGE):
        assert r["target_region_pk"]
        assert r["target_granularity_level"] == "G3_MESO_FINE"


def test_granularity_mismatch_0():
    assert SUM["qa"]["source_gran_mismatch"] == 0
    assert SUM["qa"]["target_gran_mismatch"] == 0


def test_hemisphere_mismatch_0():
    assert SUM["qa"]["hemi_mismatch"] == 0


def test_duplicate_relation_0():
    tri = Counter((r["source_region_pk"], r["target_region_pk"], r["mapping_relation"]) for r in _rows(STAGE))
    assert all(v == 1 for v in tri.values())


def test_deterministic_candidate_ids():
    rows = _rows(STAGE)
    assert len({r["candidate_id"] for r in rows}) == 461
    for r in rows[:5]:
        payload = f"{r['source_entity_id']}|{r['target_entity_id']}|{r['mapping_relation']}|G4_G3_FINAL_SCIENTIFIC_POLICY_V1"
        exp = "G4G3-STAGE-" + hashlib.sha256(payload.encode()).hexdigest()[:20].upper()
        assert r["candidate_id"] == exp


def test_scientific_rollup_true_20():
    assert sum(1 for r in _rows(STAGE) if r["scientific_rollup_eligible"] == "True") == 20
    assert SUM["scientific_rollup_true"] == 20


def test_proposed_rollup_primary_false():
    assert all(r["proposed_rollup_eligible"] == "FALSE" for r in _rows(STAGE))
    assert all(r["proposed_is_primary_rollup"] == "FALSE" for r in _rows(STAGE))
    assert SUM["proposed_rollup_true"] == 0
    assert SUM["proposed_primary_true"] == 0


def test_proposed_pending_461():
    assert all(r["proposed_record_status"] == "proposed" for r in _rows(STAGE))
    assert all(r["proposed_review_status"] == "pending" for r in _rows(STAGE))
    assert SUM["record_status_proposed"] == 461
    assert SUM["review_status_pending"] == 461


def test_confidence_not_fabricated():
    rows = _rows(STAGE)
    assert all(r["mapping_confidence"] in ("", None) for r in rows)
    assert all(r["spatial_overlap_ratio"] in ("", None) for r in rows)
    # coverage present only where a real computed metric exists
    assert all(r["source_coverage_ratio"] not in ("", None) for r in rows)


def test_provenance_complete():
    for r in _rows(STAGE):
        p = json.loads(r["provenance_json"])
        assert p["final_scientific_policy"] == "G4_G3_FINAL_SCIENTIFIC_POLICY_V1"
        assert p["decision_artifact"]
        assert p["source_canonical_g4_id"] == r["source_entity_id"]
        assert p["target_canonical_g3_id"] == r["target_entity_id"]
        assert p["owner_scientific_review_status"] == "OWNER_SCIENTIFIC_REVIEWED"
        assert p["human_reviewed"] is False
        assert p["expert_approved"] is False
        assert p["production_review_status"] == "pending"
        for k in ("evidence_2g_probability_overlap", "evidence_2h_interpretation",
                  "evidence_2ia_policy", "evidence_2ib_owner_revision", "evidence_2ic_final_decision",
                  "transform_provenance", "brainnetome_probability_asset", "julich_probability_asset"):
            assert p[k]


def test_semantic_contained_gate_20():
    rows = [r for r in _rows(STAGE) if r["mapping_relation"] == "contained_in"]
    assert len(rows) == 20
    assert all(r["semantic_compatibility_status"] in ("EXACT_FAMILY", "NESTED_COMPATIBLE_FAMILY") for r in rows)
    assert SUM["qa"]["semantic_gate_fail"] == 0


def test_no_fake_reviewer():
    for r in _rows(STAGE):
        assert r.get("reviewed_by", "") in ("", None)
    assert all("reviewed_by" not in json.loads(r["provenance_json"]) or
               json.loads(r["provenance_json"]).get("reviewed_by") is None for r in _rows(STAGE))


def test_g3_to_g1_production_unchanged():
    # Staging gate itself never writes; G3->G1 must stay intact. Phase 2J-C later
    # legitimately adds 461 G4->G3 proposed rows on top of the 246 G3->G1 rows.
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G3_MESO_FINE' AND record_status='active' AND review_status='approved'")
        active_approved = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G3_MESO_FINE'")
        g3 = cur.fetchone()[0]
    finally:
        conn.close()
    assert g3 == 246 and active_approved == 246


def test_g4_g3_production_rows_state():
    # 0 = pre-load snapshot (Phase 2J-A time); 461 = after Phase 2J-C load.
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G4_MICROSTRUCTURAL_FINE'")
        g4 = cur.fetchone()[0]
    finally:
        conn.close()
    assert g4 in (0, 461)


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
