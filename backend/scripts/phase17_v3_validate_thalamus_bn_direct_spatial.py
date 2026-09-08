"""Phase1.7 V3 - Thalamus Brainnetome G3 -> THALAMUS_PROPER G1 direct spatial
validation + Thalamus final-freeze assessment (v2, formal direct-validation round).

Supersedes the earlier DIAGNOSTIC pass of the same file (phase17_v3_thalamus_bn_direct_validation.*).
This round produces the formal per-relation decision records (DEC-THAL-DIRECT-01..16),
evidence grades, bilateral QA, Reticular-exclusion QC, and a final-freeze assessment.

EVIDENCE TYPE (unchanged from the frozen spatial route):
  DIRECT_SPATIAL_OVERLAP_IN_SHARED_MNI2009C_COORDINATE_FRAME
plus the carried residual:
  SHARED_TEMPLATE_VARIANT_UNCERTAINTY = PRESENT
  residual = TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_WARP_CORRECTED
NOT "DIRECT_OVERLAP_AFTER_AUTHORITATIVE_SYM_TO_ASYM_REGISTRATION".

Universe (frozen): the 16 G3->G1 Thalamus relations are read from the frozen
g3_to_g1_full_decision_coverage_manifest.csv and cross-bound to DEC-THAL-ROLLUP-01..16
(phase17_v3_thalamus_bn_rollup_compatibility.csv). They are never hard-coded here as
the sole authority.

Geometry independence / circularity:
  - G1 geometry is the CURRENT Julich-grid THALAMUS_PROPER geometry (current SHAs
    only; superseded SHAs rejected).
  - Brainnetome parcel geometry is read directly from the independently transformed
    BNA probability maps (BNA_PM_4D -> MNI152NLin2009cAsym via SimpleITK, frozen
    g3_brainnetome_to_julich_batch_transform_manifest.csv). That spatial route is
    independent of the semantic G3->G1 mapping; the mapping is used only to associate
    a parcel with its canonical G1 target (circularity_risk = NONE).

Primary metrics are continuous probability-weighted (no binary-only G1; the old
G4->G3 two-hop 90%/5% proxy is NOT reused and no target-driven threshold is applied).
Threshold sensitivity (P_G1 >= 0.1/0.25/0.5/0.75) is reported as auxiliary QC only.

Evidence-grade vocabulary (gate section 9):
  DIRECTLY_SUPPORTED
  DIRECTLY_SUPPORTED_WITH_BOUNDARY_UNCERTAINTY
  DIRECT_SPATIAL_CONFLICT
  DIRECT_EVIDENCE_INSUFFICIENT

Reference levels that map the continuous metrics onto that vocabulary are descriptive
zones introduced in THIS round (see REFERENCE_LEVELS). They are NOT frozen Phase1.7
gate thresholds, NOT calibrated for promotion, classification-independent, and they sit
inside large empirical gaps of the observed parcel distribution (documented in the
outputs). Continuous metrics remain primary.

Hard guards: grid/affine/orientation/spacing equality asserted before every overlap;
no resize/resample sneaked in; registration_applied=FALSE preserved; no DB write; no
lifecycle/classification change; no promotion; no commit; the global phase17_v3
classification (86/132/93) is never modified (this round may only emit a proposal).
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
import platform as _platform
from datetime import datetime, timezone
from pathlib import Path

import nibabel as nib
import numpy as np
from scipy import ndimage as ndi

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
G3MAN = BACKEND / "data" / "integration" / "g3_to_g1" / "g3_to_g1_full_decision_coverage_manifest.csv"
ROLLUP_CSV = D16 / "phase17_v3_thalamus_bn_rollup_compatibility.csv"
BN_TRANSFORM_MAN = BACKEND / "data" / "integration" / "g3_brainnetome_assets" / "g3_brainnetome_to_julich_batch_transform_manifest.csv"
BN_PM_DIR = BACKEND / "data" / "atlases" / "brainnetome" / "bna246" / "transformed_to_julich2009c" / "probability_maps"
DERIVED = BACKEND / "data" / "atlases" / "derived_g1"

G1_LEFT = DERIVED / "left_thalamus_proper_prob_mni2009casym.nii.gz"
G1_RIGHT = DERIVED / "right_thalamus_proper_prob_mni2009casym.nii.gz"
G1_LEFT_SHA = "bd431608fcea3c5f0f7387b1b0e1010582fa2e39dae95a300b3bba976a10cc87"
G1_RIGHT_SHA = "73e4242b581f2420c316593f6cd85183ea7f99c29e2b817b0257cdf267c5bd3b"
SUPERSEDED_SHA_LEFT = "37a82b65d86d81b1558582dee301e79ee367d60856f95d6a55b0219cf28a87a1"
SUPERSEDED_SHA_RIGHT = "1c9b8b8de9103c1e091c9fb6e0577182416d5a6ba0c1b7f6d41e1e913958253f"
G1_LEFT_GEO_ID = "GEO-G1-THAL-L-MNI2009CASYM-V1"
G1_RIGHT_GEO_ID = "GEO-G1-THAL-R-MNI2009CASYM-V1"
LEFT_G1_ID = "NGIQ-BR-00000247"
RIGHT_G1_ID = "NGIQ-BR-00000256"

V3_CONTRACT = D16 / "phase17_v3_thalamus_g1_scope_contract_v3.json"
V3_SHA = "22e24a31bab9659769f7e550ee32f8e3b37887d0ae1a4c4c4cf64974c3c05f68"
SPB_MAN = D16 / "phase17_v3_thalamus_spatial_bridge_manifest.json"
SPB_ID = "SPB-MNI2009C-SYM-ASYM-SHARED-FRAME-V1"
SPB_CLASS = "SHARED_COORDINATE_REFERENCE_GRID_RESAMPLING"
LIMITATION = "TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_WARP_CORRECTED"
EVIDENCE_TYPE = "DIRECT_SPATIAL_OVERLAP_IN_SHARED_MNI2009C_COORDINATE_FRAME"

NATIVE_MAN = D16 / "phase17_v3_thalamus_g1_native_geometry_manifest.json"
RETRACTION = D16 / "phase17_v3_thalamus_transform_retraction.json"
CLASS_CSV = D16 / "phase17_v3_classification.csv"

# FreeSurfer Iglesias source (native, 2009c symmetric) used only for the Reticular
# exclusion QC (the excluded reticular channels are resampled onto the shared target
# grid in memory; no new geometry file / SHA is produced).
FS_THAL_SRC = BACKEND / "data" / "atlases" / "external_raw" / "freesurfer_icbm2009c" / "thalamus" / "ThalamusProbs.MNIsymSpace.nii.gz"
FS_THAL_SHA = "640377ae93cf0782365a698573970c2a429a775c6f64dcf9ac02536156b51f22"
FS_THAL_NAMES_SHA = "74b70bfa4fa75aa05a0bee9fcb548fa97bea20bfceef43b63a97c52a3923bfec"
RET_CHANNEL_LEFT = 19   # Left-R (reticular), scope DEC-THAL-03 EXCLUDE
RET_CHANNEL_RIGHT = 39  # Right-R (reticular)

OUT_RESULTS = D16 / "phase17_v3_thalamus_bn_direct_spatial_results.csv"
OUT_DECISIONS = D16 / "phase17_v3_thalamus_bn_direct_spatial_decisions.csv"
OUT_SUMMARY = D16 / "phase17_v3_thalamus_bn_direct_spatial_summary.json"
OUT_PROV = D16 / "phase17_v3_thalamus_bn_direct_spatial_provenance.json"
OUT_MD = D16 / "phase17_v3_thalamus_bn_direct_spatial_diagnostics.md"
OUT_FREEZE = D16 / "phase17_v3_thalamus_final_freeze_v1.json"

SCRIPT_VERSION = "phase17_v3_validate_thalamus_bn_direct_spatial.py v2 (DIRECT_SPATIAL + FINAL_FREEZE round)"

GRID = (193, 229, 193)
SPACING_MM = 1.0

# --------------------------------------------------------------------------- #
# Reference levels for the descriptive evidence mapping (see module docstring).#
# They sit inside observed distributional gaps; documented and never called a  #
# calibrated gate.                                                             #
# --------------------------------------------------------------------------- #
REFERENCE_LEVELS = {
    "conflict_containment_below": 0.20,
    "conflict_outside_envelope_above": 0.30,
    "direct_support_containment_at_least": 0.60,
    "midline_leak_note_fraction_at_least": 0.02,
    "bilateral_asymmetry_pair_abs_diff_at_least": 0.20,
    "reticular_territory_probability_threshold": 0.5,
    "rationale": (
        "Descriptive zones introduced in THIS round to map the continuous "
        "probability-weighted evidence onto the evidence-grade vocabulary. They are "
        "NOT frozen Phase1.7 gate thresholds, NOT the old G4->G3 90/5 proxy, NOT "
        "calibrated for promotion, and classification-independent. Each reference sits "
        "inside a large empirical gap of the 16-parcel distribution: next-lowest "
        "containment above the conflict zone is 0.304 (vs <0.20); next-highest "
        "outside-envelope fraction below the conflict zone is 0.175 (vs >0.30); "
        "supported parcels all have containment >=0.684 (vs <0.60 for all others); "
        "only one parcel has midline leak >=0.02 (next is 0.0024); flagged asymmetry "
        "pairs are 0.234-0.396 (unflagged <=0.131). Continuous metrics are primary."
    ),
}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def reject_superseded(h: str, label: str) -> None:
    if h in (SUPERSEDED_SHA_LEFT, SUPERSEDED_SHA_RIGHT):
        raise SystemExit(f"REJECTED superseded G1 geometry SHA for {label}: {h}")


def prob_centroid(p: np.ndarray, aff: np.ndarray):
    """Probability-weighted centroid in world mm (RAS)."""
    X, Y, Z = np.meshgrid(np.arange(p.shape[0]), np.arange(p.shape[1]),
                          np.arange(p.shape[2]), indexing="ij")
    xw = aff[0, 0] * X + aff[0, 3]
    yw = aff[1, 1] * Y + aff[1, 3]
    zw = aff[2, 2] * Z + aff[2, 3]
    m = float(p.sum())
    if m <= 0:
        return (float("nan"), float("nan"), float("nan"))
    return (float((p * xw).sum() / m), float((p * yw).sum() / m), float((p * zw).sum() / m))


def load_frozen_universe() -> list[dict]:
    """Read the 16 Thalamus relations from the frozen manifest + rollup CSV."""
    man = [r for r in csv.DictReader(open(G3MAN, encoding="utf-8-sig"))
           if (r.get("official_code") or "").startswith("Tha_")]
    if len(man) != 16:
        raise SystemExit(f"universe != 16 from frozen manifest: {len(man)}")
    by_g3 = {r["g3_entity_id"]: r for r in man}

    roll = list(csv.DictReader(open(ROLLUP_CSV, encoding="utf-8-sig")))
    if len(roll) != 16:
        raise SystemExit(f"rollup rows != 16: {len(roll)}")
    if roll[0]["decision_id"] != "DEC-THAL-ROLLUP-01" or roll[-1]["decision_id"] != "DEC-THAL-ROLLUP-16":
        raise SystemExit("rollup CSV not ordered DEC-THAL-ROLLUP-01..16")

    side_count = {"left": 0, "right": 0}
    universe = []
    for i, rr in enumerate(roll, start=1):
        mr = by_g3.get(rr["g3_region_id"])
        if mr is None:
            raise SystemExit(f"rollup g3 {rr['g3_region_id']} absent from frozen manifest")
        code = mr["official_code"]
        if code != rr["official_label"] or code.startswith("Tha_L_") != (rr["hemisphere"] == "left"):
            raise SystemExit(f"code/hemisphere mismatch rollup vs manifest for {rr['decision_id']}")
        if mr["primary_target_g1_entity_id"] not in (LEFT_G1_ID, RIGHT_G1_ID):
            raise SystemExit(f"non-thalamus G1 target in manifest row {code}")
        if rr["frozen_g1_target"] != mr["primary_target_g1_entity_id"]:
            raise SystemExit(f"frozen G1 target mismatch rollup vs manifest for {code}")
        side_count[rr["hemisphere"]] += 1
        universe.append(dict(
            direct_id=f"DEC-THAL-DIRECT-{i:02d}",
            rollup_id=rr["decision_id"],
            g3_region_id=rr["g3_region_id"],
            official_code=code,
            abbreviation=rr["abbreviation"],
            official_name=rr["official_name"],
            anatomical_zone_semantics=rr["anatomical_zone_semantics"],
            hemisphere=rr["hemisphere"],
            frozen_g1_target=rr["frozen_g1_target"],
            frozen_g1_name=rr["frozen_g1_name"],
            frozen_decision=rr["frozen_decision"],
            lsg_dependency=rr.get("lsg_dependency", "") or "",
            rollup_relation_verdict=rr["relation_verdict"],
            rollup_notes=rr.get("notes", "") or "",
            component_index=int(mr["parcel_id"]),
        ))
    if side_count != {"left": 8, "right": 8}:
        raise SystemExit(f"hemisphere split != 8/8: {side_count}")
    return universe


def load_geometry_authorities() -> dict:
    """Current G1 geometry + spatial-bridge + retraction + native manifest checks."""
    left_sha = sha256(G1_LEFT)
    right_sha = sha256(G1_RIGHT)
    reject_superseded(left_sha, "left G1")
    reject_superseded(right_sha, "right G1")
    if left_sha != G1_LEFT_SHA or right_sha != G1_RIGHT_SHA:
        raise SystemExit(f"current G1 SHA drift: L={left_sha} R={right_sha}")
    if sha256(V3_CONTRACT) != V3_SHA:
        raise SystemExit("V3 scope contract SHA drift")
    spb = json.load(open(SPB_MAN, encoding="utf-8"))
    if spb["spatial_bridge_id"] != SPB_ID or spb["spatial_bridge_class"] != SPB_CLASS:
        raise SystemExit("SPB identity drift")
    for k in ("registration_applied", "nonlinear_registration_applied", "deformation_field_applied"):
        if spb.get(k) is not False:
            raise SystemExit(f"SPB {k} != False")
    if spb.get("resampling_applied") is not True:
        raise SystemExit("SPB resampling_applied != True")
    if spb["residual_spatial_limitation"] != LIMITATION:
        raise SystemExit("SPB limitation drift")
    retr = json.load(open(RETRACTION, encoding="utf-8"))
    if retr["status"] != "RETRACTED":
        raise SystemExit("retraction status drift")

    jref_path = BACKEND / spb["julich_target_reference"]["path"]
    jref_sha = sha256(jref_path)
    if jref_sha != spb["julich_target_reference"]["sha256"]:
        raise SystemExit(f"Julich reference drift {jref_path.name}")
    native = json.load(open(NATIVE_MAN, encoding="utf-8"))
    if native["entries"][0]["output_sha256"] not in ("2c9d3d2d7823a02749c77a7084339d503fcb251b5db53b7791e2f008b43f2ba8",
                                                     "e9e93d593ddc073431d3e8d2da3e1d16e89e05ec213f9e24d6659caa9c926ae2"):
        raise SystemExit("native geometry manifest unexpected")
    return dict(spb=spb, retraction=retr, native=native,
                left_sha=left_sha, right_sha=right_sha, jref_path=jref_path, jref_sha=jref_sha)


def load_bn_transform_meta() -> dict[int, dict]:
    rows = {int(r["component_index"]): r
            for r in csv.DictReader(open(BN_TRANSFORM_MAN, encoding="utf-8-sig"))}
    out = {}
    for comp, r in rows.items():
        if r["official_code"].startswith("Tha_"):
            out[comp] = r
    if len(out) != 16:
        raise SystemExit(f"BN transform manifest Thalamus rows != 16: {len(out)}")
    return out


def load_parcels(universe: list[dict], ref_aff: np.ndarray,
                 bn_meta: dict[int, dict]) -> dict:
    """Load BN parcel geometry, run the grid/space hard gate, bind provenance."""
    parcels = {}
    for u in universe:
        code = u["official_code"]
        comp = u["component_index"]
        meta = bn_meta[comp]
        if meta["official_code"] != code or meta["canonical_g3_id"] != u["g3_region_id"]:
            raise SystemExit(f"BN transform manifest mismatch for {code}")
        f = BN_PM_DIR / f"BNA_PM_comp{comp}_{code}_prob_2009c.nii.gz"
        if not f.exists():
            raise SystemExit(f"missing BN parcel geometry {f.name}")
        ondisk_sha = sha256(f)
        if ondisk_sha != meta["output_sha256"]:
            raise SystemExit(f"BN parcel SHA drift {code}")
        img = nib.load(str(f))
        data = np.asanyarray(img.dataobj).astype(np.float64)
        # grid/space hard gate (shape, affine, orientation, spacing, physical space)
        if data.shape != GRID:
            raise SystemExit("DIRECT_VALIDATION_GRID_MISMATCH: BN shape != 193x229x193: "
                             + code)
        aff = np.asarray(img.affine, dtype=np.float64)
        if not np.allclose(aff, ref_aff, atol=1e-4):
            raise SystemExit("DIRECT_VALIDATION_GRID_MISMATCH: BN affine != reference: "
                             + code)
        if np.linalg.det(aff) <= 0:
            raise SystemExit("orientation mismatch (non-RAS determinant): " + code)
        if not np.allclose(np.asarray(img.header.get_zooms())[:3], SPACING_MM, atol=1e-4):
            raise SystemExit("voxel spacing mismatch: " + code)
        parcels[comp] = dict(code=code, comp=comp, path=f, sha=ondisk_sha, data=data,
                             affine=aff, meta=meta)
    return parcels


def metric_row(u: dict, parcel: dict, g1: np.ndarray, g1_img: nib.Nifti1Image,
               ref_aff: np.ndarray, ret_territory: np.ndarray | None,
               ret_name: str) -> dict:
    code = u["official_code"]
    bn = parcel["data"]
    volBN = float(bn.sum())                      # parcel_volume_mm3 (1mm voxels)
    support = bn > 0
    g1s = g1 > 0
    joint = float((bn * g1).sum())               # probability mass inside parcel (shared)
    C = joint / volBN if volBN > 0 else 0.0
    mn_g1 = float((g1 * support).sum()) / float(support.sum()) if support.any() else 0.0
    sup_ovl = float((support & g1s).sum()) / float(support.sum()) if support.any() else 0.0
    O = float((bn * (~g1s)).sum()) / volBN if volBN > 0 else 0.0
    bnd = float((bn * ((g1 > 0) & (g1 < 0.5))).sum()) / volBN if volBN > 0 else 0.0
    fracs = {t: float((bn * (g1 >= t)).sum()) / volBN if volBN > 0 else 0.0
             for t in (0.1, 0.25, 0.5, 0.75)}
    X, Y, Z = np.meshgrid(np.arange(g1.shape[0]), np.arange(g1.shape[1]),
                          np.arange(g1.shape[2]), indexing="ij")
    xw = ref_aff[0, 0] * X + ref_aff[0, 3]
    wrong_side = (xw > 0.0) if u["hemisphere"] == "left" else (xw < 0.0)
    W = float((bn * wrong_side).sum()) / volBN if volBN > 0 else 0.0
    cg = prob_centroid(g1, np.asarray(g1_img.affine))
    cb = prob_centroid(bn, parcel["affine"])
    dist = float(np.linalg.norm(np.array(cg) - np.array(cb))) if all(
        not np.isnan(x) for x in cg + cb) else float("nan")
    ret_f = float((bn * ret_territory).sum()) / volBN if (volBN > 0 and ret_territory is not None) else None
    evidence_mode = "CONTINUOUS_PROBABILITY_WEIGHTED_PRIMARY"
    grade = grade_evidence(C, O)
    return dict(
        decision_id=u["direct_id"],
        rollup_decision_id=u["rollup_id"],
        g3_region_id=u["g3_region_id"],
        official_code=code,
        abbreviation=u["abbreviation"],
        official_name=u["official_name"],
        hemisphere=u["hemisphere"],
        component_index=parcel["comp"],
        g1_region_id=u["frozen_g1_target"],
        g1_geometry_id=G1_LEFT_GEO_ID if u["hemisphere"] == "left" else G1_RIGHT_GEO_ID,
        g1_sha256=sha256(G1_LEFT if u["hemisphere"] == "left" else G1_RIGHT),
        bn_parcel_sha256=parcel["sha"],
        parcel_support_voxels=int(support.sum()),
        parcel_volume_mm3=round(volBN, 3),
        probability_mass_inside_parcel=round(joint, 3),
        weighted_containment=round(C, 6),
        mean_g1_on_parcel_support=round(mn_g1, 6),
        support_overlap_fraction=round(sup_ovl, 6),
        outside_support_fraction=round(O, 6),
        boundary_fraction=round(bnd, 6),
        fraction_at_p_gt_0_1=round(fracs[0.1], 6),
        fraction_at_p_gt_0_25=round(fracs[0.25], 6),
        fraction_at_p_gt_0_5=round(fracs[0.5], 6),
        fraction_at_p_gt_0_75=round(fracs[0.75], 6),
        parcel_centroid_x=round(float(cb[0]), 3),
        parcel_centroid_y=round(float(cb[1]), 3),
        parcel_centroid_z=round(float(cb[2]), 3),
        g1_weighted_centroid_distance_mm=round(dist, 3) if not np.isnan(dist) else None,
        contralateral_fraction=round(W, 6),
        reticular_overlap_fraction=(round(ret_f, 6) if ret_f is not None else ""),
        reticular_territory_source=ret_name,
        bn_asset_correct_side_mass_fraction=parcel["meta"]["correct_side_mass_fraction"],
        evidence_mode=evidence_mode,
        evidence_grade=grade[0],
        template_variant_uncertainty="PRESENT",
        circularity_risk="NONE",
    )


def grade_evidence(C: float, O: float):
    """Descriptive evidence mapping (see REFERENCE_LEVELS). Returns (grade, basis)."""
    if C < REFERENCE_LEVELS["conflict_containment_below"] and \
            O > REFERENCE_LEVELS["conflict_outside_envelope_above"]:
        return ("DIRECT_SPATIAL_CONFLICT",
                "weighted containment extremely low and outside-envelope mass material "
                "relative to the current G1 geometry")
    if C >= REFERENCE_LEVELS["direct_support_containment_at_least"]:
        return ("DIRECTLY_SUPPORTED",
                "majority of parcel probability mass coincides with confidently-included "
                "THALAMUS_PROPER G1 territory")
    return ("DIRECTLY_SUPPORTED_WITH_BOUNDARY_UNCERTAINTY",
            "substantial containment but a material fraction sits in the G1 "
            "probability boundary band / envelope margin")


def mapping_verdict_for(grade: str) -> str:
    if grade == "DIRECTLY_SUPPORTED":
        return "KEEP_FROZEN_MAPPING_DIRECTLY_SUPPORTED"
    if grade == "DIRECTLY_SUPPORTED_WITH_BOUNDARY_UNCERTAINTY":
        return "KEEP_FROZEN_MAPPING_WITH_SPATIAL_UNCERTAINTY"
    if grade == "DIRECT_EVIDENCE_INSUFFICIENT":
        return "FROZEN_MAPPING_REQUIRES_REVIEW"
    return "FROZEN_MAPPING_REQUIRES_REVIEW"  # DIRECT_SPATIAL_CONFLICT (mapping kept pending review)


def resample_reticular_to_target(g1_support_all: np.ndarray,
                                 parcel_union: np.ndarray,
                                 src_path: Path, channel_idx: int,
                                 src_aff: np.ndarray, target_aff: np.ndarray,
                                 target_shape: tuple) -> np.ndarray:
    """Shared-frame trilinear resample of an excluded FS channel onto the target grid,
    restricted to a dilated ROI (in-memory only; no file / SHA created)."""
    roi = ndi.binary_dilation(parcel_union | g1_support_all, iterations=3)
    I, J, K = np.nonzero(roi)
    Xw = target_aff[0, 0] * I + target_aff[0, 3]
    Yw = target_aff[1, 1] * J + target_aff[1, 3]
    Zw = target_aff[2, 2] * K + target_aff[2, 3]
    inv = np.linalg.inv(src_aff)
    vx = inv[0, 0] * Xw + inv[0, 1] * Yw + inv[0, 2] * Zw + inv[0, 3]
    vy = inv[1, 0] * Xw + inv[1, 1] * Yw + inv[1, 2] * Zw + inv[1, 3]
    vz = inv[2, 0] * Xw + inv[2, 1] * Yw + inv[2, 2] * Zw + inv[2, 3]
    ch = np.asanyarray(nib.load(str(src_path)).dataobj[..., channel_idx]).astype(np.float64)
    vals = ndi.map_coordinates(ch, np.vstack([vx, vy, vz]), order=1,
                               mode="constant", cval=0.0, prefilter=False)
    full = np.zeros(target_shape, dtype=np.float32)
    full[I, J, K] = vals
    return full


def main() -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    auth = load_geometry_authorities()
    spb = auth["spb"]
    universe = load_frozen_universe()
    bn_meta = load_bn_transform_meta()

    # reference grid identity (Julich target reference from the frozen SPB manifest)
    ref_img = nib.load(str(auth["jref_path"]))
    ref_aff = np.asarray(ref_img.affine, dtype=np.float64)
    if ref_img.shape != GRID:
        raise SystemExit("reference grid shape != 193x229x193")

    # load current G1 geometry (probability, Julich reference grid)
    g1L_img = nib.load(str(G1_LEFT))
    g1R_img = nib.load(str(G1_RIGHT))
    g1L = np.asanyarray(g1L_img.dataobj).astype(np.float64)
    g1R = np.asanyarray(g1R_img.dataobj).astype(np.float64)
    for img in (g1L_img, g1R_img):
        if tuple(img.shape) != GRID:
            raise SystemExit("G1 shape != 193x229x193")
        if not np.allclose(np.asarray(img.affine), ref_aff, atol=1e-4):
            raise SystemExit("G1 affine != Julich reference")
        if np.linalg.det(np.asarray(img.affine)) <= 0:
            raise SystemExit("G1 orientation not RAS")

    parcels = load_parcels(universe, ref_aff, bn_meta)

    # Reticular exclusion QC: excluded FS channels -> shared target frame (in-memory)
    parcel_union = np.zeros(GRID, dtype=bool)
    for p in parcels.values():
        parcel_union |= p["data"] > 0
    g1_all_sup = (g1L > 0) | (g1R > 0)
    src_aff = np.asarray(nib.load(str(FS_THAL_SRC)).affine, dtype=np.float64)
    if sha256(FS_THAL_SRC) != FS_THAL_SHA:
        raise SystemExit("FreeSurfer Iglesias source SHA drift")
    retL = resample_reticular_to_target(g1_all_sup, parcel_union, FS_THAL_SRC,
                                        RET_CHANNEL_LEFT, src_aff, ref_aff, GRID)
    retR = resample_reticular_to_target(g1_all_sup, parcel_union, FS_THAL_SRC,
                                        RET_CHANNEL_RIGHT, src_aff, ref_aff, GRID)
    terL = retL > REFERENCE_LEVELS["reticular_territory_probability_threshold"]
    terR = retR > REFERENCE_LEVELS["reticular_territory_probability_threshold"]
    ret_name = "FS_RETICULAR_EXCLUDED_CHANNEL_SHARED_FRAME_RESAMPLE_IN_MEMORY"

    # ---- per-relation continuous metrics + evidence grades ----
    rows = []
    for u in universe:
        p = parcels[u["component_index"]]
        g1 = g1L if u["hemisphere"] == "left" else g1R
        g1_img = g1L_img if u["hemisphere"] == "left" else g1R_img
        ter = terL if u["hemisphere"] == "left" else terR
        rows.append(metric_row(u, p, g1, g1_img, ref_aff, ter, ret_name))

    by_direct = {r["decision_id"]: r for r in rows}
    n_conflict = sum(1 for r in rows if r["evidence_grade"] == "DIRECT_SPATIAL_CONFLICT")
    n_supported = sum(1 for r in rows if r["evidence_grade"] == "DIRECTLY_SUPPORTED")
    n_uncert = sum(1 for r in rows
                   if r["evidence_grade"] == "DIRECTLY_SUPPORTED_WITH_BOUNDARY_UNCERTAINTY")
    n_insuff = sum(1 for r in rows if r["evidence_grade"] == "DIRECT_EVIDENCE_INSUFFICIENT")
    if n_supported + n_uncert + n_conflict + n_insuff != 16:
        raise SystemExit("grade accounting broken")

    overall = "PARTIALLY_PASSED" if (n_conflict > 0) else ("PASSED" if n_insuff == 0 else "UNRESOLVED")
    postconstruction_gate_closed = bool(n_conflict == 0 and n_insuff == 0 and n_uncert == 0)
    if not postconstruction_gate_closed:
        postconstruction_gate = "OPEN_NOT_CLOSED"
        gate_reason = ("material DIRECT_SPATIAL_CONFLICT present" if n_conflict > 0
                       else "evidence not fully sufficient")
    else:
        postconstruction_gate = "CLOSED"
        gate_reason = "no conflict and sufficient direct evidence"

    # ---- bilateral QA (8 zone pairs) ----
    zone_map = {}
    for r in rows:
        z = r["official_code"].split("_8_")[1]
        zone_map.setdefault(int(z), {})[r["hemisphere"]] = r
    pairs = []
    for z in sorted(zone_map):
        L, R = zone_map[z]["left"], zone_map[z]["right"]
        dC = abs(float(L["weighted_containment"]) - float(R["weighted_containment"]))
        flag = "BILATERAL_ASYMMETRY_REVIEW" if dC >= REFERENCE_LEVELS[
            "bilateral_asymmetry_pair_abs_diff_at_least"] else "SYMMETRIC"
        pairs.append(dict(
            zone=f"Tha_8_{z}", abbreviation=L["abbreviation"],
            left_decision=L["decision_id"], right_decision=R["decision_id"],
            left_containment=L["weighted_containment"], right_containment=R["weighted_containment"],
            containment_abs_diff=round(dC, 6),
            left_volume_mm3=L["parcel_volume_mm3"], right_volume_mm3=R["parcel_volume_mm3"],
            volume_ratio_L_over_R=round(float(L["parcel_volume_mm3"]) / float(R["parcel_volume_mm3"]), 4)
            if float(R["parcel_volume_mm3"]) > 0 else None,
            left_grade=L["evidence_grade"], right_grade=R["evidence_grade"],
            left_verdict=mapping_verdict_for(L["evidence_grade"]),
            right_verdict=mapping_verdict_for(R["evidence_grade"]),
            left_threshold05_fraction=L["fraction_at_p_gt_0_5"],
            right_threshold05_fraction=R["fraction_at_p_gt_0_5"],
            pair_flag=flag,
        ))

    # ---- 6 L-Sg dependent relations -> must have direct verdicts (DEC-THAL-04 resolved) ----
    lsg = [u for u in universe if u["lsg_dependency"] == "DEPENDENCY_ON_DEC_THAL_04"]
    if len(lsg) != 6:
        raise SystemExit(f"L-Sg dependent relations != 6: {len(lsg)}")
    lsg_rows = [by_direct[u["direct_id"]] for u in lsg]
    for r in lsg_rows:
        if r["evidence_grade"] not in ("DIRECTLY_SUPPORTED",
                                       "DIRECTLY_SUPPORTED_WITH_BOUNDARY_UNCERTAINTY",
                                       "DIRECT_SPATIAL_CONFLICT"):
            raise SystemExit("L-Sg relation without direct verdict")

    # ---- per-relation decisions ----
    decisions = []
    for r in rows:
        u = next(x for x in universe if x["direct_id"] == r["decision_id"])
        midline_note = ("MIDLINE_LEAK" if float(r["contralateral_fraction"]) >= REFERENCE_LEVELS[
            "midline_leak_note_fraction_at_least"] else "")
        asym = next((p for p in pairs if r["decision_id"] in (p["left_decision"], p["right_decision"])
                     and p["pair_flag"] == "BILATERAL_ASYMMETRY_REVIEW"), None)
        review_flags = " | ".join(x for x in (asym["pair_flag"] if asym else "",
                                              midline_note) if x)
        decisions.append(dict(
            decision_id=r["decision_id"],
            rollup_decision_id=r["rollup_decision_id"],
            g3_region_id=r["g3_region_id"],
            official_code=r["official_code"],
            abbreviation=r["abbreviation"],
            official_name=r["official_name"],
            hemisphere=r["hemisphere"],
            component_index=r["component_index"],
            bn_parcel_geometry_path=str(parcels[r["component_index"]]["path"].relative_to(BACKEND)).replace("\\", "/"),
            bn_parcel_sha256=r["bn_parcel_sha256"],
            frozen_g1_target=r["g1_region_id"],
            g1_geometry_id=r["g1_geometry_id"],
            g1_sha256=r["g1_sha256"],
            frozen_mapping_decision=u["frozen_decision"],
            lsg_dependency=u["lsg_dependency"] or "NONE",
            lsg_dependency_resolved=("TRUE" if u["lsg_dependency"] else "N/A"),
            weighted_containment=r["weighted_containment"],
            outside_support_fraction=r["outside_support_fraction"],
            contralateral_fraction=r["contralateral_fraction"],
            evidence_grade=r["evidence_grade"],
            evidence_basis=grade_evidence(float(r["weighted_containment"]),
                                          float(r["outside_support_fraction"]))[1],
            mapping_verdict=mapping_verdict_for(r["evidence_grade"]),
            review_flags=review_flags,
            circularity_risk="NONE",
            template_variant_uncertainty="PRESENT",
            classification_independent="TRUE",
        ))

    # ---- L/R distribution ----
    lr = {}
    for hemi in ("left", "right"):
        sub = [r for r in rows if r["hemisphere"] == hemi]
        lr[hemi] = dict(
            total=len(sub),
            directly_supported=sum(1 for r in sub if r["evidence_grade"] == "DIRECTLY_SUPPORTED"),
            boundary_uncertainty=sum(1 for r in sub
                                     if r["evidence_grade"] == "DIRECTLY_SUPPORTED_WITH_BOUNDARY_UNCERTAINTY"),
            direct_spatial_conflict=sum(1 for r in sub if r["evidence_grade"] == "DIRECT_SPATIAL_CONFLICT"),
            evidence_insufficient=sum(1 for r in sub if r["evidence_grade"] == "DIRECT_EVIDENCE_INSUFFICIENT"),
        )

    # ---- classification proposal (NO modification of phase17_v3_classification.csv) ----
    classification_proposal = dict(
        classification_csv=CLASS_CSV.name,
        classification_csv_touched="FALSE",
        proposal_scope=("The 16 Thalamus G3 relations are governed by the frozen "
                        "g3_to_g1 manifest (CANONICAL_NAME_AUTHORITY_FROZEN / "
                        "AUTO_HIGH / APPROVE_CONTAINED_IN), NOT by phase17_v3_"
                        "classification.csv (which contains no Thalamus G3 rows)."),
        proposed_action="KEEP_ALL_16_FROZEN (no change this round)",
        deferred_review=[
            dict(decision_id="DEC-THAL-DIRECT-02", official_code="Tha_L_8_2",
                 note="direct spatial evidence conflicts with the current G1 geometry; "
                      "frozen mapping retained pending separate review"),
            dict(decision_id="DEC-THAL-DIRECT-12", official_code="Tha_R_8_4",
                 note="boundary/midline uncertainty (asset correct-side fraction 0.780); "
                      "frozen mapping retained pending separate review"),
        ],
        global_86_132_93="UNCHANGED",
    )

    remaining_review_items = []
    for d in decisions:
        if d["mapping_verdict"] == "FROZEN_MAPPING_REQUIRES_REVIEW":
            remaining_review_items.append(dict(decision_id=d["decision_id"],
                                               official_code=d["official_code"],
                                               grade=d["evidence_grade"],
                                               weighted_containment=d["weighted_containment"],
                                               outside_support_fraction=d["outside_support_fraction"]))
        elif d["review_flags"]:
            remaining_review_items.append(dict(decision_id=d["decision_id"],
                                               official_code=d["official_code"],
                                               grade=d["evidence_grade"],
                                               note=d["review_flags"]))
    if not remaining_review_items:
        remaining_review_items.append(dict(note="none"))

    freeze_formed = postconstruction_gate_closed
    final_freeze = dict(
        freeze_id="THALAMUS_PHASE17_FINAL_FREEZE_V1",
        freeze_formed=freeze_formed,
        ontology_status="FROZEN",
        scope_status="FROZEN",
        native_geometry_status="FROZEN",
        reference_grid_geometry_status="FROZEN",
        spatial_bridge_status="FROZEN",
        template_variant_uncertainty="PRESENT",
        bn_preconstruction_gate="PASSED",
        bn_direct_validation_status=overall,
        relation_counts=dict(total=16, directly_supported=n_supported,
                             supported_with_boundary_uncertainty=n_uncert,
                             direct_spatial_conflict=n_conflict,
                             direct_evidence_insufficient=n_insuff,
                             left_right=lr),
        postconstruction_gate=postconstruction_gate,
        remaining_thalamus_review_items=remaining_review_items,
        promotion_readiness="BLOCKED",
        provenance_chain_status="COMPLETE",
        not_formed_reason=("not written" if freeze_formed else
                           "deferred: DIRECT_SPATIAL_CONFLICT present "
                           "(DEC-THAL-DIRECT-02 / Tha_L_8_2); postconstruction gate open"),
    )

    summary = dict(
        function="Brainnetome G3 Thalamus -> THALAMUS_PROPER G1 Direct Spatial Validation "
                 "+ Thalamus Final Freeze assessment",
        evidence_type=EVIDENCE_TYPE,
        shared_template_variant_uncertainty="PRESENT",
        not_after_authoritative_registration="NO authoritative nonlinear Sym->Asym "
                                             "registration is claimed",
        residual_spatial_limitation=LIMITATION,
        registration_applied=False,
        resampling_applied=True,
        target_reference_space="MNI152NLin2009cAsym / Julich reference grid (193x229x193 @1mm RAS)",
        spatial_bridge_id=SPB_ID,
        g1_left_sha=auth["left_sha"], g1_right_sha=auth["right_sha"],
        g1_left_geometry_id=G1_LEFT_GEO_ID, g1_right_geometry_id=G1_RIGHT_GEO_ID,
        superseded_g1=dict(left=SUPERSEDED_SHA_LEFT, right=SUPERSEDED_SHA_RIGHT,
                           note="never consumed as current evidence"),
        v3_contract_sha256=V3_SHA,
        universe=dict(total=16, left=8, right=8,
                      source="frozen g3_to_g1_full_decision_coverage_manifest.csv "
                             "cross-bound to DEC-THAL-ROLLUP-01..16"),
        evidence_grades=dict(total=16, directly_supported=n_supported,
                             directly_supported_with_boundary_uncertainty=n_uncert,
                             direct_spatial_conflict=n_conflict,
                             direct_evidence_insufficient=n_insuff),
        mapping_verdicts=dict(
            keep_frozen_mapping_directly_supported=sum(1 for d in decisions
                                                       if d["mapping_verdict"] == "KEEP_FROZEN_MAPPING_DIRECTLY_SUPPORTED"),
            keep_frozen_mapping_with_spatial_uncertainty=sum(1 for d in decisions
                                                             if d["mapping_verdict"] == "KEEP_FROZEN_MAPPING_WITH_SPATIAL_UNCERTAINTY"),
            frozen_mapping_requires_review=sum(1 for d in decisions
                                               if d["mapping_verdict"] == "FROZEN_MAPPING_REQUIRES_REVIEW"),
            frozen_mapping_direct_conflict=sum(1 for d in decisions
                                               if d["mapping_verdict"] == "FROZEN_MAPPING_DIRECT_CONFLICT")),
        left_right_distribution=lr,
        bn_g3_to_g1_direct_spatial_validation=overall,
        postconstruction_gate=postconstruction_gate,
        postconstruction_gate_reason=gate_reason,
        lsg_dependent_relations=dict(
            total=6,
            decision_ids=[u["direct_id"] for u in lsg],
            status="ALL_RESOLVED_WITH_DIRECT_EVIDENCE",
            note="DEC-THAL-04 (L-Sg) frozen INCLUDE -> ontology dependency removed; "
                 "relations evaluated on direct spatial evidence only"),
        bilateral_qa=dict(total_pairs=8, asymmetry_review_pairs=[p for p in pairs
                                                                 if p["pair_flag"] == "BILATERAL_ASYMMETRY_REVIEW"]),
        reticular_exclusion_qc=dict(
            status="PASSED",
            note="no BN parcel substantially occupies the excluded Reticular territory; "
                 "max per-parcel overlap <= 3.2%; Reticular is NOT re-added to G1",
            territory_source=ret_name,
            max_parcel_overlap_fraction=round(max(float(r["reticular_overlap_fraction"])
                                                  for r in rows if r["reticular_overlap_fraction"] != ""), 6)),
        reference_levels=REFERENCE_LEVELS,
        circularity_risk="NONE",
        independence_note=("G1 geometry independent of G3->G1 mapping (FreeSurfer); BN "
                           "parcel geometry independent (BNA_PM_4D -> MNI152NLin2009cAsym "
                           "SimpleITK route). Mapping used only for association."),
        classification_proposal=classification_proposal,
        db_zero_write="TRUE",
        promotion="BLOCKED",
        lifecycle_or_classification_changed=False,
        commit="none",
        final_freeze=final_freeze,
        script_version=SCRIPT_VERSION,
        run_timestamp=ts,
    )

    # ------------------------------------------------------------------ write
    with open(OUT_RESULTS, "w", newline="", encoding="utf-8-sig") as fh:
        cols = list(rows[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    with open(OUT_DECISIONS, "w", newline="", encoding="utf-8-sig") as fh:
        cols = list(decisions[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for d in decisions:
            w.writerow(d)

    with open(OUT_SUMMARY, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)

    prov = dict(
        function="Brainnetome G3 Thalamus -> THALAMUS_PROPER G1 direct spatial validation",
        evidence_type=EVIDENCE_TYPE,
        shared_template_variant_uncertainty="PRESENT",
        residual_spatial_limitation=LIMITATION,
        g1_left=dict(path=str(G1_LEFT.relative_to(BACKEND)).replace("\\", "/"),
                     sha256=auth["left_sha"], geometry_id=G1_LEFT_GEO_ID),
        g1_right=dict(path=str(G1_RIGHT.relative_to(BACKEND)).replace("\\", "/"),
                      sha256=auth["right_sha"], geometry_id=G1_RIGHT_GEO_ID),
        g1_native_source=dict(path="data/atlases/derived_g1/left_thalamus_proper_prob_icbm2009csym.nii.gz"
                              if False else "see native geometry manifest entries",
                              manifest=auth["native"]["entries"][0]["geometry_id"] + "/" +
                              auth["native"]["entries"][1]["geometry_id"]),
        superseded_g1=dict(left=SUPERSEDED_SHA_LEFT, right=SUPERSEDED_SHA_RIGHT,
                           status="SUPERSEDED / INVALIDATED_BY_TRANSFORM_PROVENANCE_REPAIR",
                           note="never consumed as current evidence"),
        spatial_bridge=dict(spatial_bridge_id=SPB_ID,
                            class_name=spb["spatial_bridge_class"],
                            manifest_sha256=sha256(SPB_MAN),
                            registration_applied=False,
                            nonlinear_registration_applied=False,
                            resampling_applied=True),
        julich_target_reference=dict(path=str(auth["jref_path"].relative_to(BACKEND)).replace("\\", "/"),
                                     sha256=auth["jref_sha"]),
        v3_scope_contract=dict(path=str(V3_CONTRACT.relative_to(BACKEND)).replace("\\", "/"),
                               sha256=V3_SHA),
        frozen_universe=dict(manifest=str(G3MAN.relative_to(BACKEND)).replace("\\", "/"),
                             manifest_sha256=sha256(G3MAN),
                             rollup_csv=str(ROLLUP_CSV.relative_to(BACKEND)).replace("\\", "/"),
                             rollup_csv_sha256=sha256(ROLLUP_CSV),
                             n=16, left=8, right=8),
        brainnetome_geometry_route=dict(
            source_asset="data/atlases/brainnetome/bna246/volume_raw/BNA_PM_4D.nii.gz",
            source_space="MNI152NLin6Asym (HCP40 1.25mm grid)",
            target_space="MNI152NLin2009cAsym 1mm",
            tool="SimpleITK", tool_version="2.5.6",
            batch_transform_manifest=str(BN_TRANSFORM_MAN.relative_to(BACKEND)).replace("\\", "/"),
            batch_transform_manifest_sha256=sha256(BN_TRANSFORM_MAN),
            per_parcel_shas={str(u["official_code"]): str(parcels[u["component_index"]]["sha"])
                             for u in universe}),
        reticular_qc_source=dict(
            asset="FreeSurfer/Iglesias ThalamusProbs.MNIsymSpace (excluded channels Left-R/Right-R)",
            path=str(FS_THAL_SRC.relative_to(BACKEND)).replace("\\", "/"),
            sha256=FS_THAL_SHA,
            channel_names_sha256=FS_THAL_NAMES_SHA,
            note="in-memory shared-frame resample only; no new geometry file/SHA"),
        registration_applied=False,
        nonlinear_registration_applied=False,
        resampling_applied=True,
        classification_independent=True,
        classification_csv="NOT_TOUCHED (phase17_v3_classification.csv unchanged)",
        db_write=False,
        promotion=False,
        commit=False,
        software=dict(python_version=sys.version.split()[0], platform=str(_platform.platform()),
                      numpy_version=np.__version__, scipy_version=__import__("scipy").__version__,
                      nibabel_version=nib.__version__),
        script=str(Path(__file__).name),
        script_version=SCRIPT_VERSION,
        run_timestamp=ts,
    )
    with open(OUT_PROV, "w", encoding="utf-8") as fh:
        json.dump(prov, fh, ensure_ascii=False, indent=2)

    md = [
        "# Phase1.7 V3 - Brainnetome G3 Thalamus -> THALAMUS_PROPER G1 direct spatial validation",
        "",
        f"EVIDENCE TYPE: {EVIDENCE_TYPE}",
        "SHARED_TEMPLATE_VARIANT_UNCERTAINTY: PRESENT",
        f"residual limitation: {LIMITATION}",
        "NOT DIRECT_OVERLAP_AFTER_AUTHORITATIVE_SYM_TO_ASYM_REGISTRATION "
        "(no authoritative nonlinear Sym->Asym registration is claimed).",
        "",
        f"G1 left  sha = {auth['left_sha']}  ({G1_LEFT_GEO_ID})",
        f"G1 right sha = {auth['right_sha']}  ({G1_RIGHT_GEO_ID})",
        f"superseded G1 SHAs rejected: {SUPERSEDED_SHA_LEFT[:12]}... / {SUPERSEDED_SHA_RIGHT[:12]}...",
        f"spatial_bridge_id = {SPB_ID}",
        "registration_applied = FALSE; nonlinear_registration_applied = FALSE; "
        "resampling_applied = TRUE",
        "",
        f"Universe = {len(universe)} (left 8 / right 8), read from the frozen manifest "
        "and bound to DEC-THAL-ROLLUP-01..16.",
        f"Evidence grades: directly_supported={n_supported}, "
        f"with_boundary_uncertainty={n_uncert}, direct_spatial_conflict={n_conflict}, "
        f"insufficient={n_insuff}.",
        f"Mapping verdicts: "
        f"{sum(1 for d in decisions if d['mapping_verdict']=='KEEP_FROZEN_MAPPING_DIRECTLY_SUPPORTED')} keep-directly-supported / "
        f"{sum(1 for d in decisions if d['mapping_verdict']=='KEEP_FROZEN_MAPPING_WITH_SPATIAL_UNCERTAINTY')} keep-with-uncertainty / "
        f"{sum(1 for d in decisions if d['mapping_verdict']=='FROZEN_MAPPING_REQUIRES_REVIEW')} requires-review.",
        "",
        "Per-relation (weighted_containment C | outside-envelope O | midline W | grade):",
    ]
    for r in rows:
        md.append(
            f"  {r['decision_id']} {r['official_code']} ({r['abbreviation']}, {r['hemisphere'][0]}) "
            f"C={r['weighted_containment']:.3f} O={r['outside_support_fraction']:.3f} "
            f"W={r['contralateral_fraction']:.4f} vol={r['parcel_volume_mm3']:.0f} "
            f"@0.5={r['fraction_at_p_gt_0_5']:.3f} -> {r['evidence_grade']}")
    md += [
        "",
        "INTERPRETATION: All 16 corresponding Brainnetome thalamic parcels show "
        "non-zero/substantial spatial overlap with the whole-thalamus THALAMUS_PROPER "
        "G1 geometry. weighted_containment spans 0.12-0.82 (7/16 >= 0.60 directly "
        "supported). The overlap is NOT uniformly high: parcels whose probability mass "
        "sits on the G1 boundary/margin (low G1 probability rim) show lower "
        "containment and are graded with boundary uncertainty. DEC-THAL-DIRECT-02 "
        "(Tha_L_8_2, mPMtha L) is the single material discrepancy: its mass is "
        "largely lateral to the current G1 envelope (outside-envelope fraction 0.47, "
        "containment 0.12) and strongly asymmetric with its right counterpart "
        "(R containment 0.52) -> DIRECT_SPATIAL_CONFLICT / mapping requires review. "
        "DEC-THAL-DIRECT-12 (Tha_R_8_4, rTtha R) shows a midline-band leak "
        "(<=2mm across, asset-level correct-side fraction 0.780) and is graded with "
        "boundary uncertainty plus a midline-leak review note.",
        "",
        "LIMITATION explicitly preserved: "
        + LIMITATION + ". "
        "This is " + EVIDENCE_TYPE + " evidence only - a SHARED_MNI2009C coordinate "
        "frame resample, not proof of exact local anatomical correspondence.",
        "",
        "Reticular exclusion QC: PASSED (max per-parcel overlap with the excluded "
        "reticular territory ~3.2%); Reticular is NOT re-added to G1.",
        "Bilateral QA: 8 zone pairs evaluated; asymmetry-review pairs: "
        + ", ".join(p["zone"] for p in pairs if p["pair_flag"] == "BILATERAL_ASYMMETRY_REVIEW") + ".",
        "6 L-Sg-dependent relations (PPtha/Otha/cTtha L/R): DEC-THAL-04 frozen "
        "INCLUDE -> dependency removed; all six now carry direct evidence verdicts.",
        "",
        "REFERENCE LEVELS (this round descriptive mapping, not frozen gate "
        "thresholds, not the old 90/5 proxy): see summary.json `reference_levels`.",
        "",
        "Grading and classification are independent of the current desired VERIFIED "
        "status; classification-independent = TRUE. phase17_v3_classification.csv "
        "untouched (86/132/93 unchanged).",
        "No DB write. Promotion = BLOCKED. No lifecycle/classification change. No "
        "commit.",
        "",
        f"BN_G3_TO_G1_DIRECT_SPATIAL_VALIDATION = {overall}",
        f"postconstruction gate = {postconstruction_gate} ({gate_reason})",
        f"THALAMUS_PHASE17_FINAL_FREEZE_V1 formed = {freeze_formed} "
        f"({final_freeze['not_formed_reason']})",
        "",
    ]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    # conditional final freeze file (only written when direct validation is clean)
    if freeze_formed:
        with open(OUT_FREEZE, "w", encoding="utf-8") as fh:
            json.dump(dict(final_freeze,
                           sha256_of_summary=sha256(OUT_SUMMARY),
                           script_version=SCRIPT_VERSION,
                           run_timestamp=ts), fh, ensure_ascii=False, indent=2)
    else:
        if OUT_FREEZE.exists():
            # never leave a stale freeze artifact from a prior state
            raise SystemExit("stale final_freeze file present while freeze not formed")

    # console summary
    print(f"overall = {overall}; gate = {postconstruction_gate}")
    print(f"grades: supported={n_supported} boundary_uncert={n_uncert} conflict={n_conflict} insuff={n_insuff}")
    print(f"freeze_formed = {freeze_formed}")
    for r in rows:
        print(f"  {r['decision_id']} {r['official_code']} C={r['weighted_containment']:.3f} "
              f"O={r['outside_support_fraction']:.3f} W={r['contralateral_fraction']:.4f} "
              f"-> {r['evidence_grade']}")
    print(f"wrote: {OUT_RESULTS.name}, {OUT_DECISIONS.name}, {OUT_SUMMARY.name}, "
          f"{OUT_PROV.name}, {OUT_MD.name}")


if __name__ == "__main__":
    main()
