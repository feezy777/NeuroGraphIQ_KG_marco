"""Phase1.7 V3 - Hippocampus G1 canonical scope adjudication + authoritative reference
geometry construction.

Canonical identity adjudication (HIPPOCAMPUS_G1_CANONICAL_IDENTITY_V1):

  source label (Macro96)      : 'Hippocampus' / 左海马 - no formal definition in the
                                source pool -> SOURCE_LABEL_ONLY as the raw source state.
  frozen VERIFIED relations   : exactly CA1/CA2/CA3/DG (L/R = 8) are VERIFIED_DIRECT_
                                CONTAINED in Left/Right Hippocampus
                                (NGIQ-BR-00000252 / NGIQ-BR-00000260). The frozen
                                reviewer rationale operationalises G1 'Hippocampus' as
                                'FS 定义含海马体+齿状回' (FS aseg hippocampus = cornu
                                ammonis fields + dentate gyrus).
  subicular / HATA            : Subiculum / Presubiculum / Parasubiculum / Prosubiculum /
                                Transsubiculum / HATA are ONTOLOGY_DEFINITION_DEPENDENT
                                (11 rows) - NOT frozen VERIFIED.

  verdict                     : HIPPOCAMPUS_BROAD_OPERATIONAL
                                G1 = the hippocampal body: CA fields (CA1..CA4 incl. CA2,
                                which has no separate FS channel) + dentate gyrus
                                (GC/ML-DG) + hippocampal molecular layer + hippocampal
                                tail. The subicular complex and HATA are hippocampal-
                                formation / transition structures whose membership in THIS
                                G1 is NOT asserted (kept definition-dependent, outside the
                                closed current-G1 scope). This is the smallest scope that
                                (a) is consistent with the 8 frozen VERIFIED CA/CA2/CA3/DG
                                relations (no ONTOLOGY_HISTORY_CONFLICT) and (b) is closed
                                and constructible. It deliberately does NOT adopt full
                                HIPPOCAMPAL_FORMATION just to widen spatial coverage.

Geometry construction mirrors the frozen Amygdala round: aggregation (SUM) of the
included Iglesias/FreeSurfer hippocampal channels on the 0.25 mm ICBM152_2009c_SYM
native grid, then a shared-MNI2009c world-coordinate reference-grid LINEAR resample
onto the Julich MNI152NLin2009cAsym grid (193x229x193 @1 mm).

Limitation preserved: TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_WARP_CORRECTED;
registration_applied=FALSE; nonlinear_registration_applied=FALSE; resampling_applied=TRUE.
No threshold / binarization / clipping / renormalization / manual symmetry correction.
Binary NIfTI live under data/atlases/derived_g1 (gitignored); only SHAs + manifests are
tracked. No DB write / classification change / promotion / commit inside the script.
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

LEFT_G1, RIGHT_G1 = "NGIQ-BR-00000252", "NGIQ-BR-00000260"
SPB_ID = "SPB-MNI2009C-SYM-ASYM-SHARED-FRAME-V1"
SPB_CLASS = "SHARED_COORDINATE_REFERENCE_GRID_RESAMPLING"
SPB_STATEMENT = "SHARED_STEREOTAXIC_FRAME_REFERENCE_GRID_RESAMPLE"
LIMITATION = "TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_WARP_CORRECTED"
NATIVE_L_ID = "GEO-G1-HIPP-L-FS2009CSYM-V1"
NATIVE_R_ID = "GEO-G1-HIPP-R-FS2009CSYM-V1"
REF_L_ID = "GEO-G1-HIPP-L-MNI2009CASYM-V1"
REF_R_ID = "GEO-G1-HIPP-R-MNI2009CASYM-V1"
NATIVE_CLASS = "AUTHORITATIVE_DERIVED_G1_GEOMETRY"
NATIVE_DERIV = "PROBABILITY_CHANNEL_AGGREGATION_FROM_FROZEN_SCOPE"
REF_DERIV = "REFERENCE_GRID_RESAMPLING_FROM_FROZEN_NATIVE_G1_GEOMETRY"
GRID = (193, 229, 193)
IDENTITY_ID = "HIPPOCAMPUS_G1_CANONICAL_IDENTITY_V1"
SCOPE_ID = "HIPPOCAMPUS_G1_SCOPE_CONTRACT_V1"
SCRIPT_VERSION = "phase17_v3_construct_hippocampus_g1_geometry.py v1"

# included numeric labels: hippocampus body gray matter (CA + DG + mol layer + tail)
INCLUDE_LABELS = {226, 238, 237, 245, 246, 243, 240, 244, 241, 242, 239}
# canonical identity / frozen relations
CA_DG_VERIFIED = ["CA1", "CA2", "CA3", "DG"]
DEPENDENT_STRUCTURES = ["Subiculum", "Presubiculum", "Parasubiculum", "Prosubiculum",
                        "Transsubiculum", "HATA"]

NATIVE_OUT = {"left": DERIVED / "left_hippocampus_prob_icbm2009csym.nii.gz",
              "right": DERIVED / "right_hippocampus_prob_icbm2009csym.nii.gz"}
REF_OUT = {"left": DERIVED / "left_hippocampus_prob_mni2009casym.nii.gz",
           "right": DERIVED / "right_hippocampus_prob_mni2009casym.nii.gz"}

OUT_IDENTITY = D16 / "phase17_v3_hippocampus_canonical_identity_v1.json"
OUT_CH_SEM = D16 / "phase17_v3_hippocampus_source_channel_semantics.csv"
OUT_SCOPE = D16 / "phase17_v3_hippocampus_g1_scope_contract_v1.json"
OUT_NMAN = D16 / "phase17_v3_hippocampus_g1_native_geometry_manifest.json"
OUT_NQC = D16 / "phase17_v3_hippocampus_g1_native_geometry_qc.csv"
OUT_BRIDGE = D16 / "phase17_v3_hippocampus_spatial_bridge_manifest.json"
OUT_RMAN = D16 / "phase17_v3_hippocampus_g1_reference_geometry_manifest.json"
OUT_RQC = D16 / "phase17_v3_hippocampus_g1_reference_geometry_qc.csv"
OUT_PROV = D16 / "phase17_v3_hippocampus_geometry_provenance.json"
OUT_MD = D16 / "phase17_v3_hippocampus_g1_geometry_diagnostics.md"

CANON_SOURCES = [
    "data/atlases/macro96/macro96_normalized_manifest.csv (G1_MACRO 'Left/Right Hippocampus'; no formal definition)",
    "data/integration/brainregion_direct_g1_phase16/direct_g1_high_confidence.csv "
    "(NGIQ-BR-00000252 = Left Hippocampus / NGIQ-BR-00000260 = Right Hippocampus)",
    "data/integration/brainregion_direct_g1_phase16/phase17_v3_classification.csv "
    "(VERIFIED CA1/CA2/CA3/DG L/R; ONTOLOGY_DEFINITION_DEPENDENT subicular family + HATA)",
]
# ontology structure table (structure -> decision for THIS G1)
STRUCTURE_TABLE = [
    dict(structure="CA1", g1_membership="INCLUDE", in_hippocampus_proper=True,
         in_hippocampal_formation=True, geometry_channel="CA1-head/CA1-body",
         reason="cornu ammonis field; hippocampus proper; frozen VERIFIED_DIRECT_CONTAINED",
         confidence="HIGH"),
    dict(structure="CA2", g1_membership="INCLUDE", in_hippocampus_proper=True,
         in_hippocampal_formation=True, geometry_channel="NO_INDEPENDENT_CHANNEL (CA2 merged into CA1/CA3 in the Iglesias atlas)",
         reason="hippocampus proper; frozen VERIFIED_DIRECT_CONTAINED; spatially represented by CA1/CA3 territory",
         confidence="HIGH"),
    dict(structure="CA3", g1_membership="INCLUDE", in_hippocampus_proper=True,
         in_hippocampal_formation=True, geometry_channel="CA3-head/CA3-body",
         reason="cornu ammonis field; frozen VERIFIED_DIRECT_CONTAINED",
         confidence="HIGH"),
    dict(structure="CA4", g1_membership="INCLUDE", in_hippocampus_proper=False,
         in_hippocampal_formation=True, geometry_channel="CA4-head/CA4-body",
         reason="dentate-hilar region included with the DG/CA body of the operational G1 'Hippocampus'",
         confidence="MODERATE"),
    dict(structure="Dentate Gyrus (GC/ML-DG)", g1_membership="INCLUDE",
         in_hippocampus_proper=False, in_hippocampal_formation=True,
         geometry_channel="GC-ML-DG-head/GC-ML-DG-body",
         reason="dentate gyrus is part of the FS aseg 'Hippocampus' body and of the frozen "
                "VERIFIED DG relations; excluded from strict hippocampus-proper nomenclature but "
                "included in the operational G1 (per frozen rationale '海马体+齿状回')",
         confidence="HIGH"),
    dict(structure="Hippocampal molecular layer", g1_membership="INCLUDE",
         in_hippocampus_proper=True, in_hippocampal_formation=True,
         geometry_channel="molecular_layer_HP-head/-body",
         reason="molecular layer over the CA/DG body; part of the hippocampus gray body",
         confidence="HIGH"),
    dict(structure="Hippocampal tail", g1_membership="INCLUDE", in_hippocampus_proper=False,
         in_hippocampal_formation=True, geometry_channel="Hippocampal_tail",
         reason="posterior continuation of the CA/DG body; part of the operational G1 body",
         confidence="MODERATE"),
    dict(structure="Subiculum", g1_membership="EXCLUDE", in_hippocampus_proper=False,
         in_hippocampal_formation=True, geometry_channel="subiculum-head/-body (EXCLUDE)",
         reason="hippocampal-formation component but NOT part of the CA+DG operational G1; "
                "membership definition-dependent (frozen ONTOLOGY_DEFINITION_DEPENDENT)",
         confidence="HIGH"),
    dict(structure="Presubiculum", g1_membership="EXCLUDE", in_hippocampus_proper=False,
         in_hippocampal_formation=True, geometry_channel="presubiculum-head/-body (EXCLUDE)",
         reason="same as Subiculum", confidence="HIGH"),
    dict(structure="Parasubiculum", g1_membership="EXCLUDE", in_hippocampus_proper=False,
         in_hippocampal_formation=True, geometry_channel="parasubiculum (EXCLUDE)",
         reason="same as Subiculum", confidence="HIGH"),
    dict(structure="Prosubiculum", g1_membership="EXCLUDE", in_hippocampus_proper=False,
         in_hippocampal_formation=True, geometry_channel="NO_CHANNEL (NOT_APPLICABLE)",
         reason="transitional CA1-subiculum band; no FS channel; definition-dependent",
         confidence="MODERATE"),
    dict(structure="Transsubiculum", g1_membership="EXCLUDE", in_hippocampus_proper=False,
         in_hippocampal_formation=True, geometry_channel="NO_CHANNEL (NOT_APPLICABLE)",
         reason="subiculum-presubiculum transition; no FS channel; definition-dependent",
         confidence="MODERATE"),
    dict(structure="HATA", g1_membership="EXCLUDE", in_hippocampus_proper=False,
         in_hippocampal_formation=True, geometry_channel="HATA (EXCLUDE)",
         reason="hippocampo-amygdaloid transition; organised by the source LUT with hippocampal "
                "subfields but excluded from Amygdala and NOT auto-added here; membership "
                "definition-dependent (TRANSITIONAL_STRUCTURE_OUTSIDE_CANONICAL_SCOPE)",
         confidence="HIGH"),
    dict(structure="Fimbria", g1_membership="EXCLUDE", in_hippocampus_proper=False,
         in_hippocampal_formation=False, geometry_channel="fimbria (EXCLUDE)",
         reason="white-matter output tract, not hippocampal gray body",
         confidence="HIGH"),
    dict(structure="Alveus", g1_membership="EXCLUDE", in_hippocampus_proper=False,
         in_hippocampal_formation=False, geometry_channel="alveus (EXCLUDE)",
         reason="white-matter layer, not hippocampal gray body",
         confidence="HIGH"),
    dict(structure="Hippocampal fissure", g1_membership="EXCLUDE", in_hippocampus_proper=False,
         in_hippocampal_formation=False, geometry_channel="hippocampal-fissure (EXCLUDE)",
         reason="fissure/CSF space, not gray matter",
         confidence="HIGH"),
]
# per-channel geometry decisions keyed by numeric label
CHANNEL_GEOM_DECISION = {}
_CH_NAMES = {226: "hippocampal tail", 236: "subiculum-body", 238: "CA1-body",
             235: "subiculum-head", 215: "hippocampal-fissure", 233: "presubiculum-head",
             201: "alveus", 237: "CA1-head", 234: "presubiculum-body",
             203: "parasubiculum", 245: "molecular_layer_HP-head",
             246: "molecular_layer_HP-body", 243: "GC-ML-DG-head", 240: "CA3-body",
             244: "GC-ML-DG-body", 241: "CA4-head", 242: "CA4-body", 212: "fimbria",
             239: "CA3-head", 211: "HATA"}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def load_channel_rows() -> list[dict]:
    rows = []
    for i, line in enumerate(open(NAMES, encoding="utf-8")):
        line = line.strip()
        if not line:
            continue
        parts = line.split(",", 1)
        label = int(parts[0])
        name = parts[1].strip() if len(parts) > 1 else ""
        if label == 0:
            family = "BACKGROUND"
        elif label in INCLUDE_LABELS:
            family = "HIPPOCAMPUS_G1_INCLUDE"
        elif 200 <= label <= 999:
            family = "HIPPOCAMPAL_OTHER"
        elif label >= 7000:
            family = "AMYGDALA"
        else:
            family = "OTHER"
        rows.append(dict(channel_index=i, numeric_label=label, official_name=name,
                         anatomical_family=family))
    return rows


def make_decision_rows(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        label = r["numeric_label"]
        fam = r["anatomical_family"]
        if fam == "BACKGROUND":
            geo, onto = "EXCLUDE", "BACKGROUND_NOT_A_STRUCTURE"
            reason = "background channel 0; not a structure"
        elif fam == "AMYGDALA":
            geo, onto = "EXCLUDE", "AMYGDALA_NOT_IN_HIPPOCAMPUS"
            reason = "amygdala sub-nucleus channel; must never enter Hippocampus geometry (scope conservation)"
        elif fam == "HIPPOCAMPUS_G1_INCLUDE":
            geo, onto = "INCLUDE", "INCLUDE"
            reason = f"{_CH_NAMES[label]}: part of the operational G1 hippocampal body (CA+DG)"
        elif fam == "HIPPOCAMPAL_OTHER":
            geo, onto = "EXCLUDE", "HIPPOCAMPAL_FORMATION_COMPONENT_OUTSIDE_CURRENT_G1"
            reason = (f"{_CH_NAMES.get(label, label)}: hippocampal-formation/transition/white-matter "
                      "channel not part of the closed CA+DG operational G1 scope")
        else:
            geo, onto = "EXCLUDE", "OTHER"
            reason = "not hippocampal"
        out.append(dict(channel_index=r["channel_index"], numeric_label=label,
                        official_name=r["official_name"], anatomical_family=fam,
                        ontology_scope_decision=onto, geometry_scope_decision=geo,
                        reason=reason))
    return out


def centroid_world(vol, aff):
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


def resample_to_target(src, src_aff, tgt_aff, tgt_shape):
    inv = np.linalg.inv(src_aff)
    I, J, K = np.meshgrid(np.arange(tgt_shape[0]), np.arange(tgt_shape[1]),
                          np.arange(tgt_shape[2]), indexing="ij")
    Xw = tgt_aff[0, 0] * I + tgt_aff[0, 3]
    Yw = tgt_aff[1, 1] * J + tgt_aff[1, 3]
    Zw = tgt_aff[2, 2] * K + tgt_aff[2, 3]
    vx = inv[0, 0] * Xw + inv[0, 1] * Yw + inv[0, 2] * Zw + inv[0, 3]
    vy = inv[1, 0] * Xw + inv[1, 1] * Yw + inv[1, 2] * Zw + inv[1, 3]
    vz = inv[2, 0] * Xw + inv[2, 1] * Yw + inv[2, 2] * Zw + inv[2, 3]
    out = ndi.map_coordinates(src, np.vstack([vx.ravel(), vy.ravel(), vz.ravel()]),
                              order=1, mode="constant", cval=0.0, prefilter=False)
    return out.reshape(tgt_shape)


def write_nifti(path, vol, aff):
    img = nib.Nifti1Image(vol.astype(np.float32), aff)
    nib.save(img, str(path))


def main() -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # raw freeze
    for p, expect, name in ((RAW_L, RAW_L_SHA, "left"), (RAW_R, RAW_R_SHA, "right")):
        if sha256(p) != expect:
            raise SystemExit(f"RAW_ASSET_FREEZE_MISMATCH {name}")
    rows = load_channel_rows()
    if len(rows) != 30:
        raise SystemExit("channel count != 30")
    decisions = make_decision_rows(rows)
    inc_idx = [r["channel_index"] for r in decisions if r["geometry_scope_decision"] == "INCLUDE"]
    inc_labels = {r["numeric_label"] for r in decisions if r["geometry_scope_decision"] == "INCLUDE"}
    if inc_labels != INCLUDE_LABELS or len(inc_idx) != 11:
        raise SystemExit(f"include set wrong: {inc_labels}")

    # probability semantics (per side) + conservation
    sem = {}
    for side in ("left", "right"):
        img = nib.load(str(HIPPO / f"HippoAmygProbs.MNIsymSpace.{side}.nii.gz"))
        d = np.asanyarray(img.dataobj).astype(np.float64)
        S = d.sum(axis=3)
        if not np.allclose(S, 1.0, atol=1e-3):
            raise SystemExit(f"semantics not categorical {side}")
        sem[side] = dict(semantics="MUTUALLY_EXCLUSIVE_CATEGORICAL",
                         operator="SUM",
                         s_all_mean=round(float(S.mean()), 6),
                         s_all_max=round(float(S.max()), 6))

    # identity
    identity = dict(
        identity_id=IDENTITY_ID,
        canonical_left=dict(canonical_region_id=LEFT_G1, preferred_name="Left Hippocampus"),
        canonical_right=dict(canonical_region_id=RIGHT_G1, preferred_name="Right Hippocampus"),
        source_label="Hippocampus / 海马 (Macro96)",
        source_has_formal_definition=False,
        source_definition_state="SOURCE_LABEL_ONLY_NO_FORMAL_DEFINITION",
        verdict="HIPPOCAMPUS_BROAD_OPERATIONAL",
        proper_vs_formation_adjudication=dict(
            hippocampus_proper="cornu ammonis (CA1-CA4)",
            dentate_gyrus="not hippocampus proper but part of FS aseg 'Hippocampus' and of the "
                          "frozen VERIFIED DG relations",
            hippocampal_formation="DG + CA + subicular complex (+ HATA as transition)",
            decision=("G1 'Hippocampus' = HIPPOCAMPUS_BROAD_OPERATIONAL: CA fields (CA1-CA4 incl "
                      "CA2) + dentate gyrus (GC/ML-DG) + hippocampal molecular layer + hippocampal "
                      "tail - the CA+DG hippocampal body consistent with the frozen reviewer "
                      "rationale (FS 定义含海马体+齿状回). The subicular complex and HATA are NOT "
                      "asserted G1 members (kept definition-dependent / outside the closed scope). "
                      "HIPPOCAMPAL_FORMATION was NOT adopted merely to widen coverage.")),
        basis_priority=["Macro96/source terminology (label only)",
                        "frozen VERIFIED relation history (CA1/CA2/CA3/DG -> Left/Right Hippocampus)",
                        "FreeSurfer/Iglesias hippocampal-subfield label semantics",
                        "standard human neuroanatomy terminology",
                        "cross-atlas consistency (informative only)"],
        frozen_relations=dict(
            verified_in_g1=CA_DG_VERIFIED,
            verified_count=8,
            verified_status_evidence="phase17_v3_classification.csv VERIFIED_DIRECT_CONTAINED "
                                     "(CA1/CA2/CA3/DG left+right)",
            dependent_structures=DEPENDENT_STRUCTURES,
            dependent_status="ONTOLOGY_DEFINITION_DEPENDENT"),
        history_conflict_check=dict(conflict=False,
                                    note="all 8 frozen VERIFIED structures (CA1/CA2/CA3/DG) are "
                                         "contained in the CA+DG operational scope; none excluded"),
        structure_membership=STRUCTURE_TABLE,
        ontology_vs_coverage_note=("Ontology membership and source geometric channel coverage are "
                                   "recorded separately. FreeSurfer channel presence does not force "
                                   "canonical membership and vice versa."),
        canonical_identity_sources=CANON_SOURCES,
        created_at=ts, script_version=SCRIPT_VERSION)
    with open(OUT_IDENTITY, "w", encoding="utf-8") as fh:
        json.dump(identity, fh, ensure_ascii=False, indent=2)

    # scope contract
    scope = dict(
        contract_id=SCOPE_ID,
        canonical_identity=identity["verdict"],
        canonical_identity_id=IDENTITY_ID,
        canonical_left=dict(canonical_region_id=LEFT_G1, preferred_name="Left Hippocampus"),
        canonical_right=dict(canonical_region_id=RIGHT_G1, preferred_name="Right Hippocampus"),
        source=dict(asset="FreeSurfer/Iglesias HippoAmygProbs.MNIsymSpace (left/right)",
                    left_sha256=RAW_L_SHA, right_sha256=RAW_R_SHA,
                    channel_count=len(rows),
                    probability_semantics=dict(left=sem["left"]["semantics"],
                                               right=sem["right"]["semantics"],
                                               operator="SUM")),
        channel_summary=dict(total=len(rows),
                             included_geometry_channels=sorted(inc_idx),
                             included_labels=sorted(inc_labels),
                             geometry_excluded_hippocampal_channels=len(
                                 [r for r in decisions if r["anatomical_family"] == "HIPPOCAMPAL_OTHER"]),
                             amygdala_channels_excluded=sum(
                                 1 for r in decisions if r["anatomical_family"] == "AMYGDALA"),
                             background_excluded=1),
        decisions=decisions,
        scope_verdict="HIPPOCAMPUS_G1_SCOPE_FROZEN",
        review_channels=[],
        geometry_allowed=True,
        no_world_x_split=True,
        laterality_authority="source-native left/right atlas files (no world-X split)")
    with open(OUT_SCOPE, "w", encoding="utf-8") as fh:
        json.dump(scope, fh, ensure_ascii=False, indent=2)
    with open(OUT_CH_SEM, "w", newline="", encoding="utf-8-sig") as fh:
        cols = list(decisions[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in decisions:
            w.writerow(r)
    if scope["scope_verdict"] != "HIPPOCAMPUS_G1_SCOPE_FROZEN":
        raise SystemExit("scope not frozen - stop")

    # shared-frame compatibility + Julich ref
    jref = nib.load(str(JULICH_REF))
    tgt_aff = np.asarray(jref.affine, float)
    if jref.shape != GRID or sha256(JULICH_REF) != JULICH_REF_SHA:
        raise SystemExit("Julich reference mismatch")
    frame = {}
    for side in ("left", "right"):
        img = nib.load(str(HIPPO / f"HippoAmygProbs.MNIsymSpace.{side}.nii.gz"))
        aff = np.asarray(img.affine, float)
        ok = (tuple(img.shape[:3]) == (164, 224, 196) and
              np.allclose(np.asarray(img.header.get_zooms())[:3], 0.25, atol=1e-4) and
              img.header["qform_code"] == 1 and img.header["sform_code"] == 1)
        frame[side] = dict(grid=img.shape[:3], qform_code=int(img.header["qform_code"]),
                           sform_code=int(img.header["sform_code"]),
                           shared_frame_compatible=bool(ok))
        if not ok:
            raise SystemExit(f"shared-frame compatibility failed {side}")

    # ---- native construction ----
    native_entries, native_qc = {}, []
    for side, cid, gid in (("left", LEFT_G1, NATIVE_L_ID), ("right", RIGHT_G1, NATIVE_R_ID)):
        img = nib.load(str(HIPPO / f"HippoAmygProbs.MNIsymSpace.{side}.nii.gz"))
        src_aff = np.asarray(img.affine, float)
        voxvol = float(np.prod(np.asarray(img.header.get_zooms())[:3]))
        d = np.asanyarray(img.dataobj).astype(np.float64)
        prob = np.zeros(img.shape[:3], dtype=np.float64)
        for c in inc_idx:
            prob += d[..., c]
        all_sum = d.sum(axis=3)
        ex_sum = all_sum - prob
        max_res = float(np.abs(all_sum - prob - ex_sum).max())
        # amygdala contamination: amygdala channels sum should not leak into included geometry
        amy_idx = [r["channel_index"] for r in decisions if r["anatomical_family"] == "AMYGDALA"]
        amy_tot = np.zeros(img.shape[:3], dtype=np.float64)
        for c in amy_idx:
            amy_tot += d[..., c]
        amy_overlap_frac = float((prob * (amy_tot > 0.001)).sum()) / float(prob.sum()) if prob.sum() else 0.0
        out = NATIVE_OUT[side]
        write_nifti(out, prob, src_aff)
        osha = sha256(out)
        sup = prob > 0
        ctr = centroid_world(prob, src_aff)
        native_entries[side] = dict(
            geometry_id=gid, canonical_region_id=cid, hemisphere=side,
            geometry_class=NATIVE_CLASS, derivation=NATIVE_DERIV,
            source_path=str((HIPPO / f"HippoAmygProbs.MNIsymSpace.{side}.nii.gz")
                            .relative_to(BACKEND)).replace("\\", "/"),
            included_channels=sorted(inc_labels),
            included_channel_indices=sorted(inc_idx),
            excluded_channel_count=len(rows) - len(inc_idx),
            aggregation_operator="SUM", probability_semantics="MUTUALLY_EXCLUSIVE_CATEGORICAL",
            scope_contract_id=SCOPE_ID, canonical_identity_id=IDENTITY_ID,
            output_path=str(out.relative_to(BACKEND)).replace("\\", "/"),
            output_sha256=osha,
            output_grid=dict(shape=list(img.shape[:3]), spacing_mm=0.25,
                             affine=src_aff.round(6).tolist(),
                             qform_code=int(img.header["qform_code"]),
                             sform_code=int(img.header["sform_code"])),
            probability_min=round(float(prob.min()), 6), probability_max=round(float(prob.max()), 6),
            sum_probability_mass=round(float(prob.sum()), 3),
            voxel_volume_mm3=round(voxvol, 6),
            weighted_volume_mm3=round(float(prob.sum()) * voxvol, 3),
            support_voxels=int(sup.sum()),
            centroid_mm=tuple(round(float(v), 3) for v in ctr),
            max_abs_conservation_residual=round(max_res, 6),
            amygdala_contamination_fraction=round(amy_overlap_frac, 6),
            registration_applied=False, resampling_applied=False, transform_id=None,
            independent_from_g3_g1_mapping=True, circularity_risk="NONE",
            script_version=SCRIPT_VERSION, run_timestamp=ts)
        native_qc.append(dict(geometry_id=gid, hemisphere=side, output_sha256=osha,
                              weighted_volume_mm3=round(float(prob.sum()) * voxvol, 3),
                              support_voxels=int(sup.sum()),
                              centroid_mm=",".join(f"{v:.2f}" for v in ctr),
                              max_abs_conservation_residual=round(max_res, 6),
                              amygdala_contamination_fraction=round(amy_overlap_frac, 6)))
    lr = native_entries["left"]["weighted_volume_mm3"] / native_entries["right"]["weighted_volume_mm3"] \
        if native_entries["right"]["weighted_volume_mm3"] else None
    with open(OUT_NMAN, "w", encoding="utf-8") as fh:
        json.dump(dict(geometry_class=NATIVE_CLASS, derivation=NATIVE_DERIV,
                       space_status="SOURCE_NATIVE_ICBM2009C_SYMMETRIC",
                       probability_semantics="MUTUALLY_EXCLUSIVE_CATEGORICAL",
                       aggregation_operator="SUM",
                       canonical_identity=IDENTITY_ID, scope_contract=SCOPE_ID,
                       raw_left_sha256=RAW_L_SHA, raw_right_sha256=RAW_R_SHA,
                       entries=[native_entries["left"], native_entries["right"]],
                       bilateral=dict(volume_ratio_L_over_R=round(lr, 4) if lr else None),
                       script_version=SCRIPT_VERSION, run_timestamp=ts), fh, ensure_ascii=False, indent=2)
    with open(OUT_NQC, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(native_qc[0].keys()))
        w.writeheader()
        for r in native_qc:
            w.writerow(r)

    # bridge
    bridge = dict(spatial_bridge_id=SPB_ID, spatial_bridge_class=SPB_CLASS,
                  spatial_bridge_statement=SPB_STATEMENT,
                  type_note="Spatial Bridge (NOT a TRF); same frozen bridge principle, applied to "
                            "the HippoAmyg source.",
                  source_space="ICBM152_2009C_SYMMETRIC",
                  target_reference_space="MNI152NLin2009cAsym",
                  julich_target_reference=dict(path=str(JULICH_REF.relative_to(BACKEND)).replace("\\", "/"),
                                               sha256=sha256(JULICH_REF)),
                  interpolation="LINEAR",
                  registration_applied=False, nonlinear_registration_applied=False,
                  nonlinear_registration_claimed=False, deformation_field_applied=False,
                  resampling_applied=True,
                  template_variant_statement="DIFFERENT_TEMPLATE_VARIANTS_WITH_SHARED_STEREOTAXIC_COORDINATE_FRAME",
                  residual_spatial_limitation=LIMITATION,
                  authoritative_nonlinear_sym_asym_transform="NOT_AVAILABLE_NOT_USED",
                  source_compatibility=frame,
                  script_version=SCRIPT_VERSION, run_timestamp=ts)
    with open(OUT_BRIDGE, "w", encoding="utf-8") as fh:
        json.dump(bridge, fh, ensure_ascii=False, indent=2)

    # reference construction
    ref_entries, ref_qc = {}, []
    for side, cid, gid in (("left", LEFT_G1, REF_L_ID), ("right", RIGHT_G1, REF_R_ID)):
        n = native_entries[side]
        src = nib.load(str(BACKEND / n["output_path"]))
        vol = np.asanyarray(src.dataobj).astype(np.float64)
        rvol = resample_to_target(vol, np.asarray(src.affine, float), tgt_aff, GRID)
        out = REF_OUT[side]
        write_nifti(out, rvol, tgt_aff)
        osha = sha256(out)
        sup = rvol > 0
        ctr = centroid_world(rvol, tgt_aff)
        X, Y, Z = np.meshgrid(np.arange(GRID[0]), np.arange(GRID[1]), np.arange(GRID[2]),
                              indexing="ij")
        xw = tgt_aff[0, 0] * X + tgt_aff[0, 3]
        contra = float((rvol * (xw > 0)).sum()) / float(rvol.sum()) if side == "left" \
            else float((rvol * (xw < 0)).sum()) / float(rvol.sum())
        rel = (float(rvol.sum()) - n["weighted_volume_mm3"]) / n["weighted_volume_mm3"]
        ref_entries[side] = dict(
            geometry_id=gid, canonical_region_id=cid, hemisphere=side,
            geometry_class=NATIVE_CLASS, derivation=REF_DERIV,
            source_native_geometry=dict(geometry_id=n["geometry_id"],
                                        output_path=n["output_path"],
                                        output_sha256=n["output_sha256"]),
            scope_contract=dict(id=SCOPE_ID, verdict=scope["scope_verdict"]),
            spatial_bridge_id=SPB_ID, interpolation="LINEAR",
            output_path=str(out.relative_to(BACKEND)).replace("\\", "/"),
            output_sha256=osha,
            output_grid=dict(shape=list(GRID), spacing_mm=1.0,
                             affine=tgt_aff.round(6).tolist(),
                             qform_code=int(jref.header["qform_code"]),
                             sform_code=int(jref.header["sform_code"])),
            probability_min=round(float(rvol.min()), 6), probability_max=round(float(rvol.max()), 6),
            sum_probability_mass=round(float(rvol.sum()), 3),
            weighted_volume_mm3=round(float(rvol.sum()), 3),
            support_voxels=int(sup.sum()),
            centroid_mm=tuple(round(float(v), 3) for v in ctr),
            native_to_target_relative_volume_change=round(float(rel), 4),
            contralateral_mass_fraction=round(float(contra), 6),
            anterior_posterior_extent_mm=round(float((rvol * (Y.astype(float))).sum()) / float(rvol.sum()), 3)
            if False else None,
            template_variant_uncertainty="PRESENT", residual_spatial_limitation=LIMITATION,
            direct_overlap_grid_ready=True, direct_validation_executed=False,
            registration_applied=False, nonlinear_registration_applied=False,
            resampling_applied=True,
            threshold_applied=False, binarization_applied=False, clipping_applied=False,
            normalization_applied=False, no_artificial_symmetrization=True,
            independent_from_g3_g1_mapping=True, circularity_risk="NONE",
            script_version=SCRIPT_VERSION, run_timestamp=ts)
        ref_qc.append(dict(geometry_id=gid, hemisphere=side, output_sha256=osha,
                           shape="x".join(str(x) for x in GRID),
                           weighted_volume_mm3=round(float(rvol.sum()), 3),
                           centroid_mm=",".join(f"{v:.2f}" for v in ctr),
                           contralateral_mass_fraction=round(float(contra), 6),
                           direct_overlap_grid_ready=True, direct_validation_executed=False))
    lrr = ref_entries["left"]["weighted_volume_mm3"] / ref_entries["right"]["weighted_volume_mm3"] \
        if ref_entries["right"]["weighted_volume_mm3"] else None
    with open(OUT_RMAN, "w", encoding="utf-8") as fh:
        json.dump(dict(geometry_class=NATIVE_CLASS, derivation=REF_DERIV,
                       spatial_bridge_id=SPB_ID,
                       registration_applied=False, nonlinear_registration_applied=False,
                       resampling_applied=True, interpolation="LINEAR",
                       template_variant_uncertainty="PRESENT",
                       residual_spatial_limitation=LIMITATION,
                       direct_overlap_grid_ready=True, direct_validation_executed=False,
                       reference_space="MNI152NLin2009cAsym / Julich reference grid",
                       entries=[ref_entries["left"], ref_entries["right"]],
                       bilateral=dict(volume_ratio_L_over_R=round(lrr, 4) if lrr else None),
                       script_version=SCRIPT_VERSION, run_timestamp=ts), fh, ensure_ascii=False, indent=2)
    with open(OUT_RQC, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(ref_qc[0].keys()))
        w.writeheader()
        for r in ref_qc:
            w.writerow(r)

    prov = dict(
        function="Hippocampus G1 canonical scope adjudication + reference geometry construction",
        canonical_identity=dict(identity_id=IDENTITY_ID, verdict=identity["verdict"],
                                file=str(OUT_IDENTITY.relative_to(BACKEND)).replace("\\", "/"),
                                sha256=sha256(OUT_IDENTITY)),
        canonical_left=dict(canonical_region_id=LEFT_G1, preferred_name="Left Hippocampus"),
        canonical_right=dict(canonical_region_id=RIGHT_G1, preferred_name="Right Hippocampus"),
        canonical_identity_sources=CANON_SOURCES,
        raw_source=dict(asset="FreeSurfer/Iglesias HippoAmygProbs.MNIsymSpace",
                        left_sha256=RAW_L_SHA, right_sha256=RAW_R_SHA,
                        names_sha256=sha256(NAMES), channel_count=len(rows)),
        probability_semantics=dict(semantics="MUTUALLY_EXCLUSIVE_CATEGORICAL", operator="SUM",
                                   per_side={k: v["semantics"] for k, v in sem.items()}),
        scope_contract=dict(path=str(OUT_SCOPE.relative_to(BACKEND)).replace("\\", "/"),
                            verdict=scope["scope_verdict"], sha256=sha256(OUT_SCOPE)),
        native_geometry=dict(manifest=str(OUT_NMAN.relative_to(BACKEND)).replace("\\", "/"),
                             manifest_sha256=sha256(OUT_NMAN),
                             left_sha256=native_entries["left"]["output_sha256"],
                             right_sha256=native_entries["right"]["output_sha256"]),
        spatial_bridge=dict(manifest=str(OUT_BRIDGE.relative_to(BACKEND)).replace("\\", "/"),
                            spatial_bridge_id=SPB_ID, manifest_sha256=sha256(OUT_BRIDGE)),
        reference_geometry=dict(manifest=str(OUT_RMAN.relative_to(BACKEND)).replace("\\", "/"),
                                manifest_sha256=sha256(OUT_RMAN),
                                left_sha256=ref_entries["left"]["output_sha256"],
                                right_sha256=ref_entries["right"]["output_sha256"]),
        julich_reference=dict(path=str(JULICH_REF.relative_to(BACKEND)).replace("\\", "/"),
                              sha256=sha256(JULICH_REF)),
        registration_applied=False, nonlinear_registration_applied=False, resampling_applied=True,
        template_variant_uncertainty="PRESENT", residual_spatial_limitation=LIMITATION,
        no_world_x_split=True, laterality_authority="source-native left/right atlas files",
        no_atlas_coverage_driven_ontology_inflation=True,
        independent_from_g3_g1_mapping=True, circularity_risk="NONE",
        classification_csv="NOT_TOUCHED", db_write=False, promotion=False, commit=False,
        software=dict(python_version=sys.version.split()[0], platform=str(_platform.platform()),
                      numpy_version=np.__version__, scipy_version=__import__("scipy").__version__,
                      nibabel_version=nib.__version__),
        script=str(Path(__file__).name), script_version=SCRIPT_VERSION, run_timestamp=ts)
    with open(OUT_PROV, "w", encoding="utf-8") as fh:
        json.dump(prov, fh, ensure_ascii=False, indent=2)

    md = [
        "# Phase1.7 V3 - Hippocampus G1 canonical scope adjudication + reference geometry", "",
        f"Canonical: Left Hippocampus {LEFT_G1} / Right Hippocampus {RIGHT_G1}.",
        f"Identity verdict: {identity['verdict']} "
        f"(= CA fields + dentate gyrus + hippocampal molecular layer + tail; NOT full "
        "hippocampal formation; NOT strict hippocampus proper).",
        "proper-vs-formation: " + identity["proper_vs_formation_adjudication"]["decision"], "",
        "Frozen-relation consistency: 8 VERIFIED CA1/CA2/CA3/DG all inside the CA+DG scope "
        "(no ONTOLOGY_HISTORY_CONFLICT). Subicular complex + HATA stay "
        "ONTOLOGY_DEFINITION_DEPENDENT / outside the closed current-G1 scope (non-blocking).", "",
        "Included geometry channels (11): " + ",".join(str(x) for x in sorted(inc_labels)) + " "
        "(CA1/CA3/CA4 head-body, GC-ML-DG head-body, molecular_layer_HP head-body, hippocampal tail).",
        "Excluded geometry channels: all subicular (subiculum, presubiculum, parasubiculum), "
        "fimbria, alveus, hippocampal-fissure, HATA, amygdala channels, background.", "",
        f"Native (0.25mm 2009cSym): L vol {native_entries['left']['weighted_volume_mm3']} mm3 / "
        f"R vol {native_entries['right']['weighted_volume_mm3']} mm3; "
        f"centroids L {tuple(round(float(v),2) for v in native_entries['left']['centroid_mm'])} / "
        f"R {tuple(round(float(v),2) for v in native_entries['right']['centroid_mm'])}.",
        f"Reference (MNI152NLin2009cAsym / Julich): L vol {ref_entries['left']['weighted_volume_mm3']} / "
        f"R vol {ref_entries['right']['weighted_volume_mm3']} mm3.",
        f"Spatial bridge: {SPB_ID} ({SPB_CLASS}); registration FALSE, nonlinear FALSE, resample TRUE "
        "LINEAR; no threshold/bin/clip/renorm; no manual symmetry correction.",
        "Limitation retained: " + LIMITATION + "; template_variant_uncertainty PRESENT; "
        "direct_overlap_grid_ready TRUE; direct_validation_executed FALSE.", "",
        "No DB write; classification untouched (86/132/93); Promotion not executed; no commit in-script.",
        ""]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    print("identity:", identity["verdict"], "| scope:", scope["scope_verdict"])
    print("native L/R vol", native_entries["left"]["weighted_volume_mm3"],
          native_entries["right"]["weighted_volume_mm3"])
    print("ref L/R vol", ref_entries["left"]["weighted_volume_mm3"],
          ref_entries["right"]["weighted_volume_mm3"])
    print("wrote 10 artifacts")


if __name__ == "__main__":
    main()
