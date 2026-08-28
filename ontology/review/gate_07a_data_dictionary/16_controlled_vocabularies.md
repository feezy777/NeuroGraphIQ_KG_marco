# Gate 7A — Controlled Vocabularies（受控词表）

本轮状态: **仅设计文档**

---

## 1. 全局

| 词表 | 值 |
|---|---|
| entity_type | brain_region / cellular_neural_structure / neurobiological_process / connection / circuit / function / neurotransmitter / receptor / gene / disease / symptom / research_study / publication / evidence / atlas / external_region / region_mapping / circuit_connection_membership |
| record_status | active / deprecated / merged / pending |
| review_status | pending / approved / rejected / uncertain / needs_revision |
| name source | source / human_curated / translated_human / translated_ai / normalized / unknown |
| derivation_type | reported / inferred |
| alias_type | exact / abbreviation / historical / atlas_label / previous_name / narrow / broad / related |
| match_type / mapping_type | exact / close / broader / narrower / related / overlapping / unresolved |

## 2. BrainRegion

- hemisphere：left / right / bilateral / midline / unspecified
- granularity：macro / meso / fine / unknown
- region_category：cortical_region / cortical_parcel / gyrus / sulcus_region / subcortical_region / nucleus / hippocampal_subfield / amygdalar_nucleus / thalamic_nucleus / cerebellar_region / brainstem_region / other
- hierarchy relation_type：part_of / subfield_of（overlaps / located_in → DEFER，未来 spatial relations）

## 2b. Function Hierarchy

- function hierarchy relation_type：subclass_of / part_of

## 3. Connection

- connection_class：structural_connection / projection / functional_connectivity / effective_connectivity
- directionality：directed / non_directional / direction_unknown（reciprocal = DERIVED display vocabulary，非 canonical storage 首选）
- endpoint_role：endpoint / source / target
- acquisition_modality：tracer / histology / diffusion_mri / functional_mri / electrophysiology
- analysis_method：tractography / correlation / coherence / DCM / SEM / Granger
- intervention_method：lesion / TMS / DBS / optogenetics
- evidence_directness：direct / indirect
- evidence_strength：strong / moderate / weak / unknown

## 4. Function / Disease / Symptom / Molecular

- function_category：general / cognitive
- disease_category：neurodegenerative / psychiatric / neurological / other
- symptom_category：（开放，后续细化）
- neurotransmitter_class：（开放）
- receptor_family / receptor_type：（开放，参考 IUPHAR）

## 5. Assertion / Relation

- representation_role：canonical / derived
- evidence_role：supports / contradicts / qualifies
- mapping_method：automatic / manual / hybrid
- source_type：atlas / database / ontology / publication_database / literature / manual / import_pipeline（llm 移除；LLM 属 Provenance Agent 非 scientific source）

## 6. 其他

- construction_mode：composed / reconstructed
- reference_space：MNI152 / Colin27 / fsaverage / native / other
- map_type：probabilistic / maximum_probability / label / other
- study_design：cross-sectional / cohort / case-control / longitudinal / other
- publication_type：（PubMed publication type 词表）
- locus_group / locus_type / hgnc_status：（HGNC 词表）

## 7. Granularity（G1–G4）

- granularity_level：G1_MACRO / G2_MESO_ANATOMICAL / G3_MESO_FINE / G4_MICROSTRUCTURAL_FINE
- granularity_basis：macro_anatomical / anatomical_parcellation / connectivity_parcellation / multimodal_parcellation / functional_parcellation / cytoarchitectonic / microstructural / manual_canonical / other
- connection granularity_scope：G1_MACRO / G2_MESO_ANATOMICAL / G3_MESO_FINE / G4_MICROSTRUCTURAL_FINE / CROSS_GRANULARITY / UNSPECIFIED
- circuit granularity_scope：G1_MACRO / G2_MESO_ANATOMICAL / G3_MESO_FINE / G4_MICROSTRUCTURAL_FINE / MIXED / UNSPECIFIED
- aggregation mapping_relation：exact_aggregate / contained_in / dominant_overlap / partial_overlap / composite_component / approximate / manual_curated / unresolved
- aggregation mapping_method：authoritative_anatomical_mapping / atlas_crosswalk / spatial_overlap / hierarchy_inference / expert_manual / multimodal_consensus / hybrid
- species_verification_status：verified / pending / rejected
