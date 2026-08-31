# Gate 7B-B Phase 3B — Connection Observation

## 1. ConnectionObservation 角色

`connection_observations` = 某项 Study 中对某条 Connection 的**结构化观测结果**。

典型关系：Connection → ConnectionObservation → ResearchStudy / Evidence context。

- **不是** Connection 本身。
- **不是** Evidence 本身（Observation = structured measurement；Evidence = 支持/限定科学 claim 的 unit）。

## 2. 字段（按 CURRENT dict 18 §9）

- connection_pk（NN FK）、study_pk / publication_pk / evidence_pk（nullable FK）
- acquisition_modality / analysis_method / intervention_method（CHECK 受控）
- condition_name_en/zh、population_description_en/zh、sample_size
- metric_name / metric_value / metric_unit
- effect_size / effect_size_type、p_value、ci_lower / ci_upper
- direction_reported / strength_reported
- source_text_original / source_text_zh、source_* 定位
- metadata_json、remark

## 3. Observation ≠ Evidence（边界）

- `direction_reported` / `strength_reported` = 论文**报道**的观测值（observation measurement），**不是** `evidence_strength` / `evidence_directness`（EvidenceLink target-specific context，仍 deferred）。
- 未放入 evidence_strength / evidence_directness（测试 `test_observation_separated_from_evidence`）。
- evidence_links 本轮未创建。

## 4. Scientific reference 边界

- 观测来源只允许 research_studies / publications / evidence / sources。
- GPT / DeepSeek / BioSEPBERT 属 provenance agent，**不**作为 scientific source（sources 词表无 llm）。

## 5. 测试覆盖

- `test_observation_connection_fk`（FK 正确）
- `test_observation_invalid_connection_rejected`（非法 connection 拒绝）
- `test_observation_separated_from_evidence`（无 evidence_strength/directness 列）
