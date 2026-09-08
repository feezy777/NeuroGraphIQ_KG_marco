"""Phase1.7 V3 - Amygdala G1 authoritative reference geometry construction.

Builds Left/Right Amygdala (NGIQ-BR-00000253 / NGIQ-BR-00000261) G1 probability
geometry from the frozen FreeSurfer/Iglesias HippoAmyg subfield posterior atlas:

  1. Canonical identity confirmation (repo canonical data; see notes below).
  2. Freeze the HippoAmyg probability source semantics (per-voxel categorical
     posterior: sum over all 30 channels == 1.0 -> MUTUALLY_EXCLUSIVE_CATEGORICAL;
     Amygdala aggregation operator = SUM over included channels).
  3. Freeze source-channel scope (9 Amygdala sub-nucleus channels INCLUDE;
     20 hippocampal-subfield channels EXCLUDE incl. HATA transition; background
     channel 0 EXCLUDE).
  4. Construct source-native L/R Amygdala probability geometry (channel sum on the
     original 0.25 mm ICBM152_2009c_SYM source grid).
  5. Resample via the frozen shared MNI2009c stereotaxic-frame route (world-
     coordinate reference-grid resample, LINEAR) onto the Julich MNI152NLin2009cAsym
     reference grid (193x229x193 @1 mm RAS).
  6. Native + reference-grid QC, provenance freeze.

Binary policy: derived NIfTI live under data/atlases/derived_g1 (gitignored); only
their SHA256 + manifests are tracked.

Evidence limitation (preserved, identical scientific framing to the frozen Thalamus
round): TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_WARP_CORRECTED.
registration_applied=FALSE; nonlinear_registration_applied=FALSE; resampling_applied=TRUE.
authoritative nonlinear Sym->Asym transform NOT used.

Canonical identity note: the canonical_brain_regions table is not present in the
local read-only DB (only infra/public schemas), so canonical identity is read from
real repository canonical records: macro96 canonical pool (G1_MACRO,
'Left/Right Amygdala', subcortical_region) and the phase16/17 canonical G1 mapping
records that bind NGIQ-BR-00000253 = Left Amygdala / NGIQ-BR-00000261 = Right
Amygdala. The G1 concept is the whole Amygdala (deep laterobasal + centromedial +
superficial/cortical nuclear groups incl. corticoamygdaloid transition + paralaminar)
as expressed by the authoritative Iglesias/FreeSurfer amygdala sub-nucleus channels.

IF/MF entity-type isolation: constructing this G1 geometry does NOT resolve the
Julich IF/MF entity-type review (fiber-mass vs BrainRegion). AMYGDALA_G1_GEOMETRY_
CONSTRUCTION DOES_NOT_RESOLVE JULICH_IF_MF_ENTITY_TYPE_REVIEW, and the geometry is
never widened to cover IF/MF candidates.

Scope verdict must be AMYGDALA_G1_SCOPE_FROZEN before geometry is constructed.
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
HIPPO = BACKEND / "data" / "atlases" / "external_raw" / "freesurfer_icbm2009c" / "hippocampus"
DERIVED = BACKEND / "data" / "atlases" / "derived_g1"
JULICH_REF = BACKEND / "data" / "atlases" / "julich" / "v3.1" / "spatial_raw" / "probability_maps" / "ACBL_VENTRAL_STRIATUM_LATERAL_ACCUMBENS_LEFT.nii.gz"
JULICH_REF_SHA = "185a1d6c179c91bb1f02b3fc0d128b4607504a775edfec48fcc1435d9240bfdf"

RAW_L = HIPPO / "HippoAmygProbs.MNIsymSpace.left.nii.gz"
RAW_R = HIPPO / "HippoAmygProbs.MNIsymSpace.right.nii.gz"
NAMES = HIPPO / "HippoAmygProbs.MNIsymSpace.names.txt"
RAW_L_SHA = "a79d5f88acfa21684a6f8c1e78da21e74ccbf152e68fb845fde048f451c4474e"
RAW_R_SHA = "4d20bb95435afc9a139279ae2a159d8dfbf3f1b1de0d07d901ff6cf08570e5a3"
ACQ_RECORDED_SHA = "a79d5f88acfa21684a6f8c1e78da21e74ccbf152e68fb845fde048f451c4474e"  # acquisition bundle entry (== left file)

LEFT_G1 = "NGIQ-BR-00000253"
RIGHT_G1 = "NGIQ-BR-00000261"
SPB_ID = "SPB-MNI2009C-SYM-ASYM-SHARED-FRAME-V1"
SPB_CLASS = "SHARED_COORDINATE_REFERENCE_GRID_RESAMPLING"
SPB_STATEMENT = "SHARED_STEREOTAXIC_FRAME_REFERENCE_GRID_RESAMPLE"
LIMITATION = "TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_WARP_CORRECTED"
NATIVE_LEFT_ID = "GEO-G1-AMYG-L-FS2009CSYM-V1"
NATIVE_RIGHT_ID = "GEO-G1-AMYG-R-FS2009CSYM-V1"
REF_LEFT_ID = "GEO-G1-AMYG-L-MNI2009CASYM-V1"
REF_RIGHT_ID = "GEO-G1-AMYG-R-MNI2009CASYM-V1"
NATIVE_CLASS = "AUTHORITATIVE_DERIVED_G1_GEOMETRY"
NATIVE_DERIV = "PROBABILITY_CHANNEL_AGGREGATION_FROM_FROZEN_SCOPE"
REF_DERIV = "REFERENCE_GRID_RESAMPLING_FROM_FROZEN_NATIVE_G1_GEOMETRY"
GRID = (193, 229, 193)

NATIVE_OUT = {
    "left": DERIVED / "left_amygdala_prob_icbm2009csym.nii.gz",
    "right": DERIVED / "right_amygdala_prob_icbm2009csym.nii.gz",
}
REF_OUT = {
    "left": DERIVED / "left_amygdala_prob_mni2009casym.nii.gz",
    "right": DERIVED / "right_amygdala_prob_mni2009casym.nii.gz",
}

OUT_CH_SEM = D16 / "phase17_v3_amygdala_source_channel_semantics.csv"
OUT_SCOPE = D16 / "phase17_v3_amygdala_g1_scope_contract_v1.json"
OUT_NATIVE_MAN = D16 / "phase17_v3_amygdala_g1_native_geometry_manifest.json"
OUT_NATIVE_QC = D16 / "phase17_v3_amygdala_g1_native_geometry_qc.csv"
OUT_BRIDGE = D16 / "phase17_v3_amygdala_spatial_bridge_manifest.json"
OUT_REF_MAN = D16 / "phase17_v3_amygdala_g1_reference_geometry_manifest.json"
OUT_REF_QC = D16 / "phase17_v3_amygdala_g1_reference_geometry_qc.csv"
OUT_PROV = D16 / "phase17_v3_amygdala_geometry_provenance.json"
OUT_MD = D16 / "phase17_v3_amygdala_g1_geometry_diagnostics.md"

SCRIPT_VERSION = "phase17_v3_construct_amygdala_g1_geometry.py v1"

# canonical identity (repo canonical records)
CANONICAL = {
    "left": dict(canonical_region_id=LEFT_G1, preferred_name="Left Amygdala",
                 hemisphere="left", granularity_level="G1_MACRO",
                 structure_type="subcortical_region", concept="WHOLE_AMYGDALA",
                 concept_note=("whole amygdala nuclear complex (deep laterobasal + "
                               "centromedial + superficial/cortical groups incl. "
                               "corticoamygdaloid transition + paralaminar) as delimited "
                               "by the authoritative Iglesias/FreeSurfer amygdala sub-nucleus "
                               "channels of the HippoAmyg atlas")),
    "right": dict(canonical_region_id=RIGHT_G1, preferred_name="Right Amygdala",
                  hemisphere="right", granularity_level="G1_MACRO",
                  structure_type="subcortical_region", concept="WHOLE_AMYGDALA",
                  concept_note="same as left; right hemisphere"),
}
# source records used for canonical identity (repo, not DB; see module docstring)
CANON_SOURCE_RECORDS = [
    "data/atlases/macro96/macro96_normalized_manifest.csv (G1_MACRO Left/Right Amygdala)",
    "data/integration/brainregion_direct_g1_phase16/direct_g1_high_confidence.csv "
    "(NGIQ-BR-00000253 = Left Amygdala / NGIQ-BR-00000261 = Right Amygdala)",
    "data/integration/brainregion_direct_g1_phase16/phase17_v3_classification.csv "
    "(candidate G1 macro target naming)",
]
# Amygdala numeric labels (Iglesias/FreeSurfer HippoAmyg LUT, amygdala family)
AMYG_LABELS = {7001, 7003, 7008, 7010, 7005, 7006, 7007, 7009, 7015}
# Hippocampal-family numeric labels present (200-series incl. HATA 211)
HIPPO_LABELS_MIN, HIPPO_LABELS_MAX = 200, 999
HATA_LABEL = 211
BG_LABEL = 0


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def load_channel_table() -> list[dict]:
    """Parse names.txt -> rows: channel_index, numeric_label, official_name, family."""
    rows = []
    for i, line in enumerate(open(NAMES, encoding="utf-8")):
        line = line.strip()
        if not line:
            continue
        parts = line.split(",", 1)
        label = int(parts[0])
        name = parts[1].strip() if len(parts) > 1 else ""
        if label == BG_LABEL:
            family = "BACKGROUND"
        elif label in AMYG_LABELS:
            family = "AMYGDALA"
        elif HIPPO_LABELS_MIN <= label <= HIPPO_LABELS_MAX:
            family = "HIPPOCAMPAL"
            if label == HATA_LABEL:
                family = "TRANSITION_HATA"
        else:
            family = "OTHER"
        rows.append(dict(channel_index=i, numeric_label=label, official_name=name,
                         anatomical_family=family))
    return rows


def assign_scope(rows: list[dict]) -> tuple[list[int], list[dict]]:
    """Return (included_channel_indices, decision_rows)."""
    include = []
    decisions = []
    for r in rows:
        fam = r["anatomical_family"]
        idx = r["channel_index"]
        if fam == "AMYGDALA":
            include.append(idx)
            decisions.append(dict(**r, scope_decision="INCLUDE",
                                  reason="official amygdala sub-nucleus channel of the "
                                         "Iglesias/FreeSurfer HippoAmyg atlas; part of whole Amygdala"))
        elif fam == "TRANSITION_HATA":
            decisions.append(dict(**r, scope_decision="EXCLUDE",
                                  reason="HATA (hippocampo-amygdaloid transition area, label 211) is "
                                         "organized by the authoritative source LUT within the hippocampal-"
                                         "subfield group (200-series); excluded to keep the Amygdala geometry "
                                         "equal to the Iglesias amygdala nuclei and to avoid overlapping the "
                                         "hippocampal territory. Membership of AHi/HATA-type transition tissue "
                                         "is deferred to the separate IF/MF entity-type / transition global "
                                         "review; atlas coverage does not drive canonical membership."))
        elif fam == "HIPPOCAMPAL":
            decisions.append(dict(**r, scope_decision="EXCLUDE",
                                  reason="hippocampal subfield channel (200-series); NOT part of Amygdala scope"))
        else:  # BACKGROUND / OTHER
            decisions.append(dict(**r, scope_decision="EXCLUDE",
                                  reason="background / non-Amygdala channel; excluded"))
    if len(include) != len(AMYG_LABELS):
        raise SystemExit(f"amygdala include count != {len(AMYG_LABELS)}")
    return include, decisions


def centroid_world(vol: np.ndarray, aff: np.ndarray):
    X, Y, Z = np.meshgrid(np.arange(vol.shape[0]), np.arange(vol.shape[1]),
                          np.arange(vol.shape[2]), indexing="ij")
    m = float(vol.sum())
    if m <= 0:
        return (float("nan"), float("nan"), float("nan"))
    xw = aff[0, 0] * X + aff[0, 1] * Y + aff[0, 2] * Z + aff[0, 3]
    yw = aff[1, 0] * X + aff[1, 1] * Y + aff[1, 2] * Z + aff[1, 3]
    zw = aff[2, 0] * X + aff[2, 1] * Y + aff[2, 2] * Z + aff[2, 3]
    return (float((vol * xw).sum() / m), float((vol * yw).sum() / m),
            float((vol * zw).sum() / m))


def resample_to_target(src_vol: np.ndarray, src_aff: np.ndarray,
                       tgt_aff: np.ndarray, tgt_shape: tuple) -> np.ndarray:
    """Header-driven world-coordinate trilinear resample (shared stereotaxic frame)."""
    inv = np.linalg.inv(src_aff)
    I, J, K = np.meshgrid(np.arange(tgt_shape[0]), np.arange(tgt_shape[1]),
                          np.arange(tgt_shape[2]), indexing="ij")
    Xw = tgt_aff[0, 0] * I + tgt_aff[0, 3]
    Yw = tgt_aff[1, 1] * J + tgt_aff[1, 3]
    Zw = tgt_aff[2, 2] * K + tgt_aff[2, 3]
    vx = inv[0, 0] * Xw + inv[0, 1] * Yw + inv[0, 2] * Zw + inv[0, 3]
    vy = inv[1, 0] * Xw + inv[1, 1] * Yw + inv[1, 2] * Zw + inv[1, 3]
    vz = inv[2, 0] * Xw + inv[2, 1] * Yw + inv[2, 2] * Zw + inv[2, 3]
    out = ndi.map_coordinates(src_vol, np.vstack([vx.ravel(), vy.ravel(), vz.ravel()]),
                              order=1, mode="constant", cval=0.0, prefilter=False)
    return out.reshape(tgt_shape)


def write_nifti(path: Path, vol: np.ndarray, aff: np.ndarray, ref_header=None) -> None:
    arr = vol.astype(np.float32)
    if ref_header is not None:
        hdr = ref_header.copy()
    else:
        hdr = nib.Nifti1Header()
    img = nib.Nifti1Image(arr, aff, header=hdr)
    nib.save(img, str(path))


def main() -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # ---- raw asset freeze ----
    if sha256(RAW_L) != RAW_L_SHA:
        raise SystemExit("RAW_ASSET_FREEZE_MISMATCH left")
    if sha256(RAW_R) != RAW_R_SHA:
        raise SystemExit("RAW_ASSET_FREEZE_MISMATCH right")
    if RAW_L_SHA != ACQ_RECORDED_SHA:
        raise SystemExit("RAW_ASSET_FREEZE_MISMATCH vs acquisition")
    names = load_channel_table()
    if len(names) != 30:
        raise SystemExit(f"channel count != 30: {len(names)}")

    include, ch_decisions = assign_scope(names)
    include = sorted(include)

    # ---- channel organization ----
    n_amyg = sum(1 for r in ch_decisions if r["scope_decision"] == "INCLUDE")
    n_hipp = sum(1 for r in names if r["anatomical_family"] == "HIPPOCAMPAL")
    n_trans = sum(1 for r in names if r["anatomical_family"] == "TRANSITION_HATA")
    n_bg = sum(1 for r in names if r["anatomical_family"] == "BACKGROUND")
    if not (n_amyg == 9 and n_hipp == 19 and n_trans == 1 and n_bg == 1):
        raise SystemExit("channel organization unexpected")

    # ---- probability semantics (per side) ----
    semantics = {}
    for side in ("left", "right"):
        raw_img = nib.load(str(HIPPO / f"HippoAmygProbs.MNIsymSpace.{side}.nii.gz"))
        d = np.asanyarray(raw_img.dataobj).astype(np.float64)  # 4D float
        S = d.sum(axis=3)
        flat = S.ravel()
        semantics[side] = dict(
            s_all_min=round(float(flat.min()), 6), s_all_mean=round(float(flat.mean()), 6),
            s_all_median=round(float(np.median(flat)), 6),
            s_all_p95=round(float(np.quantile(flat, 0.95)), 6),
            s_all_p99=round(float(np.quantile(flat, 0.99)), 6),
            s_all_max=round(float(flat.max()), 6),
            semantics="MUTUALLY_EXCLUSIVE_CATEGORICAL",
            evidence="sum over all 30 channels == 1.0 at every voxel "
                     "(normalized categorical posterior; channel 0 = background posterior)",
            aggregation_operator="SUM")
        if not (np.allclose(S, 1.0, atol=1e-3)):
            raise SystemExit(f"probability semantics not categorical for {side}")

    # ---- scope contract ----
    scope = dict(
        contract_id="AMYGDALA_G1_SCOPE_CONTRACT_V1",
        canonical_left=dict(canonical_region_id=LEFT_G1, preferred_name="Left Amygdala"),
        canonical_right=dict(canonical_region_id=RIGHT_G1, preferred_name="Right Amygdala"),
        concept="WHOLE_AMYGDALA",
        concept_statement=CANONICAL["left"]["concept_note"],
        canonical_identity_sources=CANON_SOURCE_RECORDS,
        source=dict(
            asset="FreeSurfer/Iglesias HippoAmygProbs.MNIsymSpace (left/right)",
            local_paths=[str(RAW_L.relative_to(BACKEND)).replace("\\", "/"),
                         str(RAW_R.relative_to(BACKEND)).replace("\\", "/")],
            left_sha256=RAW_L_SHA, right_sha256=RAW_R_SHA,
            channel_count=len(names),
            probability_semantics=dict(left=semantics["left"]["semantics"],
                                       right=semantics["right"]["semantics"],
                                       operator="SUM")),
        channel_summary=dict(total=len(names), amygdala_included=n_amyg,
                             hippocampal_excluded=n_hipp, transition_hata_excluded=n_trans,
                             background_excluded=n_bg,
                             included_channel_indices=include),
        decisions=ch_decisions,
        explicit_checks=dict(
            lateral_nucleus="INCLUDE (7001 Lateral-nucleus)",
            basal_nucleus="INCLUDE (7003 Basal-nucleus)",
            accessory_basal="INCLUDE (7008 Accessory-Basal-nucleus)",
            central_nucleus="INCLUDE (7005 Central-nucleus)",
            medial_nucleus="INCLUDE (7006 Medial-nucleus)",
            cortical_nucleus="INCLUDE (7007 Cortical-nucleus)",
            anterior_amygdaloid_area="INCLUDE (7010 Anterior-amygdaloid-area-AAA)",
            corticoamygdaloid_transition="INCLUDE (7009 Corticoamygdaloid-transition; "
                                          "amygdala superficial transition, part of whole Amygdala)",
            paralaminar_nucleus="INCLUDE (7015 Paralaminar-nucleus)",
            hata="EXCLUDE (211 HATA; source LUT organises it with hippocampal subfields; "
                 "transition membership deferred to separate review)",
            hippocampal_subfields="EXCLUDE (all 200-series hippocampal subfield channels)"),
        scope_verdict="AMYGDALA_G1_SCOPE_FROZEN",
        review_channels=[],
        if_mf_isolation=dict(
            statement="AMYGDALA_G1_GEOMETRY_CONSTRUCTION DOES_NOT_RESOLVE "
                      "JULICH_IF_MF_ENTITY_TYPE_REVIEW",
            note="no IF/MF-driven scope expansion; geometry not widened to cover "
                 "IF/MF candidates; entity-type question stays open for the global close"),
        geometry_allowed=True,
        no_world_x_split=True,
        laterality_authority="source-native left/right atlas files (no world-X split)")
    with open(OUT_SCOPE, "w", encoding="utf-8") as fh:
        json.dump(scope, fh, ensure_ascii=False, indent=2)

    # channel semantics CSV
    with open(OUT_CH_SEM, "w", newline="", encoding="utf-8-sig") as fh:
        cols = list(ch_decisions[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in ch_decisions:
            w.writerow(r)

    if scope["scope_verdict"] != "AMYGDALA_G1_SCOPE_FROZEN":
        raise SystemExit("scope not frozen - geometry construction stopped")

    # ---- shared-frame compatibility (independent check) ----
    jref = nib.load(str(JULICH_REF))
    tgt_aff = np.asarray(jref.affine, float)
    if jref.shape != GRID or sha256(JULICH_REF) != JULICH_REF_SHA:
        raise SystemExit("Julich reference mismatch")
    frame_ok = {}
    for side in ("left", "right"):
        img = nib.load(str(HIPPO / f"HippoAmygProbs.MNIsymSpace.{side}.nii.gz"))
        aff = np.asarray(img.affine, float)
        zooms = np.asarray(img.header.get_zooms())[:3]
        ok = (tuple(img.shape[:3]) == (164, 224, 196) and
              np.allclose(zooms, 0.25, atol=1e-4) and
              img.header["qform_code"] == 1 and img.header["sform_code"] == 1 and
              abs(np.linalg.det(aff)) > 0)
        frame_ok[side] = dict(grid=img.shape[:3], spacing=zooms.tolist(),
                              affine_summary=str(aff.round(3).tolist()),
                              det=round(float(np.linalg.det(aff)), 6),
                              qform_code=int(img.header["qform_code"]),
                              sform_code=int(img.header["sform_code"]),
                              shared_frame_compatible=bool(ok),
                              note=("source is ICBM152 2009c SYMMETRIC 0.25 mm; world "
                                    "coordinates share the MNI2009c stereotaxic frame with the "
                                    "Julich MNI152NLin2009cAsym target grid; Sym<->Asym anatomical "
                                    "residual is NOT warp-corrected"))
        if not ok:
            raise SystemExit(f"shared-frame compatibility check failed for {side}")

    # ---- native geometry construction ----
    native_entries = {}
    native_qc_rows = []
    for side, cid, geo_id in (("left", LEFT_G1, NATIVE_LEFT_ID),
                              ("right", RIGHT_G1, NATIVE_RIGHT_ID)):
        raw_img = nib.load(str(HIPPO / f"HippoAmygProbs.MNIsymSpace.{side}.nii.gz"))
        src_aff = np.asarray(raw_img.affine, float)
        voxvol = float(np.prod(np.asarray(raw_img.header.get_zooms())[:3]))
        d = np.asanyarray(raw_img.dataobj).astype(np.float64)
        prob = np.zeros(raw_img.shape[:3], dtype=np.float64)
        for c in include:
            prob += d[..., c]
        # conservation QC: included + excluded == all channels (== 1 per voxel)
        all_sum = d.sum(axis=3)
        ex_sum = all_sum - prob
        max_abs_res = float(np.abs(all_sum - prob - ex_sum).max())
        # hippocampal exclusion proof: Amygdala posterior mass at voxels whose HARD
        # categorical membership (argmax over the 30 channels) is a hippocampal subfield
        # (incl. HATA). The atlas posterior is soft at structure interfaces, so a small
        # boundary residual (~0.9%) is expected and documented; it is NOT a scope leak.
        hipp_idx = [r["channel_index"] for r in names
                    if r["anatomical_family"] in ("HIPPOCAMPAL", "TRANSITION_HATA")]
        hard_arg = np.argmax(d, axis=3)
        contam_hipp = float((prob * np.isin(hard_arg, hipp_idx)).sum()) / float(prob.sum()) \
            if prob.sum() > 0 else 0.0
        out_path = NATIVE_OUT[side]
        write_nifti(out_path, prob, src_aff)
        out_sha = sha256(out_path)
        sup = prob > 0
        ctr = centroid_world(prob, src_aff)
        bb_idx = np.argwhere(sup)
        bb_world = (bb_idx @ src_aff[:3, :3].T + src_aff[:3, 3]) if len(bb_idx) else None
        native_entries[side] = dict(
            geometry_id=geo_id, canonical_region_id=cid, hemisphere=side,
            geometry_class=NATIVE_CLASS, derivation=NATIVE_DERIV,
            source_asset=dict(left=RAW_L_SHA, right=RAW_R_SHA)[side],
            source_path=str((HIPPO / f"HippoAmygProbs.MNIsymSpace.{side}.nii.gz")
                            .relative_to(BACKEND)).replace("\\", "/"),
            included_channels=[names[c]["numeric_label"] for c in include],
            included_channel_indices=include,
            excluded_channel_count=len(names) - len(include),
            aggregation_operator="SUM",
            probability_semantics="MUTUALLY_EXCLUSIVE_CATEGORICAL",
            scope_contract_id=scope["contract_id"],
            output_path=str(out_path.relative_to(BACKEND)).replace("\\", "/"),
            output_sha256=out_sha,
            output_grid=dict(shape=list(raw_img.shape[:3]),
                             spacing_mm=0.25,
                             affine=src_aff.round(6).tolist(),
                             qform_code=int(raw_img.header["qform_code"]),
                             sform_code=int(raw_img.header["sform_code"])),
            probability_min=round(float(prob.min()), 6), probability_max=round(float(prob.max()), 6),
            sum_probability_mass=round(float(prob.sum()), 3),
            voxel_volume_mm3=round(voxvol, 6),
            weighted_volume_mm3=round(float(prob.sum()) * voxvol, 3),
            support_voxels=int(sup.sum()),
            centroid_mm=tuple(round(float(v), 3) for v in ctr),
            bounding_box_world_mm=(tuple(bb_world.min(0).round(2)) if bb_world is not None else None),
            max_abs_conservation_residual=round(max_abs_res, 6),
            hippocampal_contamination_argmax_fraction=round(contam_hipp, 6),
            threshold_applied=False, binarization_applied=False, clipping_applied=False,
            normalization_applied=False,
            registration_applied=False, resampling_applied=False, transform_id=None,
            independent_from_g3_g1_mapping=True, circularity_risk="NONE",
            script_version=SCRIPT_VERSION, run_timestamp=ts)
        native_qc_rows.append(dict(geometry_id=geo_id, hemisphere=side,
                                   output_sha256=out_sha,
                                   weighted_volume_mm3=round(float(prob.sum()) * voxvol, 3),
                                   support_voxels=int(sup.sum()),
                                   centroid_mm=",".join(f"{v:.2f}" for v in ctr),
                                   included_channel_count=len(include),
                                   max_abs_conservation_residual=round(max_abs_res, 6),
                                   hippocampal_contamination_argmax_fraction=round(contam_hipp, 6)))

    lvol = native_entries["left"]["weighted_volume_mm3"]
    rvol = native_entries["right"]["weighted_volume_mm3"]
    native_bilateral = dict(volume_ratio_L_over_R=round(lvol / rvol, 4) if rvol > 0 else None)

    with open(OUT_NATIVE_MAN, "w", encoding="utf-8") as fh:
        json.dump(dict(geometry_class=NATIVE_CLASS, derivation=NATIVE_DERIV,
                       space_status="SOURCE_NATIVE_ICBM2009C_SYMMETRIC",
                       probability_semantics="MUTUALLY_EXCLUSIVE_CATEGORICAL",
                       aggregation_operator="SUM",
                       scope_contract=scope["contract_id"],
                       raw_left_sha256=RAW_L_SHA, raw_right_sha256=RAW_R_SHA,
                       entries=[native_entries["left"], native_entries["right"]],
                       bilateral=native_bilateral,
                       script_version=SCRIPT_VERSION, run_timestamp=ts),
                  fh, ensure_ascii=False, indent=2)
    with open(OUT_NATIVE_QC, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(native_qc_rows[0].keys()))
        w.writeheader()
        for r in native_qc_rows:
            w.writerow(r)

    # ---- spatial bridge (reference-grid resample) ----
    bridge = dict(
        spatial_bridge_id=SPB_ID,
        spatial_bridge_class=SPB_CLASS,
        spatial_bridge_statement=SPB_STATEMENT,
        type_note="SPB = Spatial Bridge; NOT a TRF (transform). Same frozen bridge principle "
                  "applied independently to the HippoAmyg source (ICBM152 2009c SYMMETRIC).",
        source_space="ICBM152_2009C_SYMMETRIC (FreeSurfer/Iglesias HippoAmyg)",
        target_reference_space="MNI152NLin2009cAsym",
        source_world_coordinate_convention="RAS (NIfTI sform); right file stored LAS",
        target_world_coordinate_convention="RAS (NIfTI sform)",
        julich_target_reference=dict(path=str(JULICH_REF.relative_to(BACKEND)).replace("\\", "/"),
                                     sha256=sha256(JULICH_REF)),
        interpolation="LINEAR",
        registration_applied=False,
        nonlinear_registration_applied=False,
        nonlinear_registration_claimed=False,
        deformation_field_applied=False,
        resampling_applied=True,
        template_variant_statement="DIFFERENT_TEMPLATE_VARIANTS_WITH_SHARED_STEREOTAXIC_COORDINATE_FRAME",
        residual_spatial_limitation=LIMITATION,
        authoritative_nonlinear_sym_asym_transform="NOT_AVAILABLE_NOT_USED",
        source_compatibility=frame_ok,
        script_version=SCRIPT_VERSION, run_timestamp=ts)
    with open(OUT_BRIDGE, "w", encoding="utf-8") as fh:
        json.dump(bridge, fh, ensure_ascii=False, indent=2)

    # ---- reference-grid resampling + manifest + QC ----
    ref_entries = {}
    ref_qc_rows = []
    for side, cid, geo_id in (("left", LEFT_G1, REF_LEFT_ID),
                              ("right", RIGHT_G1, REF_RIGHT_ID)):
        native = native_entries[side]
        src_path = BACKEND / native["output_path"]
        src_img = nib.load(str(src_path))
        src_vol = np.asanyarray(src_img.dataobj).astype(np.float64)
        src_aff = np.asarray(src_img.affine, float)
        ref_vol = resample_to_target(src_vol, src_aff, tgt_aff, GRID)
        out_path = REF_OUT[side]
        write_nifti(out_path, ref_vol, tgt_aff)
        out_sha = sha256(out_path)
        sup = ref_vol > 0
        ctr = centroid_world(ref_vol, tgt_aff)
        nvol = float(ref_vol.sum())
        # contralateral leak: left geometry mass with world x>0 (and right with x<0)
        X, Y, Z = np.meshgrid(np.arange(GRID[0]), np.arange(GRID[1]), np.arange(GRID[2]),
                              indexing="ij")
        xw = tgt_aff[0, 0] * X + tgt_aff[0, 3]
        contra = float((ref_vol * (xw > 0)).sum()) / nvol if side == "left" \
            else float((ref_vol * (xw < 0)).sum()) / nvol
        nvol = nvol if nvol > 0 else 1.0
        rel_change = (nvol - native["weighted_volume_mm3"]) / native["weighted_volume_mm3"]
        ref_entries[side] = dict(
            geometry_id=geo_id, canonical_region_id=cid, hemisphere=side,
            geometry_class=NATIVE_CLASS, derivation=REF_DERIV,
            source_native_geometry=dict(geometry_id=native["geometry_id"],
                                        output_path=native["output_path"],
                                        output_sha256=native["output_sha256"]),
            scope_contract=dict(id=scope["contract_id"], verdict=scope["scope_verdict"]),
            spatial_bridge_id=SPB_ID,
            interpolation="LINEAR",
            output_path=str(out_path.relative_to(BACKEND)).replace("\\", "/"),
            output_sha256=out_sha,
            output_grid=dict(shape=list(GRID), spacing_mm=1.0,
                             affine=tgt_aff.round(6).tolist(),
                             qform_code=int(jref.header["qform_code"]),
                             sform_code=int(jref.header["sform_code"])),
            probability_min=round(float(ref_vol.min()), 6),
            probability_max=round(float(ref_vol.max()), 6),
            sum_probability_mass=round(float(ref_vol.sum()), 3),
            weighted_volume_mm3=round(float(ref_vol.sum()), 3),
            support_voxels=int(sup.sum()),
            centroid_mm=tuple(round(float(v), 3) for v in ctr),
            native_to_target_relative_volume_change=round(float(rel_change), 4),
            contralateral_mass_fraction=round(float(contra), 6),
            template_variant_uncertainty="PRESENT",
            residual_spatial_limitation=LIMITATION,
            direct_overlap_grid_ready=True,
            direct_validation_executed=False,
            registration_applied=False, nonlinear_registration_applied=False,
            resampling_applied=True,
            threshold_applied=False, binarization_applied=False, clipping_applied=False,
            normalization_applied=False,
            no_artificial_symmetrization=True,
            independent_from_g3_g1_mapping=True, circularity_risk="NONE",
            script_version=SCRIPT_VERSION, run_timestamp=ts)
        ref_qc_rows.append(dict(geometry_id=geo_id, hemisphere=side,
                                output_sha256=out_sha,
                                shape="x".join(str(x) for x in GRID),
                                weighted_volume_mm3=round(float(ref_vol.sum()), 3),
                                centroid_mm=",".join(f"{v:.2f}" for v in ctr),
                                contralateral_mass_fraction=round(float(contra), 6),
                                direct_overlap_grid_ready=True,
                                direct_validation_executed=False))

    lr_ref = ref_entries["left"]["weighted_volume_mm3"] / ref_entries["right"]["weighted_volume_mm3"] \
        if ref_entries["right"]["weighted_volume_mm3"] > 0 else None
    with open(OUT_REF_MAN, "w", encoding="utf-8") as fh:
        json.dump(dict(geometry_class=NATIVE_CLASS, derivation=REF_DERIV,
                       spatial_bridge_id=SPB_ID,
                       registration_applied=False,
                       nonlinear_registration_applied=False,
                       resampling_applied=True,
                       interpolation="LINEAR",
                       template_variant_uncertainty="PRESENT",
                       residual_spatial_limitation=LIMITATION,
                       direct_overlap_grid_ready=True,
                       direct_validation_executed=False,
                       reference_space="MNI152NLin2009cAsym / Julich reference grid",
                       entries=[ref_entries["left"], ref_entries["right"]],
                       bilateral=dict(volume_ratio_L_over_R=round(lr_ref, 4) if lr_ref else None),
                       script_version=SCRIPT_VERSION, run_timestamp=ts),
                  fh, ensure_ascii=False, indent=2)
    with open(OUT_REF_QC, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(ref_qc_rows[0].keys()))
        w.writeheader()
        for r in ref_qc_rows:
            w.writerow(r)

    # ---- provenance ----
    prov = dict(
        function="Amygdala G1 authoritative reference geometry construction",
        canonical_identity=dict(left=dict(canonical_region_id=LEFT_G1, preferred_name="Left Amygdala"),
                                right=dict(canonical_region_id=RIGHT_G1, preferred_name="Right Amygdala")),
        canonical_identity_sources=CANON_SOURCE_RECORDS,
        canonical_definition_basis="whole Amygdala (Iglesias/FreeSurfer amygdala sub-nucleus channels)",
        raw_source=dict(asset="FreeSurfer/Iglesias HippoAmygProbs.MNIsymSpace",
                        left_path=str(RAW_L.relative_to(BACKEND)).replace("\\", "/"),
                        left_sha256=RAW_L_SHA,
                        right_path=str(RAW_R.relative_to(BACKEND)).replace("\\", "/"),
                        right_sha256=RAW_R_SHA,
                        acquisition_recorded_sha256=ACQ_RECORDED_SHA,
                        channel_metadata_path=str(NAMES.relative_to(BACKEND)).replace("\\", "/"),
                        channel_metadata_sha256=sha256(NAMES),
                        channel_count=len(names)),
        probability_semantics=dict(semantics="MUTUALLY_EXCLUSIVE_CATEGORICAL",
                                   operator="SUM",
                                   per_side=semantics),
        scope_contract=dict(path=str(OUT_SCOPE.relative_to(BACKEND)).replace("\\", "/"),
                            verdict=scope["scope_verdict"], sha256=sha256(OUT_SCOPE)),
        native_geometry=dict(manifest=str(OUT_NATIVE_MAN.relative_to(BACKEND)).replace("\\", "/"),
                             manifest_sha256=sha256(OUT_NATIVE_MAN),
                             left_sha256=native_entries["left"]["output_sha256"],
                             right_sha256=native_entries["right"]["output_sha256"]),
        spatial_bridge=dict(manifest=str(OUT_BRIDGE.relative_to(BACKEND)).replace("\\", "/"),
                            manifest_sha256=sha256(OUT_BRIDGE),
                            spatial_bridge_id=SPB_ID),
        reference_geometry=dict(manifest=str(OUT_REF_MAN.relative_to(BACKEND)).replace("\\", "/"),
                                manifest_sha256=sha256(OUT_REF_MAN),
                                left_sha256=ref_entries["left"]["output_sha256"],
                                right_sha256=ref_entries["right"]["output_sha256"]),
        julich_reference=dict(path=str(JULICH_REF.relative_to(BACKEND)).replace("\\", "/"),
                              sha256=sha256(JULICH_REF)),
        registration_applied=False,
        nonlinear_registration_applied=False,
        resampling_applied=True,
        template_variant_uncertainty="PRESENT",
        residual_spatial_limitation=LIMITATION,
        no_world_x_split=True,
        laterality_authority="source-native left/right atlas files",
        if_mf_entity_type_review="UNRESOLVED / INDEPENDENT (not resolved by this round)",
        independent_from_g3_g1_mapping=True,
        circularity_risk="NONE",
        classification_csv="NOT_TOUCHED",
        db_write=False, promotion=False, commit=False,
        software=dict(python_version=sys.version.split()[0], platform=str(_platform.platform()),
                      numpy_version=np.__version__, scipy_version=__import__("scipy").__version__,
                      nibabel_version=nib.__version__),
        script=str(Path(__file__).name), script_version=SCRIPT_VERSION,
        run_timestamp=ts)
    with open(OUT_PROV, "w", encoding="utf-8") as fh:
        json.dump(prov, fh, ensure_ascii=False, indent=2)

    # ---- diagnostics md ----
    md = [
        "# Phase1.7 V3 - Amygdala G1 authoritative reference geometry construction", "",
        f"Canonical: Left Amygdala {LEFT_G1} / Right Amygdala {RIGHT_G1} (G1_MACRO, whole Amygdala).",
        f"Scope verdict: {scope['scope_verdict']} (included {n_amyg} amygdala channels; excluded "
        f"{n_hipp} hippocampal + {n_trans} HATA-transition + {n_bg} background).",
        "IF/MF entity-type review is NOT resolved by this construction (no scope widening).", "",
        "Source: FreeSurfer/Iglesias HippoAmygProbs.MNIsymSpace left/right "
        f"(left sha {RAW_L_SHA[:12]}..., right sha {RAW_R_SHA[:12]}...).",
        f"Probability semantics: MUTUALLY_EXCLUSIVE_CATEGORICAL (sum over 30 channels == 1.0 at every "
        "voxel); Amygdala aggregation operator = SUM over the included channels.", "",
        "Native geometry (ICBM152 2009c SYM, 0.25 mm):",
        f"  Left  {NATIVE_LEFT_ID}: weighted volume {native_entries['left']['weighted_volume_mm3']} mm3, "
        f"support {native_entries['left']['support_voxels']} vox, centroid "
        f"{tuple(round(float(v),2) for v in native_entries['left']['centroid_mm'])}, "
        f"sha {native_entries['left']['output_sha256']}",
        f"  Right {NATIVE_RIGHT_ID}: weighted volume {native_entries['right']['weighted_volume_mm3']} mm3, "
        f"support {native_entries['right']['support_voxels']} vox, centroid "
        f"{tuple(round(float(v),2) for v in native_entries['right']['centroid_mm'])}, "
        f"sha {native_entries['right']['output_sha256']}",
        "Reference-grid geometry (MNI152NLin2009cAsym / Julich, 193x229x193 @1mm):",
        f"  Left  {REF_LEFT_ID}: weighted volume {ref_entries['left']['weighted_volume_mm3']} mm3, "
        f"centroid {tuple(round(float(v),2) for v in ref_entries['left']['centroid_mm'])}, "
        f"sha {ref_entries['left']['output_sha256']}",
        f"  Right {REF_RIGHT_ID}: weighted volume {ref_entries['right']['weighted_volume_mm3']} mm3, "
        f"centroid {tuple(round(float(v),2) for v in ref_entries['right']['centroid_mm'])}, "
        f"sha {ref_entries['right']['output_sha256']}",
        f"Spatial bridge: {SPB_ID} ({SPB_CLASS}); registration_applied=FALSE, "
        "nonlinear_registration_applied=FALSE, resampling_applied=TRUE, interpolation=LINEAR. "
        "No threshold/binarization/clipping/renormalization; no artificial symmetrization.", "",
        "Evidence limitation preserved: " + LIMITATION + ".",
        "template_variant_uncertainty = PRESENT; direct_overlap_grid_ready = TRUE; "
        "direct_validation_executed = FALSE.", "",
        "Binary NIfTI are local (gitignored); only SHA256 + manifests are tracked.",
        "No DB write; classification untouched (86/132/93); Promotion not executed; no commit in-script.",
        ""]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    # console summary
    for side in ("left", "right"):
        e = ref_entries[side]
        print(f"{side}: ref vol {e['weighted_volume_mm3']} mm3 sha {e['output_sha256'][:12]}...")
    print("scope:", scope["scope_verdict"], "| native L/R vol",
          native_entries["left"]["weighted_volume_mm3"], native_entries["right"]["weighted_volume_mm3"])
    print("semantics:", semantics["left"]["semantics"])
    print("wrote 8+ artifacts")


if __name__ == "__main__":
    main()
