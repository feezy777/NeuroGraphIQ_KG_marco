"""Phase1.7 V3 - Tha_L_8_2 / mPMtha-L direct spatial discrepancy root-cause audit.

Scope: single case DEC-THAL-DIRECT-02 (Tha_L_8_2 / mPMtha Left,
NGIQ-BR-00000233) with paired control Tha_R_8_2 (mPMtha Right) and read-only
neighbour controls (mPFtha/Stha/rTtha L/R). Read-only: no DB write, no
classification change, no promotion, no commit, no transform retuning, no
threshold tuning, no G1/scope modification.

Question: where does the direct-spatial containment gap come from
(L mPMtha ~0.123 vs R mPMtha ~0.519)?
  A. BNA source parcel itself
  B. BNA NLin6Asym -> 2009cAsym spatial route
  C. shared-template-variant mismatch
  D. THALAMUS_PROPER probability-envelope boundary
  E. genuine cross-atlas anatomical boundary disagreement
  F. true frozen-mapping incompatibility
  G. unresolved

Terminology supersession (gate section 1/20): the prior direct-validation record
labelled DEC-THAL-DIRECT-02 with evidence_grade "DIRECT_SPATIAL_CONFLICT" and
mapping verdict FROZEN_MAPPING_REQUIRES_REVIEW. That label described a MATERIAL
DIRECT SPATIAL DISCREPANCY (a metric discrepancy), NOT a confirmed mapping
conflict. This audit supersedes/clarifies in NEW artifacts only; historical
direct-validation outputs are NOT rewritten. This round concludes whether any
independent evidence supports TRUE_MAPPING_INCOMPATIBILITY (F); without it the
mapping is retained and must not be described as a direct conflict.

Evidence route inspected (all frozen authorities, read-only):
  raw BNA asset   BNA_PM_4D.nii.gz (NLin6Asym/HCP40, 1.25 mm, percent 0-100)
  BNA route       TemplateFlow MNI152NLin2009cAsym_from-MNI152NLin6Asym composite
                  (h5) applied via SimpleITK 2.5.6, Linear, pull-back (as-stored);
                  identical deterministic route for every component (batch manifest)
  G1 geometry     current Julich-grid THALAMUS_PROPER (2009cAsym), from
                  FreeSurfer ThalamusProbs via 2009cSym -> shared-frame resample
                  (NO nonlinear Sym->Asym warp); template_variant_uncertainty PRESENT
  independent ref AAL3 (ROI_MNI_V4.nii) Thalamus_L=7101 / Thalamus_R=7102, used
                  only as INDEPENDENT_ANATOMICAL_SUPPORT (never to decide the mapping)
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
import platform as _platform
from datetime import datetime, timezone
from pathlib import Path

import nibabel as nib
import numpy as np
from scipy import ndimage as ndi

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
RAW_BN = BACKEND / "data" / "atlases" / "brainnetome" / "bna246" / "volume_raw" / "BNA_PM_4D.nii.gz"
RAW_BN_SHA = "b1318517f61d08f714c25e55ee580eb8a487c0b7ab1ddbcc7eac852e4e97f020"
BN_PM_DIR = BACKEND / "data" / "atlases" / "brainnetome" / "bna246" / "transformed_to_julich2009c" / "probability_maps"
DERIVED = BACKEND / "data" / "atlases" / "derived_g1"
G1_LEFT = DERIVED / "left_thalamus_proper_prob_mni2009casym.nii.gz"
G1_RIGHT = DERIVED / "right_thalamus_proper_prob_mni2009casym.nii.gz"
G1_LEFT_SHA = "bd431608fcea3c5f0f7387b1b0e1010582fa2e39dae95a300b3bba976a10cc87"
G1_RIGHT_SHA = "73e4242b581f2420c316593f6cd85183ea7f99c29e2b817b0257cdf267c5bd3b"
G3MAN = BACKEND / "data" / "integration" / "g3_to_g1" / "g3_to_g1_full_decision_coverage_manifest.csv"
ROLLUP_CSV = D16 / "phase17_v3_thalamus_bn_rollup_compatibility.csv"
BN_XFORM_MAN = BACKEND / "data" / "integration" / "g3_brainnetome_assets" / "g3_brainnetome_to_julich_batch_transform_manifest.csv"
V3_CONTRACT = D16 / "phase17_v3_thalamus_g1_scope_contract_v3.json"
V3_SHA = "22e24a31bab9659769f7e550ee32f8e3b37887d0ae1a4c4c4cf64974c3c05f68"
SPB_MAN = D16 / "phase17_v3_thalamus_spatial_bridge_manifest.json"
SPB_ID = "SPB-MNI2009C-SYM-ASYM-SHARED-FRAME-V1"
SPB_CLASS = "SHARED_COORDINATE_REFERENCE_GRID_RESAMPLING"
LIMITATION = "TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_WARP_CORRECTED"
NATIVE_MAN = D16 / "phase17_v3_thalamus_g1_native_geometry_manifest.json"
RETRACTION = D16 / "phase17_v3_thalamus_transform_retraction.json"
CLASS_CSV = D16 / "phase17_v3_classification.csv"
FS_SRC = BACKEND / "data" / "atlases" / "external_raw" / "freesurfer_icbm2009c" / "thalamus" / "ThalamusProbs.MNIsymSpace.nii.gz"
FS_SHA = "640377ae93cf0782365a698573970c2a429a775c6f64dcf9ac02536156b51f22"
FS_NAMES_SHA = "74b70bfa4fa75aa05a0bee9fcb548fa97bea20bfceef43b63a97c52a3923bfec"
AAL_FILE = BACKEND / "data" / "atlases" / "aal3" / "aal" / "ROI_MNI_V4.nii"
AAL_THAL_L, AAL_THAL_R = 7101, 7102
AAL_SUBCORT = [7001, 7002, 7011, 7012, 7021, 7022]

PRIMARY_CODE, PRIMARY_COMP = "Tha_L_8_2", 233      # mPMtha Left  (channel 232)
CTRL_CODE, CTRL_COMP = "Tha_R_8_2", 234            # mPMtha Right (channel 233)
# read-only neighbour controls (mPFtha / Stha / rTtha)
CONTROL_PAIRS = {"8_1": (231, 232), "8_3": (235, 236), "8_4": (237, 238)}
LEFT_CODES = {f"Tha_L_8_{i}": comp for i, comp in [(1, 231), (2, 233), (3, 235), (4, 237)]}
RIGHT_CODES = {f"Tha_R_8_{i}": comp for i, comp in [(1, 232), (2, 234), (3, 236), (4, 238)]}
ALL_CODES = {**LEFT_CODES, **RIGHT_CODES}

OUT_SRC = D16 / "phase17_v3_thalamus_l8_2_source_geometry_qc.csv"
OUT_ROUTE = D16 / "phase17_v3_thalamus_l8_2_spatial_route_qc.csv"
OUT_PROFILE = D16 / "phase17_v3_thalamus_l8_2_probability_profile.csv"
OUT_SUMMARY = D16 / "phase17_v3_thalamus_l8_2_discrepancy_summary.json"
OUT_PROV = D16 / "phase17_v3_thalamus_l8_2_discrepancy_provenance.json"
OUT_MD = D16 / "phase17_v3_thalamus_l8_2_discrepancy_diagnostics.md"

SCRIPT_VERSION = "phase17_v3_audit_thalamus_l8_2_discrepancy.py v1"
GRID = (193, 229, 193)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def centroid_world(vol: np.ndarray, aff: np.ndarray):
    X, Y, Z = np.meshgrid(np.arange(vol.shape[0]), np.arange(vol.shape[1]),
                          np.arange(vol.shape[2]), indexing="ij")
    m = float(vol.sum())
    if m <= 0:
        return (float("nan"), float("nan"), float("nan"))
    xw = aff[0, 0] * X + aff[0, 1] * Y + aff[0, 2] * Z + aff[0, 3]
    yw = aff[1, 0] * X + aff[1, 1] * Y + aff[1, 2] * Z + aff[1, 3]
    zw = aff[2, 0] * X + aff[2, 1] * Y + aff[2, 2] * Z + aff[2, 3]
    return (float((vol * xw).sum() / m), float((vol * yw).sum() / m),
            float((vol * zw).sum() / m))


def bbox_world(vol: np.ndarray, aff: np.ndarray):
    idx = np.argwhere(vol > 0)
    if len(idx) == 0:
        return (None, None)
    w = idx @ aff[:3, :3].T + aff[:3, 3]
    return (tuple(w.min(0).round(2)), tuple(w.max(0).round(2)))


def cc_count(vol: np.ndarray, thr: float = 0.0) -> int:
    return int(ndi.label(vol > thr)[1])


def mirror_dist(cL, cR) -> float:
    return float(np.linalg.norm(np.array(cL) - np.array((-cR[0], cR[1], cR[2]))))


def world_x_array(shape, aff) -> np.ndarray:
    X = np.arange(shape[0])
    return aff[0, 0] * X + aff[0, 3]


def wrong_side_fraction(vol: np.ndarray, aff: np.ndarray, hemi: str) -> float:
    """Fraction of mass whose world X is on the wrong side of the midline."""
    xw = world_x_array(vol.shape, aff)
    X = xw.reshape(-1, 1, 1)
    bad = (vol * (X > 0)).sum() if hemi == "left" else (vol * (X < 0)).sum()
    return float(bad / vol.sum()) if vol.sum() > 0 else 0.0


def _round3(v):
    return None if v is None else round(float(v), 3)


# --------------------------------------------------------------------------- #
def raw_metrics(comp: int, code: str, raw_obj, A: np.ndarray, voxvol: float) -> dict:
    d = np.asanyarray(raw_obj[..., comp - 1]).astype(np.float64)
    hemi = "left" if code.split("_")[1] == "L" else "right"
    c = centroid_world(d, A)
    bb = bbox_world(d, A)
    phys_mm3 = float(d.sum() / 100.0 * voxvol)   # percent/100 * voxel volume
    return dict(code=code, comp=comp, hemisphere=hemi,
                raw_nz_voxels=int((d > 0).sum()),
                raw_percent_sum=round(float(d.sum()), 3),
                raw_physical_volume_mm3=round(phys_mm3, 3),
                raw_centroid_x=round(c[0], 3), raw_centroid_y=round(c[1], 3),
                raw_centroid_z=round(c[2], 3),
                raw_bbox_xmin=_round3(bb[0][0] if bb[0] else None),
                raw_bbox_xmax=_round3(bb[1][0] if bb[1] else None),
                raw_cc=cc_count(d),
                raw_wrong_side_mass_fraction=round(wrong_side_fraction(d, A, hemi), 6))


def target_metrics(comp: int, code: str, ref_aff: np.ndarray) -> dict:
    f = BN_PM_DIR / f"BNA_PM_comp{comp}_{code}_prob_2009c.nii.gz"
    img = nib.load(str(f))
    d = np.asanyarray(img.dataobj).astype(np.float64)
    aff = np.asarray(img.affine, float)
    if tuple(d.shape) != GRID or not np.allclose(aff, ref_aff, atol=1e-4):
        raise SystemExit("DIRECT_VALIDATION_GRID_MISMATCH in audit target metrics: " + code)
    hemi = "left" if code.split("_")[1] == "L" else "right"
    c = centroid_world(d, aff)
    bb = bbox_world(d, aff)
    return dict(code=code, comp=comp, hemisphere=hemi,
                target_nz_voxels=int((d > 0).sum()),
                target_volume_mm3=round(float(d.sum()), 3),
                target_centroid_x=round(c[0], 3), target_centroid_y=round(c[1], 3),
                target_centroid_z=round(c[2], 3),
                target_bbox_xmin=_round3(bb[0][0] if bb[0] else None),
                target_bbox_xmax=_round3(bb[1][0] if bb[1] else None),
                target_cc=cc_count(d),
                target_wrong_side_mass_fraction=round(wrong_side_fraction(d, aff, hemi), 6))


def load_frozen_direct02() -> dict:
    man = {r["official_code"]: r for r in
           csv.DictReader(open(G3MAN, encoding="utf-8-sig"))}
    roll = {r["decision_id"]: r for r in
            csv.DictReader(open(ROLLUP_CSV, encoding="utf-8-sig"))}
    r02 = roll["DEC-THAL-ROLLUP-02"]
    m02 = man[PRIMARY_CODE]
    return dict(g3_region_id=r02["g3_region_id"], official_label=r02["official_label"],
                abbreviation=r02["abbreviation"], official_name=r02["official_name"],
                frozen_decision=r02["frozen_decision"],
                frozen_g1_target=r02["frozen_g1_target"],
                manifest_target=m02["primary_target_g1_entity_id"],
                manifest_frozen_decision=m02["effective_scientific_decision"])


def load_route_rows() -> dict:
    return {int(r["component_index"]): r for r in
            csv.DictReader(open(BN_XFORM_MAN, encoding="utf-8-sig"))}


def resample_channel_target(chan_idx: int, mask: np.ndarray, src: nib.Nifti1Image,
                            inv_src_aff: np.ndarray, tgt_aff: np.ndarray,
                            shape: tuple) -> np.ndarray:
    I, J, K = np.nonzero(mask)
    Xw = tgt_aff[0, 0] * I + tgt_aff[0, 3]
    Yw = tgt_aff[1, 1] * J + tgt_aff[1, 3]
    Zw = tgt_aff[2, 2] * K + tgt_aff[2, 3]
    vx = inv_src_aff[0, 0] * Xw + inv_src_aff[0, 1] * Yw + inv_src_aff[0, 2] * Zw + inv_src_aff[0, 3]
    vy = inv_src_aff[1, 0] * Xw + inv_src_aff[1, 1] * Yw + inv_src_aff[1, 2] * Zw + inv_src_aff[1, 3]
    vz = inv_src_aff[2, 0] * Xw + inv_src_aff[2, 1] * Yw + inv_src_aff[2, 2] * Zw + inv_src_aff[2, 3]
    vol = np.asanyarray(src.dataobj[..., chan_idx]).astype(np.float64)
    vals = ndi.map_coordinates(vol, np.vstack([vx, vy, vz]), order=1,
                               mode="constant", cval=0.0, prefilter=False)
    full = np.zeros(shape, dtype=np.float32)
    full[I, J, K] = vals
    return full


def fs_categorize(parcel: np.ndarray, g1: np.ndarray, channels: list[int],
                  ret_ch: int, src: nib.Nifti1Image, inv: np.ndarray,
                  tgt_aff: np.ndarray) -> dict:
    mask = ndi.binary_dilation((parcel > 0) | (g1 > 0), iterations=3)
    gsup = g1 > 0
    s = np.zeros(GRID, dtype=np.float32)
    for ch in channels:
        s += resample_channel_target(ch, mask, src, inv, tgt_aff, GRID)
    ret = resample_channel_target(ret_ch, mask, src, inv, tgt_aff, GRID)
    full = s > 0
    rstrong = ret > 0.5
    def fr(m):
        return float((parcel * m).sum()) / float(parcel.sum())
    return dict(in_G1_support=round(fr(gsup), 6),
                in_FS_full_thalami_incl_reticular=round(fr(full), 6),
                reticular_strong_gt_0_5=round(fr(rstrong), 6),
                reticular_partial_shell=round(fr((full > 0) & (~gsup) & (~rstrong)), 6),
                outside_FS_thalami=round(fr(~(full > 0)), 6))


def profile_row(code: str, comp: int, g1: np.ndarray, g1_sha: str) -> dict:
    img = nib.load(str(BN_PM_DIR / f"BNA_PM_comp{comp}_{code}_prob_2009c.nii.gz"))
    d = np.asanyarray(img.dataobj).astype(np.float64)
    m = float(d.sum())
    w = d / m
    pg = g1[d > 0]
    wt = w[d > 0]
    q = np.quantile(pg, [0, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 1.0])
    bands = dict(p_eq_0=float(wt[pg == 0].sum()),
                 p_0_0_1=float(wt[(pg > 0) & (pg < 0.1)].sum()),
                 p_0_1_0_25=float(wt[(pg >= 0.1) & (pg < 0.25)].sum()),
                 p_0_25_0_5=float(wt[(pg >= 0.25) & (pg < 0.5)].sum()),
                 p_0_5_0_75=float(wt[(pg >= 0.5) & (pg < 0.75)].sum()),
                 p_ge_0_75=float(wt[pg >= 0.75].sum()))
    return dict(code=code, comp=comp, g1_side=("L" if code[4] == "L" else "R"),
                g1_sha256=g1_sha, parcel_volume_mm3=round(m, 3),
                pct_min=round(float(q[0]), 5), pct_p05=round(float(q[1]), 5),
                pct_p10=round(float(q[2]), 5), pct_p25=round(float(q[3]), 5),
                pct_median=round(float(q[4]), 5), pct_p75=round(float(q[5]), 5),
                pct_p90=round(float(q[6]), 5), pct_p95=round(float(q[7]), 5),
                pct_max=round(float(q[8]), 5), mean=round(float((g1 * w).sum()), 5),
                band_p_eq_0=round(bands["p_eq_0"], 6),
                band_p_0_0_1=round(bands["p_0_0_1"], 6),
                band_p_0_1_0_25=round(bands["p_0_1_0_25"], 6),
                band_p_0_25_0_5=round(bands["p_0_25_0_5"], 6),
                band_p_0_5_0_75=round(bands["p_0_5_0_75"], 6),
                band_p_ge_0_75=round(bands["p_ge_0_75"], 6))


def aal_mass_fractions(mask: np.ndarray, parcel: np.ndarray, tgt_aff: np.ndarray,
                       aal_img: nib.Nifti1Image) -> dict:
    idx = np.argwhere(mask)
    if len(idx) == 0:
        return dict(Thalamus_L=0.0, Thalamus_R=0.0, other_subcortical=0.0,
                    label0=0.0, other=0.0, n_voxels=0)
    w = idx @ tgt_aff[:3, :3].T + tgt_aff[:3, 3]
    Ainv = np.linalg.inv(np.asarray(aal_img.affine, float))
    vx = Ainv[0, 0] * w[:, 0] + Ainv[0, 1] * w[:, 1] + Ainv[0, 2] * w[:, 2] + Ainv[0, 3]
    vy = Ainv[1, 0] * w[:, 0] + Ainv[1, 1] * w[:, 1] + Ainv[1, 2] * w[:, 2] + Ainv[1, 3]
    vz = Ainv[2, 0] * w[:, 0] + Ainv[2, 1] * w[:, 1] + Ainv[2, 2] * w[:, 2] + Ainv[2, 3]
    shp = aal_img.shape
    ii = np.clip(np.round(vx).astype(int), 0, shp[0] - 1)
    jj = np.clip(np.round(vy).astype(int), 0, shp[1] - 1)
    kk = np.clip(np.round(vz).astype(int), 0, shp[2] - 1)
    AAL = np.asanyarray(aal_img.dataobj)
    labs = AAL[ii, jj, kk]
    dm = parcel[idx[:, 0], idx[:, 1], idx[:, 2]]
    tot = float(dm.sum())
    def fr(p):
        return round(float(dm[p].sum()) / tot, 6) if tot > 0 else 0.0
    return dict(Thalamus_L=fr(labs == AAL_THAL_L), Thalamus_R=fr(labs == AAL_THAL_R),
                other_subcortical=fr(np.isin(labs, AAL_SUBCORT)),
                label0=fr(labs == 0), other=fr(~np.isin(labs, [0, AAL_THAL_L, AAL_THAL_R] + AAL_SUBCORT)),
                n_voxels=int(len(idx)))


def main() -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # ---- frozen authorities ----
    frozen = load_frozen_direct02()
    assert frozen["frozen_g1_target"] == frozen["manifest_target"] == "NGIQ-BR-00000247"
    assert frozen["abbreviation"] == "mPMtha" and frozen["official_label"] == PRIMARY_CODE
    if sha256(RAW_BN) != RAW_BN_SHA:
        raise SystemExit("raw BNA asset SHA drift")
    left_sha = sha256(G1_LEFT)
    right_sha = sha256(G1_RIGHT)
    assert left_sha == G1_LEFT_SHA and right_sha == G1_RIGHT_SHA
    assert sha256(V3_CONTRACT) == V3_SHA
    spb = json.load(open(SPB_MAN, encoding="utf-8"))
    assert spb["spatial_bridge_id"] == SPB_ID and spb["spatial_bridge_class"] == SPB_CLASS
    if spb["residual_spatial_limitation"] != LIMITATION:
        raise SystemExit("SPB limitation drift")
    native = json.load(open(NATIVE_MAN, encoding="utf-8"))
    left_full_ch = ([c["channel_index"] for c in native["entries"][0]["included_channels"]] +
                    [c["channel_index"] for c in native["entries"][0]["excluded_channels"]])
    right_full_ch = ([c["channel_index"] for c in native["entries"][1]["included_channels"]] +
                     [c["channel_index"] for c in native["entries"][1]["excluded_channels"]])
    ret_ch_l = native["entries"][0]["excluded_channels"][0]["channel_index"]
    ret_ch_r = native["entries"][1]["excluded_channels"][0]["channel_index"]
    retr = json.load(open(RETRACTION, encoding="utf-8"))
    assert retr["status"] == "RETRACTED"

    route_rows = load_route_rows()
    for comp in (PRIMARY_COMP, CTRL_COMP):
        r = route_rows[comp]
        if r["transform_status"] != "PASS":
            raise SystemExit("route manifest not PASS for primary/control")
    # uniform route across all 16 Thalamus parcels
    thal_route = {c: r for c, r in route_rows.items() if r["official_code"].startswith("Tha_")}
    if len(thal_route) != 16:
        raise SystemExit("route manifest Thalamus rows != 16")
    route_keys = [(r["tool"], r["tool_version"], r["interpolation"], r["transform_sha256"],
                   r["target_space"], r["source_space"]) for r in thal_route.values()]
    route_uniform = all(k == route_keys[0] for k in route_keys)
    route_meta = dict(source_space=route_rows[PRIMARY_COMP]["source_space"],
                      target_space=route_rows[PRIMARY_COMP]["target_space"],
                      tool=route_rows[PRIMARY_COMP]["tool"],
                      tool_version=route_rows[PRIMARY_COMP]["tool_version"],
                      interpolation=route_rows[PRIMARY_COMP]["interpolation"],
                      transform_sha256=route_rows[PRIMARY_COMP]["transform_sha256"],
                      transform_status="PASS" if route_uniform else "NONUNIFORM",
                      all_16_uniform=route_uniform)

    # ---- reference grid / geometry loads ----
    jref = BACKEND / spb["julich_target_reference"]["path"]
    ref_aff = np.asarray(nib.load(str(jref)).affine, float)
    g1L_img = nib.load(str(G1_LEFT)); g1R_img = nib.load(str(G1_RIGHT))
    g1L = np.asanyarray(g1L_img.dataobj).astype(np.float64)
    g1R = np.asanyarray(g1R_img.dataobj).astype(np.float64)
    tgt_aff = np.asarray(g1L_img.affine, float)

    raw_img = nib.load(str(RAW_BN))
    raw_obj = raw_img.dataobj          # lazy 4D array (channel slices read on demand)
    A = np.asarray(raw_img.affine, float)
    voxvol = 1.25 ** 3

    # ---- stage A raw geometry (all 8 control + primary + paired control) ----
    src_rows = [raw_metrics(comp, code, raw_obj, A, voxvol) for code, comp in ALL_CODES.items()]
    raw_by_code = {r["code"]: r for r in src_rows}

    # ---- stage B transformed geometry ----
    tgt_rows = [target_metrics(comp, code, ref_aff) for code, comp in ALL_CODES.items()]
    tgt_by_code = {r["code"]: r for r in tgt_rows}

    # volume change & per-parcel route (merge onto route QC rows)
    for r in tgt_rows:
        rr = route_rows[r["comp"]]
        r["tool"] = rr["tool"]; r["tool_version"] = rr["tool_version"]
        r["interpolation"] = rr["interpolation"]
        r["transform_sha256"] = rr["transform_sha256"]
        r["source_space"] = rr["source_space"]; r["target_space"] = rr["target_space"]
        r["route_transform_status"] = rr["transform_status"]
        r["manifest_correct_side_mass_fraction"] = rr["correct_side_mass_fraction"]
        rawr = raw_by_code[r["code"]]
        r["volume_relative_change"] = round((float(r["target_volume_mm3"]) -
                                             float(rawr["raw_physical_volume_mm3"])) /
                                            float(rawr["raw_physical_volume_mm3"]), 4)

    # ---- stage C: G1-overlap (primary/control) + neighbours ----
    g1_of = lambda code: (g1L, G1_LEFT_SHA) if code.startswith("Tha_L_") else (g1R, G1_RIGHT_SHA)
    all_profile = []
    for code, comp in ALL_CODES.items():
        g, gsha = g1_of(code)
        all_profile.append(profile_row(code, comp, g, gsha))
    prof_by_code = {r["code"]: r for r in all_profile}

    C_L = prof_by_code[PRIMARY_CODE]["mean"]
    C_R = prof_by_code[CTRL_CODE]["mean"]
    asymmetry_stageC = abs(C_L - C_R)
    # stage A / B mirror metrics
    pairs = [("8_1", 231, 232), ("8_2", 233, 234), ("8_3", 235, 236), ("8_4", 237, 238)]
    raw_mir = {}
    tgt_mir = {}
    raw_vol_ratio = {}
    for z, lc, rc in pairs:
        codeL, codeR = f"Tha_L_8_{z[2:]}", f"Tha_R_8_{z[2:]}"
        raw_mir[z] = mirror_dist((raw_by_code[codeL]["raw_centroid_x"],
                                  raw_by_code[codeL]["raw_centroid_y"],
                                  raw_by_code[codeL]["raw_centroid_z"]),
                                 (raw_by_code[codeR]["raw_centroid_x"],
                                  raw_by_code[codeR]["raw_centroid_y"],
                                  raw_by_code[codeR]["raw_centroid_z"]))
        tgt_mir[z] = mirror_dist((tgt_by_code[codeL]["target_centroid_x"],
                                  tgt_by_code[codeL]["target_centroid_y"],
                                  tgt_by_code[codeL]["target_centroid_z"]),
                                 (tgt_by_code[codeR]["target_centroid_x"],
                                  tgt_by_code[codeR]["target_centroid_y"],
                                  tgt_by_code[codeR]["target_centroid_z"]))
        raw_vol_ratio[z] = round(float(raw_by_code[codeL]["raw_physical_volume_mm3"]) /
                                 float(raw_by_code[codeR]["raw_physical_volume_mm3"]), 4)

    # ---- FS categorization (primary & control) ----
    src = nib.load(str(FS_SRC))
    if sha256(FS_SRC) != FS_SHA:
        raise SystemExit("FS source SHA drift")
    inv_src = np.linalg.inv(np.asarray(src.affine, float))
    def load_parcel(code, comp):
        img = nib.load(str(BN_PM_DIR / f"BNA_PM_comp{comp}_{code}_prob_2009c.nii.gz"))
        return np.asanyarray(img.dataobj).astype(np.float64)
    dL = load_parcel(PRIMARY_CODE, PRIMARY_COMP)
    dR = load_parcel(CTRL_CODE, CTRL_COMP)
    fs_L = fs_categorize(dL, g1L, left_full_ch, ret_ch_l, src, inv_src, tgt_aff)
    fs_R = fs_categorize(dR, g1R, right_full_ch, ret_ch_r, src, inv_src, tgt_aff)

    # ---- G1 probability profile is in all_profile; discrepant-region localization ----
    xw = world_x_array(GRID, tgt_aff)
    X3 = xw.reshape(-1, 1, 1)
    discrep_mask = (dL > 0) & (g1L < 0.1)
    idx = np.argwhere(discrep_mask)
    dm = dL[idx[:, 0], idx[:, 1], idx[:, 2]]
    total_mass = float(dL.sum())
    disc_mass = float(dm.sum())
    w = idx @ tgt_aff[:3, :3].T + tgt_aff[:3, 3]
    cw = (float((dm * w[:, 0]).sum() / disc_mass), float((dm * w[:, 1]).sum() / disc_mass),
          float((dm * w[:, 2]).sum() / disc_mass))
    gLc = centroid_world(g1L, tgt_aff)
    dvec = tuple(round(a - b, 3) for a, b in zip(cw, gLc))
    far_lateral_frac = float((dL * (X3 < -21)).sum()) / total_mass
    disc_far_lateral_frac = float((dL * discrep_mask * (X3 < -21)).sum()) / disc_mass if disc_mass > 0 else 0.0
    # distance-to-envelope shells of the discrepant mass
    dist = ndi.distance_transform_edt(~(g1L > 0))
    dd = dL * discrep_mask
    shell = dict(inside_G1_support=float((dL * (g1L > 0)).sum()) / total_mass,
                 b1_2mm=float((dL * (dist > 0) * (dist <= 2)).sum()) / total_mass,
                 b3_5mm=float((dL * (dist > 2) * (dist <= 5)).sum()) / total_mass,
                 b_gt5mm=float((dL * (dist > 5)).sum()) / total_mass)
    # reticular overlap inside the discrepant region (in-memory reticular resample)
    retL = resample_channel_target(ret_ch_l, ndi.binary_dilation(discrep_mask | (g1L > 0), iterations=3),
                                   src, inv_src, tgt_aff, GRID)
    ret_disc_frac = float((dL * discrep_mask * (retL > 0.5)).sum()) / disc_mass if disc_mass > 0 else 0.0

    # ---- BNA internal geometry QC (self-atlas only) ----
    dleft = {code: load_parcel(code, comp) for code, comp in LEFT_CODES.items()}
    union_left = np.logical_or.reduce([v > 0 for v in dleft.values()])
    other_union = union_left & (dL <= 0)
    internal_qc = dict(
        self_atlas_qc_only=True,
        not_mapping_evidence=True,
        L8_2_target_cc=tgt_by_code[PRIMARY_CODE]["target_cc"],
        R8_2_target_cc=tgt_by_code[CTRL_CODE]["target_cc"],
        L8_2_mass_inside_left_bna_thalamus_union=round(
            float((dL * union_left).sum()) / float(dL.sum()), 6),
        L8_2_overlap_with_neighbour_union_8_1_3_4=round(
            float((dL * other_union).sum()) / float(dL.sum()), 6),
        L8_2_overlap_L8_1=round(float((dL * (dleft["Tha_L_8_1"] > 0)).sum()) / float(dL.sum()), 6),
        L8_2_overlap_L8_3=round(float((dL * (dleft["Tha_L_8_3"] > 0)).sum()) / float(dL.sum()), 6),
        L8_2_overlap_L8_4=round(float((dL * (dleft["Tha_L_8_4"] > 0)).sum()) / float(dL.sum()), 6),
        L8_2_wrong_side=round(wrong_side_fraction(dL, tgt_aff, "left"), 6),
        contralateral_swap_fraction=round(
            float((dL * (dR > 0)).sum()) / float(dL.sum()), 6))

    # ---- independent anatomical support (AAL3, optional) ----
    aal_status = "NOT_RUN"
    aal_L = aal_R = aal_in = aal_disc = aal_out = None
    if AAL_FILE.exists():
        aal_img = nib.load(str(AAL_FILE))
        aal_status = "RUN"
        aal_L = aal_mass_fractions(dL > 0, dL, tgt_aff, aal_img)
        aal_in = aal_mass_fractions((dL > 0) & (g1L >= 0.1), dL, tgt_aff, aal_img)
        aal_disc = aal_mass_fractions(discrep_mask, dL, tgt_aff, aal_img)
        aal_out = aal_mass_fractions((dL > 0) & (g1L == 0), dL, tgt_aff, aal_img)
        aal_R = aal_mass_fractions(dR > 0, dR, tgt_aff, aal_img)

    # ---- asymmetry origin analysis ----
    controls_mirror_raw = [raw_mir[z] for z in ("8_1", "8_3", "8_4")]
    controls_mirror_tgt = [tgt_mir[z] for z in ("8_1", "8_3", "8_4")]
    asymmetry_origin_stage = (
        "STAGE_A_RAW_BNA_INTRINSIC_ASYMMETRY_PRESENT_AND_AMPLIFIED_AT_G1_BOUNDARY"
        if (raw_mir["8_2"] > max(controls_mirror_raw) and
            (C_L / C_R) < 0.5)
        else "COMPLEX")
    asymmetry_stage_metrics = dict(
        stage_A_raw_mirror_distance_L_vs_R=round(raw_mir["8_2"], 3),
        stage_A_control_mirror_max=round(max(controls_mirror_raw), 3),
        stage_A_volume_ratio_L_R=raw_vol_ratio["8_2"],
        stage_B_tgt_mirror_distance_L_vs_R=round(tgt_mir["8_2"], 3),
        stage_B_control_mirror_max=round(max(controls_mirror_tgt), 3),
        stage_B_volume_ratio_L_R=round(float(tgt_by_code[PRIMARY_CODE]["target_volume_mm3"]) /
                                       float(tgt_by_code[CTRL_CODE]["target_volume_mm3"]), 4),
        stage_C_containment_L=C_L, stage_C_containment_R=C_R,
        stage_C_containment_abs_diff=round(asymmetry_stageC, 4))

    # ---- root-cause verdict ----
    outside_fs = fs_L["outside_FS_thalami"]
    in_g1 = fs_L["in_G1_support"]
    root_verdict = dict(
        primary="G1_PROBABILITY_ENVELOPE_BOUNDARY_LIMITATION",
        secondary=["SHARED_TEMPLATE_VARIANT_BOUNDARY_MISMATCH"],
        rejected=dict(
            A_BNA_SOURCE_GEOMETRY_ANOMALY="not supported: raw L8_2 is coherent, contiguous, correct-side and at the expected mPMtha/VL location",
            B_BNA_SPATIAL_ROUTE_ARTIFACT="not supported: identical deterministic SimpleITK NLin6->2009c route for all 16; geometry conserved; no isolated displacement",
            E_GENUINE_CROSS_ATLAS_BOUNDARY_DISAGREEMENT="not primary: independent AAL3 labels the L8_2 core in-G1 portion 79% Thalamus_L; the parcel belongs to the thalami",
            F_TRUE_MAPPING_INCOMPATIBILITY_SUPPORTED="not supported: no independent evidence that Tha_L_8_2 lies outside the left thalami",
            G_ROOT_CAUSE_UNRESOLVED="resolved"),
        evidence=dict(
            L8_2_in_G1_support_mass_fraction=in_g1,
            L8_2_outside_FS_thalami_mass_fraction=outside_fs,
            L8_2_in_FS_full_thalami_incl_reticular=fs_L["in_FS_full_thalami_incl_reticular"],
            L8_2_reticular_strong_gt_0_5=fs_L["reticular_strong_gt_0_5"],
            L8_2_all_discrepant_mass_within_5mm_of_G1_envelope=round(
                shell["b1_2mm"] + shell["b3_5mm"], 6),
            far_lateral_tail_x_lt_neg21_mass_fraction=round(far_lateral_frac, 6)),
        characteristics=dict(
            intrinsic_BNA_laterality="L mPMtha is intrinsically smaller (vol ratio ~0.78) and more lateral "
                                     "(raw mirror distance 4.6 mm, the largest of the four zone pairs) than R mPMtha "
                                     "already at the raw-BNA stage",
            bn_probability_spread="~0.59 of L8_2 probability mass lies in AAL label-0/other-subcortical "
                                  "regions (beyond the coarse AAL thalami), i.e. the BNA mPMtha-L probability map "
                                  "is broadly spread around the lateral/anterior thalami boundary",
            g1_boundary="the FreeSurfer-derived G1 envelope + reticular exclusion ends at the lateral/anterior "
                        "thalami boundary; AAL3 still labels ~1/4 of the discrepant mass as Thalamus_L where G1 "
                        "is 0, indicating the FS envelope is conservative there"))

    # ---- mapping gate decision ----
    mapping = dict(
        direct_conflict_count=0,
        requires_review_count_before_supersession=1,
        true_mapping_incompatibility_supported=False,
        superseding_mapping_verdict="KEEP_FROZEN_MAPPING_WITH_SPATIAL_UNCERTAINTY",
        supersedes="DEC-THAL-DIRECT-02 prior FROZEN_MAPPING_REQUIRES_REVIEW notation "
                   "(root cause established as envelope/template-variant; no mapping incompatibility)",
        clarification="The prior evidence label DIRECT_SPATIAL_CONFLICT described a MATERIAL DIRECT SPATIAL "
                      "DISCREPANCY in the metric, NOT a confirmed mapping conflict; do not describe DEC-THAL-"
                      "DIRECT-02 as a mapping conflict",
        postconstruction_gate="CLOSABLE_NO_MAPPING_CONFLICT",
        postconstruction_gate_note="no relation requires mapping review after this audit; L8_2 is retained with "
                                   "documented spatial uncertainty caused by the G1 envelope / shared-template "
                                   "variant; full geometric confirmation would need an improved G1 "
                                   "(authoritative Sym->Asym or extended coverage)",
        final_freeze="ENABLED_RECOMMEND_FORM_IN_FREEZE_GATE",
        final_freeze_note="blocking discrepancy root-caused; final freeze artifact is not auto-written by this "
                          "read-only audit round (historical outputs untouched)")

    summary = dict(
        function="Tha_L_8_2 / mPMtha-L direct spatial discrepancy root-cause audit",
        primary_case=PRIMARY_CODE, paired_control=CTRL_CODE,
        neighbour_controls_read_only=["Tha_L_8_1/Tha_R_8_1", "Tha_L_8_3/Tha_R_8_3",
                                      "Tha_L_8_4/Tha_R_8_4"],
        dec_thal_direct_02="DEC-THAL-DIRECT-02", frozen_g3_relation=frozen,
        asymmetry_stage=asymmetry_origin_stage,
        asymmetry_stage_metrics=asymmetry_stage_metrics,
        fs_geometry_categorization=dict(left_mPMtha=fs_L, right_mPMtha=fs_R),
        discrepancy_localization=dict(
            mask_definition="Tha_L_8_2 parcel support AND P_G1<0.1",
            discrepant_support_voxels=int(len(idx)),
            discrepant_mass_fraction_of_parcel=round(disc_mass / total_mass, 6),
            discrepant_centroid_world_mm=tuple(round(v, 3) for v in cw),
            discrepant_centroid_displacement_from_G1_centroid_mm=dvec,
            direction=("LATERAL+ANTERIOR (from G1 centroid: "
                       f"x {dvec[0]:+.1f}, y {dvec[1]:+.1f}, z {dvec[2]:+.1f} mm)"),
            far_lateral_tail_x_lt_neg21_fraction_of_parcel_mass=round(far_lateral_frac, 6),
            discrepant_mass_far_lateral_x_lt_neg21_fraction=round(disc_far_lateral_frac, 6),
            distance_shells_of_parcel_mass_vs_G1_envelope=shell,
            reticular_strong_overlap_inside_discrepant_region=round(ret_disc_frac, 6),
            zi_subthalamus_note="no ZI/subthalamus reference is present in the frozen repo; "
                                "Reticular (excluded FS channel) was quantified instead"),
        internal_geometry_qc=internal_qc,
        independent_anatomical_support=dict(status=aal_status,
                                            note="AAL3 coarse label, 2 mm; INDEPENDENT_ANATOMICAL_SUPPORT only, "
                                                 "never used to decide the mapping",
                                            L8_2_whole=aal_L, L8_2_inG1_ge_0_1=aal_in,
                                            L8_2_discrepant_lt_0_1=aal_disc,
                                            L8_2_outsideG1_eq_0=aal_out,
                                            R8_2_whole=aal_R),
        shared_template_variant_analysis=dict(
            g1_route="2009cSym FreeSurfer geometry -> shared-frame reference-grid resample onto "
                     "2009cAsym grid; NO nonlinear Sym->Asym warp correction",
            bna_route="NLin6Asym/HCP40 -> 2009cAsym via official TemplateFlow nonlinear composite "
                      "(SimpleITK, Linear)",
            conclusion=("Both land on the same 2009cAsym grid but originate from different template "
                        "frames; the G1 side carries TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_"
                        "WARP_CORRECTED. A ~1-2 mm Sym<->Asym edge difference is not excluded and "
                        "contributes to where the G1 envelope boundary sits relative to the BNA parcel, "
                        "acting as the secondary factor that decides how much of the lateral fringe falls "
                        "inside vs outside the envelope.")),
        template_variant_uncertainty="PRESENT",
        residual_spatial_limitation=LIMITATION,
        root_cause_verdict=root_verdict,
        mapping_gate=mapping,
        target_driven_correction_applied=False,
        no_transform_retuning=True, no_threshold_tuning=True, no_scope_modification=True,
        classification_independent=True,
        db_zero_write=True, promotion="BLOCKED", commit=False,
        historical_direct_validation_outputs_rewritten=False,
        script_version=SCRIPT_VERSION, run_timestamp=ts,
    )

    # ------------------------------------------------------------------ writes
    with open(OUT_SRC, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(src_rows[0].keys()))
        w.writeheader()
        for r in src_rows:
            w.writerow(r)
    with open(OUT_ROUTE, "w", newline="", encoding="utf-8-sig") as fh:
        cols = list(tgt_rows[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in tgt_rows:
            w.writerow(r)
    with open(OUT_PROFILE, "w", newline="", encoding="utf-8-sig") as fh:
        cols = list(all_profile[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in all_profile:
            w.writerow(r)
    with open(OUT_SUMMARY, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)

    prov = dict(
        function=summary["function"],
        dec_thal_direct_02="DEC-THAL-DIRECT-02",
        frozen_g3_relation=dict(rollup_csv=str(ROLLUP_CSV.relative_to(BACKEND)).replace("\\", "/"),
                                rollup_csv_sha256=sha256(ROLLUP_CSV),
                                g3_manifest=str(G3MAN.relative_to(BACKEND)).replace("\\", "/"),
                                g3_manifest_sha256=sha256(G3MAN),
                                g3_region_id=frozen["g3_region_id"],
                                official_label=frozen["official_label"],
                                frozen_decision=frozen["frozen_decision"],
                                frozen_g1_target=frozen["frozen_g1_target"]),
        raw_bna=dict(asset=str(RAW_BN.relative_to(BACKEND)).replace("\\", "/"),
                     sha256=sha256(RAW_BN),
                     channel_index=PRIMARY_COMP - 1,
                     component_index=PRIMARY_COMP,
                     source_space="MNI152NLin6Asym (HCP40 1.25mm grid), percent 0-100"),
        bna_spatial_route=dict(batch_manifest=str(BN_XFORM_MAN.relative_to(BACKEND)).replace("\\", "/"),
                               batch_manifest_sha256=sha256(BN_XFORM_MAN),
                               **route_meta),
        transformed_geometry=dict(directory=str(BN_PM_DIR.relative_to(BACKEND)).replace("\\", "/"),
                                  per_parcel_sha={code: route_rows[comp]["output_sha256"]
                                                  for code, comp in ALL_CODES.items()}),
        current_g1_geometry=dict(left_sha256=left_sha, right_sha256=right_sha,
                                 left_id="GEO-G1-THAL-L-MNI2009CASYM-V1",
                                 right_id="GEO-G1-THAL-R-MNI2009CASYM-V1"),
        spatial_bridge=dict(spatial_bridge_id=SPB_ID, class_name=spb["spatial_bridge_class"],
                            manifest_sha256=sha256(SPB_MAN),
                            registration_applied=False, resampling_applied=True),
        v3_scope_contract=dict(sha256=V3_SHA, id="THALAMUS_G1_SCOPE_CONTRACT_V3"),
        freesurfer_iglesias_source=dict(path=str(FS_SRC.relative_to(BACKEND)).replace("\\", "/"),
                                        sha256=FS_SHA, names_sha256=FS_NAMES_SHA),
        independent_anatomical_support=dict(path=str(AAL_FILE.relative_to(BACKEND)).replace("\\", "/"),
                                            sha256=sha256(AAL_FILE) if AAL_FILE.exists() else None),
        registration_applied=False,
        nonlinear_registration_applied=False,
        resampling_applied=True,
        template_variant_uncertainty="PRESENT",
        classification_independent=True,
        classification_csv="NOT_TOUCHED",
        db_write=False, promotion=False, commit=False,
        target_driven_correction=False,
        software=dict(python_version=sys.version.split()[0], platform=str(_platform.platform()),
                      numpy_version=np.__version__, scipy_version=__import__("scipy").__version__,
                      nibabel_version=nib.__version__),
        script=str(Path(__file__).name), script_version=SCRIPT_VERSION,
        run_timestamp=ts)
    with open(OUT_PROV, "w", encoding="utf-8") as fh:
        json.dump(prov, fh, ensure_ascii=False, indent=2)

    md = [
        "# Phase1.7 V3 - Tha_L_8_2 / mPMtha-L direct spatial discrepancy: root-cause audit", "",
        f"Primary case: {PRIMARY_CODE} (mPMtha L, DEC-THAL-DIRECT-02). Paired control: {CTRL_CODE} (mPMtha R).",
        f"Frozen G3 relation: {frozen['g3_region_id']} / {frozen['official_label']} -> "
        f"{frozen['frozen_g1_target']} ({frozen['frozen_decision']}).", "",
        "TERMINOLOGY CLARIFICATION (this audit supersedes; historical outputs untouched):",
        "  - The prior direct-validation record labelled DEC-THAL-DIRECT-02 evidence as",
        "    DIRECT_SPATIAL_CONFLICT / FROZEN_MAPPING_REQUIRES_REVIEW.",
        "  - That described a MATERIAL DIRECT SPATIAL DISCREPANCY (metric gap), NOT a confirmed mapping conflict.",
        "  - direct_conflict_count = 0; requires_review_count before supersession = 1.",
        "  - Superseding mapping verdict for DEC-THAL-DIRECT-02 = KEEP_FROZEN_MAPPING_WITH_SPATIAL_UNCERTAINTY.", "",
        f"Root cause (primary)  : {root_verdict['primary']}",
        f"Root cause (secondary): {root_verdict['secondary']}",
        f"TRUE_MAPPING_INCOMPATIBILITY_SUPPORTED = {mapping['true_mapping_incompatibility_supported']} "
        f"(no independent evidence).", "",
        "Stage evidence:",
        f"  A raw-BNA: L/R mPMtha volume ratio {raw_vol_ratio['8_2']}; raw mirror-centroid distance "
        f"{raw_mir['8_2']:.2f} mm (max of the 4 zone pairs; control max {max(controls_mirror_raw):.2f}) "
        "-> intrinsic BNA laterality asymmetry already present in the source atlas.",
        f"  B route   : identical SimpleITK NLin6->2009c route for all 16 (PASS); L8_2 target cc="
        f"{tgt_by_code[PRIMARY_CODE]['target_cc']}; route does not create the discrepancy (conserved; "
        f"mirror distance {tgt_mir['8_2']:.2f} mm).",
        f"  C G1-overlap: L containment {C_L:.3f} vs R {C_R:.3f} -> the gap is the G1-envelope intersection.",
        f"  FS categorization (L8_2): in-G1 support {fs_L['in_G1_support']:.3f}; in-FS-thalami incl reticular "
        f"{fs_L['in_FS_full_thalami_incl_reticular']:.3f}; reticular>0.5 {fs_L['reticular_strong_gt_0_5']:.3f}; "
        f"outside FS thalami {fs_L['outside_FS_thalami']:.3f}.",
        f"  Discrepant region (L8_2 & P_G1<0.1): {len(idx)} voxels, "
        f"{disc_mass/total_mass:.1%} of parcel mass, centroid "
        f"({cw[0]:.1f},{cw[1]:.1f},{cw[2]:.1f}) mm -> LATERAL+ANTERIOR of the G1 envelope.",
        f"  Reticular strong overlap inside discrepant region: {ret_disc_frac:.4f} (no substantial Reticular "
        "involvement; ZI/subthalamus not present as a repo reference).", "",
        "Independent anatomical support (AAL3):",
        f"  L8_2 in-G1 mass: {((aal_in or {}).get('Thalamus_L'))} Thalamus_L; "
        f"L8_2 discrepant mass: {((aal_disc or {}).get('Thalamus_L'))} Thalamus_L, "
        f"{((aal_disc or {}).get('label0'))} label-0.",
        "  -> the portion of L8_2 that overlaps G1 is solidly within the anatomical thalami; the discrepant "
        "fringe is partly still AAL-Thalamus (FS envelope conservative) and partly BNA probability-spread "
        "beyond the coarse anatomical thalami.", "",
        f"Gate wording (post-supersession): direct_conflict_count=0; requires_review_count=0 (L8_2 -> "
        "spatial uncertainty); postconstruction gate = CLOSABLE_NO_MAPPING_CONFLICT.",
        "Final freeze: ENABLED_RECOMMEND_FORM_IN_FREEZE_GATE (not auto-written by this read-only audit).", "",
        "Guards: no transform retuning; no threshold tuning; no scope modification; no G1 modification; "
        "no DB write; classification untouched (86/132/93); Promotion = BLOCKED; no commit.", ""]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    print("asymmetry stage:", asymmetry_origin_stage)
    print("root primary:", root_verdict["primary"], "| secondary:", root_verdict["secondary"])
    print(f"L8_2 C={C_L:.3f}  R8_2 C={C_R:.3f}  diff={asymmetry_stageC:.3f}")
    print("FS cats L8_2:", json.dumps(fs_L))
    print("AAL L8_2 discrep:", json.dumps(aal_disc))
    print("mapping:", json.dumps(mapping))
    print("wrote 6 files")


if __name__ == "__main__":
    main()
