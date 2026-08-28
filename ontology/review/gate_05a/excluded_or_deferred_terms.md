# Gate 5A — Excluded / Deferred / Remodeled Terms（排除/暂缓/重塑术语）· 第二轮修订

Ontology IRI: `https://neurographiq.org/ontology/macro96`
本轮状态: **仅记录，未写入正式 TTL**

---

## 1. REMOVE（建议从未来正式本体移除）

| 术语 | 理由 | 去向 |
|---|---|---|
| **ConnectionAssessment** | 旧 9,120 pair systematic search 路线废弃；新路线 Fine BrainRegion → Circuit → Connection | 移除（targeted search 由 SearchRun + ConnectionCandidate + ValidationRecord 表达） |
| **ConceptDefinition** | 概念定义可用 rdfs:comment / SKOS definition / annotation 表达；无实例化需求；不因旧系统保留 | 移除（若需版本化定义审批，放治理数据库层） |

## 2. DEFER / REMODEL（表示形式未定，暂缓）

| 术语 | 理由 | 去向 |
|---|---|---|
| **EvidenceType** | Gate 4A 多轴模型优先；单一 Class 分类与多轴冲突 | Evidence Formalization Gate / Gate 5A.1 |
| **ConnectionType（OWL 表示）** | Class hierarchy vs controlled vocabulary 未决（BLOCKER） | Gate 5A.1（科学语义冻结不变） |
| **CircuitType** | 保留/删除/受控词表/子类四选一未决 | Gate 5A.1 |
| **CircuitConnectionMembership** | KEEP 概念（reification），formalization 未决 | property / semantic modeling Gate |

## 3. 其他 DEFER（子类 / 个体 / 属性，本轮不建）

| 术语 | 去向 |
|---|---|
| Network | 未来（若需） |
| SensoryFunction / MotorFunction / AffectiveFunction / AutonomicFunction | 未来 Function 扩展 |
| Neuron / Axon / Dendrite / DendriticSpine / Synapse | 未来 CellularNeuralStructure 扩展 |
| SynapticPruning / Neurogenesis / SynapticPlasticity | 未来 NeurobiologicalProcess 扩展 |
| 具体 Neurotransmitter / Receptor / Gene / Disease / Symptom individual | Individual / controlled concept Gate |
| TracerEvidence 等 EvidenceType 模态子类 | Evidence Formalization Gate |
| has_symptom / causes / increases_risk_of / associated_with | future_relation_candidates |
| DomainEntity / GovernanceEntity / 模块父类 | 后续 semantic modeling Gate |

## 4. 明确排除（Gate 2/3/4A 已裁定，维持，不得回加）

| 术语 | 理由 |
|---|---|
| AssociationConnection / Coactivation / LocalAnatomicalConnection / UncertainConnection | Gate 2A 排除 |
| LoopCircuit / FeedforwardCircuit / FeedbackCircuit / RecurrentCircuit | Gate 3 排除（topology 特征） |
| StructuralCircuit / FunctionalCircuit / NetworkCircuit | Gate 3 排除 |
| PET / GeneticMolecularEvidence | Gate 4A DEFER |

## 5. 禁止的错误父子关系

| 禁止 | 正确 |
|---|---|
| Receptor subClassOf Neurotransmitter | 并列 |
| Symptom subClassOf Disease | 并列 |
| Publication subClassOf ResearchStudy | 并列 |
| Evidence subClassOf Publication | 并列 |
| Circuit subClassOf BrainRegion | 并列 |
| Connection subClassOf Circuit | 并列 |
| NeurobiologicalProcess subClassOf CellularNeuralStructure | 并列 |
| CognitiveFunction 与 Function 并列 | Function └─ CognitiveFunction |

## 6. 裁定汇总

- **REMOVE（2）**：ConnectionAssessment、ConceptDefinition
- **DEFER / REMODEL**：EvidenceType（表示）、ConnectionType/CircuitType（表示，科学语义冻结）、CircuitConnectionMembership（formalization）
- **维持排除**：Gate 2/3/4A 已排除术语
