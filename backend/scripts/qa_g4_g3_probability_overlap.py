"""Phase 2G — read-only representative QA + visual artifacts for the
414x246 probability overlap matrix.

Reads the matrix NPZ + row/col manifests + summary and renders:
  - 6 deterministic representative Julich components: 2 left-lateral cortex,
    2 right-lateral cortex, 1 near-midline, 1 subcortical (classified by true
    probability-weighted centre-of-mass x so "lateral"/"near-midline" are
    anatomically meaningful, not cherry-picked). Per-rep Top10-G3 bar charts
    (joint mass and cosine), coloured by G3 hemisphere.
  - one matrix overview heatmap.
Also recomputes every metric formula from M + masses/norms as an independent
consistency check. Writes a QA json. No DB, no matrix edits.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import nibabel as nib
import numpy as np

BACKEND = Path(__file__).resolve().parent.parent
INT = BACKEND / "data" / "integration"
QA_DIR = INT / "qa" / "g4_g3_probability_overlap"
JUL_PROB = BACKEND / "data" / "atlases" / "julich" / "v3.1" / "spatial_raw" / "probability_maps"

OUT_NPZ = INT / "g4_g3_probability_overlap_matrix.npz"
OUT_ROWS = INT / "g4_g3_probability_overlap_rows.csv"
OUT_COLS = INT / "g4_g3_probability_overlap_columns.csv"
OUT_SUM = INT / "g4_g3_probability_overlap_summary.json"
OUT_QA = INT / "g4_g3_probability_overlap_qa.json"

SUBCORTICAL = ("THALAMUS", "AMYGDALA", "HIPPOCAMPUS", "CAUDATE", "PUTAMEN",
               "PALLIDUM", "ACCUMBENS", "STRIATUM", "CLAUSTRO", "CLAUSTRE",
               "ZONA", "BASAL", "NUCLEUS")


def _rows(p: Path):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def com_x_by_row(jul_dir: Path, rows) -> dict[int, float]:
    """Probability-weighted centre-of-mass x (world mm) per Julich row."""
    out = {}
    for r in rows:
        idx = int(r["row_index"])
        img = nib.load(str(jul_dir / r["julich_asset_file"]))
        d = img.get_fdata()
        nz = d != 0
        if int(nz.sum()) == 0:
            out[idx] = float("nan")
            continue
        coords = np.argwhere(nz).astype(np.float64)
        vals = d[nz]
        vox = coords.T @ vals / vals.sum()
        out[idx] = float(nib.affines.apply_affine(img.affine, vox)[0])
    return out


def select_reps(rows, mass4, comx):
    mass_by = {int(r["row_index"]): float(mass4[int(r["row_index"]) - 1]) for r in rows}
    med = float(np.median(mass4))

    def is_subc(name):
        u = name.upper()
        return any(t in u for t in SUBCORTICAL)

    def pool(hemi=None, cortex_only=False):
        out = []
        for r in rows:
            idx = int(r["row_index"])
            if hemi and r["julich_hemisphere"] != hemi:
                continue
            if cortex_only and is_subc(r["julich_region_name"]):
                continue
            if mass_by[idx] < med:
                continue
            out.append(r)
        return sorted(out, key=lambda r: r["julich_asset_file"])

    def best_lateral(hemi, sign):
        cand = pool(hemi=hemi, cortex_only=True)
        good = [r for r in cand if np.sign(comx[int(r["row_index"])]) == sign and np.isfinite(comx[int(r["row_index"])])]
        if len(good) < 2:
            good = [r for r in cand if np.isfinite(comx[int(r["row_index"])])]
        good.sort(key=lambda r: (-abs(comx[int(r["row_index"])]), r["julich_asset_file"]))
        return good

    lat_l = best_lateral("left", -1)
    lat_r = best_lateral("right", 1)
    # near-midline: cortex, meaningful mass, min |comx|
    mid_cand = [r for r in pool(cortex_only=True) if np.isfinite(comx[int(r["row_index"])])]
    mid_cand.sort(key=lambda r: (abs(comx[int(r["row_index"])]), r["julich_asset_file"]))
    sub_cand = [r for r in rows if is_subc(r["julich_region_name"])
                and mass_by[int(r["row_index"])] >= med]
    sub_cand.sort(key=lambda r: r["julich_asset_file"])
    sub_med = float(np.median([mass_by[int(r["row_index"])] for r in sub_cand]))
    sub_cand.sort(key=lambda r: (abs(mass_by[int(r["row_index"])] - sub_med), r["julich_asset_file"]))

    candidates = [(lat_l[0], "LATERAL_LEFT_1"), (lat_l[1], "LATERAL_LEFT_2"),
                  (lat_r[0], "LATERAL_RIGHT_1"), (lat_r[1], "LATERAL_RIGHT_2"),
                  (mid_cand[0], "NEAR_MIDLINE"), (sub_cand[0], "SUBCORTICAL")]
    seen, out = set(), []
    for r, role in candidates:
        if r["row_index"] not in seen:
            seen.add(r["row_index"])
            out.append((r, role))
    return out


def main() -> int:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    QA_DIR.mkdir(parents=True, exist_ok=True)
    d = np.load(OUT_NPZ)
    M = d["M"]
    cosine = d["cosine"]
    mass4 = d["mass4"]
    rows = _rows(OUT_ROWS)
    cols = _rows(OUT_COLS)
    col_by_idx = {int(c["column_index"]): c for c in cols}
    summary = json.load(open(OUT_SUM, encoding="utf-8"))
    assert M.shape == (414, 246), M.shape

    comx = com_x_by_row(JUL_PROB, rows)
    reps = select_reps(rows, mass4, comx)

    rep_info = []
    for r, role in reps:
        row_idx = int(r["row_index"])
        j = row_idx - 1
        order = np.argsort(-M[j, :])[:10]
        labels = [f"{col_by_idx[i + 1]['g3_region_name']}" for i in order]
        vals_joint = [float(M[j, i]) for i in order]
        order_c = np.argsort(-cosine[j, :])[:10]
        labels_c = [f"{col_by_idx[i + 1]['g3_region_name']}" for i in order_c]
        vals_cos = [float(cosine[j, i]) for i in order_c]
        colors_c = ["#3b7dd8" if col_by_idx[i + 1]["g3_hemisphere"] == "left" else "#e08a3c"
                    for i in order_c]
        fig, axes = plt.subplots(1, 2, figsize=(15, 6))
        axes[0].barh(range(10)[::-1], vals_joint, color="#3b7dd8")
        axes[0].set_yticks(range(10)[::-1], labels[::-1], fontsize=8)
        axes[0].set_title("Top10 G3 by joint_weighted_mass")
        axes[1].barh(range(10)[::-1], vals_cos, color=colors_c[::-1])
        axes[1].set_yticks(range(10)[::-1], labels_c[::-1], fontsize=8)
        axes[1].set_title("Top10 G3 by probability_cosine (L blue / R orange)")
        fig.suptitle(f"{role}  julich row {row_idx}  {r['julich_region_name']}  ({r['julich_hemisphere']})  "
                     f"com_x={comx[row_idx]:.1f} mm")
        fig.tight_layout()
        png = QA_DIR / f"rep_{role}_row{row_idx:03d}.png"
        fig.savefig(png, dpi=110)
        plt.close(fig)
        rep_info.append({"role": role, "row_index": row_idx,
                         "julich_asset_file": r["julich_asset_file"],
                         "julich_region_name": r["julich_region_name"],
                         "julich_hemisphere": r["julich_hemisphere"],
                         "com_x_mm": round(comx[row_idx], 2),
                         "spatial_identity_status": r["spatial_identity_status"], "png": str(png)})

    fig, ax = plt.subplots(figsize=(11, 8))
    im = ax.imshow(np.log10(M + 1e-6), aspect="auto", cmap="inferno")
    ax.set_xlabel("Brainnetome G3 column (component_index 1..246)")
    ax.set_ylabel("Julich row (sorted asset file, 1..414)")
    ax.set_title("log10 joint_weighted_mass 414x246")
    fig.colorbar(im, ax=ax, fraction=0.03)
    overview = QA_DIR / "matrix_overview_heatmap.png"
    fig.savefig(overview, dpi=120)
    plt.close(fig)

    # independent formula recomputation from raw components
    mass3 = d["mass3"]
    g4w, g3w, sd = d["g4w"], d["g3w"], d["soft_dice"]
    n4, n3 = d["norm2_4"], d["norm2_3"]
    errs = {
        "cosine": float(np.abs(M / np.sqrt(n4[:, None] * n3[None, :]) - cosine).max()),
        "g4_mass_weighted": float(np.abs(M / mass4[:, None] - g4w).max()),
        "g3_mass_weighted": float(np.abs(M / mass3[None, :] - g3w).max()),
        "soft_dice": float(np.abs(2 * M / (n4[:, None] + n3[None, :]) - sd).max()),
    }

    qa = {"representative_components": rep_info,
          "overview_heatmap": str(overview),
          "formula_recompute_max_abs_error": max(errs.values()),
          "formula_recompute_errors": errs,
          "formula_recompute_ok": bool(max(errs.values()) < 1e-6),
          "hemisphere_QA_anomaly_count": summary["hemisphere_QA_anomaly_count"],
          "opposite_hemisphere_top1_count": summary["opposite_hemisphere_top1_count"],
          "recorded": summary["recorded"]}
    OUT_QA.write_text(json.dumps(qa, ensure_ascii=False, indent=1), encoding="utf-8")
    for x in rep_info:
        print(f"{x['role']:16s} row{x['row_index']:03d} {x['julich_asset_file']:44s} com_x={x['com_x_mm']:7.2f}")
    print("formula errors:", {k: round(v, 12) for k, v in errs.items()})
    print("QA json ->", OUT_QA)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
