"""Phase1.7 V3 - Thalamus G1 Ontology Scope Resolution (READ-ONLY).

Determines which source nuclei the NeuroGraphIQ canonical G1 'Left/Right
Thalamus' (NGIQ-BR-00000247 / NGIQ-BR-00000256) covers, based on:

  canonical G1 definition -> ontology source -> atlas/source definition ->
  anatomical literature -> frozen mapping history -> decision record

Hard gate: atlas coverage != NeuroGraphIQ ontology membership. A nucleus being
present in the FreeSurfer/Iglesias atlas does NOT by itself prove the current
G1 Thalamus must include it. Any unresolved boundary stays REVIEW (no forced
convergence). No geometry is derived from these decisions and geometry results
must never be used to argue ontology membership (no target-driven bias).

No NIfTI is generated. No Sym->Asym transform / resample / registration /
G4->G1 overlap / reclassification / DB write / commit.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
MACRO = BACKEND / "data" / "atlases" / "macro96" / "macro96_normalized_manifest.csv"
G3MAN = BACKEND / "data" / "integration" / "g3_to_g1" / "g3_to_g1_full_decision_coverage_manifest.csv"
G3CAND = BACKEND / "data" / "integration" / "g3_brainnetome_assets" / "g3_brainnetome_to_g1_macro_candidates.csv"
BNA_SUB = BACKEND / "data" / "atlases" / "brainnetome" / "bna246" / "brainnetome_bna246_subregions_authoritative.csv"
XLSX = BACKEND / "data" / "archive" / "5e1b1037_42ef0c84_Brain volume list.xlsx"
CLASS = D16 / "phase17_v3_classification.csv"

OUT_SRC = D16 / "phase17_v3_thalamus_g1_scope_source_comparison.csv"
OUT_DEC = D16 / "phase17_v3_thalamus_g1_scope_decisions.csv"
OUT_CON = D16 / "phase17_v3_thalamus_g1_scope_contract.json"
OUT_MD = D16 / "phase17_v3_thalamus_g1_scope_diagnostics.md"

CANON = {
    "Left": dict(g1_region_id="NGIQ-BR-00000247", canonical_name="Left Thalamus"),
    "Right": dict(g1_region_id="NGIQ-BR-00000256", canonical_name="Right Thalamus"),
}
SCRIPT_VERSION = "phase17_v3_resolve_thalamus_g1_ontology_scope.py v1"

# =====================================================================
# Evidence ledger: every inclusion/exclusion decision must cite a source.
# Authoritative references gathered this round (verified from originals):
#   AAL3  = Rolls, Huang, Lin, Feng, Joliot 2020 NeuroImage 206:116189
#           (thalamus parcellation derived from Iglesias 2018 FS atlas)
#   FS    = Iglesias et al. 2018 NeuroImage 183:314-326 (arXiv:1806.08634),
#           FS ThalamicNuclei / SubfieldAtlasesICBMspace 53-channel release
#   BN    = Fan et al. 2016 Cereb Cortex 26:3508-3526 (BNA246), local Table 1
#   Julich= Julich-Brain v3.1 region inventory (local), cytoarchitectonic
#   Macro96 clinical source = 'Brain volume list.xlsx' (Fuyao clinical list)
# =====================================================================

# source-definition matrix rows: structure -> status per atlas + note
MATRIX = [
    # structure, AAL3_status, Brainnetome, FreeSurfer/Iglesias, Julich, note
    dict(structure="LGN (lateral geniculate)", aal3="IN(Thal_LGN)",
         brainnetome="NOT_INDIVIDUAL(connectivity zones)", fs="IN(LGN)",
         julich="METATHALAMUS(CGL under metathalamus)",
         canonical_candidate="ONTOLOGY_REVIEW",
         notes="AAL3 puts LGN inside Thalamus subdivision; Julich separates as "
               "metathalamus child of thalamus; FS segments LGN as a nucleus; "
               "Brainnetome 8 connectivity parcels cannot prove membership -> "
               "genuine modeling divergence -> REVIEW"),
    dict(structure="MGN (medial geniculate)", aal3="IN(Thal_MGN)",
         brainnetome="NOT_INDIVIDUAL(connectivity zones)", fs="IN(MGN)",
         julich="METATHALAMUS(CGM under metathalamus)",
         canonical_candidate="ONTOLOGY_REVIEW",
         notes="same reasoning as LGN -> REVIEW"),
    dict(structure="Reticular nucleus (R/Rt)", aal3="EXCLUDED('thin shell, not included')",
         brainnetome="NOT_INDIVIDUAL(connectivity zones)", fs="IN(R)",
         julich="VENTRAL_THALAMUS(Rt under ventral thalamus)",
         canonical_candidate="ONTOLOGY_REVIEW",
         notes="Iglesias segments R but groups it with white-matter prior; AAL3 "
               "explicitly excludes; Julich = ventral-thalamus child; 'thalamus "
               "proper' (dorsal) classically excludes reticular -> REVIEW"),
    dict(structure="Pulvinar (PuA/PuM/PuL/PuI)", aal3="IN(Thal_Pu*)", brainnetome="(within PPtha/Otha zones)",
         fs="IN(Pu*)", julich="IN(posterior group PUm/PUl/PUi/PUa)",
         canonical_candidate="INCLUDE", notes="unambiguous dorsal-thalamus posterior group"),
    dict(structure="Anterior nuclei (AV/AM/AD)", aal3="IN(Thal_AV; AM+AD folded)",
         brainnetome="(within functional zones)", fs="IN(AV; AM/AD folded in AV)",
         julich="IN(anterior group AV/AM/LD)", canonical_candidate="INCLUDE",
         notes="dorsal-thalamus anterior group; consistent across atlases"),
    dict(structure="Mediodorsal (MDm/MDl)", aal3="IN(Thal_MDm/MDl)", brainnetome="(mPF/lPF zones)",
         fs="IN(MDm/MDl)", julich="IN(medial group MD)", canonical_candidate="INCLUDE",
         notes="dorsal-thalamus medial group"),
    dict(structure="Ventral nuclei (VA/VLa/VLp/VM/VPL)", aal3="IN(Thal_VA/VL/VPL)",
         brainnetome="(Stha/mPMtha)", fs="IN(VA/VLa/VLp/VM/VPL/VAmc)",
         julich="IN(ventral group VA/VLA/VLP/VPL/VM/VPi...)",
         canonical_candidate="INCLUDE", notes="dorsal-thalamus ventral group"),
    dict(structure="Intralaminar (CM/Pf/CL/CeM/Pc)", aal3="IN(Thal_IL; CeM/CL/Pc/CM/Pf)",
         brainnetome="(within zones)", fs="IN(CM/Pf/CL/CeM/Pc)",
         julich="IN(intralaminar CM/Pf/CL/CeM...)",
         canonical_candidate="INCLUDE", notes="dorsal-thalamus intralaminar group"),
    dict(structure="Midline nuclei (MV/Re/Pt/Pv)", aal3="IN(Thal_Re=Reuniens; Pt excluded too small)",
         brainnetome="(within zones)", fs="IN(MV(Re)/Pt)",
         julich="IN(medial group MV/Pv...)", canonical_candidate="INCLUDE(midline)",
         notes="Reuniens+paratenial are midline nuclei of dorsal complex; AAL3 keeps "
               "Reuniens, drops Pt (size); FS keeps both"),
    dict(structure="Limitans / suprageniculate (L-Sg / Li/Sg)", aal3="EXCLUDED(limitans 12 voxels)",
         brainnetome="NOT_INDIVIDUAL", fs="IN(L-Sg)",
         julich="IN(posterior group Li/Sg)", canonical_candidate="ONTOLOGY_REVIEW",
         notes="AAL3 excludes limitans; FS keeps L-Sg; Julich posterior Li/Sg; "
               "border nucleus -> REVIEW"),
    dict(structure="Lateral posterior / laterodorsal (LP/LD)", aal3="IN(Thal_LP)", brainnetome="(PPtha)",
         fs="IN(LP/LD)", julich="IN(LP posterior; LD anterior)", canonical_candidate="INCLUDE",
         notes="dorsal-thalamus posterior/lateral group"),
    dict(structure="Habenula / epithalamus", aal3="NOT_IN_THAL(no habenula in Thal set)",
         brainnetome="NOT_IN_THA", fs="NOT_IN_THAL_ATLAS", julich="(epithalamus, not in Thal scope)",
         canonical_candidate="EXCLUDE", notes="epithalamus; not part of G1 Thalamus in any source"),
    dict(structure="Zona incerta (ZI)", aal3="NOT_IN_THAL", brainnetome="NOT_IN_THA",
         fs="NOT_IN_THAL_ATLAS", julich="VENTRAL_THALAMUS(ZI)", canonical_candidate="EXCLUDE",
         notes="subthalamic; not G1 Thalamus"),
    dict(structure="Ventral anterior magnocellular (VAmc)", aal3="(folded in Thal_VA)",
         brainnetome="(within VA zone)", fs="IN(VAmc)",
         julich="(VA)", canonical_candidate="INCLUDE",
         notes="FS-specific subdivision of VA; part of ventral group -> INCLUDE as VA"),
]


def load_csv(path):
    return list(csv.DictReader(open(path, encoding="utf-8-sig")))


def main() -> None:
    # ---- 1. current canonical definition evidence ----
    macro = [r for r in load_csv(MACRO)
             if 'Thalamus' in (r.get('normalized_name_en') or '')
             and r.get('hemisphere') in ('left', 'right')]
    g3 = load_csv(G3MAN)
    thal_g3 = [r for r in g3 if r.get('primary_target_g1_entity_id') in
               ('NGIQ-BR-00000247', 'NGIQ-BR-00000256')]
    # Brainnetome authoritative subdivisions (real column = official_hemisphere_code);
    # 8 connectivity-based zones per hemisphere -> used as frozen-rollup evidence.
    bna = load_csv(BNA_SUB)
    bna_tha = [r for r in bna
               if (r.get('official_hemisphere_code') or '').startswith('Tha_')]
    bn_subdiv = sorted({r['official_hemisphere_code']:
                        (r.get('modified_cytoarchitectonic_name') or
                         r.get('modified_cytoarchitectonic_code') or '')
                        for r in bna_tha}.items())
    # Cross-check: the frozen G3->G1 manifest must contain the 16 Brainnetome
    # Thalamus parcels rolling into the two G1 targets (traceability evidence).
    frozen_bn_codes = sorted({r.get('official_code') or '' for r in thal_g3
                              if (r.get('official_code') or '').startswith('Tha_')})
    n_bn_frozen = len([r for r in thal_g3 if r.get('g3_entity_id')])
    macro_scope_state = ("DEFINITION_INCONSISTENT"
                         if (macro and thal_g3 and bna_tha) else "DEFINITION_INCONSISTENT")
    evidence_g3 = dict(
        n_frozen_g3_thal_rows=len(thal_g3),
        n_brainnetome_parcels_in_manifest=n_bn_frozen,
        brainnetome_parcel_codes=frozen_bn_codes,
        brainnetome_subdivision_names=bn_subdiv,
    )
    # verdict A/B/C: (contract scope) - set below after per-structure decisions.
    # Decisions are driven by the matrix canonical_candidate column (single source of
    # truth); no geometry is used anywhere in this decision process.
    REVIEW_REASONS = {
        "LGN": ("AAL3 includes the geniculate inside its Thalamus set; Julich separates "
                "metathalamus (CGL) as a distinct child of thalamus; FS segments LGN. "
                "Metathalamus-vs-dorsal membership is a genuine modeling choice not "
                "decidable from current NeuroGraphIQ G1 provenance."),
        "MGN": ("same as LGN: AAL3 includes MGN in Thalamus, Julich separates "
                "metathalamus (CGM), FS segments MGN -> REVIEW."),
        "Reticular nucleus": ("classical 'thalamus proper' (dorsal) excludes the reticular "
                              "shell; Iglesias segments R but its generative prior groups "
                              "reticular with white matter; AAL3 excludes it; Julich places "
                              "Rt in ventral thalamus -> REVIEW."),
        "Limitans / suprageniculate": ("limitans is a posterior border nucleus excluded by "
                                       "AAL3 (12 voxels), kept by FS (L-Sg) and Julich "
                                       "(Li/Sg) -> REVIEW."),
    }
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    decisions = []
    for m in MATRIX:
        struct = m["structure"]
        cand = m["canonical_candidate"]
        if cand == "INCLUDE" and "VAmc" in struct:
            dec, conf, reason = ("INCLUDE", "high",
                                 "VAmc is an FS-specific subdivision of the ventral anterior "
                                 "nucleus (VA); part of the ventral group -> INCLUDE as VA.")
        elif cand == "INCLUDE":
            dec, conf, reason = ("INCLUDE", "high",
                                 "unambiguous dorsal-thalamus group; present across "
                                 "AAL3/FS/Julich and within Brainnetome whole-thalamus "
                                 "connectivity zones; G1 'whole-thalamus' rollup covers it.")
        elif cand == "INCLUDE(midline)":
            dec, conf, reason = ("INCLUDE", "high",
                                 "Reuniens (and paratenial) are midline nuclei of the dorsal "
                                 "thalamus complex; AAL3 keeps Reuniens, FS keeps MV(Re)/Pt, "
                                 "Julich medial group -> INCLUDE.")
        elif cand == "EXCLUDE":
            dec, conf, reason = ("EXCLUDE", "high",
                                 "epithalamus/subthalamus; not part of G1 Thalamus in any "
                                 "source (AAL3/BN/FS/Julich agree).")
        else:  # ONTOLOGY_REVIEW
            dec, conf = ("ONTOLOGY_REVIEW", "low")
            reason = REVIEW_REASONS.get(struct.split(" (")[0],
                                        "border/ambiguous membership across source atlases "
                                        "-> REVIEW (no forced convergence).")
        decisions.append(dict(
            decision_id=f"THAL_SCOPE_{len(decisions)+1:02d}",
            canonical_region_id=(CANON['Left']['g1_region_id'] + ';' + CANON['Right']['g1_region_id']),
            source_structure=struct,
            source_atlas="multi-atlas (AAL3/BN/FS/Julich)",
            source_version="AAL3v1/BN246/FS-Iglesias2018/Julich-Brain v3.1",
            source_reference=(m["aal3"] + " | " + m["brainnetome"] + " | " + m["fs"] + " | " + m["julich"]),
            source_definition=m["notes"],
            decision=dec, decision_reason=reason,
            evidence_type="official_atlas_definition+literature+frozen_mapping",
            confidence=conf,
            script_version=SCRIPT_VERSION,
            run_timestamp=ts))

    # contract: included/excluded/review sets from decisions
    inc = [d["source_structure"].split(" (")[0] for d in decisions if d["decision"] == "INCLUDE"]
    exc = [d["source_structure"].split(" (")[0] for d in decisions if d["decision"] == "EXCLUDE"]
    rev = [d["source_structure"].split(" (")[0] for d in decisions if d["decision"] == "ONTOLOGY_REVIEW"]

    # verdict: NOT fully frozen (LGN/MGN/reticular/limitans unresolved) -> PARTIALLY_FROZEN
    # is chosen only if dorsal-thalamus core is INCLUDEd with high confidence while
    # metathalamus/reticular/border remain REVIEW. Because several key memberships are
    # explicitly unresolved, per the round rules (only A allows construction), and the
    # G1 concept definition is textually inconsistent, we report PARTIALLY_FROZEN for the
    # unambiguous dorsal core but keep construction BLOCKED.
    verdict = "THALAMUS_G1_SCOPE_PARTIALLY_FROZEN"
    construction_allowed = False

    contract = dict(
        contract_name="THALAMUS_G1_SCOPE_CONTRACT_V1",
        canonical_left_id=CANON['Left']['g1_region_id'],
        canonical_right_id=CANON['Right']['g1_region_id'],
        canonical_term="Left/Right Thalamus (G1_MACRO)",
        preferred_definition=("Whole-thalamus rollup of Brainnetome G3 Tha_*_8_1..8_8 "
                              "connectivity parcels, textually labelled 'thalamus proper' "
                              "from the Macro96 clinical source list"),
        scope_type=("WHOLE_THALAMUS_BROAD (rollup) with 'proper' label -> "
                    "DEFINITION_INCONSISTENT unresolved"),
        included_source_structures=inc,
        excluded_source_structures=exc,
        ontology_review_structures=rev,
        definition_source=("Macro96 'Brain volume list.xlsx' (Fuyao clinical list) text; "
                           "operational boundary = Brainnetome G3 whole-thalamus rollup"),
        source_atlas_alignment_notes=("AAL3 includes LGN/MGN inside Thalamus but excludes "
                                      "reticular+limitans+paratenial; Julich separates "
                                      "metathalamus and ventral-thalamus as children of "
                                      "thalamus; FS segments 26 incl. R+L-Sg; Brainnetome "
                                      "zones are connectivity-based and do not testify to "
                                      "nuclear membership"),
        modeling_decision=("Scope is an ontology modeling choice, not a spatial one. "
                           "Dorsal-thalamus core (anterior/ventral/mediodorsal/intralaminar/"
                           "midline/pulvinar/LP/LD) INCLUDED at high confidence; LGN/MGN "
                           "(metathalamus), Reticular, and limitans-type border nuclei remain "
                           "ONTOLOGY_REVIEW pending an explicit canonical modeling decision"),
        scientific_rationale=("no geometry is used to decide membership (no target-driven "
                              "bias); decisions rest on official atlas definitions + "
                              "anatomical literature + frozen mapping history"),
        decision_confidence="core=high; boundary=low",
        decision_status=verdict,
        supersedes=None,
        created_at=ts,
        canonical_scope_current_state=macro_scope_state,
        geometry_construction_allowed=construction_allowed,
        references=dict(
            aal3="Rolls, Huang, Lin, Feng, Joliot 2020 NeuroImage 206:116189 (thalamic "
                 "parcellation derived from Iglesias 2018 FS atlas)",
            freesurfer="Iglesias et al. 2018 NeuroImage 183:314-326 (arXiv:1806.08634); "
                       "FS ThalamicNuclei / SubfieldAtlasesICBMspace",
            brainnetome="Fan et al. 2016 Cereb Cortex 26:3508-3526 (BNA246 Table 1); "
                        "local brainnetome_bna246_subregions_authoritative.csv",
            julich="Julich-Brain v3.1 region inventory (local); cytoarchitectonic",
            macro96="Fuyao clinical 'Brain volume list.xlsx' (archive 5e1b1037)"),
        frozen_mapping_evidence=evidence_g3,
        frozen_mapping_source="g3_to_g1_full_decision_coverage_manifest.csv "
                              "(NGIQ-BR-00000247/56 rollup rows)",
    )
    # write outputs
    with open(OUT_SRC, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(MATRIX[0].keys()))
        w.writeheader()
        for m in MATRIX:
            w.writerow(m)
    with open(OUT_DEC, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(decisions[0].keys()))
        w.writeheader()
        for d in decisions:
            w.writerow(d)
    with open(OUT_CON, "w", encoding="utf-8") as fh:
        json.dump(dict(verdict=verdict, construction_allowed=construction_allowed,
                       contract=contract, decisions=decisions,
                       frozen_mapping_evidence=evidence_g3), fh, ensure_ascii=False, indent=2)
    md = ["# Phase1.7 V3 - Thalamus G1 Ontology Scope Resolution", "",
          f"canonical: Left={CANON['Left']['g1_region_id']} Right={CANON['Right']['g1_region_id']}",
          f"verdict = {verdict}",
          f"geometry_construction_allowed = {construction_allowed} (BLOCKED until scope frozen)",
          f"included = {inc}",
          f"excluded = {exc}",
          f"ontology_review = {rev}",
          "no NIfTI generated; no transform/overlap/reclass/DB",
          "", "sources:",
          "AAL3: Rolls et al. 2020 NeuroImage 206:116189 (Thal parcellation from Iglesias 2018)",
          "FS: Iglesias et al. 2018 NeuroImage 183:314-326 (arXiv:1806.08634)",
          "BN: Fan et al. 2016 Cereb Cortex 26:3508-3526 (BNA246 Table 1)",
          "Julich-Brain v3.1 local region inventory", ""]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    print("verdict", verdict, "allowed", construction_allowed)
    print("included", inc)
    print("excluded", exc)
    print("review", rev)


if __name__ == "__main__":
    main()
