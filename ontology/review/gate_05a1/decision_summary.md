# Gate 5A.1 — Decision Summary（最终推荐，明确单一选择）

Ontology IRI（当前）: `https://neurographiq.org/ontology/macro96`
本轮状态: **仅决策文档，未修改正式 TTL**

> 本文件给出**明确单一推荐**，不写"方案 A/B 均可"。

---

## 1. 五项核心决策（+1 原则）

| # | 问题 | 推荐 | 建模方式 |
|---|---|---|---|
| 1 | ConnectionType | **REMOVE** | Connection subtype hierarchy |
| 2 | CircuitType | **REMOVE from V1** | topology 由 future properties 表达 |
| 3 | EvidenceType | **REMOVE from V1** | multi-axis model（B + D） |
| 4 | Ontology IRI | **MIGRATE** → `https://neurographiq.org/ontology/human-brain` | Gate 5B major-scope migration |
| 5 | Governance | **database-first**（不放 core ontology） | PostgreSQL application/governance schema |
| 6 | Connection canonical | **reified Connection entity** | Neo4j direct edge 仅 derived projection |

## 2. 各项最终裁决

- **ConnectionType：REMOVE；建模 = subtype model**
  `Connection └─ StructuralConnection └─ Projection / FunctionalConnectivity / EffectiveConnectivity`。
  `connection_type` DB 字段保留为 application-level serialization，映射到 `rdf:type`。
- **CircuitType：REMOVE**。Circuit topology 未来由 is_closed_loop / has_feedback / topology_type / construction_mode 等 Property 表达。
- **EvidenceType：REMOVE**。Evidence 多轴（acquisition_modality / analysis_method / intervention_method / directness / strength / confidence）由未来 dimension vocabularies / Properties 表达。
- **Ontology IRI：MIGRATE** 到 `https://neurographiq.org/ontology/human-brain`（namespace `.../human-brain#`；Ontology name = NeuroGraphIQ Human Brain Ontology）。Gate 5B 执行，风险 LOW。
- **Governance：database-first**，移出 core Human Brain Ontology；ResearchStudy/Publication/Evidence 保留在 scientific ontology；Atlas/ExternalRegion/RegionMapping 保留。
- **Connection canonical：reified entity**；Neo4j direct edge 是 derived projection，非第二份 canonical truth。

## 3. 推荐 future target hierarchy（23 类）

见 `future_target_hierarchy.md`。

## 4. 推荐从正式 ontology 删除的 Class

- ConnectionType、CircuitType、EvidenceType、ConnectionAssessment、ConceptDefinition（5 个）。
- Governance classes（ConnectionCandidate/CircuitCandidate/EvidenceCandidate/SearchRun/ExtractionRun/ModelReview/HumanReview/InferenceRecord/ValidationRecord）→ database-first 移出 core ontology（9 个）。

## 5. 推荐新增 / rename 的 Class

- CellularNeuralStructure（rename←NeuralStructure）、NeurobiologicalProcess（rename←NeuralProcess）、ResearchStudy（rename←Study）。
- CognitiveFunction、Neurotransmitter、Receptor、Gene、Disease、Symptom。

## 6. 推荐保留的 Class

- BrainRegion、Connection、Circuit、Function、Publication、Evidence、Atlas、ExternalRegion、RegionMapping、CircuitConnectionMembership。
- Connection 下的科学子类（StructuralConnection/Projection/FunctionalConnectivity/EffectiveConnectivity）语义保留、父类上移。

## 7. 下一步

- Gate 5A.1 通过 → 进入 Gate 5B（正式 TTL 写入 + IRI migration + Connection subtype 落地）。
- Gate 5A.1 通过之前：禁止建立 ObjectProperty；禁止修改 TTL。
