"""Phase1.7 V3 - Thalamus G1 Canonical Concept Identity + Boundary Adjudication.

Freezes the anatomical concept expressed by the canonical G1 entities
NGIQ-BR-00000247 (Left Thalamus) and NGIQ-BR-00000256 (Right Thalamus), then
adjudicates the four boundary structures (LGN, MGN, Reticular nucleus,
Limitans/suprageniculate) strictly against that frozen identity.

Scientific traceability hard gate: every decision traces
  source concept -> source terminology -> current canonical record -> frozen
  mappings -> authoritative human neuroanatomy -> explicit modeling decision.
Atlas inclusion NEVER equals ontology membership. No target-driven design:
a definition is not chosen because it covers more existing mappings.

No geometry is built. No transform/resample/overlap/reclassify/DB/commit.
V1 scope contract is left untouched (historical snapshot); this round emits V2.

Human/authoritative terminology sources (verified from the originals):
  Mai JK, Forutan F, Kempermann G. 2018. "Toward a Common Terminology for the
    Thalamus." Front. Neuroanat. 12:114. doi:10.3389/fnana.2018.00114
    - 'metathalamus' term questioned: geniculate bodies are integral parts of
      the lateral (dorsal) thalamus; reticular nucleus = ventral thalamus /
      perithalamus (classification contested); no single universal parcellation.
  UBERON / NIFSTD / MeSH (dorsal plus ventral thalamus UBERON:0001897):
    - 'thalamus' is ambiguous between dorsal-thalamus ('thalamus proper') and
      the wider dorsal+ventral aggregate; metathalamus 'more commonly included
      as part of the dorsal thalamus'.
  Rolls et al. 2020 (AAL3) NeuroImage 206:116189 - Thal_LGN/Thal_MGN inside
    Thalamus parcellation; reticular + limitans + paratenial excluded.
  Iglesias et al. 2018 (FS) NeuroImage 183:314-326 - 26 nuclei/hemisphere incl.
    LGN, MGN, R (reticular; prior groups it with WM), L-Sg.
  Julich-Brain v3.1 (local inventory) - metathalamus (CGL/CGM) and ventral
    thalamus (Rt, ZI) as children of 'thalamus'; dorsal groups children too.
  Fan et al. 2016 (BNA246) - G3 'Thalamus' = 8 connectivity-based zones/side.
  Macro96 clinical source = Fuyao 'Brain volume list.xlsx' rows 6/22,
    label 'thalamus proper' (label-only; no formal definition column).
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
MACRO = BACKEND / "data" / "atlases" / "macro96" / "macro96_normalized_manifest.csv"
V1 = D16 / "phase17_v3_thalamus_g1_scope_contract.json"

OUT_CMP = D16 / "phase17_v3_thalamus_canonical_identity_comparison.csv"
OUT_ADJ = D16 / "phase17_v3_thalamus_boundary_adjudication.csv"
OUT_V2 = D16 / "phase17_v3_thalamus_g1_scope_contract_v2.json"
OUT_MD = D16 / "phase17_v3_thalamus_canonical_identity_diagnostics.md"

CANON = {
    "Left": dict(g1_region_id="NGIQ-BR-00000247", canonical_name="Left Thalamus"),
    "Right": dict(g1_region_id="NGIQ-BR-00000256", canonical_name="Right Thalamus"),
}
SCRIPT_VERSION = "phase17_v3_adjudicate_thalamus_canonical_identity.py v1"

# Modeling decision (Section 5). Selected on human-anatomical evidence, NOT on
# which definition covers more mappings:
#   The source label is literally 'thalamus proper'. FreeSurfer aseg itself names
#   the structure 'Thalamus-Proper' for the dorsal thalami mass. Modern consensus
#   (Mai 2018; UBERON) reads dorsal-thalamus ('thalamus proper') as INCLUDING the
#   geniculate bodies (metathalamus 'more commonly included as part of the dorsal
#   thalamus') and EXCLUDING the reticular nucleus (ventral/perithalamus). This is
#   the concept the canonical entity expresses. => CANONICAL_IDENTITY_FROZEN_THALAMUS_PROPER
IDENTITY_DECISION = "CANONICAL_IDENTITY_FROZEN_THALAMUS_PROPER"
PREFERRED_CANONICAL_NAME = "Thalamus (dorsal thalami mass; 'thalamus proper')"
IDENTITY_DEFINITION = (
    "The canonical G1 'Thalamus' expresses the DORSAL THALAMUS (thalamus proper): "
    "the main thalami mass of the diencephalon comprising the classical dorsal "
    "thalamic nuclear groups (anterior, medial, lateral, ventral, posterior/"
    "pulvinar, intralaminar, midline) plus the geniculate bodies (LGN/MGN), which "
    "modern consensus includes as integral parts of the dorsal thalamus. It EXCLUDES "
    "the ventral thalamus / perithalamus (reticular nucleus Rt, zona incerta ZI), "
    "the epithalamus (habenula), and the subthalamus. Source label 'thalamus proper' "
    "is retained verbatim; it is not upgraded into an independent ontology concept.")

# identity comparison rows: concept x source
CMP = [
    dict(structure="Canonical G1 Left/Right Thalamus (247/256)",
         macro96_status="label 'thalamus proper'; G1_MACRO; no formal definition",
         brainnetome_status="populated by whole-Thalamus 8 connectivity zones/side",
         aal3_status="AAL3 'Thalamus' parcellation (dorsal incl. Thal_LGN/MGN; excl. R/L-Sg/Pt)",
         freesurfer_status="aseg 'Thalamus-Proper' (dorsal mass); Iglesias 26 nuclei",
         julich_status="thalamus parent -> dorsal/ventral/metathalamus children",
         common_term_status="Mai 2018: dorsal-thalamus proper incl. geniculates, excl. reticular",
         controlled_status="UBERON:0001897 ambiguity dorsal vs dorsal+ventral; geniculates in dorsal",
         modeling_decision=IDENTITY_DECISION),
    dict(structure="THALAMUS_PROPER (dorsal)",
         macro96_status="label basis", brainnetome_status="not separately modeled",
         aal3_status="implied by Thal_* dorsal set", freesurfer_status="aseg Thalamus-Proper",
         julich_status="dorsal groups", common_term_status="Mai: geniculates included; reticular excl.",
         controlled_status="UBERON dorsal-thalamus", modeling_decision="selected identity"),
    dict(structure="THALAMUS_BROAD (wider/diencephalic-thalamic)",
         macro96_status="not supported by 'proper' label", brainnetome_status="closest to rollup extent",
         aal3_status="wider than AAL3 Thal", freesurfer_status="broader than aseg",
         julich_status="= parent 'thalamus' (incl ventral+metathalamus children)",
         common_term_status="not the label intent", controlled_status="UBERON dorsal+ventral aggregate",
         modeling_decision="NOT selected (label + consensus support dorsal 'proper')"),
    dict(structure="THALAMIC_COMPLEX (metathalamus+reticular as one complex)",
         macro96_status="not expressed", brainnetome_status="not expressed",
         aal3_status="not AAL3 usage", freesurfer_status="not FS usage",
         julich_status="not a single Julich node (split into ventral + metathalamus)",
         common_term_status="reticular/perithalamus + geniculates are separate developmental domains",
         controlled_status="not a UBERON single class", modeling_decision="rejected as single concept"),
]


def main() -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # ---- current entity provenance (read-only) ----
    macro = [r for r in csv.DictReader(open(MACRO, encoding="utf-8-sig"))
             if 'Thalamus' in (r.get('normalized_name_en') or '')
             and r.get('hemisphere') in ('left', 'right')]
    identity_provenance = []
    for r in macro:
        identity_provenance.append(dict(
            canonical_id=(CANON['Left']['g1_region_id'] if r['hemisphere'] == 'left'
                          else CANON['Right']['g1_region_id']),
            current_name=("Left Thalamus" if r['hemisphere'] == 'left' else "Right Thalamus"),
            source_name=r.get('source_name_en'),
            source_file="Brain volume list.xlsx (Fuyao clinical) + macro96_normalized_manifest.csv",
            source_row=r.get('source_row_id'),
            original_definition="SOURCE_LABEL_ONLY_NO_FORMAL_DEFINITION",
            normalized_name=r.get('normalized_name_en'),
            hemisphere=r.get('hemisphere'),
            structure_type=r.get('structure_type'), granularity=r.get('granularity_level'),
            existing_parent="(canonical record not exported in this read-only round)",
            existing_children="(none materialized)",
            frozen_g3_rollups="Brainnetome Tha_*_8_1..8_8 (8/side) -> G1 (frozen manifest)",
            historical_decisions="AUTO_HIGH coarse aggregation (authoritative anatomical mapping)"))

    # ---- boundary adjudication (strictly against frozen identity) ----
    # LGN/MGN: identity = THALAMUS_PROPER which, per Mai 2018 + UBERON consensus,
    # includes geniculate bodies in the dorsal thalamus => INCLUDE (boundary case
    # documented as a metathalamus naming divergence, not auto-included from FS/AAL3).
    # Reticular: ventral/perithalamus, outside dorsal-thalamus proper => EXCLUDE.
    # L-Sg: small posterior-complex border nucleus, genuinely contested (AAL3 drops
    # for size; FS/Julich keep) => REVIEW (no forced convergence).
    rulings = [
        dict(decision_id="DEC-THAL-01", structure="LGN (lateral geniculate)",
             canonical_identity_used=IDENTITY_DECISION,
             decision="INCLUDE", confidence="medium",
             rationale=("Identity = THALAMUS_PROPER (dorsal). Modern consensus (Mai 2018; "
                        "UBERON) treats the dorsal lateral geniculate nucleus as an integral "
                        "part of the dorsal/lateral thalamus; the 'metathalamus' label is "
                        "questioned precisely because it implies the geniculates are not "
                        "integral parts. AAL3 (Thal_LGN) and Iglesias (LGN) agree. This is "
                        "an explicit modeling reading of the geniculate as dorsal-thalamus; "
                        "it is NOT 'auto-include because FS/AAL3 carry it'."),
             primary_evidence="Mai 2018 Front Neuroanat 12:114 (geniculate bodies integral to lateral/dorsal thalamus)",
             secondary_evidence="AAL3 Thal_LGN; Iglesias 2018 LGN; UBERON metathalamus-in-dorsal"),
        dict(decision_id="DEC-THAL-02", structure="MGN (medial geniculate)",
             canonical_identity_used=IDENTITY_DECISION,
             decision="INCLUDE", confidence="medium",
             rationale=("Same identity basis as LGN: MGN is a dorsal-thalamus geniculate "
                        "body under modern consensus; AAL3 (Thal_MGN) and Iglesias (MGN) "
                        "agree. Metathalamus naming divergence documented, not a reason to "
                        "EXCLUDE under a dorsal-'proper' identity."),
             primary_evidence="Mai 2018; UBERON metathalamus-in-dorsal",
             secondary_evidence="AAL3 Thal_MGN; Iglesias 2018 MGN"),
        dict(decision_id="DEC-THAL-03", structure="Reticular nucleus (R/Rt)",
             canonical_identity_used=IDENTITY_DECISION,
             decision="EXCLUDE", confidence="high",
             rationale=("Reticular nucleus is a ventral-thalamus / perithalamus shell "
                        "separated from the dorsal thalami mass by the external medullary "
                        "lamina; it is NOT part of dorsal-thalamus 'proper'. AAL3 excludes "
                        "it; Julich places Rt under ventral-thalamus; Iglesias segments it "
                        "but its generative prior groups reticular with white matter. "
                        "Iglesias 'thalamic nuclei atlas coverage' does not make Rt a member "
                        "of NeuroGraphIQ G1 'thalamus proper'."),
             primary_evidence="Mai 2018; AAL3 (excluded); Julich (ventral-thalamus Rt)",
             secondary_evidence="UBERON reticular = ventral/perithalamus; Iglesias R (WM-prior)"),
        dict(decision_id="DEC-THAL-04", structure="Limitans / suprageniculate (L-Sg / Li / Sg)",
             canonical_identity_used=IDENTITY_DECISION,
             decision="REVIEW", confidence="low",
             rationale=("L-Sg is a small posterior-complex / metathalamic-adjacent border "
                        "nucleus. Membership is genuinely contested: AAL3 drops limitans "
                        "for size (12 voxels), FS keeps L-Sg, Julich keeps posterior Li/Sg. "
                        "It is spatially near MGN but must NOT be assumed to follow the MGN "
                        "decision. Left in REVIEW (no forced convergence) pending an "
                        "explicit small-nucleus / posterior-complex modeling decision."),
             primary_evidence="AAL3 (excluded, size); Julich posterior Li/Sg; Iglesias L-Sg",
             secondary_evidence="Mai 2018 posterior nuclear complex discussion")]

    # Validate that the on-disk V1 is the contract we claim to supersede (not a
    # hardcoded assertion): read V1's contract_name, warn if it does not match.
    v1_present = V1.exists()
    v1_name = None
    if v1_present:
        try:
            with open(V1, encoding="utf-8") as fh:
                v1_name = json.load(fh).get("contract", {}).get("contract_name")
        except Exception:
            v1_name = None
    supersedes_id = "THALAMUS_G1_SCOPE_CONTRACT_V1"
    if v1_name is not None and v1_name != supersedes_id:
        print(f"WARN: on-disk V1 name {v1_name!r} != expected {supersedes_id!r}")
    contract_v2 = dict(
        contract_id="THALAMUS_G1_SCOPE_CONTRACT_V2",
        supersedes=supersedes_id,
        supersedes_verified=(v1_name == supersedes_id),
        canonical_left_id=CANON['Left']['g1_region_id'],
        canonical_right_id=CANON['Right']['g1_region_id'],
        source_label="thalamus proper (source rows 6/22, Fuyao Brain volume list.xlsx)",
        preferred_canonical_name=PREFERRED_CANONICAL_NAME,
        canonical_identity=IDENTITY_DECISION,
        canonical_definition=IDENTITY_DEFINITION,
        definition_version="1.0",
        included_structures=["dorsal-thalamus nuclear groups (anterior, medial, lateral, "
                             "ventral, posterior/pulvinar, intralaminar, midline)",
                             "LGN (DEC-THAL-01)", "MGN (DEC-THAL-02)"],
        excluded_structures=["Reticular nucleus Rt (DEC-THAL-03)", "Zona incerta (ventral)",
                             "Epithalamus / habenula", "Subthalamus"],
        review_structures=["Limitans / suprageniculate L-Sg (DEC-THAL-04)"],
        LGN_decision="INCLUDE (DEC-THAL-01)",
        MGN_decision="INCLUDE (DEC-THAL-02)",
        reticular_decision="EXCLUDE (DEC-THAL-03)",
        limitans_suprageniculate_decision="REVIEW (DEC-THAL-04)",
        modeling_rationale=("Canonical identity frozen as THALAMUS_PROPER on the strength of "
                            "the source label ('thalamus proper') + FreeSurfer aseg "
                            "'Thalamus-Proper' convention + modern consensus that dorsal "
                            "thalamus includes geniculate bodies and excludes the reticular "
                            "shell. Chosen on anatomy/label, NOT to cover more mappings."),
        primary_sources=["Mai et al. 2018 Front Neuroanat 12:114",
                         "Rolls et al. 2020 NeuroImage 206:116189 (AAL3)",
                         "Iglesias et al. 2018 NeuroImage 183:314-326",
                         "Fan et al. 2016 Cereb Cortex 26:3508-3526 (BNA246)"],
        secondary_sources=["UBERON:0001897 / NIFSTD / MeSH",
                           "Julich-Brain v3.1 region inventory",
                           "FreeSurfer aseg label convention ('Thalamus-Proper')"],
        confidence="identity=high; LGN/MGN=medium; reticular=high; L-Sg=low",
        status="THALAMUS_G1_SCOPE_PARTIALLY_FROZEN",
        geometry_construction_allowed=False,
        # two INDEPENDENT block reasons: even if L-Sg were resolved, the frozen
        # rollup basis (whole-thalamus Brainnetome zones) has not been reconciled
        # to THALAMUS_PROPER territory, so geometry must remain blocked.
        geometry_blocked_reasons=[
            "L-Sg (limitans/suprageniculate) stays REVIEW (DEC-THAL-04) - unresolved",
            ("frozen G1 rollup basis is the whole-thalamus Brainnetome Tha_*_8_1..8_8 "
             "zones (BROAD extent); not yet reconciled to the frozen THALAMUS_PROPER "
             "(dorsal) identity territory")],
        evidence_note=("Two evidentiary tiers are kept separate: (a) FreeSurfer aseg "
                       "'Thalamus-Proper' supports a dorsal-mass LABEL CONVENTION and does "
                       "not itself segment geniculate bodies; (b) LGN/MGN dorsal-thalamus "
                       "MEMBERSHIP rests on the Mai-2018 / UBERON consensus that geniculate "
                       "bodies are integral to the dorsal thalamus. FS atlas geometry is NOT "
                       "cited as evidence for geniculate inclusion."),
        created_at=ts,
        v1_present_at_creation=v1_present,
    )
    # verdict: not FROZEN because L-Sg stays REVIEW => geometry BLOCKED
    verdict = "THALAMUS_G1_SCOPE_PARTIALLY_FROZEN"
    construction_allowed = False

    # write identity comparison CSV
    with open(OUT_CMP, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(CMP[0].keys()))
        w.writeheader()
        for r in CMP:
            w.writerow(r)
    with open(OUT_ADJ, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rulings[0].keys()))
        w.writeheader()
        for r in rulings:
            w.writerow(r)
    with open(OUT_V2, "w", encoding="utf-8") as fh:
        json.dump(dict(verdict=verdict, construction_allowed=construction_allowed,
                       identity_decision=IDENTITY_DECISION,
                       contract_v2=contract_v2,
                       identity_provenance=identity_provenance,
                       boundary_rulings=rulings,
                       script_version=SCRIPT_VERSION, run_timestamp=ts),
                  fh, ensure_ascii=False, indent=2)
    md = ["# Phase1.7 V3 - Thalamus Canonical Concept Identity + Boundary Adjudication", "",
          f"identity_decision = {IDENTITY_DECISION}",
          f"preferred_canonical_name = {PREFERRED_CANONICAL_NAME}",
          f"verdict = {verdict}  construction_allowed = {construction_allowed}",
          "included: dorsal-thalamus groups; LGN (DEC-THAL-01); MGN (DEC-THAL-02)",
          "excluded: Reticular Rt (DEC-THAL-03); ZI; epithalamus; subthalamus",
          "review: Limitans/suprageniculate L-Sg (DEC-THAL-04)",
          "V1 scope contract left untouched; V2 supersedes V1.",
          "no geometry/transform/overlap/reclass/DB; no commit",
          "", "sources:", "- Mai et al. 2018 Front Neuroanat 12:114",
          "- Rolls et al. 2020 NeuroImage 206:116189 (AAL3)",
          "- Iglesias et al. 2018 NeuroImage 183:314-326",
          "- Fan et al. 2016 Cereb Cortex 26:3508-3526 (BNA246)",
          "- UBERON:0001897 / MeSH; Julich-Brain v3.1; FreeSurfer aseg", ""]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    print("identity", IDENTITY_DECISION)
    print("verdict", verdict, "construction_allowed", construction_allowed)
    print("rulings:", [(r['decision_id'], r['structure'][:28], r['decision']) for r in rulings])


if __name__ == "__main__":
    main()
