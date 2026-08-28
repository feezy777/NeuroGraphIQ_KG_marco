# Gate 6E-A — Current Evidence Model（现状）

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. 已冻结语义

- Evidence ≠ Publication（Evidence 是具体证据单元，如论文中一段结果/一个图表/一个数据库记录）。
- Publication = 文献/载体；ResearchStudy = 研究活动。
- 链：`ResearchStudy reportedIn Publication`；`Publication providesEvidence Evidence`。

## 2. 最大缺口

现在能表达"Publication → Evidence"，但无法表达"Evidence → 具体知识（assertion / entity）"。supports/contradicts/qualifies 尚未正式建模。

## 3. 已冻结的 DB assertion 模型（Gate 7A）

- `knowledge_assertions`：subject_entity / predicate / object_entity。
- `relation_definitions`：谓词 vocabulary（representation_role=canonical/derived）。
- `assertion_evidence_links`：assertion_id / evidence_id / evidence_role（supports/contradicts/qualifies）/ evidence_strength / evidence_directness。

## 4. 已冻结的多轴 Evidence 语义（Gate 4A）

- Evidence 多轴：source / acquisition_modality / analysis_method / intervention_method / directness / strength / confidence。
- evidence_strength / evidence_directness 是 assertion-specific（同一 Evidence 对不同 Assertion 可不同）。
- model_confidence ≠ evidence_strength。

## 5. 本轮不推翻

- 不修改 reportedIn / providesEvidence。
- 不修改 Gate 7A。
- 不写 TTL。
