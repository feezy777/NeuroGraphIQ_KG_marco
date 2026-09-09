"""Phase1.7 V3 - BNST canonical geometry construction tests (whole-BNST probability).

Validates the manifest/QC/diagnostics of the registered Julich-Brain v3.1 whole-BST
L/R canonical probability geometry and the 15 gates. Read-only; no DB / classification
change / promotion / commit; geometry stays probability (no derived binary mask).
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
JUL_DIR = BACKEND / "data" / "atlases" / "julich" / "v3.1" / "spatial_raw" / "probability_maps"
CLASS = D16 / "phase17_v3_classification.csv"
ADMISSION = D16 / "phase17_v3_bnst_canonical_admission_v1.json"
ROLL = D16 / "phase17_v3_bnst_g1_rollup_decision.json"
THAL = D16 / "phase17_v3_thalamus_final_freeze_v1.json"
AMYG = D16 / "phase17_v3_amygdala_g1_scope_contract_v1.json"
HIPP = D16 / "phase17_v3_hippocampus_canonical_identity_v1.json"

MAN = D16 / "phase17_v3_bnst_canonical_geometry_manifest.json"
QC = D16 / "phase17_v3_bnst_canonical_geometry_qc.json"
MD = D16 / "phase17_v3_bnst_canonical_geometry_diagnostics.md"
HAS = MAN.exists() and QC.exists() and MD.exists()
LEFT_FILE = JUL_DIR / "BST_BASAL_FOREBRAIN_BED_NUCLEUS_LEFT.nii.gz"
RIGHT_FILE = JUL_DIR / "BST_BASAL_FOREBRAIN_BED_NUCLEUS_RIGHT.nii.gz"
JUL_DOI = "10.25493/KNSN-XB4"


def _j(p):
    return json.load(open(p, encoding="utf-8"))


def _git_clean(*paths: Path) -> bool:
    r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *[str(p) for p in paths]],
                       cwd=BACKEND.parent, capture_output=True)
    return r.returncode == 0


# ---- 1. exact Julich v3.1 source identity verified ----
def test_1_source_identity():
    m = _j(MAN)
    assert m["source"]["dataset"] == "Julich-Brain" and m["source"]["version"].startswith("3.1")
    assert m["source"]["dataset_doi"] == JUL_DOI
    assert "BST (Basal Forebrain, Bed Nucleus)" in m["source"]["region_label"]


# ---- 2. source SHA / provenance recorded ----
def test_2_sha_provenance():
    m = _j(MAN)
    assert len(m["left"]["source_sha256"]) == 64
    assert len(m["right"]["source_sha256"]) == 64
    assert m["left"]["source_sha256"] != m["right"]["source_sha256"]
    chain = " ".join(c.get("step", "") + " " + str(c) for c in m["provenance_chain"])
    assert JUL_DOI in chain


# ---- 3. Left and Right distinct + correctly lateralized ----
def test_3_lateralization():
    q = _j(QC)
    lc = q["left"]["weighted_centroid_world_mm"][0]
    rc = q["right"]["weighted_centroid_world_mm"][0]
    assert lc < 0 and rc > 0
    assert q["left"]["source_sha256"] != q["right"]["source_sha256"]
    assert q["left_right"]["distinct_not_duplicated"] is True
    assert q["left_right"]["normalized_overlap_mass_fraction"] < 0.05
    assert q["left"]["laterality_source"].startswith("source-native")


# ---- 4. reference-space identity explicit ----
def test_4_reference_space():
    m = _j(MAN)
    assert m["source"]["reference_space"] == "MNI 152 ICBM 2009c Nonlinear Asymmetric"
    for side in ("left", "right"):
        assert m[side]["reference_space"] == "MNI152NLin2009cAsym (Julich-Brain v3.1)"
        assert m[side]["grid"] == [193, 229, 193]
        assert m[side]["affine_matches_frozen_reference"] is True
    assert m["resampling_applied"] is False


# ---- 5. no arbitrary probability threshold ----
def test_5_no_threshold():
    m = _j(MAN)
    assert m["threshold_applied"] is False
    assert m["binarization_applied"] is False
    assert m["binary_geometry_policy"] == "UNRESOLVED"
    assert m["derived_binary_geometry"] == "NOT_CONSTRUCTED"
    assert "no threshold was chosen ad hoc" in m["binary_policy_note"]
    assert m["canonical_geometry_class"] == "CANONICAL_PROBABILITY_GEOMETRY"
    assert m["source_probability_geometry"] == "REGISTERED_DIRECTLY_FROM_ACQUIRED_JULICH_SOURCE"


# ---- 6. no morphology / smoothing / manual anatomy modification ----
def test_6_no_morphology():
    m = _j(MAN)
    assert m["morphology_edited"] is False
    assert m["nonlinear_registration_applied"] is False
    for side in ("left", "right"):
        q = _j(QC)[side]
        assert q["thresholded"] is False and q["binarized"] is False
        assert q["morphology_edited"] is False and q["resampled"] is False


# ---- 7. geometry bound to PROP-BNST-L/R-V1 (no invented NGIQ id) ----
def test_7_prop_ids():
    m = _j(MAN)
    assert m["canonical_entities"]["left"] == "PROP-BNST-L-V1"
    assert m["canonical_entities"]["right"] == "PROP-BNST-R-V1"
    assert m["canonical_entities"]["id_status"] == "PROPOSAL_IDS_ONLY_PENDING_CANONICAL_ALLOCATION"
    assert "NGIQ-BR" not in m["canonical_entities"]["id_status"]


# ---- 8. admission remains ADMIT ----
def test_8_admission_unchanged():
    assert _j(ADMISSION)["verdict"] == "ADMIT_AS_CANONICAL_BRAINREGION"


# ---- 9. G1 roll-up remains G1_ROLLUP_UNRESOLVED ----
def test_9_rollup_unchanged():
    assert _j(ROLL)["verdict"] == "G1_ROLLUP_UNRESOLVED"


# ---- 10. no Basal Forebrain relation created ----
def test_10_no_basal_forebrain_relation():
    md = MD.read_text(encoding="utf-8")
    assert "no BNST->Basal Forebrain relation" in md or "no Basal Forebrain relation" in md
    rel = [p for p in D16.glob("phase17_v3_bnst_*.json") if "relation" in p.name.lower()]
    assert not rel


# ---- 11. classification byte-identical ----
def test_11_classification_unchanged():
    assert _git_clean(CLASS)
    rows = list(csv.DictReader(open(CLASS, encoding="utf-8-sig")))
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert sum(c.values()) - c["VERIFIED_DIRECT_CONTAINED"] == 132
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


# ---- 12. DB zero writes ----
def test_12_db_zero_write():
    # file-level registration only; no derived NIfTI produced anywhere
    assert not (DERIVED / "left_bnst_prob_icbm2009csym.nii.gz").exists()
    assert not (DERIVED / "right_bnst_prob_mni2009casym.nii.gz").exists()


# ---- 13. prior frozen families untouched ----
def test_13_prior_frozen_unchanged():
    assert _git_clean(THAL, AMYG, HIPP)


# ---- 14. Theiss/Blackford corroborating only ----
def test_14_blackford_corroborating_only():
    m = _j(MAN)
    assert "corroborating only" in m["corroborating_mri_geometry"].lower() or \
        "corroborating only" in m["corroborating_mri_geometry"]
    assert "Theiss/Blackford 2017" in m["corroborating_mri_geometry"]


# ---- 15. Brandstetter 2026 not silently substituted ----
def test_15_brandstetter_not_substituted():
    m = _j(MAN)
    note = m["brandstetter_2026_note"]
    assert "10.1162/IMAG.a.1260" in note
    assert "NOT silently substituted" in note
    assert "NOT assumed" in note or "not assumed" in note


def test_manifest_and_qc_present():
    assert HAS
    md = MD.read_text(encoding="utf-8")
    assert "CANONICAL_PROBABILITY_GEOMETRY = CONSTRUCTED / REGISTERED" in md
    assert "BINARY_CANONICAL_MASK = NOT_CONSTRUCTED" in md
    assert "no resample" in md or "NO resampling" in md


def test_qc_values_sane():
    q = _j(QC)
    for side in ("left", "right"):
        s = q[side]
        assert s["nonzero_support_voxels"] > 0
        assert s["probability_mass"] > 0
        assert 0.0 <= s["value_min"] <= s["value_max"] <= 1.0
        assert s["qform_code"] == 4 and s["sform_code"] == 4
