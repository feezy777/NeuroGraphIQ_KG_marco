"""Phase1.7 V3 - Basal Forebrain G1 canonical scope + geometry authority adjudication.

ONTOLOGY/AUTHORITY ADJUDICATION ONLY. Does NOT build Basal Forebrain NIfTI, does NOT
union Ch1-Ch4, does NOT run any spatial transform, does NOT create Julich-grid
geometry, does NOT modify BNST, does NOT create a BNST->Basal Forebrain relation,
does NOT do G4->G1 direct validation, does NOT reclassify, does NOT write DB, does
NOT promote.

Two independent questions:
  Q1 WHAT_IS_BASAL_FOREBRAIN_G1?
  Q2 DOES_ZABORSZKY_CH1_CH4_GEOMETRY_REPRESENT_IT?

Live repo evidence:
  - Macro96 rows 30/31 "Left/Right Basal Forebrain": structure_type 'basal_forebrain',
    normalization_note "coarse/composite anatomical region (FreeSurfer aseg)";
    label-only, no formal definition.
  - Canonical G1 ids (from phase17 classification candidate-g1 records):
      Left Basal Forebrain  NGIQ-BR-00000264
      Right Basal Forebrain NGIQ-BR-00000265
  - phase17 candidate rows targeting Basal Forebrain G1 (all LIKELY_..._SPATIAL_REVIEW
    + CONFLICT_REVIEW, none VERIFIED): Ch4 L/R, BST L/R, Ch123 L/R.
  - Zaborszky acquisition: BF_ZABORSZKY_CH1234 = NOT_ACQUIRED / ACCESS_RESTRICTED
    (raw SHA null - never fake).
  - Julich-Brain v3.1 cytoarchitectonic 'basal forebrain' group maps ARE locally
    stored (CH_4, CH_123, TU, TUTi, BST; MNI152NLin2009cAsym) - alternative human
    cyto evidence; no multi-atlas fusion.

Decisions (ontology first, geometry second):
  Identity : D. SOURCE_LABEL_ONLY_CONSERVATIVE_OPERATIONAL_SCOPE
             Macro96 'Basal Forebrain' = label only (FS aseg composite). Conservative
             operational scope = cholinergic magnocellular basal forebrain territory
             (Ch1-Ch4/NbM magnocellular cell groups + septal/diagonal band origins +
             the surrounding FS-aseg basal-forebrain territory). NOT broad ventral
             forebrain (NAcc / ventral pallidum / olfactory tubercle / BNST not
             auto-included). NOT asserted as a formal ontology equality
             'Basal Forebrain = Ch1 u Ch2 u Ch3 u Ch4'.
  Scope    : INCLUDE Ch1..Ch4/NbM + diagonal band (cell groups); EXCLUDE NAcc / ventral
             pallidum / olfactory tubercle / BNST / anterior commissure; REVIEW
             substantia innominata territory + broad septal nuclei.
  Authority: Zaborszky 2008 maps the magnocellular cell groups Ch1-Ch4/NbM ->
             AUTHORITATIVE_OPERATIONAL_PROXY_GEOMETRY for the conservative operational
             (cholinergic magnocellular) G1 territory; NOT a complete broad-anatomy BF
             boundary. Asset status NOT_ACQUIRED -> geometry acquisition BLOCKED.
  Alternative source (locally available): Julich-Brain v3.1 cyto CH_123 + CH_4 maps -
             recorded, NOT fused, NOT substituted as the primary scientific authority.
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
ACQ_CSV = D16 / "phase17_v3_external_raw_asset_acquisition.csv"
JUL_DIR = BACKEND / "data" / "atlases" / "julich" / "v3.1" / "spatial_raw" / "probability_maps"
LEFT_BF, RIGHT_BF = "NGIQ-BR-00000264", "NGIQ-BR-00000265"
IDENTITY_ID = "BASAL_FOREBRAIN_G1_CANONICAL_IDENTITY_V1"
SCOPE_ID = "BASAL_FOREBRAIN_G1_SCOPE_CONTRACT_V1"
AUTH_ID = "BASAL_FOREBRAIN_GEOMETRY_AUTHORITY_V1"
SCRIPT_VERSION = "phase17_v3_adjudicate_basal_forebrain_g1_scope_authority.py v1"

OUT_AUDIT = D16 / "phase17_v3_basal_forebrain_canonical_source_audit.json"
OUT_XWALK = D16 / "phase17_v3_basal_forebrain_anatomical_crosswalk.csv"
OUT_ID = D16 / "phase17_v3_basal_forebrain_canonical_identity_v1.json"
OUT_SCOPE = D16 / "phase17_v3_basal_forebrain_g1_scope_contract_v1.json"
OUT_ZAB = D16 / "phase17_v3_basal_forebrain_zaborszky_authority_audit.json"
OUT_AUTH = D16 / "phase17_v3_basal_forebrain_geometry_authority_v1.json"
OUT_ALT = D16 / "phase17_v3_basal_forebrain_alternative_source_inventory.csv"
OUT_HIST = D16 / "phase17_v3_basal_forebrain_historical_mapping_compatibility.csv"
OUT_MD = D16 / "phase17_v3_basal_forebrain_scope_authority_diagnostics.md"

# crosswalk rows:
# (structure, broad_anatomical_BF, cholinergic_BF_system, represented_in_zaborszky,
#  current_G1_scope, evidence, confidence)
CROSSWALK = [
    ("Medial septal nucleus / Ch1", True, True, True, "INCLUDE",
     "cholinergic basal-forebrain magnocellular group (Ch1); in Zaborszky Ch1-4 maps", "HIGH"),
    ("Vertical limb of diagonal band / Ch2", True, True, True, "INCLUDE",
     "cholinergic basal-forebrain group (Ch2); in Zaborszky", "HIGH"),
    ("Horizontal limb of diagonal band / Ch3", True, True, True, "INCLUDE",
     "cholinergic basal-forebrain group (Ch3); in Zaborszky", "HIGH"),
    ("Nucleus basalis of Meynert / Ch4", True, True, True, "INCLUDE",
     "core cholinergic magnocellular group (Ch4/NbM); in Zaborszky", "HIGH"),
    ("Substantia innominata", True, True, False, "REVIEW",
     "region containing Ch4/NbM; likely within the FS-aseg composite BF territory but a "
     "territory (not a cell group); Zaborszky maps the cell groups within it only", "MODERATE"),
    ("Ventral pallidum", True, False, False, "EXCLUDE",
     "pallidal territory; not part of the cholinergic magnocellular basal forebrain scope", "HIGH"),
    ("Nucleus accumbens", True, False, False, "EXCLUDE",
     "separate Macro96 G1 canonical (own geometry); ventral-striatal, not cholinergic BF", "HIGH"),
    ("Olfactory tubercle", True, False, False, "EXCLUDE",
     "not cholinergic magnocellular BF (Julich 'TU' grouping is atlas coverage, not membership)", "MODERATE"),
    ("Bed nucleus of stria terminalis / BNST", True, False, False, "EXCLUDE",
     "BNST frozen independent canonical (admission ADMIT); relationship requires separate "
     "ontology adjudication; no BNST->BF relation created", "HIGH"),
    ("Anterior commissure region", True, False, False, "NOT_APPLICABLE",
     "white-matter tract, not a gray-matter basal-forebrain member", "HIGH"),
    ("Septal nuclei (broad, incl. lateral septum)", True, False, False, "REVIEW",
     "only the cholinergic medial-septal (Ch1) component is in scope; broader septal nuclei separate", "MODERATE"),
    ("Diagonal band structures (region)", True, True, True, "INCLUDE",
     "Ch2 (vertical) / Ch3 (horizontal) diagonal band; in Zaborszky", "HIGH"),
]


def macro96_bf_rows():
    out = []
    for r in csv.DictReader(open(MACRO96, encoding="utf-8-sig")):
        if "Basal Forebrain" in r.get("normalized_name_en", ""):
            out.append(dict(source_row_id=r["source_row_id"], source_name_en=r["source_name_en"],
                            normalized_name_en=r["normalized_name_en"], hemisphere=r["hemisphere"],
                            structure_type=r["structure_type"], granularity_level=r["granularity_level"],
                            normalization_note=r.get("normalization_note", "")))
    return out


def bf_candidate_rows():
    out = []
    for r in csv.DictReader(open(CLASS_CSV, encoding="utf-8-sig")):
        if r.get("candidate_g1_entity_id") in (LEFT_BF, RIGHT_BF):
            out.append(dict(source_entity_id=r["source_entity_id"], source_name_en=r["source_name_en"],
                            hemisphere=r["hemisphere"], candidate_g1_entity_id=r["candidate_g1_entity_id"],
                            v3_classification=r["v3_classification"],
                            frozen_decision=r["frozen_decision"]))
    return out


def zab_asset_row():
    for r in csv.DictReader(open(ACQ_CSV, encoding="utf-8-sig")):
        if r.get("asset_id") == "BF_ZABORSZKY_CH1234":
            return dict(asset_id=r["asset_id"], structure=r.get("structure", ""),
                        download_status=r.get("download_status", ""),
                        license_status=r.get("license_status", ""),
                        local_path=r.get("local_path", ""),
                        coordinate_space=r.get("coordinate_space", ""),
                        sha256=(r.get("sha256", "") or "").strip())
    return None


def main() -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    m96 = macro96_bf_rows()
    cands = bf_candidate_rows()
    zab = zab_asset_row()
    if len(m96) != 2:
        raise SystemExit("expected 2 Macro96 Basal Forebrain rows")
    if zab is None:
        raise SystemExit("Zaborszky acquisition row missing")
    # canonical ids confirmed from classification candidate-g1 records
    ids = {c["candidate_g1_entity_id"] for c in cands}
    if not (LEFT_BF in ids and RIGHT_BF in ids):
        raise SystemExit("Basal Forebrain G1 ids not confirmed from repo")

    source_audit = dict(
        canonical_left=dict(canonical_region_id=LEFT_BF, preferred_name="Left Basal Forebrain"),
        canonical_right=dict(canonical_region_id=RIGHT_BF, preferred_name="Right Basal Forebrain"),
        macro96=dict(rows=m96, label_only=True,
                     note="Macro96 provides name only; normalization_note points to FreeSurfer aseg "
                          "composite (coarse/composite anatomical region)"),
        external_asset_manifest_label=("basal forebrain / Ch1-4/NbM family text target; NOT used as "
                                       "canonical identity"),
        source_label_only=True, source_has_formal_definition=False,
        source_definition_state="SOURCE_LABEL_ONLY_NO_FORMAL_DEFINITION",
        canonical_identity_source="Macro96 G1_MACRO + FreeSurfer aseg composite anchor",
        created_at=ts, script_version=SCRIPT_VERSION)
    with open(OUT_AUDIT, "w", encoding="utf-8") as fh:
        json.dump(source_audit, fh, ensure_ascii=False, indent=2)

    with open(OUT_XWALK, "w", newline="", encoding="utf-8-sig") as fh:
        cols = ["structure", "is_part_of_broad_anatomical_basal_forebrain",
                "is_part_of_cholinergic_basal_forebrain_system", "represented_in_zaborszky_ch1234",
                "candidate_membership_in_current_G1", "evidence", "confidence"]
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for s in CROSSWALK:
            w.writerow(dict(structure=s[0],
                            is_part_of_broad_anatomical_basal_forebrain=s[1],
                            is_part_of_cholinergic_basal_forebrain_system=s[2],
                            represented_in_zaborszky_ch1234=s[3],
                            candidate_membership_in_current_G1=s[4],
                            evidence=s[5], confidence=s[6]))

    identity = dict(
        identity_id=IDENTITY_ID,
        canonical_left=dict(canonical_region_id=LEFT_BF, preferred_name="Left Basal Forebrain"),
        canonical_right=dict(canonical_region_id=RIGHT_BF, preferred_name="Right Basal Forebrain"),
        verdict="SOURCE_LABEL_ONLY_CONSERVATIVE_OPERATIONAL_SCOPE",
        definition=("Macro96 'Basal Forebrain' is a label-only G1 macro anchored to the FreeSurfer "
                    "aseg coarse/composite 'Basal Forebrain' region. Conservative operational scope = "
                    "cholinergic magnocellular basal forebrain territory: Ch1-Ch4 / NbM magnocellular "
                    "cell groups + septal/diagonal-band origins + surrounding FS-aseg basal-forebrain "
                    "territory. NOT broad ventral forebrain (NAcc / ventral pallidum / olfactory "
                    "tubercle / BNST not auto-included)."),
        distinction=dict(
            broad_anatomical_region_as_canonical=False,
            cholinergic_system_as_canonical=False,
            ch1_ch4_union_not_asserted=True,
            note=("This G1 is NOT declared equal to Ch1 u Ch2 u Ch3 u Ch4; it is a label-only "
                  "macro conservatively scoped to the cholinergic magnocellular basal-forebrain "
                  "territory of the FS-aseg composite anchor.")),
        anatomy_first_geometry_second=True,
        created_at=ts, script_version=SCRIPT_VERSION)
    with open(OUT_ID, "w", encoding="utf-8") as fh:
        json.dump(identity, fh, ensure_ascii=False, indent=2)

    scope = dict(
        contract_id=SCOPE_ID,
        canonical_identity=identity["verdict"],
        canonical_identity_id=IDENTITY_ID,
        canonical_left=dict(canonical_region_id=LEFT_BF, preferred_name="Left Basal Forebrain"),
        canonical_right=dict(canonical_region_id=RIGHT_BF, preferred_name="Right Basal Forebrain"),
        scope_verdict="BASAL_FOREBRAIN_G1_SCOPE_FROZEN",
        scope_statement=("conservative operational scope = cholinergic magnocellular basal forebrain "
                         "territory (Ch1-Ch4/NbM cell groups + diagonal band + FS-aseg BF envelope); "
                         "BNST / NAcc / ventral pallidum / olfactory tubercle kept independent; "
                         "substantia innominata territory and broad septal nuclei remain REVIEW "
                         "(documented, non-blocking)."),
        memberships=[dict(structure=s[0], decision=s[4], confidence=s[6],
                          ontology_membership_confidence=s[6],
                          geometry_coverage_confidence=("HIGH" if s[3] else "NONE/LOW"),
                          note=s[5]) for s in CROSSWALK],
        bnst=dict(decision="EXCLUDE_AND_INDEPENDENT",
                  note="RELATIONSHIP_REQUIRES_SEPARATE_ONTOLOGY_ADJUDICATION; no BNST->BF relation"),
        nacc=dict(decision="EXCLUDE", note="NACC_RELATIONSHIP_NOT_ASSUMED; separate G1 canonical"),
        created_at=ts, script_version=SCRIPT_VERSION)
    with open(OUT_SCOPE, "w", encoding="utf-8") as fh:
        json.dump(scope, fh, ensure_ascii=False, indent=2)

    zab_audit = dict(
        publication="Zaborszky et al. 2008, NeuroImage",
        doi="10.1016/j.neuroimage.2008.05.055",
        atlas_target_concept="magnocellular cell groups of the human basal forebrain (Ch1-Ch4 / NbM)",
        histological_basis="human histology combined with in-vivo MRI (stereotaxic probabilistic maps)",
        subjects="human (multiple subjects; group probabilistic)",
        probability_semantics="stereotaxic probabilistic maps (magnocellular cell-group territory)",
        mapped_structures=["Ch1 (medial septal)", "Ch2 (vertical diagonal band)", "Ch3 (horizontal diagonal band)",
                           "Ch4 (nucleus basalis of Meynert)"],
        unmapped_basal_forebrain_structures=["BNST/BST", "olfactory tubercle", "ventral pallidum",
                                             "nucleus accumbens", "terminal islands (TUTi)",
                                             "non-cholinergic septal nuclei"],
        reference_space="MNI152 (variant to verify)",
        atlas_scope_limitation=("maps the magnocellular Ch1-Ch4 cell groups only; ATLAS_COVERAGE != "
                                "CANONICAL_ONTOLOGY_SCOPE"),
        acquisition=zab,
        raw_sha256=None if not zab["sha256"] else zab["sha256"],
        created_at=ts, script_version=SCRIPT_VERSION)
    with open(OUT_ZAB, "w", encoding="utf-8") as fh:
        json.dump(zab_audit, fh, ensure_ascii=False, indent=2)

    auth = dict(
        authority_id=AUTH_ID,
        canonical_identity=identity["verdict"],
        scope=scope["scope_statement"],
        verdict="AUTHORITATIVE_OPERATIONAL_PROXY_GEOMETRY",
        value=("Zaborszky 2008 maps exactly the Ch1-Ch4 / NbM magnocellular cell groups - the "
               "cell-group core of the conservative operational (cholinergic magnocellular) "
               "Basal Forebrain G1 territory - so it is an authoritative OPERATIONAL PROXY for "
               "that territory; it is NOT a complete broad-anatomical basal-forebrain boundary "
               "(does not cover BNST / olfactory tubercle / ventral pallidum / NAcc). Any future "
               "geometry built from it must be labelled OPERATIONAL_PROXY."),
        asset_status=zab["download_status"],
        asset_license=zab["license_status"],
        raw_sha256=None if not zab["sha256"] else zab["sha256"],
        ontology_frozen=True,
        geometry_authority_scientifically_valid=True,
        asset_acquisition_blocked=(zab["download_status"] != "RAW_ASSET_VERIFIED"),
        alternative_not_fused=True,
        created_at=ts, script_version=SCRIPT_VERSION)
    with open(OUT_AUTH, "w", encoding="utf-8") as fh:
        json.dump(auth, fh, ensure_ascii=False, indent=2)

    alt = [
        dict(source="Zaborszky et al. 2008 (Ch1-Ch4/NbM magnocellular probabilistic maps)",
             concept_coverage="Ch1-Ch4 magnocellular cell groups (operational cholinergic BF)",
             human_subjects="yes", space="MNI152 (variant verify)", probability_semantics="probabilistic",
             license_access="ACCESS_RESTRICTED", local_availability="NOT_ACQUIRED"),
        dict(source="Julich-Brain v3.1 cytoarchitectonic CH_4 (NbM) L/R maps",
             concept_coverage="Ch4 / nucleus basalis of Meynert", human_subjects="yes (postmortem)",
             space="MNI152NLin2009cAsym", probability_semantics="probabilistic/statistical",
             license_access="EBRAINS/siibra", local_availability="LOCALLY_AVAILABLE"),
        dict(source="Julich-Brain v3.1 cytoarchitectonic CH_123 L/R maps",
             concept_coverage="Ch1-3 magnocellular groups", human_subjects="yes (postmortem)",
             space="MNI152NLin2009cAsym", probability_semantics="probabilistic/statistical",
             license_access="EBRAINS/siibra", local_availability="LOCALLY_AVAILABLE"),
        dict(source="Julich-Brain v3.1 TU / TUTi / BST / sublenticular basal-forebrain maps",
             concept_coverage="associated basal-forebrain cyto elements (not cholinergic Ch1-4 scope)",
             human_subjects="yes (postmortem)", space="MNI152NLin2009cAsym",
             probability_semantics="probabilistic/statistical", license_access="EBRAINS/siibra",
             local_availability="LOCALLY_AVAILABLE"),
        dict(source="NbM-only / Anatomy-Toolbox basal forebrain maps",
             concept_coverage="NbM (Ch4) only - cannot support whole BF alone",
             human_subjects="yes", space="unknown", probability_semantics="unknown",
             license_access="unknown", local_availability="NOT_PRESENT"),
    ]
    with open(OUT_ALT, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(alt[0].keys()))
        w.writeheader()
        for r in alt:
            w.writerow(r)

    with open(OUT_HIST, "w", newline="", encoding="utf-8-sig") as fh:
        cols = ["source_entity_id", "source_name_en", "hemisphere", "candidate_g1_entity_id",
                "v3_classification", "frozen_decision", "compatibility_note"]
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for c in sorted(cands, key=lambda x: x["source_entity_id"]):
            w.writerow(dict(source_entity_id=c["source_entity_id"],
                            source_name_en=c["source_name_en"], hemisphere=c["hemisphere"],
                            candidate_g1_entity_id=c["candidate_g1_entity_id"],
                            v3_classification=c["v3_classification"],
                            frozen_decision=c["frozen_decision"],
                            compatibility_note=(
                                "candidate-layer LIKELY/CONFLICT only (not VERIFIED). Ch123/Ch4 "
                                "candidates are consistent with the cholinergic cell-group scope; "
                                "BST candidate would require a broad-BF scope - kept separate "
                                "(BNST independent); no canonical frozen conflict")))

    md = [
        "# Phase1.7 V3 - Basal Forebrain G1 canonical scope + geometry authority adjudication", "",
        f"Canonical: Left Basal Forebrain {LEFT_BF} / Right Basal Forebrain {RIGHT_BF} (G1_MACRO).",
        f"Identity: {identity['verdict']} - label-only Macro96 (FS aseg composite anchor); "
        "conservative operational scope = cholinergic magnocellular basal-forebrain territory; "
        "not broad ventral forebrain; not declared equal to Ch1 u Ch2 u Ch3 u Ch4.",
        f"Scope: {scope['scope_verdict']} (INCLUDE Ch1-Ch4/NbM + diagonal band; EXCLUDE NAcc / "
        "ventral pallidum / olfactory tubercle / BNST / anterior commissure; REVIEW substantia "
        "innominata + broad septal nuclei).",
        "BNST: EXCLUDE_AND_INDEPENDENT (no BNST->BF relation). NAcc: EXCLUDE "
        "(NACC_RELATIONSHIP_NOT_ASSUMED).",
        f"Geometry authority: {auth['verdict']} (Zaborszky 2008 Ch1-Ch4/NbM magnocellular cell groups "
        "= authoritative OPERATIONAL PROXY for the cholinergic magnocellular G1 territory; not a "
        "complete broad-anatomy boundary).",
        f"Asset: Zaborszky BF_ZABORSZKY_CH1234 status {zab['download_status']} / "
        f"{zab['license_status']}; raw_sha256={'null (NOT_ACQUIRED - not fabricated)' if not zab['sha256'] else zab['sha256']}.",
        "Alternative (locally available, NOT fused): Julich-Brain v3.1 cyto CH_123 / CH_4 / TU / "
        "TUTi / BST maps.",
        "Historical mapping: Ch123/Ch4/BST candidate rows under Basal Forebrain are LIKELY + "
        "CONFLICT_REVIEW (candidate layer, none VERIFIED) - consistency check only; no canonical "
        "frozen conflict; BNST relation left to separate adjudication.",
        "Guards: no geometry / NIfTI / transform / DB / reclassification / promotion; BNST frozen "
        "chain byte-identical; Thalamus/Amygdala/Hippocampus untouched; no multi-atlas fusion.", ""]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    print("identity:", identity["verdict"])
    print("scope:", scope["scope_verdict"])
    print("authority:", auth["verdict"])
    print("asset:", zab["download_status"], "raw_sha:", zab["sha256"] or "null")
    print("julich BF cyto maps locally available (not fused)")
    print("wrote 9 artifacts")


if __name__ == "__main__":
    main()
