"""Phase 1F-D — G3→G1 Mapping Candidate Fidelity Review (artifact-level, read-only).

Validates the fidelity-review artifacts produced from the Phase 1F-C staging
candidates against the frozen scientific decisions. This is a STAGING
FIDELITY REVIEW — NOT a database review_status=approved transition. Zero DB
writes; production read-only identity checks only.
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

FROZEN_DIST = {"APPROVE_CONTAINED_IN": 172, "APPROVE_DOMINANT_OVERLAP": 34,
               "PARTIAL_OVERLAP": 20, "NO_G1_ROLLUP": 10, "CONFLICT_REVIEW": 10}
REL_FROM_DEC = {"APPROVE_CONTAINED_IN": "contained_in",
                "APPROVE_DOMINANT_OVERLAP": "dominant_overlap",
                "PARTIAL_OVERLAP": "partial_overlap"}


def _rows(name):
    return list(csv.DictReader(open(INT / name, encoding="utf-8-sig")))


MAN = _rows("g3_to_g1_full_decision_coverage_manifest.csv")
CAND = _rows("g3_to_g1_mapping_candidate_staging.csv")
EXCL = _rows("g3_to_g1_mapping_candidate_exclusions.csv")
REV = _rows("g3_to_g1_mapping_candidate_review.csv")
SUM = json.load(open(INT / "g3_to_g1_mapping_candidate_review_summary.json", encoding="utf-8"))
PART = _rows("g3_to_g1_mapping_candidate_partial_review.csv")


def _conn(db=PROD):
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=db, autocommit=True)


# ---------------------------------------------------------------------------
# 1-3. source coverage + union/intersection completeness
# ---------------------------------------------------------------------------

def test_246_source_coverage():
    assert len(MAN) == 246
    assert len({m["g3_entity_id"] for m in MAN}) == 246


def test_candidate_exclusion_union_is_246():
    cand_src = {c["source_entity_id"] for c in CAND}
    exc_src = {m["g3_entity_id"] for m in EXCL}
    assert len(cand_src | exc_src) == 246
    assert len(cand_src) == 226
    assert len(exc_src) == 20
    assert 226 + 20 == 246


def test_candidate_exclusion_intersection_empty():
    cand_src = {c["source_entity_id"] for c in CAND}
    exc_src = {m["g3_entity_id"] for m in EXCL}
    assert not (cand_src & exc_src)


# ---------------------------------------------------------------------------
# 4. relation fidelity
# ---------------------------------------------------------------------------

def test_relation_fidelity_all_pass():
    man_by_src = {m["g3_entity_id"]: m for m in MAN}
    for c in CAND:
        m = man_by_src[c["source_entity_id"]]
        assert REL_FROM_DEC[m["effective_scientific_decision"]] == c["mapping_relation"]


def test_relation_counts():
    from collections import Counter
    rel = Counter(c["mapping_relation"] for c in CAND)
    assert rel == Counter({"contained_in": 172, "dominant_overlap": 34,
                           "partial_overlap": 40})
    assert len(CAND) == 246


# ---------------------------------------------------------------------------
# 5. partial exactly 2 targets
# ---------------------------------------------------------------------------

def test_partial_exactly_2_targets():
    from collections import Counter
    part = [c for c in CAND if c["mapping_relation"] == "partial_overlap"]
    per_src = Counter(c["source_entity_id"] for c in part)
    assert len(per_src) == 20
    assert all(v == 2 for v in per_src.values())


def test_partial_review_all_pass():
    assert len(PART) == 20
    assert all(r["status"] == "PASS" for r in PART)


# ---------------------------------------------------------------------------
# 6. partial coverage real
# ---------------------------------------------------------------------------

def test_partial_coverage_really_per_target():
    from collections import Counter
    part = [c for c in CAND if c["mapping_relation"] == "partial_overlap"]
    per_src = {}
    for c in part:
        per_src.setdefault(c["source_entity_id"], set()).add(
            float(c["source_coverage_ratio"]))
    # each partial source has 2 DISTINCT coverage values (not top1 duplicated)
    assert all(len(v) == 2 for v in per_src.values())


# ---------------------------------------------------------------------------
# 7-8. BG NULL coverage + subcortical 24 provenance
# ---------------------------------------------------------------------------

def test_bg_authority_null_coverage():
    bg = [c for c in CAND if "Striatum" in c["source_name"]]
    assert len(bg) == 12
    for c in bg:
        assert c["source_coverage_ratio"] == ""
        assert c["target_coverage_ratio"] == ""
        assert c["mapping_confidence"] == ""
        assert c["mapping_relation"] == "contained_in"
        assert c["mapping_method"] == "authoritative_anatomical_mapping"


def test_subcortical_24_provenance_explicit():
    sub = [m for m in MAN if m["decision_origin"] == "SUBCORTICAL_CANONICAL"]
    assert len(sub) == 24
    from collections import Counter
    fams = Counter(m["official_code"].split("_")[0] for m in sub)
    assert fams == Counter({"Amyg": 4, "Hipp": 4, "Tha": 16})
    for m in sub:
        assert m["historical_decision"] == "AUTO_HIGH"
        assert m["provenance_source_artifact"] == "g3_brainnetome_to_g1_macro_candidates.csv"
        assert m["primary_target_g1_entity_id"]
    assert SUM["subcortical_canonical"]["count"] == 24


# ---------------------------------------------------------------------------
# 9. mapping_method distribution
# ---------------------------------------------------------------------------

def test_method_distribution_exact():
    from collections import Counter
    methods = Counter(c["mapping_method"] for c in CAND)
    assert methods == Counter({"authoritative_anatomical_mapping": 140, "hybrid": 106})
    # authoritative = single-seed + subcortical + BG; hybrid = composite freeze
    man_by_src = {m["g3_entity_id"]: m for m in MAN}
    for c in CAND:
        m = man_by_src[c["source_entity_id"]]
        if m["decision_origin"] in ("SEED_CONTAINMENT_CONFIRMED", "SUBCORTICAL_CANONICAL", "BG_AUTHORITY"):
            assert c["mapping_method"] == "authoritative_anatomical_mapping"
        else:
            assert c["mapping_method"] == "hybrid"
    assert SUM["method_distribution"]["authoritative_anatomical_mapping"] == 140
    assert SUM["method_distribution"]["hybrid"] == 106


# ---------------------------------------------------------------------------
# 10-13. confidence NULL / lifecycle / rollup separation
# ---------------------------------------------------------------------------

def test_confidence_all_null():
    assert all(c["mapping_confidence"] == "" for c in CAND)


def test_lifecycle_all_proposed_pending():
    for c in CAND:
        assert c["proposed_record_status"] == "proposed"
        assert c["proposed_review_status"] == "pending"
        assert c["proposed_rollup_eligible"] == "FALSE"
        assert c["proposed_is_primary_rollup"] == "FALSE"


def test_scientific_rollup_only_contained():
    for c in CAND:
        is_contained = c["mapping_relation"] == "contained_in"
        assert (c["scientific_rollup_eligible"] == "TRUE") == is_contained


# ---------------------------------------------------------------------------
# 14-15. target identity/granularity + hemisphere (production read-only)
# ---------------------------------------------------------------------------

def test_target_identity_granularity():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""SELECT b.entity_pk, e.entity_id, b.granularity_level, b.hemisphere
            FROM brain_regions b JOIN kg_entities e ON e.entity_pk=b.entity_pk
            WHERE e.record_status='active'""")
        regions = {pk: (eid, gran, hemi) for pk, eid, gran, hemi in cur.fetchall()}
    finally:
        conn.close()
    for c in CAND:
        spk, tpk = int(c["source_region_pk"]), int(c["target_region_pk"])
        assert spk in regions and regions[spk][1] == "G3_MESO_FINE"
        assert tpk in regions and regions[tpk][1] == "G1_MACRO"
        assert regions[spk][0] == c["source_entity_id"]
        assert regions[tpk][0] == c["target_entity_id"]


def test_hemisphere_consistent():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""SELECT b.entity_pk, b.hemisphere FROM brain_regions b
            JOIN kg_entities e ON e.entity_pk=b.entity_pk WHERE e.record_status='active'""")
        hemi = {pk: h for pk, h in cur.fetchall()}
    finally:
        conn.close()
    for c in CAND:
        assert hemi[int(c["source_region_pk"])] == hemi[int(c["target_region_pk"])]


def test_review_zero_hemisphere_mismatch():
    assert SUM["hemisphere_mismatch_count"] == 0


# ---------------------------------------------------------------------------
# 16. candidate_id deterministic
# ---------------------------------------------------------------------------

def test_candidate_id_deterministic_no_collision():
    ids = [c["candidate_id"] for c in CAND]
    assert len(ids) == len(set(ids)) == 246
    assert all(not i.startswith("NGIQ-BRAM") for i in ids)
    # same (source, target, relation) must map to same id
    seen = {}
    for c in CAND:
        key = (c["source_entity_id"], c["target_entity_id"], c["mapping_relation"])
        assert key not in seen or seen[key] == c["candidate_id"]
        seen[key] = c["candidate_id"]
    assert SUM["candidate_id_collision_count"] == 0


# ---------------------------------------------------------------------------
# 17. provenance
# ---------------------------------------------------------------------------

def test_provenance_complete():
    for c in CAND:
        p = json.loads(c["provenance_json"])
        assert p.get("decision_phase")
        assert p.get("decision_origin")
        assert p.get("effective_scientific_decision")
        assert p.get("source_frozen_artifact")
        assert p.get("brainnetome_parcel_identity")
        assert p.get("human_reviewed") is False
        assert p.get("expert_approved") is False
        assert "decision_source_normalized" in p


def test_chatgpt_normalized_not_reviewer():
    for c in CAND:
        p = json.loads(c["provenance_json"])
        if p["decision_origin"] == "FREEZE":
            assert p["decision_source_normalized"] == "ChatGPT-assisted scientific review"
            assert p["decision_source_raw"] == "ChatGPT human scientific review"


# ---------------------------------------------------------------------------
# 18. exclusions precise
# ---------------------------------------------------------------------------

def test_exclusions_exact_20():
    from collections import Counter
    assert len(EXCL) == 20
    dec = Counter(m["effective_scientific_decision"] for m in EXCL)
    assert dec == Counter({"NO_G1_ROLLUP": 10, "CONFLICT_REVIEW": 10})
    codes = {m["official_code"] for m in EXCL}
    required = {
        "IFG_L_6_2", "IFG_R_6_2", "STG_L_6_1", "STG_R_6_1",
        "MVOcC_L_5_5", "MVOcC_R_5_5", "pSTS_L_2_1", "pSTS_R_2_1",
        "pSTS_L_2_2", "pSTS_R_2_2", "CG_L_7_3", "CG_R_7_3",
        "MVOcC_L_5_2", "MVOcC_R_5_2", "MVOcC_L_5_3", "MVOcC_R_5_3",
        "LOcC_L_2_1", "LOcC_R_2_1", "LOcC_L_2_2", "LOcC_R_2_2",
    }
    assert codes == required


# ---------------------------------------------------------------------------
# review artifact + exceptions
# ---------------------------------------------------------------------------

def test_review_all_pass():
    assert len(REV) == 246
    assert all(r["review_result"] == "PASS" for r in REV)
    for r in REV:
        for field in ("decision_fidelity_status", "target_identity_status",
                      "hemisphere_status", "coverage_status", "method_status",
                      "lifecycle_status", "provenance_status"):
            assert r[field] == "PASS", (r["candidate_id"], field)
    assert SUM["pass_count"] == 246
    assert SUM["fail_count"] == 0


def test_exceptions_empty():
    exc = _rows("g3_to_g1_mapping_candidate_review_exceptions.csv")
    assert len(exc) == 0
    assert SUM["exception_count"] == 0


# ---------------------------------------------------------------------------
# 19. production / e2e still zero
# ---------------------------------------------------------------------------

def test_production_mapping_zero():
    # G3→G1 slice only. The later G4→G3 chain must not be counted here.
    conn = _conn(PROD)
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings"
                    " WHERE source_granularity_level='G3_MESO_FINE' AND target_granularity_level='G1_MACRO'")
        total = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings"
                    " WHERE source_granularity_level='G3_MESO_FINE' AND target_granularity_level='G1_MACRO'"
                    " AND record_status='active' AND review_status='approved'")
        active = cur.fetchone()[0]
        # 1F-H approved, then 1F-I promoted the batch to active
        assert total == 246 and active == 246
    finally:
        conn.close()


def test_e2e_mapping_zero():
    conn = _conn(E2E)
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings")
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
