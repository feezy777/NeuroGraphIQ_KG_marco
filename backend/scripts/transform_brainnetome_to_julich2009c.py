"""Phase 2E/2F — G4→G3 Standard Nonlinear Transform Toolchain.

Applies the official TemplateFlow nonlinear transform
  MNI152NLin6Asym -> MNI152NLin2009cAsym
to Brainnetome BNA_PM_4D probability components, producing derived assets on
the Julich native grid (MNI152NLin2009cAsym, 193x229x193, 1mm, RAS).

Toolchain: SimpleITK (reads/applies the ITK composite HDF5 transform natively).
Direction: the h5 is used AS-STORED (no GetInverse) — empirically locked by
template-agreement probe (Dice 0.973 vs true 2009c template; see
data/integration/g4_g3_transform_direction_lock.json).
Interpolation: Linear (continuous probability field). Background 0.

Two modes (batch parameters are byte-for-byte the Phase 2E smoke parameters):

  --component <idx>   Phase 2E single-component smoke mode (writes QA asset into
                      transformed_to_julich2009c_smoke/ + QA png/provenance).
  --all               Phase 2F deterministic batch 1..246 (writes normalized
                      0-1 probability assets into
                      transformed_to_julich2009c/{probability_maps,provenance,...},
                      idempotent / resumable / SKIP-on-valid).

Normalization policy (batch): source BNA is 0-100 percent. SimpleITK interpolates
in the original percent space; the FORMAL stored asset is the normalized
probability = transformed_percent / 100 (range 0-1). Raw percent is a
processing intermediate and is NOT persisted per component. Source BNA_PM_4D
and Julich raw maps are NEVER modified. Batch (--all) intentionally does NOT
write a single 4D copy; each component is an independent compressed NIfTI.
Overlap / mapping / DB writes are NOT performed here.

Usage:
    python scripts/transform_brainnetome_to_julich2009c.py --component <index>
    python scripts/transform_brainnetome_to_julich2009c.py --component <index> --dry-run
    python scripts/transform_brainnetome_to_julich2009c.py --all
    python scripts/transform_brainnetome_to_julich2009c.py --all --dry-run
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import nibabel as nib
import numpy as np

try:
    import SimpleITK as sitk
except ImportError:  # pragma: no cover
    sys.exit("SimpleITK required: pip install SimpleITK")

BACKEND = Path(__file__).resolve().parent.parent
BNA_VOL = BACKEND / "data" / "atlases" / "brainnetome" / "bna246" / "volume_raw"
JULICH = BACKEND / "data" / "atlases" / "julich" / "v3.1" / "spatial_raw" / "probability_maps"
TF = BACKEND / "data" / "atlases" / "templateflow_ref"
OUTDIR = BNA_VOL.parent / "transformed_to_julich2009c_smoke"          # Phase 2E smoke dir
BATCH_ROOT = BNA_VOL.parent / "transformed_to_julich2009c"             # Phase 2F batch dir
BATCH_PROB = BATCH_ROOT / "probability_maps"
BATCH_PROV = BATCH_ROOT / "provenance"
BATCH_MAN = BATCH_ROOT / "manifest"
QA_DIR = BACKEND / "data" / "integration" / "qa" / "g4_g3_transform_smoke"
INT = BACKEND / "data" / "integration"

PM4D = BNA_VOL / "BNA_PM_4D.nii.gz"
BN1 = BNA_VOL / "BN_Atlas_246_1mm.nii.gz"
HCP = BNA_VOL / "HCP40_MNI_1.25mm.nii.gz"
XFM = TF / "MNI152NLin2009cAsym_from-MNI152NLin6Asym_mode-image_xfm.h5"
N9 = TF / "tpl-MNI152NLin2009cAsym_res01_desc-brain_T1w.nii.gz"

# Julich native target grid (authority from an actual Julich PM)
JULICH_REF = sorted(JULICH.glob("*.nii.gz"))[0]

TARGET_SHAPE = (193, 229, 193)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _rows(name: str) -> list[dict]:
    return list(csv.DictReader(open(INT / name, encoding="utf-8-sig")))


def _com_world(img: nib.Nifti1Image, data: np.ndarray):
    coords = np.argwhere(data != 0).astype(np.float64)
    vals = data[data != 0]
    vox = coords.T @ vals / vals.sum()
    return nib.affines.apply_affine(img.affine, vox[:3])


def _hemisphere_analysis(data: np.ndarray, img: nib.Nifti1Image, hemisphere: str):
    """Mass-weighted fraction of probability on the expected side (RAS: x<0 left).
    Used for a midline-aware hemisphere check (a near-zero CoM sign flip is only
    counted as a real flip when the majority of the probability mass sits on the
    WRONG side)."""
    nz = data != 0
    if int(nz.sum()) == 0:
        return {"correct_side_mass_fraction": None, "flip": False, "note": "empty"}
    coords = np.argwhere(nz).astype(np.float64)
    vals = data[nz].astype(np.float64)
    wx = nib.affines.apply_affine(img.affine, coords)[:, 0]
    mass_correct = vals[wx < 0].sum() if hemisphere == "left" else vals[wx > 0].sum()
    frac = float(mass_correct / vals.sum())
    flip = bool(frac < 0.5)
    return {"correct_side_mass_fraction": round(frac, 6), "flip": flip}


def select_smoke_component(d4: np.ndarray) -> int:
    """Deterministic selection: first component whose nonzero-voxel count falls
    in the median-based safe band (not degenerate, not extreme)."""
    nnz = np.array([(d4[..., c] != 0).sum() for c in range(d4.shape[-1])], dtype=float)
    lo = np.median(nnz) * 0.3
    hi = np.percentile(nnz, 99)
    for c in range(d4.shape[-1]):  # 0-based here
        if lo < nnz[c] < hi:
            return c + 1  # 1-based component_index
    return int(np.argmax(nnz)) + 1


# ---------------------------------------------------------------------------
# Phase 2F batch helpers
# ---------------------------------------------------------------------------

def load_batch_identity() -> list[dict]:
    """246 rows, ordered by component_index, from the Phase 2D frozen alignment.
    No name matching — component_index == parcel_id == canonical is the frozen link."""
    rows = _rows("g3_brainnetome_probability_to_canonical_alignment.csv")
    by_index = {int(r["component_index"]): r for r in rows}
    ordered = [by_index[i] for i in range(1, 247)]
    assert len(ordered) == 246
    from collections import Counter
    hemi = Counter(r["hemisphere"] for r in ordered)
    assert hemi == {"left": 123, "right": 123}, hemi
    assert all(r["alignment_status"] == "ALIGNED" for r in ordered)
    return ordered


def batch_out_path(row: dict) -> Path:
    idx = int(row["component_index"])
    code = row["official_hemisphere_code"] or row["canonical_name"]
    safe = "".join(ch for ch in code if ch.isalnum() or ch == "_")
    return BATCH_PROB / f"BNA_PM_comp{idx:03d}_{safe}_prob_2009c.nii.gz"


def batch_prov_path(idx: int) -> Path:
    return BATCH_PROV / f"comp{idx:03d}_provenance.json"


def _is_valid_existing(idx: int, row: dict, source_sha: str, xfm_sha: str) -> bool:
    """SKIP rule: normalized output exists AND provenance exists AND every
    recorded sha/metadata is correct. Otherwise the component is reprocessed."""
    out_p = batch_out_path(row)
    prov_p = batch_prov_path(idx)
    if not (out_p.exists() and prov_p.exists()):
        return False
    try:
        prov = json.loads(prov_p.read_text(encoding="utf-8"))
    except Exception:
        return False
    return bool(
        prov.get("component_index") == idx
        and prov.get("status") == "PASS"
        and prov.get("output_sha256") == _sha(out_p)
        and prov.get("source_sha256") == source_sha
        and prov.get("transform_sha256") == xfm_sha
    )


def _batch_process_one(row: dict, arr4: np.ndarray, img4_affine, xfm, ref_sitk,
                       ref_nib, ref_canon, tmp_root: Path) -> dict:
    idx = int(row["component_index"])
    official_code = row["official_hemisphere_code"] or row["canonical_name"]
    hemisphere = row["hemisphere"]
    out_p = batch_out_path(row)
    src32 = arr4[..., idx - 1]  # (145,173,145) float32 view->copy
    src = np.ascontiguousarray(src32, dtype=np.float32)
    sf = src.astype(np.float64)  # stats in float64 (matches Phase 2E smoke)
    nnz_src = int((sf != 0).sum())
    sum_src = float(sf.sum())
    src_img = nib.Nifti1Image(src, img4_affine)
    src_com = _com_world(src_img, sf).tolist() if nnz_src else None

    tmp = tmp_root / f"_src_comp{idx:03d}.nii.gz"
    nib.save(src_img, str(tmp))
    try:
        out = sitk.Resample(sitk.ReadImage(str(tmp)), ref_sitk, xfm,
                            sitk.sitkLinear, 0.0, sitk.sitkFloat32)
        norm_sitk = sitk.Multiply(out, 0.01)  # percent -> probability (0..1)
        sitk.WriteImage(norm_sitk, str(out_p))
    finally:
        if tmp.exists():
            tmp.unlink()

    # read back + verify (independent geometry/numeric QA)
    out_img = nib.load(str(out_p))
    nd = out_img.get_fdata()
    nnz_t = int((nd != 0).sum())
    nmin, nmax = float(nd.min()), float(nd.max())
    nan_c = int(np.isnan(nd).sum())
    inf_c = int(np.isinf(nd).sum())
    t_com = _com_world(out_img, nd).tolist() if nnz_t else None
    shape_ok = nd.shape == TARGET_SHAPE
    affine_ok = np.allclose(out_img.affine, ref_canon.affine, atol=1e-3)
    orient_ok = tuple(nib.aff2axcodes(out_img.affine)) == ("R", "A", "S")
    hemi = _hemisphere_analysis(nd, out_img, hemisphere)
    checks = {
        "TARGET_GRID_MATCH": bool(shape_ok and affine_ok and orient_ok),
        "NaN_Inf_absent": bool(nan_c == 0 and inf_c == 0),
        "range_0_1": bool(nmin >= -1e-4 and nmax <= 1.000001),
        "nonempty": bool(nnz_t > 0),
        "no_hemisphere_flip": bool(not hemi["flip"]),
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    prov = {
        "status": status,
        "component_index": idx,
        "parcel_id": int(row["parcel_id"]),
        "lut_name": row["lut_name"],
        "official_code": official_code,
        "hemisphere": hemisphere,
        "canonical_g3_id": row["canonical_g3_id"],
        "canonical_name": row["canonical_name"],
        "source_asset": "BNA_PM_4D.nii.gz",
        "source_asset_path": "data/atlases/brainnetome/bna246/volume_raw/BNA_PM_4D.nii.gz",
        "source_sha256": _sha(PM4D),
        "source_space": "MNI152NLin6Asym (HCP40 1.25mm grid)",
        "source_scale": "percent_0_100",
        "output_asset": str(out_p.relative_to(BACKEND)).replace("\\", "/"),
        "output_sha256": _sha(out_p),
        "target_space": "MNI152NLin2009cAsym 1mm",
        "target_shape": list(TARGET_SHAPE),
        "output_scale": "normalized_0_1",
        "normalization": "divide_by_100_after_transform",
        "transform_file": str(XFM.relative_to(BACKEND)).replace("\\", "/"),
        "transform_sha256": _sha(XFM),
        "transform_direction": "as_stored (no GetInverse)",
        "transform_provider": "TemplateFlow",
        "tool": "SimpleITK",
        "tool_version": sitk.Version_VersionString(),
        "interpolation": "Linear",
        "background": 0.0,
        "target_reference": str(JULICH_REF.relative_to(BACKEND)).replace("\\", "/"),
        "target_reference_sha256": _sha(JULICH_REF),
        "source_nonzero_voxels": nnz_src,
        "target_nonzero_voxels": nnz_t,
        "source_probability_sum": round(sum_src, 4),
        "target_probability_sum": round(float(nd.sum()), 4),
        "probability_sum_ratio": round(float(nd.sum()) / sum_src, 6) if sum_src else None,
        "support_volume_ratio": round(nnz_t / nnz_src, 6) if nnz_src else None,
        "source_weighted_com_mm": [round(x, 3) for x in src_com] if src_com else None,
        "target_weighted_com_mm": [round(x, 3) for x in t_com] if t_com else None,
        "normalized_min": nmin,
        "normalized_max": nmax,
        "hemisphere_correct_side_mass_fraction": hemi["correct_side_mass_fraction"],
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return prov


def run_batch(dry_run: bool = False) -> int:
    from collections import Counter
    BATCH_PROB.mkdir(parents=True, exist_ok=True)
    BATCH_PROV.mkdir(parents=True, exist_ok=True)
    BATCH_MAN.mkdir(parents=True, exist_ok=True)

    identity = load_batch_identity()
    source_sha = _sha(PM4D)
    xfm_sha = _sha(XFM)

    to_skip: list[int] = []
    to_process: list[dict] = []
    for row in identity:
        idx = int(row["component_index"])
        if _is_valid_existing(idx, row, source_sha, xfm_sha):
            to_skip.append(idx)
        else:
            to_process.append(row)

    print(f"[batch] total=246 pending={len(to_process)} valid_skip={len(to_skip)}")

    if dry_run:
        nums = [int(r["component_index"]) for r in to_process]
        print("[dry-run] pending component count:", len(nums))
        print("[dry-run] would transform components (first 12):", nums[:12], "...")
        return 0

    processed: list[int] = []
    failed: list[int] = []
    ref_nib = nib.load(str(JULICH_REF))
    ref_canon = nib.as_closest_canonical(ref_nib)
    ref_sitk = sitk.ReadImage(str(JULICH_REF))
    xfm = sitk.ReadTransform(str(XFM))

    tmp_root = Path(tempfile.mkdtemp(prefix="bna_xfm_", dir=str(BATCH_ROOT)))
    try:
        if to_process:
            arr4 = np.asarray(nib.load(str(PM4D)).dataobj)  # float32, once
            img4_affine = nib.load(str(PM4D)).affine
            for row in to_process:
                idx = int(row["component_index"])
                try:
                    prov = _batch_process_one(row, arr4, img4_affine, xfm, ref_sitk,
                                              ref_nib, ref_canon, tmp_root)
                    batch_prov_path(idx).write_text(
                        json.dumps(prov, ensure_ascii=False, indent=1), encoding="utf-8")
                    if prov["status"] == "PASS":
                        processed.append(idx)
                        print(f"  processed comp {idx:03d} PASS", flush=True)
                    else:
                        failed.append(idx)
                        print(f"  processed comp {idx:03d} FAIL {prov['checks']}", flush=True)
                except Exception as exc:  # isolation: one failure never kills the batch
                    failed.append(idx)
                    print(f"  ERROR comp {idx:03d}: {type(exc).__name__}: {exc}", flush=True)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    counts = {
        "total": 246,
        "processed": len(processed),
        "skipped": len(to_skip),
        "failed": len(failed),
        "failed_components": failed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    (BATCH_MAN / "batch_run_record.json").write_text(
        json.dumps(counts, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[batch] processed={len(processed)} skipped={len(to_skip)} failed={len(failed)}")
    if failed:
        print("[batch] FAILED components:", failed)
        return 2
    if processed:
        print("[batch] ALL_PASS")
    return 0


# ---------------------------------------------------------------------------
# Phase 2E single-component smoke mode (unchanged semantics)
# ---------------------------------------------------------------------------

def run_smoke(comp_arg, dry_run: bool) -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    QA_DIR.mkdir(parents=True, exist_ok=True)

    img4 = nib.load(str(PM4D))
    d4 = img4.get_fdata()
    comp = select_smoke_component(d4) if comp_arg is None else int(comp_arg)
    assert 1 <= comp <= 246, "component index must be 1..246"
    src = d4[..., comp - 1].astype(np.float64)

    align = next((r for r in _rows("g3_brainnetome_probability_to_canonical_alignment.csv")
                  if int(r["component_index"]) == comp), {})
    nnz = int((src != 0).sum())
    if nnz == 0:
        print(f"FAIL: component {comp} is empty")
        return 3

    # ---- physical-space lattice report (1mm BN_Atlas vs 1.25mm PM grid) ----
    bn1 = nib.load(str(BN1))
    hcp = nib.load(str(HCP))
    lattice = {
        "bn_atlas_246_1mm": {"shape": list(bn1.shape), "origin_world_mm": [round(float(x), 3) for x in
                            nib.affines.apply_affine(bn1.affine, np.array([0, 0, 0]))]},
        "bna_pm_4d_grid": {"shape": list(img4.shape[:3]), "origin_world_mm": [round(float(x), 3) for x in
                           nib.affines.apply_affine(img4.affine, np.array([0, 0, 0]))]},
        "hcp40_1_25mm": {"shape": list(hcp.shape), "origin_world_mm": [round(float(x), 3) for x in
                        nib.affines.apply_affine(hcp.affine, np.array([0, 0, 0]))]},
    }
    src_stats = {
        "component_index": comp, "min": float(src.min()), "max": float(src.max()),
        "sum": float(src.sum()), "nonzero_voxels": nnz,
        "center_of_mass_world_mm": [round(float(x), 2) for x in _com_world(img4, src)],
    }
    print("selected component:", comp)
    print("identity row:", align)
    print("source stats:", src_stats)
    print("physical lattice report:", json.dumps(lattice, ensure_ascii=False))

    ref_img = nib.load(str(JULICH_REF))
    print("Julich target reference:", JULICH_REF.name,
          "shape:", ref_img.shape,
          "orient:", nib.aff2axcodes(ref_img.affine))
    if dry_run:
        print("[dry-run] component", comp, "->", "would apply as-stored composite onto Julich 2009c grid")
        return 0

    # ---- apply transform (as-stored, locked direction) ----
    tmp = OUTDIR / f"_tmp_source_comp{comp:03d}.nii.gz"
    nib.save(nib.Nifti1Image(src, img4.affine), str(tmp))
    try:
        xfm = sitk.ReadTransform(str(XFM))
        ref_sitk = sitk.ReadImage(str(JULICH_REF))
        out = sitk.Resample(sitk.ReadImage(str(tmp)), ref_sitk, xfm,
                            sitk.sitkLinear, 0.0, sitk.sitkFloat64)
        out_path = OUTDIR / f"BNA_PM4D_comp{comp:03d}_NLin6to2009c_raw_percent.nii.gz"
        sitk.WriteImage(out, str(out_path))
    finally:
        if tmp.exists():
            tmp.unlink()

    # ---- verify ----
    out_img = nib.load(str(out_path))
    tout = out_img.get_fdata()
    tmin, tmax = float(tout.min()), float(tout.max())
    tnan, tinf = int(np.isnan(tout).sum()), int(np.isinf(tout).sum())
    ref_canon = nib.as_closest_canonical(ref_img)
    t_com = None
    if (tout != 0).sum() > 0:
        t_com = _com_world(out_img, tout)
    raw_stats = {
        "min": tmin, "max": tmax, "sum": float(tout.sum()),
        "nonzero_voxels": int((tout != 0).sum()), "nan": tnan, "inf": tinf,
        "center_of_mass_world_mm": [round(float(x), 2) for x in t_com] if t_com is not None else None,
    }
    norm = tout / 100.0
    norm_path = OUTDIR / f"BNA_PM4D_comp{comp:03d}_NLin6to2009c_probability.nii.gz"
    nib.save(nib.Nifti1Image(norm, out_img.affine), str(norm_path))
    nmin, nmax = float(norm.min()), float(norm.max())
    print("transformed raw stats:", raw_stats)
    print("normalized range:", nmin, nmax)

    # ---- checks ----
    shape_ok = tout.shape == TARGET_SHAPE
    affine_ok = np.allclose(out_img.affine, ref_canon.affine, atol=1e-3)
    orient_ok = tuple(nib.aff2axcodes(out_img.affine)) == ("R", "A", "S")
    naninf_ok = (tnan == 0 and tinf == 0)
    raw_range_ok = (tmin >= -0.001) and (tmax <= 100.001)
    norm_range_ok = (nmin >= -1e-6) and (nmax <= 1.000001)
    hemi = align.get("hemisphere", "")
    flip = bool(hemi and t_com is not None and
                ((hemi == "left" and t_com[0] > 0) or (hemi == "right" and t_com[0] < 0)))
    # centroid still inside 2009c brain?
    n9_img = nib.load(str(N9))
    n9d = n9_img.get_fdata()
    brain_ok = False
    if t_com is not None:
        ij = np.round(nib.affines.apply_affine(np.linalg.inv(n9_img.affine), t_com)[:3]).astype(int)
        if all(0 <= ij[k] < n9d.shape[k] for k in range(3)):
            brain_ok = bool(n9d[ij[0], ij[1], ij[2]] > n9d.max() * 0.1)
    checks = {
        "TARGET_GRID_MATCH": bool(shape_ok and affine_ok and orient_ok),
        "NaN_Inf_absent": bool(naninf_ok),
        "raw_percent_range_0_100": bool(raw_range_ok),
        "normalized_range_0_1": bool(norm_range_ok),
        "no_hemisphere_flip": bool(not flip),
        "centroid_within_2009c_brain": bool(brain_ok),
    }
    for k, v in checks.items():
        print(f"  {k}: {v}")

    # ---- QA slices ----
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        src_c = nib.as_closest_canonical(nib.Nifti1Image(src, img4.affine)).get_fdata()
        tc = nib.as_closest_canonical(out_img).get_fdata()
        shp = TARGET_SHAPE
        slices = [shp[0] // 2, shp[1] // 2, shp[2] // 2]
        axes_names = ["sagittal", "coronal", "axial"]
        fig, axes = plt.subplots(2, 3, figsize=(15, 9))
        for j, (sl) in enumerate(slices):
            axes[0, j].imshow(np.rot90(src_c[sl, :, :] if j == 0 else (src_c[:, sl, :] if j == 1 else src_c[:, :, sl])), cmap="hot")
            axes[0, j].set_title(f"source (NLin6) {axes_names[j]}")
            axes[1, j].imshow(np.rot90(tc[sl, :, :] if j == 0 else (tc[:, sl, :] if j == 1 else tc[:, :, sl])), cmap="hot")
            axes[1, j].set_title(f"transformed (2009c) {axes_names[j]}")
        fig.suptitle(f"BNA_PM_4D component {comp} ({align.get('canonical_name','')}) NLin6->2009c smoke")
        fig.tight_layout()
        qa_png = QA_DIR / f"smoke_comp{comp:03d}_slices.png"
        fig.savefig(qa_png, dpi=110)
        plt.close(fig)
        print("QA image:", qa_png)
    except Exception as e:  # pragma: no cover
        print("QA image skipped:", type(e).__name__, str(e)[:100])

    # ---- provenance ----
    ok = all(checks.values())
    prov = {
        "status": "PASS" if ok else "FAIL",
        "component_index": comp,
        "canonical_g3_id": align.get("canonical_g3_id"),
        "canonical_name": align.get("canonical_name"),
        "lut_name": align.get("lut_name"),
        "official_hemisphere_code": align.get("official_hemisphere_code"),
        "hemisphere": align.get("hemisphere"),
        "source_asset": str(PM4D), "source_sha256": _sha(PM4D),
        "source_space": "MNI152NLin6Asym (HCP40 1.25mm grid, physical space shared with BN_Atlas_246_1mm)",
        "source_scale": "0-100 percent (NOT normalized; overlap later divides by 100)",
        "target_space": "MNI152NLin2009cAsym 1mm",
        "transform_file": str(XFM), "transform_sha256": _sha(XFM),
        "transform_direction": "as_stored (no GetInverse) — locked by template-agreement probe Dice 0.973",
        "transform_provider": "TemplateFlow",
        "tool": "SimpleITK", "tool_version": sitk.Version_VersionString(),
        "interpolation": "Linear", "background": 0.0,
        "target_reference": str(JULICH_REF), "target_reference_sha256": _sha(JULICH_REF),
        "physical_lattice_report": lattice,
        "source_stats": src_stats, "transformed_raw_stats": raw_stats,
        "normalized_derivative": str(norm_path),
        "normalized_min": nmin, "normalized_max": nmax,
        "checks": checks,
        "output_raw": str(out_path),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    (QA_DIR / f"smoke_comp{comp:03d}_provenance.json").write_text(
        json.dumps(prov, ensure_ascii=False, indent=1), encoding="utf-8")
    print("SMOKE RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 3


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--component", type=int, default=None,
                        help="BNA_PM_4D component index (1..246) for single smoke mode.")
    parser.add_argument("--all", dest="batch", action="store_true",
                        help="Phase 2F deterministic batch: components 1..246 (idempotent/resumable).")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.batch and args.component is not None:
        print("error: --all and --component are mutually exclusive")
        return 2
    if args.batch:
        return run_batch(dry_run=args.dry_run)
    return run_smoke(args.component, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
