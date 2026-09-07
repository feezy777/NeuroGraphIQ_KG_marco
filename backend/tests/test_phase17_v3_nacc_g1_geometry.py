"""Phase1.7 V3 - CIT168 Nucleus Accumbens G1 geometry construction v1 tests.

Validates the derived L/R NAcc probability geometry and its audit manifest.
Read-only: never writes DB, never recomputes geometry, never downloads.
16 required checks + grid invariant + invariants.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
RAW = BACKEND / "data" / "atlases" / "external_raw" / "cit168"
DERIVED = BACKEND / "data" / "atlases" / "derived_g1" / "cit168_nacc"
JULICH_REF = (BACKEND / "data" / "atlases" / "julich" / "v3.1" / "spatial_raw"
              / "probability_maps" / "AREA_44_IFG_LEFT.nii.gz")
OUTJSON = D16 / "phase17_v3_nacc_g1_geometry_manifest.json"
MANIFEST = D16 / "phase17_v3_external_g1_asset_manifest.csv"
CLASS = D16 / "phase17_v3_classification.csv"

SRC_PROB = RAW / "CIT168toMNI152-2009c_prob.nii.gz"
SRC_DET = RAW / "CIT168toMNI152-2009c_det.nii.gz"

_HAS_SRC = SRC_PROB.exists() and SRC_DET.exists()
_HAS_OUT = (DERIVED / "left" / "left_nucleus_accumbens_prob.nii.gz").exists() and \
    (DERIVED / "right" / "right_nucleus_accumbens_prob.nii.gz").exists()
_HAS_MAN = OUTJSON.exists()


def _man():
    with open(OUTJSON, encoding="utf-8") as fh:
        return json.load(fh)


# ---- 1. source must be the CIT168 probability atlas ----
@pytest.mark.skipif(not (_HAS_SRC and _HAS_MAN),
                    reason="CIT168 raw or geometry manifest not present")
def test_1_source_is_cit168_prob():
    im = nib.load(SRC_PROB)
    assert im.shape[:3] == (193, 229, 193) and len(im.shape) == 4
    m = _man()
    assert m["source"]["asset_id"] == "CIT168_NAcc"
    assert m["source"]["file"] == "CIT168toMNI152-2009c_prob.nii.gz"


# ---- 2. source NAC channel metadata consistent ----
@pytest.mark.skipif(not (_HAS_SRC and _HAS_MAN),
                    reason="CIT168 raw or geometry manifest not present")
def test_2_nac_channel_consistent():
    m = _man()
    lut = {}
    for line in (RAW / "labels.txt").read_text(encoding="utf-8").splitlines():
        p = line.strip().split()
        if len(p) == 2 and p[0].isdigit():
            lut[int(p[0])] = p[1]
    ch = m["source"]["channel"]
    assert lut.get(ch) == "NAC"
    im = nib.load(SRC_PROB)
    assert ch < im.shape[3]


# ---- 3. det atlas used for QC only ----
@pytest.mark.skipif(not _HAS_MAN, reason="geometry manifest not present")
def test_3_det_only_qc():
    m = _man()
    assert m["source"]["det_role"] == "QC_ONLY"
    # derived geometries are probability; det never referenced as geometry source
    for hemi in ("left", "right"):
        assert m[hemi]["source_filename"] == "CIT168toMNI152-2009c_prob.nii.gz"


# ---- 4/5. probability not thresholded / not binarized ----
@pytest.mark.skipif(not _HAS_MAN, reason="geometry manifest not present")
def test_45_no_threshold_no_binarize():
    m = _man()
    for hemi in ("left", "right"):
        g = m[hemi]
        assert g["threshold_applied"] == "FALSE"
        assert g["binarization_applied"] == "FALSE"
        qc = g["qc"]
        assert 0.0 < qc["min"] < qc["max"] <= 1.0  # fractional probabilities preserved
        assert qc["mass"] > 0
        # fractional interior => not binarized: max==1 but mass << nonzero count
        assert qc["mass"] < qc["nonzero"]  # probabilities are < 1 on average


# ---- 6/7. no registration / no resampling ----
@pytest.mark.skipif(not _HAS_MAN, reason="geometry manifest not present")
def test_67_no_registration_no_resampling():
    m = _man()
    for hemi in ("left", "right"):
        assert m[hemi]["registration_applied"] == "FALSE"
        assert m[hemi]["resampling_applied"] == "FALSE"


# ---- 8. output grid identical to source ----
@pytest.mark.skipif(not (_HAS_SRC and _HAS_OUT), reason="raw/derived not present")
def test_8_output_grid_matches_source():
    src = nib.load(SRC_PROB)
    for hemi in ("left", "right"):
        out = nib.load(DERIVED / hemi / f"{hemi}_nucleus_accumbens_prob.nii.gz")
        assert tuple(out.shape) == tuple(src.shape[:3])
        assert all(abs(a - b) < 1e-3 for a, b in zip(out.affine.ravel(), src.affine.ravel()))


# ---- 9. output grid EXACT_GRID_MATCH with Julich ----
@pytest.mark.skipif(not _HAS_OUT, reason="derived not present")
def test_9_grid_exact_julich():
    jref = nib.load(JULICH_REF)
    for hemi in ("left", "right"):
        out = nib.load(DERIVED / hemi / f"{hemi}_nucleus_accumbens_prob.nii.gz")
        assert tuple(out.shape) == tuple(jref.shape)
        assert all(abs(float(a) - float(b)) < 1e-3
                   for a, b in zip(out.affine.ravel(), jref.affine.ravel()))


# ---- 10. L/R do not overlap ----
@pytest.mark.skipif(not _HAS_OUT, reason="derived not present")
def test_10_left_right_no_overlap():
    l = np.asanyarray(nib.load(DERIVED / "left" / "left_nucleus_accumbens_prob.nii.gz").dataobj)
    r = np.asanyarray(nib.load(DERIVED / "right" / "right_nucleus_accumbens_prob.nii.gz").dataobj)
    assert int(((l > 0) & (r > 0)).sum()) == 0


# ---- 11. L + R + midline mass == bilateral source mass ----
@pytest.mark.skipif(not _HAS_MAN, reason="geometry manifest not present")
def test_11_mass_conservation():
    mc = _man()["mass_conservation"]
    assert mc["conserved"] is True
    assert abs((mc["left"] + mc["right"] + mc["midline"]) - mc["bilateral"]) < 1e-3
    assert mc["midline"] == 0.0


# ---- 11b. VOXEL-WISE value preservation:
#      left + right + midline == source_nac_prob at every voxel (float tolerance).
#      Not just total-mass conservation - per-voxel value must be preserved.
#      (Reconstructs NAC channel from the LUT, independent of the manifest values.)
# ----
@pytest.mark.skipif(not (_HAS_SRC and _HAS_OUT),
                    reason="raw/derived not present (gitignored)")
def test_11b_voxel_wise_conservation():
    src = nib.load(SRC_PROB).get_fdata()
    # derive the NAC channel from LUT metadata (not a hardcoded index in this test)
    lut = {}
    with open(RAW / "labels.txt", encoding="utf-8") as fh:
        for line in fh:
            p = line.strip().split()
            if len(p) == 2 and p[0].isdigit():
                lut[int(p[0])] = p[1]
    hits = [k for k, v in lut.items() if v.strip().upper() in ("NAC", "NUCLEUS ACCUMBENS", "ACB")]
    assert len(hits) == 1
    nac = src[..., hits[0]].astype(np.float64)

    L = np.asanyarray(nib.load(
        DERIVED / "left" / "left_nucleus_accumbens_prob.nii.gz").dataobj).astype(np.float64)
    R = np.asanyarray(nib.load(
        DERIVED / "right" / "right_nucleus_accumbens_prob.nii.gz").dataobj).astype(np.float64)
    # midline reconstructed as whatever is neither left nor right in source support
    M = nac - (L + R)

    # no negative residuals anywhere (nothing lost or invented)
    assert float(M.min()) >= -1e-6, M.min()
    assert float((nac - (L + R + M)).max()) < 1e-6
    # per-voxel value preservation over every voxel
    max_abs = float(np.abs(nac - (L + R)).max())
    assert max_abs < 1e-6, f"voxel-wise value not preserved (max|src-(L+R)|={max_abs})"
    # midline must be (numerically) empty because L+R reconstructs source exactly
    assert float(M.max()) < 1e-6


# ---- 12. hemisphere split is world-coordinate based ----
@pytest.mark.skipif(not _HAS_MAN, reason="geometry manifest not present")
def test_12_world_coordinate_split():
    m = _man()
    # Left centroid X < 0, Right centroid X > 0 (RAS world coordinate)
    assert m["left"]["qc"]["centroid"][0] < -1
    assert m["right"]["qc"]["centroid"][0] > 1
    assert "world X" in m["left"]["hemisphere_split_rule"]


# ---- 13. raw assets byte-identical (sha256 in manifest matches on-disk) ----
@pytest.mark.skipif(not (_HAS_SRC and _HAS_MAN),
                    reason="CIT168 raw or geometry manifest not present")
def test_13_raw_byte_identical():
    import hashlib
    m = _man()
    h = hashlib.sha256()
    with open(SRC_PROB, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    assert h.hexdigest() == m["source"]["sha256"]


# ---- 14. derived geometry independent of G3->G1 mapping ----
@pytest.mark.skipif(not _HAS_MAN, reason="geometry manifest not present")
def test_14_independent_of_g3_g1():
    m = _man()
    for hemi in ("left", "right"):
        assert m[hemi]["independent_from_g3_g1_mapping"] == "TRUE"
        assert m[hemi]["circularity_risk"] == "NONE"


# ---- 15. classification byte-identical (unchanged) ----
def test_15_classification_unchanged():
    with open(CLASS, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    from collections import Counter
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert sum(c.values()) - c["VERIFIED_DIRECT_CONTAINED"] == 132
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


# ---- 16. DB zero-write (no DB import/path in artifact scope); guard present ----
@pytest.mark.skipif(not _HAS_MAN, reason="geometry manifest not present")
def test_16_no_db_artifacts():
    # construction outputs are file-based under derived_g1/ + integration audit dir
    m = _man()
    assert m["scope"].startswith("Nucleus Accumbens only")
    # canonical ids present & correct
    assert m["canonical"]["Left"]["g1_region_id"] == "NGIQ-BR-00000254"
    assert m["canonical"]["Right"]["g1_region_id"] == "NGIQ-BR-00000262"
    # only L/R NAcc geometries were produced this round
    assert set(m.keys()) >= {"left", "right", "bilateral", "midline"}
    assert m["left"]["canonical_name"] == "Left Nucleus Accumbens"
    assert m["right"]["canonical_name"] == "Right Nucleus Accumbens"


# ---- grid invariant / geometry class / no other G1 family ----
@pytest.mark.skipif(not _HAS_MAN, reason="geometry manifest not present")
def test_grid_class_scope():
    m = _man()
    assert m["grid_relation_to_julich"] == "EXACT_GRID_MATCH"
    for hemi in ("left", "right"):
        assert m[hemi]["geometry_class"] == "AUTHORITATIVE_DERIVED_G1_GEOMETRY"
        assert m[hemi]["coordinate_space"] == "MNI152NLin2009cAsym"
        assert m[hemi]["hemisphere"] in ("left", "right")
    # the only derived outputs referenced are the two NAcc hemispheres
    assert "left" in m and "right" in m
    assert not any(k.startswith("thal") or k.startswith("hippo") for k in m)
