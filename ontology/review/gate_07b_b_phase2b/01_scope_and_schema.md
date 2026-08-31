# Gate 7B-B Phase 2B — Scope & Schema

## 1. 本轮范围

创建 5 张 Evidence & Atlas 科学实体表（13/32 → 18/32）。

| # | 表 | kg_entities.entity_type |
|---|---|---|
| 1 | research_studies | research_study |
| 2 | publications | publication |
| 3 | evidence | evidence |
| 4 | atlases | atlas |
| 5 | external_regions | external_region |

## 2. 未创建（Phase 3+）

hierarchy / spatial / aggregation / connection / circuit / mapping / assertion / evidence_links / relation_definitions 等。

## 3. 建模：shared-PK（延续 Phase 2A）

- 全部 `entity_pk BIGINT PRIMARY KEY → kg_entities(entity_pk) ON DELETE RESTRICT`。
- 复用集中守卫 `infra.assert_entity_type()`（5 个新触发器）。
- 无第二 public ID / 独立 serial PK / 重复 name/status。

## 4. 各表字段（仅 subtype 特有）

| 表 | 关键字段 |
|---|---|
| research_studies | study_design(CHECK), study_type, population_description_en/zh, sample_size, species_scope, condition_en/zh, modality_summary, study_start/end_date |
| publications | original_title/language, pmid/pmcid/doi/pii(可 NULL), journal_*, issn/eissn, volume/issue/pages, publication_date/year, publication_type, abstract_en/zh, authors_text/json, affiliations/mesh/keywords/grant json, conflict_of_interest, is_open_access, full_text_url, citation_count(DR), source_database |
| evidence | evidence_summary_en/zh, publication_pk/study_pk/scientific_source_pk(FK), evidence_text_original/zh, source_* 定位, acquisition_modality/analysis_method/intervention_method(CHECK), methodological_quality, sample_size, effect_size/type, p_value, ci_lower/upper, model_confidence, extraction_* provenance, human_review_status, reviewer, reviewed_at, provenance_json |
| atlases | atlas_family, atlas_version, species, parcellation_method, reference_space(CHECK), resolution_json, map_type(CHECK), region_count, release_date/year, publisher_or_institution, source_url/download_url, license, citation_pmid/doi |
| external_regions | atlas_pk(NN FK→atlases), source_region_id, label_index, hemisphere(CHECK), parent_external_region_pk(DERIVED cache), structure_path, hierarchy_depth, display_order, reference_space, granularity_level(G1–G4, atlas context only), granularity_basis, centroid_*, volume_mm3, color_hex, metadata_json |

## 5. 冻结边界（本轮落实）

- ResearchStudy ≠ Publication。
- PMID/DOI 是 publication 专属检索字段（保留在 publications）；其他外部 ID 仍在 entity_xrefs。
- evidence_strength / evidence_directness **未**放进 evidence（属于 future EvidenceLink target-specific context）。
- 未创建 evidence_links / knowledge_assertions / relation_definitions。
- Atlas ≠ granularity（atlases 无 granularity_level 列）。
- ExternalRegion ≠ canonical BrainRegion（无直接 FK/合并；mapping 属后续 RegionMapping phase）。

## 6. migration

`backend/migrations/gate7b_004_evidence_atlas_entities.sql`，同一文件应用于 production 与 E2E。
