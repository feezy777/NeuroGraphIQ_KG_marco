"""Phase1.7 V3 - Thalamus Julich-reference-grid G1 Geometry (SPATIAL BRIDGE).

v2 - SHARED_FRAME_RESAMPLE. This script does NOT perform a nonlinear Sym->Asym
anatomical registration.

SCIENTIFIC POSITION (adjudicated):

  * ICBM152 2009c symmetric and MNI152NLin2009cAsym are DIFFERENT template
    variants that SHARE a stereotaxic world-coordinate frame
    (DIFFERENT_TEMPLATE_VARIANTS_WITH_SHARED_STEREOTAXIC_COORDINATE_FRAME).
    They are NOT anatomically identical averages, and this project does NOT
    manufacture an uncalibrated nonlinear Sym->Asym warp.

  * A previous project-derived ANTs SyN attempt (TRF-ICBM2009CSYM-TO-
    MNI2009CASYM-V1) is RETRACTED: on this Windows/Python3.13/ANTsPy 0.6.3
    runtime the SyN stage emitted zero-displacement fields (full-SyN result
    == affine/shared-grid result; fwd/inv warp SHAs were identical because both
    were empty). Recorded as CURRENT_RUNTIME_IMPLEMENTATION_ANOMALY - NOT a
    general statement that ANTs SyN is scientifically invalid.

  * FreeSurfer ThalamusProbs.MNIsymSpace probabilities live approximately in
    ICBM152 2009c symmetric world coordinates; the atlas shares world
    coordinates though not necessarily the source voxel grid. Resampling the
    native 0.5mm probability map onto the 1mm Julich reference grid by
    physical/world-coordinate resampling is a source-supported operation.

  * This round emits a SPATIAL BRIDGE (SPB), not a transform:
      SPB-MNI2009C-SYM-ASYM-SHARED-FRAME-V1
      class = SHARED_COORDINATE_REFERENCE_GRID_RESAMPLING
      registration_applied = FALSE
      nonlinear_registration_applied = FALSE
      deformation_field_applied = FALSE
      resampling_applied = TRUE
      resampling_basis = SHARED_MNI152_2009C_WORLD_COORDINATE_FRAME
      interpolation = LINEAR

Residual scientific limitation is explicitly retained:
  TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_WARP_CORRECTED
Downstream direct-overlap evidence must be labelled
  DIRECT_SPATIAL_OVERLAP_IN_SHARED_MNI2009C_COORDINATE_FRAME
(not "after authoritative sym-to-asym anatomical registration").

No threshold/binarization/clipping/renormalization. Mass change is QC only.
Outputs are local derived assets (NOT committed); provenance/SHA/QC tracked.
No BN direct validation; no G4->G1 overlap; no reclassification; no promotion;
no DB write; no commit.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import nibabel as nib
import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
DERIVED = BACKEND / "data" / "atlases" / "derived_g1"

# frozen source authorities
V3 = D16 / "phase17_v3_thalamus_g1_scope_contract_v3.json"
SRC_LEFT = DERIVED / "left_thalamus_proper_prob_icbm2009csym.nii.gz"
SRC_RIGHT = DERIVED / "right_thalamus_proper_prob_icbm2009csym.nii.gz"
V3_SHA_EXPECTED = "22e24a31bab9659769f7e550ee32f8e3b37887d0ae1a4c4c4cf64974c3c05f68"
LEFT_SHA_EXPECTED = "2c9d3d2d7823a02749c77a7084339d503fcb251b5db53b7791e2f008b43f2ba8"
RIGHT_SHA_EXPECTED = "e9e93d593ddc073431d3e8d2da3e1d16e89e05ec213f9e24d6659caa9c926ae2"

# templates (shared-frame authority)
SRC_TPL = BACKEND / "data" / "atlases" / "external_raw" / "_ref" / "mni_icbm152_t1_tal_nlin_sym_09c.nii"
SRC_TPL_MASK = BACKEND / "data" / "atlases" / "external_raw" / "_ref" / "mni_icbm152_t1_tal_nlin_sym_09c_mask.nii"
TGT_TPL = BACKEND / "data" / "atlases" / "templateflow_ref" / "tpl-MNI152NLin2009cAsym_res01_desc-brain_T1w.nii.gz"
JULICH_PM_DIR = BACKEND / "data" / "atlases" / "julich" / "v3.1" / "spatial_raw" / "probability_maps"

OUT_SPB_MAN = D16 / "phase17_v3_thalamus_spatial_bridge_manifest.json"
OUT_SPB_QC = D16 / "phase17_v3_thalamus_spatial_bridge_qc.csv"
OUT_GEOM_MAN = D16 / "phase17_v3_thalamus_g1_julich_geometry_manifest.json"
OUT_GEOM_QC = D16 / "phase17_v3_thalamus_g1_julich_geometry_qc.csv"
OUT_MD = D16 / "phase17_v3_thalamus_g1_julich_geometry_diagnostics.md"
OUT_RETR = D16 / "phase17_v3_thalamus_transform_retraction.json"
OUT_ENV = D16 / "phase17_v3_thalamus_transform_environment.json"

OUT_LEFT_ASYM = DERIVED / "left_thalamus_proper_prob_mni2009casym.nii.gz"
OUT_RIGHT_ASYM = DERIVED / "right_thalamus_proper_prob_mni2009casym.nii.gz"

GEOM_L = "GEO-G1-THAL-L-MNI2009CASYM-V1"
GEOM_R = "GEO-G1-THAL-R-MNI2009CASYM-V1"
LID, RID = "NGIQ-BR-00000247", "NGIQ-BR-00000256"
SPB_ID = "SPB-MNI2009C-SYM-ASYM-SHARED-FRAME-V1"
OLD_TRF_ID = "TRF-ICBM2009CSYM-TO-MNI2009CASYM-V1"
OLD_LEFT_SHA = "37a82b65d86d81b1558582dee301e79ee367d60856f95d6a55b0219cf28a87a1"
OLD_RIGHT_SHA = "1c9b8b8de9103c1e091c9fb6e0577182416d5a6ba0c1b7f6d41e1e913958253f"
SCRIPT_VERSION = "phase17_v3_transform_thalamus_g1_to_julich_space.py v2 (SHARED_FRAME_RESAMPLE)"
TOL = 1e-5


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def linear_resample_to_grid(native_img, target_shape, target_affine, native_affine):
    """Pure header-driven linear (trilinear) coordinate resample in shared world frame."""
    d = np.asanyarray(native_img.dataobj).astype(np.float64)
    sh = d.shape
    inv_a = np.linalg.inv(native_affine)
    out = np.zeros(target_shape, dtype=np.float64)
    I, J, K = np.meshgrid(np.arange(target_shape[0]), np.arange(target_shape[1]),
                          np.arange(target_shape[2]), indexing="ij")
    wx = target_affine[0, 0] * I + target_affine[0, 1] * J + target_affine[0, 2] * K + target_affine[0, 3]
    wy = target_affine[1, 0] * I + target_affine[1, 1] * J + target_affine[1, 2] * K + target_affine[1, 3]
    wz = target_affine[2, 0] * I + target_affine[2, 1] * J + target_affine[2, 2] * K + target_affine[2, 3]
    nx = inv_a[0, 0] * wx + inv_a[0, 1] * wy + inv_a[0, 2] * wz + inv_a[0, 3]
    ny = inv_a[1, 0] * wx + inv_a[1, 1] * wy + inv_a[1, 2] * wz + inv_a[1, 3]
    nz = inv_a[2, 0] * wx + inv_a[2, 1] * wy + inv_a[2, 2] * wz + inv_a[2, 3]
    x0 = np.floor(nx).astype(np.int64); y0 = np.floor(ny).astype(np.int64); z0 = np.floor(nz).astype(np.int64)
    fx = nx - x0; fy = ny - y0; fz = nz - z0
    valid = ((x0 >= 0) & (x0 < sh[0] - 1) & (y0 >= 0) & (y0 < sh[1] - 1)
             & (z0 >= 0) & (z0 < sh[2] - 1))

    def g(x, y, z):
        x = np.clip(x, 0, sh[0] - 1); y = np.clip(y, 0, sh[1] - 1); z = np.clip(z, 0, sh[2] - 1)
        return d[x, y, z]

    val = (g(x0, y0, z0) * (1 - fx) * (1 - fy) * (1 - fz)
           + g(x0 + 1, y0, z0) * fx * (1 - fy) * (1 - fz)
           + g(x0, y0 + 1, z0) * (1 - fx) * fy * (1 - fz)
           + g(x0 + 1, y0 + 1, z0) * fx * fy * (1 - fz)
           + g(x0, y0, z0 + 1) * (1 - fx) * (1 - fy) * fz
           + g(x0 + 1, y0, z0 + 1) * fx * (1 - fy) * fz
           + g(x0, y0 + 1, z0 + 1) * (1 - fx) * fy * fz
           + g(x0 + 1, y0 + 1, z0 + 1) * fx * fy * fz)
    val[~valid] = 0.0
    return val


def write_nifti(prob, out, target_img):
    tgt = nib.load(str(target_img))
    hdr = nib.Nifti1Header()
    hdr.set_data_shape(prob.shape)
    hdr.set_zooms(list(tgt.header.get_zooms()[:3]))
    hdr.set_xyzt_units("mm", "sec")
    hdr.set_qform(tgt.get_qform(), code=int(tgt.header["qform_code"]))
    hdr.set_sform(tgt.get_sform(), code=int(tgt.header["sform_code"]))
    img = nib.Nifti1Image(prob.astype(np.float32), tgt.affine.copy(), header=hdr)
    nib.save(img, str(out))
    return sha256(out)


def main() -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for p in (V3, SRC_LEFT, SRC_RIGHT, SRC_TPL, SRC_TPL_MASK, TGT_TPL):
        if not p.exists():
            raise SystemExit(f"FAIL: missing input {p}")
    jpms = sorted(JULICH_PM_DIR.glob("*.nii.gz"))
    assert jpms, "no Julich probability maps for target grid authority"
    JUL_REF = jpms[0]

    v3_sha = sha256(V3)
    left_sha = sha256(SRC_LEFT)
    right_sha = sha256(SRC_RIGHT)
    assert v3_sha == V3_SHA_EXPECTED
    assert left_sha == LEFT_SHA_EXPECTED
    assert right_sha == RIGHT_SHA_EXPECTED
    src_tpl_sha = sha256(SRC_TPL)
    src_mask_sha = sha256(SRC_TPL_MASK)
    tgt_tpl_sha = sha256(TGT_TPL)
    jul_sha = sha256(JUL_REF)

    jul_nib = nib.load(str(JUL_REF))
    jul_data = np.asanyarray(jul_nib.dataobj)
    assert jul_data.shape == (193, 229, 193)
    jul_aff = jul_nib.affine

    # ---- shared-frame evidence ----
    tgt_nib = nib.load(str(TGT_TPL))
    sym_nib = nib.load(str(SRC_TPL))
    assert np.allclose(sym_nib.affine, tgt_nib.affine, atol=1e-4), "templates not shared-frame"
    assert sym_nib.shape == tgt_nib.shape == (193, 229, 193)
    mask_data = np.asanyarray(nib.load(str(SRC_TPL_MASK)).dataobj) > 0.5
    asym_arr = np.asanyarray(tgt_nib.dataobj)
    asym_brain = asym_arr > np.percentile(asym_arr[asym_arr > 0], 1)
    inter = (mask_data & asym_brain).sum()
    dice_identity = 2 * inter / (mask_data.sum() + asym_brain.sum() + 1e-9)
    assert dice_identity > 0.95

    # ---- spatial bridge resample (shared-frame coordinate grid resampling) ----
    left_img = nib.load(str(SRC_LEFT))
    right_img = nib.load(str(SRC_RIGHT))
    left_asym = linear_resample_to_grid(left_img, jul_data.shape, jul_aff, left_img.affine)
    right_asym = linear_resample_to_grid(right_img, jul_data.shape, jul_aff, right_img.affine)

    for hemi, arr in (("left", left_asym), ("right", right_asym)):
        neg = float((arr < -TOL).mean())
        pos = float((arr > 1 + TOL).mean())
        if neg > 1e-4 or pos > 1e-4:
            raise SystemExit(f"PROBABILITY_RANGE_QC_REVIEW: {hemi}")

    left_sha_o = write_nifti(left_asym, OUT_LEFT_ASYM, JUL_REF)
    right_sha_o = write_nifti(right_asym, OUT_RIGHT_ASYM, JUL_REF)

    for p in (OUT_LEFT_ASYM, OUT_RIGHT_ASYM):
        img = nib.load(str(p)); dd = np.asanyarray(img.dataobj)
        assert dd.shape == (193, 229, 193)
        assert np.allclose(img.affine, jul_aff, atol=1e-5)
        assert np.allclose(np.asarray(img.header.get_zooms())[:3], 1.0, atol=1e-4)

    # ---- per-side QC ----
    def qc(prob, src_p, gid, cid, hemi):
        X, Y, Z = np.meshgrid(np.arange(prob.shape[0]), np.arange(prob.shape[1]),
                              np.arange(prob.shape[2]), indexing="ij")
        xw = jul_aff[0, 0] * X + jul_aff[0, 3]; yw = jul_aff[1, 1] * Y + jul_aff[1, 3]
        zw = jul_aff[2, 2] * Z + jul_aff[2, 3]
        mass = float(prob.sum())
        support = int((prob > 0).sum())
        wvol = mass  # 1mm^3 voxels
        cx = float((prob * xw).sum() / (mass + 1e-12))
        cy = float((prob * yw).sum() / (mass + 1e-12))
        cz = float((prob * zw).sum() / (mass + 1e-12))
        nz = np.argwhere(prob > 0)
        bb = ([int(nz[:, 0].min()), int(nz[:, 1].min()), int(nz[:, 2].min())],
              [int(nz[:, 0].max()), int(nz[:, 1].max()), int(nz[:, 2].max())])
        s_img = nib.load(str(src_p))
        s = np.asanyarray(s_img.dataobj).astype(np.float64)
        svox = float(np.prod(s_img.header.get_zooms()[:3]))
        native_wvol = float(s.sum()) * svox
        contra = float(prob[(xw > 0) if hemi == "left" else (xw < 0)].sum() / (mass + 1e-12))
        return dict(geometry_id=gid, canonical_region_id=cid, hemisphere=hemi,
                    p_min=float(prob.min()), p_max=float(prob.max()), p_mean=float(prob.mean()),
                    sum_probability_mass=mass, weighted_volume_mm3=wvol,
                    support_voxels=support, centroid_mm=[round(cx, 3), round(cy, 3), round(cz, 3)],
                    bbox_voxel=bb, native_weighted_volume_mm3=native_wvol,
                    relative_volume_change=round((wvol - native_wvol) / (native_wvol + 1e-12), 4),
                    support_change=round(support / (int((s > 0).sum()) + 1e-12), 4),
                    frac_p_lt_neg_tol=float((prob < -TOL).mean()),
                    frac_p_gt_1_tol=float((prob > 1 + TOL).mean()),
                    contralateral_prob_fraction=round(contra, 6),
                    output_sha256=(left_sha_o if hemi == "left" else right_sha_o))

    qL = qc(left_asym, SRC_LEFT, GEOM_L, LID, "left")
    qR = qc(right_asym, SRC_RIGHT, GEOM_R, RID, "right")

    # ---- SPB manifest ----
    spb = dict(
        spatial_bridge_id=SPB_ID,
        spatial_bridge_class="SHARED_COORDINATE_REFERENCE_GRID_RESAMPLING",
        type_note="SPB = Spatial Bridge; NOT a TRF (transform).",
        source_space="ICBM152_2009C_SYMMETRIC",
        target_reference_space="MNI152NLin2009cAsym",
        source_world_coordinate_convention="RAS (NIfTI sform)",
        target_world_coordinate_convention="RAS (NIfTI sform)",
        source_grid=dict(shape=list(nib.load(str(SRC_LEFT)).shape), spacing_mm=0.5),
        target_grid=dict(shape=[193, 229, 193], spacing_mm=1.0),
        affine_relation="identical world-coordinate frame; grids differ only by sampling",
        resampling_method="header-driven trilinear world-coordinate resample",
        interpolation="LINEAR",
        registration_applied=False,
        nonlinear_registration_applied=False,
        nonlinear_registration_claimed=False,
        deformation_field_applied=False,
        resampling_applied=True,
        resampling_basis="SHARED_MNI152_2009C_WORLD_COORDINATE_FRAME",
        template_variant_statement="DIFFERENT_TEMPLATE_VARIANTS_WITH_SHARED_STEREOTAXIC_COORDINATE_FRAME",
        template_identity_statement="not IDENTICAL_ANATOMICAL_TEMPLATE; no NO_ANATOMICAL_DIFFERENCE claim",
        residual_spatial_limitation="TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_WARP_CORRECTED",
        freesurfer_source_semantics=(
            "ThalamusProbs.MNIsymSpace lives approximately in ICBM152 2009c symmetric "
            "world coordinates; probabilities share atlas world coordinates though not "
            "necessarily the voxel grid. FreeSurfer provenance does NOT prove Sym and "
            "Asym templates are anatomically identical."),
        transform_id=None,
        old_retracted_transform=dict(id=OLD_TRF_ID, status="RETRACTED"),
        moving_template=dict(path=str(SRC_TPL.relative_to(BACKEND)).replace("\\", "/"), sha256=src_tpl_sha,
                             brain_mask_sha256=src_mask_sha),
        fixed_template=dict(path=str(TGT_TPL.relative_to(BACKEND)).replace("\\", "/"), sha256=tgt_tpl_sha),
        julich_target_reference=dict(path=str(JUL_REF.relative_to(BACKEND)).replace("\\", "/"), sha256=jul_sha),
        shared_frame_qc=dict(identity_shared_frame_brain_dice=round(dice_identity, 4),
                             note="global brain-mask shared-frame agreement does NOT prove "
                                  "local thalamic anatomy identical"),
        generated_at=ts,
        independent_from_g3_g1_mapping=True,
        circularity_risk="NONE",
        script=str(Path(__file__).name), script_version=SCRIPT_VERSION,
    )
    with open(OUT_SPB_MAN, "w", encoding="utf-8") as fh:
        json.dump(spb, fh, ensure_ascii=False, indent=2)

    with open(OUT_SPB_QC, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["metric", "value"])
        w.writeheader()
        for k, v in [("identity_shared_frame_brain_dice", round(dice_identity, 4)),
                     ("spatial_bridge_class", spb["spatial_bridge_class"]),
                     ("registration_applied", False),
                     ("nonlinear_registration_applied", False),
                     ("resampling_applied", True),
                     ("interpolation", "LINEAR"),
                     ("residual_spatial_limitation", spb["residual_spatial_limitation"])]:
            w.writerow({"metric": k, "value": v})

    # ---- retraction record ----
    retr = dict(
        transform_id=OLD_TRF_ID,
        status="RETRACTED",
        reason="ANTSPY_SYN_ZERO_DISPLACEMENT_FIELD_PROVENANCE_ANOMALY",
        anomaly_details=dict(
            forward_nonlinear_warp="zero displacement",
            inverse_nonlinear_warp="zero displacement",
            identical_sha_cause="both represented empty/zero displacement field",
            full_syn_equals="affine/shared-grid result (max abs diff 0.0)",
            interpretation="previous nonlinear-transform interpretation invalid"),
        runtime_scope_note="CURRENT_RUNTIME_IMPLEMENTATION_ANOMALY on this "
                           "Windows/Python3.13/ANTsPy 0.6.3 runtime; NOT a general "
                           "statement that ANTs SyN is scientifically invalid.",
        replacement_route=dict(spatial_bridge_id=SPB_ID,
                               class_name="SHARED_COORDINATE_REFERENCE_GRID_RESAMPLING"),
        superseded_geometry=dict(
            left=dict(old_sha=OLD_LEFT_SHA, status="SUPERSEDED / INVALIDATED_BY_TRANSFORM_PROVENANCE_REPAIR"),
            right=dict(old_sha=OLD_RIGHT_SHA, status="SUPERSEDED / INVALIDATED_BY_TRANSFORM_PROVENANCE_REPAIR")),
        history_chain="attempt -> anomaly -> retraction -> replacement route (SPB)",
        generated_at=ts,
        script=str(Path(__file__).name), script_version=SCRIPT_VERSION,
    )
    with open(OUT_RETR, "w", encoding="utf-8") as fh:
        json.dump(retr, fh, ensure_ascii=False, indent=2)

    # ---- geometry manifest ----
    geom = dict(
        geometry_class="AUTHORITATIVE_DERIVED_G1_GEOMETRY",
        derivation="REFERENCE_GRID_RESAMPLING_FROM_NATIVE_G1_GEOMETRY",
        spatial_bridge_id=SPB_ID,
        transform_id=None,
        registration_applied=False,
        nonlinear_registration_applied=False,
        deformation_field_applied=False,
        resampling_applied=True,
        space_status="TARGET_MNI2009C_ASYMMETRIC",
        target_grid_ready=True,
        direct_overlap_grid_ready=True,
        authoritatively_registered_to_julich=False,
        template_variant_uncertainty="PRESENT",
        direct_overlap_evidence_type="DIRECT_SPATIAL_OVERLAP_IN_SHARED_MNI2009C_COORDINATE_FRAME",
        interpolation="LINEAR",
        threshold_applied=False, binarization_applied=False,
        clipping_applied=False, normalization_applied=False,
        entries=[
            dict(geometry_id=GEOM_L, canonical_region_id=LID, hemisphere="left",
                 source_native_geometry=dict(geometry_id="GEO-G1-THAL-L-FS2009CSYM-V1",
                                            path=str(SRC_LEFT.relative_to(BACKEND)).replace("\\", "/"),
                                            sha256=left_sha),
                 scope_contract=dict(id="THALAMUS_G1_SCOPE_CONTRACT_V3", sha256=v3_sha),
                 spatial_bridge_id=SPB_ID,
                 target_grid=dict(shape=[193, 229, 193], spacing_mm=1.0,
                                  affine=jul_aff.tolist(), reference=JUL_REF.name),
                 output_path=str(OUT_LEFT_ASYM.relative_to(BACKEND)).replace("\\", "/"),
                 output_sha256=left_sha_o, probability_qc=qL,
                 independent_from_g3_g1_mapping=True, circularity_risk="NONE",
                 script=str(Path(__file__).name), script_version=SCRIPT_VERSION,
                 run_timestamp=ts),
            dict(geometry_id=GEOM_R, canonical_region_id=RID, hemisphere="right",
                 source_native_geometry=dict(geometry_id="GEO-G1-THAL-R-FS2009CSYM-V1",
                                            path=str(SRC_RIGHT.relative_to(BACKEND)).replace("\\", "/"),
                                            sha256=right_sha),
                 scope_contract=dict(id="THALAMUS_G1_SCOPE_CONTRACT_V3", sha256=v3_sha),
                 spatial_bridge_id=SPB_ID,
                 target_grid=dict(shape=[193, 229, 193], spacing_mm=1.0,
                                  affine=jul_aff.tolist(), reference=JUL_REF.name),
                 output_path=str(OUT_RIGHT_ASYM.relative_to(BACKEND)).replace("\\", "/"),
                 output_sha256=right_sha_o, probability_qc=qR,
                 independent_from_g3_g1_mapping=True, circularity_risk="NONE",
                 script=str(Path(__file__).name), script_version=SCRIPT_VERSION,
                 run_timestamp=ts),
        ],
        bilateral=dict(volume_ratio_L_over_R=round(qL["weighted_volume_mm3"] / (qR["weighted_volume_mm3"] + 1e-12), 4)),
        residual_spatial_limitation="TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_WARP_CORRECTED",
    )
    with open(OUT_GEOM_MAN, "w", encoding="utf-8") as fh:
        json.dump(geom, fh, ensure_ascii=False, indent=2)

    geom_rows = []
    for q in (qL, qR):
        row = dict(q); row.pop("bbox_voxel")
        geom_rows.append(row)
    with open(OUT_GEOM_QC, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(geom_rows[0].keys()))
        w.writeheader()
        for r in geom_rows:
            w.writerow(r)

    # ---- environment provenance ----
    import sys, platform
    env = dict(
        python_version=sys.version.split()[0],
        python_executable=sys.executable,
        platform=str(platform.platform()),
        numpy_version=None, scipy_version=None, nibabel_version=None,
        antspy_version=None, simpleitk_version=None,
        antspy_syn_functional=False,
        antspy_syn_note="empty nonlinear warp output observed on this runtime; recorded as "
                        "CURRENT_RUNTIME_IMPLEMENTATION_ANOMALY, not used",
        note="Julich-reference geometry produced by shared-frame header-driven resample "
             "(nibabel+numpy); no external registration engine dependency",
    )
    for modname, key in (("numpy", "numpy_version"), ("scipy", "scipy_version"),
                         ("nibabel", "nibabel_version"), ("ants", "antspy_version"),
                         ("SimpleITK", "simpleitk_version")):
        try:
            mod = __import__(modname)
            env[key] = getattr(mod, "__version__", "unknown")
        except Exception:
            env[key] = None
    with open(OUT_ENV, "w", encoding="utf-8") as fh:
        json.dump(env, fh, ensure_ascii=False, indent=2)

    # ---- diagnostics ----
    md = [
        "# Phase1.7 V3 - Thalamus Julich-reference-grid G1 geometry (SPATIAL BRIDGE, v2)",
        "",
        "## Adjudicated scientific position",
        "- ICBM152 2009c symmetric and MNI152NLin2009cAsym are DIFFERENT template variants",
        "  with SHARED stereotaxic world-coordinate frame.",
        "- No authoritative nonlinear Sym->Asym anatomical warp is used; none is",
        "  manufactured.",
        "- Previous project-derived SyN attempt TRF-ICBM2009CSYM-TO-MNI2009CASYM-V1 is",
        "  RETRACTED (ANTSPy SyN zero-displacement provenance anomaly on this runtime).",
        "",
        f"spatial_bridge_id = {SPB_ID}",
        f"spatial_bridge_class = {spb['spatial_bridge_class']}  (NOT a TRF)",
        f"registration_applied = FALSE; nonlinear_registration_applied = FALSE; "
        f"deformation_field_applied = FALSE",
        f"resampling_applied = TRUE; resampling_basis = SHARED_MNI152_2009C_WORLD_COORDINATE_FRAME",
        f"interpolation = LINEAR",
        f"template_variant_statement = {spb['template_variant_statement']}",
        f"residual_spatial_limitation = {spb['residual_spatial_limitation']}",
        f"global shared-frame brain-mask Dice = {dice_identity:.4f}  (NOT proof of local "
        "thalamic anatomy identity)",
        f"direct-overlap evidence type = DIRECT_SPATIAL_OVERLAP_IN_SHARED_MNI2009C_COORDINATE_FRAME",
        f"left  = {GEOM_L}  wvol_mm3={qL['weighted_volume_mm3']:.3f}  centroid={qL['centroid_mm']}  "
        f"support={qL['support_voxels']}  rel_vol_change={qL['relative_volume_change']}",
        f"right = {GEOM_R}  wvol_mm3={qR['weighted_volume_mm3']:.3f}  centroid={qR['centroid_mm']}  "
        f"support={qR['support_voxels']}  rel_vol_change={qR['relative_volume_change']}",
        f"output grid = 193x229x193 @1mm; affine == Julich reference (verified); zooms=1mm",
        f"left  output_sha256 = {left_sha_o}",
        f"right output_sha256 = {right_sha_o}",
        "old SyN-derived geometry SHAs (37a82b65.../1c9b8b8d...) = SUPERSEDED / "
        "INVALIDATED_BY_TRANSFORM_PROVENANCE_REPAIR",
        "direct_overlap_grid_ready = TRUE; template_variant_uncertainty = PRESENT",
        "BN direct validation = PENDING_NEXT_FUNCTION; Promotion = BLOCKED",
        "no DB write; no commit; no reclassification; no BN/G4 overlap; no nonlinear "
        "registration claimed", "",
    ]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    print("spatial_bridge_id:", SPB_ID)
    print("identity shared-frame brain Dice:", round(dice_identity, 4))
    print("left  wvol", round(qL["weighted_volume_mm3"], 3), "centroid", qL["centroid_mm"])
    print("right wvol", round(qR["weighted_volume_mm3"], 3), "centroid", qR["centroid_mm"])
    print("left  sha", left_sha_o)
    print("right sha", right_sha_o)


if __name__ == "__main__":
    main()
