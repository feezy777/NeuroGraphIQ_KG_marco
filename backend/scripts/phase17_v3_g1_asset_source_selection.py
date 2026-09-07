"""Phase1.7 V3 - G1 gold-standard source selection (CORRECTED metadata; READ-ONLY).

Fact corrections applied (per advisor review):
  * Amygdala group probability atlas source FOUND (FreeSurfer SubfieldAtlasesICBMspace:
    hippocampal subfields + amygdala nuclei, MNI-ICBM 152 2009c symmetric) -> PENDING_EXTERNAL.
  * Thalamus / Hippocampus confirmed as FOUND / PENDING_EXTERNAL (2009c symmetric).
  * No EXACT voxel-grid claim before real header inspection -> RESAMPLING_REQUIRED=TRUE, exact=FALSE/UNKNOWN.
  * Basal Forebrain: Zaborszky 2008 (NeuroImage 42(3):1127-1141, DOI 10.1016/j.neuroimage.2008.05.055)
    -> FOUND / PENDING_EXTERNAL, license/download TO_VERIFY; used by JuBrain/Anatomy Toolbox.
  * BST stays SEPARATE (no matched authoritative group geometry).
  * Nucleus Accumbens: STANDARD_GROUP_GEOMETRY_NOT_CONFIRMED (segmentation model != group atlas).
"""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
OUTM = D16 / "phase17_v3_external_g1_asset_manifest.csv"
OUTS = D16 / "phase17_v3_external_g1_asset_summary.json"
OUTD = D16 / "phase17_v3_external_g1_asset_diagnostics.md"
OUTC = D16 / "phase17_v3_cortical_geometry_source_comparison.csv"
OUTSC = D16 / "phase17_v3_subcortical_geometry_source_comparison.csv"
OUTB = D16 / "phase17_v3_basal_forebrain_asset_audit.md"

BASE = dict(asset_id="", supported_g1="", atlas_name="", atlas_version="", source_org="",
            official_source="", publication="", doi="", species="human", geometry_type="",
            surface_or_volume="", probabilistic_or_discrete="", coordinate_space="",
            template="", resolution="", original_filename="", local_raw_path="", shape="",
            voxel_spacing="", affine_summary="", orientation="", file_size="", checksum="",
            license="", redistribution_status="", asset_role="", native_or_derived="",
            subject_specific_or_group="", independent_from_g3_g1_mapping="",
            independent_gold_standard_candidate="", registration_required="",
            resampling_required="", scientific_risk="", notes="", acquisition_status="",
            exact_voxel_grid_match="")


def A(**kw):
    d = dict(BASE)
    d.update(kw)
    return d


ASSETS = [
    # ---------------- locally present authoritative raw ----------------
    A(asset_id="JULICH_V31_PM", supported_g1="cortex+subcortex (G4 source)",
      atlas_name="Julich-Brain", atlas_version="v3.1.0", source_org="FZ Jülich / HBP",
      official_source="https://julich-brain-atlas.de", publication="Amunts et al. 2020",
      doi="10.1126/science.abb4588", geometry_type="probability volume",
      surface_or_volume="volume", probabilistic_or_discrete="probabilistic",
      coordinate_space="MNI152NLin2009cAsym", template="ICBM152 2009c Asym", resolution="1mm",
      original_filename="*_L/R.nii.gz (414)", local_raw_path="data/atlases/julich/v3.1/spatial_raw/probability_maps",
      shape="193x229x193", voxel_spacing="1x1x1", affine_summary="origin -96 (LPS)", orientation="RAS",
      license="CC BY 4.0", redistribution_status="allowed", asset_role="G4 source geometry",
      native_or_derived="native", subject_specific_or_group="group",
      independent_from_g3_g1_mapping="TRUE", independent_gold_standard_candidate="FALSE(G4 source)",
      registration_required="NO", resampling_required="NO", scientific_risk="none",
      notes="EXACT grid with 2009cAsym T1", acquisition_status="LOCAL_PRESENT",
      exact_voxel_grid_match="TRUE(verified header)"),
    A(asset_id="BN_2009C_TRANSFORMED_PM", supported_g1="G3 bridge",
      atlas_name="Brainnetome (resampled)", atlas_version="BNA246->2009c", source_org="CAS/ION",
      official_source="http://atlas.brainnetome.org", publication="Fan et al. 2016",
      doi="10.1093/cercor/bhw157", geometry_type="probability volume",
      surface_or_volume="volume", probabilistic_or_discrete="probabilistic",
      coordinate_space="MNI152NLin2009cAsym", resolution="1mm",
      local_raw_path="data/atlases/brainnetome/bna246/transformed_to_julich2009c/probability_maps",
      shape="193x229x193", license="academic", redistribution_status="local",
      asset_role="G3 bridge", native_or_derived="derived", subject_specific_or_group="group",
      independent_from_g3_g1_mapping="TRUE", independent_gold_standard_candidate="FALSE",
      registration_required="NO", resampling_required="NO",
      notes="EXACT with Julich 2009c; resampled via TemplateFlow h5",
      acquisition_status="LOCAL_PRESENT", exact_voxel_grid_match="TRUE(verified header)"),
    A(asset_id="FS_DK_SURFACE", supported_g1="cortical G1",
      atlas_name="FreeSurfer Desikan-Killiany", atlas_version="fsaverage", source_org="Martinos/FreeSurfer",
      official_source="surfer.nmr.mgh.harvard.edu", publication="Desikan et al. 2006",
      doi="10.1016/j.neuroimage.2006.01.021", geometry_type="surface annotation/label",
      surface_or_volume="surface", probabilistic_or_discrete="discrete",
      coordinate_space="fsaverage", local_raw_path="data/atlases/freesurfer/fsaverage/label",
      license="FreeSurfer terms", asset_role="cortical G1 surface geometry",
      native_or_derived="native", subject_specific_or_group="group template",
      independent_from_g3_g1_mapping="TRUE", independent_gold_standard_candidate="YES(as surface)",
      registration_required="YES(surf2vol)", resampling_required="YES",
      scientific_risk="surface vs Julich volume",
      notes="AUTHORITATIVE_NATIVE cortical G1 (surface)", acquisition_status="LOCAL_PRESENT",
      exact_voxel_grid_match="n/a(surface)"),
    A(asset_id="TPL_2009C_T1", supported_g1="space anchor",
      atlas_name="TemplateFlow MNI152NLin2009cAsym", atlas_version="res-01", source_org="TemplateFlow",
      publication="Esteban et al. 2019", doi="10.1038/s41592-019-0511-7",
      geometry_type="T1 template", surface_or_volume="volume",
      coordinate_space="MNI152NLin2009cAsym", resolution="1mm",
      local_raw_path="data/atlases/templateflow_ref", shape="193x229x193",
      license="CC0", asset_role="space anchor", native_or_derived="native",
      subject_specific_or_group="group", independent_from_g3_g1_mapping="TRUE",
      registration_required="NO", resampling_required="NO",
      acquisition_status="LOCAL_PRESENT", exact_voxel_grid_match="TRUE(verified header)"),
    # ---------------- external authoritative probability atlases (PENDING) ----------------
    A(asset_id="FS_SUBFIELD_HIPPO", supported_g1="Hippocampus",
      atlas_name="FreeSurfer hippocampal subfields (SubfieldAtlasesICBMspace)",
      atlas_version="ICBM 2009c symmetric", source_org="Martinos/FreeSurfer",
      official_source="surfer.nmr.mgh.harvard.edu", publication="Iglesias et al. 2015 (subfields)",
      doi="10.1016/j.neuroimage.2015.03.066", geometry_type="group probabilistic atlas",
      surface_or_volume="volume", probabilistic_or_discrete="probabilistic",
      coordinate_space="MNI-ICBM 152 2009c symmetric", template="2009c symmetric",
      resolution="1mm", original_filename="(FreeSurfer dist: hippo subfields)",
      local_raw_path="", license="FreeSurfer terms", redistribution_status="see terms",
      asset_role="Hippocampus G1 probability", native_or_derived="native",
      subject_specific_or_group="group standard", independent_from_g3_g1_mapping="TRUE",
      independent_gold_standard_candidate="YES(hippocampus proper/formation per ontology; no subiculum merge this round)",
      registration_required="TEMPLATE_VARIANT_CHECK(sym vs Asym)",
      resampling_required="TRUE", scientific_risk="same world coords but voxel grid UNKNOWN until read",
      notes="probability maps & template same world coordinates, NOT guaranteed same voxel grid",
      acquisition_status="PENDING_EXTERNAL", exact_voxel_grid_match="FALSE/UNKNOWN(not inspected)"),
    A(asset_id="FS_AMYG_NUCLEI", supported_g1="Amygdala",
      atlas_name="FreeSurfer nuclei of the amygdala (SubfieldAtlasesICBMspace)",
      atlas_version="ICBM 2009c symmetric", source_org="Martinos/FreeSurfer",
      official_source="surfer.nmr.mgh.harvard.edu",
      publication="Saygin et al. 2017 (amygdala nuclei)",
      doi="10.1038/s41593-017-0017-1", geometry_type="group probabilistic atlas",
      surface_or_volume="volume", probabilistic_or_discrete="probabilistic",
      coordinate_space="MNI-ICBM 152 2009c symmetric", template="2009c symmetric",
      resolution="1mm", original_filename="(FreeSurfer dist: amygdala nuclei)",
      local_raw_path="", license="FreeSurfer terms", redistribution_status="see terms",
      asset_role="Amygdala G1 probability", native_or_derived="native",
      subject_specific_or_group="group standard", independent_from_g3_g1_mapping="TRUE",
      independent_gold_standard_candidate="YES(amygdala nuclei)",
      registration_required="TEMPLATE_VARIANT_CHECK(sym vs Asym)",
      resampling_required="TRUE", scientific_risk="same world coords but voxel grid UNKNOWN until read",
      notes="probability maps & template same world coordinates, NOT guaranteed same voxel grid",
      acquisition_status="PENDING_EXTERNAL", exact_voxel_grid_match="FALSE/UNKNOWN(not inspected)"),
    A(asset_id="FS_THAL_ICBM", supported_g1="Thalamus",
      atlas_name="FreeSurfer/Iglesias thalamic nuclei", atlas_version="ICBM 2009c symmetric",
      source_org="Martinos/FreeSurfer", official_source="surfer.nmr.mgh.harvard.edu",
      publication="Iglesias et al. 2018", doi="10.1016/j.neuroimage.2018.06.012",
      geometry_type="group probabilistic atlas", surface_or_volume="volume",
      probabilistic_or_discrete="probabilistic",
      coordinate_space="MNI-ICBM 152 2009c symmetric", template="2009c symmetric",
      resolution="1mm", original_filename="(FreeSurfer dist: thal nuclei)",
      local_raw_path="", license="FreeSurfer terms", redistribution_status="see terms",
      asset_role="Thalamus G1 probability", native_or_derived="native",
      subject_specific_or_group="group standard", independent_from_g3_g1_mapping="TRUE",
      independent_gold_standard_candidate="YES(thal nuclei)",
      registration_required="TEMPLATE_VARIANT_CHECK(sym vs Asym)", resampling_required="TRUE",
      scientific_risk="grid UNKNOWN until real file header read",
      acquisition_status="PENDING_EXTERNAL", exact_voxel_grid_match="FALSE/UNKNOWN"),
    A(asset_id="BF_ZABORSZKY_CH1234", supported_g1="Basal Forebrain (Ch1-3, Ch4, NbM)",
      atlas_name="Zaborszky et al. human postmortem stereotaxic probabilistic maps (Ch1-4/NbM; JuBrain/AnatomyToolbox)",
      atlas_version="2008", source_org="Zaborszky et al.", official_source="JuBrain/Anatomy Toolbox",
      publication="Zaborszky et al. 2008, NeuroImage 42(3):1127-1141",
      doi="10.1016/j.neuroimage.2008.05.055", geometry_type="group probabilistic atlas",
      surface_or_volume="volume", probabilistic_or_discrete="probabilistic",
      coordinate_space="MNI152 (2009c variant to verify)", template="MNI152",
      resolution="1mm", original_filename="(Ch1-4/NbM probability maps)", local_raw_path="",
      license="TO_VERIFY", redistribution_status="TO_VERIFY",
      asset_role="Basal Forebrain G1 probability", native_or_derived="native",
      subject_specific_or_group="group standard", independent_from_g3_g1_mapping="TRUE",
      independent_gold_standard_candidate="YES(Ch/NbM)",
      registration_required="TEMPLATE_VARIANT_CHECK", resampling_required="TRUE",
      scientific_risk="license/download source to verify",
      acquisition_status="PENDING_EXTERNAL", exact_voxel_grid_match="FALSE/UNKNOWN"),
    # ---------------- subject segmentation model (secondary only) ----------------
    A(asset_id="FS_ASEG_SUBJECT", supported_g1="Accumbens/Amygdala/Hippocampus/Thalamus/GPe",
      atlas_name="FreeSurfer aseg (subject segmentation)", atlas_version="FS aseg",
      source_org="Martinos/FreeSurfer", official_source="surfer.nmr.mgh.harvard.edu",
      publication="Fischl et al. 2002", doi="10.1016/S0896-6273(02)00569-X",
      geometry_type="subject segmentation volume", surface_or_volume="volume",
      probabilistic_or_discrete="discrete", coordinate_space="subject native/Talairach",
      template="subject", local_raw_path="", license="FreeSurfer terms",
      asset_role="secondary subject validation only", native_or_derived="native",
      subject_specific_or_group="SUBJECT_SPECIFIC", independent_from_g3_g1_mapping="TRUE",
      independent_gold_standard_candidate="NO(subject-specific)",
      registration_required="YES(to group)", resampling_required="YES",
      scientific_risk="segmentation model/output is NOT a group atlas",
      acquisition_status="SUBJECT_SPECIFIC_ONLY", exact_voxel_grid_match="n/a"),
    # ---------------- no acceptable source ----------------
    A(asset_id="BF_BST", supported_g1="Basal Forebrain BST",
      atlas_name="Bed nucleus of stria terminalis - no matched authoritative group geometry",
      atlas_version="", source_org="", official_source="", publication="", doi="",
      geometry_type="n/a", coordinate_space="unknown", local_raw_path="",
      independent_gold_standard_candidate="FALSE",
      scientific_risk="kept separate; not merged into Ch atlas",
      acquisition_status="NO_ACCEPTABLE_SOURCE", exact_voxel_grid_match="n/a"),
    A(asset_id="NAcc_GROUP", supported_g1="Nucleus Accumbens",
      atlas_name="group probabilistic accumbens - not confirmed",
      atlas_version="", source_org="", official_source="", publication="", doi="",
      geometry_type="n/a", coordinate_space="unknown", local_raw_path="",
      independent_gold_standard_candidate="FALSE(no group atlas)",
      scientific_risk="segmentation model only; do not force as gold standard",
      acquisition_status="STANDARD_GROUP_GEOMETRY_NOT_CONFIRMED", exact_voxel_grid_match="n/a"),
]

COLUMNS = list(BASE.keys())


def main():
    with open(OUTM, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for a in ASSETS:
            w.writerow(a)
    import json
    status = Counter(a["acquisition_status"] for a in ASSETS)
    found = [a["asset_id"] for a in ASSETS if a["acquisition_status"] in
             ("PENDING_EXTERNAL", "LOCAL_PRESENT") and "PROBABILITY_ATLAS" in a.get("geometry_type", "") or
             a["acquisition_status"] == "PENDING_EXTERNAL"]
    summary = dict(assets=len(ASSETS), status=dict(status),
                   source_found_pending=[a["asset_id"] for a in ASSETS
                                         if a["acquisition_status"] == "PENDING_EXTERNAL"],
                   local_present=[a["asset_id"] for a in ASSETS
                                  if a["acquisition_status"] == "LOCAL_PRESENT"],
                   no_acceptable=[a["asset_id"] for a in ASSETS
                                  if a["acquisition_status"] in ("NO_ACCEPTABLE_SOURCE",
                                                                 "STANDARD_GROUP_GEOMETRY_NOT_CONFIRMED")],
                   note="no downloads; corrected Amygdala/BF statuses; no exact-voxel claim before header read")
    with open(OUTS, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    sub = [
        dict(structure="Thalamus", status="AUTHORITATIVE_PROBABILITY_ATLAS_SOURCE_FOUND",
             acquisition="PENDING_EXTERNAL", space="MNI-ICBM 152 2009c symmetric",
             grid="FALSE/UNKNOWN until header", source="FS/Iglesias thal nuclei"),
        dict(structure="Hippocampus", status="AUTHORITATIVE_PROBABILITY_ATLAS_SOURCE_FOUND",
             acquisition="PENDING_EXTERNAL", space="MNI-ICBM 152 2009c symmetric",
             grid="FALSE/UNKNOWN until header",
             source="FS/Iglesias subfields; construction must follow hippocampus proper vs formation ontology (no subiculum merge this round)"),
        dict(structure="Amygdala", status="AUTHORITATIVE_PROBABILITY_ATLAS_SOURCE_FOUND",
             acquisition="PENDING_EXTERNAL", space="MNI-ICBM 152 2009c symmetric",
             grid="FALSE/UNKNOWN until header",
             source="FS SubfieldAtlasesICBMspace: hippocampal subfields + nuclei of amygdala"),
        dict(structure="Nucleus Accumbens", status="STANDARD_GROUP_GEOMETRY_NOT_CONFIRMED",
             acquisition="", space="n/a", grid="n/a", source="segmentation model only - not group atlas"),
        dict(structure="Basal Forebrain", status="AUTHORITATIVE_PROBABILITY_ATLAS_SOURCE_FOUND",
             acquisition="PENDING_EXTERNAL", space="MNI152 (variant verify)",
             grid="FALSE/UNKNOWN until header",
             source="Zaborszky 2008 (Ch1-3, Ch4; JuBrain/AnatomyToolbox); license TO_VERIFY"),
        dict(structure="BST", status="NO_MATCHED_AUTHORITATIVE_GROUP_GEOMETRY",
             acquisition="", space="", grid="", source="keep separate; not merged into Ch atlas"),
    ]
    with open(OUTSC, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(sub[0].keys()))
        w.writeheader()
        for r in sub:
            w.writerow(r)
    cort = [dict(route="A_FS_DK_surface_bridge", verdict="native DK surface present; volume gold standard needs official FS surf2vol/template bridge",
                 class_="B_AUTHORITATIVE_NATIVE_REQUIRES_BRIDGE"),
            dict(route="B_independent_MNI_volumetric_DK", verdict="no clean authoritative DK-equivalent 2009c volume locally",
                 class_="E_THIRD_PARTY_DERIVED / NO_ASSET"),
            dict(route="C_other_gyral_atlas", verdict="name alone != current G1 definition; not acceptable gold standard",
                 class_="F_SURROGATE_NOT_ACCEPTABLE")]
    with open(OUTC, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cort[0].keys()))
        w.writeheader()
        for r in cort:
            w.writerow(r)
    bf = """# Basal Forebrain asset audit (corrected)

- Authoritative probability atlas FOUND: **Zaborszky et al. 2008**, NeuroImage 42(3):1127-1141,
  DOI 10.1016/j.neuroimage.2008.05.055. Human postmortem stereotaxic probabilistic maps of
  magnocellular cell groups Ch1-3 and Ch4 (NbM). Used by JuBrain / Anatomy Toolbox.
- acquisition_status = PENDING_EXTERNAL; license_status = TO_VERIFY; download_source = TO_VERIFY.
- NO download performed this round.
- Brainnetome G3 provides NO Basal Forebrain surrogate; Accumbens/Thalamus must NOT be used as BF surrogate.
- **BST (bed nucleus of stria terminalis) kept SEPARATE**: no matched authoritative group geometry;
  not merged into the Ch atlas.
"""
    with open(OUTB, "w", encoding="utf-8") as fh:
        fh.write(bf)
    diag = ["# External G1 asset source selection (fact-corrected)", "",
            "status=" + str(dict(status)),
            "Thalamus/Hippocampus/Amygdala/Basal Forebrain -> AUTHORITATIVE_PROBABILITY_ATLAS_SOURCE_FOUND / PENDING_EXTERNAL",
            "No exact voxel-grid claim before real header read (RESAMPLING_REQUIRED).",
            "NAcc -> STANDARD_GROUP_GEOMETRY_NOT_CONFIRMED; BST -> NO_MATCHED_AUTHORITATIVE_GROUP_GEOMETRY; aseg -> SUBJECT_SPECIFIC_ONLY."]
    with open(OUTD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(diag))
    print("assets", len(ASSETS), "status", dict(status))


if __name__ == "__main__":
    main()
