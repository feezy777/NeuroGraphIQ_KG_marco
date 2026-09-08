"""Phase1.7 V3 - Thalamus Julich-reference-grid G1 geometry tests (SPATIAL BRIDGE).

The earlier nonlinear-SyN transform claim was RETRACTED after evidence showed the
ANTsPy 0.6.3 runtime on this platform emits zero-displacement warp fields, and
that the 2009c Sym / MNI2009c Asym templates are DIFFERENT variants sharing a
stereotaxic world-coordinate frame. The current operation is a SPATIAL BRIDGE
(shared-coordinate reference-grid resampling), NOT a transform.

Local NIfTI-dependent tests skip in a clean repo; manifest/invariant tests run.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
DERIVED = BACKEND / "data" / "atlases" / "derived_g1"
V3 = D16 / "phase17_v3_thalamus_g1_scope_contract_v3.json"
CLASS = D16 / "phase17_v3_classification.csv"
SRC_LEFT = DERIVED / "left_thalamus_proper_prob_icbm2009csym.nii.gz"
SRC_RIGHT = DERIVED / "right_thalamus_proper_prob_icbm2009csym.nii.gz"
OUT_LEFT = DERIVED / "left_thalamus_proper_prob_mni2009casym.nii.gz"
OUT_RIGHT = DERIVED / "right_thalamus_proper_prob_mni2009casym.nii.gz"
SRC_TPL = BACKEND / "data" / "atlases" / "external_raw" / "_ref" / "mni_icbm152_t1_tal_nlin_sym_09c.nii"
SRC_TPL_MASK = BACKEND / "data" / "atlases" / "external_raw" / "_ref" / "mni_icbm152_t1_tal_nlin_sym_09c_mask.nii"
TGT_TPL = BACKEND / "data" / "atlases" / "templateflow_ref" / "tpl-MNI152NLin2009cAsym_res01_desc-brain_T1w.nii.gz"
SPB_MAN = D16 / "phase17_v3_thalamus_spatial_bridge_manifest.json"
SPB_QC = D16 / "phase17_v3_thalamus_spatial_bridge_qc.csv"
RETR = D16 / "phase17_v3_thalamus_transform_retraction.json"
ENV = D16 / "phase17_v3_thalamus_transform_environment.json"
GEOM_MAN = D16 / "phase17_v3_thalamus_g1_julich_geometry_manifest.json"
GEOM_QC = D16 / "phase17_v3_thalamus_g1_julich_geometry_qc.csv"
MD = D16 / "phase17_v3_thalamus_g1_julich_geometry_diagnostics.md"

V3_SHA_EXPECTED = "22e24a31bab9659769f7e550ee32f8e3b37887d0ae1a4c4c4cf64974c3c05f68"
LEFT_SHA_EXPECTED = "2c9d3d2d7823a02749c77a7084339d503fcb251b5db53b7791e2f008b43f2ba8"
RIGHT_SHA_EXPECTED = "e9e93d593ddc073431d3e8d2da3e1d16e89e05ec213f9e24d6659caa9c926ae2"
SPB_ID = "SPB-MNI2009C-SYM-ASYM-SHARED-FRAME-V1"
OLD_TRF = "TRF-ICBM2009CSYM-TO-MNI2009CASYM-V1"
OLD_LEFT_SHA = "37a82b65d86d81b1558582dee301e79ee367d60856f95d6a55b0219cf28a87a1"
OLD_RIGHT_SHA = "1c9b8b8de9103c1e091c9fb6e0577182416d5a6ba0c1b7f6d41e1e913958253f"

_HAS_MAN = SPB_MAN.exists() and GEOM_MAN.exists() and RETR.exists()
_HAS_NIFTI = OUT_LEFT.exists() and OUT_RIGHT.exists()


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _spb():
    return json.load(open(SPB_MAN, encoding="utf-8"))


def _geom():
    return json.load(open(GEOM_MAN, encoding="utf-8"))


def _retr():
    return json.load(open(RETR, encoding="utf-8"))


def _entry(hemi):
    for e in _geom()["entries"]:
        if e["hemisphere"] == hemi:
            return e
    raise KeyError(hemi)


# ---- 1. old TRF status = RETRACTED ----
def test_1_old_trf_retracted():
    r = _retr()
    assert r["transform_id"] == OLD_TRF
    assert r["status"] == "RETRACTED"
    assert r["reason"] == "ANTSPY_SYN_ZERO_DISPLACEMENT_FIELD_PROVENANCE_ANOMALY"


# ---- 2. old nonlinear geometry SHA no longer current ----
def test_2_old_geometry_superseded():
    r = _retr()
    assert r["superseded_geometry"]["left"]["old_sha"] == OLD_LEFT_SHA
    assert "SUPERSEDED" in r["superseded_geometry"]["left"]["status"]
    assert r["superseded_geometry"]["right"]["old_sha"] == OLD_RIGHT_SHA
    # current geometry must differ from old superseded SHAs
    for hemi in ("left", "right"):
        cur = _entry(hemi)["output_sha256"]
        assert cur != (OLD_LEFT_SHA if hemi == "left" else OLD_RIGHT_SHA)


# ---- 3. replacement route is SPATIAL_BRIDGE, not TRF ----
def test_3_replacement_is_spb():
    assert _retr()["replacement_route"]["spatial_bridge_id"] == SPB_ID
    assert "RESAMPLING" in _retr()["replacement_route"]["class_name"]
    spb = _spb()
    assert spb["spatial_bridge_id"] == SPB_ID
    assert "TRF" not in spb["spatial_bridge_class"]


# ---- 4. registration_applied = FALSE ----
def test_4_registration_false():
    assert _spb()["registration_applied"] is False
    assert _geom()["registration_applied"] is False


# ---- 5. nonlinear_registration_applied = FALSE ----
def test_5_nonlinear_registration_false():
    assert _spb()["nonlinear_registration_applied"] is False
    assert _spb()["nonlinear_registration_claimed"] is False
    assert _geom()["nonlinear_registration_applied"] is False


# ---- 6. resampling_applied = TRUE ----
def test_6_resampling_true():
    assert _spb()["resampling_applied"] is True
    assert _geom()["resampling_applied"] is True


# ---- 7. interpolation = LINEAR ----
def test_7_interpolation_linear():
    assert _spb()["interpolation"] == "LINEAR"
    assert _geom()["interpolation"] == "LINEAR"


# ---- 8. source/target physical-coordinate metadata complete ----
def test_8_physical_metadata():
    spb = _spb()
    for k in ("source_space", "target_reference_space",
              "source_world_coordinate_convention", "target_world_coordinate_convention",
              "source_grid", "target_grid", "affine_relation"):
        assert spb.get(k), k
    assert spb["source_space"] == "ICBM152_2009C_SYMMETRIC"
    assert spb["target_reference_space"] == "MNI152NLin2009cAsym"
    assert spb["source_grid"]["spacing_mm"] == 0.5
    assert spb["target_grid"]["shape"] == [193, 229, 193]


# ---- 9. target shape = 193x229x193 ----
def test_9_target_shape():
    assert _spb()["target_grid"]["shape"] == [193, 229, 193]
    assert _geom()["entries"][0]["target_grid"]["shape"] == [193, 229, 193]


# ---- 10. target affine = Julich reference ----
@pytest.mark.skipif(not _HAS_NIFTI, reason="derived NIfTI absent (clean repo)")
def test_10_target_affine():
    import nibabel as nib
    import numpy as np
    jp = sorted((BACKEND / "data" / "atlases" / "julich" / "v3.1" / "spatial_raw" / "probability_maps").glob("*.nii.gz"))[0]
    ref = nib.load(str(jp))
    for out in (OUT_LEFT, OUT_RIGHT):
        img = nib.load(str(out))
        assert np.allclose(np.asarray(img.affine), np.asarray(ref.affine), atol=1e-4)


# ---- 11. new output SHA fixed ----
def test_11_new_output_sha():
    for hemi in ("left", "right"):
        e = _entry(hemi)
        assert len(e["output_sha256"]) == 64
    if OUT_LEFT.exists():
        assert _sha(OUT_LEFT) == _entry("left")["output_sha256"]
    if OUT_RIGHT.exists():
        assert _sha(OUT_RIGHT) == _entry("right")["output_sha256"]


# ---- 12. old SyN output SHA superseded ----
def test_12_old_syn_superseded():
    assert _retr()["superseded_geometry"]["left"]["status"] == \
        "SUPERSEDED / INVALIDATED_BY_TRANSFORM_PROVENANCE_REPAIR"
    assert _retr()["superseded_geometry"]["right"]["status"] == \
        "SUPERSEDED / INVALIDATED_BY_TRANSFORM_PROVENANCE_REPAIR"


# ---- 13. residual template-variant limitation explicit ----
def test_13_residual_limitation():
    lim = _spb()["residual_spatial_limitation"]
    assert "TEMPLATE_VARIANT_ANATOMICAL_MISMATCH" in lim
    assert "NOT_EXPLICITLY_WARP_CORRECTED" in lim
    assert _geom()["residual_spatial_limitation"] == lim
    assert _geom()["template_variant_uncertainty"] == "PRESENT"
    assert _spb()["template_variant_statement"] == \
        "DIFFERENT_TEMPLATE_VARIANTS_WITH_SHARED_STEREOTAXIC_COORDINATE_FRAME"


# ---- 14-17. no threshold/bin/clip/renorm ----
@pytest.mark.parametrize("flag", ["threshold_applied", "binarization_applied",
                                  "clipping_applied", "normalization_applied"])
def test_14_17_no_ops(flag):
    assert _geom()[flag] is False


# ---- 18. V1/V2/V3 unchanged ----
@pytest.mark.skipif(not V3.exists(), reason="V3 absent")
def test_18_contracts_unchanged():
    import subprocess
    for p in (D16 / "phase17_v3_thalamus_g1_scope_contract.json",
              D16 / "phase17_v3_thalamus_g1_scope_contract_v2.json",
              V3):
        r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", str(p)],
                           cwd=BACKEND.parent, capture_output=True)
        assert r.returncode == 0, f"{p.name} differs from HEAD"


# ---- 19. classification byte-identical ----
@pytest.mark.skipif(not CLASS.exists(), reason="classification not present")
def test_19_classification_unchanged():
    with open(CLASS, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


# ---- 20. DB zero-write ----
def test_20_db_zero_write():
    md = MD.read_text(encoding="utf-8")
    assert "no DB write" in md and "no commit" in md


# ---- 21. BN direct validation still PENDING ----
def test_21_bn_pending():
    assert "PENDING_NEXT_FUNCTION" in MD.read_text(encoding="utf-8")


# ---- 22. Promotion still BLOCKED ----
def test_22_promotion_blocked():
    assert "Promotion = BLOCKED" in MD.read_text(encoding="utf-8")


# ---- 23. no unauthorized geometry ----
@pytest.mark.skipif(not _HAS_MAN, reason="manifests absent")
def test_23_no_unauthorized_geometry():
    _authorized = {"left_thalamus_proper_prob_icbm2009csym.nii.gz",
                   "right_thalamus_proper_prob_icbm2009csym.nii.gz",
                   "left_thalamus_proper_prob_mni2009casym.nii.gz",
                   "right_thalamus_proper_prob_mni2009casym.nii.gz"}
    present = {p.name for p in Path(BACKEND, "data", "atlases", "derived_g1").rglob("*thalamus*.nii.gz")}
    assert present <= _authorized, present


# ---- 24. environment provenance complete ----
def test_24_environment_provenance():
    assert ENV.exists()
    env = json.load(open(ENV, encoding="utf-8"))
    for k in ("python_version", "platform", "numpy_version", "scipy_version",
              "nibabel_version", "antspy_version", "simpleitk_version"):
        assert env.get(k), k
    assert env["antspy_syn_functional"] is False
    assert "CURRENT_RUNTIME_IMPLEMENTATION_ANOMALY" in env["antspy_syn_note"]


# ---- additional structural checks ----
def test_native_geometry_sha():
    if SRC_LEFT.exists():
        assert _sha(SRC_LEFT) == LEFT_SHA_EXPECTED
    if SRC_RIGHT.exists():
        assert _sha(SRC_RIGHT) == RIGHT_SHA_EXPECTED


def test_v3_sha():
    if V3.exists():
        assert _sha(V3) == V3_SHA_EXPECTED
    for e in _geom()["entries"]:
        assert e["scope_contract"]["sha256"] == V3_SHA_EXPECTED


def test_laterality_preserved():
    assert _entry("left")["probability_qc"]["centroid_mm"][0] < 0
    assert _entry("right")["probability_qc"]["centroid_mm"][0] > 0


def test_direct_overlap_flags():
    assert _geom()["direct_overlap_grid_ready"] is True
    assert _geom()["target_grid_ready"] is True
    assert _geom()["authoritatively_registered_to_julich"] is False
    assert "DIRECT_SPATIAL_OVERLAP_IN_SHARED_MNI2009C_COORDINATE_FRAME" == \
        _geom()["direct_overlap_evidence_type"]


def test_derivation():
    assert _geom()["derivation"] == "REFERENCE_GRID_RESAMPLING_FROM_NATIVE_G1_GEOMETRY"


def test_geometry_qc_csv_consistent():
    if not _HAS_MAN:
        pytest.skip("manifests absent")
    rows = list(csv.DictReader(open(GEOM_QC, encoding="utf-8-sig")))
    assert len(rows) == 2
    assert {r["hemisphere"] for r in rows} == {"left", "right"}
    for r in rows:
        assert len(r["output_sha256"]) == 64


def test_spb_qc_csv():
    if not _HAS_MAN:
        pytest.skip("manifests absent")
    rows = list(csv.DictReader(open(SPB_QC, encoding="utf-8-sig")))
    kv = {r["metric"]: r["value"] for r in rows}
    assert kv["registration_applied"] == "False"
    assert kv["nonlinear_registration_applied"] == "False"
    assert kv["resampling_applied"] == "True"
    assert kv["interpolation"] == "LINEAR"
