# Gate 6G-A — ObjectProperty Matrix（26）

| Property | 中文 | Domain | Range | Canonical/Derived | subPropertyOf | Status |
|---|---|---|---|---|---|---|
| structurallyConnectedTo | 结构连接 | BrainRegion | BrainRegion | Derived | — | OK |
| functionallyConnectedTo | 功能连接 | BrainRegion | BrainRegion | Derived | — | OK |
| projectsTo | 投射到 | BrainRegion | BrainRegion | Derived | structurallyConnectedTo | OK |
| effectivelyConnectedTo | 有效连接 | BrainRegion | BrainRegion | Derived | — | OK |
| participatesIn | 参与 | BrainRegion | Circuit ∪ Function | Canonical | — | OK |
| modulates | 调控 | Gene ∪ Neurotransmitter | BrainRegion ∪ Circuit ∪ Function | Canonical | — | OK |
| increasesRiskOf | 增加风险 | Gene | Disease | Canonical | — | OK |
| hasFunction | 具有功能 | Circuit | Function | Canonical | — | OK |
| hasSymptom | 具有症状 | Disease | Symptom | Canonical | — | OK |
| actsOn | 作用于 | Neurotransmitter | Receptor | Canonical | — | OK |
| hasEndpointRegion | 连接端点脑区 | Connection | BrainRegion | Canonical | — | OK |
| hasSourceRegion | 起始脑区 | Connection | BrainRegion | Canonical | hasEndpointRegion | OK |
| hasTargetRegion | 目标脑区 | Connection | BrainRegion | Canonical | hasEndpointRegion | OK |
| includesRegion | 包含脑区 | Circuit | BrainRegion | Canonical | — | OK |
| hasConnectionMembership | 具有连接成员关系 | Circuit | CircuitConnectionMembership | Canonical | — | OK |
| membershipConnection | 成员连接 | CircuitConnectionMembership | Connection | Canonical | — | OK |
| hasConnection | 包含连接 | Circuit | Connection | Derived | — | OK |
| reportedIn | 报道于 | ResearchStudy | Publication | Canonical | — | OK |
| providesEvidence | 提供证据 | Publication | Evidence | Canonical | — | OK |
| definedInAtlas | 定义于图谱 | ExternalRegion | Atlas | Canonical | — | OK |
| mappingSource | 映射源 | RegionMapping | ExternalRegion | Canonical | — | OK |
| mappingTarget | 映射目标 | RegionMapping | BrainRegion | Canonical | — | OK |
| mapsTo | 映射到 | ExternalRegion | BrainRegion | Derived | — | OK |
| partOf | 属于 | BrainRegion | BrainRegion | Canonical | — | OK |
| subfieldOf | 亚区属于 | BrainRegion | BrainRegion | Canonical | partOf | OK |
| subFunctionOf | 下位功能 | Function | Function | Canonical | — | OK |

## 结论

- 26 ObjectProperty 全部符合冻结清单。
- 4 subPropertyOf 正确；无意外 subPropertyOf。
- 无 supports/contradicts/qualifies/spatial relation 进入 OWL。
