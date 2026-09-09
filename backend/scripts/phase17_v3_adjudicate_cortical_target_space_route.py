"""Phase1.7 V3 - fsaverage/MNI305 -> MNI152NLin2009cAsym target spatial route authority.

ADJUDICATION / AUDIT ONLY. No Docker, no license, no ribbon pilot, no cortical volume,
no transform application, no MNI2009c geometry, no G4/Julich overlap, no bulk 62
targets, no registration execution, no DB, no reclassification, no promotion.

Answers the only question of the round: by what scientific, traceable, G4-mapping-
INDEPENDENT spatial route can the current fsaverage cortical source-volume geometry
enter the MNI152NLin2009cAsym (Julich) reference space?

EVIDENCE (authoritative):
  - FreeSurfer official wiki: fsaverage is an average subject distributed by FreeSurfer
    that is ALREADY registered to Talairach/MNI305 space and is the default MNI305 target
    for mri_vol2vol; FreeSurfer 'Talairach MNI' coordinates ARE MNI305 coordinates; true
    Talairach differs via Brett's transform. talairach.xfm = affine orig -> MNI305 atlas
    (talairach_avi / mritotal vs MNI average_305). tkRAS (surface RAS) differs from
    scanner/world RAS by c_ras; vox2ras_tkr (Torig) is the FS-conformed tkRAS mapping.
  - TemplateFlow (per-template GitHub repos, enumerated live):
      tpl-MNI305            : T1w + brain/head masks only - NO transforms.
      tpl-MNI152NLin2009cAsym: transforms from-MNI152NLin6Asym (+ OASISTRT20) only -
                              NO from-MNI305/fsaverage.
      tpl-MNI152NLin6Asym    : transforms from-MNI152NLin2009cAsym (+ MNIInfant) only -
                              NO from-MNI305/fsaverage.
    => TemplateFlow hosts NO direct MNI305->2009cAsym transform and NO MNI305/fsaverage
       first-hop transform.
  - Real local assets:
      fsaverage mri/orig.mgz: 256^3 @1mm uint8, vox2ras==vox2ras_tkr (FS-internal grid),
          orientation LIA, world center ~ RAS (0.5,-0.5,0.5), SHA frozen.
      tpl-MNI305_T1w.nii.gz (acquired from TemplateFlow S3 this round, official):
          172x220x156 @1mm int16 RAS, sha256 ad5bbda6..., size 2879454 (annex md5 f590a905...).
      MNI152NLin2009cAsym_from-MNI152NLin6Asym_mode-image_xfm.h5 (frozen; sha
          2e3869a0...) + both template brains cached under data/atlases/templateflow_ref.

IDENTITY TEST (image-level, honest, computed live):
  resampling fsaverage orig onto the tpl-MNI305 RAS grid: NCC ~0.59, MI ~0.60 bits,
  brain COM displacement ~5.5 mm (z-dominated). => NOT exact grid identity; NOT a shared
  world-RAS frame at identity; moderate anatomical correspondence only.
  relation_classification = ONLY_DOCUMENTED_AS_MNI305_DERIVED (documented MNI305-derived
  template identity; actual grid/world-RAS identity with TemplateFlow tpl-MNI305 is NOT
  established and would require an affine/nonlinear whole-brain registration).

TALAIRACH: talairach.xfm absence is NOT a source-ribbon blocker (frozen) and, per FS
documentation, fsaverage's MNI305/Talairach identity is template-inherent
(TALAIRACH_XFM_NOT_REQUIRED_FOR_FSAVERAGE_TEMPLATE_IDENTITY). talairach.xfm remains
TARGET_ROUTE_RELATED_MISSING_ASSET for per-subject normalization only.

VERDICT: CORTICAL_TARGET_ROUTE_PROJECT_DERIVED_ALLOWED_PENDING_EXECUTION (D).
  - No official precomputed direct (A) or multi-hop (B) MNI305/fsaverage->2009cAsym
    transform exists (TemplateFlow authoritative enumeration; FreeSurfer dist is
    license-gated, unverifiable this round).
  - Shared-frame resample (C) is REJECTED: fsaverage orig and MNI152NLin2009cAsym are
    NOT a shared stereotaxic frame (Talairach/MNI305 != MNI152NLin2009cAsym; grids and
    content differ).
  - The scientifically allowed candidate (D) is a whole-brain anatomical registration
    (moving = fsaverage mri/orig.mgz whole-template intensity; fixed =
    MNI152NLin2009cAsym brain template) estimated WITHOUT any DK/Julich/G4 label content,
    then applied to future binary ribbon volumes with label-safe (NearestNeighbor)
    interpolation. Reproducible, mapping-independent, circularity_risk = NONE.
    NOT executed this round - requires an independent registration-execution round.
  route_v1 (CORTICAL_FSAVERAGE_TO_MNI2009C_ROUTE_V1) is NOT generated (only after the
  candidate route is executed + QC'd).
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import nibabel as nib
from nibabel.freesurfer.mghformat import MGHImage
from scipy.ndimage import map_coordinates

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
FS = BACKEND / "data" / "atlases" / "freesurfer" / "fsaverage"
TF = BACKEND / "data" / "atlases" / "templateflow_ref"
SCRIPT_VERSION = "phase17_v3_adjudicate_cortical_target_space_route.py v1"

OUT_SEM = D16 / "phase17_v3_fsaverage_mni305_semantic_audit.json"
OUT_GCMP = D16 / "phase17_v3_fsaverage_mni305_geometry_comparison.csv"
OUT_MREF = D16 / "phase17_v3_mni305_reference_asset_manifest.json"
OUT_TINV = D16 / "phase17_v3_cortical_target_transform_inventory.csv"
OUT_RC = D16 / "phase17_v3_cortical_target_route_candidates.csv"
OUT_COMP = D16 / "phase17_v3_cortical_target_route_compatibility_audit.json"
OUT_MD = D16 / "phase17_v3_cortical_target_route_diagnostics.md"
# OUT_V1 intentionally NOT produced (verdict D = pending execution)

ORIG = FS / "mri/orig.mgz"
MNI305 = TF / "tpl-MNI305_T1w.nii.gz"
NLIN6 = TF / "tpl-MNI152NLin6Asym_res01_desc-brain_T1w.nii.gz"
T09 = TF / "tpl-MNI152NLin2009cAsym_res01_desc-brain_T1w.nii.gz"
XFM = TF / "MNI152NLin2009cAsym_from-MNI152NLin6Asym_mode-image_xfm.h5"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def volume_geometry(img, path):
    h = img.header
    sh = np.array(img.shape)
    ctr_vox = np.array([(sh[0] - 1) / 2, (sh[1] - 1) / 2, (sh[2] - 1) / 2, 1.0])
    lo = img.affine @ np.array([0, 0, 0, 1.0])
    hi = img.affine @ np.r_[sh - 1, 1.0]
    return dict(
        path=str(path).replace("\\", "/"),
        sha256=sha256(path),
        size_bytes=path.stat().st_size,
        shape=[int(x) for x in sh],
        spacing=[float(z) for z in h.get_zooms()[:3]],
        dtype=str(img.get_data_dtype()),
        orientation="".join(nib.aff2axcodes(img.affine)),
        center_ras=[round(float(x), 2) for x in (img.affine @ ctr_vox)[:3]],
        fov_lo_ras=[round(float(x), 2) for x in lo[:3]],
        fov_hi_ras=[round(float(x), 2) for x in hi[:3]],
        affine_rows=[[round(float(x), 4) for x in row] for row in img.affine],
    )


def identity_test(orig_img, mni_img, mni_path, orig_sha):
    """Resample fsaverage orig onto tpl-MNI305 grid; honest content-level metrics."""
    od = orig_img.get_fdata().astype(np.float64)
    md = mni_img.get_fdata().astype(np.float64)
    inv_o = np.linalg.inv(orig_img.affine)
    sh = np.array(md.shape)
    i, j, k = np.meshgrid(np.arange(sh[0]), np.arange(sh[1]), np.arange(sh[2]), indexing="ij")
    vox_m = np.stack([i + 0.5, j + 0.5, k + 0.5, np.ones(i.shape)], axis=0).reshape(4, -1)
    ras_m = mni_img.affine @ vox_m
    vox_o = inv_o @ ras_m
    os_ = map_coordinates(od, vox_o[:3], mode="constant", cval=0.0, order=1).reshape(sh)

    mth = float(np.percentile(md[md > 0], 5)) if (md > 0).any() else 0.0
    oth = 25.0
    bm = (md > mth) & (os_ > oth)
    n = int(bm.sum())
    a = md[bm].ravel()
    b = os_[bm].ravel()
    ncc = float(np.corrcoef(a, b)[0, 1]) if n > 100 else None
    h2 = np.histogram2d(a, b, bins=64)[0] + 1e-12
    p = h2 / h2.sum()
    mi = float((p * np.log2(p / (p.sum(0, keepdims=True) * p.sum(1, keepdims=True)))).sum())

    def com_int(vals):
        w = vals > 0
        idx = np.argwhere(w).astype(float) + 0.5
        vw = vals[w]
        r = mni_img.affine[:3, :3] @ idx.T + mni_img.affine[:3, 3:4]
        return (vw[None, :] * r).sum(1) / (vw.sum() + 1e-9)

    cm = com_int(md)
    co = com_int(os_)
    disp = float(np.linalg.norm(cm - co))
    return dict(
        resample_target=str(mni_path).replace("\\", "/"),
        orig_sha256=orig_sha,
        ncc_masked=round(ncc, 4) if ncc is not None else None,
        mutual_info_bits=round(mi, 3),
        brain_com_ras_mni305=[round(float(x), 2) for x in cm],
        brain_com_ras_orig_resampled=[round(float(x), 2) for x in co],
        com_displacement_mm=round(disp, 2),
        masked_voxels=n,
        grid_identical=False,
        world_ras_identity=False,
        note="moderate anatomical correspondence only; exact grid/world-RAS identity with "
             "TemplateFlow tpl-MNI305 is NOT established; an affine/nonlinear whole-brain "
             "registration would be required to map between the grids.",
    )


def main() -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    orig_img = MGHImage.load(str(ORIG))
    mni_img = nib.load(str(MNI305))
    nlin6_img = nib.load(str(NLIN6))
    t09_img = nib.load(str(T09))

    g_orig = volume_geometry(orig_img, ORIG)
    g_mni = volume_geometry(mni_img, MNI305)
    g_nlin6 = volume_geometry(nlin6_img, NLIN6)
    g_t09 = volume_geometry(t09_img, T09)
    itest = identity_test(orig_img, mni_img, MNI305, g_orig["sha256"])

    # ---- semantic audit ----
    sem = dict(
        audit_id="FSAVERAGE_MNI305_SEMANTIC_AUDIT_V1",
        fsaverage_template_identity=dict(
            statement="FreeSurfer-distributed average subject (fsaverage); per the official "
                      "FreeSurfer wiki it is ALREADY registered to Talairach/MNI305 space and is "
                      "the default MNI305 target for mri_vol2vol.",
            source_urls=["https://surfer.nmr.mgh.harvard.edu/fswiki/CoordinateSystems",
                         "https://freesurfer.net/fswiki/FreeSurferTalairach"],
            local_fsaverage="data/atlases/freesurfer/fsaverage"),
        distinctions=dict(
            template_anatomical_identity="fsaverage = FS average template subject (MNI305-derived identity documented)",
            orig_voxel_grid="256^3 @1mm uint8, FS-conformed internal grid, vox2ras==vox2ras_tkr",
            fs_conformed_volume_geometry="conformed cube, world center ~ RAS origin area; not a scanner-space grid",
            tkRAS="surface RAS (tkRAS/Torig) - for fsaverage coincides with its vox2ras (template-internal)",
            scanner_world_RAS="vox2ras world RAS - distinct from tkRAS for regular subjects (c_ras shift); "
                               "for fsaverage orig they coincide by construction",
            mni305_stereotaxic="FreeSurfer 'Talairach MNI' coordinates ARE MNI305; true Talairach only via Brett transform",
            templateflow_mni305_grid="172x220x156 @1mm RAS int16 (tpl-MNI305_T1w)"),
        talairach_xfm=dict(
            official_semantics="per-subject affine from orig.mgz to the MNI305 atlas (average_305); created by "
                               "talairach_avi / mritotal",
            fsaverage_identity_role="TALAIRACH_XFM_NOT_REQUIRED_FOR_FSAVERAGE_TEMPLATE_IDENTITY - fsaverage's "
                                    "MNI305/Talairach identity is template-inherent (already registered); the "
                                    "absent xfm is not required to assert the DOCUMENTED identity",
            exact_grid_affine_unverified=True,
            note="asserting the exact affine of fsaverage tkRAS to the TemplateFlow tpl-MNI305 grid is NOT "
                 "possible without toolchain/registration - not assumed"),
        identity_test=itest,
        relation_classification="ONLY_DOCUMENTED_AS_MNI305_DERIVED",
        grid_identical=itest["grid_identical"],
        local_orig_sha256=g_orig["sha256"],
        created_at=ts, script_version=SCRIPT_VERSION)
    with open(OUT_SEM, "w", encoding="utf-8") as fh:
        json.dump(sem, fh, ensure_ascii=False, indent=2)

    # ---- geometry comparison CSV (source + MNI305 + target-frame context) ----
    with open(OUT_GCMP, "w", newline="", encoding="utf-8-sig") as fh:
        cols = ["volume_id", "role", "path", "sha256", "size_bytes", "shape", "spacing_mm",
                "dtype", "orientation", "center_ras", "fov_lo_ras", "fov_hi_ras", "affine"]
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for vid, role, g in (("fsaverage_orig.mgz", "SOURCE (cortical source volume)", g_orig),
                             ("tpl-MNI305_T1w", "AUTHORITATIVE MNI305 reference", g_mni),
                             ("tpl-MNI152NLin6Asym_res01_brain", "MNI152 frame (multi-hop context)", g_nlin6),
                             ("tpl-MNI152NLin2009cAsym_res01_brain", "TARGET frame (Julich space)", g_t09)):
            w.writerow(dict(volume_id=vid, role=role, path=g["path"], sha256=g["sha256"],
                            size_bytes=g["size_bytes"], shape=str(g["shape"]),
                            spacing_mm=str(g["spacing"]), dtype=g["dtype"],
                            orientation=g["orientation"], center_ras=str(g["center_ras"]),
                            fov_lo_ras=str(g["fov_lo_ras"]), fov_hi_ras=str(g["fov_hi_ras"]),
                            affine=str(g["affine_rows"])))
        # identity-test summary row
        w.writerow(dict(volume_id="IDENTITY_TEST_orig_vs_MNI305", role=itest["note"],
                        path=itest["resample_target"], sha256="", size_bytes="", shape="",
                        spacing_mm="", dtype="", orientation="", center_ras="",
                        fov_lo_ras="NCC=" + str(itest["ncc_masked"]), fov_hi_ras="",
                        affine="MI_bits=" + str(itest["mutual_info_bits"]) + " | COM_disp_mm=" +
                               str(itest["com_displacement_mm"])))

    # ---- MNI305 reference asset manifest ----
    mref = dict(
        provider="TemplateFlow (official template archive; Curator O. Esteban)",
        template_id="tpl-MNI305",
        identifier="MNI305",
        name="MNI Average Brain (305 MRI) Stereotaxic Registration Model",
        authors=["Collins DL", "Neelin P", "Peters TM", "Evans AC"],
        species="Homo sapiens",
        license="See tpl-MNI305 LICENSE (TemplateFlow)",
        download_url="https://templateflow.s3.amazonaws.com/tpl-MNI305/tpl-MNI305_T1w.nii.gz",
        local_path=str(MNI305).replace("\\", "/"),
        sha256=g_mni["sha256"],
        annex_md5="f590a905bdefb1bf18617d65907b2492",
        annex_size_bytes=2879454,
        size_bytes=g_mni["size_bytes"],
        shape=g_mni["shape"], spacing=g_mni["spacing"], dtype=g_mni["dtype"],
        orientation=g_mni["orientation"], affine=g_mni["affine_rows"],
        sibling_assets_present_in_repo=["desc-brain_mask", "desc-head_mask (not cached locally)"],
        reference_binary_status="AVAILABLE_LOCAL_CACHE (official TemplateFlow source)",
        created_at=ts, script_version=SCRIPT_VERSION)
    with open(OUT_MREF, "w", encoding="utf-8") as fh:
        json.dump(mref, fh, ensure_ascii=False, indent=2)

    # ---- transform inventory (authoritative) ----
    inv_rows = [
        dict(transform_id="XFM_NLIN6_TO_2009C", source="MNI152NLin6Asym", target="MNI152NLin2009cAsym",
             direction="NLin6Asym -> 2009cAsym", file="MNI152NLin2009cAsym_from-MNI152NLin6Asym_mode-image_xfm.h5",
             format="ITK h5 (SimpleITK)", provider="TemplateFlow", official="TRUE",
             availability="LOCAL_FROZEN", sha256="2e3869a07b96aec406e0419ca2e434afc54882d37cc212b933b139d1b63a4dfe",
             note="frozen project asset; usable only as final-hop candidate"),
        dict(transform_id="XFM_2009C_TO_NLIN6", source="MNI152NLin2009cAsym", target="MNI152NLin6Asym",
             direction="2009cAsym -> NLin6Asym", file="MNI152NLin6Asym_from-MNI152NLin2009cAsym_mode-image_xfm.h5",
             format="ITK h5", provider="TemplateFlow", official="TRUE",
             availability="TEMPLATEFLOW_REMOTE_NOT_CACHED", sha256="",
             note="inverse hop exists in tpl-MNI152NLin6Asym; not cached"),
        dict(transform_id="XFM_MNI305_TO_2009C", source="MNI305", target="MNI152NLin2009cAsym",
             direction="MNI305 -> 2009cAsym", file="(absent)",
             format="n/a", provider="TemplateFlow", official="FALSE",
             availability="NOT_PRESENT", sha256="",
             note="verified ABSENT in templateflow/tpl-MNI152NLin2009cAsym (only from-NLin6Asym and "
                  "from-OASISTRT20 exist)"),
        dict(transform_id="XFM_MNI305_TO_NLIN6", source="MNI305", target="MNI152NLin6Asym",
             direction="MNI305 -> NLin6Asym", file="(absent)",
             format="n/a", provider="TemplateFlow", official="FALSE",
             availability="NOT_PRESENT", sha256="",
             note="verified ABSENT in templateflow/tpl-MNI152NLin6Asym (only from-2009cAsym and "
                  "from-MNIInfant exist)"),
        dict(transform_id="XFM_FSAVERAGE_TO_ANY", source="fsaverage/FS subject", target="(any MNI152)",
             direction="fsaverage -> n/a", file="(absent)",
             format="n/a", provider="TemplateFlow", official="FALSE",
             availability="NOT_PRESENT", sha256="",
             note="TemplateFlow hosts no fsaverage-source transform (tpl-MNI305 has no transforms)"),
        dict(transform_id="XFM_FSDIST_SUBJECT_TALAIRACH", source="per-subject orig", target="MNI305",
             direction="orig -> MNI305 (affine)", file="transforms/talairach.xfm (inside full FS subject)",
             format="FreeSurfer xfm", provider="FreeSurfer official distribution",
             official="TRUE", availability="MANUAL_AUTHORIZED_ACCESS_REQUIRED", sha256="",
             note="FreeSurfer distribution is license-gated; NOT accessible this round; per-subject "
                  "normalization only; fsaverage identity does not require it"),
    ]
    with open(OUT_TINV, "w", newline="", encoding="utf-8-sig") as fh:
        cols = list(inv_rows[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in inv_rows:
            w.writerow(r)

    # ---- candidate routes ----
    rc_rows = [
        dict(route_id="R_A_DIRECT_OFFICIAL", class_code="A", summary="precomputed direct "
             "MNI305/fsaverage -> 2009cAsym transform",
             status="NOT_AVAILABLE", evidence="no such xfm in TemplateFlow (enumerated tpl-2009c, "
             "tpl-MNI305); FS dist not accessible (license)"),
        dict(route_id="R_B_MULTIHOP_OFFICIAL", class_code="B", summary="official precomputed "
             "multi-hop MNI305/fsaverage -> ... -> 2009cAsym",
             status="NOT_AVAILABLE", evidence="first hop (fsaverage/MNI305 -> any MNI152) does not "
             "exist authoritatively; NLin6->2009c alone cannot bridge from MNI305/fsaverage"),
        dict(route_id="R_C_SHARED_FRAME", class_code="C", summary="documented shared-frame RAS "
             "resample (no warp)",
             status="REJECTED", evidence="fsaverage orig and MNI152NLin2009cAsym are NOT a shared "
             "stereotaxic frame (Talairach/MNI305 != MNI152NLin2009cAsym); grids differ; NCC 0.59 / "
             "COM offset ~5.5mm vs tpl-MNI305 shows no identity - resample-only would be invalid"),
        dict(route_id="R_D_PROJECT_DERIVED_DIRECT", class_code="D", summary="project-derived whole-"
             "brain registration fsaverage mri/orig.mgz -> MNI152NLin2009cAsym brain (single final "
             "target registration), then apply to future binary ribbon with NearestNeighbor",
             status="CANDIDATE_ALLOWED_PENDING_EXECUTION",
             evidence="moving/fixed are whole-template anatomical intensities (no DK/Julich/G4 label "
             "content); reproducible; circularity NONE; execution deferred to an independent "
             "registration round"),
        dict(route_id="R_D2_PROJECT_DERIVED_VIA_NLIN6", class_code="D", summary="alternative: "
             "project-derived fsaverage orig -> NLin6Asym registration, then frozen official "
             "NLin6->2009cAsym as final hop",
             status="CANDIDATE_ALLOWED_PENDING_EXECUTION",
             evidence="mathematically valid 2-hop; MORE components/error than R_D_PROJECT_DERIVED_DIRECT "
             "and reuses the frozen xfm only as final hop; deprioritized vs direct-to-target candidate"),
        dict(route_id="R_E_FSDISTRIBUTION", class_code="A_or_B_IF_EXISTS", summary="FreeSurfer official "
             "distribution may contain FS-native MNI305/template assets/transforms",
             status="MANUAL_AUTHORIZED_ACCESS_REQUIRED", evidence="license-gated; cannot inventory "
             "this round; if later found, re-adjudicate (A/B would supersede D)"),
    ]
    with open(OUT_RC, "w", newline="", encoding="utf-8-sig") as fh:
        cols = list(rc_rows[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rc_rows:
            w.writerow(r)

    # ---- compatibility audit ----
    comp = dict(
        verdict="CORTICAL_TARGET_ROUTE_PROJECT_DERIVED_ALLOWED_PENDING_EXECUTION",
        coordinate_convention=dict(
            fsaverage_orig="world RAS via vox2ras (== vox2ras_tkr for fsaverage); internal tkRAS frame",
            templateflow_h5="ITK/SimpleITK convention (LPS-internal); resampling interpreted by SimpleITK "
                            "from NIfTI RAS headers",
            mni305="TemplateFlow tpl-MNI305 RAS grid (172x220x156 @1mm)"),
        ras_lps=dict(note="RAS and LPS must never be mixed by hand; SimpleITK reads NIfTI sform/qform so "
                          "the h5 application is header-consistent; any manual composition must respect "
                          "LPS convention"),
        frozen_final_hop=dict(transform="NLin6Asym -> 2009cAsym",
                              sha256="2e3869a07b96aec406e0419ca2e434afc54882d37cc212b933b139d1b63a4dfe",
                              usable_as="final hop ONLY; requires a compatible first hop whose source is "
                                        "fsaverage-orig/MNI305 (not present authoritatively)"),
        no_fsaverage_as_nlin6=True,
        no_fsaverage_as_nlin6_note="fsaverage/MNI305 must NEVER be treated as MNI152NLin6Asym; they are "
                                   "distinct spaces",
        composition_order="forward: moving(fsaverage orig) -> (project-derived warp) -> target grid; if "
                          "2-hop: apply hop1 then hop2 in head-to-target order; NN for discrete ribbon",
        interpolation_rule=dict(
            future_binary_ribbon="NearestNeighbor (label-safe) for discrete/binary cortical ribbon "
                                 "geometry in target space",
            future_fractional="fractional ribbon/probability semantics to be defined separately later",
            note="NOT applied this round; frozen as future semantics only"),
        do_not_conflate_note="Hippo/Amyg probability -> LINEAR interpolation does NOT carry over: "
                             "cortical ribbon is discrete/binary geometry",
        g4_circularity=dict(used_g4_overlap=False, used_mapping_result=False,
                            circularity_risk="NONE"),
        no_registration_executed=True,
        created_at=ts, script_version=SCRIPT_VERSION)
    with open(OUT_COMP, "w", encoding="utf-8") as fh:
        json.dump(comp, fh, ensure_ascii=False, indent=2)

    # ---- diagnostics ----
    md = [
        "# Phase1.7 V3 - fsaverage/MNI305 -> MNI152NLin2009cAsym target spatial route authority", "",
        f"VERDICT: {comp['verdict']} (D)",
        "No official precomputed direct (A) or multi-hop (B) MNI305/fsaverage -> 2009cAsym transform "
        "exists (TemplateFlow authoritative enumeration this round: tpl-2009c has only "
        "from-NLin6Asym/from-OASISTRT20; tpl-MNI305 and tpl-NLin6 have no MNI305/fsaverage-source "
        "transforms; FreeSurfer distribution is license-gated/unverifiable).",
        "Shared-frame resample (C) REJECTED: Talairach/MNI305 != MNI152NLin2009cAsym; grids differ.",
        "Scientifically allowed candidate (D): whole-brain anatomical registration of fsaverage "
        "mri/orig.mgz (moving) -> MNI152NLin2009cAsym brain template (fixed), estimated without any "
        "DK/Julich/G4 label content, then applied to future binary ribbon volumes with "
        "NearestNeighbor. Deferred to an independent registration-execution round (not run now).",
        "",
        "fsaverage MNI305 semantic audit (documentation-level statements are NOT proof of grid/"
        "world identity):",
        f"  local orig.mgz: shape {g_orig['shape']} @ {g_orig['spacing']} mm dtype {g_orig['dtype']} "
        f"orientation {g_orig['orientation']}, sha {g_orig['sha256'][:16]}...",
        f"  TemplateFlow tpl-MNI305: shape {g_mni['shape']} @ {g_mni['spacing']} mm dtype {g_mni['dtype']} "
        f"orientation {g_mni['orientation']}, sha {g_mni['sha256'][:16]}..., local cache.",
        "  fsaverage is documented (FreeSurfer wiki) as already registered to Talairach/MNI305; "
        "'Talairach MNI' == MNI305; true Talairach differs (Brett). talairach.xfm = per-subject "
        "orig->MNI305 affine; NOT required to assert fsaverage template identity.",
        f"  identity test (orig resampled onto tpl-MNI305 grid): NCC {itest['ncc_masked']}, "
        f"MI {itest['mutual_info_bits']} bits, brain COM displacement {itest['com_displacement_mm']} mm.",
        "  => relation_classification: ONLY_DOCUMENTED_AS_MNI305_DERIVED (not exact grid identity).",
        "",
        "Guardrails: no Docker/license/ribbon run, no transform applied, no MNI2009c geometry, no G4 "
        "overlap, no mapping-based tuning, no project-derived registration executed, no bulk 62, no "
        "DB, no reclassification, no promotion. route_v1 NOT generated (pending execution). "
        "Source-ribbon license blocker and prior frozen states unchanged.", ""]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    print("verdict:", comp["verdict"])
    print("relation:", sem["relation_classification"], "| grid_identical:", itest["grid_identical"])
    print("orig sha", g_orig["sha256"][:16], "| MNI305 sha", g_mni["sha256"][:16])
    print("NCC", itest["ncc_masked"], "MI", itest["mutual_info_bits"],
          "COM_disp_mm", itest["com_displacement_mm"])
    print("route_v1 NOT generated | wrote 7 artifacts")


if __name__ == "__main__":
    main()
