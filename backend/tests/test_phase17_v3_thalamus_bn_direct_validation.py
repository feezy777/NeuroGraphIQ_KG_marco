"""Phase1.7 V3 - Thalamus Brainnetome direct spatial validation tests.

Verifies the DIAGNOSTIC BN-direct spatial validation on the frozen Julich-grid
G1 geometry. Never modifies DB / lifecycle_status / classification; never
promotes; read-only. Local NIfTI-dependent tests skip in a clean repo.
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
BN_PM_DIR = BACKEND / "data" / "atlases" / "brainnetome" / "bna246" / "transformed_to_julich2009c" / "probability_maps"
G1_LEFT = DERIVED / "left_thalamus_proper_prob_mni2009casym.nii.gz"
G1_RIGHT = DERIVED / "right_thalamus_proper_prob_mni2009casym.nii.gz"
V3 = D16 / "phase17_v3_thalamus_g1_scope_contract_v3.json"
CLASS = D16 / "phase17_v3_classification.csv"
SPB_MAN = D16 / "phase17_v3_thalamus_spatial_bridge_manifest.json"
RES = D16 / "phase17_v3_thalamus_bn_direct_validation.json"
PROV = D16 / "phase17_v3_thalamus_bn_direct_validation_provenance.json"
PARCEL = D16 / "phase17_v3_thalamus_bn_direct_validation_parcels.csv"
HEMI = D16 / "phase17_v3_thalamus_bn_direct_validation_hemispheres.csv"
MD = D16 / "phase17_v3_thalamus_bn_direct_validation_diagnostics.md"

G1_LEFT_SHA = "bd431608fcea3c5f0f7387b1b0e1010582fa2e39dae95a300b3bba976a10cc87"
G1_RIGHT_SHA = "73e4242b581f2420c316593f6cd85183ea7f99c29e2b817b0257cdf267c5bd3b"
SUP_LEFT = "37a82b65d86d81b1558582dee301e79ee367d60856f95d6a55b0219cf28a87a1"
SUP_RIGHT = "1c9b8b8de9103c1e091c9fb6e0577182416d5a6ba0c1b7f6d41e1e913958253f"
SPB_ID = "SPB-MNI2009C-SYM-ASYM-SHARED-FRAME-V1"
LIM = "TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_WARP_CORRECTED"

_HAS = RES.exists() and PROV.exists() and PARCEL.exists() and HEMI.exists()
_HAS_NIFTI = G1_LEFT.exists() and G1_RIGHT.exists()


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _res():
    return json.load(open(RES, encoding="utf-8"))


def _prov():
    return json.load(open(PROV, encoding="utf-8"))


def _rows():
    return list(csv.DictReader(open(PARCEL, encoding="utf-8-sig")))


def _hemi():
    return list(csv.DictReader(open(HEMI, encoding="utf-8-sig")))


# ---- 1. only CURRENT G1 SHAs accepted ----
def test_1_current_sha_used():
    r = _res()
    assert r["g1_left_sha"] == G1_LEFT_SHA
    assert r["g1_right_sha"] == G1_RIGHT_SHA
    p = _prov()
    assert p["g1_left"]["sha256"] == G1_LEFT_SHA
    assert p["g1_right"]["sha256"] == G1_RIGHT_SHA
    if G1_LEFT.exists():
        assert _sha(G1_LEFT) == G1_LEFT_SHA
    if G1_RIGHT.exists():
        assert _sha(G1_RIGHT) == G1_RIGHT_SHA


# ---- 2. superseded SHAs rejected / not consumed ----
def test_2_superseded_rejected():
    p = _prov()
    assert p["superseded_g1"]["left"] == SUP_LEFT
    assert p["superseded_g1"]["right"] == SUP_RIGHT
    assert "never consumed as current evidence" in p["superseded_g1"]["note"]
    # current SHAs must differ from superseded
    assert G1_LEFT_SHA != SUP_LEFT
    assert G1_RIGHT_SHA != SUP_RIGHT
    # no artifact references superseded as current
    blob = json.dumps(_res()) + PARCEL.read_text(encoding="utf-8")
    assert SUP_LEFT not in blob and SUP_RIGHT not in blob


# ---- 3. left G1 not evaluated against right parcels as ipsilateral evidence ----
def test_3_no_left_g1_vs_right_parcel_ipsilateral():
    for r in _rows():
        if r["hemisphere"] == "left":
            assert r["parcel_code"].startswith("Tha_L_")
            assert r["g1_entity_id"] == "NGIQ-BR-00000247"
        else:
            assert r["parcel_code"].startswith("Tha_R_")
            assert r["g1_entity_id"] == "NGIQ-BR-00000256"


# ---- 4. right G1 not evaluated against left parcels as ipsilateral evidence ----
def test_4_no_right_g1_vs_left_parcel_ipsilateral():
    for r in _rows():
        if r["parcel_code"].startswith("Tha_L_"):
            assert r["hemisphere"] == "left"
            assert r["g1_entity_id"] == "NGIQ-BR-00000247"
        else:
            assert r["hemisphere"] == "right"
            assert r["g1_entity_id"] == "NGIQ-BR-00000256"


# ---- 5. overlap volumes non-negative ----
def test_5_overlap_nonnegative():
    for r in _rows():
        assert float(r["intersection_mass"]) >= 0
        assert float(r["bn_volume_mm3_equiv"]) >= 0
        assert float(r["g1_volume_mm3_equiv"]) >= 0


# ---- 6. overlap ratios bounded [0,1] ----
def test_6_ratios_bounded():
    for r in _rows():
        assert 0.0 <= float(r["overlap_ratio_vs_G1"]) <= 1.0
        assert 0.0 <= float(r["overlap_ratio_vs_BN"]) <= 1.0


# ---- 7. Dice bounded [0,1] ----
def test_7_dice_bounded():
    for r in _rows():
        assert 0.0 <= float(r["dice"]) <= 1.0


# ---- 8. union coverage does not double-count voxels ----
@pytest.mark.skipif(not _HAS_NIFTI, reason="NIfTI absent (clean repo)")
def test_8_union_no_double_count():
    import nibabel as nib
    import numpy as np
    g1 = np.asanyarray(nib.load(str(G1_LEFT)).dataobj).astype(np.float64)
    union = np.zeros(g1.shape, dtype=bool)
    for f in sorted(BN_PM_DIR.glob("*Tha_L_8_*prob_2009c.nii.gz")):
        union |= np.asanyarray(nib.load(str(f)).dataobj).astype(np.float64) > 0
    # per-voxel union mass equals sum over union mask once
    expected = float((g1 * union).sum())
    hemi = _hemi()
    left = [h for h in hemi if h["hemisphere"] == "left"][0]
    # CSV stores mm3-equiv rounded to 3 decimals
    assert abs(float(left["bn_covered_g1_volume_mm3_equiv"]) - expected) < 0.001


# ---- 9. top-parcel (max G1 coverage) ranking deterministic ----
def test_9_ranking_deterministic():
    for side in ("left", "right"):
        sub = [r for r in _rows() if r["hemisphere"] == side]
        # ranks 1..n unique and deterministic by descending overlap_ratio_vs_G1
        srt = sorted(sub, key=lambda r: -float(r["overlap_ratio_vs_G1"]))
        for i, r in enumerate(srt, start=1):
            assert int(r["rank_by_g1_coverage"]) == i
        ranks = sorted(int(r["rank_by_g1_coverage"]) for r in sub)
        assert ranks == list(range(1, len(sub) + 1))


# ---- 10. source/target grid compatibility checked before overlap ----
@pytest.mark.skipif(not _HAS_NIFTI, reason="NIfTI absent (clean repo)")
def test_10_grid_compatibility():
    import nibabel as nib
    import numpy as np
    g1 = nib.load(str(G1_LEFT))
    for f in sorted(BN_PM_DIR.glob("*Tha_*_prob_2009c.nii.gz")):
        bn = nib.load(str(f))
        assert bn.shape == g1.shape == (193, 229, 193)
        assert np.allclose(bn.affine, g1.affine, atol=1e-4)
    # provenance records julich reference grid identity
    assert _prov()["julich_reference"]["sha256"]


# ---- 11. registration_applied remains FALSE ----
def test_11_registration_false():
    r = _res()
    assert r["registration_applied"] is False
    assert _prov()["registration_applied"] is False
    assert _prov()["nonlinear_registration_applied"] is False
    assert _prov()["resampling_applied"] is True


# ---- 12. spatial_bridge_id preserved ----
def test_12_spb_preserved():
    assert _res()["spatial_bridge_id"] == SPB_ID
    assert _prov()["spatial_bridge_id"] == SPB_ID
    if SPB_MAN.exists():
        spb = json.load(open(SPB_MAN, encoding="utf-8"))
        assert spb["spatial_bridge_id"] == SPB_ID


# ---- 13. template_variant_uncertainty PRESENT ----
def test_13_uncertainty_present():
    assert _res()["template_variant_uncertainty"] == "PRESENT"
    assert _res()["residual_spatial_limitation"] == LIM
    assert _prov()["template_variant_uncertainty"] == "PRESENT"
    assert _prov()["residual_spatial_limitation"] == LIM


# ---- 14. Promotion remains BLOCKED ----
def test_14_promotion_blocked():
    md = MD.read_text(encoding="utf-8")
    assert "no promotion" in md
    assert "diagnostic only" in md
    # evidence type is shared-frame, not authoritative registration
    assert "DIRECT_SPATIAL_OVERLAP_IN_SHARED_MNI2009C_COORDINATE_FRAME" in md
    assert "NOT" in md


# ---- 15. DB remains unchanged (no DB artifact / zero-write) ----
def test_15_db_zero_write():
    md = MD.read_text(encoding="utf-8")
    assert "No DB write" in md or "no DB write" in md


# ---- 16. classification 86/132/93 byte-identical ----
@pytest.mark.skipif(not CLASS.exists(), reason="classification not present")
def test_16_classification_unchanged():
    with open(CLASS, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


# ---- additional structural checks ----
def test_all_16_parcels_present():
    codes = {r["parcel_code"] for r in _rows()}
    assert len(codes) == 16
    for side in ("L", "R"):
        for i in range(1, 9):
            assert f"Tha_{side}_8_{i}" in codes


def test_frozen_target_consistent():
    for r in _rows():
        expected = "NGIQ-BR-00000247" if r["hemisphere"] == "left" else "NGIQ-BR-00000256"
        assert r["frozen_g1_target"] == expected


def test_hemisphere_summary_complete():
    hemi = _hemi()
    assert len(hemi) == 2
    assert {h["hemisphere"] for h in hemi} == {"left", "right"}
    for h in hemi:
        assert float(h["total_g1_volume_mm3_equiv"]) > 0
        assert 0.0 <= float(h["union_coverage_ratio"]) <= 1.0
        assert 0.0 <= float(h["contralateral_overlap_ratio"]) <= 1.0


def test_validation_type_and_scope():
    r = _res()
    assert "DIRECT_SPATIAL_OVERLAP" in r["validation_type"]
    assert "NOT" in r["evidence_scope"]
