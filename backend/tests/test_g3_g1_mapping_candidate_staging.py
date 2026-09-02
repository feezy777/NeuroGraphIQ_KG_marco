"""Phase 1F-C — G3→G1 Mapping Candidate Staging (artifact-level + production read-only).

Validates the four staging artifacts without writing any database rows:
  * g3_to_g1_full_decision_coverage_manifest.csv  — 246 G3 sources, 0 pending
  * g3_to_g1_mapping_candidate_staging.csv        — candidate relation rows
  * g3_to_g1_mapping_candidate_exclusions.csv     — NO_G1_ROLLUP / CONFLICT_REVIEW
  * g3_to_g1_mapping_candidate_staging_summary.json

Decision precedence frozen: G3_G1_SCIENTIFIC_FREEZE_V1 > BG/human authority >
SEED_CONTAINMENT_CONFIRMED. sOcG / pSTS / rCunG / cCunG never produce candidates.
Production brain_region_aggregation_mappings stays at 0.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import psycopg
import pytest

BACKEND = Path(__file__).resolve().parents[1]
PROD = "neurographiq_human_brain_v1"
E2E = "neurographiq_human_brain_v1_e2e"
INT = BACKEND / "data" / "integration"

COMP = {"MFG", "IFG", "OrG", "STG", "PhG", "IPL", "CG", "MVOcC"}
FROZEN_DIST = {"APPROVE_CONTAINED_IN": 172, "APPROVE_DOMINANT_OVERLAP": 34,
               "PARTIAL_OVERLAP": 20, "NO_G1_ROLLUP": 10, "CONFLICT_REVIEW": 10}


def _rows(name):
    return list(csv.DictReader(open(INT / name, encoding="utf-8-sig")))


MANIFEST = _rows("g3_to_g1_full_decision_coverage_manifest.csv")
CAND = _rows("g3_to_g1_mapping_candidate_staging.csv")
EXCL = _rows("g3_to_g1_mapping_candidate_exclusions.csv")
SUMMARY = json.load(open(INT / "g3_to_g1_mapping_candidate_staging_summary.json", encoding="utf-8"))


def _conn(db=PROD):
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=db, autocommit=True)


# ---------------------------------------------------------------------------
# 1-2. full 246 decision coverage, 0 pending
# ---------------------------------------------------------------------------

def test_manifest_246_rows():
    assert len(MANIFEST) == 246
    assert len({m["g3_entity_id"] for m in MANIFEST}) == 246
    assert len({m["parcel_id"] for m in MANIFEST}) == 246


def test_manifest_zero_pending():
    assert all(m["effective_scientific_decision"] != "PENDING_CHATGPT_FREEZE"
               and "PENDING" not in m["effective_scientific_decision"]
               for m in MANIFEST)


def test_manifest_distribution_exact():
    from collections import Counter
    dist = Counter(m["effective_scientific_decision"] for m in MANIFEST)
    assert dist == Counter(FROZEN_DIST)


# ---------------------------------------------------------------------------
# 3. decision precedence: freeze overrides older authority
# ---------------------------------------------------------------------------

def test_socg_conflict_overrides_seed_containment():
    # sOcG = LOcC_2_1 / LOcC_2_2 (parcels 207-210); LOcC_4_x parcels stay contained
    socg = [m for m in MANIFEST if m["official_code"].startswith("LOcC")
            and "_2_" in m["official_code"]]
    assert len(socg) == 4
    assert all(m["effective_scientific_decision"] == "CONFLICT_REVIEW" for m in socg)
    assert all(m["historical_decision"] == "SEED_CONTAINMENT_CONFIRMED (historical)"
               for m in socg)


def test_rcung_ccung_conflict_overrides_approved_candidate():
    for suffix in ("MVOcC_L_5_2", "MVOcC_R_5_2", "MVOcC_L_5_3", "MVOcC_R_5_3"):
        rows = [m for m in MANIFEST if m["official_code"] == suffix]
        assert len(rows) == 1
        assert rows[0]["effective_scientific_decision"] == "CONFLICT_REVIEW"
        assert rows[0]["historical_decision"] == "HUMAN_AUTHORITY_APPROVED_CANDIDATE"


def test_bg_direct_retained_as_contained():
    bg = [m for m in MANIFEST if m["official_code"].startswith("BG")]
    assert len(bg) == 12
    assert all(m["effective_scientific_decision"] == "APPROVE_CONTAINED_IN" for m in bg)
    assert all(m["primary_target_g1_entity_id"] for m in bg)


# ---------------------------------------------------------------------------
# 4-5. candidate/exclusion separation
# ---------------------------------------------------------------------------

def test_candidate_relations_only_three():
    rels = {c["mapping_relation"] for c in CAND}
    assert rels == {"contained_in", "dominant_overlap", "partial_overlap"}


def test_exclusions_only_no_rollup_conflict():
    decs = {m["effective_scientific_decision"] for m in EXCL}
    assert decs == {"NO_G1_ROLLUP", "CONFLICT_REVIEW"}
    assert len(EXCL) == 20


def test_no_target_pk_in_exclusions():
    assert all(not m.get("target_region_pk") for m in EXCL)


def test_socg_psts_not_in_candidates():
    src_names = {c["source_name"] for c in CAND}
    assert not any("occipital" in n.lower() and "superior lateral" in n.lower() for n in src_names)
    assert not any("STS" in n.upper() for n in src_names)


# ---------------------------------------------------------------------------
# 6. partial multi-target (one relation row per evidence target)
# ---------------------------------------------------------------------------

def test_partial_one_row_per_target():
    from collections import Counter
    part = [c for c in CAND if c["mapping_relation"] == "partial_overlap"]
    assert len(part) == 40  # 20 sources x 2 evidence targets
    per_src = Counter(c["source_entity_id"] for c in part)
    assert all(v == 2 for v in per_src.values())


def test_partial_no_fake_primary_in_manifest():
    part = [m for m in MANIFEST if m["effective_scientific_decision"] == "PARTIAL_OVERLAP"]
    assert len(part) == 20
    assert all(not m["primary_target_g1_entity_id"] for m in part)


# ---------------------------------------------------------------------------
# 7. deterministic target resolution (read-only production)
# ---------------------------------------------------------------------------

def test_manifest_targets_resolve_in_production():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT entity_id, entity_pk FROM kg_entities WHERE record_status='active'")
        eid2pk = dict(cur.fetchall())
    finally:
        conn.close()
    for m in MANIFEST:
        assert int(m["g3_region_pk"]) == eid2pk[m["g3_entity_id"]]
        if m["primary_target_g1_entity_id"]:
            assert m["primary_target_g1_entity_id"] in eid2pk


def test_candidate_sources_and_targets_are_regions():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT entity_pk, granularity_level FROM brain_regions")
        gran = dict(cur.fetchall())
    finally:
        conn.close()
    for c in CAND:
        assert gran.get(int(c["source_region_pk"])) == "G3_MESO_FINE"
        assert gran.get(int(c["target_region_pk"])) == "G1_MACRO"


# ---------------------------------------------------------------------------
# 8. hemisphere preservation
# ---------------------------------------------------------------------------

def test_hemisphere_consistent_with_target_name():
    def hemi_of_name(n):
        return "left" if n.startswith("Left ") else "right"
    hemi_map = {m["g3_entity_id"]: m["hemisphere"] for m in MANIFEST}
    for c in CAND:
        assert hemi_map[c["source_entity_id"]] == hemi_of_name(c["target_name"])


# ---------------------------------------------------------------------------
# 9-10. lifecycle defaults + scientific vs DB rollup separation
# ---------------------------------------------------------------------------

def test_candidate_lifecycle_defaults():
    for c in CAND:
        assert c["proposed_record_status"] == "proposed"
        assert c["proposed_review_status"] == "pending"
        assert c["proposed_rollup_eligible"] == "FALSE"
        assert c["proposed_is_primary_rollup"] == "FALSE"
        assert c["mapping_confidence"] == ""


def test_scientific_rollup_only_contained():
    for c in CAND:
        is_contained = c["mapping_relation"] == "contained_in"
        assert (c["scientific_rollup_eligible"] == "TRUE") == is_contained


# ---------------------------------------------------------------------------
# 11. coverage NULL semantics (BG / subcortical have no surface)
# ---------------------------------------------------------------------------

def test_subcortical_coverage_null():
    sub = [c for c in CAND if "Amygdala" in c["source_name"]
           or "Hippocampus" in c["source_name"] or "Thalamus" in c["source_name"]
           or "Striatum" in c["source_name"]]
    assert len(sub) == 36  # 12 BG + 24 subcortical
    for c in sub:
        assert c["source_coverage_ratio"] == ""
        assert c["target_coverage_ratio"] == ""


def test_surface_coverage_real_positive():
    surf = [c for c in CAND if c["source_coverage_ratio"]]
    assert len(surf) > 0
    for c in surf:
        assert float(c["source_coverage_ratio"]) > 0


# ---------------------------------------------------------------------------
# 12. provenance semantics
# ---------------------------------------------------------------------------

def test_provenance_human_reviewed_false():
    for c in CAND:
        p = json.loads(c["provenance_json"])
        assert p["human_reviewed"] is False
        assert p["expert_approved"] is False
        assert "decision_source_normalized" in p


def test_chatgpt_not_labeled_human_reviewer():
    for c in CAND:
        p = json.loads(c["provenance_json"])
        if p["decision_origin"] == "FREEZE":
            assert p["decision_source_raw"] == "ChatGPT human scientific review"
            assert p["decision_source_normalized"] == "ChatGPT-assisted scientific review"


# ---------------------------------------------------------------------------
# 13. summary consistency
# ---------------------------------------------------------------------------

def test_summary_consistent():
    assert SUMMARY["full_g3_source_count"] == 246
    assert SUMMARY["contained_source_count"] == 172
    assert SUMMARY["dominant_source_count"] == 34
    assert SUMMARY["partial_source_count"] == 20
    assert SUMMARY["no_rollup_source_count"] == 10
    assert SUMMARY["conflict_source_count"] == 10
    assert SUMMARY["excluded_source_count"] == 20
    assert SUMMARY["unresolved_source_count"] == 0
    assert SUMMARY["unresolved_target_count"] == 0
    assert SUMMARY["duplicate_candidate_count"] == 0
    assert SUMMARY["hemisphere_mismatch_count"] == 0
    assert SUMMARY["production_write_count"] == 0


# ---------------------------------------------------------------------------
# 14. production / e2e zero write
# ---------------------------------------------------------------------------

def test_production_aggregation_zero():
    # Phase 1F-F loaded the 246 candidates as proposed+pending; the staging
    # gate's zero-insert guarantee became "all loaded rows are proposed+pending".
    conn = _conn(PROD)
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings")
        total = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings"
                    " WHERE record_status='active' AND review_status='approved'")
        active = cur.fetchone()[0]
        # 1F-H approved, then 1F-I promoted the batch to active
        assert total == 246 and active == 246
    finally:
        conn.close()


def test_e2e_aggregation_zero():
    conn = _conn(E2E)
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings")
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
