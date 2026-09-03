"""Phase 2F — read-only QA + manifest + summary for the G3 (Brainnetome) → G4-grid
batch transform.

Loads every component output NIfTI in transformed_to_julich2009c/probability_maps
and INDEPENDENTLY re-verifies geometry / numerics / hemisphere / support + sum
ratios / boundary contact, cross-checks each against the transform-time per-
component provenance, then writes:

  backend/data/integration/g3_brainnetome_to_julich_batch_transform_manifest.csv
  backend/data/integration/g4_g3_batch_transform_validation.json

It also re-confirms (read-only) that all 414 Julich v3.1 probability maps share
the identical 2009c target grid, and renders 6 deterministic representative
source/transformed QA images (2L + 2R + 1 near-midline + 1 subcortical).

No DB writes. No overlap. No mapping. Raw assets untouched.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import nibabel as nib
import numpy as np

BACKEND = Path(__file__).resolve().parent.parent
INT = BACKEND / "data" / "integration"
BATCH = BACKEND / "data" / "atlases" / "brainnetome" / "bna246" / "transformed_to_julich2009c"
PROB = BATCH / "probability_maps"
PROV = BATCH / "provenance"
QA_DIR = INT / "qa" / "g4_g3_batch_transform"
JULICH = BACKEND / "data" / "atlases" / "julich" / "v3.1" / "spatial_raw" / "probability_maps"
BNA_VOL = BACKEND / "data" / "atlases" / "brainnetome" / "bna246" / "volume_raw"
TF = BACKEND / "data" / "atlases" / "templateflow_ref"

PM4D = BNA_VOL / "BNA_PM_4D.nii.gz"
XFM = TF / "MNI152NLin2009cAsym_from-MNI152NLin6Asym_mode-image_xfm.h5"
JULICH_REF = sorted(JULICH.glob("*.nii.gz"))[0]
SHAPE = (193, 229, 193)

MANIFEST = INT / "g3_brainnetome_to_julich_batch_transform_manifest.csv"
SUMMARY = INT / "g4_g3_batch_transform_validation.json"


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _rows(name):
    return list(csv.DictReader(open(INT / name, encoding="utf-8-sig")))


def _percentiles(xs):
    a = np.array([float(x) for x in xs])
    return {
        "median": round(float(np.median(a)), 4),
        "p5": round(float(np.percentile(a, 5)), 4),
        "p95": round(float(np.percentile(a, 95)), 4),
        "min": round(float(a.min()), 4),
        "max": round(float(a.max()), 4),
    }


def _hemi_flip(nd, affine, hemisphere):
    nz = nd != 0
    if int(nz.sum()) == 0:
        return {"correct_side_mass_fraction": None, "flip": True, "empty": True}
    coords = np.argwhere(nz).astype(np.float64)
    vals = nd[nz].astype(np.float64)
    wx = nib.affines.apply_affine(affine, coords)[:, 0]
    frac = (vals[wx < 0].sum() / vals.sum()) if hemisphere == "left" \
        else (vals[wx > 0].sum() / vals.sum())
    return {"correct_side_mass_fraction": round(float(frac), 6), "flip": bool(frac < 0.5)}


def _com(nd, affine):
    nz = nd != 0
    if int(nz.sum()) == 0:
        return None
    coords = np.argwhere(nz).astype(np.float64)
    vals = nd[nz].astype(np.float64)
    return [round(float(x), 3) for x in nib.affines.apply_affine(affine, coords.T @ vals / vals.sum())]


def verify_component(idx, row, ref_affine):
    code = row["official_code"]
    safe = "".join(ch for ch in code if ch.isalnum() or ch == "_")
    out_p = PROB / f"BNA_PM_comp{idx:03d}_{safe}_prob_2009c.nii.gz"
    prov_p = PROV / f"comp{idx:03d}_provenance.json"
    assert out_p.exists(), out_p
    assert prov_p.exists(), prov_p
    img = nib.load(str(out_p))
    nd = img.get_fdata()
    nan_c = int(np.isnan(nd).sum())
    inf_c = int(np.isinf(nd).sum())
    nnz = int((nd != 0).sum())
    nmin, nmax = float(nd.min()), float(nd.max())
    tsum = float(nd.sum())
    grid_ok = (nd.shape == SHAPE
               and np.allclose(img.affine, ref_affine, atol=1e-3)
               and tuple(nib.aff2axcodes(img.affine)) == ("R", "A", "S"))
    finite_ok = (nan_c == 0 and inf_c == 0)
    range_ok = (nmin >= -1e-4) and (nmax <= 1.000001)
    nonempty_ok = nnz > 0
    h = _hemi_flip(nd, img.affine, row["hemisphere"])
    flip = bool(h["flip"] or h.get("empty", False))
    com = _com(nd, img.affine)
    # boundary contact: support voxels on any outer FOV plane (1-voxel shell)
    if nnz:
        coords = np.argwhere(nd != 0)
        on_face = ((coords[:, 0] == 0) | (coords[:, 0] == SHAPE[0] - 1)
                   | (coords[:, 1] == 0) | (coords[:, 1] == SHAPE[1] - 1)
                   | (coords[:, 2] == 0) | (coords[:, 2] == SHAPE[2] - 1)).mean()
    else:
        on_face = None
    prov = json.loads(prov_p.read_text(encoding="utf-8"))
    # cross-check transform-time provenance vs independent recompute
    cross_ok = bool(
        prov.get("output_sha256") == _sha(out_p)
        and prov.get("target_nonzero_voxels") == nnz
        and prov.get("normalized_min") is not None
    )
    return {
        "component_index": idx,
        "parcel_id": int(row["parcel_id"]),
        "lut_name": row["lut_name"],
        "official_code": code,
        "hemisphere": row["hemisphere"],
        "canonical_g3_id": row["canonical_g3_id"],
        "canonical_name": row["canonical_name"],
        "official_name": row.get("official_name", row["canonical_name"]),
        "lobe": row.get("lobe", ""),
        "macro_gyrus_name": row.get("macro_gyrus_name", ""),
        "source_asset": row["source_asset_path"],
        "source_sha256": prov["source_sha256"],
        "output_asset": f"data/atlases/brainnetome/bna246/transformed_to_julich2009c/probability_maps/{out_p.name}",
        "output_sha256": _sha(out_p),
        "source_space": prov["source_space"],
        "target_space": prov["target_space"],
        "transform_sha256": prov["transform_sha256"],
        "tool": prov["tool"],
        "tool_version": prov["tool_version"],
        "interpolation": prov["interpolation"],
        "source_scale": prov["source_scale"],
        "output_scale": prov["output_scale"],
        "source_nonzero_voxels": prov["source_nonzero_voxels"],
        "target_nonzero_voxels": nnz,
        "source_probability_sum": prov["source_probability_sum"],
        "target_probability_sum": round(tsum, 4),
        "probability_sum_ratio": round(tsum / prov["source_probability_sum"], 6) if prov["source_probability_sum"] else None,
        "support_volume_ratio": round(nnz / prov["source_nonzero_voxels"], 6) if prov["source_nonzero_voxels"] else None,
        "source_weighted_com_mm": prov["source_weighted_com_mm"],
        "target_weighted_com_mm": com,
        "boundary_touch_fraction": round(float(on_face), 6) if on_face is not None else None,
        "target_grid_match": bool(grid_ok),
        "hemisphere_check": bool(not flip),
        "finite_check": bool(finite_ok),
        "range_check": bool(range_ok),
        "nonempty_check": bool(nonempty_ok),
        "cross_check": bool(cross_ok),
        "normalized_min": nmin,
        "normalized_max": nmax,
        "correct_side_mass_fraction": h["correct_side_mass_fraction"],
        "transform_status": "PASS" if (grid_ok and finite_ok and range_ok and nonempty_ok and not flip and cross_ok) else "FAIL",
    }


def _load_authoritative_by_parcel():
    rows = list(csv.DictReader(open(BNA_VOL.parent / "brainnetome_bna246_subregions_authoritative.csv", encoding="utf-8-sig")))
    return {int(r["parcel_id"]): r for r in rows}


def _draw_rep(pix_src, pix_tgt, name, idx, code, out_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    shp = SHAPE
    sl = [shp[0] // 2, shp[1] // 2, shp[2] // 2]
    axes_names = ["sagittal", "coronal", "axial"]
    fig, ax = plt.subplots(2, 3, figsize=(15, 9))
    for j, s in enumerate(sl):
        ax[0, j].imshow(np.rot90(pix_src[s, :, :] if j == 0 else (pix_src[:, s, :] if j == 1 else pix_src[:, :, s])), cmap="hot")
        ax[0, j].set_title(f"source (NLin6) {axes_names[j]}")
        ax[1, j].imshow(np.rot90(pix_tgt[s, :, :] if j == 0 else (pix_tgt[:, s, :] if j == 1 else pix_tgt[:, :, s])), cmap="hot")
        ax[1, j].set_title(f"transformed (2009c) {axes_names[j]}")
    fig.suptitle(f"BNA comp {idx:03d} {code} ({name}) NLin6->2009c [rep QA]")
    fig.tight_layout()
    fig.savefig(out_png, dpi=110)
    plt.close(fig)


def main() -> int:
    QA_DIR.mkdir(parents=True, exist_ok=True)
    identity = _rows("g3_brainnetome_probability_to_canonical_alignment.csv")
    auth = _load_authoritative_by_parcel()
    # merge authoritative (frozen, by parcel_id) for official macro names / lobes
    merged = []
    for r in identity:
        pid = int(r["parcel_id"])
        a = auth.get(pid, {})
        merged.append({
            "component_index": int(r["component_index"]),
            "parcel_id": pid,
            "lut_name": r["lut_name"],
            "official_code": r["official_hemisphere_code"] or r["canonical_name"],
            "hemisphere": r["hemisphere"],
            "canonical_g3_id": r["canonical_g3_id"],
            "canonical_name": r["canonical_name"],
            "official_name": a.get("macro_gyrus_name", r["canonical_name"]),
            "lobe": a.get("lobe", ""),
            "macro_gyrus_name": a.get("macro_gyrus_name", ""),
            "source_asset_path": "data/atlases/brainnetome/bna246/volume_raw/BNA_PM_4D.nii.gz",
        })
    assert len(merged) == 246

    # ---- Julich 414 grid read-only re-verification ----
    jul_files = sorted(JULICH.glob("*.nii.gz"))
    ref_affine = None
    jul_ok = 0
    jul_issues = []
    for f in jul_files:
        im = nib.load(str(f))
        if ref_affine is None:
            ref_affine = np.asarray(im.affine)
            ref_shape = im.shape
        ok = (im.shape == ref_shape == SHAPE
              and np.allclose(im.affine, ref_affine, atol=1e-4)
              and tuple(nib.aff2axcodes(im.affine)) == ("R", "A", "S"))
        if ok:
            jul_ok += 1
        else:
            jul_issues.append(f.name)
    ref_affine_arr = ref_affine

    # ---- independent per-component verification ----
    rows_out = []
    for row in merged:
        idx = row["component_index"]
        try:
            rec = verify_component(idx, row, ref_affine_arr)
        except Exception as exc:
            rec = {**row, "transform_status": f"ERROR:{type(exc).__name__}:{str(exc)[:60]}"}
        rows_out.append(rec)

    # ---- aggregate ----
    stat = lambda k: [r[k] for r in rows_out if isinstance(r.get(k), (int, float))]
    grid_n = sum(1 for r in rows_out if r.get("target_grid_match") is True)
    finite_n = sum(1 for r in rows_out if r.get("finite_check") is True)
    range_n = sum(1 for r in rows_out if r.get("range_check") is True)
    nonempty_n = sum(1 for r in rows_out if r.get("nonempty_check") is True)
    flip_n = sum(1 for r in rows_out if r.get("hemisphere_check") is not True)
    cross_n = sum(1 for r in rows_out if r.get("cross_check") is True)
    pass_n = sum(1 for r in rows_out if r.get("transform_status") == "PASS")
    fail_n = sum(1 for r in rows_out if r.get("transform_status") != "PASS")

    sum_ratio = _percentiles(stat("probability_sum_ratio"))
    support_ratio = _percentiles(stat("support_volume_ratio"))
    boundary = [r for r in rows_out if (r.get("boundary_touch_fraction") or 0) >= 0.05]
    # any prob-mass in a wider outer shell (clipping proxy) - reported, not auto-fail
    shell_heavy = []
    for r in rows_out:
        if r.get("transform_status") not in ("PASS",):
            continue
        img = nib.load(str(PROB / Path(r["output_asset"]).name))
        nd = img.get_fdata()
        nz = nd != 0
        if int(nz.sum()) == 0:
            continue
        coords = np.argwhere(nz)
        in_shell = ((coords[:, 0] < 3) | (coords[:, 0] > SHAPE[0] - 4)
                    | (coords[:, 1] < 3) | (coords[:, 1] > SHAPE[1] - 4)
                    | (coords[:, 2] < 3) | (coords[:, 2] > SHAPE[2] - 4))
        frac = float((nd[nz][in_shell]).sum() / nd[nz].sum())
        if frac > 0.05:
            shell_heavy.append({"component": r["component_index"], "code": r["official_code"],
                                "outer_5mm_mass_fraction": round(frac, 5)})

    # ---- L/R symmetric auxiliary QA (pairs by frozen bilateral code) ----
    pairs = defaultdict(list)
    for r in rows_out:
        code = r["official_code"]
        # BNA bilateral code infix _L_/_R_ -> _X_
        if "_L_" in code:
            key = code.replace("_L_", "_X_", 1)
        elif "_R_" in code:
            key = code.replace("_R_", "_X_", 1)
        else:
            key = None
        if key:
            pairs[key].append(r)
    bad_pairs = {k: v for k, v in pairs.items() if len(v) != 2}
    pair_vol = []
    for k, v in pairs.items():
        if len(v) == 2:
            l = next(x for x in v if x["hemisphere"] == "left")
            r = next(x for x in v if x["hemisphere"] == "right")
            ratio = l["target_nonzero_voxels"] / r["target_nonzero_voxels"] if r["target_nonzero_voxels"] else None
            if ratio is not None:
                pair_vol.append(ratio)
    pair_ratio_pct = _percentiles(pair_vol) if pair_vol else None

    # ---- representative deterministic selection (role-labelled) ----
    def candidates(pred):
        return [r for r in rows_out if r.get("transform_status") == "PASS" and pred(r)]
    lats = {}
    for hemi in ("left", "right"):
        pool = candidates(lambda r, h=hemi: r["hemisphere"] == h and r["lobe"] != "Subcortical nuclei"
                          and r["target_weighted_com_mm"])
        pool = sorted(pool, key=lambda r: abs(r["target_weighted_com_mm"][0]), reverse=True)
        lats[hemi] = pool[:2]
    mid_pool = candidates(lambda r: r["target_weighted_com_mm"]
                          and r["target_nonzero_voxels"] >= np.median(stat("target_nonzero_voxels")))
    mid = sorted(mid_pool, key=lambda r: abs(r["target_weighted_com_mm"][0]))[0]
    sub_pool = candidates(lambda r: r["lobe"] == "Subcortical nuclei" and r["target_nonzero_voxels"])
    sub_med = float(np.median([r["target_nonzero_voxels"] for r in sub_pool]))
    sub = sorted(sub_pool, key=lambda r: abs(r["target_nonzero_voxels"] - sub_med))[0]
    role_map = [
        (lats["left"][0], "LATERAL_LEFT_1"), (lats["left"][1], "LATERAL_LEFT_2"),
        (lats["right"][0], "LATERAL_RIGHT_1"), (lats["right"][1], "LATERAL_RIGHT_2"),
        (mid, "NEAR_MIDLINE"), (sub, "SUBCORTICAL"),
    ]
    seen = []
    for r, role in role_map:
        if r["component_index"] not in [x[0]["component_index"] for x in seen]:
            seen.append((r, role))
    seen_det = [{"component_index": r["component_index"], "official_code": r["official_code"],
                 "canonical_name": r["canonical_name"], "hemisphere": r["hemisphere"],
                 "lobe": r["lobe"], "role": role} for r, role in seen]

    # render representative QA (loads source 4D once)
    src4 = np.asarray(nib.load(str(PM4D)).dataobj).astype(np.float64)
    rep_paths = []
    for (r, role), det in zip(seen, seen_det):
        idx = r["component_index"]
        code_safe = "".join(ch for ch in r["official_code"] if ch.isalnum() or ch == "_")
        tgt = nib.load(str(PROB / Path(r["output_asset"]).name))
        out_png = QA_DIR / f"rep_comp{idx:03d}_{code_safe}_slices.png"
        _draw_rep(src4[..., idx - 1], tgt.get_fdata(),
                  r["canonical_name"], idx, r["official_code"], out_png)
        rep_paths.append(str(out_png))
        det["png"] = str(out_png)

    # ---- write manifest CSV ----
    cols = ["component_index", "parcel_id", "official_name", "official_code", "canonical_g3_id",
            "hemisphere", "lut_name", "lobe", "macro_gyrus_name",
            "source_asset", "source_sha256", "output_asset", "output_sha256",
            "source_space", "target_space", "transform_sha256", "tool", "tool_version",
            "interpolation", "source_scale", "output_scale",
            "source_nonzero_voxels", "target_nonzero_voxels",
            "source_probability_sum", "target_probability_sum", "probability_sum_ratio",
            "support_volume_ratio", "target_grid_match", "hemisphere_check",
            "finite_check", "range_check", "nonempty_check", "cross_check",
            "boundary_touch_fraction", "correct_side_mass_fraction", "transform_status"]
    with open(MANIFEST, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows_out:
            w.writerow(r)

    summary = {
        "phase": "G4_G3_BATCH_TRANSFORM_V1",
        "component_total": 246,
        "pass_count": pass_n,
        "fail_count": fail_n,
        "target_grid_match_count": grid_n,
        "finite_pass_count": finite_n,
        "range_pass_count": range_n,
        "nonempty_pass_count": nonempty_n,
        "hemisphere_flip_count": flip_n,
        "cross_check_pass_count": cross_n,
        "probability_sum_ratio": sum_ratio,
        "support_volume_ratio": support_ratio,
        "boundary_touch_anomaly_candidates": boundary,
        "outer_5mm_shell_mass_heavy": shell_heavy,
        "lr_pair_count": len(pairs),
        "lr_pair_volume_ratio_L_over_R": pair_ratio_pct,
        "malformed_pairs": {k: len(v) for k, v in bad_pairs.items()},
        "Julich_target_grid_count": len(jul_files),
        "Julich_target_grid_match": jul_ok,
        "Julich_grid_issues": jul_issues,
        "transform_file": str(XFM.relative_to(BACKEND)).replace("\\", "/"),
        "transform_sha256": _sha(XFM),
        "tool": "SimpleITK",
        "version": json.loads(open(PROV / "comp001_provenance.json", encoding="utf-8").read())["tool_version"],
        "interpolation": "Linear",
        "normalization_policy": "divide_by_100_after_transform; raw percent is processing intermediate (not stored per component); normalized 0-1 is the formal downstream asset",
        "representative_qa": rep_paths,
        "representative_qa_detail": seen_det,
        "batch_status": "READY_FOR_G4_G3_PROBABILITY_OVERLAP" if pass_n == 246 and jul_ok == len(jul_files) else "G4_G3_BATCH_TRANSFORM_FIX_REQUIRED",
        "recorded": datetime.now(timezone.utc).isoformat(),
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- console report ----
    print(f"grid={grid_n}/246 finite={finite_n}/246 range={range_n}/246 nonempty={nonempty_n}/246 "
          f"hemi_flips={flip_n} cross={cross_n}/246 pass={pass_n}/246 fail={fail_n}/246")
    print("probability_sum_ratio:", sum_ratio)
    print("support_volume_ratio:", support_ratio)
    print("boundary_touch_anomaly_candidates:", len(boundary))
    print("outer_5mm_shell_mass_heavy:", len(shell_heavy))
    print("lr pairs:", len(pairs), "bad:", len(bad_pairs))
    print("Julich grid:", jul_ok, "/", len(jul_files))
    print("manifest:", MANIFEST)
    print("summary:", SUMMARY)
    print("batch_status:", summary["batch_status"])
    return 0 if summary["batch_status"] == "READY_FOR_G4_G3_PROBABILITY_OVERLAP" else 1


if __name__ == "__main__":
    sys.exit(main())
