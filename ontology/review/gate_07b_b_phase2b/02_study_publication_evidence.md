# Gate 7B-B Phase 2B — Study / Publication / Evidence

## 1. ResearchStudy ≠ Publication（保持分离）

- `research_studies` = 研究活动 / study。
- `publications` = 文献载体 / document。
- 二者是不同实体，独立 shared-PK。
- PMID / DOI 不当作 Evidence；pmid/pmcid/doi/pii 是 publication 专属检索字段（可 NULL）。

## 2. Evidence = 具体证据单元

- 不是 Publication、不是 PMID/DOI、不是 LLM 输出、不是"整篇文章默认一个 Evidence"。
- 来源三字段均 nullable：`publication_pk` / `study_pk` / `scientific_source_pk`。
- `scientific_source_pk → sources(source_pk)`（scientific source registry，**排除** GPT/DeepSeek/BioSEPBERT 等 provenance agent）。

## 3. ACTIVE Evidence source completeness（冻结 §P / 指令 §六）

触发器 `infra.assert_evidence_active_source()`（BEFORE INSERT OR UPDATE）：

```
IF record_status = 'active'
   AND publication_pk IS NULL
   AND scientific_source_pk IS NULL
THEN RAISE EXCEPTION
```

- `study_pk` 单独存在 **不满足** ACTIVE 完整性（必须 publication_pk OR scientific_source_pk）。
- PROPOSED Evidence 允许暂时缺 publication/source（保留 extraction provenance / human_review_status 等 resolution 状态）。

## 4. evidence_strength / evidence_directness 未放入 evidence

- 二者是 Evidence 与 assertion/entity target 的**关联属性**，不是 Evidence 固有全局属性。
- canonical 存储 = future EvidenceLink（Assertion/Evidence linking phase）。
- `model_confidence`（模型置信度）≠ evidence_strength，保留在 evidence。

## 5. 测试覆盖

- `test_active_evidence_no_source_rejected`（无 pub/source → 拒绝）
- `test_active_evidence_only_study_rejected`（仅 study_pk → 拒绝）
- `test_active_evidence_with_publication_allowed` / `..._with_scientific_source_allowed`
- `test_proposed_evidence_without_source_allowed`
- `test_evidence_scientific_source_fk_enforced`
