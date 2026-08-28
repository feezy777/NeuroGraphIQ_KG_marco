# Gate 7A — Connection Tables（连接表）

本轮状态: **仅设计文档**

---

## 1. connections（canonical reified Connection）

| 字段 | 说明 |
|---|---|
| connection_pk | 内部主键 |
| connection_id | NGIQ-CON-… |
| name_en / name_zh | 名称 |
| connection_class | structural_connection / projection / functional_connectivity / effective_connectivity |
| directionality | directed / reciprocal / non_directional / direction_unknown |
| source_region_id / target_region_id | 源/目标（仅 directed / reciprocal 时必填） |
| laterality_relation | 侧别关系 |
| derivation_type | reported / inferred |
| canonical_status | canonical 状态 |
| summary_en / summary_zh | 摘要 |
| evidence_count / publication_count / observation_count | 派生统计（DERIVED，非 truth） |
| confidence_summary | 置信度摘要 |
| first_reported_year / latest_evidence_year | 年份（DERIVED） |
| created_at / updated_at | 时间戳 |
| remark | 备注 |

> 遵守 Gate 6：FunctionalConnectivity 不能伪造 source/target。

## 2. connection_endpoints（端点）

| 字段 | 说明 |
|---|---|
| endpoint_pk | 内部主键 |
| endpoint_id | NGIQ-EP-… |
| connection_id | 指向 connections |
| brain_region_id | 指向 brain_regions |
| endpoint_role | endpoint / source / target |
| display_order | 顺序 |
| remark | 备注 |

> 用于 FunctionalConnectivity 与 direction_unknown StructuralConnection（endpoint_role=endpoint）。source/target 若已由 connections 主表明确表示，则**不再**为 directed 连接创建 endpoint rows，避免两套人工维护 truth。

## 3. connection_observations（观测层）

canonical Connection 与某研究中的具体观测分层。

| 字段 | 说明 |
|---|---|
| observation_pk | 内部主键 |
| observation_id | NGIQ-OBS-… |
| connection_id | 指向 connections |
| study_id / publication_id / evidence_id | 研究/文献/证据 |
| acquisition_modality | tracer / histology / diffusion_mri / functional_mri / electrophysiology |
| analysis_method | tractography / correlation / DCM / Granger … |
| intervention_method | lesion / TMS / DBS / optogenetics |
| condition_name_en / condition_name_zh | 条件 |
| population_description_en / population_description_zh | 人群 |
| sample_size | 样本量 |
| metric_name / metric_value / metric_unit | 指标 |
| effect_size / effect_size_type | 效应量（nullable） |
| p_value | p 值（nullable） |
| ci_lower / ci_upper | 置信区间（nullable） |
| direction_reported | 报道方向 |
| strength_reported | 报道强度 |
| source_text_original / source_text_zh | 原文/译文 |
| source_section / source_page / source_paragraph / source_sentence / source_table / source_figure | 定位 |
| metadata_json | 元数据 |
| remark | 备注 |

> p value / effect size / CI 非所有方法都有，均 nullable。
