# Gate 7B-B Phase 2A — Scope & Schema

## 1. 本轮范围

一次性创建 9 张 first-class core scientific entity 表（4/32 → 13/32）。

| # | 表 | kg_entities.entity_type |
|---|---|---|
| 1 | brain_regions | brain_region |
| 2 | cellular_neural_structures | cellular_neural_structure |
| 3 | neurobiological_processes | neurobiological_process |
| 4 | functions | function |
| 5 | neurotransmitters | neurotransmitter |
| 6 | receptors | receptor |
| 7 | genes | gene |
| 8 | diseases | disease |
| 9 | symptoms | symptom |

## 2. 未创建（Phase 2B/3+）

atlases / external_regions / region_mappings / evidence / publications / research_studies / connections / circuits / brain_region_hierarchy_relations / function_hierarchy_relations / knowledge_assertions / evidence_links / 其他。

## 3. 建模：shared-PK

所有 9 张表：

```
entity_pk BIGINT PRIMARY KEY → kg_entities(entity_pk) ON DELETE RESTRICT
```

- 无第二 public ID（无 `<type>_id`）。
- 无独立 serial PK。
- 无 name_en/name_zh/entity_id/record_status/created_at/updated_at 重复 —— kg_entities 是唯一 identity/name/lifecycle truth（Gate 7A §D/§E）。

## 4. 每表字段（仅 subtype 特有）

| 表 | 字段 |
|---|---|
| brain_regions | region_category, hemisphere, granularity_level, anatomical_level, canonical_source_pk(FK→sources), species_taxon_id, parent_region_pk(自FK, DERIVED cache), hierarchy_depth, display_order, color_hex, canonical_status, remark |
| cellular_neural_structures | structure_category, canonical_status, remark |
| neurobiological_processes | process_category, canonical_status, remark |
| functions | function_category(NN), function_level, parent_function_pk(自FK, DERIVED cache), canonical_status, remark |
| neurotransmitters | chemical_formula, molecular_weight, neurotransmitter_class, remark |
| receptors | receptor_family, receptor_type, remark |
| genes | approved_symbol(NN), approved_name, locus_group, locus_type, chromosome, cytogenetic_location, gene_group, hgnc_status, remark |
| diseases | disease_category, remark |
| symptoms | symptom_category, remark |

## 5. 已从 subtype 移除的外部 ID（→ entity_xrefs，Phase 1）

- genes：hgnc_id / ncbi_gene_id / ensembl_gene_id / uniprot_id
- diseases：mondo_id / doid / mesh_id / umls_cui / icd10_code
- symptoms：hpo_id / mesh_id / umls_cui
- neurotransmitters：chebi_id / pubchem_cid
- receptors：iuphar_id / gene_symbol / hgnc_id / uniprot_id

> 依 Gate 7B-B Phase 2A 指令 §10「外部数据库 ID 不要塞 subtype」：外部 identifier truth 统一由 entity_xrefs 管理。

## 6. migration

`backend/migrations/gate7b_003_core_scientific_entities.sql`，由现有 Gate 7B runner 应用（production 与 E2E 同一文件）。
