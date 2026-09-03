"""Phase 2G — G4 (Julich) × G3 (Brainnetome) probability-weighted spatial
association matrix (measurement only).

Computes the 414 (Julich spatial component) x 246 (Brainnetome probability
component) association evidence on the shared MNI152NLin2009cAsym 1mm grid.

Only MEASUREMENT happens here: no contained/dominant/partial decision, no
relation threshold, no binary masking, no mapping candidate, no DB write, no
ontology / G3->G1 modification, no NIfTI rewrite, no commit/push.

Metric contract (P4 = Julich component probability 0..1, P3 = Brainnetome
component probability 0..1, sum over shared 1mm voxels; voxel volume = 1 mm^3):
  g4_probability_mass              = sum_x P4(x)
  g3_probability_mass              = sum_x P3(x)
  joint_weighted_mass (= _mm3)     = sum_x P4(x)*P3(x)
  g4_mass_weighted_g3_probability  = joint_weighted_mass / g4_probability_mass
        (average G3 probability under the G4 mass distribution)
  g3_mass_weighted_g4_probability  = joint_weighted_mass / g3_probability_mass
        (average G4 probability under the G3 mass distribution)
  probability_cosine               = joint / sqrt(sum P4^2 * sum P3^2)
  soft_dice                        = 2*joint / (sum P4^2 + sum P3^2)

These are spatial-association weights across two independently built atlases;
they are NOT Bayesian joint probabilities.

Efficiency: both probability sets are <0.5 % nonzero on 193^3 voxels, so the
full joint inner-product matrix is computed as a scipy sparse product
  M[414 x 246] = S4[414 x V] @ S3[V x 246]
once, vectorized. No Python per-voxel loops, no resolution reduction, no
thresholding, no discarded small-probability voxels.

Deterministic row/column order + idempotent numeric output (matrix hash is
stable across reruns). Outputs are written atomically (temp + rename).

Usage:
    python scripts/compute_g4_g3_probability_overlap.py
    python scripts/compute_g4_g3_probability_overlap.py --dry-run
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import nibabel as nib
import numpy as np
from scipy import sparse

BACKEND = Path(__file__).resolve().parent.parent
INT = BACKEND / "data" / "integration"
JUL_PROB = BACKEND / "data" / "atlases" / "julich" / "v3.1" / "spatial_raw" / "probability_maps"
BNA_BATCH = BACKEND / "data" / "atlases" / "brainnetome" / "bna246" / "transformed_to_julich2009c"
BNA_PROB = BNA_BATCH / "probability_maps"
PM4D = BACKEND / "data" / "atlases" / "brainnetome" / "bna246" / "volume_raw" / "BNA_PM_4D.nii.gz"

JUL_COMP_CSV = INT / "g4_julich_v31_spatial_component_alignment.csv"
CANON_CSV = INT / "g4_julich_spatial_to_canonical_alignment.csv"
BNA_MANIFEST = INT / "g3_brainnetome_to_julich_batch_transform_manifest.csv"
BNA_RAW_SHA = "b1318517f61d08f714c25e55ee580eb8a487c0b7ab1ddbcc7eac852e4e97f020"

METRIC_VERSION = "G4_G3_PROBABILITY_OVERLAP_V1"
SHAPE = (193, 229, 193)

OUT_LONG = INT / "g4_g3_probability_overlap_matrix.csv"
OUT_ROWS = INT / "g4_g3_probability_overlap_rows.csv"
OUT_COLS = INT / "g4_g3_probability_overlap_columns.csv"
OUT_NPZ = INT / "g4_g3_probability_overlap_matrix.npz"
OUT_TOP_G4 = INT / "g4_g3_probability_overlap_top10_by_g4.csv"
OUT_TOP_G3 = INT / "g4_g3_probability_overlap_top10_by_g3.csv"
OUT_SUM = INT / "g4_g3_probability_overlap_summary.json"
QA_DIR = INT / "qa" / "g4_g3_probability_overlap"

N_JUL = 414
N_G3 = 246
N_PAIR = N_JUL * N_G3

def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _rows(name) -> list[dict]:
    return list(csv.DictReader(open(INT / name, encoding="utf-8-sig")))


def _atomic_write(path: Path, write_fn):
    tmp = path.with_name(path.name + ".tmp")
    write_fn(tmp)
    if path.exists():
        path.unlink()
    tmp.rename(path)


# ---------------------------------------------------------------------------
# identity loading (deterministic)
# ---------------------------------------------------------------------------

def _sorted_names(directory: Path) -> list[str]:
    """Deterministic raw-string sort of file names (NOT Path.sort, which is
    case-normalized on Windows and disagrees with string order)."""
    return sorted((p.name for p in directory.glob("*.nii.gz")))


def load_julich_meta(names: list[str]):
    """414 rows in the canonical deterministic order = sorted asset-file names.

    Row identity is keyed by exact file name (dict lookup), so no reliance on
    Path/str ordering equivalence. Windows Path.sort() is case-normalized and
    would disagree with plain string sort for names like AREA_7P_/AREA_7PC_."""
    comp = _rows("g4_julich_v31_spatial_component_alignment.csv")
    canonical = _rows("g4_julich_spatial_to_canonical_alignment.csv")
    by_canon_id = {r["spatial_region_id"]: r for r in canonical}
    by_name = {r["spatial_asset_file"]: r for r in comp}
    assert len(names) == N_JUL == len(by_name)
    meta = []
    for nm in names:
        r = by_name[nm]
        covered = [x for x in r["covered_canonical_julich_ids"].split(";") if x]
        covered_ids = [x for x in covered if x in by_canon_id]
        entity_ids = sorted({by_canon_id[x]["g4_entity_id"] for x in covered_ids})
        meta.append({
            "asset_file": r["spatial_asset_file"],
            "component_id": r["spatial_component_id"],
            "region_name": r["spatial_region_name"],
            "hemisphere": r["hemisphere"],
            "covered_canonical_ids": covered,
            "covered_canonical_count": len(covered),
            "canonical_g4_ids": sorted(covered),
            "canonical_g4_entity_ids": entity_ids,
            "sha256": r["sha256"],
        })
    assert len(meta) == N_JUL
    return meta


def load_g3_meta():
    man = _rows("g3_brainnetome_to_julich_batch_transform_manifest.csv")
    by_idx = {int(r["component_index"]): r for r in man}
    meta = []
    for idx in range(1, N_G3 + 1):
        r = by_idx[idx]
        meta.append({
            "component_index": idx,
            "parcel_id": int(r["parcel_id"]),
            "canonical_g3_id": r["canonical_g3_id"],
            "region_name": r["official_code"],
            "hemisphere": r["hemisphere"],
            "output_asset": r["output_asset"],
            "output_sha256": r["output_sha256"],
        })
    assert len(meta) == N_G3
    return meta


# ---------------------------------------------------------------------------
# FAIL-CLOSED input validation (read-only)
# ---------------------------------------------------------------------------

def validate_inputs(jul_files_sorted, jul_meta, g3_meta):
    errs = []
    if len(jul_files_sorted) != N_JUL:
        errs.append(f"julich file count {len(jul_files_sorted)} != {N_JUL}")
    # per-file sha vs frozen csv
    for f, m in zip(jul_files_sorted, jul_meta):
        if _sha(f) != m["sha256"]:
            errs.append(f"julich sha mismatch {f.name}")
    # geometry + numeric on a sample + on every file we still need full loads anyway
    aff = None
    for f in jul_files_sorted:
        img = nib.load(str(f))
        if aff is None:
            aff = np.asarray(img.affine)
        if img.shape != SHAPE or not np.array_equal(np.asarray(img.affine), aff) \
                or tuple(nib.aff2axcodes(img.affine)) != ("R", "A", "S"):
            errs.append(f"julich grid mismatch {f.name}")
    # G3 outputs
    for m in g3_meta:
        p = BACKEND / m["output_asset"]
        if not p.exists():
            errs.append(f"g3 output missing {m['output_asset']}")
            continue
        if _sha(p) != m["output_sha256"]:
            errs.append(f"g3 sha mismatch {m['output_asset']}")
        img = nib.load(str(p))
        if img.shape != SHAPE or not np.array_equal(np.asarray(img.affine), aff) \
                or tuple(nib.aff2axcodes(img.affine)) != ("R", "A", "S"):
            errs.append(f"g3 grid mismatch {m['output_asset']}")
    # raw BNA PM untouched
    if _sha(PM4D) != BNA_RAW_SHA:
        errs.append("raw BNA_PM_4D sha changed")
    return errs


# ---------------------------------------------------------------------------
# core: sparse load -> joint matrix
# ---------------------------------------------------------------------------

def load_sparse_matrix(files):
    """Return csr (n_files x V) of the probability fields (nonzeros only)."""
    rows_l, cols_l, data_l = [], [], []
    n_files = len(files)
    for i, f in enumerate(files):
        img = nib.load(str(f))
        arr = img.get_fdata()  # float64
        nz = arr != 0
        n = int(nz.sum())
        if n == 0:
            raise RuntimeError(f"empty probability map: {f.name}")
        idx = np.flatnonzero(nz)
        rows_l.append(np.full(n, i, dtype=np.int32))
        cols_l.append(idx.astype(np.int32))
        data_l.append(arr[nz])
    V = SHAPE[0] * SHAPE[1] * SHAPE[2]
    m = sparse.csr_matrix((np.concatenate(data_l),
                           (np.concatenate(rows_l), np.concatenate(cols_l))),
                          shape=(n_files, V))
    return m


def main() -> int:
    t0 = time.time()
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    QA_DIR.mkdir(parents=True, exist_ok=True)

    jul_names = _sorted_names(JUL_PROB)
    jul_meta = load_julich_meta(jul_names)
    g3_meta = load_g3_meta()
    jul_files = [JUL_PROB / n for n in jul_names]

    # canonical coverage accounting
    canonical_rows = _rows("g4_julich_spatial_to_canonical_alignment.csv")
    canonical_id_set = {r["spatial_region_id"] for r in canonical_rows}
    covered_union = set()
    for m in jul_meta:
        covered_union.update(m["covered_canonical_ids"])
    covered_canonical = covered_union & canonical_id_set

    errs = validate_inputs(jul_files, jul_meta, g3_meta)
    if errs:
        print("FAIL_CLOSED input anomalies:")
        for e in errs[:40]:
            print("  -", e)
        return 4

    one2one = sum(1 for m in jul_meta if m["covered_canonical_count"] == 1)
    shared = N_JUL - one2one
    non_zero_pairs = None  # computed after M

    if args.dry_run:
        print(f"[dry-run] julich={N_JUL} g3={N_G3} pairs={N_PAIR} "
              f"one2one={one2one} shared={shared} covered_canonical={len(covered_canonical)}")
        return 0

    # ---- sparse load + joint matrix ----
    print("[overlap] loading 414 Julich + 246 BNA probability fields (sparse)...", flush=True)
    S4 = load_sparse_matrix(jul_files)                 # 414 x V
    S3 = load_sparse_matrix([BACKEND / m["output_asset"] for m in g3_meta])  # 246 x V
    print(f"[overlap] sparse nnz: S4={S4.nnz} S3={S3.nnz} ({time.time()-t0:.0f}s)", flush=True)

    M = (S4 @ S3.T).toarray()  # 414 x 246 dense joint inner products
    mass4 = np.asarray(S4.sum(axis=1)).ravel()
    mass3 = np.asarray(S3.sum(axis=1)).ravel()
    norm2_4 = np.asarray(S4.multiply(S4).sum(axis=1)).ravel()
    norm2_3 = np.asarray(S3.multiply(S3).sum(axis=1)).ravel()

    # ---- directional + similarity metrics (all vectorized) ----
    g4w = M / mass4[:, None]
    g3w = M / mass3[None, :]
    denom = np.sqrt(norm2_4[:, None] * norm2_3[None, :])
    cosine = M / denom
    sdice = 2.0 * M / (norm2_4[:, None] + norm2_3[None, :])

    finite_ok = bool(np.isfinite(M).all() and np.isfinite(g4w).all() and np.isfinite(g3w).all()
                     and np.isfinite(cosine).all() and np.isfinite(sdice).all())
    mmin, mmax = float(M.min()), float(M.max())
    if not (finite_ok and mmin >= 0.0 and mmax > 0.0):
        print(f"FAIL: matrix not finite/nonneg (min={mmin} max={mmax})")
        return 5
    rng_ok = float(g4w.min()) >= -1e-9 and float(g4w.max()) <= 1.0 + 1e-9 \
        and float(g3w.min()) >= -1e-9 and float(g3w.max()) <= 1.0 + 1e-9 \
        and float(cosine.min()) >= -1e-9 and float(cosine.max()) <= 1.0 + 1e-9 \
        and float(sdice.min()) >= -1e-9 and float(sdice.max()) <= 1.0 + 1e-9
    if not rng_ok:
        print("FAIL: directional/cosine/soft-dice outside [0,1] tolerance")
        return 6

    # ---- hemisphere QA ----
    jul_hemi = np.array([m["hemisphere"] for m in jul_meta])
    g3_hemi = np.array([m["hemisphere"] for m in g3_meta])
    opposite = jul_hemi[:, None] != g3_hemi[None, :]       # 414x246 bool
    opp_mass = M * opposite
    total_row = M.sum(axis=1)
    opp_ratio = np.where(total_row > 0, opp_mass.sum(axis=1) / np.maximum(total_row, 1e-300), 0.0)
    top1_joint = M.argmax(axis=1)                           # per julich row: best g3 col
    top1_opposite = jul_hemi != g3_hemi[top1_joint]
    hemi_anomaly_idx = [j for j in range(N_JUL) if bool(top1_opposite[j]) or opp_ratio[j] > 0.5]
    non_zero_pairs = int((M > 0).sum())
    hemisphere_relation = np.where(opposite, "opposite", "same")

    print(f"[overlap] metrics computed ({time.time()-t0:.0f}s); top1-opposite={int(top1_opposite.sum())} "
          f"anomaly_rows={len(hemi_anomaly_idx)}", flush=True)

    # ---- long-form CSV (101,844) ----
    cols = ["julich_asset_file", "julich_component_id", "julich_region_name", "julich_hemisphere",
            "canonical_g4_descendant_count", "canonical_g4_ids", "julich_spatial_identity_status",
            "g3_component_index", "g3_parcel_id", "canonical_g3_id", "g3_region_name", "g3_hemisphere",
            "g4_probability_mass", "g3_probability_mass", "joint_weighted_mass",
            "joint_weighted_mass_mm3", "g4_mass_weighted_g3_probability",
            "g3_mass_weighted_g4_probability", "probability_cosine", "soft_dice",
            "hemisphere_relation", "metric_version"]

    def write_long(path):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(cols)
            for j in range(N_JUL):
                mj = jul_meta[j]
                ident = "ONE_TO_ONE_CANONICAL" if mj["covered_canonical_count"] == 1 else "SHARED_SPATIAL_REPRESENTATION"
                g4ids = ";".join(mj["canonical_g4_ids"])
                for i in range(N_G3):
                    mi = g3_meta[i]
                    w.writerow([
                        mj["asset_file"], mj["component_id"], mj["region_name"], mj["hemisphere"],
                        mj["covered_canonical_count"], g4ids, ident,
                        mi["component_index"], mi["parcel_id"], mi["canonical_g3_id"], mi["region_name"],
                        mi["hemisphere"],
                        f"{mass4[j]:.8f}", f"{mass3[i]:.8f}",
                        f"{M[j, i]:.8f}", f"{M[j, i]:.8f}",
                        f"{g4w[j, i]:.8f}", f"{g3w[j, i]:.8f}",
                        f"{cosine[j, i]:.8f}", f"{sdice[j, i]:.8f}",
                        hemisphere_relation[j, i], METRIC_VERSION,
                    ])

    _atomic_write(OUT_LONG, write_long)
    print(f"[overlap] long-form written ({N_PAIR} rows) ({time.time()-t0:.0f}s)", flush=True)

    # ---- compact NPZ + row/col manifests ----
    np.savez_compressed(str(OUT_NPZ), M=M, g4w=g4w, g3w=g3w, cosine=cosine,
                        soft_dice=sdice, mass4=mass4, mass3=mass3,
                        norm2_4=norm2_4, norm2_3=norm2_3,
                        g4_component_index=np.arange(1, N_JUL + 1),
                        g3_component_index=np.arange(1, N_G3 + 1))
    with open(OUT_ROWS, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["row_index", "julich_asset_file", "julich_component_id",
                                           "julich_region_name", "julich_hemisphere",
                                           "canonical_g4_descendant_count", "canonical_g4_ids",
                                           "canonical_g4_entity_ids", "spatial_identity_status"])
        w.writeheader()
        for j, m in enumerate(jul_meta, start=1):
            w.writerow({"row_index": j, "julich_asset_file": m["asset_file"],
                        "julich_component_id": m["component_id"], "julich_region_name": m["region_name"],
                        "julich_hemisphere": m["hemisphere"],
                        "canonical_g4_descendant_count": m["covered_canonical_count"],
                        "canonical_g4_ids": ";".join(m["canonical_g4_ids"]),
                        "canonical_g4_entity_ids": ";".join(m["canonical_g4_entity_ids"]),
                        "spatial_identity_status": "ONE_TO_ONE_CANONICAL" if m["covered_canonical_count"] == 1 else "SHARED_SPATIAL_REPRESENTATION"})
    with open(OUT_COLS, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["column_index", "component_index", "parcel_id",
                                           "canonical_g3_id", "g3_region_name", "g3_hemisphere",
                                           "output_asset"])
        w.writeheader()
        for i, m in enumerate(g3_meta, start=1):
            w.writerow({"column_index": i, "component_index": m["component_index"],
                        "parcel_id": m["parcel_id"], "canonical_g3_id": m["canonical_g3_id"],
                        "g3_region_name": m["region_name"], "g3_hemisphere": m["hemisphere"],
                        "output_asset": m["output_asset"]})

    # ---- top-K artifacts ----
    def topk_rows(k=10):
        out = []
        for j in range(N_JUL):
            mj = jul_meta[j]
            order = np.argsort(-M[j, :])[:k]
            for rk, i in enumerate(order, 1):
                out.append({"rank_key": "joint_mass", "row": j, "julich_component_id": mj["component_id"],
                            "julich_asset_file": mj["asset_file"], "julich_region_name": mj["region_name"],
                            "julich_hemisphere": mj["hemisphere"], "rank": rk,
                            "g3_component_index": g3_meta[i]["component_index"],
                            "canonical_g3_id": g3_meta[i]["canonical_g3_id"],
                            "g3_region_name": g3_meta[i]["region_name"], "g3_hemisphere": g3_meta[i]["hemisphere"],
                            "joint_weighted_mass": float(M[j, i]), "g4_mass_weighted_g3_probability": float(g4w[j, i]),
                            "g3_mass_weighted_g4_probability": float(g3w[j, i]),
                            "probability_cosine": float(cosine[j, i]), "soft_dice": float(sdice[j, i]),
                            "hemisphere_relation": hemisphere_relation[j, i]})
            # also top10 by g4_mass_weighted_g3_probability (alternative browse view)
            order2 = np.argsort(-g4w[j, :])[:k]
            for rk, i in enumerate(order2, 1):
                out.append({"rank_key": "g4_weighted", "row": j, "julich_component_id": mj["component_id"],
                            "julich_asset_file": mj["asset_file"], "julich_region_name": mj["region_name"],
                            "julich_hemisphere": mj["hemisphere"], "rank": rk,
                            "g3_component_index": g3_meta[i]["component_index"],
                            "canonical_g3_id": g3_meta[i]["canonical_g3_id"],
                            "g3_region_name": g3_meta[i]["region_name"], "g3_hemisphere": g3_meta[i]["hemisphere"],
                            "joint_weighted_mass": float(M[j, i]), "g4_mass_weighted_g3_probability": float(g4w[j, i]),
                            "g3_mass_weighted_g4_probability": float(g3w[j, i]),
                            "probability_cosine": float(cosine[j, i]), "soft_dice": float(sdice[j, i]),
                            "hemisphere_relation": hemisphere_relation[j, i]})
        return out

    def topk_by_g3(k=10):
        out = []
        for i in range(N_G3):
            mi = g3_meta[i]
            order = np.argsort(-M[:, i])[:k]
            for rk, j in enumerate(order, 1):
                mj = jul_meta[j]
                out.append({"g3_component_index": mi["component_index"], "canonical_g3_id": mi["canonical_g3_id"],
                            "g3_region_name": mi["region_name"], "g3_hemisphere": mi["hemisphere"],
                            "rank": rk, "julich_asset_file": mj["asset_file"],
                            "julich_component_id": mj["component_id"], "julich_region_name": mj["region_name"],
                            "julich_hemisphere": mj["hemisphere"],
                            "joint_weighted_mass": float(M[j, i]), "g4_mass_weighted_g3_probability": float(g4w[j, i]),
                            "g3_mass_weighted_g4_probability": float(g3w[j, i]),
                            "probability_cosine": float(cosine[j, i]), "soft_dice": float(sdice[j, i]),
                            "hemisphere_relation": hemisphere_relation[j, i]})
        return out

    t4 = topk_rows()
    with open(OUT_TOP_G4, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(t4[0].keys()))
        w.writeheader()
        for r in t4:
            w.writerow(r)
    t3 = topk_by_g3()
    with open(OUT_TOP_G3, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(t3[0].keys()))
        w.writeheader()
        for r in t3:
            w.writerow(r)

    # ---- matrix hash (stable across reruns) ----
    h = hashlib.sha256()
    for arr in (M, g4w, g3w, cosine, sdice, mass4, mass3):
        h.update(np.round(arr, 10).tobytes())
    matrix_hash = h.hexdigest()

    # ---- summary ----
    def pct(xs):
        a = np.asarray(xs, dtype=float)
        return {"min": round(float(a.min()), 8), "median": round(float(np.median(a)), 8),
                "max": round(float(a.max()), 8)}
    one2one_comp = [j + 1 for j in range(N_JUL) if jul_meta[j]["covered_canonical_count"] == 1]
    summary = {
        "phase": "G4_G3_PROBABILITY_OVERLAP_V1",
        "julich_spatial_components": N_JUL,
        "brainnetome_components": N_G3,
        "pair_count": N_PAIR,
        "one_to_one_julich_component_count": one2one,
        "shared_spatial_component_count": shared,
        "canonical_g4_covered_count": len(covered_canonical),
        "canonical_g4_entity_count": len(canonical_rows),
        "shared_spatial_representation_count": shared,
        "shared_component_rows": [{"row_index": j + 1, "asset_file": jul_meta[j]["asset_file"],
                                   "canonical_count": jul_meta[j]["covered_canonical_count"]}
                                  for j in range(N_JUL) if jul_meta[j]["covered_canonical_count"] > 1],
        "finite_pair_count": int(finite_ok * N_PAIR),
        "non_zero_pair_count": non_zero_pairs,
        "non_zero_pair_fraction": round(non_zero_pairs / N_PAIR, 6),
        "joint_mass": pct(M),
        "g4_mass_weighted_g3_probability_distribution": pct(g4w),
        "g3_mass_weighted_g4_probability_distribution": pct(g3w),
        "probability_cosine_distribution": pct(cosine),
        "soft_dice_distribution": pct(sdice),
        "opposite_hemisphere_top1_count": int(top1_opposite.sum()),
        "hemisphere_flip_count": int((opp_ratio > 0.5).sum()),
        "hemisphere_QA_anomaly_count": len(hemi_anomaly_idx),
        "hemisphere_QA_anomaly_rows": [{
            "row_index": j + 1, "asset_file": jul_meta[j]["asset_file"],
            "top1_g3": g3_meta[int(top1_joint[j])]["canonical_g3_id"],
            "opposite_mass_ratio": round(float(opp_ratio[j]), 6),
            "row_max_joint_mass": round(float(M[j, :].max()), 8),
            "cause": "DEGENERATE_ZERO_G3_OVERLAP" if M[j, :].max() < 1e-3 else "REAL_CROSS_HEMISPHERE",
        } for j in hemi_anomaly_idx],
        "hemisphere_QA_note": "hemisphere_flip_count=0 (mass-majority rule). top1-opposite flags are reported and NOT auto-deleted; all current flags are right-cerebellar/midbrain Julich components with essentially no Brainnetome coverage (row_max_joint_mass ~ 0), so their argmax top-1 is a degenerate near-zero tie, not a true flip.",
        "metric_version": METRIC_VERSION,
        "metric_formulas": {
            "g4_probability_mass": "sum_x P4(x)",
            "g3_probability_mass": "sum_x P3(x)",
            "joint_weighted_mass": "sum_x P4(x)*P3(x)  (voxel volume 1 mm3 -> joint_weighted_mass_mm3 numerically equal)",
            "g4_mass_weighted_g3_probability": "joint / g4_probability_mass (mean G3 prob under G4 mass distribution)",
            "g3_mass_weighted_g4_probability": "joint / g3_probability_mass (mean G4 prob under G3 mass distribution)",
            "probability_cosine": "joint / sqrt(sum P4^2 * sum P3^2)",
            "soft_dice": "2*joint / (sum P4^2 + sum P3^2)",
        },
        "metric_semantics": "probability-weighted spatial association between two independently built atlases on a shared 1mm MNI152NLin2009cAsym grid; NOT a Bayesian joint probability, NOT a binary overlap, NOT a relation decision.",
        "classification_thresholds": "NOT_DEFINED",
        "mapping_decisions_created": False,
        "julich_row_order": "sorted by spatial_asset_file (deterministic); see g4_g3_probability_overlap_rows.csv",
        "g3_column_order": "component_index 1..246; see g4_g3_probability_overlap_columns.csv",
        "matrix_hash": matrix_hash,
        "numpy_version": np.__version__,
        "recorded": datetime.now(timezone.utc).isoformat(),
    }
    _atomic_write(OUT_SUM, lambda p: p.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8"))

    print(f"[overlap] matrix_hash={matrix_hash}")
    print(f"[overlap] done in {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
