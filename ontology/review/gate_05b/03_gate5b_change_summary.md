# Gate 5B — Change Summary（Human Brain Core Ontology 正式构建变更记录）

---

## 1. Ontology Scope Migration

| 项 | 旧 | 新 |
|---|---|---|
| Ontology IRI | `https://neurographiq.org/ontology/macro96` | `https://neurographiq.org/ontology/human-brain` |
| Namespace | `https://neurographiq.org/ontology/macro96#` | `https://neurographiq.org/ontology/human-brain#` |
| Label | NeuroGraphIQ Macro96 Ontology | NeuroGraphIQ Human Brain Ontology |
| 中文 label | NeuroGraphIQ Macro96 本体 | NeuroGraphIQ 人脑知识本体 |
| versionInfo | `0.3.0-gate3b` | `0.5.0-gate5b` |
| Scope | Macro96-only | Human Brain（Homo sapiens） |

> Macro96 不删除，改为未来高层 BrainRegion mapping / aggregation layer。

## 2. REMOVE（从 core ontology 删除）

- ConnectionType
- CircuitType
- EvidenceType
- ConnectionAssessment
- ConceptDefinition

## 3. Governance moved out（移出 core ontology → PostgreSQL governance schema）

- ConnectionCandidate
- CircuitCandidate
- EvidenceCandidate
- SearchRun
- ExtractionRun
- ModelReview
- HumanReview
- InferenceRecord
- ValidationRecord

## 4. 新增 Class

- CellularNeuralStructure（原 NeuralStructure）
- NeurobiologicalProcess（原 NeuralProcess）
- CognitiveFunction
- Neurotransmitter
- Receptor
- Gene
- Disease
- Symptom
- ResearchStudy（原 Study）

## 5. Connection hierarchy 重构

| 旧 | 新 |
|---|---|
| Connection；ConnectionType ├─ StructuralConnection └─ Projection / FunctionalConnectivity / EffectiveConnectivity | Connection ├─ StructuralConnection └─ Projection / FunctionalConnectivity / EffectiveConnectivity |

- 父类从 ConnectionType 改为 Connection（subtype model，Gate 5A.1 决策）。
- Gate 2 科学语义完全保留。

## 6. Function hierarchy

- 新增 `Function └─ CognitiveFunction`。

## 7. 本轮未做（后续 Gate）

- 未新增 ObjectProperty / DataProperty / Individual / AnnotationProperty / SHACL / Restriction / owl:imports。
- 未导入真实 BrainRegion / atlas / circuit / connection 实例。
- 未修改 Governance database / API / frontend / Neo4j。
