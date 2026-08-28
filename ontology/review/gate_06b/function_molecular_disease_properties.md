# Gate 6B — Function / Molecular / Disease Properties

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
version: `0.6.0-gate6b`

---

## 1. 功能关系

| Property | Domain | Range | 语义 | Role |
|---|---|---|---|---|
| participatesIn | BrainRegion | Circuit ∪ Function | 脑区参与回路/功能 | Canonical |
| hasFunction | Circuit | Function | 回路关联功能 | Canonical |

- BrainRegion→Function 用 participatesIn；Circuit→Function 用 hasFunction。

## 2. 分子关系

| Property | Domain | Range | 语义 | Role |
|---|---|---|---|---|
| modulates | Gene ∪ Neurotransmitter | BrainRegion ∪ Circuit ∪ Function | 调控 | Canonical |
| actsOn | Neurotransmitter | Receptor | 作用于 | Canonical |

## 3. 疾病关系

| Property | Domain | Range | 语义 | Role |
|---|---|---|---|---|
| increasesRiskOf | Gene | Disease | 增加风险（≠ causes） | Canonical |
| hasSymptom | Disease | Symptom | 具有症状 | Canonical |

## 4. 边界

- modulates ≠ associatedWith ≠ causes。
- increasesRiskOf ≠ causes；APOE ε4 等 variant 级留未来 GeneticVariant/Allele 模型。
- hasSymptom 表示常见/报道临床表现，非所有患者必然。
- 不扩展 pharmacology / protein / drug / molecular pathway 关系。
