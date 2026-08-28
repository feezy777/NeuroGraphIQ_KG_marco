# Gate 5A — Proposed Class Hierarchy（修订后推荐模块结构）· 第二轮修订

Ontology IRI: `https://neurographiq.org/ontology/macro96`
本轮状态: **conceptual module view，未写入正式 TTL，不建模块父类**

> 以下为**概念模块视图**，不是正式 OWL hierarchy。**不得**把 A–E 做成 `NeuroscienceDomain` / `EvidenceDomain` / `GovernanceDomain` 等正式 Class。正式 OWL hierarchy 在本 Gate 仍保持轻量。

---

## A. Neuroscience Domain（神经科学领域本体）

```
BrainRegion
CellularNeuralStructure
NeurobiologicalProcess
Connection
ConnectionType              [当前正式模型临时保留；语义表示未决 → Gate 5A.1]
  ├─ StructuralConnection   [Gate 2 hierarchy 临时保留，表示未决]
  │  └─ Projection
  ├─ FunctionalConnectivity
  └─ EffectiveConnectivity
Circuit
CircuitType                 [reserved / 未决 → Gate 5A.1]
Function
  └─ CognitiveFunction
Neurotransmitter
Receptor
Gene
Disease
Symptom
```

## B. Scientific Evidence / Provenance

```
ResearchStudy
Publication
Evidence
EvidenceType                [DEFER / REMODEL]
```

## C. Atlas / Integration

```
Atlas
ExternalRegion
RegionMapping
```

## D. Modeling / Reification

```
CircuitConnectionMembership  [KEEP 概念；formalization 后续]
```

## E. Knowledge Production / Governance

```
ConnectionCandidate
CircuitCandidate
EvidenceCandidate
SearchRun
ExtractionRun
ModelReview
HumanReview
InferenceRecord
ValidationRecord
ConceptDefinition           [重新审查 → 建议 REMOVE]
ConnectionAssessment        [REMOVE]
```

---

## 明确不进入 hierarchy 的错误关系（禁止）

- Receptor ⊄ Neurotransmitter
- Symptom ⊄ Disease
- Publication ⊄ ResearchStudy
- Evidence ⊄ Publication
- Circuit ⊄ BrainRegion
- Connection ⊄ Circuit
- CognitiveFunction 与 Function 并列无关系（必须 Function └─ CognitiveFunction）
- NeurobiologicalProcess ⊄ CellularNeuralStructure
- CellularNeuralStructure 与 BrainRegion 混为一类（必须区分宏观/中观 vs 细胞/亚细胞）

---

## 与当前 TTL 的差异（仅记录，不写入）

| 项 | 当前 TTL | 推荐（Round 2） |
|---|---|---|
| NeuralStructure / NeuralProcess | 无 | 新增 CellularNeuralStructure / NeurobiologicalProcess（顶层） |
| CognitiveFunction | 无 | 新增（Function 子类） |
| Neurotransmitter / Receptor / Gene / Disease / Symptom | 无 | 新增（顶层，扩展/轻量） |
| Study | 无 | 新增 ResearchStudy（顶层） |
| ConnectionAssessment | 顶层 | **REMOVE** |
| ConceptDefinition | 顶层 | **REMOVE**（推荐） |
| EvidenceType | 顶层 | **DEFER / REMODEL** |
| CircuitConnectionMembership | 顶层 | KEEP 概念（Modeling/Reification），formalization 后续 |
| ConnectionType 4 子类 | 顶层（冻结） | 科学语义冻结；**OWL 表示 → Gate 5A.1** |
| CircuitType | reserved | 去留/表示 → Gate 5A.1 |
