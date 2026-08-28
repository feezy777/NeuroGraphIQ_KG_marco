# Gate 5B — Validation Report（构建验证报告）

对 `ontology/neurographiq_macro96_v1.ttl`（文件名暂保留旧名，内容已升级）的验证结果。

---

## 1. 元数据验证

| 项 | 期望 | 实际 |
|---|---|---|
| Ontology IRI | `https://neurographiq.org/ontology/human-brain` | ✅ |
| Namespace | `https://neurographiq.org/ontology/human-brain#` | ✅ |
| prefix | `ngiq:` | ✅ |
| version | `0.5.0-gate5b` | ✅ |
| Class | 23 | ✅ |
| ObjectProperty | 0 | ✅ |
| DataProperty | 0 | ✅ |
| Individual | 0 | ✅ |
| owl:imports | 0 | ✅ |

## 2. Class 清单（23）

顶层（18）：BrainRegion、CellularNeuralStructure、NeurobiologicalProcess、Connection、Circuit、Function、Neurotransmitter、Receptor、Gene、Disease、Symptom、ResearchStudy、Publication、Evidence、Atlas、ExternalRegion、RegionMapping、CircuitConnectionMembership

嵌套（5）：StructuralConnection、Projection、FunctionalConnectivity、EffectiveConnectivity、CognitiveFunction

## 3. Connection hierarchy

```
Connection
├─ StructuralConnection
│  └─ Projection
├─ FunctionalConnectivity
└─ EffectiveConnectivity
```
✅ StructuralConnection/Projection/FunctionalConnectivity/EffectiveConnectivity 均 `rdfs:subClassOf Connection`（Projection 经 StructuralConnection）。

## 4. Function hierarchy

```
Function
└─ CognitiveFunction
```
✅ CognitiveFunction `rdfs:subClassOf Function`。

## 5. 不得存在的 Class（验证通过）

- [x] 无 ConnectionType
- [x] 无 CircuitType
- [x] 无 EvidenceType
- [x] 无 ConnectionAssessment
- [x] 无 ConceptDefinition
- [x] 无 Governance classes（ConnectionCandidate/CircuitCandidate/EvidenceCandidate/SearchRun/ExtractionRun/ModelReview/HumanReview/InferenceRecord/ValidationRecord）

## 6. 关键约束验证

- [x] 无 ObjectProperty / DataProperty / Individual / SHACL / Restriction / EquivalentClass / DisjointClass / property chain
- [x] 无 owl:imports
- [x] 无真实 BrainRegion / atlas / circuit / connection 实例数据
- [x] 每个 Class 有 en + zh label + comment（含 1–2 例）

## 7. 结论

**Human Brain Core Ontology V1（0.5.0-gate5b）构建通过，等待 Protégé 人工审查。**
