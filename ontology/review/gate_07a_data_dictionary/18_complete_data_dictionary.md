# Gate 7A — Complete Data Dictionary（完整数据字典）

本轮状态: **仅设计文档**

> 图例：Type 用 PostgreSQL 类型；Role=Field Role（ID=IDENTITY / SC=SCIENTIFIC / DP=DISPLAY / DR=DERIVED / PR=PROVENANCE / GV=GOVERNANCE / TC=TECHNICAL）；Display=Frontend Display（P=PRIMARY / D=DETAIL / A=ADVANCED / H=HIDDEN）。`NN`=NOT NULL。每个表均含 `remark TEXT NULL`（如未列出则统一默认）。

> **Final Correction 权威说明（优先于本文件其余内容）**：
> 1. 命名规则：`*_pk` = 内部 BIGINT 主键/FK 目标；`*_id` = public ID（`NGIQ-…`）。本文件历史列名中 FK 字段（如 source_region_id / circuit_id / brain_region_id）实施时应读作引用内部 `*_pk`，public-ID 字段用 `*_id`。详见 `23_gate_07a_freeze_candidate.md` §E。
> 2. shared-PK：first-class 实体的 `entity_pk`（kg_entities）即 subtype 表 PK，subtype 表不另生成 `*_pk`、不重复 name/definition/description。
> 3. public ID 为 8 位（`NGIQ-BR-00000001`）。
> 4. brain_region_hierarchy_relations relation_type 仅 part_of / subfield_of。
> 5. evidence_strength / evidence_directness canonical 存储在 evidence_links。
> 6. Governance 审核历史不在此 schema（仅 review_status_snapshot）。

---

## 1. kg_entities

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| pk | 内部主键 | BIGSERIAL | NN | TC | H | 内部 PK，不对外 |
| entity_id | 实体 ID | VARCHAR(32) | NN(UNIQUE) | ID | P | NGIQ-… |
| entity_type | 实体类型 | VARCHAR(48) | NN | ID | A | 受控词表 |
| name_en | 英文名 | TEXT | NN | DP | P | — |
| name_zh | 中文名 | TEXT | NULL | DP | P | — |
| abbreviation | 缩写 | VARCHAR(64) | NULL | DP | P | — |
| definition_en | 英文定义 | TEXT | NULL | DP | D | — |
| definition_zh | 中文定义 | TEXT | NULL | DP | D | — |
| description_en | 英文描述 | TEXT | NULL | DP | D | — |
| description_zh | 中文描述 | TEXT | NULL | DP | D | — |
| source_name_original | 原始来源名 | TEXT | NULL | SC | A | 不翻译 |
| source_language | 来源语言 | VARCHAR(16) | NULL | PR | A | — |
| name_en_source | 英文名来源 | VARCHAR(24) | NULL | PR | A | source/human_curated/translated_human/translated_ai/normalized/unknown |
| name_zh_source | 中文名来源 | VARCHAR(24) | NULL | PR | A | 同上 |
| translation_review_status | 翻译审核 | VARCHAR(24) | NULL | GV | A | — |
| record_status | 记录状态 | VARCHAR(16) | NN | GV | A | active/deprecated/merged/pending |
| review_status | 审核状态 | VARCHAR(24) | NULL | GV | A | — |
| version | 版本 | INT | NULL | TC | H | — |
| created_at / updated_at | 时间戳 | TIMESTAMPTZ | NN | TC | H | — |
| created_by / updated_by | 操作者 | VARCHAR(64) | NULL | PR | H | — |
| metadata_json | 元数据 | JSONB | NULL | TC | A | 不稳定字段 |
| remark | 备注 | TEXT | NULL | GV | A | 人工补充 |

## 2. entity_aliases

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| alias_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| alias_id | 别名 ID | VARCHAR(32) | NN(UNIQUE) | ID | A | NGIQ-ALIAS-… |
| entity_id | 实体 | VARCHAR(32) | NN(FK) | SC | A | → kg_entities |
| alias_text | 别名文本 | TEXT | NN | SC | D | — |
| language | 语言 | VARCHAR(8) | NULL | SC | A | — |
| alias_type | 别名类型 | VARCHAR(24) | NN | SC | A | exact/abbreviation/historical/atlas_label/previous_name/narrow/broad/related |
| source_id | 来源 | VARCHAR(32) | NULL(FK) | PR | A | → sources |
| source_record_id | 来源记录 | VARCHAR(64) | NULL | PR | A | — |
| is_preferred | 首选 | BOOLEAN | NN(def false) | SC | A | — |
| created_at | 时间戳 | TIMESTAMPTZ | NN | TC | H | — |

## 3. entity_xrefs

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| xref_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| xref_id | Xref ID | VARCHAR(32) | NN(UNIQUE) | ID | A | NGIQ-XREF-… |
| entity_id | 实体 | VARCHAR(32) | NN(FK) | SC | A | → kg_entities |
| source_database | 来源库 | VARCHAR(64) | NN | SC | A | HGNC/MONDO/ChEBI… |
| external_id | 外部 ID | VARCHAR(64) | NN | SC | A | — |
| external_uri | 外部 URI | TEXT | NULL | SC | A | — |
| match_type | 匹配类型 | VARCHAR(24) | NN | SC | A | exact/close/broader/narrower/related/unresolved |
| is_primary | 主映射 | BOOLEAN | NN(def false) | SC | A | — |
| source_version | 来源版本 | VARCHAR(32) | NULL | PR | A | — |
| retrieved_at | 抓取时间 | TIMESTAMPTZ | NULL | PR | H | — |

## 4. sources

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| source_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| source_id | 来源 ID | VARCHAR(32) | NN(UNIQUE) | ID | P | NGIQ-SRC-… |
| name_en / name_zh | 名称 | TEXT | NN | DP | P | — |
| abbreviation | 缩写 | VARCHAR(64) | NULL | DP | P | — |
| source_type | 类型 | VARCHAR(32) | NN | SC | A | atlas/database/ontology/publication_database/literature/manual/llm/import_pipeline |
| provider | 提供方 | VARCHAR(128) | NULL | SC | A | — |
| version | 版本 | VARCHAR(32) | NULL | PR | A | — |
| species_scope | 物种范围 | VARCHAR(64) | NULL | SC | A | — |
| url / api_url | 链接 | TEXT | NULL | DP | A | — |
| license | 许可证 | VARCHAR(64) | NULL | SC | A | — |
| citation_text | 引用 | TEXT | NULL | DP | A | — |
| description_en / description_zh | 描述 | TEXT | NULL | DP | D | — |
| last_checked_at | 核对时间 | TIMESTAMPTZ | NULL | PR | H | — |
| record_status | 状态 | VARCHAR(16) | NN | GV | A | — |

## 5. brain_regions

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| brain_region_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| entity_id | 实体 ID | VARCHAR(32) | NN(UNIQUE,FK) | ID | P | NGIQ-BR-… → kg_entities |
| region_category | 区域类别 | VARCHAR(32) | NULL | SC | D | 受控词表 |
| hemisphere | 半球 | VARCHAR(16) | NULL | SC | D | left/right/bilateral/midline/unspecified |
| granularity | 粒度 | VARCHAR(16) | NULL | SC | D | macro/meso/fine/unknown |
| anatomical_level | 解剖层级 | VARCHAR(32) | NULL | SC | D | — |
| canonical_source_id | 来源 | VARCHAR(32) | NULL(FK) | PR | A | → sources |
| species_taxon_id | 物种 | VARCHAR(32) | NULL | SC | A | V1=Homo sapiens |
| parent_region_pk | 父区域 | VARCHAR(32) | NULL(FK) | DR | A | hierarchy cache |
| hierarchy_depth | 层级深度 | INT | NULL | DR | A | — |
| display_order | 展示顺序 | INT | NULL | DR | A | — |
| color_hex | 颜色 | VARCHAR(9) | NULL | DP | A | — |
| canonical_status | canonical 状态 | VARCHAR(24) | NULL | GV | A | — |

## 6. brain_region_spatial_representations

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| spatial_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| spatial_id | 空间表示 ID | VARCHAR(32) | NN(UNIQUE) | ID | A | NGIQ-SPAT-… |
| brain_region_id | 脑区 | VARCHAR(32) | NN(FK) | SC | A | → brain_regions |
| atlas_id | 图谱 | VARCHAR(32) | NULL(FK) | SC | A | → atlases |
| reference_space | 参考空间 | VARCHAR(32) | NULL | SC | A | MNI152/Colin27/fsaverage/native |
| atlas_version | 版本 | VARCHAR(32) | NULL | PR | A | — |
| hemisphere | 半球 | VARCHAR(16) | NULL | SC | A | — |
| label_index | 标签索引 | INT | NULL | SC | A | — |
| map_type | 图类型 | VARCHAR(32) | NULL | SC | A | probabilistic/maximum_probability/label |
| centroid_x_mm / centroid_y_mm / centroid_z_mm | 质心 | DOUBLE PRECISION | NULL | SC | A | — |
| bbox_json | 包围盒 | JSONB | NULL | SC | A | — |
| volume_mm3 | 体积 | DOUBLE PRECISION | NULL | SC | A | — |
| voxel_count | 体素数 | INT | NULL | SC | A | — |
| resolution_json | 分辨率 | JSONB | NULL | SC | A | — |
| mask_uri / mesh_uri | 掩膜/网格 | TEXT | NULL | SC | A | — |
| color_hex | 颜色 | VARCHAR(9) | NULL | DP | A | — |
| source_id | 来源 | VARCHAR(32) | NULL(FK) | PR | A | → sources |
| metadata_json | 元数据 | JSONB | NULL | TC | A | — |

## 7. connections

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| connection_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| connection_id | 连接 ID | VARCHAR(32) | NN(UNIQUE) | ID | P | NGIQ-CON-… |
| name_en / name_zh | 名称 | TEXT | NULL | DP | P | — |
| connection_class | 连接类别 | VARCHAR(32) | NN | SC | P | structural_connection/projection/functional_connectivity/effective_connectivity |
| directionality | 方向 | VARCHAR(24) | NN | SC | P | directed/reciprocal/non_directional/direction_unknown |
| source_region_id | 源脑区 | VARCHAR(32) | NULL(FK) | SC | D | 仅 directed/reciprocal |
| target_region_id | 目标脑区 | VARCHAR(32) | NULL(FK) | SC | D | 仅 directed/reciprocal |
| laterality_relation | 侧别关系 | VARCHAR(24) | NULL | SC | A | — |
| derivation_type | 来源类型 | VARCHAR(16) | NN | PR | A | reported/inferred |
| canonical_status | canonical 状态 | VARCHAR(24) | NULL | GV | A | — |
| summary_en / summary_zh | 摘要 | TEXT | NULL | DP | D | — |
| evidence_count | 证据数 | INT | NULL | DR | A | 派生 |
| publication_count | 文献数 | INT | NULL | DR | A | 派生 |
| observation_count | 观测数 | INT | NULL | DR | A | 派生 |
| confidence_summary | 置信度摘要 | VARCHAR(64) | NULL | DR | A | — |
| first_reported_year / latest_evidence_year | 年份 | INT | NULL | DR | A | 派生 |
| created_at / updated_at | 时间戳 | TIMESTAMPTZ | NN | TC | H | — |

## 8. connection_endpoints

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| endpoint_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| endpoint_id | 端点 ID | VARCHAR(32) | NN(UNIQUE) | ID | A | NGIQ-EP-… |
| connection_id | 连接 | VARCHAR(32) | NN(FK) | SC | A | → connections |
| brain_region_id | 脑区 | VARCHAR(32) | NN(FK) | SC | A | → brain_regions |
| endpoint_role | 端点角色 | VARCHAR(16) | NN | SC | A | endpoint/source/target |
| display_order | 顺序 | INT | NULL | DP | A | — |

## 9. connection_observations

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| observation_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| observation_id | 观测 ID | VARCHAR(32) | NN(UNIQUE) | ID | A | NGIQ-OBS-… |
| connection_id | 连接 | VARCHAR(32) | NN(FK) | SC | A | → connections |
| study_id / publication_id / evidence_id | 研究/文献/证据 | VARCHAR(32) | NULL(FK) | PR | A | — |
| acquisition_modality | 采集模态 | VARCHAR(24) | NULL | SC | A | 受控词表 |
| analysis_method | 分析方式 | VARCHAR(24) | NULL | SC | A | 受控词表 |
| intervention_method | 干预方式 | VARCHAR(24) | NULL | SC | A | 受控词表 |
| condition_name_en / condition_name_zh | 条件 | TEXT | NULL | SC | A | — |
| population_description_en / population_description_zh | 人群 | TEXT | NULL | SC | A | — |
| sample_size | 样本量 | INT | NULL | SC | A | — |
| metric_name / metric_value / metric_unit | 指标 | TEXT | NULL | SC | A | — |
| effect_size / effect_size_type | 效应量 | DOUBLE / VARCHAR | NULL | SC | A | — |
| p_value | p 值 | DOUBLE PRECISION | NULL | SC | A | — |
| ci_lower / ci_upper | 置信区间 | DOUBLE PRECISION | NULL | SC | A | — |
| direction_reported | 报道方向 | VARCHAR(24) | NULL | SC | A | — |
| strength_reported | 报道强度 | VARCHAR(24) | NULL | SC | A | — |
| source_text_original / source_text_zh | 原文/译文 | TEXT | NULL | SC | A | — |
| source_section / source_page / source_paragraph / source_sentence / source_table / source_figure | 定位 | TEXT | NULL | PR | A | — |
| metadata_json | 元数据 | JSONB | NULL | TC | A | — |

## 10. circuits

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| circuit_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| circuit_id | 回路 ID | VARCHAR(32) | NN(UNIQUE) | ID | P | NGIQ-CIR-… |
| name_en / name_zh | 名称 | TEXT | NN | DP | P | — |
| abbreviation | 缩写 | VARCHAR(64) | NULL | DP | P | — |
| description_en / description_zh | 描述 | TEXT | NULL | DP | D | — |
| construction_mode | 组装方式 | VARCHAR(24) | NULL | SC | A | composed/reconstructed |
| derivation_type | 来源类型 | VARCHAR(16) | NN | PR | A | reported/inferred |
| topology_summary_en / topology_summary_zh | 拓扑摘要 | TEXT | NULL | DP | D | — |
| is_closed_loop / has_feedback / has_recurrence | 拓扑特征 | BOOLEAN | NULL | SC | A | — |
| region_count / connection_count | 成员统计 | INT | NULL | DR | A | 派生 |
| evidence_count / publication_count | 证据统计 | INT | NULL | DR | A | 派生 |
| canonical_status | canonical 状态 | VARCHAR(24) | NULL | GV | A | — |
| confidence_summary | 置信度摘要 | VARCHAR(64) | NULL | DR | A | — |
| first_reported_year / latest_evidence_year | 年份 | INT | NULL | DR | A | — |

## 11. circuit_region_memberships

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| membership_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| membership_id | 成员 ID | VARCHAR(32) | NN(UNIQUE) | ID | A | NGIQ-CRM-… |
| circuit_id | 回路 | VARCHAR(32) | NN(FK) | SC | A | → circuits |
| brain_region_id | 脑区 | VARCHAR(32) | NN(FK) | SC | A | → brain_regions |
| role_en / role_zh | 角色 | TEXT | NULL | SC | A | — |
| sequence_order | 顺序 | INT | NULL | SC | A | — |
| is_core_member | 核心成员 | BOOLEAN | NULL | SC | A | — |
| membership_confidence | 成员置信度 | DOUBLE PRECISION | NULL | SC | A | — |

## 12. circuit_connection_memberships

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| membership_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| membership_id | 成员 ID | VARCHAR(32) | NN(UNIQUE) | ID | A | NGIQ-CCM-… |
| circuit_id | 回路 | VARCHAR(32) | NN(FK) | SC | A | → circuits |
| connection_id | 连接 | VARCHAR(32) | NN(FK) | SC | A | → connections |
| step_order | 步骤顺序 | INT | NULL | SC | A | — |
| branch_group | 分支组 | VARCHAR(32) | NULL | SC | A | — |
| role_en / role_zh | 角色 | TEXT | NULL | SC | A | — |
| is_required | 必需 | BOOLEAN | NULL | SC | A | — |
| is_core_connection | 核心连接 | BOOLEAN | NULL | SC | A | — |
| membership_confidence | 成员置信度 | DOUBLE PRECISION | NULL | SC | A | — |

## 13. functions

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| function_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| function_id | 功能 ID | VARCHAR(32) | NN(UNIQUE) | ID | P | NGIQ-FUN-… |
| name_en / name_zh | 名称 | TEXT | NN | DP | P | — |
| abbreviation | 缩写 | VARCHAR(64) | NULL | DP | P | — |
| function_category | 类别 | VARCHAR(16) | NN | SC | D | general/cognitive |
| function_level | 层级 | VARCHAR(24) | NULL | SC | A | — |
| parent_function_pk | 父功能 | VARCHAR(32) | NULL(FK) | DR | A | — |
| definition_en / definition_zh | 定义 | TEXT | NULL | DP | D | — |
| description_en / description_zh | 描述 | TEXT | NULL | DP | D | — |
| canonical_status | canonical 状态 | VARCHAR(24) | NULL | GV | A | — |

## 14. cellular_neural_structures / 15. neurobiological_processes

（两者结构相同，轻量）

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| *_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| *_id | 实体 ID | VARCHAR(32) | NN(UNIQUE) | ID | P | NGIQ-CNS-… / NGIQ-NBP-… |
| name_en / name_zh | 名称 | TEXT | NN | DP | P | — |
| abbreviation | 缩写 | VARCHAR(64) | NULL | DP | P | — |
| structure_category / process_category | 类别 | VARCHAR(32) | NULL | SC | D | — |
| definition_en / definition_zh | 定义 | TEXT | NULL | DP | D | — |
| description_en / description_zh | 描述 | TEXT | NULL | DP | D | — |
| canonical_status | canonical 状态 | VARCHAR(24) | NULL | GV | A | — |

## 16. genes

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| gene_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| gene_id | 基因 ID | VARCHAR(32) | NN(UNIQUE) | ID | P | NGIQ-GEN-… |
| name_en / name_zh | 名称 | TEXT | NULL | DP | P | — |
| approved_symbol | 批准符号 | VARCHAR(32) | NN | SC | P | HGNC |
| approved_name | 批准名称 | TEXT | NULL | SC | D | — |
| hgnc_id | HGNC ID | VARCHAR(32) | NULL | SC | A | — |
| ncbi_gene_id / ensembl_gene_id / uniprot_id | 外部 ID | VARCHAR(32) | NULL | SC | A | — |
| locus_group / locus_type | 基因座 | VARCHAR(32) | NULL | SC | A | — |
| chromosome / cytogenetic_location | 定位 | VARCHAR(32) | NULL | SC | A | — |
| gene_group | 基因家族 | VARCHAR(64) | NULL | SC | A | — |
| summary_en / summary_zh | 摘要 | TEXT | NULL | DP | D | — |
| hgnc_status | 状态 | VARCHAR(24) | NULL | SC | A | — |

## 17. neurotransmitters

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| neurotransmitter_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| neurotransmitter_id | 递质 ID | VARCHAR(32) | NN(UNIQUE) | ID | P | NGIQ-NT-… |
| name_en / name_zh | 名称 | TEXT | NN | DP | P | — |
| abbreviation | 缩写 | VARCHAR(32) | NULL | DP | P | — |
| chebi_id / pubchem_cid | 化学 ID | VARCHAR(32) | NULL | SC | A | — |
| chemical_formula | 化学式 | VARCHAR(64) | NULL | SC | A | — |
| molecular_weight | 分子量 | DOUBLE PRECISION | NULL | SC | A | — |
| neurotransmitter_class | 类别 | VARCHAR(32) | NULL | SC | D | — |
| description_en / description_zh | 描述 | TEXT | NULL | DP | D | — |

## 18. receptors

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| receptor_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| receptor_id | 受体 ID | VARCHAR(32) | NN(UNIQUE) | ID | P | NGIQ-RCP-… |
| name_en / name_zh | 名称 | TEXT | NN | DP | P | — |
| abbreviation | 缩写 | VARCHAR(32) | NULL | DP | P | — |
| iuphar_id | IUPHAR ID | VARCHAR(32) | NULL | SC | A | — |
| gene_symbol / hgnc_id / uniprot_id | 关联 | VARCHAR(32) | NULL | SC | A | — |
| receptor_family / receptor_type | 家族/类型 | VARCHAR(64) | NULL | SC | D | — |
| description_en / description_zh | 描述 | TEXT | NULL | DP | D | — |

## 19. diseases

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| disease_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| disease_id | 疾病 ID | VARCHAR(32) | NN(UNIQUE) | ID | P | NGIQ-DIS-… |
| name_en / name_zh | 名称 | TEXT | NN | DP | P | — |
| abbreviation | 缩写 | VARCHAR(32) | NULL | DP | P | — |
| mondo_id / doid / mesh_id / umls_cui / icd10_code | 外部 ID | VARCHAR(32) | NULL | SC | A | — |
| disease_category | 类别 | VARCHAR(32) | NULL | SC | D | — |
| definition_en / definition_zh | 定义 | TEXT | NULL | DP | D | — |
| description_en / description_zh | 描述 | TEXT | NULL | DP | D | — |

## 20. symptoms

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| symptom_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| symptom_id | 症状 ID | VARCHAR(32) | NN(UNIQUE) | ID | P | NGIQ-SYM-… |
| name_en / name_zh | 名称 | TEXT | NN | DP | P | — |
| abbreviation | 缩写 | VARCHAR(32) | NULL | DP | P | — |
| hpo_id / mesh_id / umls_cui | 外部 ID | VARCHAR(32) | NULL | SC | A | — |
| symptom_category | 类别 | VARCHAR(32) | NULL | SC | D | — |
| definition_en / definition_zh | 定义 | TEXT | NULL | DP | D | — |
| description_en / description_zh | 描述 | TEXT | NULL | DP | D | — |

## 21. research_studies

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| study_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| study_id | 研究 ID | VARCHAR(32) | NN(UNIQUE) | ID | P | NGIQ-STU-… |
| name_en / name_zh | 名称 | TEXT | NULL | DP | P | — |
| study_design | 设计 | VARCHAR(32) | NULL | SC | A | — |
| study_type | 类型 | VARCHAR(32) | NULL | SC | A | — |
| population_description_en / population_description_zh | 人群 | TEXT | NULL | SC | D | — |
| sample_size | 样本量 | INT | NULL | SC | A | — |
| species_scope | 物种 | VARCHAR(64) | NULL | SC | A | — |
| condition_en / condition_zh | 条件 | TEXT | NULL | SC | A | — |
| modality_summary | 模态摘要 | TEXT | NULL | SC | A | — |
| study_start_date / study_end_date | 起止 | DATE | NULL | SC | A | — |
| description_en / description_zh | 描述 | TEXT | NULL | DP | D | — |

## 22. publications

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| publication_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| publication_id | 文献 ID | VARCHAR(32) | NN(UNIQUE) | ID | P | NGIQ-PUB-… |
| title_en / title_zh | 标题 | TEXT | NN | DP | P | — |
| original_title / original_language | 原标题 | TEXT | NULL | SC | A | — |
| pmid / pmcid / doi / pii | 标识 | VARCHAR(64) | NULL | SC | A | — |
| journal_name / journal_abbreviation | 期刊 | TEXT | NULL | DP | D | — |
| issn / eissn | ISSN | VARCHAR(16) | NULL | SC | A | — |
| volume / issue / pages | 卷期页 | VARCHAR(32) | NULL | DP | D | — |
| publication_date / publication_year | 日期/年份 | DATE / INT | NULL | DP | D | — |
| publication_type | 类型 | VARCHAR(32) | NULL | SC | A | — |
| abstract_en / abstract_zh | 摘要 | TEXT | NULL | DP | D | — |
| authors_text / authors_json | 作者 | TEXT/JSONB | NULL | DP | D | — |
| affiliations_json | 机构 | JSONB | NULL | SC | A | — |
| mesh_terms_json / keywords_json | 主题词 | JSONB | NULL | SC | A | — |
| grant_info_json | 资助 | JSONB | NULL | SC | A | — |
| conflict_of_interest | 利益冲突 | TEXT | NULL | SC | A | — |
| is_open_access | 开放获取 | BOOLEAN | NULL | SC | A | — |
| full_text_url | 全文 URL | TEXT | NULL | DP | A | — |
| citation_count | 引用数 | INT | NULL | DR | A | — |
| source_database | 来源库 | VARCHAR(32) | NULL | PR | A | — |

## 23. evidence

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| evidence_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| evidence_id | 证据 ID | VARCHAR(32) | NN(UNIQUE) | ID | P | NGIQ-EVI-… |
| name_en / name_zh | 名称 | TEXT | NULL | DP | P | — |
| evidence_summary_en / evidence_summary_zh | 摘要 | TEXT | NULL | DP | D | — |
| publication_id / study_id | 文献/研究 | VARCHAR(32) | NULL(FK) | PR | A | — |
| evidence_text_original / evidence_text_zh | 原文/译文 | TEXT | NULL | SC | D | — |
| source_section / source_page / source_paragraph / source_sentence / source_table / source_figure | 定位 | TEXT | NULL | PR | A | — |
| acquisition_modality | 采集模态 | VARCHAR(24) | NULL | SC | D | 受控词表 |
| analysis_method | 分析方式 | VARCHAR(24) | NULL | SC | D | 受控词表 |
| intervention_method | 干预方式 | VARCHAR(24) | NULL | SC | D | 受控词表 |
| evidence_directness | 直接性 | VARCHAR(16) | NULL | SC | D | direct/indirect |
| evidence_strength | 强度 | VARCHAR(16) | NULL | SC | D | strong/moderate/weak/unknown |
| sample_size | 样本量 | INT | NULL | SC | A | — |
| effect_size / effect_size_type / p_value / ci_lower / ci_upper | 统计量 | DOUBLE/VARCHAR | NULL | SC | A | — |
| model_confidence | 模型置信度 | DOUBLE PRECISION | NULL | SC | A | — |
| extraction_method / extractor_name / extractor_version / extraction_run_id | 抽取 provenance | TEXT | NULL | PR | A | — |
| human_review_status / reviewer / reviewed_at | 人工审核 | VARCHAR/TIMESTAMP | NULL | GV | A | — |
| provenance_json | provenance | JSONB | NULL | PR | A | — |

## 24. atlases

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| atlas_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| atlas_id | 图谱 ID | VARCHAR(32) | NN(UNIQUE) | ID | P | NGIQ-ATL-… |
| name_en / name_zh | 名称 | TEXT | NN | DP | P | — |
| abbreviation | 缩写 | VARCHAR(64) | NULL | DP | P | — |
| atlas_family | 家族 | VARCHAR(64) | NULL | SC | A | — |
| atlas_version | 版本 | VARCHAR(32) | NULL | PR | A | — |
| species | 物种 | VARCHAR(64) | NULL | SC | A | — |
| parcellation_method | 划分方法 | VARCHAR(64) | NULL | SC | A | — |
| reference_space | 参考空间 | VARCHAR(32) | NULL | SC | A | — |
| resolution_json | 分辨率 | JSONB | NULL | SC | A | — |
| map_type | 图类型 | VARCHAR(32) | NULL | SC | A | — |
| region_count | 区域数 | INT | NULL | SC | A | — |
| release_date / release_year | 发布 | DATE/INT | NULL | SC | A | — |
| publisher_or_institution | 机构 | TEXT | NULL | SC | A | — |
| source_url / download_url | 链接 | TEXT | NULL | DP | A | — |
| license | 许可证 | VARCHAR(64) | NULL | SC | A | — |
| citation_pmid / citation_doi | 引用 | TEXT | NULL | DP | A | — |
| description_en / description_zh | 描述 | TEXT | NULL | DP | D | — |

## 25. external_regions

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| external_region_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| external_region_id | 外部脑区 ID | VARCHAR(32) | NN(UNIQUE) | ID | P | NGIQ-XREG-… |
| name_en / name_zh | 名称 | TEXT | NN | DP | P | — |
| source_name_original | 原始来源名 | TEXT | NULL | SC | P | 不翻译 |
| abbreviation | 缩写 | VARCHAR(64) | NULL | DP | P | — |
| atlas_id | 图谱 | VARCHAR(32) | NN(FK) | SC | A | → atlases |
| source_region_id | 来源区域 ID | VARCHAR(64) | NULL | SC | A | — |
| label_index | 标签索引 | INT | NULL | SC | A | — |
| hemisphere | 半球 | VARCHAR(16) | NULL | SC | A | — |
| parent_external_region_id | 父外部区域 | VARCHAR(32) | NULL(FK) | DR | A | — |
| structure_path | 结构路径 | TEXT | NULL | SC | A | — |
| hierarchy_depth | 层级深度 | INT | NULL | DR | A | — |
| display_order | 展示顺序 | INT | NULL | DP | A | — |
| reference_space | 参考空间 | VARCHAR(32) | NULL | SC | A | — |
| centroid_x_mm / centroid_y_mm / centroid_z_mm | 质心 | DOUBLE PRECISION | NULL | SC | A | — |
| volume_mm3 | 体积 | DOUBLE PRECISION | NULL | SC | A | — |
| color_hex | 颜色 | VARCHAR(9) | NULL | DP | A | — |
| metadata_json | 元数据 | JSONB | NULL | TC | A | — |

## 26. region_mappings

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| mapping_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| region_mapping_id | 映射 ID | VARCHAR(32) | NN(UNIQUE) | ID | A | NGIQ-RMAP-… |
| name_en / name_zh | 名称 | TEXT | NULL | DP | A | — |
| external_region_id | 外部脑区 | VARCHAR(32) | NN(FK) | SC | A | → external_regions |
| brain_region_id | canonical 脑区 | VARCHAR(32) | NN(FK) | SC | A | → brain_regions |
| mapping_type | 映射类型 | VARCHAR(16) | NN | SC | A | exact/close/broader/narrower/overlapping/unresolved |
| mapping_method | 方法 | VARCHAR(24) | NULL | PR | A | — |
| spatial_overlap | 空间重叠 | DOUBLE PRECISION | NULL | SC | A | — |
| name_similarity / semantic_similarity / hierarchy_similarity | 相似度 | DOUBLE PRECISION | NULL | SC | A | — |
| overall_confidence | 总体置信度 | DOUBLE PRECISION | NULL | SC | A | — |
| mapping_source | 来源 | VARCHAR(24) | NULL | PR | A | — |
| review_status / reviewer / reviewed_at | 审核 | VARCHAR/TIMESTAMP | NULL | GV | A | — |
| evidence_summary_en / evidence_summary_zh | 证据摘要 | TEXT | NULL | DP | A | — |

## 27. relation_definitions

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| predicate_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| predicate_id | 谓词 ID | VARCHAR(32) | NN(UNIQUE) | ID | A | NGIQ-PRED-… |
| predicate_key | 谓词键 | VARCHAR(64) | NN(UNIQUE) | ID | A | participatesIn |
| name_en / name_zh | 名称 | TEXT | NN | DP | A | — |
| description_en / description_zh | 描述 | TEXT | NULL | DP | A | — |
| domain_class | domain | VARCHAR(64) | NULL | SC | A | — |
| range_description | range | TEXT | NULL | SC | A | — |
| is_directional | 有向 | BOOLEAN | NN | SC | A | — |
| representation_role | 角色 | VARCHAR(16) | NN | SC | A | canonical/derived |
| owl_iri | OWL IRI | TEXT | NULL | SC | A | — |
| is_active | 启用 | BOOLEAN | NN(def true) | GV | A | — |
| display_order | 展示顺序 | INT | NULL | DP | A | — |

## 28. knowledge_assertions

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| assertion_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| assertion_id | 断言 ID | VARCHAR(32) | NN(UNIQUE) | ID | A | NGIQ-AST-… |
| subject_entity_id | 主语 | VARCHAR(32) | NN(FK) | SC | A | → kg_entities |
| predicate_id | 谓词 | VARCHAR(32) | NN(FK) | SC | A | → relation_definitions |
| object_entity_id | 宾语 | VARCHAR(32) | NN(FK) | SC | A | → kg_entities |
| display_name_en / display_name_zh | 展示名 | TEXT | NULL | DP | P | — |
| derivation_type | 来源类型 | VARCHAR(16) | NN | PR | A | reported/inferred |
| assertion_status | 状态 | VARCHAR(24) | NULL | GV | A | — |
| confidence | 置信度 | DOUBLE PRECISION | NULL | SC | A | — |
| qualifiers_json | 限定词 | JSONB | NULL | SC | A | — |
| condition_en / condition_zh | 条件 | TEXT | NULL | SC | A | — |
| source_scope | 来源范围 | VARCHAR(32) | NULL | PR | A | — |
| valid_from / valid_to | 有效期 | TIMESTAMPTZ | NULL | SC | A | — |
| review_status / reviewer / reviewed_at | 审核 | VARCHAR/TIMESTAMP | NULL | GV | A | — |
| created_at / updated_at | 时间戳 | TIMESTAMPTZ | NN | TC | H | — |

## 29. evidence_links

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| link_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| link_id | 链接 ID | VARCHAR(32) | NN(UNIQUE) | ID | A | NGIQ-ELK-… |
| evidence_pk | 证据 | BIGINT | NN(FK) | SC | A | → evidence |
| assertion_pk | 断言 | BIGINT | NULL(FK) | SC | A | → knowledge_assertions（XOR） |
| entity_pk | 实体 | BIGINT | NULL(FK) | SC | A | → kg_entities（XOR） |
| evidence_role | 证据角色 | VARCHAR(16) | NN | SC | A | supports/contradicts/qualifies |
| evidence_strength | 强度 | VARCHAR(16) | NULL | SC | A | target-specific |
| evidence_directness | 直接性 | VARCHAR(16) | NULL | SC | A | target-specific |
| claim_scope | claim 范围 | VARCHAR(32) | NULL | SC | A | entity_overall/direction/connection_type/topology/membership/mapping_identity/mapping_equivalence/mapping_overlap/other（function 已移除） |
| is_primary_evidence | 主证据 | BOOLEAN | NN(def false) | SC | A | — |
| record_status | 记录状态 | VARCHAR(16) | NN | GV | A | active/deprecated/merged/pending |
| created_at / updated_at | 时间戳 | TIMESTAMPTZ | NN | TC | H | — |
| remark | 备注 | TEXT | NULL | GV | A | — |

> XOR：assertion_pk 与 entity_pk 必须且只能填一个。

---

## 30. brain_region_hierarchy_relations（Round 2 新增）

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| hierarchy_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| hierarchy_relation_id | 层级关系 ID | VARCHAR(32) | NN(UNIQUE) | ID | A | NGIQ-BRH-… |
| parent_region_pk | 上位脑区 | VARCHAR(32) | NN(FK) | SC | A | → brain_regions |
| child_region_id | 下位脑区 | VARCHAR(32) | NN(FK) | SC | A | → brain_regions |
| relation_type | 关系类型 | VARCHAR(32) | NN | SC | A | part_of/subfield_of |
| hierarchy_source | 层级来源 | VARCHAR(24) | NULL | PR | A | ontology/atlas/curated |
| is_canonical | 是否 canonical | BOOLEAN | NN(def true) | GV | A | — |
| confidence | 置信度 | DOUBLE PRECISION | NULL | SC | A | — |
| source_id | 来源 | VARCHAR(32) | NULL(FK) | PR | A | → sources |
| remark | 备注 | TEXT | NULL | GV | A | — |

## 31. function_hierarchy_relations（Round 2 新增）

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| hierarchy_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| hierarchy_relation_id | 层级关系 ID | VARCHAR(32) | NN(UNIQUE) | ID | A | NGIQ-FHR-… |
| parent_function_pk | 上位功能 | VARCHAR(32) | NN(FK) | SC | A | → functions |
| child_function_id | 下位功能 | VARCHAR(32) | NN(FK) | SC | A | → functions |
| relation_type | 关系类型 | VARCHAR(24) | NN | SC | A | subclass_of/part_of |
| hierarchy_source | 层级来源 | VARCHAR(24) | NULL | PR | A | ontology/curated |
| is_canonical | 是否 canonical | BOOLEAN | NN(def true) | GV | A | — |
| confidence | 置信度 | DOUBLE PRECISION | NULL | SC | A | — |
| source_id | 来源 | VARCHAR(32) | NULL(FK) | PR | A | → sources |
| remark | 备注 | TEXT | NULL | GV | A | — |

---

## 32. brain_region_aggregation_mappings（Phase A 新增）

| Column | 中文 | Type | Null | Role | Display | 说明 |
|---|---|---|---|---|---|---|
| mapping_pk | 内部主键 | BIGSERIAL | NN | TC | H | — |
| mapping_id | 映射 ID | VARCHAR(32) | NN(UNIQUE) | ID | A | NGIQ-BRAM-… |
| source_region_pk | 较细脑区 | BIGINT | NN(FK) | SC | A | → brain_regions（fine） |
| target_region_pk | 较粗脑区 | BIGINT | NN(FK) | SC | A | → brain_regions（coarse） |
| mapping_relation | 映射关系 | VARCHAR(32) | NN | SC | A | exact_aggregate/contained_in/dominant_overlap/partial_overlap/composite_component/approximate/manual_curated/unresolved |
| mapping_method | 映射方法 | VARCHAR(32) | NULL | PR | A | authoritative_anatomical_mapping/atlas_crosswalk/spatial_overlap/hierarchy_inference/expert_manual/multimodal_consensus/hybrid |
| source_granularity_level | 源颗粒度 | VARCHAR(32) | NULL | DR | A | DERIVED/SNAPSHOT（= source_region.granularity_level，自动复制） |
| target_granularity_level | 目标颗粒度 | VARCHAR(32) | NULL | DR | A | DERIVED/SNAPSHOT（= target_region.granularity_level，自动复制） |
| source_coverage_ratio | 源覆盖比例 | DOUBLE PRECISION | NULL | SC | A | nullable |
| target_coverage_ratio | 目标覆盖比例 | DOUBLE PRECISION | NULL | SC | A | nullable |
| spatial_overlap_ratio | 空间重叠比例 | DOUBLE PRECISION | NULL | SC | A | nullable |
| mapping_confidence | 映射置信度 | DOUBLE PRECISION | NULL | SC | A | — |
| rollup_eligible | 可 roll-up | BOOLEAN | NN(def false) | SC | A | 仅 TRUE 进入 roll-up |
| is_primary_rollup | 主 roll-up | BOOLEAN | NN(def false) | SC | A | — |
| scientific_source_pk | 科学来源 | BIGINT | NULL(FK) | PR | A | → sources |
| provenance_json | provenance | JSONB | NULL | PR | A | — |
| record_status | 记录状态 | VARCHAR(16) | NN | GV | A | — |
| remark | 备注 | TEXT | NULL | GV | A | — |
