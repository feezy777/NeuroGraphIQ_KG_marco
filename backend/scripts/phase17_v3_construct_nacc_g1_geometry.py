"""Phase1.7 V3 - CIT168 Nucleus Accumbens G1 Reference Geometry Construction v1.

First formal G1 *derived* geometry construction. From the frozen CIT168
authoritative probability atlas (MNI152NLin2009cAsym, 193x229x193, 1mm), extract
the NAC probability channel and split it into Left/Right Nucleus Accumbens G1
probability geometry using world-coordinate X (affine-based), preserving the
full probability field on the original grid.

- NO registration, NO resampling, NO threshold, NO binarize.
- NO G4->G1 overlap, NO reclassification, NO DB write, NO commit.
- Det atlas is used for QC/cross-check only (never the geometry source).

Output geometry class: AUTHORITATIVE_DERIVED_G1_GEOMETRY
Derivation:        PROBABILITY_CHANNEL_EXTRACTION_AND_HEMISPHERE_SPLIT

Canonical targets (verified from frozen G3->G1 manifest / Macro96):
  Left Nucleus Accumbens   = NGIQ-BR-00000254
  Right Nucleus Accumbens  = NGIQ-BR-00000262
"""
from __future__ import annotations

import csv
import datetime as _dt
import hashlib
import json
from pathlib import Path

import nibabel as nib
import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
RAW = BACKEND / "data" / "atlases" / "external_raw" / "cit168"
OUTDIR = BACKEND / "data" / "atlases" / "derived_g1" / "cit168_nacc"
LEFT_D = OUTDIR / "left"
RIGHT_D = OUTDIR / "right"
OUTJSON = D16 / "phase17_v3_nacc_g1_geometry_manifest.json"
OUTCSV = D16 / "phase17_v3_nacc_g1_geometry_qc.csv"
OUTMD = D16 / "phase17_v3_nacc_g1_geometry_diagnostics.md"

SRC_PROB = RAW / "CIT168toMNI152-2009c_prob.nii.gz"     # primary geometry source
SRC_DET = RAW / "CIT168toMNI152-2009c_det.nii.gz"        # QC-only
SRC_LUT = RAW / "labels.txt"
JULICH_REF = (BACKEND / "data" / "atlases" / "julich" / "v3.1" / "spatial_raw"
              / "probability_maps" / "AREA_44_IFG_LEFT.nii.gz")

CANON = {
    "LEFT": dict(g1_region_id="NGIQ-BR-00000254",
                 canonical_name="Left Nucleus Accumbens", hemisphere="left"),
    "RIGHT": dict(g1_region_id="NGIQ-BR-00000262",
                  canonical_name="Right Nucleus Accumbens", hemisphere="right"),
}

SCRIPT_VERSION = "phase17_v3_construct_nacc_g1_geometry.py v1"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def load_lut() -> dict:
    lut = {}
    for line in SRC_LUT.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split()
        if len(parts) == 2 and parts[0].isdigit():
            lut[int(parts[0])] = parts[1]
    return lut


def pick_nac_channel(prob_img) -> tuple[int, float]:
    """NAC channel must be confirmed from LUT + dimension, not hardcoded."""
    d = prob_img.get_fdata()
    nvol = d.shape[3] if d.ndim == 4 else 1
    lut = load_lut()
    # LUT keys are 0-based CIT168 channels; map by name
    hits = [k for k, v in lut.items() if v.strip().upper() in ("NAC", "NUCLEUS ACCUMBENS", "ACB")]
    if len(hits) != 1:
        raise SystemExit(f"FAIL: LUT NAC ambiguity: {hits}")
    ch = hits[0]
    if ch >= nvol:
        raise SystemExit(f"FAIL: NAC channel {ch} >= prob volumes {nvol}")
    # cross-check support magnitude is accumbens-plausible
    mass = float(d[..., ch].sum())
    if not (200.0 < mass < 5000.0):
        raise SystemExit(f"FAIL: NAC channel mass {mass:.1f} implausible")
    return ch, mass


def world_x_for_mask(affine: np.ndarray, shape: tuple, flat_pos: np.ndarray) -> np.ndarray:
    """World X for a set of flat (C-order) voxel positions (N,)."""
    ijk = np.column_stack(np.unravel_index(flat_pos, shape)).astype(np.float64)
    xyz = nib.affines.apply_affine(affine, ijk)
    return xyz[:, 0]


def qc_stats(vals3d: np.ndarray, affine: np.ndarray,
             mask: np.ndarray | None = None) -> dict:
    """voxel-set QC over a 3-D array (prob field, values used as weights)."""
    v = vals3d.astype(np.float64)
    if mask is None:
        mask = v > 0
    nz = int(mask.sum())
    if nz == 0:
        return dict(nonzero=0, mass=0.0, weighted_volume_mm3=0.0, centroid=[None]*3,
                    bbox=[None]*6, min=0.0, max=0.0)
    w = v[mask]
    ijk = np.argwhere(mask).astype(np.float64)  # N x3 (i,j,k)
    xyz = nib.affines.apply_affine(affine, ijk)
    mass = float(w.sum())
    voxvol = float(abs(np.linalg.det(affine[:3, :3])))
    cx = float((xyz[:, 0] * w).sum() / mass)
    cy = float((xyz[:, 1] * w).sum() / mass)
    cz = float((xyz[:, 2] * w).sum() / mass)
    bbox = [float(xyz[:, 0].min()), float(xyz[:, 0].max()),
            float(xyz[:, 1].min()), float(xyz[:, 1].max()),
            float(xyz[:, 2].min()), float(xyz[:, 2].max())]
    return dict(nonzero=nz, mass=mass, weighted_volume_mm3=mass * voxvol,
                centroid=[cx, cy, cz], bbox=bbox,
                min=float(w.min()), max=float(w.max()))


def _prior_source_sha():
    """Return the frozen source_sha256 from an existing manifest, if present."""
    if not OUTJSON.exists():
        return None
    try:
        return json.loads(OUTJSON.read_text(encoding="utf-8")).get("source", {}).get("sha256")
    except Exception:
        return None


def main() -> None:
    # ---- inputs exist & source bytes frozen ----
    for p in (SRC_PROB, SRC_DET, SRC_LUT, JULICH_REF):
        if not p.exists():
            raise SystemExit(f"FAIL: missing input {p}")
    src_sha = sha256(SRC_PROB)
    det_sha = sha256(SRC_DET)
    # freeze guard: derived geometry must not be regenerated from different source bytes
    prior_sha = _prior_source_sha()
    if prior_sha is not None and prior_sha != src_sha:
        raise SystemExit(f"FAIL: CIT168 source sha changed ({prior_sha[:12]} -> {src_sha[:12]}); "
                         f"refusing to overwrite previously frozen derived geometry")

    prob_img = nib.load(SRC_PROB)
    det_img = nib.load(SRC_DET)
    ch, chmass = pick_nac_channel(prob_img)
    prob4 = prob_img.get_fdata()
    nac = prob4[..., ch].astype(np.float64)          # full bilateral NAC probability
    det = det_img.get_fdata()

    aff = prob_img.affine
    shape = nac.shape
    voxvol = float(abs(np.linalg.det(aff[:3, :3])))   # == 1.0 (1mm isotropic)
    if tuple(shape) != (193, 229, 193):
        raise SystemExit(f"FAIL: unexpected source shape {shape}")

    # ---- hemisphere split by WORLD X (affine-based) ----
    # convention verified: RAS, LEFT = x<0, RIGHT = x>0 (matches Julich LEFT centroid x<0)
    flat = nac.ravel()
    pos = np.flatnonzero(flat > 0)
    xw = world_x_for_mask(aff, shape, pos)
    left = np.zeros_like(flat); right = np.zeros_like(flat)
    lm = xw < 0.0
    rm = xw > 0.0
    mm = xw == 0.0
    left[pos[lm]] = flat[pos[lm]]
    right[pos[rm]] = flat[pos[rm]]
    midpos = pos[mm]
    left_img = left.reshape(shape)
    right_img = right.reshape(shape)

    # ---- QC + all abort-capable gates (before any write) ----
    stat_bil = qc_stats(nac, aff)
    stat_L = qc_stats(left_img, aff)
    stat_R = qc_stats(right_img, aff)
    midvals = np.zeros(shape, dtype=np.float64)
    midvals.ravel()[midpos] = flat[midpos]
    stat_M = qc_stats(midvals, aff)
    mass_L, mass_R, mass_M = stat_L["mass"], stat_R["mass"], stat_M["mass"]
    loss = stat_bil["mass"] - (mass_L + mass_R + mass_M)
    if abs(loss) / stat_bil["mass"] > 1e-6:
        raise SystemExit(f"FAIL: probability loss {loss:.4f} > tol")
    if stat_M["nonzero"] > 0:
        raise SystemExit("FAIL/QC_REVIEW: midline NAC probability mass present")
    # laterality gate (RAS): left centroid must be x<0, right x>0
    if not (stat_L["centroid"][0] < -1.0 and stat_R["centroid"][0] > 1.0):
        raise SystemExit("FAIL: laterality sanity (L x<0, R x>0) not satisfied; "
                         "aborting before write")

    # ---- deterministic QC (cross-check only); det==3 is the NAC label (LUT idx 2 + 1) ----
    det_nac = (det == 3)
    det_in_prob = int(((det == 3) & (nac > 0)).sum())
    det_total = int((det == 3).sum())
    if det_total == 0 or det_in_prob != det_total:
        raise SystemExit(f"FAIL: det==3 ({det_total}) not fully inside NAC prob support "
                         f"(inside {det_in_prob}); deterministic QC gate failed")
    stat_detL = qc_stats(det_nac.astype(np.float64) * (left_img > 0), aff)
    stat_detR = qc_stats(det_nac.astype(np.float64) * (right_img > 0), aff)
    stat_det = qc_stats(det_nac.astype(np.float64), aff)

    # ---- Julich grid invariant (before any write) ----
    jref = nib.load(JULICH_REF)
    g = lambda a, b: all(abs(float(x) - float(y)) < 1e-3
                         for x, y in zip(np.asarray(a).ravel(), np.asarray(b).ravel()))
    grid_ok = (tuple(prob_img.shape[:3]) == tuple(jref.shape[:3])
               and g(prob_img.affine, jref.affine))
    if not grid_ok:
        raise SystemExit("FAIL: derived grid no longer EXACT_GRID_MATCH vs Julich")
    grid_rel = "EXACT_GRID_MATCH"

    # ---- write derived geometry (same grid/affine/orientation) ----
    LEFT_D.mkdir(parents=True, exist_ok=True)
    RIGHT_D.mkdir(parents=True, exist_ok=True)
    lpath = LEFT_D / "left_nucleus_accumbens_prob.nii.gz"
    rpath = RIGHT_D / "right_nucleus_accumbens_prob.nii.gz"
    li = nib.Nifti1Image(left_img, aff)
    ri = nib.Nifti1Image(right_img, aff)
    # preserve orientation/zoom header codes from source
    for tgt in (li, ri):
        tgt.header.set_zooms([1.0, 1.0, 1.0])
        tgt.header.set_qform(aff, code=int(prob_img.header["qform_code"]))
        tgt.header.set_sform(aff, code=int(prob_img.header["sform_code"]))
    nib.save(li, lpath)
    nib.save(ri, rpath)
    out_sha_L = sha256(lpath)
    out_sha_R = sha256(rpath)

    ts = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")

    def make_geom(hemi, img_path, img, stat, out_sha):
        c = CANON[hemi]
        return dict(
            geometry_id=f"CIT168_NAC_{hemi}_G1_PROB_v1",
            g1_region_id=c["g1_region_id"], canonical_name=c["canonical_name"],
            hemisphere=c["hemisphere"],
            source_asset_id="CIT168_NAcc",
            source_atlas="CIT168 (Pauli, Nili & Tyszka 2018, Sci Data 5:180063)",
            source_version="CIT168_Reinf_Learn_v1.1.0",
            source_filename=SRC_PROB.name,
            source_sha256=src_sha,
            source_label="NAC / Nucleus Accumbens",
            source_channel=ch,
            geometry_class="AUTHORITATIVE_DERIVED_G1_GEOMETRY",
            derivation_method="PROBABILITY_CHANNEL_EXTRACTION_AND_HEMISPHERE_SPLIT",
            independent_from_g3_g1_mapping="TRUE",
            circularity_risk="NONE",
            coordinate_space="MNI152NLin2009cAsym",
            shape=list(img.shape), spacing=[1.0, 1.0, 1.0],
            affine=[float(x) for x in aff.ravel()],
            orientation="RAS",
            registration_applied="FALSE", resampling_applied="FALSE",
            threshold_applied="FALSE", binarization_applied="FALSE",
            hemisphere_split_rule="world X < 0 => LEFT; world X > 0 => RIGHT (affine-based, RAS)",
            midline_rule="x==0 midline; must be empty for NAcc (FAIL if mass present)",
            qc=stat,
            output_path=str(img_path.relative_to(BACKEND)),
            output_sha256=out_sha,
            construction_script_version=SCRIPT_VERSION,
            construction_timestamp=ts,
        )

    geom_L = make_geom("LEFT", lpath, left_img, stat_L, out_sha_L)
    geom_R = make_geom("RIGHT", rpath, right_img, stat_R, out_sha_R)

    manifest = dict(
        scope="Nucleus Accumbens only (no Thalamus/Hippocampus/Amygdala/BF/BST/cortical)",
        source=dict(asset_id="CIT168_NAcc", file=SRC_PROB.name, sha256=src_sha,
                    det_sha256=det_sha, det_role="QC_ONLY",
                    label="NAC / Nucleus Accumbens", channel=ch,
                    channel_confirmed_via="CIT168 labels.txt LUT name match + 4D stack dimension",
                    det_qc=dict(nac_det_label=3, det_total_voxels=det_total,
                                det_inside_nac_prob_support=det_in_prob,
                                fully_contained=(det_in_prob == det_total))),
        canonical=dict(Left=CANON["LEFT"], Right=CANON["RIGHT"]),
        coordinate_space="MNI152NLin2009cAsym",
        geometry_class="AUTHORITATIVE_DERIVED_G1_GEOMETRY",
        derivation_method="PROBABILITY_CHANNEL_EXTRACTION_AND_HEMISPHERE_SPLIT",
        grid_relation_to_julich=grid_rel,
        bilateral=stat_bil,
        left=geom_L, right=geom_R,
        midline=stat_M,
        mass_conservation=dict(left=mass_L, right=mass_R, midline=mass_M,
                               bilateral=stat_bil["mass"],
                               loss=loss,
                               conserved=abs(loss) / stat_bil["mass"] <= 1e-6),
        qc_det=dict(nac_det_label=3,
                    det_left=stat_detL, det_right=stat_detR, det_bilateral=stat_det),
        construction_script_version=SCRIPT_VERSION,
        construction_timestamp=ts,
        note="no registration/resampling/threshold/binarize; grid preserved; "
             "det only QC; no direct overlap computed this round",
    )
    with open(OUTJSON, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    # ---- QC csv ----
    def qc_row(geometry, g1_region_id, canonical_name, st, out_sha):
        return dict(geometry=geometry, g1_region_id=g1_region_id,
                    canonical_name=canonical_name,
                    probability_min=st["min"], probability_max=st["max"],
                    nonzero_voxels=st["nonzero"], probability_mass=st["mass"],
                    weighted_volume_mm3=st["weighted_volume_mm3"],
                    centroid_x=st["centroid"][0], centroid_y=st["centroid"][1],
                    centroid_z=st["centroid"][2],
                    bbox=st["bbox"], output_sha256=out_sha)
    qc_rows = [qc_row("BILATERAL_SOURCE", "", "Nucleus Accumbens (bilateral CIT168 ch2)",
                      stat_bil, src_sha)]
    for hemi in ("LEFT", "RIGHT"):
        gd = manifest[hemi.lower()]
        qc_rows.append(qc_row(hemi, gd["g1_region_id"], gd["canonical_name"],
                              gd["qc"], gd["output_sha256"]))
    # det QC rows
    qc_rows.append(qc_row("DET_NAC_bilateral", "", "det QC only", stat_det, det_sha))
    with open(OUTCSV, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(qc_rows[0].keys()))
        w.writeheader()
        for r in qc_rows:
            w.writerow(r)

    md = ["# Phase1.7 V3 - CIT168 Nucleus Accumbens G1 geometry construction v1", "",
          f"source: {SRC_PROB.name} sha256={src_sha}",
          f"source channel = {ch} (NAC) confirmed via LUT/labels + dims + det cross-check",
          f"bilateral mass={stat_bil['mass']:.3f} mm3  L={mass_L:.3f}  R={mass_R:.3f}  midline={mass_M:.3f}",
          f"mass conservation loss={loss:.6f} ({'OK' if abs(loss)/stat_bil['mass']<=1e-6 else 'FAIL'})",
          f"grid vs Julich = {grid_rel} (no resample/registration)",
          f"outputs: {lpath.relative_to(BACKEND)} sha={out_sha_L}",
          f"         {rpath.relative_to(BACKEND)} sha={out_sha_R}",
          f"no threshold/binarize; probability preserved; det used for QC only",
          "no direct overlap / no reclass / no DB / no commit this round"]
    with open(OUTMD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    print(f"channel {ch} NAC mass bilateral {stat_bil['mass']:.3f}")
    print(f"L {mass_L:.3f} R {mass_R:.3f} M {mass_M:.3f} loss {loss:.6f} grid {grid_rel}")
    print("outputs", lpath, rpath)


if __name__ == "__main__":
    main()
