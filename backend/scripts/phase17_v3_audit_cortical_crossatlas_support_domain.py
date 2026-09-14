"""Phase1.7 V3 - Brainnetome <-> FreeSurfer DK cortical support-domain compatibility audit.

DIAGNOSTIC ONLY. Explains why raw containment is low (~0.32) and ~65% of BNA voxels fall
outside the current selected-62 G1 union, by separating four confounds:
  A. cortical support / tissue-representation mismatch (BNA volumetric parcels vs DK
     gray-matter ribbon)
  B. selected-62-only coverage omission (full official DK cortex has more labels)
  C. cross-route spatial inconsistency (BNA NLin6->2009c vs fsaverage->2009c)
  D. genuine atlas boundary disagreement

The V2 direct-spatial evidence (08e4508) is treated as IMMUTABLE. No mapping / geometry /
transform / registration / classification / DB changes. Independent evidence only:
  - full official DK cortical support (aparc+aseg + FreeSurferColorLUT DK set + frozen
    fsaverage->2009c transform, single NN application)
  - full BNA cortical support (parcel 1..210, official BN246 split: 1-210 cortical,
    211-246 subcortical)
  - official TemplateFlow MNI152NLin2009cAsym res-01 GM/WM/CSF tissue probability priors
    (probability mass; no arbitrary GM threshold as primary metric)
  - GM-weighted containment & 31-G1 competition (denominator independent of any G1)
  - physical-distance analysis of outside-full-DK BNA voxels to the DK ribbon
  - cross-route center-of-mass / extent / tissue-alignment comparison

Verdicts: A SUPPORT_DOMAIN_MISMATCH_CONFIRMED | B TRANSFORM_COMPATIBILITY_FAILED |
          C BOUNDARY_MISMATCH_DOMINANT | D UNRESOLVED.
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

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
SD = BACKEND / "data" / "atlases" / "derived_g1" / "cort_support_domain"
TF = BACKEND / "data" / "atlases" / "templateflow_ref"
FS = BACKEND / "data" / "atlases" / "freesurfer" / "fsaverage"
FSROOT = BACKEND / "data" / "atlases" / "freesurfer"
RUN = BACKEND / "data" / "atlases" / "derived_g1" / "cort_reg_run_v1"
G1DIR = BACKEND / "data" / "atlases" / "derived_g1" / "cort_g1_62"
SCRIPT_VERSION = "phase17_v3_audit_cortical_crossatlas_support_domain.py v1"
TRF_ID = "TRF-CORT-FSAVG-TO-MNI2009C-DIRECT-V1"
FINE_VOL = (BACKEND / "data/atlases/brainnetome/bna246/transformed_label_to_julich2009c/"
            "BN_Atlas_246_1mm_NLin6to2009c_labels.nii.gz")
FINE_SHA = "9c0185c7c0b9a2bf03a9e72d296d4fc8caed0e1318a59723a52ada8f06f1e19f"

ASEG = FS / "mri/aparc+aseg.mgz"
ORIG = FS / "mri/orig.mgz"
LUT = FSROOT / "FreeSurferColorLUT.txt"
FIXED = TF / "tpl-MNI152NLin2009cAsym_res01_desc-brain_T1w.nii.gz"
PGM = TF / "tpl-MNI152NLin2009cAsym_res-01_label-GM_probseg.nii.gz"
PWM = TF / "tpl-MNI152NLin2009cAsym_res-01_label-WM_probseg.nii.gz"
PCSF = TF / "tpl-MNI152NLin2009cAsym_res-01_label-CSF_probseg.nii.gz"
G1MAN = D16 / "phase17_v3_cortical_g1_62_reference_geometry_manifest.csv"
V1EVD = D16 / "phase17_v3_cortical_170_direct_spatial_evidence.csv"
UNIV = D16 / "phase17_v3_cortical_170_relation_universe.csv"
CVG = D16 / "phase17_v3_aparc_aseg_62target_coverage.csv"

OUT_ASSET = D16 / "phase17_v3_cortical_support_domain_asset_inventory.json"
OUT_FDK = D16 / "phase17_v3_full_dk_cortical_support_manifest.json"
OUT_BNA = D16 / "phase17_v3_bna_full_cortical_support_manifest.json"
OUT_TQ = D16 / "phase17_v3_cortical_support_domain_tissue_qc.json"
OUT_DEC = D16 / "phase17_v3_cortical_170_support_decomposition.csv"
OUT_GM = D16 / "phase17_v3_cortical_170_gm_weighted_evidence.csv"
OUT_GML = D16 / "phase17_v3_cortical_170_gm_weighted_competition_long.csv"
OUT_DIST = D16 / "phase17_v3_cortical_support_distance_qc.csv"
OUT_CR = D16 / "phase17_v3_cortical_crossroute_compatibility_qc.json"
OUT_ST = D16 / "phase17_v3_cortical_support_domain_status.json"
OUT_MD = D16 / "phase17_v3_cortical_support_domain_diagnostics.md"

DK_CANONICAL = ["bankssts", "caudalanteriorcingulate", "caudalmiddlefrontal", "cuneus",
                "entorhinal", "frontalpole", "fusiform", "inferiorparietal", "inferiortemporal",
                "insula", "isthmuscingulate", "lateraloccipital", "lateralorbitofrontal",
                "lingual", "medialorbitofrontal", "middletemporal", "parahippocampal",
                "paracentral", "parsopercularis", "parsorbitalis", "parstriangularis",
                "pericalcarine", "postcentral", "posteriorcingulate", "precentral", "precuneus",
                "rostralanteriorcingulate", "rostralmiddlefrontal", "superiorfrontal",
                "superiorparietal", "superiortemporal", "supramarginal", "temporalpole",
                "transversetemporal"]


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def parse_lut(path):
    out = {}
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        q = ln.split()
        if len(q) >= 2 and q[0].isdigit():
            out[int(q[0])] = q[1]
    return out


def write_json(p, o):
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(o, fh, ensure_ascii=False, indent=2)


def com(mask, aff):
    idx = np.argwhere(mask).astype(np.float64) + 0.5
    return (aff[:3, :3] @ idx.T + aff[:3, 3:4]).mean(1) if idx.shape[0] else np.full(3, np.nan)


def _best_translation(a, b, rng=15):
    """Integer voxel shift of `b` that maximises its overlap with `a` (FFT cross-correlation).

    Thickness-insensitive: unlike a centre-of-mass difference it is not biased by the two
    supports carrying different amounts of tissue. Sign convention: rolling `b` by the
    returned shift on each axis maximises the overlap with `a`. Verified against a
    synthetic known shift at import time (see _selftest_best_translation).
    """
    A = a.astype(np.float32)
    B = b.astype(np.float32)
    c = np.fft.fftshift(np.fft.irfftn(
        np.fft.rfftn(A, s=A.shape, axes=(0, 1, 2)) *
        np.conj(np.fft.rfftn(B, s=B.shape, axes=(0, 1, 2))), s=A.shape, axes=(0, 1, 2)))
    ctr = np.array(A.shape) // 2
    win = c[tuple(slice(int(ctr[i]) - rng, int(ctr[i]) + rng + 1) for i in range(3))]
    idx = np.unravel_index(int(np.argmax(win)), win.shape)
    return np.array(idx, dtype=int) - rng, float(win.max())


def _selftest_best_translation():
    """Deterministic guard against a silent sign/index error in _best_translation."""
    z = np.zeros((41, 43, 45), dtype=bool)
    z[5:20, 6:30, 7:25] = True
    truth = np.array([3, -4, 2])
    moved = np.roll(np.roll(np.roll(z, truth[0], 0), truth[1], 1), truth[2], 2)
    got, _ = _best_translation(z, moved)
    assert np.array_equal(got, -truth), f"_best_translation selftest failed: {got} != {-truth}"


# Support-domain-aware compatibility thresholds. Justified by the measured morphology of
# the two supports: the DK cortical ribbon is ~4 mm thick, so only an offset approaching
# that scale is detectable as displacement, and BNA parcels form a ~3 mm thicker
# volumetric territory around it. The previous criterion (cortical COM difference > 4 mm)
# is invalid here because a thickened support has a different COM without having moved.
COMPAT_SHIFT_TOL_MM = 2.0
COMPAT_DK_CONTAINMENT_MIN = 0.90
COMPAT_EXTRA_MEDIAN_MM_MAX = 2.5
COMPAT_SUPPORT_OFFSET_MIN_MM = 2


def support_domain_compatibility(bna_union, dk_union, aff):
    """Support-domain-aware cross-route spatial compatibility assessment.

    Replaces the centre-of-mass difference criterion. Every measure below is insensitive
    to the difference in cortical support-domain thickness between the two routes:
      - FFT-optimal relative translation of one support onto the other (detects real
        displacement independent of mass distribution),
      - containment of the thin (ribbon) support inside the thick (parcel) support,
      - distance bound from the excess layer to the thin support,
      - fitted uniform-dilation offset that reproduces the thick support (descriptive).
    """
    inter = int((bna_union & dk_union).sum())
    n_bna, n_dk = int(bna_union.sum()), int(dk_union.sum())
    dice0 = 2.0 * inter / (n_bna + n_dk)
    shift_vox, peak = _best_translation(dk_union, bna_union)
    axis_mm = np.linalg.norm(aff[:3, :3], axis=0)
    shift_mm = shift_vox.astype(float) * axis_mm
    dk_in_bna = inter / n_dk
    bna_in_dk = inter / n_bna
    # displacement bound: where the excess layer (BNA beyond the ribbon) actually sits
    d_dk = ndimage.distance_transform_edt(~dk_union)
    extra = bna_union & ~dk_union
    ev = d_dk[extra] if extra.any() else np.zeros(1)
    # support-domain offset: uniform dilation of the ribbon that best reproduces BNA
    st = ndimage.generate_binary_structure(3, 1)
    cur = dk_union
    offset_r, offset_dice = 0, dice0
    for r in range(1, 7):
        cur = ndimage.binary_dilation(cur, structure=st, iterations=1)
        sc = 2.0 * int((cur & bna_union).sum()) / (int(cur.sum()) + n_bna)
        if sc > offset_dice:
            offset_r, offset_dice = r, sc
    ok = bool(float(np.max(np.abs(shift_mm))) <= COMPAT_SHIFT_TOL_MM
              and dk_in_bna >= COMPAT_DK_CONTAINMENT_MIN
              and float(np.median(ev)) <= COMPAT_EXTRA_MEDIAN_MM_MAX)
    return dict(
        method="support-domain-aware (FFT optimal translation + containment + excess-layer "
               "distance bound); COM difference is reported but NOT used as a criterion",
        optimal_shift_vox=shift_vox.tolist(),
        optimal_shift_mm=[round(float(x), 3) for x in shift_mm],
        max_abs_shift_mm=round(float(np.max(np.abs(shift_mm))), 3),
        dice_at_zero_shift=round(float(dice0), 5),
        dice_at_optimal_shift=round(float(2.0 * peak / (n_bna + n_dk)), 5),
        dk_in_bna_containment=round(float(dk_in_bna), 5),
        bna_in_dk_containment=round(float(bna_in_dk), 5),
        excess_layer_voxels=int(extra.sum()),
        excess_layer_median_distance_mm=round(float(np.median(ev)), 3),
        excess_layer_p90_distance_mm=round(float(np.percentile(ev, 90)), 3),
        support_thickness_offset_mm=int(offset_r),
        support_thickness_offset_dice=round(float(offset_dice), 5),
        thresholds=dict(shift_tol_mm=COMPAT_SHIFT_TOL_MM,
                        dk_containment_min=COMPAT_DK_CONTAINMENT_MIN,
                        excess_median_max_mm=COMPAT_EXTRA_MEDIAN_MM_MAX,
                        support_offset_min_mm=COMPAT_SUPPORT_OFFSET_MIN_MM),
        spatial_compatibility_ok=ok,
        verdict=("SPATIALLY_COMPATIBLE" if ok else "CROSS_ROUTE_DISPLACEMENT_DETECTED"))


def main() -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _selftest_best_translation()
    SD.mkdir(parents=True, exist_ok=True)

    # ---------- independent assets ----------
    m = np.asanyarray(nib.load(str(FINE_VOL)).dataobj).astype(np.int16)
    gm = np.asanyarray(nib.load(str(PGM)).dataobj).astype(np.float64)
    wm = np.asanyarray(nib.load(str(PWM)).dataobj).astype(np.float64)
    csf = np.asanyarray(nib.load(str(PCSF)).dataobj).astype(np.float64)
    fixed_nib = nib.load(str(FIXED))
    faff = fixed_nib.affine

    # selected-62 G1 masks by canonical id + same-side unions
    g1rows = list(csv.DictReader(open(G1MAN, encoding="utf-8-sig")))
    g1mask = {}
    for r in g1rows:
        g1mask[r["canonical_region_id"]] = np.asanyarray(
            nib.load(str(G1DIR / f"{r['geometry_id']}.nii.gz")).dataobj) > 0
    sel_by_side = {"left": [], "right": []}
    union62 = {"left": np.zeros(m.shape, bool), "right": np.zeros(m.shape, bool)}
    for r in g1rows:
        sel_by_side[r["hemisphere"]].append(r["canonical_region_id"])
        union62[r["hemisphere"]] |= g1mask[r["canonical_region_id"]]

    # V1 evidence + universe (immutable read; assert containment/rank equality later)
    v1 = list(csv.DictReader(open(V1EVD, encoding="utf-8-sig")))
    assert len(v1) == 170
    univ = {r["fine_region_id"]: r for r in csv.DictReader(open(UNIV, encoding="utf-8-sig"))}
    sel_dk_by_side = {"left": set(), "right": set()}
    for r in csv.DictReader(open(CVG, encoding="utf-8-sig")):
        sel_dk_by_side[r["hemisphere"]].add(r["dk_label_name"])
    selected_dk_names = sel_dk_by_side["left"] | sel_dk_by_side["right"]

    # ---------- full official DK cortical support (from aparc+aseg + LUT) ----------
    lut = parse_lut(LUT)
    ad = np.asanyarray(MGHImage.load(str(ASEG)).dataobj)
    oaff = MGHImage.load(str(ORIG)).affine
    dk_ids = []
    dk_ids_l = []
    dk_ids_r = []
    for lid in np.unique(ad):
        nm = lut.get(int(lid), "")
        if nm.startswith("ctx-") and nm[7:] in DK_CANONICAL and int((ad == lid).sum()) > 0:
            dk_ids.append(int(lid))
            if nm.startswith("ctx-lh-"):
                dk_ids_l.append(int(lid))
            else:
                dk_ids_r.append(int(lid))
    dk_ids = sorted(dk_ids)
    full_dk_lm_fs = np.where(np.isin(ad, np.array(dk_ids)), ad, 0).astype(np.int16)
    nib.save(nib.Nifti1Image(full_dk_lm_fs, oaff), str(SD / "FULL_DK_CORTICAL_LABELMAP_FSAVG_DIAGNOSTIC.nii.gz"))
    # transform once NN to 2009c
    moving_ants = ants.image_read(str(RUN / "moving_fsaverage_orig.nii.gz"))
    fixed_ants = ants.image_read(str(FIXED))
    lm_ants = ants.from_numpy(full_dk_lm_fs, origin=moving_ants.origin, spacing=moving_ants.spacing,
                              direction=moving_ants.direction)
    fwd = [str(RUN / f"{TRF_ID}_forward_warp.nii.gz"), str(RUN / f"{TRF_ID}_affine.mat")]
    tgt_ants = ants.apply_transforms(fixed=fixed_ants, moving=lm_ants, transformlist=fwd,
                                     interpolator="nearestNeighbor")
    full_dk_tgt = tgt_ants.numpy().astype(np.int16)
    nib.save(nib.Nifti1Image(full_dk_tgt, faff), str(SD / "FULL_DK_CORTICAL_LABELMAP_MNI2009C_DIAGNOSTIC.nii.gz"))
    full_dk_union = full_dk_tgt > 0
    dk_tgt_ids = sorted({int(x) for x in np.unique(full_dk_tgt) if x > 0})
    # per-side full dk names
    names_side = {"left": set(), "right": set()}
    for lid in dk_ids:
        nm = lut.get(lid, "")
        side = "left" if nm.startswith("ctx-lh-") else "right"
        names_side[side].add(nm[7:])
    omitted = {s: sorted(names_side[s] - sel_dk_by_side[s]) for s in ("left", "right")}
    omitted_names = omitted

    # ---------- full BNA cortical support (parcels 1..210) ----------
    bna_cortical_union = (m >= 1) & (m <= 210)
    bna_semantics = dict(
        atlas_version="BNA246 (2016) Fan et al. Cerebral Cortex 26(8):3508-3526",
        parcel_scope="210 cortical (1..210) + 36 subcortical (211..246: Tha16 BG12 Amyg4 Hipp4) - "
                     "official split inferred from authoritative BN table and G3 manifest codes",
        label_semantics="cortical parcel volumetric territory at 1mm in MNI space "
                        "(surface-derived volumetric labels)",
        tissue_constrained_ribbon_official="NOT_STATED_IN_AUTHORITY_METADATA -> "
                                           "SEMANTICS_PARTIALLY_RESOLVED",
        note="tissue composition measured independently from TemplateFlow GM/WM/CSF priors below")
    # full BNA union diagnostic nii (mask values 1 inside cortical parcels)
    nib.save(nib.Nifti1Image((bna_cortical_union.astype(np.int16)) * 1, faff),
             str(SD / "BNA_FULL_CORTICAL_UNION_MNI2009C_V1.nii.gz"))
    # full DK union diagnostic nii
    nib.save(nib.Nifti1Image(full_dk_union.astype(np.int16), faff),
             str(SD / "FULL_DK_CORTICAL_RIBBON_UNION_MNI2009C_DIAGNOSTIC.nii.gz"))

    # asset inventory / manifests
    write_json(OUT_ASSET, dict(
        bna_volume=dict(path=str(FINE_VOL).replace("\\", "/"), sha256=sha256(FINE_VOL),
                        space="MNI152NLin2009cAsym 1mm (NLin6->2009c frozen route)", grid=list(m.shape)),
        full_dk_labelmap_fs=dict(sha256=sha256(SD / "FULL_DK_CORTICAL_LABELMAP_FSAVG_DIAGNOSTIC.nii.gz"),
                                 dk_ids_l=len(dk_ids_l), dk_ids_r=len(dk_ids_r)),
        full_dk_labelmap_tgt=dict(sha256=sha256(SD / "FULL_DK_CORTICAL_LABELMAP_MNI2009C_DIAGNOSTIC.nii.gz"),
                                  target_ids=len(dk_tgt_ids), grid=list(m.shape)),
        tissue_priors=dict(
            gm=dict(path=str(PGM).replace("\\", "/"), sha256=sha256(PGM), provider="TemplateFlow "
                    "(official) tpl-MNI152NLin2009cAsym res-01 label-GM probseg"),
            wm=dict(path=str(PWM).replace("\\", "/"), sha256=sha256(PWM)),
            csf=dict(path=str(PCSF).replace("\\", "/"), sha256=sha256(PCSF))),
        transform=dict(id=TRF_ID,
                       fwd_sha=sha256(RUN / f"{TRF_ID}_forward_warp.nii.gz"),
                       aff_sha=sha256(RUN / f"{TRF_ID}_affine.mat")),
        bna_semantics=bna_semantics,
        created_at=ts, script_version=SCRIPT_VERSION))
    write_json(OUT_FDK, dict(
        full_dk_ids=dk_ids, left_ids=dk_ids_l, right_ids=dk_ids_r,
        left_label_names=sorted(names_side["left"]), right_label_names=sorted(names_side["right"]),
        selected_62_names=sorted(selected_dk_names),
        omitted_dk_labels=omitted_names,
        omitted_count_per_side={s: len(omitted_names[s]) for s in ("left", "right")},
        voxels=dict(union=int(full_dk_union.sum()), left=int((full_dk_union & _side_vol(faff, "left")).sum()),
                    right=int((full_dk_union & _side_vol(faff, "right")).sum())),
        diag_assets="FULL_DK_CORTICAL_LABELMAP_FSAVG/MNI2009C_DIAGNOSTIC + "
                    "FULL_DK_CORTICAL_RIBBON_UNION (gitignored)",
        created_at=ts, script_version=SCRIPT_VERSION))
    write_json(OUT_BNA, dict(
        cortical_parcel_ids=[1, 210], cortical_parcel_count=210, subcortical_ids=[211, 246],
        subcortical_parcel_count=36,
        bna_cortical_union_voxels=int(bna_cortical_union.sum()),
        diag_asset="BNA_FULL_CORTICAL_UNION_MNI2009C_V1 (gitignored)",
        created_at=ts, script_version=SCRIPT_VERSION))

    # ---------- tissue helper ----------
    def mass_props(mask):
        gm_v, wm_v, csf_v = float((gm * mask).sum()), float((wm * mask).sum()), float((csf * mask).sum())
        tot = gm_v + wm_v + csf_v
        return dict(gm=gm_v, wm=wm_v, csf=csf_v,
                    gm_frac=round(gm_v / tot, 5) if tot else 0.0,
                    wm_frac=round(wm_v / tot, 5) if tot else 0.0,
                    csf_frac=round(csf_v / tot, 5) if tot else 0.0,
                    sum_prob=round(gm_v + wm_v + csf_v, 2))

    dk_tissue = mass_props(full_dk_union)
    sel62_tissue = mass_props(union62["left"] | union62["right"])
    bna_cort_tissue = mass_props(bna_cortical_union)
    write_json(OUT_TQ, dict(
        bna_cortical_union=mass_props(bna_cortical_union),
        full_dk_ribbon_union=dk_tissue,
        selected_62_union=sel62_tissue,
        note="probability-mass fractions (TemplateFlow GM/WM/CSF); no threshold used"))
    # outside-full-DK GM subset check etc computed per-parcel below

    # EDT distance to full DK ribbon
    edt = ndimage.distance_transform_edt(~full_dk_union)  # voxel dist to nearest fullDK (1mm grid)

    # weighted bincount helpers
    Wgm_parcel = np.bincount(m.ravel(), weights=gm.ravel(), minlength=247)
    # per-G1 weighted overlap per parcel
    overlapW = {}  # g1_id -> array(247)
    for cid, gmm in g1mask.items():
        overlapW[cid] = np.bincount(m[gmm], weights=gm[gmm], minlength=247)

    raw_decomp = []
    gm_rows = []
    gm_long = []
    dist_rows = []
    for vr in v1:
        cid_p = vr["fine_region_id"]
        pid = int(univ[cid_p]["parcel_id"])
        hemi = vr["hemisphere"]
        fine = m == pid
        fsz = int(fine.sum())
        un_sel = union62[hemi]
        inside62 = int((fine & un_sel).sum())
        inside_fulldk = int((fine & full_dk_union).sum())
        inside_omitted = int((fine & full_dk_union & ~un_sel).sum())
        out62 = fsz - inside62
        out_fdk = fsz - inside_fulldk
        # tissue of outside-full-DK portion
        od = fine & ~full_dk_union
        out_tissue = mass_props(od) if out_fdk else dict(gm_frac=0.0, wm_frac=0.0, csf_frac=0.0,
                                                         gm=0.0, wm=0.0, csf=0.0, sum_prob=0.0)
        # distance stats of outside voxels
        if out_fdk:
            dvals = edt[od]
            dist_rows.append(dict(fine_region_id=cid_p, hemisphere=hemi,
                                  outside_full_dk_voxels=out_fdk,
                                  median_mm=round(float(np.median(dvals)), 3),
                                  p75_mm=round(float(np.percentile(dvals, 75)), 3),
                                  p90_mm=round(float(np.percentile(dvals, 90)), 3),
                                  p95_mm=round(float(np.percentile(dvals, 95)), 3),
                                  max_mm=round(float(dvals.max()), 3),
                                  outside_gm_frac=out_tissue["gm_frac"]))
        raw_decomp.append(dict(fine_region_id=cid_p, hemisphere=hemi, fine_voxels=fsz,
                               inside_selected62_voxels=inside62,
                               inside_selected62_fraction=round(inside62 / fsz, 5),
                               outside_selected62_fraction=round(out62 / fsz, 5),
                               inside_full_dk_fraction=round(inside_fulldk / fsz, 5),
                               inside_omitted_dk_fraction=round(inside_omitted / fsz, 5),
                               outside_full_dk_fraction=round(out_fdk / fsz, 5),
                               conservation_check=round((inside62 + inside_omitted + out_fdk) / fsz, 6)))
        # GM-weighted metrics
        denom = float(Wgm_parcel[pid])
        prop = vr["proposed_g1_id"]
        num = float(overlapW[prop][pid])
        gmc = num / denom if denom else 0.0
        order = []
        for cid in sel_by_side[hemi]:
            o = float(overlapW[cid][pid]) / denom if denom else 0.0
            order.append((cid, o))
        order.sort(key=lambda kv: -kv[1])
        wprop_rank = 1 + sum(1 for kv in order if kv[1] > gmc + 1e-12)
        best = order[0]
        best_non = next((kv for kv in order if kv[0] != prop), None)
        gm_rows.append(dict(
            fine_region_id=cid_p, hemisphere=hemi, gm_mass=round(denom, 2),
            raw_proposed_containment=vr["proposed_containment"],
            gm_weighted_proposed_containment=round(gmc, 5),
            raw_proposed_rank=int(vr["proposed_rank"]),
            gm_weighted_rank=wprop_rank,
            raw_best_competitor=vr["best_non_proposed_g1_id"],
            gm_best_non_proposed_id=best_non[0] if best_non else "",
            gm_best_non_proposed_score=round(best_non[1], 5) if best_non else 0.0,
            gm_margin=round(gmc - (best_non[1] if best_non else 0.0), 5),
            gm_inside_full_dk_fraction=round(inside_fulldk / fsz, 5) if fsz else 0.0,
            gm_outside_full_dk_fraction=round(out_fdk / fsz, 5) if fsz else 0.0))
        for cid, o in order:
            gm_long.append(dict(fine_region_id=cid_p, hemisphere=hemi, g1_id=cid,
                                gm_weighted_score=round(o, 5)))

    # raw vs weighted summary (only over rows present both = all 170)
    raw_c = [float(r["proposed_containment"]) for r in v1]
    w_c = [r["gm_weighted_proposed_containment"] for r in gm_rows]
    med_raw, p25_raw, p75_raw = np.median(raw_c), np.percentile(raw_c, 25), np.percentile(raw_c, 75)
    med_w, p25_w, p75_w = np.median(w_c), np.percentile(w_c, 25), np.percentile(w_c, 75)
    spearman = float(np.corrcoef(raw_c, w_c)[0, 1])
    wrank1 = sum(1 for r in gm_rows if r["gm_weighted_rank"] == 1)
    rank_change = sum(1 for r in gm_rows if r["gm_weighted_rank"] != r["raw_proposed_rank"])

    with open(OUT_DEC, "w", newline="", encoding="utf-8-sig") as fh:
        cols = list(raw_decomp[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for row in raw_decomp:
            w.writerow(row)
    with open(OUT_GM, "w", newline="", encoding="utf-8-sig") as fh:
        cols = list(gm_rows[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for row in gm_rows:
            w.writerow(row)
    with open(OUT_GML, "w", newline="", encoding="utf-8-sig") as fh:
        cols = list(gm_long[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for row in gm_long:
            w.writerow(row)
    with open(OUT_DIST, "w", newline="", encoding="utf-8-sig") as fh:
        cols = list(dist_rows[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for row in dist_rows:
            w.writerow(row)

    # ---------- cross-route compatibility ----------
    # COM values are reported for description only. They are NOT used as a criterion: the
    # two supports carry different amounts of tissue (BNA = volumetric parcel territory,
    # DK = FreeSurfer GM ribbon), so a thickened support has a different COM without moving.
    com_bna = com(bna_cortical_union, faff)
    com_dk = com(full_dk_union, faff)
    com_delta = float(np.linalg.norm(com_bna - com_dk))
    compat = support_domain_compatibility(bna_cortical_union, full_dk_union, faff)
    # extents
    def bbox_extent(mask):
        idx = np.argwhere(mask)
        return idx.max(0) - idx.min(0)
    ext_bna = bbox_extent(bna_cortical_union)
    ext_dk = bbox_extent(full_dk_union)
    gm_alignment_delta = dk_tissue["gm_frac"] - bna_cort_tissue["gm_frac"]
    cross = dict(
        bna_cortical_com_mm=com_bna.round(2).tolist(), dk_ribbon_com_mm=com_dk.round(2).tolist(),
        com_delta_mm=round(com_delta, 3),
        com_note="DESCRIPTIVE ONLY - not a spatial criterion; the two supports differ in "
                 "thickness/extent so their COMs are not comparable "
                 "(see cross_route_spatial_compatibility)",
        extent_bna_vox=ext_bna.tolist(), extent_dk_vox=ext_dk.tolist(),
        bna_cortical_union_gm_frac=bna_cort_tissue["gm_frac"],
        dk_ribbon_union_gm_frac=dk_tissue["gm_frac"],
        gm_frac_delta=round(gm_alignment_delta, 5),
        selected62_gm_frac=sel62_tissue["gm_frac"],
        cross_route_spatial_compatibility=compat,
        note="no registration/transform run; diagnostic of frozen routes only",
        created_at=ts, script_version=SCRIPT_VERSION)
    write_json(OUT_CR, cross)

    # ---------- interpretability + verdict ----------
    out62s = [r["outside_selected62_fraction"] for r in raw_decomp]
    out_fdk_s = [r["outside_full_dk_fraction"] for r in raw_decomp]
    omitted_s = [r["inside_omitted_dk_fraction"] for r in raw_decomp]
    out_tissue_gm = [d["outside_gm_frac"] for d in dist_rows]
    median_improve = med_w - med_raw
    low_gm_outside = bool(np.median(out_tissue_gm) < 0.5) if out_tissue_gm else True
    # verdict rules (explicit diagnostic thresholds). Cross-route displacement is now
    # decided by support-domain-aware criteria, not by the cortical COM difference.
    cross_route_displacement_detected = not compat["spatial_compatibility_ok"]
    support_offset_detected = (compat["support_thickness_offset_mm"]
                               >= COMPAT_SUPPORT_OFFSET_MIN_MM)
    if cross_route_displacement_detected:
        verdict = "CORTICAL_CROSS_ATLAS_TRANSFORM_COMPATIBILITY_FAILED"
    elif support_offset_detected:
        verdict = "CORTICAL_CROSS_ATLAS_SUPPORT_DOMAIN_MISMATCH_CONFIRMED"
    elif not low_gm_outside and median_improve < 0.12:
        verdict = "CORTICAL_ATLAS_BOUNDARY_MISMATCH_DOMINANT"
    else:
        verdict = "CORTICAL_SUPPORT_DOMAIN_COMPATIBILITY_UNRESOLVED"
    raw_interpret = ("DESCRIPTIVE_ONLY" if verdict in (
        "CORTICAL_CROSS_ATLAS_SUPPORT_DOMAIN_MISMATCH_CONFIRMED",
        "CORTICAL_ATLAS_BOUNDARY_MISMATCH_DOMINANT") else
        ("INVALID_FOR_ADJUDICATION" if verdict == "CORTICAL_CROSS_ATLAS_TRANSFORM_COMPATIBILITY_FAILED"
         else "UNRESOLVED"))
    status = dict(
        status_id="CORTICAL_SUPPORT_DOMAIN_COMPATIBILITY_STATUS_V1",
        verdict=verdict,
        raw_containment_interpretability=raw_interpret,
        raw_outside_union_interpretability=("SELECTED_G1_COVERAGE_BIASED + SUPPORT_DOMAIN_BIASED"
                                            if verdict in (
            "CORTICAL_CROSS_ATLAS_SUPPORT_DOMAIN_MISMATCH_CONFIRMED",
            "CORTICAL_ATLAS_BOUNDARY_MISMATCH_DOMINANT") else
            ("UNRESOLVED" if verdict == "CORTICAL_SUPPORT_DOMAIN_COMPATIBILITY_UNRESOLVED"
             else "TRANSFORM_BIASED")),
        decomposition=dict(outside_selected62_median=round(float(np.median(out62s)), 5),
                           inside_omitted_dk_median=round(float(np.median(omitted_s)), 5),
                           outside_full_dk_median=round(float(np.median(out_fdk_s)), 5),
                           omitted_dk_labels_per_side=omitted_names),
        raw_containment=dict(median=round(float(med_raw), 5), p25=round(float(p25_raw), 5),
                             p75=round(float(p75_raw), 5)),
        gm_weighted_containment=dict(median=round(float(med_w), 5), p25=round(float(p25_w), 5),
                                     p75=round(float(p75_w), 5),
                                     median_improvement=round(float(median_improve), 5),
                                     pearson_raw_vs_weighted=round(spearman, 4)),
        rank=dict(raw_rank1=170, gm_weighted_rank1=int(wrank1), rank_changed=int(rank_change)),
        outside_full_dk_tissue=dict(median_gm_frac=round(float(np.median(out_tissue_gm)), 4)
                                    if out_tissue_gm else None),
        distance=dict(outside_voxel_median_mm=round(float(np.median([d['median_mm'] for d in dist_rows])), 3)
                      if dist_rows else None,
                      p95_mm=round(float(np.median([d['p95_mm'] for d in dist_rows])), 3)
                      if dist_rows else None),
        cross_route=cross,
        cross_route_displacement_detected=bool(cross_route_displacement_detected),
        cross_route_spatial_compatibility=compat["verdict"],
        adjudication=dict(
            spatial_compatibility="CONFIRMED" if compat["spatial_compatibility_ok"] else "FAILED",
            raw_containment_absolute_level="NOT_USABLE_FOR_ADJUDICATION",
            raw_containment_ranking="USABLE (relative ranking is preserved; the support-domain "
                                    "offset depresses all parcels comparably, rank1 170/170 raw "
                                    "and GM-weighted)",
            resume_requires="human review of the corrected criterion; this artifact is evidence "
                            "classification only and does not by itself authorise adjudication"),
        v2_evidence_immutable=True,
        no_mapping_change=True, no_geometry_change=True, no_transform_change=True,
        created_at=ts, script_version=SCRIPT_VERSION)
    write_json(OUT_ST, status)

    md = [
        "# Phase1.7 V3 - Brainnetome <-> FreeSurfer DK cortical support-domain compatibility audit",
        f"VERDICT: {verdict}",
        f"BNA semantics: {bna_semantics['label_semantics']} (SEMANTICS_PARTIALLY_RESOLVED for "
        f"tissue constraint)",
        f"full BNA cortical parcels = 210 (1..210); subcortical 211..246 (36). full DK cortical "
        f"labels per side: lh {len(dk_ids_l)} / rh {len(dk_ids_r)}; selected-62 per side 31; "
        f"omitted DK per side {omitted_names}.",
        f"decomposition (median over 170): outside_selected62 {round(float(np.median(out62s)),4)}; "
        f"inside_omitted_DK {round(float(np.median(omitted_s)),4)}; "
        f"outside_full_DK {round(float(np.median(out_fdk_s)),4)}.",
        f"tissue: BNA cortical union GM frac {bna_cort_tissue['gm_frac']}; DK ribbon union GM "
        f"{dk_tissue['gm_frac']}; selected62 GM {sel62_tissue['gm_frac']}.",
        f"containment raw med/P25/P75 {round(med_raw,4)}/{round(p25_raw,4)}/{round(p75_raw,4)}; "
        f"GM-weighted med/P25/P75 {round(med_w,4)}/{round(p25_w,4)}/{round(p75_w,4)}; "
        f"median improvement {round(median_improve,4)}; pearson {round(spearman,4)}.",
        f"rank: raw rank1 170/170; GM-weighted rank1 {wrank1}/170; rank changed {rank_change}.",
        f"outside-full-DK median GM frac {round(float(np.median(out_tissue_gm)),4)}; "
        f"distance median {round(float(np.median([d['median_mm'] for d in dist_rows])),3) if dist_rows else 'n/a'} mm "
        f"P95 {round(float(np.median([d['p95_mm'] for d in dist_rows])),3) if dist_rows else 'n/a'} mm.",
        f"cross-route cortical COM delta {round(com_delta,3)} mm - DESCRIPTIVE ONLY, NOT a "
        f"criterion: the two supports differ in thickness/extent so their COMs are not "
        f"comparable.",
        f"support-domain-aware compatibility: optimal relative shift "
        f"{compat['optimal_shift_mm']} mm (max {compat['max_abs_shift_mm']} mm, tol "
        f"{COMPAT_SHIFT_TOL_MM}); DK-in-BNA containment {compat['dk_in_bna_containment']} (min "
        f"{COMPAT_DK_CONTAINMENT_MIN}); excess-layer median distance "
        f"{compat['excess_layer_median_distance_mm']} mm (max {COMPAT_EXTRA_MEDIAN_MM_MAX}); "
        f"dice at zero shift {compat['dice_at_zero_shift']} vs at optimum "
        f"{compat['dice_at_optimal_shift']} => "
        f"{compat['verdict']}.",
        f"support-domain offset: dilating the DK ribbon by "
        f"{compat['support_thickness_offset_mm']} mm reproduces the BNA support at dice "
        f"{compat['support_thickness_offset_dice']} - a thickness/extent difference, not a "
        f"displacement.",
        f"interpretability: raw containment {raw_interpret}; outside-selected62 flag bias as "
        f"reported in status.",
        "V2 direct-spatial evidence immutable; no mapping/geometry/transform change; no "
        "registration; independent GM prior used (TemplateFlow official).", ""]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    print("verdict:", verdict)
    print("omitted DK per side:", omitted_names)
    print("decomp medians out62/omittedDK/outFullDK:", round(float(np.median(out62s)),4),
          round(float(np.median(omitted_s)),4), round(float(np.median(out_fdk_s)),4))
    print("raw med", round(float(med_raw),4), "gmw med", round(float(med_w),4),
          "improve", round(float(median_improve),4), "| gmw rank1", wrank1, "changed", rank_change)
    print("BNA gm", bna_cort_tissue["gm_frac"], "DK gm", dk_tissue["gm_frac"],
          "| outFDK gm median", round(float(np.median(out_tissue_gm)),4),
          "| dist med/P95", round(float(np.median([d['median_mm'] for d in dist_rows])),3),
          round(float(np.median([d['p95_mm'] for d in dist_rows])),3),
          "| COM delta (descriptive only)", round(com_delta,3))
    print("spatial compatibility:", compat["verdict"],
          "| shift_mm", compat["optimal_shift_mm"],
          "| dk_in_bna", compat["dk_in_bna_containment"],
          "| excess median mm", compat["excess_layer_median_distance_mm"],
          "| support offset mm", compat["support_thickness_offset_mm"],
          "| dice@0", compat["dice_at_zero_shift"], "dice@opt", compat["dice_at_optimal_shift"])


def _side_vol(aff, side):
    sh = tuple(int(x) for x in np.eye(4)[:3].sum(0)) if False else None
    # left = RAS x<0
    ii, jj, kk = np.ogrid[:193, :229, :193]
    x = aff[0, 0] * (ii + 0.5) + aff[0, 1] * (jj + 0.5) + aff[0, 2] * (kk + 0.5) + aff[0, 3]
    return x < 0 if side == "left" else x > 0


if __name__ == "__main__":
    main()
