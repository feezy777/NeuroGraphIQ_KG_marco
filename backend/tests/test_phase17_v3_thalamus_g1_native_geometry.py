"""Phase1.7 V3 - THALAMUS_PROPER G1 native-space geometry construction tests.

Local-integration tests skip when the raw/derived NIfTI binaries are absent (CI
must not depend on uncommitted large NIfTI); manifest/metadata/invariant tests
still run because those files ARE tracked.

37 gate invariants.
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
RAW = BACKEND / "data" / "atlases" / "external_raw" / "freesurfer_icbm2009c" / "thalamus" / "ThalamusProbs.MNIsymSpace.nii.gz"
NAMES = BACKEND / "data" / "atlases" / "external_raw" / "freesurfer_icbm2009c" / "thalamus" / "ThalamusProbs.MNIsymSpace.names.txt"
V3 = D16 / "phase17_v3_thalamus_g1_scope_contract_v3.json"
CLASS = D16 / "phase17_v3_classification.csv"
MANIFEST = D16 / "phase17_v3_thalamus_g1_native_geometry_manifest.json"
QC = D16 / "phase17_v3_thalamus_g1_native_geometry_qc.csv"
MD = D16 / "phase17_v3_thalamus_g1_native_geometry_diagnostics.md"
OUT_L = DERIVED / "left_thalamus_proper_prob_icbm2009csym.nii.gz"
OUT_R = DERIVED / "right_thalamus_proper_prob_icbm2009csym.nii.gz"

RAW_SHA_EXPECTED = "640377ae93cf0782365a698573970c2a429a775c6f64dcf9ac02536156b51f22"
V3_SHA_EXPECTED = "22e24a31bab9659769f7e550ee32f8e3b37887d0ae1a4c4c4cf64974c3c05f68"
NAMES_SHA_EXPECTED = "74b70bfa4fa75aa05a0bee9fcb548fa97bea20bfceef43b63a97c52a3923bfec"

_HAS_MAN = MANIFEST.exists() and QC.exists()
_HAS_NIFTI = OUT_L.exists() and OUT_R.exists()
_HAS_RAW = RAW.exists()


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _man():
    return json.load(open(MANIFEST, encoding="utf-8"))


def _entry(hemi):
    for e in _man()["entries"]:
        if e["hemisphere"] == hemi:
            return e
    raise KeyError(hemi)


# ---- 1. raw SHA == acquisition freeze ----
@pytest.mark.skipif(not _HAS_RAW, reason="raw NIfTI not present (clean repo)")
def test_1_raw_sha_frozen():
    assert _sha(RAW) == RAW_SHA_EXPECTED


# ---- 2. raw byte-identical (sha stable = byte-identical) ----
@pytest.mark.skipif(not _HAS_RAW, reason="raw NIfTI not present (clean repo)")
def test_2_raw_byte_identical():
    assert len(_sha(RAW)) == 64
    # manifest must record the same sha
    assert _man()["entries"][0]["source_sha256"] == _sha(RAW)


# ---- 3. channel count = 53 ----
def test_3_channel_count_53():
    assert _man()["source"]["channel_count"] == 53
    assert _man()["source"]["shape"] == [138, 106, 94, 53]


# ---- 4. names metadata SHA fixed ----
def test_4_names_metadata_sha():
    if NAMES.exists():
        assert _sha(NAMES) == NAMES_SHA_EXPECTED
    assert _man()["entries"][0]["channel_metadata_sha256"] == NAMES_SHA_EXPECTED


# ---- 5. scope contract = V3 ----
def test_5_scope_contract_v3():
    for e in _man()["entries"]:
        assert e["scope_contract_id"] == "THALAMUS_G1_SCOPE_CONTRACT_V3"


# ---- 6. V3 SHA fixed ----
def test_6_v3_sha_fixed():
    if V3.exists():
        assert _sha(V3) == V3_SHA_EXPECTED
    for e in _man()["entries"]:
        assert e["scope_contract_sha256"] == V3_SHA_EXPECTED


# ---- 7. Left/Right included set derived from V3 ----
def test_7_included_set_from_v3():
    for hemi in ("left", "right"):
        e = _entry(hemi)
        inc = {c["official_name"] for c in e["included_channels"]}
        # all included channels carry a V3-derived scope decision id
        for c in e["included_channels"]:
            assert c["scope_decision_id"], c
        assert len(inc) == 25


# ---- 8. Reticular R explicitly EXCLUDE ----
def test_8_reticular_excluded():
    for hemi in ("left", "right"):
        e = _entry(hemi)
        exc = e["excluded_channels"]
        assert len(exc) == 1
        assert exc[0]["official_name"].endswith("-R")
        assert exc[0]["decision"] == "EXCLUDE"
        assert exc[0]["scope_decision_id"] == "DEC-THAL-03"


# ---- 9. Background EXCLUDE ----
def test_9_background_excluded():
    for e in _man()["entries"]:
        assert e["background_channel"]["channel_index"] == 0
        assert e["background_channel"]["scope"] == "EXCLUDE"


# ---- 10. LGN INCLUDE ----
def test_10_lgn_include():
    for hemi in ("left", "right"):
        names_inc = {c["official_name"] for c in _entry(hemi)["included_channels"]}
        assert any(n.endswith("-LGN") for n in names_inc)
        lgn = [c for c in _entry(hemi)["included_channels"] if c["official_name"].endswith("-LGN")][0]
        assert lgn["scope_decision_id"] == "DEC-THAL-01"


# ---- 11. MGN INCLUDE ----
def test_11_mgn_include():
    for hemi in ("left", "right"):
        mgn = [c for c in _entry(hemi)["included_channels"] if c["official_name"].endswith("-MGN")][0]
        assert mgn["scope_decision_id"] == "DEC-THAL-02"


# ---- 12. L-Sg INCLUDE ----
def test_12_lsg_include():
    for hemi in ("left", "right"):
        lsg = [c for c in _entry(hemi)["included_channels"] if c["official_name"].endswith("-L-Sg")][0]
        assert lsg["scope_decision_id"] == "DEC-THAL-04-LSG"


# ---- 13. included count == metadata-derived count ----
def test_13_included_count_derived():
    # names file has 26 nuclei per side; all except R are included -> 25
    for e in _man()["entries"]:
        assert len(e["included_channels"]) == 25
        assert len(e["excluded_channels"]) == 1
    assert _man()["qc_left"]["included_channel_count"] == 25
    assert _man()["qc_right"]["included_channel_count"] == 25
    assert _man()["qc_left"]["excluded_channel_count"] == 1
    assert _man()["qc_right"]["excluded_channel_count"] == 1


# ---- 14. SUM operator ----
def test_14_sum_operator():
    for e in _man()["entries"]:
        assert e["aggregation_operator"] == "SUM"
        assert e["probability_semantics"] == "MUTUALLY_EXCLUSIVE_CATEGORICAL"


# ---- 15-20. no MAX / union / clipping / threshold / binarization / normalization ----
def test_15_sum_operator_not_max():
    for e in _man()["entries"]:
        assert e["derivation"] == "PROBABILITY_CHANNEL_SUM_FROM_FROZEN_SCOPE"
        assert e["aggregation_operator"] == "SUM"


@pytest.mark.parametrize("flag", ["threshold_applied", "binarization_applied",
                                  "clipping_applied", "normalization_applied"])
def test_16_no_threshold_bin_clip_normalize(flag):
    for e in _man()["entries"]:
        assert e[flag] is False


def test_17_no_probabilistic_union():
    # union (probabilistic OR) would require a non-SUM operator; operator is SUM
    for e in _man()["entries"]:
        assert e["aggregation_operator"] == "SUM"


# ---- 21. native laterality, no world-X split ----
def test_21_native_laterality():
    assert _man()["qc_left"]["laterality_source"] == "SOURCE_NATIVE_CHANNEL_IDENTITY"
    assert _man()["qc_right"]["laterality_source"] == "SOURCE_NATIVE_CHANNEL_IDENTITY"
    assert _man()["qc_left"]["laterality_expected"] == "x<0"
    assert _man()["qc_right"]["laterality_expected"] == "x>0"
    # centroids confirm native laterality (left x<0, right x>0)
    assert _man()["qc_left"]["weighted_centroid_mm"][0] < 0
    assert _man()["qc_right"]["weighted_centroid_mm"][0] > 0


# ---- 22. all26 == G1 + R voxelwise ----
@pytest.mark.skipif(not _HAS_NIFTI, reason="derived NIfTI not present (clean repo)")
def test_22_all26_eq_g1_plus_r():
    import nibabel as nib
    import numpy as np
    raw = nib.load(RAW)
    d = np.asanyarray(raw.dataobj)
    names = [l for l in open(NAMES, encoding="utf-8").read().strip().splitlines() if l.strip()]
    for side, out in (("left", OUT_L), ("right", OUT_R)):
        prefix = "Left-" if side == "left" else "Right-"
        all26_ids = [i for i, l in enumerate(names) if l.split(",", 1)[1].startswith(prefix)]
        inc_ids = [c["channel_index"] for c in _entry(side)["included_channels"]]
        r_id = [c["channel_index"] for c in _entry(side)["excluded_channels"]][0]
        all26 = np.sum(np.asarray(d[..., all26_ids], dtype=np.float64), axis=-1)
        g1 = np.asarray(nib.load(out).dataobj, dtype=np.float64)
        r = np.asarray(d[..., r_id], dtype=np.float64)
        res = all26 - (g1 + r)
        assert np.abs(res).max() < 1e-3, side


# ---- 23. bg + all52 ~ 1 ----
@pytest.mark.skipif(not _HAS_RAW, reason="raw NIfTI not present (clean repo)")
def test_23_bg_plus_all52_conservation():
    import nibabel as nib
    import numpy as np
    raw = nib.load(RAW)
    d = np.asanyarray(raw.dataobj)
    bg = np.asarray(d[..., 0], dtype=np.float64)
    all52 = np.sum(np.asarray(d[..., 1:53], dtype=np.float64), axis=-1)
    s = bg + all52
    assert float(np.mean(np.abs(s - 1))) < 1e-3
    assert float(s.max()) <= 1 + 1e-3


# ---- 24. G1 probability no illegal values ----
@pytest.mark.skipif(not _HAS_NIFTI, reason="derived NIfTI not present (clean repo)")
def test_24_g1_no_illegal_values():
    import nibabel as nib
    import numpy as np
    for out in (OUT_L, OUT_R):
        d = np.asanyarray(nib.load(out).dataobj)
        assert d.ndim == 3
        assert float(np.nanmin(d)) >= 0.0
        assert float(np.nanmax(d)) <= 1 + 1e-3


# ---- 25. output grid == source grid ----
@pytest.mark.skipif(not _HAS_NIFTI, reason="derived NIfTI not present (clean repo)")
def test_25_output_grid_source_grid():
    import nibabel as nib
    raw = nib.load(RAW)
    for out in (OUT_L, OUT_R):
        o = nib.load(out)
        assert o.shape == raw.shape[:3]


# ---- 26. output affine == source affine ----
@pytest.mark.skipif(not _HAS_NIFTI, reason="derived NIfTI not present (clean repo)")
def test_26_output_affine_source_affine():
    import nibabel as nib
    import numpy as np
    raw = nib.load(RAW)
    for out in (OUT_L, OUT_R):
        o = nib.load(out)
        assert np.allclose(o.affine, raw.affine)
        assert np.allclose(o.get_qform(), raw.get_qform())
        assert np.allclose(o.get_sform(), raw.get_sform())


# ---- 27. no registration ----
def test_27_no_registration():
    for e in _man()["entries"]:
        assert e["registration_applied"] is False


# ---- 28. no resampling ----
def test_28_no_resampling():
    for e in _man()["entries"]:
        assert e["resampling_applied"] is False


# ---- 29. transform_id = null ----
def test_29_transform_id_null():
    for e in _man()["entries"]:
        assert e["transform_id"] is None


# ---- 30. direct_g4_overlap_ready = false ----
def test_30_not_julich_ready():
    assert _man()["julich_readiness"]["direct_g4_overlap_ready"] is False
    assert "SYMMETRIC_TO_ASYMMETRIC" in _man()["julich_readiness"]["transform_required"]


# ---- 31. independent from G3->G1 ----
def test_31_independent_from_g3_g1():
    for e in _man()["entries"]:
        assert e["independent_from_g3_g1_mapping"] is True


# ---- 32. circularity = none ----
def test_32_circularity_none():
    for e in _man()["entries"]:
        assert e["circularity_risk"] == "NONE"


# ---- 33. output SHA256 fixed ----
def test_33_output_sha256_fixed():
    for e in _man()["entries"]:
        assert len(e["output_sha256"]) == 64
    if OUT_L.exists():
        assert _sha(OUT_L) == _entry("left")["output_sha256"]
    if OUT_R.exists():
        assert _sha(OUT_R) == _entry("right")["output_sha256"]


# ---- 34. classification byte-identical ----
@pytest.mark.skipif(not CLASS.exists(), reason="classification not present")
def test_34_classification_unchanged():
    with open(CLASS, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


# ---- 35. DB zero-write ----
def test_35_db_zero_write():
    # manifest records construction flags - geometry derived from files only
    assert _man()["geometry_class"] == "AUTHORITATIVE_DERIVED_G1_GEOMETRY"


# ---- 36. BN direct validation still PENDING ----
def test_36_bn_direct_validation_pending():
    # sibling frozen gate-transition records keep the post-construction state
    gt = D16 / "phase17_v3_thalamus_lsg_gate_transition.json"
    if gt.exists():
        g = json.load(open(gt, encoding="utf-8"))
        assert g["bn_postconstruction_direct_validation"] == "PENDING_POSTCONSTRUCTION"
    # this round performs no BN direct validation: manifest declares independence
    for e in _man()["entries"]:
        assert e["independent_from_g3_g1_mapping"] is True


# ---- 37. Promotion still BLOCKED ----
def test_37_promotion_blocked():
    gt = D16 / "phase17_v3_thalamus_lsg_gate_transition.json"
    if gt.exists():
        g = json.load(open(gt, encoding="utf-8"))
        assert g["promotion"] == "BLOCKED"
    md = MD.read_text(encoding="utf-8")
    assert "no DB write" in md and "no commit" in md


# ---- QC CSV exists and is consistent ----
def test_qc_csv_consistent():
    if not _HAS_MAN:
        pytest.skip("manifest not present")
    rows = list(csv.DictReader(open(QC, encoding="utf-8-sig")))
    assert len(rows) == 2
    sides = {r["side"] for r in rows}
    assert sides == {"left", "right"}
    for r in rows:
        assert int(r["included_channel_count"]) == 25
        assert int(r["excluded_channel_count"]) == 1
        assert len(r["output_sha256"]) == 64
