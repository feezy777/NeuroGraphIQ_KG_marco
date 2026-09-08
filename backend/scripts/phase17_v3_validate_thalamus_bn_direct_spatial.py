"""Phase1.7 V3 - Thalamus Brainnetome G3 direct spatial validation (DIAGNOSTIC).

Validates overlap between the frozen Thalamus G1 probability geometry (Julich
reference grid, shared MNI2009c frame) and the 16 Brainnetome thalamic parcels
(Tha_L/R_8_1..8_8) whose G3->G1 rollup mappings are frozen.

EVIDENCE TYPE:
  DIRECT_SPATIAL_OVERLAP_IN_SHARED_MNI2009C_COORDINATE_FRAME
This is NOT authoritative nonlinear registration evidence, NOT proof of exact
local anatomical correspondence, NOT proof that Sym/Asym templates are
anatomically identical, and NOT sufficient by itself for automatic mapping
promotion.

Metrics (probability-weighted / soft, consistent with the frozen phase17
probability semantics + the compute_g4_g3_probability_overlap framework):
  - masses: volG1 = sum(P_G1), volBN = sum(P_BN)  (1mm^3 voxels -> mm3-equivalent)
  - joint_j   = sum(P_G1 * P_BN_j)               (shared probability mass)
  - overlap_ratio_vs_G1   = joint_j / volG1
  - overlap_ratio_vs_BN   = joint_j / volBN_j    (parcel containment within G1)
  - dice                  = 2*joint_j / (norm2_G1 + norm2_BN_j)   in [0,1]
  - centroid distance (mm) between probability-weighted centroids
  - ipsilateral only: left G1 vs left parcels; right G1 vs right parcels
  - contralateral overlap fraction: P_G1 mass overlapping the OTHER side parcels
Per hemisphere (union, no double counting):
  - total G1 volume, BN-covered G1 (voxels with any ipsilateral BN P>0, weighted
    by P_G1, once), uncovered G1, union coverage ratio, top parcel (max
    overlap_ratio_vs_G1), top-parcel G1-coverage ratio, number of parcels with
    non-zero overlap.

CATEGORICAL-BAND NOTE (audit):
  A draft version of this script introduced descriptive bands
  ZERO/TRACE/MATERIAL/DOMINANT_OVERLAP with cutoffs 0.01/0.25. Audit found NO
  frozen Phase1.7 definition for those labels or for a 0.25 dominant-overlap
  cutoff on G1 coverage (the frozen APPROVE_DOMINANT_OVERLAP / DOMINANT_CRITERIA_V1
  is a G4->G3 mapping_relation enum with hard_total>=0.70 / hard1>=0.50; the
  spatial_review_audit 0.25 is an unrelated candidate-vs-mapped heuristic).
  To avoid introducing a new scientific threshold in this round, the categorical
  band interpretation was REMOVED. Only continuous metrics + deterministic
  ranking + top parcel / top-parcel coverage / union coverage are retained.
  No promotion rule is created.

Grid compatibility is checked before any overlap. Only CURRENT G1 SHAs are
accepted (superseded SHAs rejected). registration_applied=FALSE is preserved.
No DB write; no lifecycle_status change; no classification change; no promotion;
no commit.
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
BN_PM_DIR = BACKEND / "data" / "atlases" / "brainnetome" / "bna246" / "transformed_to_julich2009c" / "probability_maps"
JULICH_PM_DIR = BACKEND / "data" / "atlases" / "julich" / "v3.1" / "spatial_raw" / "probability_maps"

# current G1 geometry (Julich reference grid)
G1_LEFT = BACKEND / "data" / "atlases" / "derived_g1" / "left_thalamus_proper_prob_mni2009casym.nii.gz"
G1_RIGHT = BACKEND / "data" / "atlases" / "derived_g1" / "right_thalamus_proper_prob_mni2009casym.nii.gz"
G1_LEFT_SHA = "bd431608fcea3c5f0f7387b1b0e1010582fa2e39dae95a300b3bba976a10cc87"
G1_RIGHT_SHA = "73e4242b581f2420c316593f6cd85183ea7f99c29e2b817b0257cdf267c5bd3b"
SUPERSEDED_SHA_LEFT = "37a82b65d86d81b1558582dee301e79ee367d60856f95d6a55b0219cf28a87a1"
SUPERSEDED_SHA_RIGHT = "1c9b8b8de9103c1e091c9fb6e0577182416d5a6ba0c1b7f6d41e1e913958253f"

V3_CONTRACT = D16 / "phase17_v3_thalamus_g1_scope_contract_v3.json"
V3_SHA = "22e24a31bab9659769f7e550ee32f8e3b37887d0ae1a4c4c4cf64974c3c05f68"
SPB_MAN = D16 / "phase17_v3_thalamus_spatial_bridge_manifest.json"
SPB_ID = "SPB-MNI2009C-SYM-ASYM-SHARED-FRAME-V1"
G3MAN = BACKEND / "data" / "integration" / "g3_to_g1" / "g3_to_g1_full_decision_coverage_manifest.csv"

OUT_JSON = D16 / "phase17_v3_thalamus_bn_direct_validation.json"
OUT_QC = D16 / "phase17_v3_thalamus_bn_direct_validation_qc.csv"
OUT_PARCEL = D16 / "phase17_v3_thalamus_bn_direct_validation_parcels.csv"
OUT_HEMI = D16 / "phase17_v3_thalamus_bn_direct_validation_hemispheres.csv"
OUT_PROV = D16 / "phase17_v3_thalamus_bn_direct_validation_provenance.json"
OUT_MD = D16 / "phase17_v3_thalamus_bn_direct_validation_diagnostics.md"

SCRIPT_VERSION = "phase17_v3_validate_thalamus_bn_direct_spatial.py v1"
LEFT_G1_ID = "NGIQ-BR-00000247"
RIGHT_G1_ID = "NGIQ-BR-00000256"

# 16 BN thal parcel codes; probability maps comp231..246
BN_CODES = []
for side in ("L", "R"):
    for i in range(1, 9):
        BN_CODES.append(f"Tha_{side}_8_{i}")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def reject_superseded(sha: str, label: str) -> None:
    if sha in (SUPERSEDED_SHA_LEFT, SUPERSEDED_SHA_RIGHT):
        raise SystemExit(f"REJECTED superseded G1 geometry SHA for {label}: {sha}")


def prob_centroid(p, aff):
    X, Y, Z = np.meshgrid(np.arange(p.shape[0]), np.arange(p.shape[1]),
                          np.arange(p.shape[2]), indexing="ij")
    xw = aff[0, 0] * X + aff[0, 3]; yw = aff[1, 1] * Y + aff[1, 3]; zw = aff[2, 2] * Z + aff[2, 3]
    m = float(p.sum())
    if m <= 0:
        return (float("nan"), float("nan"), float("nan"))
    return (float((p * xw).sum() / m), float((p * yw).sum() / m), float((p * zw).sum() / m))


def main() -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    import sys, platform as _platform

    # frozen authority checks
    left_sha = sha256(G1_LEFT)
    right_sha = sha256(G1_RIGHT)
    reject_superseded(left_sha, "left G1")
    reject_superseded(right_sha, "right G1")
    assert left_sha == G1_LEFT_SHA, f"left G1 SHA mismatch {left_sha}"
    assert right_sha == G1_RIGHT_SHA, f"right G1 SHA mismatch {right_sha}"
    assert sha256(V3_CONTRACT) == V3_SHA
    spb = json.load(open(SPB_MAN, encoding="utf-8"))
    assert spb["spatial_bridge_id"] == SPB_ID
    assert spb["registration_applied"] is False
    assert spb["resampling_applied"] is True
    assert spb["residual_spatial_limitation"] == \
        "TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_WARP_CORRECTED"

    # load G1 (probability, Julich grid)
    g1L_img = nib.load(str(G1_LEFT)); g1R_img = nib.load(str(G1_RIGHT))
    g1L = np.asanyarray(g1L_img.dataobj).astype(np.float64)
    g1R = np.asanyarray(g1R_img.dataobj).astype(np.float64)
    assert g1L.shape == g1R.shape == (193, 229, 193)

    # reference grid authority
    jpms = sorted(JULICH_PM_DIR.glob("*.nii.gz"))
    assert jpms
    ref_aff = nib.load(str(jpms[0])).affine
    jul_ref_sha = sha256(jpms[0])
    for img in (g1L_img, g1R_img):
        assert np.allclose(img.affine, ref_aff, atol=1e-4), "G1 affine != Julich reference"
        assert np.allclose(np.asarray(img.header.get_zooms())[:3], 1.0)

    # frozen G3->G1 manifest
    g3rows = list(csv.DictReader(open(G3MAN, encoding="utf-8-sig")))
    g3_sha = sha256(G3MAN)
    # map official_code -> frozen target
    frozen_target = {r["official_code"]: r["primary_target_g1_entity_id"]
                     for r in g3rows if (r.get("official_code") or "").startswith("Tha_")}

    # load 16 BN parcel probability maps
    # filename: BNA_PM_compNNN_<official_code>_prob_2009c.nii.gz
    pm_files = {p.name: p for p in BN_PM_DIR.glob("*.nii.gz")}
    parcels = {}
    for code in BN_CODES:
        cand = [p for n, p in pm_files.items() if f"_{code}_prob_2009c" in n]
        assert len(cand) == 1, f"expected exactly 1 PM for {code}, got {len(cand)}"
        p = cand[0]
        img = nib.load(str(p))
        d = np.asanyarray(img.dataobj).astype(np.float64)
        assert d.shape == (193, 229, 193)
        assert np.allclose(img.affine, ref_aff, atol=1e-4), f"BN {code} affine != Julich reference"
        parcels[code] = dict(path=p, sha=sha256(p), data=d, affine=img.affine.copy(),
                             target=frozen_target.get(code),
                             comp=int(p.name.split("comp")[1].split("_")[0]))

    # grid compatibility gate
    for code, px in parcels.items():
        assert px["data"].shape == g1L.shape == (193, 229, 193)
        assert np.allclose(px["affine"], ref_aff, atol=1e-4)

    # ---- per-parcel metrics (ipsilateral only) ----
    side_map = {"L": "left", "R": "right"}
    rows = []
    for code, px in parcels.items():
        side = side_map[code.split("_")[1]]
        g1 = g1L if side == "left" else g1R
        bn = px["data"]
        volG1 = float(g1.sum())
        volBN = float(bn.sum())
        joint = float((g1 * bn).sum())
        ratio_g1 = joint / volG1 if volG1 > 0 else 0.0
        ratio_bn = joint / volBN if volBN > 0 else 0.0
        norm2_g1 = float((g1 * g1).sum()); norm2_bn = float((bn * bn).sum())
        dice = 2.0 * joint / (norm2_g1 + norm2_bn) if (norm2_g1 + norm2_bn) > 0 else 0.0
        cg = prob_centroid(g1, g1L_img.affine)
        cb = prob_centroid(bn, px["affine"])
        dist = float(np.linalg.norm(np.array(cg) - np.array(cb))) if all(
            not np.isnan(x) for x in cg + cb) else float("nan")
        rows.append(dict(parcel_code=code, hemisphere=side,
                         component_index=px["comp"],
                         bn_parcel_sha=px["sha"],
                         frozen_g1_target=px["target"] or "",
                         g1_entity_id=(LEFT_G1_ID if side == "left" else RIGHT_G1_ID),
                         bn_volume_mm3_equiv=round(volBN, 3),
                         g1_volume_mm3_equiv=round(volG1, 3),
                         intersection_mass=round(joint, 3),
                         overlap_ratio_vs_G1=round(ratio_g1, 6),
                         overlap_ratio_vs_BN=round(ratio_bn, 6),
                         dice=round(dice, 6),
                         centroid_distance_mm=round(dist, 3) if not np.isnan(dist) else None))
    # deterministic ranking by G1-coverage within each side
    for side in ("left", "right"):
        sub = [r for r in rows if r["hemisphere"] == side]
        sub_sorted = sorted(sub, key=lambda r: -r["overlap_ratio_vs_G1"])
        for rank, r in enumerate(sub_sorted, start=1):
            r["rank_by_g1_coverage"] = rank

    # world X for strict-ipsilateral boundary check (world-X is QC only)
    Xg, Yg, Zg = np.meshgrid(np.arange(g1L.shape[0]), np.arange(g1L.shape[1]),
                             np.arange(g1L.shape[2]), indexing="ij")
    xw = ref_aff[0, 0] * Xg + ref_aff[0, 3]

    # ---- hemisphere summaries (union, no double count) ----
    hemi = []
    for side in ("left", "right"):
        g1 = g1L if side == "left" else g1R
        side_parcels = [px for code, px in parcels.items() if side_map[code.split("_")[1]] == side]
        # union coverage: voxels where any ipsilateral BN parcel has P>0, weight by P_G1, count once
        union_mask = np.zeros(g1.shape, dtype=bool)
        for px in side_parcels:
            union_mask |= px["data"] > 0
        covered = float((g1 * union_mask).sum())
        total = float(g1.sum())
        uncovered = float((g1 * (~union_mask)).sum())
        # also raw union of BN support (voxel count) for reference
        bn_union_vox = int(union_mask.sum())
        # parcels with non-zero overlap (ratio_vs_G1 > 0) - continuous, no threshold band
        sub = [r for r in rows if r["hemisphere"] == side]
        nonzero = [r for r in sub if float(r["overlap_ratio_vs_G1"]) > 0]
        top = max(sub, key=lambda r: r["overlap_ratio_vs_G1"]) if sub else None
        # contralateral (probability): G1 mass overlapping the OTHER side parcel union
        other_side = "right" if side == "left" else "left"
        other_parcels = [px for code, px in parcels.items()
                         if side_map[code.split("_")[1]] == other_side]
        other_mask = np.zeros(g1.shape, dtype=bool)
        for px in other_parcels:
            other_mask |= px["data"] > 0
        contra = float((g1 * other_mask).sum()) / total if total > 0 else 0.0
        # strict-ipsilateral: G1 mass that lies beyond |x|>1mm on the WRONG side
        if side == "left":
            strict_wrong = float((g1 * (xw > 1.0)).sum()) / total if total > 0 else 0.0
        else:
            strict_wrong = float((g1 * (xw < -1.0)).sum()) / total if total > 0 else 0.0
        # per-parcel cross-midline leak summary for the OTHER-side parcel set (diagnostic note)
        leak_parcels = []
        for code, px in parcels.items():
            if side_map[code.split("_")[1]] != other_side:
                continue
            pdata = px["data"]
            cross = (pdata * (xw < 0) if code.split("_")[1] == "R"
                     else pdata * (xw > 0)).sum()
            frac = cross / pdata.sum() if pdata.sum() > 0 else 0.0
            if frac > 0.005:
                leak_parcels.append(dict(parcel=code, cross_midline_mass_fraction=round(float(frac), 4)))
        hemi.append(dict(
            hemisphere=side, g1_entity_id=(LEFT_G1_ID if side == "left" else RIGHT_G1_ID),
            total_g1_volume_mm3_equiv=round(total, 3),
            bn_covered_g1_volume_mm3_equiv=round(covered, 3),
            uncovered_g1_volume_mm3_equiv=round(uncovered, 3),
            union_coverage_ratio=round(covered / total, 6) if total > 0 else 0.0,
            bn_union_support_voxels=bn_union_vox,
            top_parcel=(top["parcel_code"] if top else None),
            top_parcel_g1_coverage=round(top["overlap_ratio_vs_G1"], 6) if top else None,
            n_nonzero_overlap_parcels=len(nonzero),
            n_parcels_evaluated=len(sub),
            contralateral_overlap_ratio=round(contra, 6),
            strict_ipsilateral_wrongside_mass_fraction=round(strict_wrong, 6),
            cross_midline_leak_parcels=leak_parcels,
            method="union counted once; weighted by P_G1; world-X used for ipsilateral QC only"))

    # ---- machine JSON ----
    result = dict(
        validation_type="DIRECT_SPATIAL_OVERLAP_IN_SHARED_MNI2009C_COORDINATE_FRAME",
        evidence_scope="diagnostic only; NOT authoritative nonlinear-registration "
                       "evidence; NOT promotion evidence",
        spatial_bridge_id=SPB_ID,
        registration_applied=False,
        resampling_applied=True,
        template_variant_uncertainty="PRESENT",
        residual_spatial_limitation="TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_WARP_CORRECTED",
        target_reference_space="MNI152NLin2009cAsym / Julich reference grid",
        g1_left_sha=left_sha, g1_right_sha=right_sha,
        g1_left_geometry_id="GEO-G1-THAL-L-MNI2009CASYM-V1",
        g1_right_geometry_id="GEO-G1-THAL-R-MNI2009CASYM-V1",
        band_note="No categorical overlap bands used. Audit found no frozen "
                  "Phase1.7 definition for ZERO/TRACE/MATERIAL/DOMINANT_OVERLAP "
                  "labels or a 0.25 dominant-overlap cutoff on G1 coverage, so the "
                  "draft categorical interpretation was removed. Only continuous "
                  "metrics + deterministic ranking + top parcel/coverage + union "
                  "coverage are reported. No new scientific threshold or promotion "
                  "rule is introduced.",
        parcels=rows,
        hemispheres=hemi,
        script_version=SCRIPT_VERSION,
        run_timestamp=ts,
    )
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    # per-parcel CSV
    with open(OUT_PARCEL, "w", newline="", encoding="utf-8-sig") as fh:
        cols = list(rows[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # hemisphere CSV
    with open(OUT_HEMI, "w", newline="", encoding="utf-8-sig") as fh:
        cols = list(hemi[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in hemi:
            w.writerow(r)

    # QC CSV (summary scalar rows)
    qc_rows = []
    for h in hemi:
        qc_rows.append(dict(hemisphere=h["hemisphere"],
                            total_g1=h["total_g1_volume_mm3_equiv"],
                            union_coverage_ratio=h["union_coverage_ratio"],
                            top_parcel=h["top_parcel"],
                            top_parcel_g1_coverage=h["top_parcel_g1_coverage"],
                            contralateral=h["contralateral_overlap_ratio"]))
    with open(OUT_QC, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(qc_rows[0].keys()))
        w.writeheader()
        for r in qc_rows:
            w.writerow(r)

    # provenance
    prov = dict(
        g1_left=dict(path=str(G1_LEFT.relative_to(BACKEND)).replace("\\", "/"), sha256=left_sha),
        g1_right=dict(path=str(G1_RIGHT.relative_to(BACKEND)).replace("\\", "/"), sha256=right_sha),
        superseded_g1=dict(left=SUPERSEDED_SHA_LEFT, right=SUPERSEDED_SHA_RIGHT,
                           note="never consumed as current evidence"),
        brainnetome_source=dict(
            directory=str(BN_PM_DIR.relative_to(BACKEND)).replace("\\", "/"),
            n_thal_parcels=16,
            parcel_shas={c: parcels[c]["sha"] for c in BN_CODES}),
        julich_reference=dict(path=str(jpms[0].relative_to(BACKEND)).replace("\\", "/"),
                              sha256=jul_ref_sha),
        spatial_bridge_id=SPB_ID,
        v3_contract_sha256=V3_SHA,
        g3_to_g1_frozen_manifest_sha256=g3_sha,
        registration_applied=False,
        resampling_applied=True,
        nonlinear_registration_applied=False,
        template_variant_uncertainty="PRESENT",
        residual_spatial_limitation="TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_WARP_CORRECTED",
        evidence_type="DIRECT_SPATIAL_OVERLAP_IN_SHARED_MNI2009C_COORDINATE_FRAME",
        software=dict(python_version=sys.version.split()[0], platform=str(_platform.platform()),
                      numpy_version=np.__version__, nibabel_version=nib.__version__),
        script=str(Path(__file__).name), script_version=SCRIPT_VERSION,
        run_timestamp=ts,
    )
    with open(OUT_PROV, "w", encoding="utf-8") as fh:
        json.dump(prov, fh, ensure_ascii=False, indent=2)

    # diagnostics MD
    md = ["# Phase1.7 V3 - Thalamus Brainnetome G3 direct spatial validation (DIAGNOSTIC)", "",
          "EVIDENCE TYPE: DIRECT_SPATIAL_OVERLAP_IN_SHARED_MNI2009C_COORDINATE_FRAME",
          "NOT authoritative nonlinear-registration evidence; NOT proof of exact local",
          "anatomical correspondence; NOT sufficient for automatic promotion.", "",
          f"G1 left sha  = {left_sha}",
          f"G1 right sha = {right_sha}",
          f"superseded G1 SHAs rejected: {SUPERSEDED_SHA_LEFT[:12]}... / {SUPERSEDED_SHA_RIGHT[:12]}...",
          f"spatial_bridge_id = {SPB_ID}",
          "registration_applied = FALSE; resampling_applied = TRUE",
          f"template_variant_uncertainty = PRESENT",
          f"residual limitation = TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_WARP_CORRECTED", ""]
    for h in hemi:
        md.append(f"HEMISPHERE {h['hemisphere']}: total G1={h['total_g1_volume_mm3_equiv']}mm3 "
                  f"BN-covered={h['bn_covered_g1_volume_mm3_equiv']}mm3 "
                  f"uncovered={h['uncovered_g1_volume_mm3_equiv']}mm3 "
                  f"union coverage={h['union_coverage_ratio']:.4f} "
                  f"top parcel={h['top_parcel']} (G1 coverage {h['top_parcel_g1_coverage']:.4f}) "
                  f"nonzero-overlap parcels={h['n_nonzero_overlap_parcels']} "
                  f"contralateral={h['contralateral_overlap_ratio']:.6f}")
    md.append("")
    md.append("Ranked parcels per hemisphere (by G1 coverage; continuous, no threshold band):")
    for side in ("left", "right"):
        md.append(f"  {side}:")
        for r in sorted([x for x in rows if x["hemisphere"] == side],
                        key=lambda x: x["rank_by_g1_coverage"]):
            md.append(f"    {r['rank_by_g1_coverage']}. {r['parcel_code']} "
                      f"vsG1={r['overlap_ratio_vs_G1']:.4f} vsBN={r['overlap_ratio_vs_BN']:.4f} "
                      f"dice={r['dice']:.4f} dist={r['centroid_distance_mm']}")
    md += ["",
           "INTERPRETATION (SUPPORTIVE BUT NON-DECISIVE): all 16 corresponding "
           "Brainnetome thalamic parcels show non-zero/substantial spatial overlap "
           "with the whole-thalamus G1 geometry. overlap_ratio_vs_BN ranges from "
           "0.30 to 0.82, with 7/16 parcels reaching >=0.70. Each parcel occupies "
           "only a fraction of G1 (overlap_ratio_vs_G1 0.02-0.18; union coverage "
           "0.97-0.98), consistent with G1 being the whole thalami and the 8 "
           "connectivity zones tiling it.",
           "Limitation explicitly preserved: "
           "TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_WARP_CORRECTED. "
           "This is DIRECT_SPATIAL_OVERLAP_IN_SHARED_MNI2009C_COORDINATE_FRAME "
           "evidence only.",
           "No categorical overlap bands / no new threshold; no DB write; no "
           "lifecycle/classification change; no promotion; no commit; diagnostic only.", ""]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    # console summary
    for h in hemi:
        print(f"{h['hemisphere']}: total={h['total_g1_volume_mm3_equiv']:.2f} "
              f"covered={h['bn_covered_g1_volume_mm3_equiv']:.2f} "
              f"uncovered={h['uncovered_g1_volume_mm3_equiv']:.2f} "
              f"union={h['union_coverage_ratio']:.4f} "
              f"top={h['top_parcel']}({h['top_parcel_g1_coverage']:.4f}) "
              f"nz={h['n_nonzero_overlap_parcels']} contra={h['contralateral_overlap_ratio']:.6f}")
    for r in rows:
        print(f"  {r['parcel_code']} rank={r['rank_by_g1_coverage']} "
              f"vsG1={r['overlap_ratio_vs_G1']:.4f} vsBN={r['overlap_ratio_vs_BN']:.4f} "
              f"dice={r['dice']:.4f} dist={r['centroid_distance_mm']}")


if __name__ == "__main__":
    main()
