"""Phase1.7 V3 - BNST canonical entity admission + granularity / G1-rollup decision.

ONTOLOGY-ADMISSION ONLY (no geometry / no NIfTI / no transform / no DB / no
classification change / no promotion).

Repository audit findings (verified live):
  - Macro96 pool: NO BST/BNST row (0).
  - Canonical BrainRegion layer: NO canonical BST/BNST (0).
  - Canonical NGIQ-BR ids for BST: 0.
  - However TWO Julich-Brain G4 CANDIDATE rows reference BST:
      NGIQ-BR-00000344 "BST (Basal Forebrain, Bed Nucleus) left"  -> candidate G1 Left  Basal Forebrain (NGIQ-BR-00000264)
      NGIQ-BR-00000343 "BST (Basal Forebrain, Bed Nucleus) right" -> candidate G1 Right Basal Forebrain (NGIQ-BR-00000265)
    both v3_classification=LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW, frozen_decision=CONFLICT_REVIEW.
    These are source/candidate entities, NOT canonical entities; they are NOT modified.

Decisions:
  Terminology   : BST == BNST == Bed nucleus of the stria terminalis
                  (SAME_CANONICAL_STRUCTURE); preferred human term used; aliases kept.
  Concept scope : WHOLE_BNST_COMPLEX (not dBNST/vBNST).
  Laterality    : LATERALIZED_CANONICAL_ENTITIES_REQUIRED (repo convention per-side).
  Granularity   : NON_G1_CANONICAL_BRAINREGION on the EXISTING granularity class
                  'subregion' (L3). No invented G2; no fabricated G1_MACRO. The
                  existing Julich BST maps live at G4/cyto (candidate layer) - context,
                  not the proposed whole-BNST canonical granularity.
  G1 roll-up    : G1_ROLLUP_UNRESOLVED - Basal Forebrain is a PLAUSIBLE Macro96 G1
                  parent with an EXISTING LIKELY/CONFLICT_REVIEW candidate (Julich BST
                  -> Basal Forebrain); its containment is NOT canonical and cannot be
                  adjudicated inside this round (Basal Forebrain scope is out of scope
                  here). No forced part_of/contained_in is created for Basal Forebrain,
                  Amygdala, NAcc, or Thalamus. Deferred to the Basal Forebrain round.
  Admission     : ADMIT_AS_CANONICAL_BRAINREGION (human evidence: Blackford/Theiss
                  whole-BNST n=10 primary; standard human terminology; Sibbach d/v and
                  Brandstetter cyto human evidence as subdivision support).
  Canonical ID  : PENDING_CANONICAL_ALLOCATION - no file-level NGIQ-BR allocator /
                  reservation mechanism exists in the repo (canonical region_code is a
                  DB-layer 'ng:br:*' IRI). No max+1 guessing. Stable proposal tags:
                  PROP-BNST-L-V1 / PROP-BNST-R-V1 (NOT NGIQ-BR).
  Blackford     : SUPPORTS_GEOMETRY_FOR the proposed whole-BNST concept; geometry
                  construction = NOT_STARTED (next round).
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
MACRO96 = BACKEND / "data" / "atlases" / "macro96" / "macro96_normalized_manifest.csv"
CLASS_CSV = D16 / "phase17_v3_classification.csv"
EXT_MAN = D16 / "phase17_v3_external_g1_asset_manifest.csv"
ADMISSION_ID = "BNST_CANONICAL_ENTITY_ADMISSION_V1"
PROPOSAL_ID = "BNST_CANONICAL_REGION_PROPOSAL_V1"
SCRIPT_VERSION = "phase17_v3_adjudicate_bnst_canonical_admission.py v1"

OUT_AUDIT = D16 / "phase17_v3_bnst_canonical_entity_audit.json"
OUT_XWALK = D16 / "phase17_v3_bnst_terminology_crosswalk.csv"
OUT_GRAN = D16 / "phase17_v3_bnst_granularity_decision.json"
OUT_ROLL = D16 / "phase17_v3_bnst_g1_rollup_decision.json"
OUT_ADM = D16 / "phase17_v3_bnst_canonical_admission_v1.json"
OUT_PROP = D16 / "phase17_v3_bnst_canonical_region_proposal_v1.json"
OUT_MD = D16 / "phase17_v3_bnst_canonical_admission_diagnostics.md"

_BST_PAT = ("bst", "bed nucleus", "stria terminalis", "bnst", "stria")


def count_macro96_bnst() -> int:
    n = 0
    for r in csv.DictReader(open(MACRO96, encoding="utf-8-sig")):
        blob = " ".join(str(v).lower() for v in r.values())
        if any(k in blob for k in _BST_PAT):
            n += 1
    return n


def julich_bst_candidates() -> list[dict]:
    """Julich-Brain G4 candidate rows that name BST (candidate layer, NOT canonical)."""
    out = []
    for r in csv.DictReader(open(CLASS_CSV, encoding="utf-8-sig")):
        name = r.get("source_name_en", "")
        blob = (name + " " + r.get("source_atlas", "")).lower()
        if "bst" in blob.split(" (")[0].lower() and "basal forebrain" in blob.lower():
            out.append(dict(source_entity_id=r["source_entity_id"],
                            source_name_en=name,
                            source_granularity=r.get("source_granularity", ""),
                            hemisphere=r.get("hemisphere", ""),
                            candidate_g1_entity_id=r.get("candidate_g1_entity_id", ""),
                            candidate_g1_name_en=r.get("candidate_g1_name_en", ""),
                            v3_classification=r.get("v3_classification", ""),
                            frozen_decision=r.get("frozen_decision", "")))
    return out


def manifest_label_record() -> dict:
    for r in csv.DictReader(open(EXT_MAN, encoding="utf-8-sig")):
        if r.get("asset_id") == "BST_BLACKFORD_WHOLE":
            return dict(asset_id=r["asset_id"], supported_g1_label=r.get("supported_g1", ""),
                        semantic="ASSET_TARGET_LABEL_WITHOUT_CANONICAL_ENTITY",
                        stale="SEMANTIC_LABEL_STALE_NOT_CANONICAL_G1",
                        note=("field records a planned-support target anatomical concept; "
                              "it does NOT assert an existing canonical G1 entity"))
    raise SystemExit("BST_BLACKFORD_WHOLE not found in external_g1 manifest")


def blackford_source_record() -> dict:
    for r in csv.DictReader(open(D16 / "phase17_v3_external_raw_asset_acquisition.csv",
                                 encoding="utf-8-sig")):
        if r.get("asset_id") == "BST_BLACKFORD_WHOLE":
            return dict(asset_id=r["asset_id"], structure=r.get("structure", ""),
                        source_status=r.get("source_status", ""),
                        sha256=r.get("sha256", ""), local_path=r.get("local_path", ""),
                        coordinate_space=r.get("coordinate_space", ""),
                        template_variant=r.get("template_variant", ""),
                        shape=r.get("shape", ""), license=r.get("license_status", ""),
                        probabilistic=r.get("probabilistic_or_discrete", ""),
                        species="human (Theiss et al. 2017)")
    raise SystemExit("BST_BLACKFORD_WHOLE not found in acquisition CSV")


def main() -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    macro_bnst = count_macro96_bnst()
    candidates = julich_bst_candidates()
    if macro_bnst != 0:
        raise SystemExit("unexpected macro96 BNST rows")
    if len(candidates) not in (0, 2):
        raise SystemExit("unexpected Julich BST candidate count")
    label = manifest_label_record()
    src = blackford_source_record()

    audit = dict(
        audit_id="BNST_REPOSITORY_ENTITY_AUDIT",
        macro96_pool=dict(count_bnst=macro_bnst, note="Macro96 has NO BST/BNST row"),
        canonical_brainregions=dict(count_bnst=0,
                                    note="no canonical BST/BNST BrainRegion in canonical records"),
        canonical_ngiq_br_ids=dict(count_bnst=0, note="no canonical NGIQ-BR id refers to BST/BNST"),
        julich_g4_candidate_rows=dict(count=len(candidates), rows=candidates,
                                      note=("candidate/source layer only (Julich-Brain), mapped to "
                                            "Basal Forebrain G1 candidate with LIKELY + CONFLICT_REVIEW; "
                                            "NOT canonical entities and NOT modified by this round")),
        external_manifest_label=label,
        conclusion=("repository has NO canonical BNST entity. BST is present only as (a) a Julich "
                    "G4 candidate pair under Basal Forebrain (LIKELY/CONFLICT_REVIEW) and (b) a "
                    "planned-support text label in the external asset manifest."),
        created_at=ts, script_version=SCRIPT_VERSION)
    with open(OUT_AUDIT, "w", encoding="utf-8") as fh:
        json.dump(audit, fh, ensure_ascii=False, indent=2)

    xwalk = [
        dict(term="BST", canonical_structure=True, verdict="SAME_CANONICAL_STRUCTURE",
             note="abbreviation of bed nucleus of the stria terminalis"),
        dict(term="BNST", canonical_structure=True, verdict="SAME_CANONICAL_STRUCTURE",
             note="abbreviation (bed nucleus stria terminalis)"),
        dict(term="Bed nucleus of the stria terminalis", canonical_structure=True,
             verdict="SAME_CANONICAL_STRUCTURE", note="preferred canonical human terminology"),
        dict(term="Bed nuclei of the stria terminalis", canonical_structure=True,
             verdict="SAME_CANONICAL_STRUCTURE", note="complex reading of the same structure"),
        dict(term="bed nucleus of stria terminalis", canonical_structure=True,
             verdict="SAME_CANONICAL_STRUCTURE", note="Blackford/Theiss 2017 asset label"),
        dict(term="BST (Basal Forebrain, Bed Nucleus)", canonical_structure=True,
             verdict="SAME_CANONICAL_STRUCTURE",
             note="Julich-Brain G4 candidate label; adds a basal-forebrain grouping context that is "
                  "an open containment question (see G1 roll-up decision)"),
        dict(term="dBNST / vBNST", canonical_structure=False,
             verdict="SCOPE_DIFFERENCE_SUBDIVISION",
             note="dorsal/ventral subdivisions (Sibbach); not the whole canonical concept"),
    ]
    with open(OUT_XWALK, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(xwalk[0].keys()))
        w.writeheader()
        for r in xwalk:
            w.writerow(r)

    gran = dict(
        decision_id="BNST_GRANULARITY_DECISION_V1",
        verdict="NON_G1_CANONICAL_BRAINREGION",
        existing_granularity_class="subregion (L3)",
        existing_granularity_code="subregion",
        description=("fine-grained subcortical canonical region on the existing 'subregion' (L3) "
                     "scale band (subnucleus/subfield level). whole-BNST is not a Macro96 macro and "
                     "is deliberately NOT elevated to G1_MACRO."),
        vocabulary_reference="backend/migrations/20260826_multiscale_granularity_refactor.sql "
                             "(macro L1 / meso L2 / subregion L3 / cyto L4 / molecular L5)",
        candidate_layer_context=("the existing Julich BST maps are registered at G4/fine (cyto) "
                                 "granularity in the candidate layer; that is context, not the "
                                 "proposed whole-BNST canonical granularity"),
        invented_G2=False, fabricated_G1=False,
        note="no G2 was invented (ontology has no formal G2 token); no G1_MACRO was fabricated.",
        created_at=ts)
    with open(OUT_GRAN, "w", encoding="utf-8") as fh:
        json.dump(gran, fh, ensure_ascii=False, indent=2)

    roll = dict(
        decision_id="BNST_G1_ROLLUP_DECISION_V1",
        verdict="G1_ROLLUP_UNRESOLVED",
        macro96_parent=None,
        plausible_macro96_parent="Left/Right Basal Forebrain (NGIQ-BR-00000264/00000265)",
        existing_candidate_evidence=[c["source_entity_id"] for c in candidates],
        note=("Julich-Brain G4 BST candidates (LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW + "
              "CONFLICT_REVIEW) already point at Basal Forebrain G1. Containment of BNST in the "
              "Basal Forebrain G1 macro is therefore a plausible-but-unconfirmed open question "
              "that this round is NOT allowed to resolve (Basal Forebrain scope is out of scope). "
              "No forced part_of/contained_in is created for Basal Forebrain, Amygdala, NAcc or "
              "Thalamus. Resolution is deferred to the Basal Forebrain scope round."),
        rejected_forced_parents=dict(BasalForebrain="not forced (open LIKELY/CONFLICT candidate; "
                                                    "deferred)", Amygdala="no evidence",
                                     NucleusAccumbens="no evidence", Thalamus="no evidence"),
        created_at=ts)
    with open(OUT_ROLL, "w", encoding="utf-8") as fh:
        json.dump(roll, fh, ensure_ascii=False, indent=2)

    admission = dict(
        admission_id=ADMISSION_ID,
        verdict="ADMIT_AS_CANONICAL_BRAINREGION",
        structure="Bed nucleus of the stria terminalis (whole BNST complex)",
        human_evidence=[
            dict(source="Blackford/Theiss 2017 whole-BNST probabilistic atlas (human n=10)",
                 role="primary human geometry/identity evidence", status="ACQUIRED_VERIFIED"),
            dict(source="Sibbach et al. 2024 dBNST/vBNST human probabilistic atlas (n=25)",
                 role="human subdivision evidence", status="NOT_ACQUIRED_METADATA"),
            dict(source="Brandstetter/Juellich human cytoarchitectonic BST (BSTC/D/M/P)",
                 role="human cytoarchitectonic support", status="NOT_ACQUIRED_METADATA"),
            dict(source="standard human neuroanatomical terminology",
                 role="terminology/identity support", status="LITERATURE")],
        animal_evidence_used=False,
        non_human_note="animal evidence (e.g. Allen mouse 'bed nucleus') OUT_OF_SCOPE_NON_HUMAN; "
                       "not used as admission authority",
        criteria_met=dict(anatomically_bounded=True, human_neural_structure=True,
                          accepted_regional_identity=True),
        created_at=ts)
    with open(OUT_ADM, "w", encoding="utf-8") as fh:
        json.dump(admission, fh, ensure_ascii=False, indent=2)

    proposal = dict(
        proposal_id=PROPOSAL_ID,
        proposal_entities=[
            dict(proposal_entity_id="PROP-BNST-L-V1",
                 preferred_name="Left bed nucleus of the stria terminalis",
                 aliases=["Left BNST", "Left BST"], chinese_name="左侧终纹床核",
                 hemisphere="left", entity_type="BrainRegion (canonical proposal)",
                 whole_subdivision_scope="WHOLE_BNST_COMPLEX"),
            dict(proposal_entity_id="PROP-BNST-R-V1",
                 preferred_name="Right bed nucleus of the stria terminalis",
                 aliases=["Right BNST", "Right BST"], chinese_name="右侧终纹床核",
                 hemisphere="right", entity_type="BrainRegion (canonical proposal)",
                 whole_subdivision_scope="WHOLE_BNST_COMPLEX")],
        status="PROPOSED_CANONICAL",
        not_active_not_promoted=True,
        canonical_definition=("whole bed nucleus of the stria terminalis (BNST complex), a small "
                              "subcortical grey-matter structure of the basal forebrain / "
                              "extended-amygdala region, per the human whole-BNST concept of "
                              "Blackford/Theiss 2017"),
        laterality="LATERALIZED_CANONICAL_ENTITIES_REQUIRED",
        granularity=gran["verdict"] + " / existing class " + gran["existing_granularity_class"],
        g1_rollup_status=roll["verdict"],
        canonical_id_status="PENDING_CANONICAL_ALLOCATION",
        canonical_ids=dict(left="PENDING_CANONICAL_ALLOCATION",
                           right="PENDING_CANONICAL_ALLOCATION"),
        id_allocation_policy_note=("no file-level NGIQ-BR allocator / reservation mechanism exists "
                                   "in the repository (canonical region_code is a DB-layer 'ng:br:*' "
                                   "IRI allocated at region creation); NGIQ-BR ids are therefore NOT "
                                   "guessed (no max+1) and NOT reserved this round"),
        proposal_id_policy_note="PROP-* are stable proposal tags only, NOT canonical NGIQ-BR ids",
        human_authority_sources=[s["source"] for s in admission["human_evidence"]],
        blackford_relation=dict(asset="BST_BLACKFORD_WHOLE",
                                relation="SUPPORTS_GEOMETRY_FOR whole-BNST proposed canonical concept",
                                geometry_authority_available=True),
        geometry_construction="NOT_STARTED",
        created_at=ts)
    with open(OUT_PROP, "w", encoding="utf-8") as fh:
        json.dump(proposal, fh, ensure_ascii=False, indent=2)

    md = [
        "# Phase1.7 V3 - BNST canonical entity admission + granularity / G1-rollup decision", "",
        f"Admission: {admission['verdict']} (whole bed nucleus of the stria terminalis, WHOLE_BNST_COMPLEX).",
        "Terminology: BST == BNST == bed nucleus of the stria terminalis (SAME_CANONICAL_STRUCTURE).",
        f"Granularity: {gran['verdict']} on existing class '{gran['existing_granularity_code']}' (L3). "
        "No invented G2; no fabricated G1_MACRO.",
        f"G1 roll-up: {roll['verdict']}. Macro96 Basal Forebrain is a plausible parent via the "
        "existing Julich BST candidates (LIKELY + CONFLICT_REVIEW) but its containment is NOT "
        "adjudicated here (Basal Forebrain out of scope); no forced relation created.",
        "Repo audit: Macro96 BNST count 0; canonical BNST count 0; canonical NGIQ-BR BNST ids 0. "
        f"Julich G4 candidate BST rows: {len(candidates)} "
        f"({', '.join(c['source_entity_id'] for c in candidates)}).",
        "external_g1_asset_manifest 'supported_g1' = ASSET_TARGET_LABEL_WITHOUT_CANONICAL_ENTITY / "
        "SEMANTIC_LABEL_STALE_NOT_CANONICAL_G1.",
        f"Laterality: {proposal['laterality']} (Left BNST + Right BNST proposals).",
        "Canonical id status: PENDING_CANONICAL_ALLOCATION (no repo file-level allocator; no "
        "max+1 guessing; proposal ids PROP-BNST-L-V1 / PROP-BNST-R-V1 only).",
        "Blackford asset (human whole-BNST) SUPPORTS_GEOMETRY_FOR the proposed concept; "
        "geometry construction is NOT_STARTED (ontology admission only).",
        "Guards: no geometry / NIfTI / transform / DB write / promotion / classification change "
        "(86/132/93); prior frozen families unchanged; Julich candidate rows untouched.", ""]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    print("admission:", admission["verdict"])
    print("granularity:", gran["verdict"], "| existing class:", gran["existing_granularity_code"])
    print("rollup:", roll["verdict"], "(Basal Forebrain deferred)")
    print("julich candidates found:", len(candidates))
    print("ids: PENDING_CANONICAL_ALLOCATION (proposals PROP-BNST-L/R-V1)")
    print("geometry: NOT_STARTED | wrote 7 artifacts")


if __name__ == "__main__":
    main()
