"""Phase1.7 V3 - Amygdala G1 authoritative reference geometry construction tests.

Validates the scope contract, source-channel semantics, native + reference-grid
geometry manifests/QC, spatial bridge, provenance and 34 hard invariants. Read-only;
no DB write / classification change / promotion / commit. NIfTI-dependent tests skip
in a clean repo.
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
ACQ_SHA = "a79d5f88acfa21684a6f8c1e78da21e74ccbf152e68fb845fde048f451c4474e"
LEFT_G1, RIGHT_G1 = "NGIQ-BR-00000253", "NGIQ-BR-00000261"
CLASS = D16 / "phase17_v3_classification.csv"
V1 = D16 / "phase17_v3_thalamus_g1_scope_contract.json"
V2 = D16 / "phase17_v3_thalamus_g1_scope_contract_v2.json"
V3 = D16 / "phase17_v3_thalamus_g1_scope_contract_v3.json"
THAL_FREEZE = D16 / "phase17_v3_thalamus_final_freeze_v1.json"
THAL_FILES = [D16 / f for f in (
    "phase17_v3_thalamus_bn_direct_spatial_decisions.csv",
    "phase17_v3_thalamus_bn_direct_spatial_summary.json",
    "phase17_v3_thalamus_final_freeze_v1.json",
    "phase17_v3_thalamus_l8_2_discrepancy_summary.json",
)]

CH_SEM = D16 / "phase17_v3_amygdala_source_channel_semantics.csv"
SCOPE = D16 / "phase17_v3_amygdala_g1_scope_contract_v1.json"
NMAN = D16 / "phase17_v3_amygdala_g1_native_geometry_manifest.json"
NQC = D16 / "phase17_v3_amygdala_g1_native_geometry_qc.csv"
BRIDGE = D16 / "phase17_v3_amygdala_spatial_bridge_manifest.json"
RMAN = D16 / "phase17_v3_amygdala_g1_reference_geometry_manifest.json"
RQC = D16 / "phase17_v3_amygdala_g1_reference_geometry_qc.csv"
PROV = D16 / "phase17_v3_amygdala_geometry_provenance.json"
MD = D16 / "phase17_v3_amygdala_g1_geometry_diagnostics.md"

NAT_L = DERIVED / "left_amygdala_prob_icbm2009csym.nii.gz"
NAT_R = DERIVED / "right_amygdala_prob_icbm2009csym.nii.gz"
REF_L = DERIVED / "left_amygdala_prob_mni2009casym.nii.gz"
REF_R = DERIVED / "right_amygdala_prob_mni2009casym.nii.gz"
_HAS_NIFTI = all(p.exists() for p in (REF_L, REF_R, NAT_L, NAT_R))
AMYG_LABELS = {7001, 7003, 7008, 7010, 7005, 7006, 7007, 7009, 7015}


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


# ---- 1. canonical IDs from real canonical data ----
def test_1_canonical_ids():
    s = _j(SCOPE)
    assert s["canonical_left"]["canonical_region_id"] == LEFT_G1
    assert s["canonical_right"]["canonical_region_id"] == RIGHT_G1
    assert s["canonical_identity_sources"]


# ---- 2. raw L/R SHA consistent with acquisition freeze ----
def test_2_raw_sha():
    s = _j(SCOPE)["source"]
    assert s["left_sha256"] == RAW_L_SHA and s["right_sha256"] == RAW_R_SHA
    assert _j(PROV)["raw_source"]["acquisition_recorded_sha256"] == ACQ_SHA
    if RAW_L.exists():
        assert _sha(RAW_L) == RAW_L_SHA
    if RAW_R.exists():
        assert _sha(RAW_R) == RAW_R_SHA


# ---- 3. raw channel count from file ----
@pytest.mark.skipif(not (RAW_L.exists() and RAW_R.exists()), reason="raw absent")
def test_3_channel_count_from_file():
    import nibabel as nib
    for side, p in (("left", RAW_L), ("right", RAW_R)):
        img = nib.load(str(p))
        assert len(img.shape) == 4 and img.shape[3] == 30
        assert img.shape[:3] == (164, 224, 196)
        zooms = img.header.get_zooms()
        assert all(abs(z - 0.25) < 1e-4 for z in zooms[:3])


# ---- 4. official channel metadata traceable ----
def test_4_channel_metadata():
    rows = _rows(CH_SEM)
    assert len(rows) == 30
    assert rows[0]["numeric_label"] == "0" and rows[0]["anatomical_family"] == "BACKGROUND"
    assert any(r["official_name"] == "Lateral-nucleus" for r in rows)


# ---- 5. Amygdala / Hippocampus channels clearly separated ----
def test_5_amyg_vs_hippocampus_separated():
    rows = _rows(CH_SEM)
    amyg = {int(r["numeric_label"]) for r in rows if r["anatomical_family"] == "AMYGDALA"}
    hipp = [r for r in rows if r["anatomical_family"] in ("HIPPOCAMPAL", "TRANSITION_HATA")]
    assert amyg == AMYG_LABELS
    assert len(hipp) == 20
    assert all(int(r["numeric_label"]) < 1000 for r in hipp)


# ---- 6. source-channel scope fully explicit ----
def test_6_scope_explicit():
    rows = _rows(CH_SEM)
    assert all(r["scope_decision"] in ("INCLUDE", "EXCLUDE") for r in rows)
    assert sum(1 for r in rows if r["scope_decision"] == "INCLUDE") == 9


# ---- 7. no unknown channel auto INCLUDE ----
def test_7_no_unknown_auto_include():
    rows = _rows(CH_SEM)
    for r in rows:
        if r["scope_decision"] == "INCLUDE":
            assert r["anatomical_family"] == "AMYGDALA"
            assert int(r["numeric_label"]) in AMYG_LABELS


# ---- 8. scope verdict FROZEN before geometry ----
def test_8_scope_frozen():
    s = _j(SCOPE)
    assert s["scope_verdict"] == "AMYGDALA_G1_SCOPE_FROZEN"
    assert s["geometry_allowed"] is True


# ---- 9/10. aggregation semantics verified + operator consistent ----
def test_9_10_semantics_and_operator():
    s = _j(SCOPE)
    for side in ("left", "right"):
        assert s["source"]["probability_semantics"][side] == "MUTUALLY_EXCLUSIVE_CATEGORICAL"
    assert s["source"]["probability_semantics"]["operator"] == "SUM"
    n = _j(NMAN)
    assert n["probability_semantics"] == "MUTUALLY_EXCLUSIVE_CATEGORICAL"
    assert n["aggregation_operator"] == "SUM"
    assert _j(PROV)["probability_semantics"]["operator"] == "SUM"


# ---- 11. no IF/MF-driven scope expansion ----
def test_11_no_if_mf_scope_expansion():
    s = _j(SCOPE)
    assert s["if_mf_isolation"]["statement"] == \
        "AMYGDALA_G1_GEOMETRY_CONSTRUCTION DOES_NOT_RESOLVE JULICH_IF_MF_ENTITY_TYPE_REVIEW"
    assert "no IF/MF-driven scope expansion" in s["if_mf_isolation"]["note"]


# ---- 12/13. native laterality authority + no world-X split ----
def test_12_13_laterality_no_world_x_split():
    s = _j(SCOPE)
    assert s["no_world_x_split"] is True
    assert "source-native left/right" in s["laterality_authority"]
    n = _j(NMAN)
    assert n["entries"][0]["hemisphere"] == "left"
    assert n["entries"][1]["hemisphere"] == "right"


# ---- 14. native geometry SHA recorded ----
def test_14_native_sha_recorded():
    n = _j(NMAN)
    for e in n["entries"]:
        assert len(e["output_sha256"]) == 64
        if e["hemisphere"] == "left" and NAT_L.exists():
            assert _sha(NAT_L) == e["output_sha256"]
        if e["hemisphere"] == "right" and NAT_R.exists():
            assert _sha(NAT_R) == e["output_sha256"]


# ---- 15. source grid preserved ----
def test_15_source_grid_preserved():
    n = _j(NMAN)
    for e in n["entries"]:
        assert e["output_grid"]["shape"] == [164, 224, 196]
        assert e["output_grid"]["spacing_mm"] == 0.25
        assert e["output_grid"]["qform_code"] == 1 and e["output_grid"]["sform_code"] == 1
        assert e["registration_applied"] is False and e["resampling_applied"] is False


# ---- 16. shared-frame compatibility independently checked ----
def test_16_shared_frame_compatible():
    b = _j(BRIDGE)
    assert b["spatial_bridge_statement"] == "SHARED_STEREOTAXIC_FRAME_REFERENCE_GRID_RESAMPLE"
    for side in ("left", "right"):
        assert b["source_compatibility"][side]["shared_frame_compatible"] is True
        assert b["source_compatibility"][side]["qform_code"] == 1


# ---- 17-22. no nonlinear reg / linear interp / no threshold/binarize/clip/renorm ----
def test_17_22_no_reg_no_ops():
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
    b = _j(BRIDGE)
    assert b["nonlinear_registration_applied"] is False
    assert b["resampling_applied"] is True


# ---- 23/24. target shape/affine ----
@pytest.mark.skipif(not (_HAS_NIFTI and JUL.exists()), reason="NIfTI absent")
def test_23_24_target_grid():
    import nibabel as nib
    import numpy as np
    ref = nib.load(str(JUL))
    assert tuple(ref.shape) == (193, 229, 193)
    for p in (REF_L, REF_R):
        img = nib.load(str(p))
        assert tuple(img.shape) == (193, 229, 193)
        assert np.allclose(np.asarray(img.affine), np.asarray(ref.affine), atol=1e-4)


# ---- 25. target geometry SHA recorded ----
def test_25_target_sha_recorded():
    r = _j(RMAN)
    for e in r["entries"]:
        assert len(e["output_sha256"]) == 64
        p = REF_L if e["hemisphere"] == "left" else REF_R
        if p.exists():
            assert _sha(p) == e["output_sha256"]


# ---- 26/27. template-variant limitation + direct_overlap flags ----
def test_26_27_template_limitation():
    r = _j(RMAN)
    assert r["template_variant_uncertainty"] == "PRESENT"
    assert "TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_WARP_CORRECTED" in \
        r["residual_spatial_limitation"]
    for e in r["entries"]:
        assert e["direct_overlap_grid_ready"] is True
        assert e["direct_validation_executed"] is False


# ---- 28. IF/MF review remains unresolved ----
def test_28_if_mf_remains_unresolved():
    assert _j(PROV)["if_mf_entity_type_review"].startswith("UNRESOLVED")
    md = MD.read_text(encoding="utf-8")
    assert "DOES_NOT_RESOLVE" in md or "NOT resolved" in md


# ---- 29-32. classification/DB/promotion/Thalamus untouched ----
def test_29_classification_unchanged():
    assert _git_clean(CLASS)
    rows = list(csv.DictReader(open(CLASS, encoding="utf-8-sig")))
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert sum(c.values()) - c["VERIFIED_DIRECT_CONTAINED"] == 132
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


def test_30_db_zero_write():
    assert _j(PROV)["db_write"] is False


def test_31_no_promotion():
    assert _j(PROV)["promotion"] is False


def test_32_thalamus_unchanged():
    assert _git_clean(*THAL_FILES, V1, V2, V3)
    assert THAL_FREEZE.exists()


# ---- 33/34. provenance complete + derived nifti untracked policy ----
def test_33_provenance_complete():
    p = _j(PROV)
    assert p["raw_source"]["left_sha256"] == RAW_L_SHA
    assert p["native_geometry"]["manifest_sha256"]
    assert p["spatial_bridge"]["spatial_bridge_id"] == "SPB-MNI2009C-SYM-ASYM-SHARED-FRAME-V1"
    assert p["reference_geometry"]["manifest_sha256"]
    assert p["reference_geometry"]["left_sha256"]
    assert p["julich_reference"]["sha256"]
    assert p["scope_contract"]["verdict"] == "AMYGDALA_G1_SCOPE_FROZEN"
    assert p["independent_from_g3_g1_mapping"] is True
    assert p["circularity_risk"] == "NONE"


def test_34_no_binary_in_outputs():
    # all tracked/committed outputs are textual; derived NIfTI are gitignored
    outs = [CH_SEM, SCOPE, NMAN, NQC, BRIDGE, RMAN, RQC, PROV, MD]
    for f in outs:
        assert f.exists()
        assert f.suffix in (".csv", ".json", ".md")


# ---- additional structural checks ----
def test_native_qc_contains_both_sides():
    rows = {r["hemisphere"]: r for r in _rows(NQC)}
    assert set(rows) == {"left", "right"}
    for r in rows.values():
        assert float(r["max_abs_conservation_residual"]) < 1e-3
        # hard-membership (argmax) contamination by hippocampal subfields is a small,
        # documented soft-boundary residual of the categorical posterior (not a leak)
        assert float(r["hippocampal_contamination_argmax_fraction"]) < 0.02


def test_reference_qc_contains_both_sides():
    rows = {r["hemisphere"]: r for r in _rows(RQC)}
    assert set(rows) == {"left", "right"}
    for r in rows.values():
        assert r["shape"] == "193x229x193"
        assert r["direct_overlap_grid_ready"] == "True"
        assert r["direct_validation_executed"] == "False"


@pytest.mark.skipif(not _HAS_NIFTI, reason="NIfTI absent")
def test_native_centroid_in_amygdala():
    import nibabel as nib
    import numpy as np
    for side, p, exp_sign in (("left", NAT_L, -1), ("right", NAT_R, 1)):
        img = nib.load(str(p))
        vol = np.asanyarray(img.dataobj).astype(np.float64)
        X, Y, Z = np.meshgrid(np.arange(vol.shape[0]), np.arange(vol.shape[1]),
                              np.arange(vol.shape[2]), indexing="ij")
        aff = np.asarray(img.affine, float)
        xw = aff[0, 0] * X + aff[0, 3]
        m = vol.sum()
        cx = (vol * xw).sum() / m
        # amygdala lives ~x +/-18..27 mm in MNI
        assert cx * exp_sign > 15, (side, cx)


def test_reference_centroid_sane():
    r = _j(RMAN)
    for e in r["entries"]:
        cx = e["centroid_mm"][0]
        assert abs(cx) > 15 and abs(cx) < 32, e["geometry_id"]
