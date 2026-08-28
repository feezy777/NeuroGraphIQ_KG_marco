# Gate 6G-B — Frozen Ontology Manifest（冻结语义清单）

> 本文是 freeze 的语义权威清单；与 `03_freeze_declaration.md`（声明）配合。TTL 已冻结于 0.9.0-ontology-core-freeze，本文内容不可再改。

---

## 1. Frozen Class Manifest（23）

| Class | 中文 | Parent | 角色 |
|---|---|---|---|
| BrainRegion | 脑区 | owl:Thing | canonical 区域实体 |
| CellularNeuralStructure | 细胞与亚细胞神经结构 | owl:Thing | 细胞/亚细胞结构 |
| NeurobiologicalProcess | 神经生物学过程 | owl:Thing | 神经生物学过程 |
| Connection | 连接 | owl:Thing | reified 连接实体 |
| StructuralConnection | 结构连接 | Connection | 解剖通路 |
| Projection | 投射 | StructuralConnection | 有向轴突投射 |
| FunctionalConnectivity | 功能连接 | Connection | 统计依赖/相关 |
| EffectiveConnectivity | 有效连接 | Connection | 有向影响 |
| Circuit | 神经回路 | owl:Thing | 有组织连接单元 |
| Function | 功能 | owl:Thing | 神经生物学功能 |
| CognitiveFunction | 认知功能 | Function | 认知域功能 |
| Neurotransmitter | 神经递质 | owl:Thing | 化学信号分子 |
| Receptor | 受体 | owl:Thing | 受体蛋白 |
| Gene | 基因 | owl:Thing | 人类基因 |
| Disease | 疾病 | owl:Thing | 神经/精神疾病 |
| Symptom | 症状 | owl:Thing | 临床表现 |
| ResearchStudy | 研究 | owl:Thing | 研究活动 |
| Publication | 文献 | owl:Thing | 文献载体 |
| Evidence | 证据 | owl:Thing | 证据单元 |
| Atlas | 脑图谱 | owl:Thing | 图谱资源 |
| ExternalRegion | 外部脑区 | owl:Thing | 外部区域概念 |
| RegionMapping | 脑区映射 | owl:Thing | reified 映射实体 |
| CircuitConnectionMembership | 回路连接成员关系 | owl:Thing | reified 成员关系 |

## 2. Frozen ObjectProperty Manifest（26）

| Property | 中文 | Domain | Range | Canonical/Derived | subPropertyOf | Role |
|---|---|---|---|---|---|---|
| structurallyConnectedTo | 结构连接 | BrainRegion | BrainRegion | Derived | — | 结构通路直连投影 |
| functionallyConnectedTo | 功能连接 | BrainRegion | BrainRegion | Derived | — | 功能相关直连投影 |
| projectsTo | 投射到 | BrainRegion | BrainRegion | Derived | structurallyConnectedTo | 有向投射投影 |
| effectivelyConnectedTo | 有效连接 | BrainRegion | BrainRegion | Derived | — | 有向影响投影 |
| participatesIn | 参与 | BrainRegion | Circuit ∪ Function | Canonical | — | 参与回路/功能 |
| modulates | 调控 | Gene ∪ Neurotransmitter | BrainRegion ∪ Circuit ∪ Function | Canonical | — | 调控 |
| increasesRiskOf | 增加风险 | Gene | Disease | Canonical | — | 风险关系 |
| hasFunction | 具有功能 | Circuit | Function | Canonical | — | 回路关联功能 |
| hasSymptom | 具有症状 | Disease | Symptom | Canonical | — | 疾病症状 |
| actsOn | 作用于 | Neurotransmitter | Receptor | Canonical | — | 递质-受体 |
| hasEndpointRegion | 连接端点脑区 | Connection | BrainRegion | Canonical | — | 无方向端点 |
| hasSourceRegion | 起始脑区 | Connection | BrainRegion | Canonical | hasEndpointRegion | 已知起点 |
| hasTargetRegion | 目标脑区 | Connection | BrainRegion | Canonical | hasEndpointRegion | 已知终点 |
| includesRegion | 包含脑区 | Circuit | BrainRegion | Canonical | — | 回路成员脑区 |
| hasConnectionMembership | 具有连接成员关系 | Circuit | CircuitConnectionMembership | Canonical | — | reified 成员 |
| membershipConnection | 成员连接 | CircuitConnectionMembership | Connection | Canonical | — | reified 成员→连接 |
| hasConnection | 包含连接 | Circuit | Connection | Derived | — | 便捷投影 |
| reportedIn | 报道于 | ResearchStudy | Publication | Canonical | — | 研究→文献 |
| providesEvidence | 提供证据 | Publication | Evidence | Canonical | — | 文献→证据 |
| definedInAtlas | 定义于图谱 | ExternalRegion | Atlas | Canonical | — | 外部区域→图谱 |
| mappingSource | 映射源 | RegionMapping | ExternalRegion | Canonical | — | reified 映射源 |
| mappingTarget | 映射目标 | RegionMapping | BrainRegion | Canonical | — | reified 映射目标 |
| mapsTo | 映射到 | ExternalRegion | BrainRegion | Derived | — | 便捷投影 |
| partOf | 属于 | BrainRegion | BrainRegion | Canonical | — | 解剖层级 |
| subfieldOf | 亚区属于 | BrainRegion | BrainRegion | Canonical | partOf | 解剖亚区 |
| subFunctionOf | 下位功能 | Function | Function | Canonical | — | 功能语义层级 |

## 3. Connection Semantics Freeze

- Projection ⊑ StructuralConnection ⊑ Connection。
- directed ≠ Projection（Projection 需 source+target+axonal projection 语义）。
- DTI/tractography alone 不提供 Projection direction。
- FunctionalConnectivity ≠ StructuralConnection（统计依赖不隐含结构通路）。
- EffectiveConnectivity ≠ Projection（模型有向影响 ≠ 解剖投射）。

## 4. Circuit Semantics Freeze

- Circuit = biological/functional circuit，非 graph theory cycle。
- closed loop 非必要条件。
- "≥3 regions + ≥2 connections" 非 ontology definition。
- 随机 connection set 不自动成为 Circuit。

## 5. BrainRegion Hierarchy Freeze

- partOf：BrainRegion → BrainRegion。
- subfieldOf：BrainRegion → BrainRegion；subfieldOf ⊑ partOf。
- aggregation mapping ≠ partOf；spatial overlap ≠ partOf；RegionMapping ≠ partOf。

## 6. Function Hierarchy Freeze

- CognitiveFunction rdfs:subClassOf Function（TBox）。
- subFunctionOf：Function → Function（ABox，具体 Function concept 未来为 Individual）。
- 不得 WorkingMemory rdfs:subClassOf Memory。
- Function part_of：DEFER。

## 7. Canonical / Derived Boundary

- Canonical Connection = Connection entity + endpoint/source/target rows。
- Derived = structurallyConnectedTo / functionallyConnectedTo / projectsTo / effectivelyConnectedTo。
- Canonical Circuit membership = CircuitConnectionMembership；Derived = hasConnection。
- Canonical external mapping = RegionMapping（mappingSource/mappingTarget）；Derived = mapsTo。
- 禁止独立双写 truth。

## 8. Evidence / Assertion Boundary

- OWL：ResearchStudy / Publication / Evidence + reportedIn / providesEvidence。
- PostgreSQL：KnowledgeAssertion / evidence_links / supports / contradicts / qualifies / claim_scope / evidence_strength / evidence_directness / Inference lineage / governance。
- KnowledgeAssertion 不进入 OWL。

## 9. Spatial Boundary

- spatiallyOverlaps / adjacentTo：DB ONLY / DEFER OWL。
- locatedIn：REMOVE / DEFER。
- SpatialRepresentation：V1 DB layer（不新增 OWL Class）。
- future spatial relation 倾向 SpatialRepresentation → SpatialRepresentation。

## 10. Atlas / Mapping Boundary

- Atlas / ExternalRegion / RegionMapping；definedInAtlas / mappingSource / mappingTarget / mapsTo（derived）。
- RegionMapping（ExternalRegion→canonical）≠ brain_region_aggregation_mappings（canonical→coarser）。

## 11. Granularity Boundary

- G1_MACRO / G2_MESO_ANATOMICAL / G3_MESO_FINE / G4_MICROSTRUCTURAL_FINE 属 PostgreSQL granularity framework。
- 不新增 G1/G2/G3/G4 OWL Class；不用 partOf 表达 granularity aggregation。

## 12. Human-only Scope

- V1 production scope = Homo sapiens（NCBI Taxonomy 9606）。
- Allen Mouse production excluded；mouse/rat/macaque/chimpanzee 不得进入 production canonical data。

## 13. TBox / ABox Policy

- Class = 类别；Individual/DB entity = 具体 canonical concept。
- 例：BrainRegion=Class、Hippocampus=future Individual；Gene=Class、APOE=future Individual；Function=Class、Memory=future Individual。
- DataProperty=0 是设计决定，非遗漏。
