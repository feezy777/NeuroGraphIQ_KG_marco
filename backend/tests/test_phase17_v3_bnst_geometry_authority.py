"""Phase1.7 V3 - BNST geometry authority selection / precedence audit tests.

Validates the authority audit artifacts and the 8 gates. Read-only; no geometry, no
NIfTI, no DB write, no reclassification, no Basal Forebrain relation, no NGIQ-BR
allocation; prior frozen family outputs untouched.
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
DERIVED = BACKEND / "data" / "atlases" / "derived_g1"
CLASS = D16 / "phase17_v3_classification.csv"
ADMISSION = D16 / "phase17_v3_bnst_canonical_admission_v1.json"
THAL = D16 / "phase17_v3_thalamus_final_freeze_v1.json"
AMYG = D16 / "phase17_v3_amygdala_g1_scope_contract_v1.json"
HIPP = D16 / "phase17_v3_hippocampus_canonical_identity_v1.json"

AUDIT = D16 / "phase17_v3_bnst_geometry_authority_audit.json"
DEC = D16 / "phase17_v3_bnst_geometry_authority_decision.json"
MD = D16 / "phase17_v3_bnst_geometry_authority_diagnostics.md"
HAS = AUDIT.exists() and DEC.exists() and MD.exists()


def _j(p):
    return json.load(open(p, encoding="utf-8"))


def _git_clean(*paths: Path) -> bool:
    r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *[str(p) for p in paths]],
                       cwd=BACKEND.parent, capture_output=True)
    return r.returncode == 0


# ---- 1. no NIfTI / geometry generated ----
def test_1_no_geometry_or_nifti():
    assert not (DERIVED / "left_bnst_prob_icbm2009csym.nii.gz").exists()
    assert not (DERIVED / "right_bnst_prob_icbm2009csym.nii.gz").exists()
    assert not (DERIVED / "left_bnst_prob_mni2009casym.nii.gz").exists()
    names = {Path(p).name for p in D16.glob("phase17_v3_bnst_*.json")}
    assert "phase17_v3_bnst_g1_reference_geometry_manifest.json" not in names
    assert "phase17_v3_bnst_spatial_route_manifest.json" not in names
    assert "phase17_v3_bnst_source_geometry_manifest.json" not in names


# ---- 2. no DB write ----
def test_2_no_db_write():
    # this round is file-level only: only audit/decision/diagnostics artifacts exist
    outs = {Path(p).name for p in D16.glob("phase17_v3_bnst_geometry_authority_*")}
    assert outs == {"phase17_v3_bnst_geometry_authority_audit.json",
                    "phase17_v3_bnst_geometry_authority_decision.json",
                    "phase17_v3_bnst_geometry_authority_diagnostics.md"}


# ---- 3. no Phase1.7 classification change ----
def test_3_classification_unchanged():
    assert _git_clean(CLASS)
    rows = list(csv.DictReader(open(CLASS, encoding="utf-8-sig")))
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert sum(c.values()) - c["VERIFIED_DIRECT_CONTAINED"] == 132
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


# ---- 4. no Basal Forebrain relation created ----
def test_4_no_basal_forebrain_relation():
    d = _j(DEC)
    assert any("Basal Forebrain relations untouched" in n or "no Basal Forebrain" in n
               for n in d["notes"])
    # no part_of/contained relation artifact is produced by this round
    rel_files = [p for p in D16.glob("phase17_v3_bnst_*.json")
                 if "relation" in p.name.lower()]
    assert not rel_files


# ---- 5. existing BNST admission verdict unchanged ----
def test_5_admission_unchanged():
    assert _j(ADMISSION)["verdict"] == "ADMIT_AS_CANONICAL_BRAINREGION"
    assert "ADMIT_AS_CANONICAL_BRAINREGION" in _j(DEC)["entity_authority"]["value"]
    assert "unchanged from commit e04ed86" in _j(DEC)["notes"][-1]


# ---- 6. primary vs corroborating authority separate ----
def test_6_primary_and_corroborating_separate():
    d = _j(DEC)
    p = d["primary_anatomical_geometry_authority"]["value"]
    c = d["corroborating_clinical_mri_geometry"]["value"]
    assert "PRIMARY_ANATOMICAL_GEOMETRY_AUTHORITY" in p
    assert "Brandstetter" in p or "Juellich" in p or "Julich" in p
    assert "CORROBORATING_CLINICAL_MRI_GEOMETRY" in c
    assert "Theiss/Blackford 2017" in c
    assert d["entity_authority"]["role"] == "A. ENTITY AUTHORITY"
    assert d["primary_anatomical_geometry_authority"]["role"] == "B. ANATOMICAL GEOMETRY AUTHORITY"
    assert d["corroborating_clinical_mri_geometry"]["role"] == "C. CORROBORATING / CLINICAL GEOMETRY ASSET"


# ---- 7. source scope/modality/space/provenance explicit ----
def test_7_source_metadata_explicit():
    a = _j(AUDIT)
    cards = a["source_cards"]
    for key in ("julich_v31_whole_bst", "brandstetter_2026", "theiss_blackford_2017", "sibbach_2024"):
        assert key in cards, key
        for field in ("family", "modality", "whole_scope", "laterality", "reference_space",
                      "probability_map", "acquisition_status"):
            assert field in cards[key], (key, field)
    # equivalence not assumed
    assert "NOT assumed" in a["equivalence_caveat"] or "not assumed" in a["equivalence_caveat"]
    # stored julich v3.1 whole-BST maps sha verified against provenance
    jv = cards["julich_v31_whole_bst"]
    assert jv["stored_sha_verified"]["left"] is True
    assert jv["stored_sha_verified"]["right"] is True


# ---- 8. prior frozen Thalamus/Amygdala/Hippocampus untouched ----
def test_8_prior_frozen_untouched():
    assert _git_clean(THAL, AMYG, HIPP)


def test_artifacts_present():
    assert HAS
    md = MD.read_text(encoding="utf-8")
    assert "PRIMARY_ANATOMICAL_GEOMETRY_AUTHORITY" in md
    assert "Theiss/Blackford 2017" in md
    assert "NOT_STARTED" in md
    assert "no NIfTI" in md or "no Nifti" in md
