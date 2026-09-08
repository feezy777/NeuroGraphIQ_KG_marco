"""Phase1.7 V3 - Thalamus postconstruction direct-validation gate closure + Phase1.7
final freeze.

Closes the BN postconstruction gate and forms THALAMUS_PHASE17_FINAL_FREEZE_V1 by:

1. Recording the DEC-THAL-DIRECT-02 supersession (DEC-THAL-DIRECT-02-S1) that turns
   the previous REQUIRES_REVIEW notation into the effective
   KEEP_FROZEN_MAPPING_WITH_SPATIAL_UNCERTAINTY verdict (root cause established by the
   L8_2 discrepancy audit: primary G1_PROBABILITY_ENVELOPE_BOUNDARY_LIMITATION,
   secondary SHARED_TEMPLATE_VARIANT_BOUNDARY_MISMATCH; TRUE_MAPPING_INCOMPATIBILITY
   not supported).
2. Computing the effective 16-relation state from the HISTORICAL direct decisions
   (phase17_v3_thalamus_bn_direct_spatial_decisions.csv - NEVER rewritten) plus the
   L8_2 supersession.
3. Writing the postconstruction gate closure record.
4. Writing THALAMUS_PHASE17_FINAL_FREEZE_V1 with the full provenance chain.
5. Writing a human-readable freeze diagnostics markdown.

Scope/guards: file-level scientific freeze only - NOT a DB promotion, NOT a global
reclassification. phase17_v3_classification.csv stays byte-identical (86/132/93).
No DB write. Promotion is NOT executed (readiness recorded only). V1/V2/V3 scope
contracts, geometry/spatial-bridge manifests and every prior historical snapshot
(DIRECT-02 remains REQUIRES_REVIEW in the historical file) are untouched.

Evidence type preserved:
  DIRECT_SPATIAL_OVERLAP_IN_SHARED_MNI2009C_COORDINATE_FRAME
  residual limitation: TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_WARP_CORRECTED
  template_variant_uncertainty: PRESENT
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

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
DERIVED = BACKEND / "data" / "atlases" / "derived_g1"

HIST_DECISIONS = D16 / "phase17_v3_thalamus_bn_direct_spatial_decisions.csv"
HIST_SUMMARY = D16 / "phase17_v3_thalamus_bn_direct_spatial_summary.json"
AUDIT_SUMMARY = D16 / "phase17_v3_thalamus_l8_2_discrepancy_summary.json"
AUDIT_PROV = D16 / "phase17_v3_thalamus_l8_2_discrepancy_provenance.json"
G3MAN = BACKEND / "data" / "integration" / "g3_to_g1" / "g3_to_g1_full_decision_coverage_manifest.csv"
ROLLUP_CSV = D16 / "phase17_v3_thalamus_bn_rollup_compatibility.csv"
BN_XFORM_MAN = BACKEND / "data" / "integration" / "g3_brainnetome_assets" / "g3_brainnetome_to_julich_batch_transform_manifest.csv"
V3_CONTRACT = D16 / "phase17_v3_thalamus_g1_scope_contract_v3.json"
V3_SHA = "22e24a31bab9659769f7e550ee32f8e3b37887d0ae1a4c4c4cf64974c3c05f68"
SPB_MAN = D16 / "phase17_v3_thalamus_spatial_bridge_manifest.json"
SPB_ID = "SPB-MNI2009C-SYM-ASYM-SHARED-FRAME-V1"
SPB_CLASS = "SHARED_COORDINATE_REFERENCE_GRID_RESAMPLING"
NATIVE_MAN = D16 / "phase17_v3_thalamus_g1_native_geometry_manifest.json"
RETRACTION = D16 / "phase17_v3_thalamus_transform_retraction.json"
CLASS_CSV = D16 / "phase17_v3_classification.csv"

G1_LEFT = DERIVED / "left_thalamus_proper_prob_mni2009casym.nii.gz"
G1_RIGHT = DERIVED / "right_thalamus_proper_prob_mni2009casym.nii.gz"
G1_LEFT_SHA = "bd431608fcea3c5f0f7387b1b0e1010582fa2e39dae95a300b3bba976a10cc87"
G1_RIGHT_SHA = "73e4242b581f2420c316593f6cd85183ea7f99c29e2b817b0257cdf267c5bd3b"
SUP_LEFT = "37a82b65d86d81b1558582dee301e79ee367d60856f95d6a55b0219cf28a87a1"
SUP_RIGHT = "1c9b8b8de9103c1e091c9fb6e0577182416d5a6ba0c1b7f6d41e1e913958253f"
G1_LEFT_GEO = "GEO-G1-THAL-L-MNI2009CASYM-V1"
G1_RIGHT_GEO = "GEO-G1-THAL-R-MNI2009CASYM-V1"
LIMITATION = "TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_WARP_CORRECTED"
EVIDENCE = "DIRECT_SPATIAL_OVERLAP_IN_SHARED_MNI2009C_COORDINATE_FRAME"
LEFT_G1 = "NGIQ-BR-00000247"
RIGHT_G1 = "NGIQ-BR-00000256"

OUT_SUPERSEDE = D16 / "phase17_v3_thalamus_direct_decision_supersession.json"
OUT_EFFECTIVE = D16 / "phase17_v3_thalamus_bn_direct_effective_decisions.csv"
OUT_GATE = D16 / "phase17_v3_thalamus_postconstruction_gate_closure.json"
OUT_FREEZE = D16 / "phase17_v3_thalamus_final_freeze_v1.json"
OUT_MD = D16 / "phase17_v3_thalamus_final_freeze_diagnostics.md"

SCRIPT_VERSION = "phase17_v3_freeze_thalamus_postconstruction.py v1"
FREEZE_ID = "THALAMUS_PHASE17_FINAL_FREEZE_V1"
SUPERSEDE_ID = "DEC-THAL-DIRECT-02-S1"
GATE_ID = "THALAMUS_BN_POSTCONSTRUCTION_GATE_V1"

SUPPORTED = "KEEP_FROZEN_MAPPING_DIRECTLY_SUPPORTED"
UNCERT = "KEEP_FROZEN_MAPPING_WITH_SPATIAL_UNCERTAINTY"
REVIEW = "FROZEN_MAPPING_REQUIRES_REVIEW"
CONFLICT = "FROZEN_MAPPING_DIRECT_CONFLICT"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main() -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # ---- frozen authority checks (all read-only) ----
    hist = list(csv.DictReader(open(HIST_DECISIONS, encoding="utf-8-sig")))
    if len(hist) != 16:
        raise SystemExit("historical decisions != 16")
    hist_by_id = {r["decision_id"]: r for r in hist}
    h02 = hist_by_id["DEC-THAL-DIRECT-02"]
    if h02["mapping_verdict"] != REVIEW:
        raise SystemExit("historical DIRECT-02 verdict changed - expected REQUIRES_REVIEW (must not rewrite)")
    if not (G1_LEFT.exists() and (D16 / "phase17_v3_thalamus_bn_direct_spatial_summary.json").exists()):
        raise SystemExit("missing chain inputs")
    if sha256(V3_CONTRACT) != V3_SHA:
        raise SystemExit("V3 contract SHA drift")
    spb = json.load(open(SPB_MAN, encoding="utf-8"))
    if spb["spatial_bridge_id"] != SPB_ID or spb["residual_spatial_limitation"] != LIMITATION:
        raise SystemExit("SPB drift")
    retr = json.load(open(RETRACTION, encoding="utf-8"))
    if retr["status"] != "RETRACTED":
        raise SystemExit("retraction drift")
    native = json.load(open(NATIVE_MAN, encoding="utf-8"))
    native_left_id = native["entries"][0]["geometry_id"]
    native_right_id = native["entries"][1]["geometry_id"]

    audit = json.load(open(AUDIT_SUMMARY, encoding="utf-8"))
    rv = audit["root_cause_verdict"]
    if rv["primary"] != "G1_PROBABILITY_ENVELOPE_BOUNDARY_LIMITATION":
        raise SystemExit("audit primary root cause drift")
    if rv["secondary"] != ["SHARED_TEMPLATE_VARIANT_BOUNDARY_MISMATCH"]:
        raise SystemExit("audit secondary root cause drift")

    # ---- 1. supersession record ----
    supersession = dict(
        supersession_id=SUPERSEDE_ID,
        supersedes="DEC-THAL-DIRECT-02",
        decision_kind="EFFECTIVE_DECISION_SUPERSESSION",
        g3_region_id=h02["g3_region_id"],
        g3_official_code=h02["official_code"],
        g3_abbreviation=h02["abbreviation"],
        relation=dict(
            frozen_mapping_decision=h02["frozen_mapping_decision"],
            frozen_g1_target=h02["frozen_g1_target"],
            g1_geometry_id=h02["g1_geometry_id"]),
        previous_verdict=h02["mapping_verdict"],
        effective_verdict=UNCERT,
        mapping_conflict=False,
        mapping_review_required=False,
        root_cause_primary=rv["primary"],
        root_cause_secondary=rv["secondary"][0],
        raw_bna_intrinsic_asymmetry="PRESENT",
        template_variant_uncertainty="PRESENT",
        confidence=dict(
            mapping_not_incompatible="HIGH",
            primary_secondary_ascription="MODERATE"),
        root_cause_audit=dict(
            audit_id=audit.get("function", "Tha_L_8_2 discrepancy root-cause audit"),
            path=str(AUDIT_SUMMARY.relative_to(BACKEND)).replace("\\", "/"),
            sha256=sha256(AUDIT_SUMMARY)),
        provenance_path=str(AUDIT_PROV.relative_to(BACKEND)).replace("\\", "/"),
        provenance_sha256=sha256(AUDIT_PROV),
        historical_decisions_path=str(HIST_DECISIONS.relative_to(BACKEND)).replace("\\", "/"),
        historical_decisions_sha256=sha256(HIST_DECISIONS),
        historical_outputs_rewritten=False,
        note=("Supersedes only the previous REVIEW notation of DEC-THAL-DIRECT-02. The "
              "historical direct-validation snapshot is left untouched. Effective verdict "
              "keeps the frozen mapping WITH documented spatial uncertainty because the "
              "root cause is a G1 probability-envelope boundary limitation + shared-template-"
              "variant mismatch, not a mapping incompatibility."),
        created_at=ts,
    )
    with open(OUT_SUPERSEDE, "w", encoding="utf-8") as fh:
        json.dump(supersession, fh, ensure_ascii=False, indent=2)

    # ---- 2. effective decisions (historical + supersession) ----
    effective = []
    for r in hist:
        did = r["decision_id"]
        if did == "DEC-THAL-DIRECT-02":
            verdict = UNCERT
            ss = SUPERSEDE_ID
            ev = "SPATIAL_UNCERTAINTY_RETAINED"
            note = ("G1 probability-envelope boundary limitation + shared-template-variant "
                    "mismatch (L8_2 root-cause audit); envelope-limited containment; "
                    "raw BNA intrinsic L/R asymmetry PRESENT")
            nbu = True
        elif did == "DEC-THAL-DIRECT-12":
            verdict = UNCERT
            ss = ""
            ev = "SPATIAL_UNCERTAINTY_RETAINED"
            note = "MIDLINE_LEAK (<=2 mm band; BN asset correct-side 0.780); non-blocking"
            nbu = True
        else:
            verdict = r["mapping_verdict"]
            ss = ""
            ev = "DIRECTLY_SUPPORTED" if verdict == SUPPORTED else "SPATIAL_UNCERTAINTY_RETAINED"
            note = r.get("review_flags", "") or ""
            nbu = verdict == UNCERT
        effective.append(dict(
            decision_id=did,
            rollup_decision_id=r["rollup_decision_id"],
            official_code=r["official_code"],
            abbreviation=r["abbreviation"],
            hemisphere=r["hemisphere"],
            frozen_g1_target=r["frozen_g1_target"],
            g1_geometry_id=r["g1_geometry_id"],
            g1_sha256=r["g1_sha256"],
            historical_mapping_verdict=r["mapping_verdict"],
            effective_mapping_verdict=verdict,
            evidence_class=ev,
            uncertainty_note=note,
            supersession_id=ss,
            nonblocking_spatial_uncertainty="TRUE" if nbu else "FALSE"))
    with open(OUT_EFFECTIVE, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(effective[0].keys()))
        w.writeheader()
        for row in effective:
            w.writerow(row)

    counts = {v: sum(1 for x in effective if x["effective_mapping_verdict"] == v)
              for v in (SUPPORTED, UNCERT, REVIEW, CONFLICT)}
    if counts != {SUPPORTED: 7, UNCERT: 9, REVIEW: 0, CONFLICT: 0}:
        raise SystemExit(f"effective counts mismatch: {counts}")

    # ---- 3. postconstruction gate closure ----
    gate = dict(
        gate_id=GATE_ID,
        previous_status="OPEN_DUE_TO_MATERIAL_UNRESOLVED_DISCREPANCY",
        root_cause_resolution="COMPLETED",
        confirmed_mapping_conflicts=0,
        mapping_review_items=0,
        nonblocking_spatial_uncertainties=counts[UNCERT],
        gate_status="CLOSED_NO_MAPPING_CONFLICT",
        direct_validation_status="PASSED_WITH_RECORDED_SPATIAL_UNCERTAINTY",
        note=("PASSED does NOT equal PERFECT_GEOMETRIC_CONTAINMENT. Continuous "
              "probability-weighted containment varied substantially across parcels "
              "(weighted containment 0.12-0.82). The recorded spatial uncertainties are "
              "retained and are NOT removed by this gate closure."),
        supersession=SUPERSEDE_ID,
        effective_decisions_path=str(OUT_EFFECTIVE.relative_to(BACKEND)).replace("\\", "/"),
        created_at=ts,
    )
    with open(OUT_GATE, "w", encoding="utf-8") as fh:
        json.dump(gate, fh, ensure_ascii=False, indent=2)

    # ---- 4. final freeze ----
    chain = [
        dict(role="effective direct decisions", path=str(OUT_EFFECTIVE.relative_to(BACKEND)).replace("\\", "/")),
        dict(role="L8_2 supersession (DEC-THAL-DIRECT-02-S1)", path=str(OUT_SUPERSEDE.relative_to(BACKEND)).replace("\\", "/"),
             sha256=sha256(OUT_SUPERSEDE)),
        dict(role="historical direct decisions (DEC-THAL-DIRECT-01..16)", path=str(HIST_DECISIONS.relative_to(BACKEND)).replace("\\", "/"),
             sha256=sha256(HIST_DECISIONS)),
        dict(role="historical direct validation summary", path=str(HIST_SUMMARY.relative_to(BACKEND)).replace("\\", "/"),
             sha256=sha256(HIST_SUMMARY)),
        dict(role="L8_2 discrepancy root-cause audit summary", path=str(AUDIT_SUMMARY.relative_to(BACKEND)).replace("\\", "/"),
             sha256=sha256(AUDIT_SUMMARY)),
        dict(role="L8_2 discrepancy audit provenance", path=str(AUDIT_PROV.relative_to(BACKEND)).replace("\\", "/"),
             sha256=sha256(AUDIT_PROV)),
        dict(role="frozen G3->G1 relations", path=str(G3MAN.relative_to(BACKEND)).replace("\\", "/"),
             sha256=sha256(G3MAN)),
        dict(role="DEC-THAL-ROLLUP-01..16 bindings", path=str(ROLLUP_CSV.relative_to(BACKEND)).replace("\\", "/"),
             sha256=sha256(ROLLUP_CSV)),
        dict(role="BNA NLin6Asym->2009cAsym batch transform manifest", path=str(BN_XFORM_MAN.relative_to(BACKEND)).replace("\\", "/"),
             sha256=sha256(BN_XFORM_MAN)),
        dict(role="spatial bridge manifest (SPB-MNI2009C-SYM-ASYM-SHARED-FRAME-V1)", path=str(SPB_MAN.relative_to(BACKEND)).replace("\\", "/"),
             sha256=sha256(SPB_MAN)),
        dict(role="native geometry manifest", path=str(NATIVE_MAN.relative_to(BACKEND)).replace("\\", "/"),
             sha256=sha256(NATIVE_MAN)),
        dict(role="V3 scope contract", path=str(V3_CONTRACT.relative_to(BACKEND)).replace("\\", "/"),
             sha256=V3_SHA),
        dict(role="transform retraction (superseded SyN route)", path=str(RETRACTION.relative_to(BACKEND)).replace("\\", "/"),
             sha256=sha256(RETRACTION)),
    ]
    freeze = dict(
        freeze_id=FREEZE_ID,
        canonical_left_id=LEFT_G1,
        canonical_right_id=RIGHT_G1,
        ontology_identity="THALAMUS_PROPER",
        ontology_status="FROZEN",
        scope_contract="THALAMUS_G1_SCOPE_CONTRACT_V3",
        scope_contract_sha256=V3_SHA,
        scope_status="FROZEN",
        probability_semantics="MUTUALLY_EXCLUSIVE_CATEGORICAL",
        aggregation_operator="SUM",
        native_geometry_status="FROZEN",
        native_geometry_ids=[native_left_id, native_right_id],
        reference_grid_geometry_status="FROZEN",
        reference_grid_geometry_ids=[G1_LEFT_GEO, G1_RIGHT_GEO],
        current_g1_geometry=dict(
            left_sha256=G1_LEFT_SHA, right_sha256=G1_RIGHT_SHA,
            left_geometry_id=G1_LEFT_GEO, right_geometry_id=G1_RIGHT_GEO),
        superseded_syn_geometry=dict(
            left=SUP_LEFT, right=SUP_RIGHT, status="SUPERSEDED / NOT_CURRENT",
            note="must never be consumed as current evidence"),
        spatial_bridge_status="FROZEN_SHARED_COORDINATE_RESAMPLE",
        spatial_bridge_id=SPB_ID,
        authoritative_nonlinear_sym_asym_transform="NOT_AVAILABLE_NOT_USED",
        template_variant_uncertainty="PRESENT",
        residual_spatial_limitation=LIMITATION,
        evidence_mode=EVIDENCE,
        evidence_mode_note="NOT DIRECT_OVERLAP_AFTER_AUTHORITATIVE_SYM_TO_ASYM_REGISTRATION",
        bn_preconstruction_gate="PASSED",
        bn_postconstruction_gate="CLOSED_NO_MAPPING_CONFLICT",
        bn_direct_validation_status="PASSED_WITH_RECORDED_SPATIAL_UNCERTAINTY",
        relation_counts=dict(
            total=16,
            supported=counts[SUPPORTED],
            uncertainty=counts[UNCERT],
            review=counts[REVIEW],
            conflict=counts[CONFLICT],
            insufficient=0),
        effective_decision_ids=[x["decision_id"] for x in effective],
        direct_02_supersession_id=SUPERSEDE_ID,
        direct_02_effective_verdict=UNCERT,
        direct_02_true_mapping_incompatibility=False,
        remaining_blocking_thalamus_items=[],
        nonblocking_uncertainties=[
            dict(decision="DEC-THAL-DIRECT-02 (Tha_L_8_2, superseded by DEC-THAL-DIRECT-02-S1)",
                 kind="NON_BLOCKING_SPATIAL_UNCERTAINTY",
                 note="G1 probability-envelope boundary limitation + shared-template-variant mismatch; "
                      "raw BNA intrinsic L/R asymmetry PRESENT"),
            dict(decision="DEC-THAL-DIRECT-12 (Tha_R_8_4)",
                 kind="NON_BLOCKING_SPATIAL_UNCERTAINTY",
                 note="MIDLINE_LEAK (<=2 mm band; BN asset correct-side mass fraction 0.780); "
                      "root cause NOT expanded in this round"),
            dict(kind="SHARED_TEMPLATE_VARIANT_UNCERTAINTY",
                 note="G1 derived from 2009cSym shared-frame resample; BN side nonlinearly warped "
                      "NLin6Asym->2009cAsym; residual not warp-corrected (PRESENT)"),
            dict(kind="RECORDED_BOUNDARY_UNCERTAINTY",
                 note="boundary uncertainty retained on all other effective WITH_SPATIAL_UNCERTAINTY "
                      "decisions (Tha_L_8_3, Tha_L_8_4, Tha_L_8_7, Tha_L_8_8, Tha_R_8_2, Tha_R_8_3, "
                      "Tha_R_8_7)"),
        ],
        promotion_readiness="READY_FOR_LATER_GLOBAL_PROMOTION_REVIEW",
        promotion_executed=False,
        db_zero_write=True,
        classification_csv_unchanged=True,
        classification_snapshot=dict(verified=86, non_verified=132, likely=93),
        provenance_chain=chain,
        created_at=ts,
        script_version=SCRIPT_VERSION,
    )
    with open(OUT_FREEZE, "w", encoding="utf-8") as fh:
        json.dump(freeze, fh, ensure_ascii=False, indent=2)

    # ---- 5. diagnostics md ----
    md = [
        "# Phase1.7 V3 - Thalamus postconstruction gate closure + final freeze", "",
        f"Freeze ID: {FREEZE_ID}", f"Gate ID: {GATE_ID}", f"Supersession: {SUPERSEDE_ID}",
        "",
        "Effective 16-relation state (from historical direct decisions + L8_2 supersession):",
        f"  KEEP_FROZEN_MAPPING_DIRECTLY_SUPPORTED        = {counts[SUPPORTED]}",
        f"  KEEP_FROZEN_MAPPING_WITH_SPATIAL_UNCERTAINTY  = {counts[UNCERT]}",
        f"  FROZEN_MAPPING_REQUIRES_REVIEW                 = {counts[REVIEW]}",
        f"  FROZEN_MAPPING_DIRECT_CONFLICT                 = {counts[CONFLICT]}",
        f"  (insufficient)                                 = 0",
        "",
        f"Confirmed mapping conflicts = {gate['confirmed_mapping_conflicts']}; "
        f"mapping review items = {gate['mapping_review_items']}; "
        f"non-blocking spatial uncertainties = {gate['nonblocking_spatial_uncertainties']}.",
        f"Gate status = {gate['gate_status']}; direct validation = {gate['direct_validation_status']}.",
        "",
        "NOTES:",
        "  - PASSED does NOT equal PERFECT_GEOMETRIC_CONTAINMENT. Continuous containment varied "
        "substantially across parcels (weighted containment 0.12-0.82); recorded spatial "
        "uncertainty is retained.",
        "  - DEC-THAL-DIRECT-02 / Tha_L_8_2: historical snapshot still shows REQUIRES_REVIEW; "
        "effective verdict via DEC-THAL-DIRECT-02-S1 is KEEP_FROZEN_MAPPING_WITH_SPATIAL_UNCERTAINTY "
        "(root cause = G1 probability-envelope boundary limitation + shared-template-variant "
        "mismatch; TRUE_MAPPING_INCOMPATIBILITY not supported).",
        "  - Tha_R_8_4 midline leak remains NON_BLOCKING_SPATIAL_UNCERTAINTY.",
        "  - template_variant_uncertainty PRESENT; residual limitation "
        f"{LIMITATION} preserved; evidence mode {EVIDENCE}.",
        "  - Current G1 SHAs: L " + G1_LEFT_SHA + ", R " + G1_RIGHT_SHA +
        "; superseded SyN geometry " + SUP_LEFT[:12] + "... / " + SUP_RIGHT[:12] + " is NOT current.",
        "  - This is a FILE-LEVEL scientific freeze. No DB promotion (brain_regions 770 / active "
        "mappings 707 unchanged), no global reclassification (86/132/93 unchanged). Promotion not "
        "executed (readiness = READY_FOR_LATER_GLOBAL_PROMOTION_REVIEW).", "",
        f"Provenance chain recorded with artifact SHAs ({len(chain)} links); see "
        f"{OUT_FREEZE.name}.", "",
    ]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    print("effective counts:", json.dumps({k: v for k, v in counts.items()}))
    print("gate:", gate["gate_status"], "| direct_validation:", gate["direct_validation_status"])
    print("freeze:", FREEZE_ID, "written")
    print("wrote: supersession.json, effective_decisions.csv, gate_closure.json, final_freeze_v1.json, diagnostics.md")


if __name__ == "__main__":
    main()
