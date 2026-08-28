# Gate 5A.1 — Future Target Hierarchy（推荐正式骨架）

Ontology IRI（当前）: `https://neurographiq.org/ontology/macro96`
本轮状态: **候选骨架，未写入正式 TTL**

---

## 1. FUTURE TARGET HIERARCHY（V1 Human Brain Ontology）

```
owl:Thing
│
├─ BrainRegion
├─ CellularNeuralStructure
├─ NeurobiologicalProcess
│
├─ Connection
│  ├─ StructuralConnection
│  │  └─ Projection
│  ├─ FunctionalConnectivity
│  └─ EffectiveConnectivity
│
├─ Circuit
│
├─ Function
│  └─ CognitiveFunction
│
├─ Neurotransmitter
├─ Receptor
├─ Gene
├─ Disease
├─ Symptom
│
├─ ResearchStudy
├─ Publication
├─ Evidence
│
├─ Atlas
├─ ExternalRegion
├─ RegionMapping
│
└─ CircuitConnectionMembership
```

## 2. V1 formal ontology 不再包含

- ConnectionType
- CircuitType
- EvidenceType
- ConnectionAssessment
- ConceptDefinition
- Governance classes（ConnectionCandidate / CircuitCandidate / EvidenceCandidate / SearchRun / ExtractionRun / ModelReview / HumanReview / InferenceRecord / ValidationRecord）→ database-first 移出 core ontology

## 3. 统计

- 顶层 Class（owl:Thing 直接子类）= 18。
- 嵌套子类 = 5（Connection 下 4 + Function 下 CognitiveFunction 1）。
- **未来正式类总数 = 23**。

## 4. 说明

- 这是 Gate 5A.1 的推荐目标，**不写入 TTL**。
- 实际写入 TTL 由后续 Gate（Gate 5B 及之后）执行，且需执行 IRI migration（macro96 → human-brain）。
- Governance 类从 core ontology 移出，但保留 design docs 与 PostgreSQL schema 规划。
