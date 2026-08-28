# Gate 7A — Study / Publication / Evidence Tables

本轮状态: **仅设计文档**

---

## 1. research_studies

| 字段 | 说明 |
|---|---|
| study_pk | 内部主键 |
| study_id | NGIQ-STU-… |
| name_en / name_zh | 名称 |
| study_design | 设计（cross-sectional / cohort / case-control …） |
| study_type | 类型 |
| population_description_en / population_description_zh | 人群 |
| sample_size | 样本量 |
| species_scope | 物种 |
| condition_en / condition_zh | 条件 |
| modality_summary | 模态摘要 |
| study_start_date / study_end_date | 起止 |
| description_en / description_zh | 描述 |
| remark | 备注 |

> ResearchStudy ≠ Publication。

## 2. publications（覆盖 PubMed / Europe PMC 常见 metadata）

| 字段 | 说明 |
|---|---|
| publication_pk | 内部主键 |
| publication_id | NGIQ-PUB-… |
| title_en / title_zh | 标题 |
| original_title / original_language | 原标题/语言 |
| pmid / pmcid / doi / pii | 标识 |
| journal_name / journal_abbreviation | 期刊 |
| issn / eissn | ISSN |
| volume / issue / pages | 卷期页 |
| publication_date / publication_year | 日期/年份 |
| publication_type | 类型 |
| abstract_en / abstract_zh | 摘要 |
| authors_text / authors_json | 作者 |
| affiliations_json | 机构 |
| mesh_terms_json / keywords_json | 主题词 |
| grant_info_json | 资助 |
| conflict_of_interest | 利益冲突 |
| is_open_access | 开放获取 |
| full_text_url | 全文 URL |
| citation_count | 引用数 |
| source_database | 来源库 |
| remark | 备注 |

> 不要求所有 Publication 都有 DOI/PMID（可 NULL）。

## 3. evidence（支持前端展示"证据到底是什么"）

| 字段 | 说明 |
|---|---|
| evidence_pk | 内部主键 |
| evidence_id | NGIQ-EVI-… |
| name_en / name_zh | 名称 |
| evidence_summary_en / evidence_summary_zh | 摘要 |
| publication_pk / study_pk / scientific_source_pk | 来源（均 nullable：文献/研究/科学来源 registry） |
| evidence_text_original / evidence_text_zh | 原文/译文 |
| source_section / source_page / source_paragraph / source_sentence / source_table / source_figure | 定位 |
| acquisition_modality | tracer / histology / diffusion_mri / functional_mri / electrophysiology |
| analysis_method | tractography / correlation / DCM / Granger … |
| intervention_method | lesion / TMS / DBS / optogenetics |
| methodological_quality | 方法学质量（可选，非 target-specific strength/directness） |
| sample_size | 样本量 |
| effect_size / effect_size_type / p_value / ci_lower / ci_upper | 统计量（nullable） |
| model_confidence | 模型置信度 |
| extraction_method / extractor_name / extractor_version / extraction_run_id | 抽取 provenance |
| human_review_status / reviewer / reviewed_at | 人工审核 |
| provenance_json | provenance |
| remark | 备注 |

> **strength/directness 已移到 evidence_links（target-specific）**，evidence 表不保存同义 truth。model_confidence（模型置信度）≠ evidence_strength。
>
> **ACTIVE source completeness**：record_status=ACTIVE 须 publication_pk OR scientific_source_pk 非空；study_pk 单独不足；LLM 非 scientific source。
