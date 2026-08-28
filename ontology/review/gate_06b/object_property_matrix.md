# Gate 6B — ObjectProperty Matrix（对象属性总表）

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
version: `0.6.0-gate6b`

| Property | 中文 | Domain | Range | Canonical/Derived | Direction | PPT/Project | SubPropertyOf |
|---|---|---|---|---|---|---|---|
| structurallyConnectedTo | 结构连接 | BrainRegion | BrainRegion | Derived | — | PPT | — |
| functionallyConnectedTo | 功能连接 | BrainRegion | BrainRegion | Derived | — | PPT | — |
| projectsTo | 投射到 | BrainRegion | BrainRegion | Derived | → | PPT | structurallyConnectedTo |
| effectivelyConnectedTo | 有效连接 | BrainRegion | BrainRegion | Derived | → | Project | — |
| participatesIn | 参与 | BrainRegion | Circuit ∪ Function | Canonical | → | PPT | — |
| modulates | 调控 | Gene ∪ Neurotransmitter | BrainRegion ∪ Circuit ∪ Function | Canonical | → | PPT | — |
| increasesRiskOf | 增加风险 | Gene | Disease | Canonical | → | PPT | — |
| hasFunction | 具有功能 | Circuit | Function | Canonical | → | Project | — |
| hasSymptom | 具有症状 | Disease | Symptom | Canonical | → | Project | — |
| actsOn | 作用于 | Neurotransmitter | Receptor | Canonical | → | Project | — |
| hasEndpointRegion | 连接端点脑区 | Connection | BrainRegion | Canonical | 无方向 | Project | — |
| hasSourceRegion | 起始脑区 | Connection | BrainRegion | Canonical | → | Project | hasEndpointRegion |
| hasTargetRegion | 目标脑区 | Connection | BrainRegion | Canonical | → | Project | hasEndpointRegion |
| includesRegion | 包含脑区 | Circuit | BrainRegion | Canonical | → | Project | — |
| hasConnectionMembership | 具有连接成员关系 | Circuit | CircuitConnectionMembership | Canonical | → | Project | — |
| membershipConnection | 成员连接 | CircuitConnectionMembership | Connection | Canonical | → | Project | — |
| hasConnection | 包含连接 | Circuit | Connection | Derived | → | Project | — |
| reportedIn | 报道于 | ResearchStudy | Publication | Canonical | → | Project | — |
| providesEvidence | 提供证据 | Publication | Evidence | Canonical | → | Project | — |
| definedInAtlas | 定义于图谱 | ExternalRegion | Atlas | Canonical | → | Project | — |
| mappingSource | 映射源 | RegionMapping | ExternalRegion | Canonical | → | Project | — |
| mappingTarget | 映射目标 | RegionMapping | BrainRegion | Canonical | → | Project | — |
| mapsTo | 映射到 | ExternalRegion | BrainRegion | Derived | → | Project | — |

---

## 统计

- Canonical：17；Derived：6；总计：23。
- 3 条 subPropertyOf（projectsTo、hasSourceRegion、hasTargetRegion）。
- supports / contradicts 未写入（DEFER）。
