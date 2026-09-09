"""Phase1.7 V3 - BNST canonical entity admission + granularity / G1-rollup decision tests.

Validates the ontology-admission package (audit, terminology crosswalk, granularity,
G1 roll-up, admission, proposal) against the 23 hard gates. Read-only; no DB write /
classification change / promotion / commit; no geometry artifacts are produced.
"""
from __future__ import annotations

import csv
import json
import subprocess
from collections import Counter
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
MACRO96 = BACKEND / "data" / "atlases" / "macro96" / "macro96_normalized_manifest.csv"
CLASS = D16 / "phase17_v3_classification.csv"
EXT_MAN = D16 / "phase17_v3_external_g1_asset_manifest.csv"
DERIVED = BACKEND / "data" / "atlases" / "derived_g1"
THAL = D16 / "phase17_v3_thalamus_final_freeze_v1.json"
AMYG = D16 / "phase17_v3_amygdala_g1_scope_contract_v1.json"
HIPP = D16 / "phase17_v3_hippocampus_canonical_identity_v1.json"

AUDIT = D16 / "phase17_v3_bnst_canonical_entity_audit.json"
XWALK = D16 / "phase17_v3_bnst_terminology_crosswalk.csv"
GRAN = D16 / "phase17_v3_bnst_granularity_decision.json"
ROLL = D16 / "phase17_v3_bnst_g1_rollup_decision.json"
ADM = D16 / "phase17_v3_bnst_canonical_admission_v1.json"
PROP = D16 / "phase17_v3_bnst_canonical_region_proposal_v1.json"
MD = D16 / "phase17_v3_bnst_canonical_admission_diagnostics.md"
HAS = all(p.exists() for p in (AUDIT, XWALK, GRAN, ROLL, ADM, PROP))


def _j(p):
    return json.load(open(p, encoding="utf-8"))


def _rows(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _git_clean(*paths: Path) -> bool:
    r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *[str(p) for p in paths]],
                       cwd=BACKEND.parent, capture_output=True)
    return r.returncode == 0


def _macro96_bst():
    pat = ("bst", "bed nucleus", "stria terminalis", "bnst")
    n = 0
    for r in csv.DictReader(open(MACRO96, encoding="utf-8-sig")):
        blob = " ".join(str(v).lower() for v in r.values())
        if any(k in blob for k in pat):
            n += 1
    return n


# ---- 1. Macro96 BNST count = 0 ----
def test_1_macro96_bnst_zero():
    assert _macro96_bst() == 0
    assert _j(AUDIT)["macro96_pool"]["count_bnst"] == 0


# ---- 2. existing canonical BNST count = 0 ----
def test_2_canonical_count_zero():
    a = _j(AUDIT)
    assert a["canonical_brainregions"]["count_bnst"] == 0


# ---- 3. existing canonical NGIQ-BR BNST ids = 0 ----
def test_3_canonical_ngiq_zero():
    a = _j(AUDIT)
    assert a["canonical_ngiq_br_ids"]["count_bnst"] == 0
    # the two Julich G4 candidates are documented as candidate-layer only
    assert a["julich_g4_candidate_rows"]["count"] == 2
    ids = {c["source_entity_id"] for c in a["julich_g4_candidate_rows"]["rows"]}
    assert ids == {"NGIQ-BR-00000343", "NGIQ-BR-00000344"}


# ---- 4. external manifest label not a canonical entity ----
def test_4_manifest_label_not_canonical():
    a = _j(AUDIT)
    lab = a["external_manifest_label"]
    assert lab["semantic"] == "ASSET_TARGET_LABEL_WITHOUT_CANONICAL_ENTITY"
    assert lab["stale"] == "SEMANTIC_LABEL_STALE_NOT_CANONICAL_G1"


# ---- 5. human admission evidence complete ----
def test_5_human_evidence():
    ad = _j(ADM)
    assert ad["verdict"] == "ADMIT_AS_CANONICAL_BRAINREGION"
    srcs = " ".join(e["source"].lower() for e in ad["human_evidence"])
    assert "blackford" in srcs and "human" in srcs


# ---- 6. terminology resolved ----
def test_6_terminology_resolved():
    rows = _rows(XWALK)
    assert any(r["term"] == "BST" and r["verdict"] == "SAME_CANONICAL_STRUCTURE" for r in rows)
    assert any(r["term"] == "BNST" and r["verdict"] == "SAME_CANONICAL_STRUCTURE" for r in rows)


# ---- 7. whole BNST scope resolved ----
def test_7_whole_scope():
    ad = _j(ADM)
    assert "WHOLE_BNST_COMPLEX" in ad["structure"] or "whole" in ad["structure"]
    for e in _j(PROP)["proposal_entities"]:
        assert e["whole_subdivision_scope"] == "WHOLE_BNST_COMPLEX"


# ---- 8. laterality convention resolved ----
def test_8_laterality():
    p = _j(PROP)
    assert p["laterality"] == "LATERALIZED_CANONICAL_ENTITIES_REQUIRED"
    assert [e["proposal_entity_id"] for e in p["proposal_entities"]] == \
        ["PROP-BNST-L-V1", "PROP-BNST-R-V1"]


# ---- 9. granularity explicit ----
def test_9_granularity_explicit():
    g = _j(GRAN)
    assert g["verdict"] == "NON_G1_CANONICAL_BRAINREGION"
    assert g["existing_granularity_code"] == "subregion"
    assert "(L3)" in g["existing_granularity_class"]


# ---- 10/11. no invented G2 / no fabricated G1 ----
def test_10_11_no_invented_granularity():
    g = _j(GRAN)
    assert g["invented_G2"] is False
    assert g["fabricated_G1"] is False


# ---- 12. G1 roll-up explicit ----
def test_12_rollup_explicit():
    r = _j(ROLL)
    assert r["decision_id"] == "BNST_G1_ROLLUP_DECISION_V1"
    assert r["verdict"] == "G1_ROLLUP_UNRESOLVED"
    assert "Basal Forebrain" in r["plausible_macro96_parent"]


# ---- 13/14. no forced parents ----
def test_13_14_no_forced_parents():
    r = _j(ROLL)
    for k in ("BasalForebrain", "Amygdala", "NucleusAccumbens", "Thalamus"):
        assert k in r["rejected_forced_parents"], k
    assert r["macro96_parent"] is None


# ---- 15. admission explicit ----
def test_15_admission_explicit():
    ad = _j(ADM)
    assert ad["admission_id"] == "BNST_CANONICAL_ENTITY_ADMISSION_V1"
    assert ad["verdict"] == "ADMIT_AS_CANONICAL_BRAINREGION"


# ---- 16/17. ID allocation follows repo policy / no guessed id ----
def test_16_17_id_policy():
    p = _j(PROP)
    assert p["canonical_id_status"] == "PENDING_CANONICAL_ALLOCATION"
    assert p["canonical_ids"]["left"] == "PENDING_CANONICAL_ALLOCATION"
    assert p["canonical_ids"]["right"] == "PENDING_CANONICAL_ALLOCATION"
    assert "no max+1" in p["id_allocation_policy_note"]
    assert p["proposal_id_policy_note"]
    assert p["status"] == "PROPOSED_CANONICAL"
    assert p["not_active_not_promoted"] is True


# ---- 18/19. no geometry construction / no NIfTI generation ----
def test_18_19_no_geometry_no_nifti():
    p = _j(PROP)
    assert p["geometry_construction"] == "NOT_STARTED"
    # this round must not create derived BNST geometry
    assert not (DERIVED / "left_bnst_prob_icbm2009csym.nii.gz").exists()
    assert not (DERIVED / "left_bnst_prob_mni2009casym.nii.gz").exists()
    # no transform/spatial artifacts produced by this round
    names = {Path(p).name for p in D16.glob("phase17_v3_bnst_*.json")}
    assert "phase17_v3_bnst_spatial_route_manifest.json" not in names
    assert "phase17_v3_bnst_g1_reference_geometry_manifest.json" not in names


# ---- 20. DB zero-write ----
def test_20_db_zero_write():
    # no DB artifact exists; proposal states DB-layer allocation is pending
    assert _j(PROP)["canonical_id_status"] == "PENDING_CANONICAL_ALLOCATION"


# ---- 21. classification unchanged ----
def test_21_classification_unchanged():
    assert _git_clean(CLASS)
    rows = list(csv.DictReader(open(CLASS, encoding="utf-8-sig")))
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert sum(c.values()) - c["VERIFIED_DIRECT_CONTAINED"] == 132
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


# ---- 22. prior frozen families unchanged ----
def test_22_prior_frozen_unchanged():
    assert _git_clean(THAL, AMYG, HIPP)


# ---- 23. provenance complete ----
def test_23_provenance():
    a = _j(AUDIT)
    p = _j(PROP)
    assert a["macro96_pool"]["count_bnst"] == 0
    assert p["human_authority_sources"]
    assert p["blackford_relation"]["relation"].startswith("SUPPORTS_GEOMETRY_FOR")
    assert p["blackford_relation"]["geometry_authority_available"] is True
    md = MD.read_text(encoding="utf-8")
    assert "ADMIT_AS_CANONICAL_BRAINREGION" in md
    assert "no forced relation created" in md or "no forced part_of" in md.lower()


# ---- additional structural checks ----
def test_no_ngiq_id_in_proposal():
    p = _j(PROP)
    for e in p["proposal_entities"]:
        assert e["proposal_entity_id"].startswith("PROP-BNST-")
        assert not e["proposal_entity_id"].startswith("NGIQ-BR-")


def test_audit_files_present():
    assert HAS
    for f in (AUDIT, XWALK, GRAN, ROLL, ADM, PROP, MD):
        assert f.exists(), f


def test_candidate_rows_untouched():
    # Julich G4 BST candidates remain LIKELY + CONFLICT_REVIEW (not modified)
    rows = {r["source_entity_id"]: r for r in
            csv.DictReader(open(CLASS, encoding="utf-8-sig"))}
    for cid in ("NGIQ-BR-00000343", "NGIQ-BR-00000344"):
        r = rows[cid]
        assert r["v3_classification"] == "LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"
        assert r["frozen_decision"] == "CONFLICT_REVIEW"
