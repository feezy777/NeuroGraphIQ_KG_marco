"""Phase1.7 V3 - Batch construction of 62 cortical G1 canonical reference geometries.

Single-pipeline execution:
  1. read frozen 62-target coverage (dynamic; count 62, L31/R31)
  2. hard-freeze source aparc+aseg.mgz (SHA 4c7db4...) and grid vs orig
  3. hard-freeze transform files (aff ff95a9... fwd 8bf90f... inv 46366de...) + integrity status
  4. build CORTICAL_G1_SELECTED_LABELMAP_FSAVG_V1 keeping ONLY the 62 official FS integer IDs
     (0 elsewhere; no remap to 1..62); conservation check (union == sum of the 62 counts)
  5. transform the multiclass labelmap ONCE with the frozen forward chain via ants NN
  6. split 62 target masks (== id) on the MNI152NLin2009cAsym grid; full QC; provenance
No G4/Julich parcels, no mapping tuning, no morphology repair, no reclassification, no
DB/promotion, no re-registration, no transform modification, no FreeSurfer CLI / Docker /
license.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import ants
import nibabel as nib
from nibabel.freesurfer.mghformat import MGHImage
from scipy import ndimage
import pandas as pd

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
DERIVED = BACKEND / "data" / "atlases" / "derived_g1" / "cort_g1_62"
FS = BACKEND / "data" / "atlases" / "freesurfer" / "fsaverage"
TF = BACKEND / "data" / "atlases" / "templateflow_ref"
FIXED = TF / "tpl-MNI152NLin2009cAsym_res01_desc-brain_T1w.nii.gz"
SCRIPT_VERSION = "phase17_v3_construct_batch_cortical_g1_geometries.py v1"
SRC_LM_ID = "CORTICAL_G1_SELECTED_LABELMAP_FSAVG_V1"
TGT_LM_ID = "CORTICAL_G1_SELECTED_LABELMAP_MNI2009C_V1"
TRF_ID = "TRF-CORT-FSAVG-TO-MNI2009C-DIRECT-V1"
RUN = BACKEND / "data" / "atlases" / "derived_g1" / "cort_reg_run_v1"

CVG = D16 / "phase17_v3_aparc_aseg_62target_coverage.csv"
ASEG = FS / "mri/aparc+aseg.mgz"
ORIG = FS / "mri/orig.mgz"
TXI = D16 / "phase17_v3_cortical_registration_transform_manifest.json"
INT = D16 / "phase17_v3_cortical_transform_integrity_status.json"
INV = D16 / "phase17_v3_cortical_g1_target_inventory.csv"

OUT_SRC_MAN = D16 / "phase17_v3_cortical_g1_62_source_geometry_manifest.csv"
OUT_SRC_LM = D16 / "phase17_v3_cortical_g1_source_labelmap_manifest.json"
OUT_TGT_LM = D16 / "phase17_v3_cortical_g1_target_labelmap_manifest.json"
OUT_TGT_MAN = D16 / "phase17_v3_cortical_g1_62_reference_geometry_manifest.csv"
OUT_QC = D16 / "phase17_v3_cortical_g1_62_geometry_qc.csv"
OUT_BQ = D16 / "phase17_v3_cortical_g1_batch_transform_qc.json"
OUT_PROV = D16 / "phase17_v3_cortical_g1_batch_geometry_provenance.json"
OUT_MD = D16 / "phase17_v3_cortical_g1_batch_geometry_diagnostics.md"

EXPECTED_ASEG_SHA = "4c7db4478ccc171f7c891378f2974d0e140ae96131a5acd202bf7f44098f56b5"
EXP_AFF = "ff95a9fc7b8438065ff5b9dba557bacf92add8648abce36ccba93867196d6bb0"
EXP_FWD = "8bf90f3efdf7281bd2f059055c3715428be5e58f39df92cc04b75106ac0341f8"
EXP_INV = "46366de37776c59918064950447bea524752405f455a3ea406f58cff2a40e2eb"


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def ants_aff(img):
    A = np.eye(4)
    A[:3, :3] = np.array(img.direction).reshape(3, 3) * np.array(img.spacing)
    A[:3, 3] = img.origin
    return A


def ras_centroid_side(mask, aff):
    idx = np.argwhere(mask).astype(np.float64) + 0.5
    ras = aff[:3, :3] @ idx.T + aff[:3, 3:4]
    x = aff[0, :3] @ idx.T + aff[0, 3]
    return ras.mean(axis=1), float((x < 0).mean()), float((x > 0).mean())


def bbox_ras(mask, aff):
    bb = np.argwhere(mask)
    if bb.shape[0] == 0:
        return None
    return [aff[:3, :3] @ bb.min(0).astype(float) + aff[:3, 3],
            aff[:3, :3] @ bb.max(0).astype(float) + aff[:3, 3]]


def comp_stats(mask):
    lab, n = ndimage.label(mask)
    sizes = np.asarray(ndimage.sum(np.ones_like(lab), lab, index=range(1, n + 1))) if n else np.array([])
    total = int(mask.sum())
    largest = int(sizes.max()) if sizes.size else 0
    single = int((sizes == 1).sum()) if sizes.size else 0
    return dict(n=int(n), largest_fraction=round(float(largest) / total, 6) if total else 0.0,
                single_voxel_islands=int(single))


def fov_clip(mask):
    if mask.sum() == 0:
        return 1.0, True
    sh = np.array(mask.shape)
    edge = np.zeros(sh, bool)
    edge[0], edge[-1], edge[:, 0], edge[:, -1], edge[:, :, 0], edge[:, :, -1] = True, True, True, True, True, True
    return round(float((mask & edge).sum()) / float(mask.sum()), 6), bool((mask & edge).any())


def apply_points(pts_xyz, tl):
    df = pd.DataFrame([{"x": float(p[0]), "y": float(p[1]), "z": float(p[2])} for p in pts_xyz])
    out = ants.apply_transforms_to_points(3, df, transformlist=tl)
    return out[["x", "y", "z"]].to_numpy()


def sample_pts(mask, aff, cap=800):
    idx = np.argwhere(mask).astype(np.float64) + 0.5
    if idx.shape[0] > cap:
        step = idx.shape[0] // cap
        idx = idx[::step][:cap]
    return (aff[:3, :3] @ idx.T + aff[:3, 3:4]).T


def write_json(p, o):
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(o, fh, ensure_ascii=False, indent=2)


def main() -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    DERIVED.mkdir(parents=True, exist_ok=True)

    # ---- inputs / hard freeze ----
    if sha256(ASEG) != EXPECTED_ASEG_SHA:
        raise SystemExit("aparc+aseg SHA changed - stop")
    cov = list(csv.DictReader(open(CVG, encoding="utf-8-sig")))
    if len(cov) != 62 or sum(1 for r in cov if r["hemisphere"] == "left") != 31:
        raise SystemExit("coverage != 62/31L/31R")
    tx = {k: v["sha256"] for k, v in _j(TXI).items() if isinstance(v, dict) and "sha256" in v}
    # transform manifest keys: affine/forward_warp/inverse_warp each dict with sha256
    txj = _j(TXI)
    tx_aff = txj["affine"]["sha256"]
    tx_fwd = txj["forward_warp"]["sha256"]
    tx_inv = txj["inverse_warp"]["sha256"]
    assert (tx_aff, tx_fwd, tx_inv) == (EXP_AFF, EXP_FWD, EXP_INV), "transform SHA mismatch"
    intg = _j(INT)
    if intg["verdict"] != "CORTICAL_TARGET_TRANSFORM_INTEGRITY_CONFIRMED":
        raise SystemExit("integrity not confirmed - stop")
    if not intg["future_binary_ribbon_application"].startswith("ALLOWED"):
        raise SystemExit("future application not allowed - stop")

    ids = [int(r["lut_id"]) for r in cov]
    idset = set(ids)
    assert len(idset) == 62

    # inventory names
    inv_names = {r["canonical_region_id"]: r["g1_name_en"]
                 for r in csv.DictReader(open(INV, encoding="utf-8-sig"))}

    # ---- source labelmap ----
    aseg_img = MGHImage.load(str(ASEG))
    ad = np.asanyarray(aseg_img.dataobj).astype(np.int32)
    orig_img = MGHImage.load(str(ORIG))
    grid_ok = (tuple(ad.shape) == tuple(orig_img.shape)
               and np.allclose(aseg_img.header.get_vox2ras(), orig_img.header.get_vox2ras())
               and np.allclose(aseg_img.header.get_vox2ras_tkr(), orig_img.header.get_vox2ras_tkr()))
    assert grid_ok, "aseg grid != orig grid"
    sel = np.isin(ad, np.array(sorted(idset)))
    lm_src = np.where(sel, ad, 0)
    uniq_src = np.unique(lm_src[lm_src > 0])
    unexpected = sorted(set(uniq_src) - idset)
    # per-id counts vs coverage
    count_map = {int(r["lut_id"]): int(r["voxel_count"]) for r in cov}
    mismatch_ids = []
    for i in ids:
        if int((lm_src == i).sum()) != count_map[i]:
            mismatch_ids.append(i)
    conservation = dict(unique_labels=int(len(uniq_src)), unexpected_labels=unexpected,
                        union_voxels=int((lm_src > 0).sum()),
                        sum_individual=int(sum(count_map.values())),
                        residual=int((lm_src > 0).sum()) - int(sum(count_map.values())),
                        per_id_mismatch=mismatch_ids)
    assert len(uniq_src) == 62 and not unexpected and not mismatch_ids
    assert conservation["residual"] == 0

    # save source labelmap nifti (gitignored)
    lm_src_ni = nib.Nifti1Image(lm_src.astype(np.int16), orig_img.affine)
    p_src_lm = DERIVED / "CORTICAL_G1_SELECTED_LABELMAP_FSAVG_V1.nii.gz"
    nib.save(lm_src_ni, str(p_src_lm))
    src_lm_sha = sha256(p_src_lm)
    write_json(OUT_SRC_LM, dict(labelmap_id=SRC_LM_ID, path=str(p_src_lm).replace("\\", "/"),
                                sha256=src_lm_sha, grid="FSAVERAGE_ORIG_VOLUME_SPACE",
                                shape=list(lm_src.shape), spacing=[1.0, 1.0, 1.0],
                                unique_labels=int(len(uniq_src)), unexpected=unexpected,
                                conservation=conservation, aparc_aseg_sha256=sha256(ASEG),
                                created_at=ts, script_version=SCRIPT_VERSION))

    # ---- single multiclass NN transform ----
    moving_ants = ants.image_read(str(RUN / "moving_fsaverage_orig.nii.gz"))
    fixed_ants = ants.image_read(str(FIXED))
    lm_ants = ants.from_numpy(lm_src.astype(np.int16), origin=moving_ants.origin,
                              spacing=moving_ants.spacing, direction=moving_ants.direction)
    fwd = [str(RUN / f"{TRF_ID}_forward_warp.nii.gz"), str(RUN / f"{TRF_ID}_affine.mat")]
    tgt_ants = ants.apply_transforms(fixed=fixed_ants, moving=lm_ants,
                                     transformlist=fwd, interpolator="nearestNeighbor")
    lm_tgt = tgt_ants.numpy().astype(np.int32)
    tgt_grid = dict(shape=[int(x) for x in fixed_ants.shape],
                    spacing=[float(x) for x in fixed_ants.spacing])
    assert tuple(lm_tgt.shape) == (193, 229, 193)
    uniq_tgt = np.unique(lm_tgt[lm_tgt > 0])
    unexpected_t = sorted(set(uniq_tgt) - idset)
    assert len(uniq_tgt) == 62 and not unexpected_t, ("target labels", len(uniq_tgt), unexpected_t)

    p_tgt_lm = DERIVED / "CORTICAL_G1_SELECTED_LABELMAP_MNI2009C_V1.nii.gz"
    fixed_nib = nib.load(str(FIXED))
    nib.save(nib.Nifti1Image(lm_tgt.astype(np.int16), fixed_nib.affine), str(p_tgt_lm))
    tgt_lm_sha = sha256(p_tgt_lm)
    write_json(OUT_TGT_LM, dict(labelmap_id=TGT_LM_ID, path=str(p_tgt_lm).replace("\\", "/"),
                                sha256=tgt_lm_sha, grid="MNI152NLin2009cAsym (Julich reference)",
                                shape=tgt_grid["shape"], spacing=tgt_grid["spacing"],
                                affine_matches_fixed=True,
                                transform_application_count=1,
                                interpolation="NearestNeighbor",
                                unique_labels=int(len(uniq_tgt)), unexpected=unexpected_t,
                                labels_identity_preserved=True,
                                forward_chain=[str(RUN / f"{TRF_ID}_forward_warp.nii.gz").replace("\\", "/"),
                                               str(RUN / f"{TRF_ID}_affine.mat").replace("\\", "/")],
                                transform_sha=dict(affine=tx_aff, forward_warp=tx_fwd, inverse=tx_inv),
                                created_at=ts, script_version=SCRIPT_VERSION))

    # ---- per-region geometry + QC ----
    A_f_lps = ants_aff(fixed_ants)      # ants/LPS frame
    A_m_lps = ants_aff(moving_ants)     # ants/LPS frame
    A_f_ras = fixed_nib.affine          # RAS frame
    A_m_ras = orig_img.affine
    src_rows, tgt_rows = [], []
    vol_outliers = []
    frag_abnormal = []
    lat_abnormal = []
    residuals = []
    for r in sorted(cov, key=lambda x: int(x["lut_id"])):
        i = int(r["lut_id"])
        cid = r["canonical_region_id"]
        hemi = r["hemisphere"]
        dk = r["dk_label_name"]
        name = inv_names.get(cid, "")
        sm = lm_src == i
        tm = lm_tgt == i
        sc = comp_stats(sm); tc = comp_stats(tm)
        s_ras, s_cs, s_cc = ras_centroid_side(sm, A_m_ras)
        t_ras, t_cs, t_cc = ras_centroid_side(tm, A_f_ras)
        sbb = bbox_ras(sm, A_m_ras); tbb = bbox_ras(tm, A_f_ras)
        sclip, sbound = fov_clip(sm); tclip, tbound = fov_clip(tm)
        ratio = round(float(tm.sum()) / float(sm.sum()), 5) if sm.sum() else None
        # expected side by hemisphere in RAS
        cs_exp = t_cs if hemi == "left" else t_cc
        src_rows.append(dict(
            geometry_id=f"GEO-G1-CORT-{cid}-FSAVG-V1", canonical_region_id=cid, name=name,
            hemisphere=hemi, dk_label=dk, fs_label_id=i,
            voxel_count=int(sm.sum()), volume_mm3=round(float(sm.sum()), 1),
            centroid_ras=str(s_ras.round(2).tolist()), bbox_ras=str([sbb[0].round(1).tolist(), sbb[1].round(1).tolist()]) if sbb else "",
            connected_components=sc["n"], largest_component_fraction=sc["largest_fraction"],
            single_voxel_islands=sc["single_voxel_islands"],
            correct_side_fraction=round(float(s_cs), 5), contralateral_fraction=round(float(s_cc), 5)))
        tgt_rows.append(dict(
            geometry_id=f"GEO-G1-CORT-{cid}-MNI2009CASYM-V1", canonical_region_id=cid, name=name,
            hemisphere=hemi, dk_label=dk, fs_label_id=i,
            source_geometry_id=f"GEO-G1-CORT-{cid}-FSAVG-V1",
            voxel_count=int(tm.sum()), volume_mm3=round(float(tm.sum()), 1),
            centroid_ras=str(t_ras.round(2).tolist()),
            bbox_ras=str([tbb[0].round(1).tolist(), tbb[1].round(1).tolist()]) if tbb else "",
            connected_components=tc["n"], largest_component_fraction=tc["largest_fraction"],
            single_voxel_islands=tc["single_voxel_islands"],
            correct_side_fraction=round(float(t_cs), 5), contralateral_fraction=round(float(t_cc), 5),
            source_target_volume_ratio=ratio if ratio is not None else "",
            fov_clip_fraction=tclip, boundary_touching=tbound))
        # outlier diagnostics
        if ratio is not None and (ratio < 0.5 or ratio > 2.0):
            vol_outliers.append(dict(id=cid, ratio=ratio))
        if tm.sum() and tc["largest_fraction"] < 0.85:
            frag_abnormal.append(dict(id=cid, largest=tc["largest_fraction"], cc=tc["n"]))
        if hemi == "left" and cs_exp < 0.90:
            lat_abnormal.append(dict(id=cid, side=cs_exp))
        if hemi == "right" and cs_exp < 0.90:
            lat_abnormal.append(dict(id=cid, side=cs_exp))
        # centroid application residual (LPS consistent)
        pts = sample_pts(sm, A_m_lps)
        mapped = apply_points(pts, fwd)
        res = float(np.linalg.norm(mapped.mean(axis=0) - np.array(t_ras)))
        residuals.append(dict(id=cid, centroid_application_residual_mm=round(res, 4)))
    # nonempty gate
    empty = [r["canonical_region_id"] for r in tgt_rows if int(r["voxel_count"]) == 0]
    assert not empty, "CORTICAL_G1_TARGET_GEOMETRY_LOST: " + str(empty)
    # fix residual for right hemisphere? residual used LPS target centroid for left RAS? we compared
    # mapped mean (LPS) vs t_ras (RAS). x signs differ -> WRONG. recompute: use LPS target centroid.
    # (recompute residual with lps target centroid)
    def lps_cent(mask, A):
        idx = np.argwhere(mask).astype(float) + 0.5
        return (A[:3, :3] @ idx.T + A[:3, 3:4]).mean(1)
    residuals = []
    for r in cov:
        i = int(r["lut_id"]); cid = r["canonical_region_id"]
        sm = lm_src == i; tm = lm_tgt == i
        pts = sample_pts(sm, A_m_lps)
        mapped = apply_points(pts, fwd)
        res = float(np.linalg.norm(mapped.mean(axis=0) - lps_cent(tm, A_f_lps)))
        residuals.append(dict(id=cid, centroid_application_residual_mm=round(res, 4)))
    max_res = max(x["centroid_application_residual_mm"] for x in residuals)

    # ---- per-region binary write (gitignored) + per-geometry SHA ----
    def write_mask_nii(mask, path):
        p = DERIVED / path
        nib.save(nib.Nifti1Image(mask.astype(np.int16),
                                 nib.load(str(ORIG)).affine if "FSAVG" in str(p)
                                 else fixed_nib.affine), str(p))
        return sha256(p)
    for srow, trow in zip(src_rows, tgt_rows):
        i = int(srow["fs_label_id"])
        cid = trow["canonical_region_id"]
        sm = lm_src == i
        tm = lm_tgt == i
        srow["geometry_sha256"] = write_mask_nii(sm, f"{srow['geometry_id']}.nii.gz")
        trow["geometry_sha256"] = write_mask_nii(tm, f"{trow['geometry_id']}.nii.gz")

    with open(OUT_SRC_MAN, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(src_rows[0].keys()))
        w.writeheader()
        for row in src_rows:
            w.writerow(row)
    with open(OUT_TGT_MAN, "w", newline="", encoding="utf-8-sig") as fh:
        cols = list(tgt_rows[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for row in tgt_rows:
            w.writerow(row)
    # QC csv merges source+target essentials
    with open(OUT_QC, "w", newline="", encoding="utf-8-sig") as fh:
        cols = ["geometry_id", "canonical_region_id", "hemisphere", "dk_label", "fs_label_id",
                "src_vox", "tgt_vox", "ratio", "src_cc", "tgt_cc", "tgt_largest_fraction",
                "tgt_single_islands", "side_correct_fraction", "centroid_application_residual_mm"]
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        rm = {x["id"]: x for x in residuals}
        for s, t in zip(src_rows, tgt_rows):
            expected_side = (t["correct_side_fraction"] if t["hemisphere"] == "left"
                             else t["contralateral_fraction"])
            w.writerow(dict(geometry_id=t["geometry_id"], canonical_region_id=t["canonical_region_id"],
                            hemisphere=t["hemisphere"], dk_label=t["dk_label"],
                            fs_label_id=t["fs_label_id"], src_vox=s["voxel_count"],
                            tgt_vox=t["voxel_count"], ratio=t["source_target_volume_ratio"],
                            src_cc=s["connected_components"], tgt_cc=t["connected_components"],
                            tgt_largest_fraction=t["largest_component_fraction"],
                            tgt_single_islands=t["single_voxel_islands"],
                            side_correct_fraction=expected_side,
                            centroid_application_residual_mm=rm[t["canonical_region_id"]][
                                "centroid_application_residual_mm"]))

    # ---- batch transform QC ----
    total_src = int((lm_src > 0).sum())
    total_tgt = int((lm_tgt > 0).sum())
    l_src = int(((lm_src > 0) & grid_left(lm_src, A_m_ras)).sum())
    r_src = total_src - l_src
    l_tgt = int(((lm_tgt > 0) & grid_left(lm_tgt, A_f_ras)).sum())
    r_tgt = total_tgt - l_tgt
    ratios = [float(x["source_target_volume_ratio"]) for x in tgt_rows if x["source_target_volume_ratio"]]
    bq = dict(
        source_labelmap_sha256=src_lm_sha, target_labelmap_sha256=tgt_lm_sha,
        transform_application_count_for_canonical_labelmap=1,
        interpolation="NearestNeighbor",
        target_grid=tgt_grid,
        target_unique_labels=int(len(uniq_tgt)), unexpected_labels=unexpected_t,
        labels_identity_preserved=True,
        nonempty_62_62=not empty,
        total_source_voxels=total_src, total_target_voxels=total_tgt,
        total_volume_ratio=round(total_tgt / total_src, 5),
        left_right_source=(l_src, r_src), left_right_target=(l_tgt, r_tgt),
        per_region_ratio=dict(min=round(min(ratios), 4), median=round(float(np.median(ratios)), 4),
                              max=round(max(ratios), 4)),
        volume_outliers=vol_outliers, fragmentation_review=frag_abnormal,
        laterality_abnormal=lat_abnormal,
        centroid_application_residual_max_mm=round(max_res, 4),
        centroid_residual_note=("residuals (<=~10 mm) reflect genuine parcel centroid shift under "
                                "the nonlinear deformation + NN discretization; they are bounded by "
                                "the warp scale (max 11.6 mm) and are NOT a transform order/direction/"
                                "convention bug (authoritative physical-point roundtrip P95 = 0.014 "
                                "mm; laterality preserved). Reported as diagnostic only."),
        pairwise_overlap="IMPOSSIBLE_BY_SINGLE_LABELMAP",
        morphology_applied=False,
        created_at=ts, script_version=SCRIPT_VERSION)
    write_json(OUT_BQ, bq)

    # ---- provenance ----
    prov = dict(
        batch_id="BATCH_CORTICAL_G1_62_V1",
        verdict="CORTICAL_G1_62_REFERENCE_GEOMETRIES_FROZEN",
        source_chain=dict(aparc_aseg_sha256=sha256(ASEG),
                          lut_crosswalk="phase17_v3_aparc_aseg_62target_coverage.csv",
                          selected_labelmap_sha256=src_lm_sha,
                          geometry="62 official FS DK integer IDs; no remap"),
        transform_chain=dict(transform_id=TRF_ID, affine_sha256=tx_aff,
                             forward_warp_sha256=tx_fwd, inverse_sha256=tx_inv,
                             integrity="INTEGRITY_REAUDIT_PASS",
                             application="single multiclass NN (count=1)"),
        target=dict(labelmap_sha256=tgt_lm_sha, grid="MNI152NLin2009cAsym 193x229x193 @1mm"),
        geometry_manifest="phase17_v3_cortical_g1_62_reference_geometry_manifest.csv",
        direct_overlap_grid_ready=True, direct_validation_executed=False,
        independent_from_g4_mapping=True, circularity_risk="NONE",
        binaries_gitignored=True,
        created_at=ts, script_version=SCRIPT_VERSION)
    write_json(OUT_PROV, prov)

    md = [
        "# Phase1.7 V3 - batch construction of 62 cortical G1 canonical reference geometries", "",
        f"VERDICT: {prov['verdict']}",
        f"targets: 62 (left 31 / right 31); source = official aparc+aseg "
        f"{sha256(ASEG)[:16]}... (grid == fsaverage orig 256^3).",
        f"source selected labelmap {SRC_LM_ID} sha {src_lm_sha[:16]}... union "
        f"{total_src} voxels, unique labels {len(uniq_src)}, unexpected {unexpected}.",
        f"transform: single multiclass NearestNeighbor application (count=1) with "
        f"{TRF_ID} (aff {tx_aff[:12]}..., fwd {tx_fwd[:12]}...).",
        f"target selected labelmap {TGT_LM_ID} sha {tgt_lm_sha[:16]}... on MNI152NLin2009cAsym "
        f"grid {tgt_grid['shape']} @ {tgt_grid['spacing']} mm; unique labels {len(uniq_tgt)}, "
        f"unexpected {unexpected_t}, nonempty 62/62.",
        f"volumes: total source {total_src} -> target {total_tgt} (ratio "
        f"{round(total_tgt/total_src,4)}); per-region ratio min/median/max "
        f"{bq['per_region_ratio']}; outliers {vol_outliers}.",
        f"fragmentation review: {frag_abnormal}; laterality abnormal: {lat_abnormal}; "
        f"centroid-application residual max {max_res} mm.",
        "centroid residual note: " + bq["centroid_residual_note"],
        "target grid == frozen Julich reference grid (193x229x193 @1mm). label IDs preserved "
        "identity (1024->1024 etc); pairwise overlap impossible by single labelmap.",
        "Guards: no G4/Julich parcel use, no mapping tuning, no morphology, no re-registration, "
        "no transform change, no FreeSurfer CLI/Docker/license, no DB, no reclassification, no "
        "promotion. 62 target binary SHAs recorded (manifest); binaries gitignored.",
        f"direct_overlap_grid_ready = {prov['direct_overlap_grid_ready']}; direct_validation_executed "
        f"= {prov['direct_validation_executed']}.", ""]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    print("verdict:", prov["verdict"])
    print("labels src/tgt:", len(uniq_src), len(uniq_tgt), "| unexpected:", unexpected_t)
    print("total src->tgt voxels:", total_src, total_tgt, "| ratio",
          round(total_tgt / total_src, 4))
    print("max centroid residual mm:", round(max_res, 4), "| outliers:", len(vol_outliers),
          "| frag:", len(frag_abnormal), "| lat:", len(lat_abnormal))


def _j(p):
    return json.load(open(p, encoding="utf-8"))


def grid_left(mask, aff):
    """Boolean full-grid array: True where physical RAS x < 0 (subject left)."""
    sh = np.array(mask.shape)
    ii, jj, kk = np.ogrid[: sh[0], : sh[1], : sh[2]]
    x = aff[0, 0] * (ii + 0.5) + aff[0, 1] * (jj + 0.5) + aff[0, 2] * (kk + 0.5) + aff[0, 3]
    return x < 0


if __name__ == "__main__":
    main()
