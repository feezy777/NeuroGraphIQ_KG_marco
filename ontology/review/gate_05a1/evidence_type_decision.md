# Gate 5A.1 — EvidenceType 去留/表达决策

Ontology IRI（当前）: `https://neurographiq.org/ontology/macro96`
本轮状态: **仅决策文档，未修改正式 TTL**

---

## 1. 前提：Gate 4A 多轴模型冻结

Evidence 不能由单一 EvidenceType hierarchy 表达。至少具有正交轴：

- source / acquisition_modality / analysis_method / intervention_method
- evidence_directness / evidence_strength / confidence

例：Evidence E001 → acquisition_modality=functional_mri、analysis_method=DCM、source_level=primary、directness=indirect。

## 2. 四方案比较

| 方案 | 说明 | 评估 |
|---|---|---|
| A | KEEP reserved placeholder | 单一占位与多轴冲突 |
| B | **REMOVE from V1** | 单一 Class 表达不了多轴 |
| C | Controlled vocabulary | 单一词表仍解决不了正交轴 |
| D | 建立多个独立 dimension vocabularies | 与多轴模型一致 |

## 3. 推荐：B + D

- **EvidenceType → REMOVE FROM V1 formal ontology**。
- 以后按需建立（本轮**不建**）：
  - EvidenceAcquisitionModality
  - EvidenceAnalysisMethod
  - EvidenceInterventionMethod
  - EvidenceSourceLevel
  - EvidenceDirectness
  - EvidenceStrength
  或相应 Property + vocabulary。

## 4. 关键澄清：REMOVE EvidenceType ≠ Evidence 没有分类维度

Evidence 仍有多轴分类维度（modality / analysis / intervention / directness / strength / confidence），只是不再用单一 EvidenceType Class 表达。

## 5. 结论

| 项 | 决策 |
|---|---|
| EvidenceType | **REMOVE from V1** |
| Evidence | KEEP（Gate 4A 多轴语义） |
| 后续表达 | 多轴 dimension vocabularies / Properties（未来 Gate） |
| 是否重审 Gate 4A 科学语义 | 否 |
