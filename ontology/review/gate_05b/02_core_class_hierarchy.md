# NeuroGraphIQ Human Brain Ontology — Core Class Hierarchy（V1）

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
version: `0.5.0-gate5b`

---

```
owl:Thing
│
├─ BrainRegion
│
├─ CellularNeuralStructure
│
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

---

## 统计

- 顶层 Class（owl:Thing 直接子类）：18
- 嵌套子类：5（Connection 下 4 + Function 下 CognitiveFunction 1）
- **Class 总数：23**

## 不包含（已移出 core ontology）

- ConnectionType、CircuitType、EvidenceType、ConnectionAssessment、ConceptDefinition
- Governance 类（ConnectionCandidate、CircuitCandidate、EvidenceCandidate、SearchRun、ExtractionRun、ModelReview、HumanReview、InferenceRecord、ValidationRecord）
