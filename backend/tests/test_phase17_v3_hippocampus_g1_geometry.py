"""Phase1.7 V3 - Hippocampus G1 canonical scope adjudication + reference geometry tests.

Validates the canonical identity, structure membership, source-channel semantics,
scope contract, native + reference-grid geometry manifests/QC, spatial bridge and
provenance against the 40 hard gates. Read-only; no DB write / classification change
/ promotion / commit. NIfTI-dependent tests skip in a clean repo.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
HIPPO = BACKEND / "data" / "atlases" / "external_raw" / "freesurfer_icbm2009c" / "hippocampus"
DERIVED = BACKEND / "data" / "atlases" / "derived_g1"
JUL = BACKEND / "data" / "atlases" / "julich" / "v3.1" / "spatial_raw" / "probability_maps" / "ACBL_VENTRAL_STRIATUM_LATERAL_ACCUMBENS_LEFT.nii.gz"

RAW_L = HIPPO / "HippoAmygProbs.MNIsymSpace.left.nii.gz"
RAW_R = HIPPO / "HippoAmygProbs.MNIsymSpace.right.nii.gz"
RAW_L_SHA = "a79d5f88acfa21684a6f8c1e78da21e74ccbf152e68fb845fde048f451c4474e"
RAW_R_SHA = "4d20bb95435afc9a139279ae2a159d8dfbf3f1b1de0d07d901ff6cf08570e5a3"
LEFT_G1, RIGHT_G1 = "NGIQ-BR-00000252", "NGIQ-BR-00000260"
CLASS = D16 / "phase17_v3_classification.csv"
THAL_FILES = [D16 / f for f in (
    "phase17_v3_thalamus_bn_direct_spatial_decisions.csv",
    "phase17_v3_thalamus_final_freeze_v1.json",
    "phase17_v3_thalamus_l8_2_discrepancy_summary.json")]
AMYG_FILES = [D16 / f for f in (
    "phase17_v3_amygdala_g1_scope_contract_v1.json",
    "phase17_v3_amygdala_g1_reference_geometry_manifest.json",
    "phase17_v3_amygdala_geometry_provenance.json")]
INCLUDE_LABELS = {226, 238, 237, 245, 246, 243, 240, 244, 241, 242, 239}
AMYG_LABELS = {7001, 7003, 7008, 7010, 7005, 7006, 7007, 7009, 7015}

IDENT = D16 / "phase17_v3_hippocampus_canonical_identity_v1.json"
CH = D16 / "phase17_v3_hippocampus_source_channel_semantics.csv"
SCOPE = D16 / "phase17_v3_hippocampus_g1_scope_contract_v1.json"
NMAN = D16 / "phase17_v3_hippocampus_g1_native_geometry_manifest.json"
NQC = D16 / "phase17_v3_hippocampus_g1_native_geometry_qc.csv"
BRIDGE = D16 / "phase17_v3_hippocampus_spatial_bridge_manifest.json"
RMAN = D16 / "phase17_v3_hippocampus_g1_reference_geometry_manifest.json"
RQC = D16 / "phase17_v3_hippocampus_g1_reference_geometry_qc.csv"
PROV = D16 / "phase17_v3_hippocampus_geometry_provenance.json"
MD = D16 / "phase17_v3_hippocampus_g1_geometry_diagnostics.md"
NAT_L = DERIVED / "left_hippocampus_prob_icbm2009csym.nii.gz"
NAT_R = DERIVED / "right_hippocampus_prob_icbm2009csym.nii.gz"
REF_L = DERIVED / "left_hippocampus_prob_mni2009casym.nii.gz"
REF_R = DERIVED / "right_hippocampus_prob_mni2009casym.nii.gz"
_HAS_NIFTI = all(p.exists() for p in (REF_L, REF_R, NAT_L, NAT_R))


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _j(p):
    return json.load(open(p, encoding="utf-8"))


def _rows(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _git_clean(*paths: Path) -> bool:
    r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *[str(p) for p in paths]],
                       cwd=BACKEND.parent, capture_output=True)
    return r.returncode == 0


# ---- 1/2. canonical IDs from real repository + source label/definition separated ----
def test_1_2_canonical_ids_and_source_label():
    i = _j(IDENT)
    assert i["canonical_left"]["canonical_region_id"] == LEFT_G1
    assert i["canonical_right"]["canonical_region_id"] == RIGHT_G1
    assert i["source_label"] == "Hippocampus / 海马 (Macro96)"
    assert i["source_has_formal_definition"] is False
    assert i["source_definition_state"] == "SOURCE_LABEL_ONLY_NO_FORMAL_DEFINITION"


# ---- 3/4. identity verdict + proper-vs-formation adjudicated ----
def test_3_4_identity_verdict():
    i = _j(IDENT)
    assert i["verdict"] == "HIPPOCAMPUS_BROAD_OPERATIONAL"
    d = i["proper_vs_formation_adjudication"]["decision"]
    assert "HIPPOCAMPAL_FORMATION was NOT adopted merely to widen coverage" in d
    assert "CA fields" in d and "dentate gyrus" in d


# ---- 5. CA1/CA2/CA3/DG consistent with frozen history ----
def test_5_ca_dg_frozen_consistent():
    i = _j(IDENT)
    assert i["history_conflict_check"]["conflict"] is False
    assert sorted(i["frozen_relations"]["verified_in_g1"]) == ["CA1", "CA2", "CA3", "DG"]
    assert i["frozen_relations"]["verified_count"] == 8
    # every VERIFIED CA/DG has g1_membership INCLUDE in the structure table
    tbl = {r["structure"]: r for r in i["structure_membership"]}
    for key in ("CA1", "CA2", "CA3", "CA4", "Dentate Gyrus (GC/ML-DG)"):
        assert tbl[key]["g1_membership"] == "INCLUDE"


# ---- 6-11. subicular family + HATA explicit decisions ----
def test_6_11_subicular_and_hata_decisions():
    i = _j(IDENT)
    tbl = {r["structure"]: r for r in i["structure_membership"]}
    assert tbl["Subiculum"]["g1_membership"] == "EXCLUDE"
    assert tbl["Presubiculum"]["g1_membership"] == "EXCLUDE"
    assert tbl["Parasubiculum"]["g1_membership"] == "EXCLUDE"
    assert tbl["Prosubiculum"]["g1_membership"] == "EXCLUDE"
    assert tbl["Transsubiculum"]["g1_membership"] == "EXCLUDE"
    assert tbl["HATA"]["g1_membership"] == "EXCLUDE"
    assert "definition-dependent" in tbl["Subiculum"]["reason"].lower()
    # subicular terms are hippocampal-formation members but not this-G1 members
    for s in ("Subiculum", "Presubiculum", "Parasubiculum"):
        assert tbl[s]["in_hippocampal_formation"] is True
        assert tbl[s]["in_hippocampus_proper"] is False


# ---- 12. no atlas-coverage-driven ontology inflation ----
def test_12_no_atlas_coverage_driven_inflation():
    i = _j(IDENT)
    assert i["ontology_vs_coverage_note"]
    assert _j(PROV)["no_atlas_coverage_driven_ontology_inflation"] is True


# ---- 13. raw SHA fixed ----
def test_13_raw_sha():
    assert _j(SCOPE)["source"]["left_sha256"] == RAW_L_SHA
    assert _j(PROV)["raw_source"]["right_sha256"] == RAW_R_SHA
    if RAW_L.exists():
        assert _sha(RAW_L) == RAW_L_SHA


# ---- 14. channel metadata authority complete ----
def test_14_channel_metadata():
    rows = _rows(CH)
    assert len(rows) == 30
    assert any(r["official_name"] == "CA1-head" for r in rows)


# ---- 15/16. semantics resolved + SUM operator math ----
def test_15_16_semantics_sum():
    s = _j(SCOPE)
    assert s["source"]["probability_semantics"]["left"] == "MUTUALLY_EXCLUSIVE_CATEGORICAL"
    assert s["source"]["probability_semantics"]["operator"] == "SUM"
    assert _j(NMAN)["probability_semantics"] == "MUTUALLY_EXCLUSIVE_CATEGORICAL"
    assert _j(NMAN)["aggregation_operator"] == "SUM"


# ---- 17. Amygdala channels never enter Hippocampus geometry ----
def test_17_amygdala_excluded():
    rows = _rows(CH)
    amy = [r for r in rows if int(r["numeric_label"]) in AMYG_LABELS]
    assert len(amy) == 9
    assert all(r["geometry_scope_decision"] == "EXCLUDE" for r in amy)
    # only a small soft-boundary residual of the categorical posterior is present
    # at the amygdala<->hippocampus interface (documented; not a scope leak)
    for r in _rows(NQC):
        assert float(r["amygdala_contamination_fraction"]) < 0.02


# ---- 18. scope FROZEN before geometry ----
def test_18_scope_frozen():
    s = _j(SCOPE)
    assert s["scope_verdict"] == "HIPPOCAMPUS_G1_SCOPE_FROZEN"
    assert s["geometry_allowed"] is True
    assert s["canonical_identity"] == "HIPPOCAMPUS_BROAD_OPERATIONAL"


# ---- 19/20. native laterality source-native + no world-X ----
def test_19_20_laterality_no_world_x():
    s = _j(SCOPE)
    assert s["no_world_x_split"] is True
    assert "source-native left/right" in s["laterality_authority"]
    assert _j(NMAN)["entries"][0]["hemisphere"] == "left"
    assert _j(NMAN)["entries"][1]["hemisphere"] == "right"


# ---- 21. native SHA recorded ----
def test_21_native_sha():
    n = _j(NMAN)
    for e in n["entries"]:
        assert len(e["output_sha256"]) == 64
        p = NAT_L if e["hemisphere"] == "left" else NAT_R
        if p.exists():
            assert _sha(p) == e["output_sha256"]


# ---- 22. shared-frame compatibility PASS ----
def test_22_shared_frame():
    b = _j(BRIDGE)
    for side in ("left", "right"):
        assert b["source_compatibility"][side]["shared_frame_compatible"] is True


# ---- 23-28. no nonlinear reg / LINEAR / no ops ----
def test_23_28_no_reg_no_ops():
    r = _j(RMAN)
    assert r["registration_applied"] is False
    assert r["nonlinear_registration_applied"] is False
    assert r["resampling_applied"] is True
    assert r["interpolation"] == "LINEAR"
    for e in r["entries"]:
        for flag in ("threshold_applied", "binarization_applied", "clipping_applied",
                     "normalization_applied"):
            assert e[flag] is False, flag
        assert e["no_artificial_symmetrization"] is True


# ---- 29/30. target grid + affine exact ----
@pytest.mark.skipif(not (_HAS_NIFTI and JUL.exists()), reason="NIfTI absent")
def test_29_30_target_grid():
    import nibabel as nib
    import numpy as np
    ref = nib.load(str(JUL))
    assert tuple(ref.shape) == (193, 229, 193)
    for p in (REF_L, REF_R):
        img = nib.load(str(p))
        assert tuple(img.shape) == (193, 229, 193)
        assert np.allclose(np.asarray(img.affine), np.asarray(ref.affine), atol=1e-4)


# ---- 31. reference SHA recorded ----
def test_31_reference_sha():
    r = _j(RMAN)
    for e in r["entries"]:
        assert len(e["output_sha256"]) == 64
        p = REF_L if e["hemisphere"] == "left" else REF_R
        if p.exists():
            assert _sha(p) == e["output_sha256"]


# ---- 32. template-variant uncertainty retained ----
def test_32_template_limitation():
    r = _j(RMAN)
    assert r["template_variant_uncertainty"] == "PRESENT"
    assert "TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_WARP_CORRECTED" in \
        r["residual_spatial_limitation"]


# ---- 33/34. direct_overlap flags ----
def test_33_34_direct_overlap():
    r = _j(RMAN)
    for e in r["entries"]:
        assert e["direct_overlap_grid_ready"] is True
        assert e["direct_validation_executed"] is False
    assert r["direct_overlap_grid_ready"] is True and r["direct_validation_executed"] is False


# ---- 35. provenance complete ----
def test_35_provenance():
    p = _j(PROV)
    assert p["canonical_identity"]["verdict"] == "HIPPOCAMPUS_BROAD_OPERATIONAL"
    assert p["raw_source"]["left_sha256"] == RAW_L_SHA
    assert p["scope_contract"]["verdict"] == "HIPPOCAMPUS_G1_SCOPE_FROZEN"
    assert p["native_geometry"]["left_sha256"]
    assert p["spatial_bridge"]["spatial_bridge_id"] == "SPB-MNI2009C-SYM-ASYM-SHARED-FRAME-V1"
    assert p["reference_geometry"]["manifest_sha256"]
    assert p["julich_reference"]["sha256"]
    assert p["independent_from_g3_g1_mapping"] is True
    assert p["circularity_risk"] == "NONE"


# ---- 36/37/38. classification / DB / promotion ----
def test_36_classification_unchanged():
    assert _git_clean(CLASS)
    rows = list(csv.DictReader(open(CLASS, encoding="utf-8-sig")))
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert sum(c.values()) - c["VERIFIED_DIRECT_CONTAINED"] == 132
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


def test_37_db_zero_write():
    assert _j(PROV)["db_write"] is False


def test_38_no_promotion():
    assert _j(PROV)["promotion"] is False


# ---- 39. Thalamus + Amygdala frozen chains unchanged ----
def test_39_prior_frozen_unchanged():
    assert _git_clean(*THAL_FILES, *AMYG_FILES)


# ---- 40. identity file + structure table presence ----
def test_40_identity_file_and_structure():
    i = _j(IDENT)
    assert i["identity_id"] == "HIPPOCAMPUS_G1_CANONICAL_IDENTITY_V1"
    assert len(i["structure_membership"]) >= 16


# ---- additional structural checks ----
def test_conservation_zero_and_amyg_contamination_bounded():
    for r in _rows(NQC):
        assert float(r["max_abs_conservation_residual"]) == 0.0
        assert float(r["amygdala_contamination_fraction"]) < 0.02


def test_native_qc_both_sides():
    rows = {r["hemisphere"]: r for r in _rows(NQC)}
    assert set(rows) == {"left", "right"}


def test_reference_qc_both_sides_grid():
    rows = {r["hemisphere"]: r for r in _rows(RQC)}
    assert set(rows) == {"left", "right"}
    for r in rows.values():
        assert r["shape"] == "193x229x193"
        assert r["direct_validation_executed"] == "False"


@pytest.mark.skipif(not _HAS_NIFTI, reason="NIfTI absent")
def test_native_centroid_in_hippocampus():
    import nibabel as nib
    import numpy as np
    for side, p, exp in (("left", NAT_L, -1), ("right", NAT_R, 1)):
        img = nib.load(str(p))
        vol = np.asanyarray(img.dataobj).astype(np.float64)
        X = np.arange(vol.shape[0])
        xw = np.asarray(img.affine, float)[0, 0] * X + np.asarray(img.affine, float)[0, 3]
        cx = (vol * xw.reshape(-1, 1, 1)).sum() / vol.sum()
        # hippocampus body ~ x 18-30 mm from midline
        assert cx * exp > 15, (side, cx)


def test_md_preserves_scoping_wording():
    txt = MD.read_text(encoding="utf-8")
    assert "HIPPOCAMPUS_BROAD_OPERATIONAL" in txt
    assert "not full hippocampal formation" in txt or "NOT full hippocampal formation" in txt
