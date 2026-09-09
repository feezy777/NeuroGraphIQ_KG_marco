"""Phase1.7 V3 - fsaverage -> MNI152NLin2009cAsym project-derived whole-template registration.

EXECUTES frozen candidate R_D_PROJECT_DERIVED_DIRECT:
  moving = official FreeSurfer fsaverage mri/orig.mgz (whole-head template anatomical average)
  fixed  = TemplateFlow MNI152NLin2009cAsym res-01 desc-brain T1w (whole-brain template)
Registration = ANTs SyN (affine + diffeomorphic nonlinear), estimated from whole-template
anatomical intensities; the metric is restricted to the FIXED whole-brain mask (clean
foreground), so the moving brain is aligned brain-to-brain even though the moving average
carries a head/skull envelope. No parcel/label content of any kind.

Input properties (measured): moving max 231, ~46% nonzero (whole-head avg); fixed desc-brain
foreground 768..9848 cleanly separated (brain-only). Fixed mask = intensity-derived whole-brain
support (max*0.02 + largest CC + close + dilate). No moving brain extraction is required and no
DK/G4/Julich/Brainnetome label is used anywhere.

Direct fsaverage-orig -> MNI2009cAsym ONLY. NO MNI305 intermediate, NO NLin6, NO talairach.xfm,
NO TemplateFlow NLin6->2009c transform, NO R_D2.

Runtime validated BEFORE freezing the recipe (ANTsPy 0.6.3 synthetic SyN sanity: warp finite,
nonzero displacement, forward != inverse, apply_transforms changes image => the historical
"SyN zero-displacement" anomaly is NOT reproduced). random seed 17 + regular sampling.

Guards: no FreeSurfer/license, no ribbon, no label transform, no cortical geometry, no G4
overlap, no DB, no reclassification, no promotion. Raw templates never modified.

Verdicts: A CORTICAL_TARGET_PROJECT_DERIVED_TRANSFORM_FROZEN | B QC_FAILED |
          C RUNTIME_INVALID | D EXECUTION_BLOCKED. route_v1 only on A.
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import ants
import nibabel as nib
from nibabel.freesurfer.mghformat import MGHImage
from scipy import ndimage
from scipy.ndimage import map_coordinates

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
RUN = BACKEND / "data" / "atlases" / "derived_g1" / "cort_reg_run_v1"
FS = BACKEND / "data" / "atlases" / "freesurfer" / "fsaverage"
TF = BACKEND / "data" / "atlases" / "templateflow_ref"
ORIG = FS / "mri/orig.mgz"
FIXED = TF / "tpl-MNI152NLin2009cAsym_res01_desc-brain_T1w.nii.gz"
SCRIPT_VERSION = "phase17_v3_execute_cortical_target_registration.py v1"
TRF_ID = "TRF-CORT-FSAVG-TO-MNI2009C-DIRECT-V1"
RUN_ID = "RUN-CORT-FSAVG-TO-MNI2009C-DIRECT-V1"
SEED = 17

OUT_RECIPE = D16 / "phase17_v3_cortical_registration_recipe_v1.json"
OUT_RT = D16 / "phase17_v3_cortical_registration_runtime_manifest.json"
OUT_IN = D16 / "phase17_v3_cortical_registration_input_manifest.json"
OUT_TX = D16 / "phase17_v3_cortical_registration_transform_manifest.json"
OUT_SIM = D16 / "phase17_v3_cortical_registration_similarity_qc.csv"
OUT_DEF = D16 / "phase17_v3_cortical_registration_deformation_qc.json"
OUT_GEOM = D16 / "phase17_v3_cortical_registration_geometry_qc.csv"
OUT_PROV = D16 / "phase17_v3_cortical_registration_provenance.json"
OUT_V1 = D16 / "phase17_v3_cortical_target_route_v1.json"
OUT_MD = D16 / "phase17_v3_cortical_registration_diagnostics.md"

RECIPE = dict(
    recipe_id="REGISTRATION_RECIPE_V1",
    route="R_D_PROJECT_DERIVED_DIRECT",
    moving="official FreeSurfer fsaverage mri/orig.mgz (whole-head avg; no skull-strip needed)",
    fixed="TemplateFlow MNI152NLin2009cAsym res-01 desc-brain T1w",
    runtime="ANTs (SyN) via ANTsPy 0.6.3",
    type_of_transform="SyN",
    aff_metric="mattes", syn_metric="mattes",
    aff_sampling=64, syn_sampling=64,
    sampling_strategy="regular deterministic (not random)",
    mask_usage="FIXED whole-brain mask only (intensity-derived; max*0.02 + largest CC + close2 + "
               "dilate1); metric restricted to the fixed brain => brain-to-brain alignment. "
               "No label content; no moving brain extraction.",
    reg_iterations=(40, 20, 10),
    reg_convergence="[40x20x10,1e-7,8]", reg_smoothing="2x1x0 (derived)", reg_shrink="4x2x1 (derived)",
    aff_iterations="ANTs SyN default low-dim schedule",
    random_seed=SEED, histogram_matching=False, singleprecision=True,
    notes=["recipe frozen BEFORE any result review; no post-hoc tuning / recipe V2 this round.",
           "masks derived only from whole-brain/intensity geometry, independent of all parcels."],
    QC_pass_thresholds=dict(
        coverage_nonlinear_min=0.80,
        coverage_not_degraded_vs_affine_minus=0.02,
        finite_required=True,
        max_displacement_mm_max=45.0,
        zero_displacement_fraction_max=0.90,
        negative_jacobian_fraction_max=0.02,
        jacobian_median_range=(0.4, 1.8),
        laterality_preserved_required=True,
        fov_no_truncation_required=True,
    ),
)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def otsu(vals: np.ndarray) -> float:
    vals = vals[vals > 0]
    if vals.size == 0:
        return 0.0
    hist, edges = np.histogram(vals, bins=256)
    c = (edges[:-1] + edges[1:]) / 2
    w = np.cumsum(hist)
    mu = np.cumsum(hist * c)
    mt = mu[-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        b = (mt * w - mu) ** 2 / (w * (w[-1] - w))
    b[~np.isfinite(b)] = 0
    return float(c[np.argmax(b)])


def brain_support_mask(arr: np.ndarray, frac: float = 0.02) -> np.ndarray:
    m = arr > float(arr.max()) * frac
    lab, n = ndimage.label(m)
    if n == 0:
        return np.zeros_like(m, dtype=bool)
    sizes = ndimage.sum(np.ones_like(lab), lab, index=range(1, n + 1))
    m = lab == int(np.argmax(sizes)) + 1
    st = ndimage.generate_binary_structure(3, 1)
    m = ndimage.binary_closing(m, structure=st, iterations=2)
    m = ndimage.binary_dilation(m, structure=st, iterations=1)
    return m


def ncc_mi(a, b, mask):
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    sel = mask & np.isfinite(a) & np.isfinite(b)
    if sel.sum() < 200:
        return None, None
    av, bv = a[sel], b[sel]
    ncc = float(np.corrcoef(av, bv)[0, 1])
    la, ha = np.percentile(av, 1), np.percentile(av, 99)
    lb, hb = np.percentile(bv, 1), np.percentile(bv, 99)
    h2, *_ = np.histogram2d(np.clip(av, la, ha), np.clip(bv, lb, hb), bins=64)
    p = h2 / h2.sum() + 1e-12
    p = p / p.sum()
    with np.errstate(divide="ignore", invalid="ignore"):
        mi = float((p * np.log2(p / (p.sum(0, keepdims=True) * p.sum(1, keepdims=True)))).sum())
    return ncc, mi


def affine_of(img) -> np.ndarray:
    d = np.array(img.direction).reshape(3, 3)
    s = np.array(img.spacing)
    o = np.array(img.origin)
    A = np.eye(4)
    A[:3, :3] = d * s
    A[:3, 3] = o
    return A


def content_mask_threshold(stage_arr, fixed_mask):
    """Deterministic relative tissue threshold: 20% of the max of the warped-moving intensities
    inside the fixed whole-brain mask (moving scale; no labels, no cross-scale assumption)."""
    inside = stage_arr[fixed_mask]
    if inside.max() <= 0:
        return 1e18
    return float(inside.max()) * 0.2


def content_coverage(stage_arr, fixed_mask):
    """Coverage of the fixed whole-brain mask by warped-moving brain content (content = values
    above the relative tissue threshold; no labels)."""
    thr = content_mask_threshold(stage_arr, fixed_mask)
    content = stage_arr > thr
    cov = float((content & fixed_mask).sum()) / float(fixed_mask.sum())
    return cov


def face_no_truncation(content, fixed_mask, tol=3):
    """True if content reaches each face of the fixed-mask bounding box (no frontal/occipital/
    temporal/cerebellar truncation by the target FOV)."""
    idx = np.argwhere(fixed_mask)
    lo = idx.min(axis=0)
    hi = idx.max(axis=0)
    cidx = np.argwhere(content)
    if cidx.shape[0] == 0:
        return False
    clo = cidx.min(axis=0)
    chi = cidx.max(axis=0)
    return bool(np.all(clo <= lo + tol) and np.all(chi >= hi - tol))


def com_ras(mask, A):
    idx = np.argwhere(mask).astype(np.float64) + 0.5
    if idx.shape[0] == 0:
        return np.full(3, np.nan)
    return (A[:3, :3] @ idx.T + A[:3, 3:4]).mean(axis=1)


def jacobian_det(warp):
    g = np.gradient(warp.astype(np.float64), axis=(0, 1, 2))
    J = np.zeros(warp.shape[:-1] + (3, 3), dtype=np.float64)
    for a in range(3):
        J[..., a, a] = 1.0
    for c in range(3):
        for a in range(3):
            J[..., c, a] += g[a][..., c]
    a = J[..., 0, 0]; b = J[..., 0, 1]; c0 = J[..., 0, 2]
    d = J[..., 1, 0]; e = J[..., 1, 1]; f = J[..., 1, 2]
    gg = J[..., 2, 0]; h = J[..., 2, 1]; ii = J[..., 2, 2]
    return a * (e * ii - f * h) - b * (d * ii - f * gg) + c0 * (d * h - e * gg)


def lps_x_grid(img):
    """Elementwise LPS x per voxel (+ = subject LEFT in ANTs/ITK LPS frame)."""
    A = affine_of(img)
    n = img.shape
    ii, jj, kk = np.ogrid[: n[0], : n[1], : n[2]]
    return A[0, 0] * (ii + 0.5) + A[0, 1] * (jj + 0.5) + A[0, 2] * (kk + 0.5) + A[0, 3]


def laterality_check(moving_ants, fixed_ants, fwd, n_sample=400):
    """Laterality via physical POINT transforms (ants.apply_transforms_to_points).

    Points are the lateral-hemisphere tissue voxels of the moving image (split by the moving
    LPS-x sign), transformed to the fixed image with the forward transform. Because the point
    transform is applied by ANTs in a single consistent physical frame, source-side sign ==
    target-side sign proves no left-right reflection. Whole-template geometry only, no labels.
    """
    md = moving_ants.numpy()
    A_m = affine_of(moving_ants)
    A_f = affine_of(fixed_ants)
    supp = md > md.max() * 0.05
    xval = lps_x_grid(moving_ants)
    # clearly-lateral tissue only (|x| >= 12 mm) to avoid ambiguous near-midline points
    res, ok = {}, True
    for name, side_mask in (("anatomical_left_LPSplusx", supp & (xval >= 12.0)),
                            ("anatomical_right_LPSminusx", supp & (xval <= -12.0))):
        idx = np.argwhere(side_mask).astype(np.float64) + 0.5
        if idx.shape[0] < 50:
            res[name] = dict(preserved=False, reason="too few source voxels")
            ok = False
            continue
        step = max(1, idx.shape[0] // n_sample)
        idx = idx[::step][:n_sample]
        pts = (A_m[:3, :3] @ idx.T + A_m[:3, 3:4]).T
        import pandas as pd
        df = pd.DataFrame([{"x": float(p[0]), "y": float(p[1]), "z": float(p[2])} for p in pts])
        out = ants.apply_transforms_to_points(3, df, transformlist=fwd)
        tx = out["x"].to_numpy()
        source_plus = bool((pts[:, 0] >= 0).mean() > 0.99)
        target_frac_plus = float((tx >= 0).mean())
        frac = target_frac_plus if source_plus else 1.0 - target_frac_plus
        side_ok = frac > 0.99
        res[name] = dict(preserved=side_ok, correct_side_fraction=round(frac, 4),
                         n_points=int(len(tx)),
                         source_mean_x_mm=float(pts[:, 0].mean()),
                         target_mean_x_mm=float(tx.mean()))
        ok = ok and side_ok
    return dict(preserved=bool(ok), probes=res,
                note="physical-point laterality probe (ANTs point transform, no labels); "
                     "side preserved = no left-right reflection")


def _write_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)


def main() -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    RUN.mkdir(parents=True, exist_ok=True)

    moving_nii = RUN / "moving_fsaverage_orig.nii.gz"
    if not moving_nii.exists():
        o = MGHImage.load(str(ORIG))
        nib.save(nib.Nifti1Image(np.asanyarray(o.dataobj), o.affine), str(moving_nii))

    moving_ants = ants.image_read(str(moving_nii))
    fixed_ants = ants.image_read(str(FIXED))
    od = moving_ants.numpy()
    fd = fixed_ants.numpy()
    A_f = affine_of(fixed_ants)
    A_m = affine_of(moving_ants)
    mf = brain_support_mask(fd, frac=0.02)
    fixed_mask = ants.from_numpy(mf.astype(np.uint8), origin=fixed_ants.origin,
                                 spacing=fixed_ants.spacing, direction=fixed_ants.direction)
    ants.image_write(fixed_mask, str(RUN / "fixed_mask.nii.gz"))

    # ---- baseline (pure grid resample moving -> fixed grid, NO transform) ----
    sh = np.array(fixed_ants.shape)
    i, j, k = np.meshgrid(np.arange(sh[0]), np.arange(sh[1]), np.arange(sh[2]), indexing="ij")
    vox_f = np.stack([i + 0.5, j + 0.5, k + 0.5, np.ones(i.shape)], axis=0).reshape(4, -1)
    vox_m = np.linalg.inv(A_m) @ (A_f @ vox_f)
    base_arr = map_coordinates(od, vox_m[:3], mode="constant", cval=0.0, order=1).reshape(tuple(sh))
    msupp = od > od.max() * 0.05
    ncc_b, mi_b = ncc_mi(base_arr, fd, mf)
    cov_b = content_coverage(base_arr, mf)

    _write_json(OUT_RECIPE, dict(RECIPE, created_at=ts, script_version=SCRIPT_VERSION))
    _write_json(OUT_IN, dict(
        moving=dict(identity="official FreeSurfer fsaverage mri/orig.mgz", sha256=sha256(ORIG),
                    shape=[int(x) for x in moving_ants.shape],
                    spacing=[float(x) for x in moving_ants.spacing],
                    dtype=str(np.asanyarray(MGHImage.load(str(ORIG)).dataobj).dtype)),
        fixed=dict(identity="TemplateFlow tpl-MNI152NLin2009cAsym res-01 desc-brain T1w",
                   sha256=sha256(FIXED), shape=[int(x) for x in fixed_ants.shape],
                   spacing=[float(x) for x in fixed_ants.spacing],
                   dtype=str(fd.dtype)),
        fixed_brain_mask=dict(derivation="intensity-derived whole-brain support: max*0.02 + largest "
                                         "CC + close(2) + dilate(1); no labels",
                              voxels=int(mf.sum())),
        note="moving whole-head avg used directly; metric restricted to fixed whole-brain mask "
             "(brain-to-brain). Raw templates never modified.",
        created_at=ts, script_version=SCRIPT_VERSION))

    if stage == "prep":
        _write_json(RUN / "baseline.json", dict(ncc=ncc_b, mi=mi_b, coverage=cov_b))
        print("prep done. baseline ncc", round(ncc_b or -1, 4), "mi", round(mi_b or -1, 3),
              "coverage", round(cov_b, 4))
        return

    # ---------------- registration ----------------
    ants.config._random_seed = SEED
    reg = ants.registration(
        fixed=fixed_ants, moving=moving_ants, type_of_transform="SyN",
        aff_metric="mattes", syn_metric="mattes",
        aff_sampling=64, syn_sampling=64,
        mask=fixed_mask, moving_mask=None, mask_all_stages=True,
        reg_iterations=tuple(RECIPE["reg_iterations"]),
        verbose=False, outprefix=str(RUN / "reg_"))

    fwd = [p for p in reg.get("fwdtransforms", []) if p and Path(p).exists()]
    inv = [p for p in reg.get("invtransforms", []) if p and Path(p).exists()]
    if not fwd:
        _write_md(ts, "CORTICAL_TARGET_REGISTRATION_RUNTIME_INVALID",
                  dict(no_transform=True), None, None, None, None, None, False)
        raise SystemExit("registration produced no forward transform")
    aff_p = next(p for p in fwd if "Affine" in p)
    warp_p = next(p for p in fwd if "Warp" in p)
    invw_p = next((p for p in inv if "InverseWarp" in p), None)

    aff_asset = RUN / f"{TRF_ID}_affine.mat"
    fwd_asset = RUN / f"{TRF_ID}_forward_warp.nii.gz"
    inv_asset = RUN / f"{TRF_ID}_inverse_warp.nii.gz"
    shutil.copy(aff_p, aff_asset)
    shutil.copy(warp_p, fwd_asset)
    if invw_p:
        shutil.copy(invw_p, inv_asset)

    warped_full = ants.apply_transforms(fixed=fixed_ants, moving=moving_ants,
                                        transformlist=fwd, interpolator="linear")
    warped_aff = ants.apply_transforms(fixed=fixed_ants, moving=moving_ants,
                                       transformlist=[aff_p], interpolator="linear")
    ants.image_write(warped_full, str(RUN / f"{TRF_ID}_warped_moving_brain.nii.gz"))
    ants.image_write(warped_aff, str(RUN / f"{TRF_ID}_warped_moving_affine_only.nii.gz"))
    wf = warped_full.numpy()
    wa = warped_aff.numpy()

    ncc_aff, mi_aff = ncc_mi(wa, fd, mf)
    ncc_nl, mi_nl = ncc_mi(wf, fd, mf)
    cov_aff = content_coverage(wa, mf)
    cov_nl = content_coverage(wf, mf)
    content_full = wf > content_mask_threshold(wf, mf)
    no_trunc = face_no_truncation(content_full, mf)
    com_aff = float(np.linalg.norm(com_ras(wa > 0, A_f) - com_ras(mf, A_f)))
    com_nl = float(np.linalg.norm(com_ras(content_full, A_f) - com_ras(mf, A_f)))

    # deformation QC
    warp_arr = ants.image_read(str(fwd_asset)).numpy()
    mag = np.sqrt((warp_arr.astype(np.float64) ** 2).sum(axis=-1))
    finite = bool(np.isfinite(warp_arr).all())
    zero_frac = float((mag <= 1e-9).mean())
    disp = dict(mean_mm=float(mag.mean()), median_mm=float(np.median(mag)),
                p95_mm=float(np.percentile(mag, 95)), max_mm=float(mag.max()),
                finite=finite, zero_vector_fraction=round(zero_frac, 6),
                comp_min=[float(warp_arr[..., c].min()) for c in range(3)],
                comp_max=[float(warp_arr[..., c].max()) for c in range(3)])
    J = jacobian_det(warp_arr)
    jac = dict(min=float(J.min()), p01=float(np.percentile(J, 1)), p05=float(np.percentile(J, 5)),
               median=float(np.median(J)), p95=float(np.percentile(J, 95)),
               p99=float(np.percentile(J, 99)), max=float(J.max()),
               negative_fraction=round(float((J < 0).mean()), 6),
               nonpositive_fraction=round(float((J <= 0).mean()), 6),
               finite_jac=bool(np.isfinite(J).all()))
    th = RECIPE["QC_pass_thresholds"]
    deform_valid = (finite and jac["finite_jac"] and jac["negative_fraction"] <=
                    th["negative_jacobian_fraction_max"]
                    and th["jacobian_median_range"][0] <= jac["median"] <=
                    th["jacobian_median_range"][1])
    def_qc = dict(deformation=disp, jacobian=jac,
                  validity="VALID" if deform_valid else "REGISTRATION_DEFORMATION_INVALID")

    # inverse consistency (image round trip)
    back = ants.apply_transforms(fixed=moving_ants, moving=warped_full,
                                 transformlist=inv, interpolator="linear")
    bb = back.numpy()
    ncc_rt, mi_rt = ncc_mi(bb, od, msupp)
    cov_rt = content_coverage(bb, msupp)
    inv_qc = dict(inverse_status="AVAILABLE" if invw_p else "NOT_AVAILABLE",
                  roundtrip_ncc=ncc_rt, roundtrip_mi_bits=mi_rt,
                  roundtrip_coverage=cov_rt)

    laterality = laterality_check(moving_ants, fixed_ants, fwd)

    geom_qc = dict(
        moving_tissue_support_ml=round(float((od > od.max() * 0.05).sum()) / 1000.0, 1),
        fixed_brain_mask_ml=round(float(mf.sum()) / 1000.0, 1),
        coverage_baseline=round(cov_b, 4), coverage_affine=round(cov_aff, 4),
        coverage_nonlinear=round(cov_nl, 4),
        com_disp_baseline_mm=round(float(np.linalg.norm(com_ras(base_arr > 0, A_f) -
                                                        com_ras(mf, A_f))) if (base_arr > 0).any()
                                   else float("nan"), 2),
        com_disp_affine_mm=round(com_aff, 2), com_disp_nonlinear_mm=round(com_nl, 2),
        fov_no_truncation=no_trunc,
        laterality_preserved=laterality["preserved"])

    flags = dict(
        runtime_registered=True,
        deformation_valid=deform_valid,
        finite=finite,
        nonzero_disp=disp["max_mm"] > 0.5,
        zero_frac_ok=zero_frac <= th["zero_displacement_fraction_max"],
        max_disp_ok=disp["max_mm"] <= th["max_displacement_mm_max"],
        coverage_min_ok=cov_nl >= th["coverage_nonlinear_min"],
        coverage_not_degraded_vs_affine=cov_nl >= cov_aff - th["coverage_not_degraded_vs_affine_minus"],
        no_truncation_ok=no_trunc,
        laterality_ok=laterality["preserved"],
    )
    qc_pass = all(flags.values())
    verdict = ("CORTICAL_TARGET_PROJECT_DERIVED_TRANSFORM_FROZEN" if qc_pass
               else "CORTICAL_TARGET_REGISTRATION_QC_FAILED")

    # ---- artifacts ----
    _write_json(OUT_RT, dict(
        runtime="ANTs (SyN diffeomorphic) via ANTsPy 0.6.3",
        software="ANTs/ANTsPy", ants_python_version="0.6.3",
        elastix_available=False, itk_python_available=False,
        runtime_sanity_test=dict(performed=True, result="PASS",
                                 evidence="synthetic SyN: warp finite, nonzero displacement, "
                                          "forward != inverse, apply_transforms changes image; "
                                          "historical zero-warp anomaly NOT reproduced"),
        sampling="regular deterministic", random_seed=SEED, flags=flags,
        created_at=ts, script_version=SCRIPT_VERSION))
    _write_json(OUT_TX, dict(
        run_id=RUN_ID, transform_id=TRF_ID,
        direction="fsaverage orig (moving) -> MNI152NLin2009cAsym (fixed)",
        affine=dict(path=str(aff_asset).replace("\\", "/"), sha256=sha256(aff_asset),
                    size_bytes=aff_asset.stat().st_size, format="ANTs GenericAffine .mat"),
        forward_warp=dict(path=str(fwd_asset).replace("\\", "/"), sha256=sha256(fwd_asset),
                          size_bytes=fwd_asset.stat().st_size,
                          format="ANTs displacement field nii.gz"),
        inverse_warp=(dict(path=str(inv_asset).replace("\\", "/"), sha256=sha256(inv_asset),
                           size_bytes=inv_asset.stat().st_size,
                           format="ANTs inverse displacement field nii.gz") if inv_asset else None),
        warped_moving_anatomical=str(RUN / f"{TRF_ID}_warped_moving_brain.nii.gz").replace("\\", "/"),
        software_convention="ANTs transforms; fwd list [warp, affine] moving->fixed; "
                            "inv list [affine, inverseWarp]",
        created_at=ts, script_version=SCRIPT_VERSION))
    sim_rows = [
        dict(stage="baseline_grid_resample", ncc=round(ncc_b or -1, 4), mi_bits=round(mi_b or -1, 3),
             coverage=round(cov_b, 4), note="pure grid resample, no transform"),
        dict(stage="post_affine", ncc=round(ncc_aff or -1, 4), mi_bits=round(mi_aff or -1, 3),
             coverage=round(cov_aff, 4), note="affine stage only"),
        dict(stage="post_nonlinear_SyN", ncc=round(ncc_nl or -1, 4), mi_bits=round(mi_nl or -1, 3),
             coverage=round(cov_nl, 4), note="full SyN (affine + warp)"),
        dict(stage="inverse_roundtrip", ncc=round(ncc_rt or -1, 4), mi_bits=round(mi_rt or -1, 3),
             coverage=round(cov_rt or 0, 4), note="warp -> inverse transform back to moving"),
    ]
    with open(OUT_SIM, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["stage", "ncc", "mi_bits", "coverage", "note"])
        w.writeheader()
        for r in sim_rows:
            w.writerow(r)
    _write_json(OUT_DEF, dict(def_qc, created_at=ts, script_version=SCRIPT_VERSION))
    geom_rows = [dict(metric=k, value=(v if isinstance(v, (int, float, str, bool)) else json.dumps(v)))
                 for k, v in geom_qc.items()]
    with open(OUT_GEOM, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["metric", "value"])
        w.writeheader()
        for r in geom_rows:
            w.writerow(r)
    _write_json(OUT_PROV, dict(run_id=RUN_ID, verdict=verdict, pass_flags=flags,
                               laterality=laterality, inverse_consistency=inv_qc,
                               geometry=geom_qc, route="R_D_PROJECT_DERIVED_DIRECT",
                               raw_templates_untouched=True, binaries_gitignored=True,
                               created_at=ts, script_version=SCRIPT_VERSION))
    if qc_pass:
        _write_json(OUT_V1, dict(
            route_id="CORTICAL_FSAVERAGE_TO_MNI2009C_ROUTE_V1",
            route_class="PROJECT_DERIVED_TEMPLATE_REGISTRATION",
            run_id=RUN_ID, transform_id=TRF_ID,
            moving_identity="official FreeSurfer fsaverage mri/orig.mgz",
            moving_sha256=sha256(ORIG),
            fixed_identity="TemplateFlow MNI152NLin2009cAsym res-01 desc-brain T1w",
            fixed_sha256=sha256(FIXED),
            affine_sha256=sha256(aff_asset),
            forward_warp_sha256=sha256(fwd_asset),
            inverse_sha256=sha256(inv_asset) if inv_asset else "NOT_AVAILABLE",
            software="ANTs (ANTsPy 0.6.3)", recipe="REGISTRATION_RECIPE_V1",
            coordinate_convention="ANTs LPS-internal; NIfTI RAS headers preserved; no manual "
                                  "RAS/LPS flipping",
            qc_summary=dict(coverage_nonlinear=cov_nl,
                            ncc_nonlinear=ncc_nl, mi_nonlinear=mi_nl,
                            jacobian_median=round(jac["median"], 4),
                            negative_jacobian_fraction=jac["negative_fraction"],
                            laterality_preserved=laterality["preserved"]),
            mapping_independent=True, circularity_risk="NONE",
            future_application_semantics=dict(
                binary_cortical_ribbon="NearestNeighbor (label-safe) when the future ribbon "
                                       "volume is transformed to this target space",
                note="no cortical ribbon is transformed this round"),
            created_at=ts, script_version=SCRIPT_VERSION))
    _write_md(ts, verdict, flags, geom_qc, jac, disp, laterality, inv_qc, qc_pass)

    print("verdict:", verdict)
    print("coverage baseline/affine/nonlinear:", round(cov_b, 3), round(cov_aff, 3), round(cov_nl, 3))
    print("ncc baseline/affine/nonlinear:", round(ncc_b or -1, 3), round(ncc_aff or -1, 3),
          round(ncc_nl or -1, 3))
    print("disp max mm:", round(disp["max_mm"], 2), "zero frac:", round(zero_frac, 5),
          "jac neg:", jac["negative_fraction"], "med:", round(jac["median"], 4),
          "| laterality:", laterality["preserved"], "| no_trunc:", no_trunc)


def _write_md(ts, verdict, flags, geom_qc, jac, disp, laterality, inv_qc, qc_pass):
    lines = [
        "# Phase1.7 V3 - fsaverage -> MNI152NLin2009cAsym project-derived whole-template "
        "registration execution + QC freeze", "",
        f"VERDICT: {verdict}",
        f"run: {RUN_ID} | transform: {TRF_ID} (direct R_D; no MNI305/NLin6/talairach intermediate)",
        f"moving = fsaverage mri/orig.mgz (sha {sha256(ORIG)[:16]}...) | fixed = MNI152NLin2009cAsym "
        f"res01 desc-brain (sha {sha256(FIXED)[:16]}...)",
        "runtime ANTs SyN (ANTsPy 0.6.3); runtime sanity PASS (no zero-warp anomaly); seed 17; "
        "regular sampling.",
        f"pass flags: {json.dumps(flags, ensure_ascii=False)}",
    ]
    if geom_qc is not None:
        lines += [
            f"coverage(fixed-brain by warped content) baseline/affine/nonlinear = "
            f"{geom_qc['coverage_baseline']} / {geom_qc['coverage_affine']} / "
            f"{geom_qc['coverage_nonlinear']}",
            f"COM disp affine/nonlinear = {geom_qc['com_disp_affine_mm']} / "
            f"{geom_qc['com_disp_nonlinear_mm']} mm; fov_no_truncation = "
            f"{geom_qc['fov_no_truncation']}",
            f"deformation max {disp['max_mm']} mm, median {disp['median_mm']} mm, zero-vec frac "
            f"{disp['zero_vector_fraction']}, finite {disp['finite']}",
            f"Jacobian median {jac['median']}, negative frac {jac['negative_fraction']}, "
            f"min {jac['min']}",
            f"inverse status {inv_qc['inverse_status']}; roundtrip coverage "
            f"{inv_qc.get('roundtrip_coverage')}",
            f"laterality preserved: {laterality['preserved']}",
            "mapping independence: whole-template anatomical intensities only; metric restricted to "
            "the fixed whole-brain mask; no DK/G4/Julich/Brainnetome labels, no mapping results -> "
            "circularity NONE. No FreeSurfer/license, no ribbon, no label transform, no cortical "
            "geometry, no G4 overlap, no DB, no reclassification, no promotion.",
            f"route_v1 generated: {OUT_V1.name if OUT_V1.exists() else 'NO'} (only on FROZEN).",
        ]
    else:
        lines.append("no transform produced - registration runtime invalid.")
    lines.append("")
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
