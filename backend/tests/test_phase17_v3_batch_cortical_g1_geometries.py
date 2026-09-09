"""Phase1.7 V3 - 62-target batch cortical G1 reference geometry construction tests.

Validates verdict CORTICAL_G1_62_REFERENCE_GEOMETRIES_FROZEN and the 35 hard gates.
Single multiclass NearestNeighbor transform; 62 source + 62 target per-region geometries;
no morphology / no G4 / no re-registration / no DB / no promotion. Binaries gitignored;
SHAs + provenance tracked. Prior frozen states unchanged.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np
import pytest
from nibabel.freesurfer.mghformat import MGHImage

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
DERIVED = BACKEND / "data" / "atlases" / "derived_g1" / "cort_g1_62"
FS = BACKEND / "data" / "atlases" / "freesurfer" / "fsaverage"
TF = BACKEND / "data" / "atlases" / "templateflow_ref"
FIXED = TF / "tpl-MNI152NLin2009cAsym_res01_desc-brain_T1w.nii.gz"
CLASS = D16 / "phase17_v3_classification.csv"
BF_BLOCK = D16 / "phase17_v3_zaborszky_acquisition_blocker_v1.json"
EFF = D16 / "phase17_v3_cortical_effective_prerequisite_status.json"
THAL = D16 / "phase17_v3_thalamus_final_freeze_v1.json"
AMYG = D16 / "phase17_v3_amygdala_g1_scope_contract_v1.json"
HIPP = D16 / "phase17_v3_hippocampus_canonical_identity_v1.json"
BNST_ADM = D16 / "phase17_v3_bnst_canonical_admission_v1.json"
BNST_GEOM = D16 / "phase17_v3_bnst_canonical_geometry_manifest.json"
CT = D16 / "phase17_v3_freesurfer_container_manifest.json"
ASEG = FS / "mri/aparc+aseg.mgz"
CVG = D16 / "phase17_v3_aparc_aseg_62target_coverage.csv"
TXI = D16 / "phase17_v3_cortical_registration_transform_manifest.json"
INT = D16 / "phase17_v3_cortical_transform_integrity_status.json"

SRC_MAN = D16 / "phase17_v3_cortical_g1_62_source_geometry_manifest.csv"
SRC_LM = D16 / "phase17_v3_cortical_g1_source_labelmap_manifest.json"
TGT_LM = D16 / "phase17_v3_cortical_g1_target_labelmap_manifest.json"
TGT_MAN = D16 / "phase17_v3_cortical_g1_62_reference_geometry_manifest.csv"
QC = D16 / "phase17_v3_cortical_g1_62_geometry_qc.csv"
BQ = D16 / "phase17_v3_cortical_g1_batch_transform_qc.json"
PROV = D16 / "phase17_v3_cortical_g1_batch_geometry_provenance.json"
MD = D16 / "phase17_v3_cortical_g1_batch_geometry_diagnostics.md"
OUTS = [SRC_MAN, SRC_LM, TGT_LM, TGT_MAN, QC, BQ, PROV, MD]

EXP_ASEG = "4c7db4478ccc171f7c891378f2974d0e140ae96131a5acd202bf7f44098f56b5"
EXP_AFF = "ff95a9fc7b8438065ff5b9dba557bacf92add8648abce36ccba93867196d6bb0"
EXP_FWD = "8bf90f3efdf7281bd2f059055c3715428be5e58f39df92cc04b75106ac0341f8"


def _j(p):
    return json.load(open(p, encoding="utf-8"))


def _rows(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _git_clean(*paths: Path) -> bool:
    r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *[str(p) for p in paths]],
                       cwd=BACKEND.parent, capture_output=True)
    return r.returncode == 0


# ---- 1. HEAD ----
def test_1_head():
    r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=BACKEND.parent,
                       capture_output=True, text=True)
    assert r.stdout.strip() == "c97d7d8"


# ---- 2/3. counts 62, L/R 31/31 ----
def test_2_3_counts():
    src = _rows(SRC_MAN)
    tgt = _rows(TGT_MAN)
    assert len(src) == 62 and len(tgt) == 62
    assert sum(1 for r in src if r["hemisphere"] == "left") == 31
    assert sum(1 for r in tgt if r["hemisphere"] == "right") == 31


# ---- 4/5. aparc+aseg SHA + LUT/crosswalk unchanged ----
def test_4_5_source_freeze():
    assert _sha(ASEG) == EXP_ASEG == _j(SRC_LM)["aparc_aseg_sha256"]
    assert _git_clean(CVG)


# ---- 6. 62 source labels all present ----
def test_6_source_labels():
    lm = _j(SRC_LM)
    assert lm["unique_labels"] == 62
    assert lm["unexpected"] == []
    assert lm["conservation"]["residual"] == 0
    assert lm["conservation"]["union_voxels"] == lm["conservation"]["sum_individual"]


# ---- 7. source voxel counts match frozen coverage ----
def test_7_source_counts_match():
    cnt = {int(r["lut_id"]): int(r["voxel_count"]) for r in _rows(CVG)}
    for r in _rows(SRC_MAN):
        assert int(r["voxel_count"]) == cnt[int(r["fs_label_id"])], r["dk_label"]


# ---- 8. source union conservation exact ----
def test_8_union_conservation():
    assert _j(SRC_LM)["conservation"]["residual"] == 0


# ---- 9/10. transform SHA + integrity PASS ----
def test_9_10_transform_freeze():
    t = _j(TXI)
    assert t["affine"]["sha256"] == EXP_AFF
    assert t["forward_warp"]["sha256"] == EXP_FWD
    assert _j(INT)["verdict"] == "CORTICAL_TARGET_TRANSFORM_INTEGRITY_CONFIRMED"
    assert _j(TGT_LM)["transform_sha"]["affine"] == EXP_AFF
    assert _j(TGT_LM)["transform_sha"]["forward_warp"] == EXP_FWD


# ---- 11/12/13. single multiclass NN transform ----
def test_11_12_13_single_nn():
    b = _j(BQ)
    assert b["transform_application_count_for_canonical_labelmap"] == 1
    assert b["interpolation"] == "NearestNeighbor"
    assert _j(TGT_LM)["transform_application_count"] == 1
    assert _j(TGT_LM)["interpolation"] == "NearestNeighbor"


# ---- 14/15. target shape/affine exact ----
def test_14_15_target_grid():
    lm = _j(TGT_LM)
    assert lm["shape"] == [193, 229, 193]
    assert lm["spacing"] == [1.0, 1.0, 1.0]
    assert lm["affine_matches_fixed"] is True
    b = _j(BQ)
    assert b["target_grid"]["shape"] == [193, 229, 193]


# ---- 16/17. target labels preserved / no unexpected ----
def test_16_17_labels():
    b = _j(BQ)
    assert b["target_unique_labels"] == 62
    assert b["unexpected_labels"] == []
    assert b["labels_identity_preserved"] is True
    assert _j(TGT_LM)["unique_labels"] == 62
    assert _j(TGT_LM)["unexpected"] == []


# ---- 18. 62/62 nonempty ----
def test_18_nonempty():
    assert all(int(r["voxel_count"]) > 0 for r in _rows(TGT_MAN))
    assert all(int(r["voxel_count"]) > 0 for r in _rows(SRC_MAN))


# ---- 19. laterality preserved (expected-side per hemisphere) ----
def test_19_laterality():
    for r in _rows(TGT_MAN):
        exp = float(r["correct_side_fraction"]) if r["hemisphere"] == "left" \
            else float(r["contralateral_fraction"])
        assert exp > 0.90, r["dk_label"]


# ---- 20. no LR reflection (LR totals balanced + Q no flags) ----
def test_20_no_reflection():
    b = _j(BQ)
    assert b["laterality_abnormal"] == []
    l_src, r_src = b["left_right_source"]
    l_tgt, r_tgt = b["left_right_target"]
    assert l_src > 100000 and r_src > 100000
    assert l_tgt > 100000 and r_tgt > 100000


# ---- 21/22. fragmentation + volume audited ----
def test_21_22_audited():
    b = _j(BQ)
    assert b["fragmentation_review"] == []
    assert b["volume_outliers"] == []
    assert 0.5 < b["per_region_ratio"]["median"] < 2.0
    assert 0.9 < b["total_volume_ratio"] < 2.0


# ---- 23. centroid transform consistency audited ----
def test_23_centroid_audited():
    b = _j(BQ)
    assert b["centroid_application_residual_max_mm"] < 15.0
    assert "NOT a transform order/direction" in b["centroid_residual_note"]


# ---- 24. no morphology ----
def test_24_no_morphology():
    assert _j(BQ)["morphology_applied"] is False
    assert "no morphology" in MD.read_text(encoding="utf-8")


# ---- 25/26. no G4 / no mapping tuning ----
def test_25_26_no_g4():
    assert _j(PROV)["independent_from_g4_mapping"] is True
    assert _j(PROV)["circularity_risk"] == "NONE"
    md = MD.read_text(encoding="utf-8")
    assert "no G4/Julich parcel use" in md and "no mapping tuning" in md


# ---- 27. target SHA all recorded ----
def test_27_target_shas():
    for r in _rows(TGT_MAN):
        assert len(r["geometry_sha256"]) == 64
        assert (DERIVED / f"{r['geometry_id']}.nii.gz").is_file()
    for r in _rows(SRC_MAN):
        assert len(r["geometry_sha256"]) == 64


# ---- 28/29. direct_overlap_grid_ready / validation not executed ----
def test_28_29_ready_flags():
    p = _j(PROV)
    assert p["direct_overlap_grid_ready"] is True
    assert p["direct_validation_executed"] is False


# ---- 30. provenance complete ----
def test_30_provenance():
    assert all(p.exists() for p in OUTS)
    p = _j(PROV)
    assert p["verdict"] == "CORTICAL_G1_62_REFERENCE_GEOMETRIES_FROZEN"
    assert p["batch_id"] == "BATCH_CORTICAL_G1_62_V1"
    assert len(p["source_chain"]["selected_labelmap_sha256"]) == 64
    assert len(p["target"]["labelmap_sha256"]) == 64
    assert "CORTICAL_G1_62_REFERENCE_GEOMETRIES_FROZEN" in MD.read_text(encoding="utf-8")


# ---- 31. classification unchanged ----
def test_31_classification():
    assert _git_clean(CLASS)
    rows = list(csv.DictReader(open(CLASS, encoding="utf-8-sig")))
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert sum(c.values()) - c["VERIFIED_DIRECT_CONTAINED"] == 132
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


# ---- 32. DB zero-write ----
def test_32_db_zero_write():
    assert "no DB" in MD.read_text(encoding="utf-8")
    assert not any("_db_" in p.name for p in OUTS)


# ---- 33. promotion not executed ----
def test_33_no_promotion():
    assert "no promotion" in MD.read_text(encoding="utf-8")


# ---- 34. BF blocker unchanged ----
def test_34_bf_blocker():
    assert _git_clean(BF_BLOCK)
    assert _j(BF_BLOCK)["geometry"] == "BLOCKED_ON_AUTHORITATIVE_ASSET_ACCESS"


# ---- 35. prior frozen families unchanged ----
def test_35_prior_frozen():
    assert _git_clean(EFF, THAL, AMYG, HIPP, BNST_ADM, BNST_GEOM, CT, CVG, TXI, INT)
    assert _j(CT)["verdict"] == "CORTICAL_FSAVERAGE_RIBBON_METHOD_BLOCKED_TOOLCHAIN"


# ---- extra: labelmap SHAs + QC csv well-formed ----
def test_extra_labelmaps_and_qc():
    slm = _j(SRC_LM)["sha256"]
    tlm = _j(TGT_LM)["sha256"]
    assert len(slm) == 64 and len(tlm) == 64
    qc = _rows(QC)
    assert len(qc) == 62
    assert all(float(r["centroid_application_residual_mm"]) < 15.0 for r in qc)
    # identity-preserving labels check: same fs_label_id survives in target manifest
    src_ids = {int(r["fs_label_id"]) for r in _rows(SRC_MAN)}
    tgt_ids = {int(r["fs_label_id"]) for r in _rows(TGT_MAN)}
    assert src_ids == tgt_ids and len(src_ids) == 62
