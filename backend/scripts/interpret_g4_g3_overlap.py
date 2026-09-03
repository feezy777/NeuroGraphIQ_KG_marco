"""Phase 2H — G4→G3 spatial evidence interpretation & decision calibration prep.

Turns the Phase 2G continuous 414x246 evidence into ROW-LEVEL evidence profiles
for later scientific decisioning. This gate does NOT set relation thresholds,
does NOT emit contained/dominant/partial, does NOT create mapping candidates.

Role split (frozen):
  PRIMARY cross-atlas evidence  = Julich probability x Brainnetome probability
                                  (all Phase 2G metrics kept).
  AUXILIARY containment        = hard-label coverage of G4 probability mass
                                  inside Brainnetome BN_Atlas_246_1mm parcels
                                  (deterministic atlas, transformed to the
                                  Julich 2009c grid with NearestNeighbor).

Evidence strata (e.g. SINGLE_TARGET_CONCENTRATED / DIFFUSE_ASSOCIATION /
LOW_BNA_COVERAGE / ZERO_BNA_ASSOCIATION / SHARED_SPATIAL_REPRESENTATION) are
DESCRIPTIVE review strata only — never ontology relations.

Zero-overlap semantics: rows with max joint mass == 0 are marked
NO_SPATIAL_ASSOCIATION with NULL top1 (no fabricated argmax). Phase 2G artifacts
are NOT modified; the correction happens at this interpretation layer.

Usage:
    python scripts/interpret_g4_g3_overlap.py
"""

from __future__ import annotations

import csv
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
    sys.exit("SimpleITK required")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compute_g4_g3_probability_overlap as C  # reuse frozen identity/inputs

BACKEND = C.BACKEND
INT = C.INT
JUL_PROB = C.JUL_PROB
BNA_BATCH = BACKEND / "data" / "atlases" / "brainnetome" / "bna246"
BN1 = BNA_BATCH / "volume_raw" / "BN_Atlas_246_1mm.nii.gz"
XFM = BACKEND / "data" / "atlases" / "templateflow_ref" / "MNI152NLin2009cAsym_from-MNI152NLin6Asym_mode-image_xfm.h5"
JUL_REF = sorted(JUL_PROB.glob("*.nii.gz"))[0]
LABEL_DIR = BNA_BATCH / "transformed_label_to_julich2009c"
LABEL_OUT = LABEL_DIR / "BN_Atlas_246_1mm_NLin6to2009c_labels.nii.gz"
LABEL_PROV = LABEL_DIR / "label_transform_provenance.json"

NPZ = INT / "g4_g3_probability_overlap_matrix.npz"
ROWS_CSV = INT / "g4_g3_probability_overlap_rows.csv"
PROFILES = INT / "g4_g3_overlap_interpretation_profiles.csv"
SUMMARY = INT / "g4_g3_overlap_interpretation_summary.json"
DISAGREE = INT / "g4_g3_probability_hardlabel_disagreements.csv"
SHARED_REVIEW = INT / "g4_g3_shared_spatial_component_review.csv"
PACKET = INT / "g4_g3_scientific_review_packet.csv"
EXAMPLES = INT / "g4_g3_evidence_pattern_examples.csv"
THRESH = INT / "g4_g3_threshold_sensitivity_table.csv"
QA_DIR = INT / "qa" / "g4_g3_overlap_interpretation"

N_JUL = 414
N_G3 = 246
METRIC_VERSION = "G4_G3_OVERLAP_INTERPRETATION_V1"


def _atomic_write(path: Path, fn):
    tmp = path.with_name(path.name + ".tmp")
    fn(tmp)
    if path.exists():
        path.unlink()
    tmp.rename(path)


def _write_csv(path: Path, rows, cols):
    def _fn(tmp):
        with open(tmp, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)
    _atomic_write(path, _fn)


# ---------------------------------------------------------------------------
# 1. deterministic BN label transform (auxiliary asset, NearestNeighbor)
# ---------------------------------------------------------------------------

def ensure_label_transform() -> dict:
    LABEL_DIR.mkdir(parents=True, exist_ok=True)
    xfm_sha = C._sha(XFM)
    out = None
    if LABEL_OUT.exists() and LABEL_PROV.exists():
        try:
            prov = json.loads(LABEL_PROV.read_text(encoding="utf-8"))
        except Exception:
            prov = None
        if prov and prov.get("output_sha256") == C._sha(LABEL_OUT) \
                and prov.get("transform_sha256") == xfm_sha:
            out = prov
    if out is None:
        img = nib.load(str(BN1))
        labels = img.get_fdata()
        assert (labels == np.round(labels)).all()
        tmp_root = Path(tempfile.mkdtemp(prefix="bnlbl_", dir=str(LABEL_DIR)))
        try:
            tmp = tmp_root / "_src_labels.nii.gz"
            nib.save(nib.Nifti1Image(labels.astype(np.int32), img.affine), str(tmp))
            xfm = sitk.ReadTransform(str(XFM))
            ref_sitk = sitk.ReadImage(str(JUL_REF))
            out_img = sitk.Resample(sitk.ReadImage(str(tmp)), ref_sitk, xfm,
                                    sitk.sitkNearestNeighbor, 0, sitk.sitkUInt16)
            sitk.WriteImage(out_img, str(LABEL_OUT))
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)
        # read back + QA
        o = nib.load(str(LABEL_OUT))
        d = o.get_fdata()
        uniq = np.unique(d).astype(int)
        assert (d == np.round(d)).all()
        assert int(uniq.min()) >= 0 and int(uniq.max()) <= 246
        ref = nib.load(str(JUL_REF))
        grid_ok = (d.shape == (193, 229, 193)
                   and np.array_equal(np.asarray(o.affine), np.asarray(ref.affine))
                   and tuple(nib.aff2axcodes(o.affine)) == ("R", "A", "S"))
        present = set(uniq.tolist())
        vanished = sorted(set(range(1, 247)) - present)
        out = {
            "status": "PASS" if grid_ok else "FAIL",
            "source_asset": str(BN1),
            "source_sha256": C._sha(BN1),
            "source_space": "MNI152NLin6Asym 1mm",
            "target_space": "MNI152NLin2009cAsym 1mm (Julich native)",
            "transform_file": str(XFM),
            "transform_sha256": xfm_sha,
            "interpolation": "NearestNeighbor (GenericLabel)",
            "tool": "SimpleITK",
            "tool_version": sitk.Version_VersionString(),
            "output_asset": str(LABEL_OUT),
            "output_sha256": C._sha(LABEL_OUT),
            "shape": list(d.shape),
            "grid_match": bool(grid_ok),
            "integer_labels_only": True,
            "labels_range_ok": bool(int(d.min()) >= 0 and int(d.max()) <= 246),
            "labels_present_count": len(present),
            "labels_vanished_in_target": vanished,
            "nonzero_voxels_target": int((d != 0).sum()),
            "recorded": datetime.now(timezone.utc).isoformat(),
        }
        LABEL_PROV.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# 2. main interpretation
# ---------------------------------------------------------------------------

def _f(x, nd=8):
    return None if x is None else round(float(x), nd)


def _safe_div(a, b):
    return float(a / b) if b and b > 0 else (0.0 if a == 0 else None)


def _entropy_effective(p):
    """p: 1D non-negative weights -> (effective_target_count, entropy)."""
    p = np.asarray(p, dtype=float)
    p = p[p > 0]
    if p.size == 0:
        return None, None
    p = p / p.sum()
    h = float(-(p * np.log(p)).sum())
    return float(np.exp(h)), h


def main() -> int:
    QA_DIR.mkdir(parents=True, exist_ok=True)
    label_prov = ensure_label_transform()
    print("[2H] label transform:", label_prov["status"],
          "| vanished parcels:", label_prov["labels_vanished_in_target"])

    lab = nib.load(str(LABEL_OUT)).get_fdata().astype(np.int16)
    assert (lab == np.round(lab)).all()

    # ---- S4 reload + hard-label membership matrix ----
    jul_names = C._sorted_names(JUL_PROB)
    jul_meta = C.load_julich_meta(jul_names)
    g3_meta = C.load_g3_meta()
    g3byname = {m["canonical_g3_id"]: m for m in g3_meta}
    jul_files = [JUL_PROB / n for n in jul_names]
    print("[2H] building sparse S4 (414 Julich PMs)...", flush=True)
    S4 = C.load_sparse_matrix(jul_files)

    V = 193 * 229 * 193
    flat = lab.ravel()
    nz = np.flatnonzero(flat)
    col = flat[nz].astype(np.int64) - 1  # 0..245 (label 1..246 -> parcel index)
    assert (col >= 0).all() and (col < 246).all()
    row = nz.astype(np.int64)            # voxel index within L[V x 246]
    from scipy import sparse
    L = sparse.csr_matrix((np.ones(nz.size, dtype=np.float64), (row, col)),
                          shape=(V, N_G3))
    H = (S4 @ L).toarray()  # 414 x 246 hard-label numerator

    # ---- Phase 2G arrays ----
    d = np.load(str(NPZ))
    M = d["M"]            # joint inner product
    g4w = d["g4w"]        # g4_mass_weighted_g3
    g3w = d["g3w"]
    cosine = d["cosine"]
    sd = d["soft_dice"]
    mass4 = d["mass4"]
    assert M.shape == (414, 246)

    hard_cov = H / mass4[:, None]          # hard_label_g4_coverage
    hard_total = hard_cov.sum(axis=1)
    uncovered = 1.0 - hard_total
    # persist full coverage for the Phase 2I decision engine
    np.savez_compressed(str(INT / "g4_g3_hard_label_coverage_matrix.npz"),
                        coverage=hard_cov, uncovered=uncovered)

    canonical = C._rows("g4_julich_spatial_to_canonical_alignment.csv")
    canon_by_id = {r["spatial_region_id"]: r for r in canonical}

    # ---- per-row profile ----
    profiles = []
    for j in range(N_JUL):
        mj = jul_meta[j]
        ident = ("SHARED_SPATIAL_REPRESENTATION" if mj["covered_canonical_count"] > 1
                 else "ONE_TO_ONE_CANONICAL")
        rowj = M[j]
        rowmax = float(rowj.max())
        # PP top by joint mass (positive-mass columns only -> no fake zero top2)
        if rowmax > 0:
            pos_i = np.flatnonzero(rowj)
            order = pos_i[np.argsort(-rowj[pos_i])][:3]
            pp = []
            for i in order:
                pp.append({"g3_id": g3_meta[i]["canonical_g3_id"],
                           "name": g3_meta[i]["region_name"],
                           "joint": float(rowj[i]),
                           "g4w": float(g4w[j, i]), "g3w": float(g3w[j, i]),
                           "cos": float(cosine[j, i]), "sd": float(sd[j, i])})
        else:
            pp = []
        pp_top1 = pp[0] if pp else None
        pp_top2 = pp[1] if len(pp) > 1 else None
        pp_top3 = pp[2] if len(pp) > 2 else None
        pp_margin = (pp_top1["g4w"] - pp_top2["g4w"]) if (pp_top1 and pp_top2) else None
        pp_ratio = (_safe_div(pp_top1["g4w"], pp_top2["g4w"]) if (pp_top1 and pp_top2) else None)
        eff_pp, _ = _entropy_effective(rowj)

        # Hard-label top (positive-coverage parcels only -> no fake zero top2)
        hc = hard_cov[j]
        if hard_total[j] > 0:
            pos_h = np.flatnonzero(hc > 0)
            horder = pos_h[np.argsort(-hc[pos_h])][:3]
        else:
            horder = []
        hard = [{"g3_id": g3_meta[i]["canonical_g3_id"], "name": g3_meta[i]["region_name"],
                 "cov": float(hc[i])} for i in horder]
        h1 = hard[0] if hard else None
        h2 = hard[1] if len(hard) > 1 else None
        h3 = hard[2] if len(hard) > 2 else None
        hard_margin = (h1["cov"] - h2["cov"]) if (h1 and h2) else None
        hard_ratio = (_safe_div(h1["cov"], h2["cov"]) if (h1 and h2) else None)
        eff_hard, _ = _entropy_effective(hc) if hard_total[j] > 0 else (None, None)

        # agreement (only when both defined)
        if pp_top1 and h1:
            agree = bool(pp_top1["g3_id"] == h1["g3_id"])
            agreement = "TRUE" if agree else "FALSE"
        else:
            agreement = "NA"

        # coverage-gap / zero-association semantics
        zero_assoc = rowmax == 0.0
        coverage_gap_cand = bool((hard_total[j] < 0.10) or zero_assoc)

        # descriptive evidence pattern
        if zero_assoc:
            pattern = "ZERO_BNA_ASSOCIATION"
        elif ident == "SHARED_SPATIAL_REPRESENTATION":
            pattern = "SHARED_SPATIAL_REPRESENTATION"
        elif hard_total[j] < 0.10:
            pattern = "LOW_BNA_COVERAGE"
        elif h1 and h1["cov"] >= 0.7:
            pattern = "SINGLE_TARGET_CONCENTRATED"
        elif h1 and h1["cov"] >= 0.4 and h2 and h2["cov"] >= 0.2:
            pattern = "MULTI_TARGET_CONCENTRATED"
        else:
            pattern = "DIFFUSE_ASSOCIATION"
        if agreement == "FALSE" and not zero_assoc:
            pattern = "PROBABILITY_HARDLABEL_DISAGREEMENT"

        flags = []
        if zero_assoc:
            flags.append("NO_SPATIAL_ASSOCIATION")
        if coverage_gap_cand and not zero_assoc:
            flags.append("BNA_COVERAGE_GAP_CANDIDATE")
        if agreement == "FALSE":
            flags.append("PP_HARDLABEL_TOP1_DISAGREE")
        flags.append("shared" if ident == "SHARED_SPATIAL_REPRESENTATION" else "one_to_one")

        profiles.append({
            "row_index": j + 1,
            "julich_asset_file": mj["asset_file"],
            "julich_component_id": mj["component_id"],
            "julich_region_name": mj["region_name"],
            "julich_hemisphere": mj["hemisphere"],
            "spatial_identity_status": ident,
            "canonical_g4_descendant_count": mj["covered_canonical_count"],
            "canonical_g4_ids": ";".join(mj["canonical_g4_ids"]),
            "canonical_g4_entity_ids": ";".join(mj["canonical_g4_entity_ids"]),
            # probability x probability top1
            "pp_top1_g3_id": pp_top1["g3_id"] if pp_top1 else None,
            "pp_top1_name": pp_top1["name"] if pp_top1 else None,
            "pp_top1_joint_mass": _f(pp_top1["joint"]) if pp_top1 else None,
            "pp_top1_g4_weighted": _f(pp_top1["g4w"]) if pp_top1 else None,
            "pp_top1_g3_weighted": _f(pp_top1["g3w"]) if pp_top1 else None,
            "pp_top1_cosine": _f(pp_top1["cos"]) if pp_top1 else None,
            "pp_top1_soft_dice": _f(pp_top1["sd"]) if pp_top1 else None,
            # pp top2/3
            "pp_top2_g3_id": pp_top2["g3_id"] if pp_top2 else None,
            "pp_top2_g4_weighted": _f(pp_top2["g4w"]) if pp_top2 else None,
            "pp_top3_g3_id": pp_top3["g3_id"] if pp_top3 else None,
            "pp_top1_top2_margin": _f(pp_margin),
            "pp_top1_top2_ratio": _f(pp_ratio, 4),
            "pp_association_effective_targets": _f(eff_pp, 4),
            # hard-label coverage top1..3
            "hard_top1_g3_id": h1["g3_id"] if h1 else None,
            "hard_top1_name": h1["name"] if h1 else None,
            "hard_top1_coverage": _f(h1["cov"]) if h1 else None,
            "hard_top2_g3_id": h2["g3_id"] if h2 else None,
            "hard_top2_coverage": _f(h2["cov"]) if h2 else None,
            "hard_top3_g3_id": h3["g3_id"] if h3 else None,
            "hard_top3_coverage": _f(h3["cov"]) if h3 else None,
            "hard_top1_top2_margin": _f(hard_margin),
            "hard_top1_top2_ratio": _f(hard_ratio, 4),
            "hard_total_bna_coverage": _f(hard_total[j]),
            "bna_uncovered_fraction": _f(uncovered[j]),
            "effective_target_count": _f(eff_hard, 4),
            "top1_agreement": agreement,
            "evidence_pattern": pattern,
            "qa_flags": "|".join(flags),
            "metric_version": METRIC_VERSION,
        })
    assert len(profiles) == 414

    # row index for joins
    prof_by_row = {int(r["row_index"]): r for r in profiles}

    # ---- shared-component review ----
    shared_rows = [r for r in profiles if r["spatial_identity_status"] == "SHARED_SPATIAL_REPRESENTATION"]
    shared_leaf_ids = set()
    for r in shared_rows:
        shared_leaf_ids.update(x for x in r["canonical_g4_ids"].split(";") if x)
    shared_review = []
    for r in shared_rows:
        leaf_ids = [x for x in r["canonical_g4_ids"].split(";") if x]
        names = [canon_by_id.get(x, {}).get("g4_name", x) for x in leaf_ids]
        shared_review.append({
            "row_index": r["row_index"],
            "julich_component_id": r["julich_component_id"],
            "julich_region_name": r["julich_region_name"],
            "julich_hemisphere": r["julich_hemisphere"],
            "canonical_descendant_count": r["canonical_g4_descendant_count"],
            "canonical_g4_ids": ";".join(leaf_ids),
            "canonical_g4_names": ";".join(names),
            "pp_top1_g3_id": r["pp_top1_g3_id"], "pp_top1_name": r["pp_top1_name"],
            "pp_top1_joint_mass": r["pp_top1_joint_mass"],
            "hard_top1_g3_id": r["hard_top1_g3_id"], "hard_top1_coverage": r["hard_top1_coverage"],
            "hard_total_bna_coverage": r["hard_total_bna_coverage"],
            "bna_uncovered_fraction": r["bna_uncovered_fraction"],
            "effective_target_count": r["effective_target_count"],
            "shared_evidence_status": "SHARED_COMPONENT_LEVEL_ONLY",
            "independent_leaf_spatial_evidence": "NO_INDEPENDENT_LEAF_SPATIAL_EVIDENCE",
            "note": "single official probability map per spatial component; no finer leaf map in the 414-map official set; component-level evidence must not be duplicated across canonical leaves",
        })
    _write_csv(SHARED_REVIEW, shared_review,
               list(shared_review[0].keys()) if shared_review else ["row_index"])

    # canonical leaf accounting (one-to-one vs shared)
    canonical_id_set = set(canon_by_id.keys())
    o2o_leaves = set()
    sh_leaves = set()
    for r in profiles:
        target = sh_leaves if r["spatial_identity_status"] == "SHARED_SPATIAL_REPRESENTATION" else o2o_leaves
        target.update(x for x in r["canonical_g4_ids"].split(";") if x)
    canonical_o2o = o2o_leaves & canonical_id_set
    canonical_shared = sh_leaves & canonical_id_set
    o2o_noncanonical = o2o_leaves - canonical_id_set
    leaf_accounting = {
        "one_to_one_distinct_leaves": len(o2o_leaves),
        "one_to_one_canonical_leaf_subset": len(canonical_o2o),
        "one_to_one_noncanonical_single_leaves": sorted(o2o_noncanonical),
        "shared_distinct_canonical_leaves": len(canonical_shared),
        "shared_noncanonical_leaves": sorted(sh_leaves - canonical_id_set),
        "canonical_union_check": len(canonical_o2o | canonical_shared),
        "hypothesis_check": "gate hypothesized 24 shared components -> 50 remaining canonical leaves; measured = {0} canonical leaves (not 50) because {1} one-to-one single leaves are outside the 440-canonical registry.".format(
            len(canonical_shared), len(o2o_noncanonical)),
    }

    # ---- disagreements ----
    disag = [r for r in profiles if r["top1_agreement"] == "FALSE"]
    disag.sort(key=lambda r: -(r["pp_top1_joint_mass"] or 0.0))
    _write_csv(DISAGREE, disag, [c for c in profiles[0] if c not in ("canonical_g4_ids", "canonical_g4_entity_ids")])

    # ---- one-to-one scientific review packet (390) ----
    o2o = [r for r in profiles if r["spatial_identity_status"] == "ONE_TO_ONE_CANONICAL"]
    packet = []
    for r in sorted(o2o, key=lambda r: int(r["row_index"])):
        pr = dict(r)
        pr["scientific_decision"] = ""
        pr["decision_reason"] = ""
        packet.append(pr)
    packet_cols = [c for c in profiles[0] if c not in ("canonical_g4_entity_ids",)] + ["scientific_decision", "decision_reason"]
    _write_csv(PACKET, packet, packet_cols)
    _write_csv(PROFILES, profiles, list(profiles[0].keys()))

    # ---- empirical distributions on one-to-one (390) ----
    o2o_vals = {}
    for key in ("hard_top1_coverage", "hard_top2_coverage", "hard_total_bna_coverage",
                "bna_uncovered_fraction", "hard_top1_top2_margin",
                "pp_top1_g4_weighted", "pp_top2_g4_weighted", "pp_top1_top2_margin",
                "pp_top1_cosine", "pp_top1_soft_dice", "effective_target_count"):
        xs = [r[key] for r in o2o if r[key] is not None]
        if not xs:
            continue
        a = np.array(xs, dtype=float)
        o2o_vals[key] = {
            "min": round(float(a.min()), 6),
            "p5": round(float(np.percentile(a, 5)), 6),
            "p10": round(float(np.percentile(a, 10)), 6),
            "p25": round(float(np.percentile(a, 25)), 6),
            "median": round(float(np.median(a)), 6),
            "p75": round(float(np.percentile(a, 75)), 6),
            "p90": round(float(np.percentile(a, 90)), 6),
            "p95": round(float(np.percentile(a, 95)), 6),
            "max": round(float(a.max()), 6),
        }

    # ---- joint 2D pattern description (bins over one-to-one) ----
    def _n(pred):
        return sum(1 for r in o2o if pred(r) and r["hard_total_bna_coverage"] is not None)

    hard_top1s = [r["hard_top1_coverage"] or 0.0 for r in o2o]
    pp_top1s = [r["pp_top1_g4_weighted"] or 0.0 for r in o2o]
    try:
        from scipy.stats import spearmanr
        rho = spearmanr(hard_top1s, pp_top1s).statistic if len(hard_top1s) > 3 else None
    except Exception:
        rho = None
    joint_desc = {
        "HIGH_CONCENTRATION_CLUSTER_count": _n(lambda r: (r["hard_top1_coverage"] or 0) >= 0.7 and (r["pp_top1_g4_weighted"] or 0) >= 0.5),
        "DUAL_TARGET_BAND_count": _n(lambda r: 0.4 <= (r["hard_top1_coverage"] or 0) < 0.7 and (r["hard_top2_coverage"] or 0) >= 0.2),
        "LOW_BNA_COVERAGE_count": _n(lambda r: (r["hard_total_bna_coverage"] or 0) < 0.10),
        "AMBIGUOUS_MIDDLE_count": None,
        "spearman_hard_top1_vs_pp_top1_g4w": None if rho is None else round(float(rho), 4),
        "note": "descriptive only; not named contained/dominant/partial",
    }
    joint_desc["AMBIGUOUS_MIDDLE_count"] = sum(
        1 for r in o2o if not (r["evidence_pattern"] in ("LOW_BNA_COVERAGE",) )
        and r["hard_total_bna_coverage"] is not None
        and not ((r["hard_top1_coverage"] or 0) >= 0.7 and (r["pp_top1_g4_weighted"] or 0) >= 0.5)
        and not (0.4 <= (r["hard_top1_coverage"] or 0) < 0.7 and (r["hard_top2_coverage"] or 0) >= 0.2)
        and r["hard_total_bna_coverage"] >= 0.10)

    # ---- representative example sets A-F ----
    example_rows = []

    def _tag(tag, rows_list):
        for r in rows_list:
            e = {k: r.get(k) for k in
                 ("row_index", "julich_asset_file", "julich_region_name", "julich_hemisphere",
                  "spatial_identity_status", "pp_top1_g3_id", "pp_top1_name", "pp_top1_g4_weighted",
                  "hard_top1_g3_id", "hard_top1_coverage", "hard_total_bna_coverage",
                  "bna_uncovered_fraction", "effective_target_count", "top1_agreement",
                  "evidence_pattern")}
            e["example_set"] = tag
            example_rows.append(e)

    one = [r for r in profiles if r["spatial_identity_status"] == "ONE_TO_ONE_CANONICAL"]
    _tag("A_highest_hard_top1", sorted(one, key=lambda r: -(r["hard_top1_coverage"] or 0))[:5])
    defined = [r for r in one if r["hard_top1_coverage"] is not None and r["hard_top2_coverage"] is not None]
    _tag("B_smallest_top1_top2_margin", sorted(defined, key=lambda r: abs(r["hard_top1_top2_margin"] or 0))[:5])
    _tag("C_highest_uncovered", sorted(one, key=lambda r: -(r["bna_uncovered_fraction"] or 0))[:10])
    dis = [r for r in disag if r["spatial_identity_status"] == "ONE_TO_ONE_CANONICAL"]
    _tag("D_strongest_pp_hard_disagreement", dis[:10])
    effd = [r for r in one if r["effective_target_count"] is not None]
    _tag("E_highest_effective_targets", sorted(effd, key=lambda r: -(r["effective_target_count"] or 0))[:10])
    _tag("F_shared_spatial_component_examples", shared_rows[:10])
    ex_cols = ["example_set"] + [c for c in example_rows[0] if c != "example_set"]
    _write_csv(EXAMPLES, example_rows, ex_cols)

    # ---- threshold sensitivity (DESCRIPTIVE_ONLY) ----
    thresh_rows = []
    for cut in (0.50, 0.60, 0.70, 0.80, 0.90):
        n_all = sum(1 for r in profiles if r["hard_top1_coverage"] is not None and r["hard_top1_coverage"] >= cut)
        n_o2o = sum(1 for r in o2o if r["hard_top1_coverage"] is not None and r["hard_top1_coverage"] >= cut)
        thresh_rows.append({
            "hypothetical_cut_on_hard_top1_coverage": cut,
            "n_components_all_414": n_all,
            "n_components_one_to_one_390": n_o2o,
            "pct_all_414": round(100 * n_all / N_JUL, 2),
            "pct_one_to_one_390": round(100 * n_o2o / len(o2o), 2),
            "status": "DESCRIPTIVE_ONLY_NOT_SCIENTIFICALLY_APPROVED",
        })
    _write_csv(THRESH, thresh_rows, list(thresh_rows[0].keys()))

    # ---- summary ----
    from collections import Counter
    pattern_counts = dict(Counter(r["evidence_pattern"] for r in profiles))
    disagree_count = sum(1 for r in profiles if r["top1_agreement"] == "FALSE")
    zero_assoc_count = sum(1 for r in profiles if "NO_SPATIAL_ASSOCIATION" in (r["qa_flags"] or ""))
    gap_cand_count = sum(1 for r in profiles if "BNA_COVERAGE_GAP_CANDIDATE" in (r["qa_flags"] or ""))
    eff_nonnull = [r for r in one if r["effective_target_count"] is not None]

    summary = {
        "phase": METRIC_VERSION,
        "julich_spatial_components": 414,
        "one_to_one_julich_component_count": len(o2o),
        "shared_spatial_component_count": len(shared_rows),
        "shared_canonical_leaf_count": len(canonical_shared),
        "shared_distinct_leaf_count": len(shared_leaf_ids),
        "canonical_leaf_accounting": leaf_accounting,
        "hard_label_transform": label_prov,
        "role_of_evidence": {
            "primary": "Julich probability x Brainnetome probability (cross-atlas spatial association; NOT a partition; g4_mass_weighted_g3 is not '% of G4 belonging to G3')",
            "auxiliary": "hard-label coverage of G4 mass inside BN_Atlas_246_1mm parcels (containment interpretability only)",
        },
        "empirical_distribution_one_to_one_390": o2o_vals,
        "joint_2d_pattern": joint_desc,
        "top1_agreement_count": sum(1 for r in profiles if r["top1_agreement"] == "TRUE"),
        "top1_disagreement_count": disagree_count,
        "top1_na_count": sum(1 for r in profiles if r["top1_agreement"] == "NA"),
        "zero_association_count": zero_assoc_count,
        "zero_association_rows": [r["row_index"] for r in profiles if r["pp_top1_g3_id"] is None],
        "coverage_gap_candidate_count": gap_cand_count,
        "coverage_gap_candidate_rows": [{"row_index": r["row_index"], "asset": r["julich_asset_file"],
                                         "hard_total": r["hard_total_bna_coverage"],
                                         "uncovered": r["bna_uncovered_fraction"]}
                                        for r in profiles if "BNA_COVERAGE_GAP_CANDIDATE" in (r["qa_flags"] or "")],
        "evidence_pattern_counts": pattern_counts,
        "evidence_strata_are_descriptive_only": True,
        "classification_thresholds": "NOT_DEFINED",
        "scientific_decisions_created": False,
        "shared_component_hierarchy_split": "NO_INDEPENDENT_LEAF_SPATIAL_EVIDENCE (single official probability map per component; no finer/hemisphere-child map in the 414-map official set)",
        "threshold_sensitivity_table": "g4_g3_threshold_sensitivity_table.csv (DESCRIPTIVE_ONLY)",
        "recorded": datetime.now(timezone.utc).isoformat(),
    }
    # Phase 2G matrix hash cross-check (Phase 2G artifact is never rewritten here)
    try:
        g2g = json.loads((INT / "g4_g3_probability_overlap_summary.json").read_text(encoding="utf-8"))
        summary["phase2g_matrix_hash"] = g2g["matrix_hash"]
    except Exception:
        summary["phase2g_matrix_hash"] = None
    _atomic_write(SUMMARY, lambda p: p.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8"))

    print(f"[2H] one_to_one={len(o2o)} shared={len(shared_rows)} shared_canonical_leaves={len(canonical_shared)} "
          f"(o2o_canonical={len(canonical_o2o)} o2o_noncanonical={len(o2o_noncanonical)} union={len(canonical_o2o | canonical_shared)})")
    print(f"[2H] disagreements={disagree_count} zero_assoc={zero_assoc_count} gap_cand={gap_cand_count}")
    print("[2H] patterns:", pattern_counts)
    print("[2H] artifacts written to", INT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
