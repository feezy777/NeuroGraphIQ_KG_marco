# Gate 6A — Relation Matrix（关系总表）· 第二轮修订

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
本轮状态: **仅总表，未修改正式 TTL**

23 行（当前可正式写入 ObjectProperty 的 V1 候选）。方向 `→` = directed，`—` = non-directional/unknown。

| # | Source | Relation | Target | Direction | Role | 来源 |
|---|---|---|---|---|---|---|
| 1 | BrainRegion | structurallyConnectedTo | BrainRegion | — | Derived | PPT |
| 2 | BrainRegion | functionallyConnectedTo | BrainRegion | — | Derived | PPT |
| 3 | BrainRegion | projectsTo | BrainRegion | → | Derived | PPT |
| 4 | BrainRegion | effectivelyConnectedTo | BrainRegion | → | Derived | Added |
| 5 | BrainRegion | participatesIn | Circuit OR Function | → | Canonical | PPT |
| 6 | Gene/Neurotransmitter | modulates | BrainRegion/Circuit/Function | → | Canonical | PPT |
| 7 | Gene | increasesRiskOf | Disease | → | Canonical | PPT |
| 8 | Circuit | hasFunction | Function | → | Canonical | Added |
| 9 | Disease | hasSymptom | Symptom | → | Canonical | Added |
| 10 | Neurotransmitter | actsOn | Receptor | → | Canonical | Added |
| 11 | Connection | hasEndpointRegion | BrainRegion | 无方向 | Canonical | Added |
| 12 | Connection | hasSourceRegion | BrainRegion | → | Canonical | Added |
| 13 | Connection | hasTargetRegion | BrainRegion | → | Canonical | Added |
| 14 | Circuit | includesRegion | BrainRegion | → | Canonical | Added |
| 15 | Circuit | hasConnectionMembership | CircuitConnectionMembership | → | Canonical | Added |
| 16 | CircuitConnectionMembership | membershipConnection | Connection | → | Canonical | Added |
| 17 | Circuit | hasConnection | Connection | → | Derived | Added |
| 18 | ResearchStudy | reportedIn | Publication | → | Canonical | Added |
| 19 | Publication | providesEvidence | Evidence | → | Canonical | Added |
| 20 | ExternalRegion | definedInAtlas | Atlas | → | Canonical | Added |
| 21 | RegionMapping | mappingSource | ExternalRegion | → | Canonical | Added |
| 22 | RegionMapping | mappingTarget | BrainRegion | → | Canonical | Added |
| 23 | ExternalRegion | mapsTo | BrainRegion | → | Derived | Added |

---

## 统计（Round 2）

- PPT 原始：6（#1 #2 #3 #5 #6 #7）
- Canonical current：17
- Derived current：6（#1 #2 #3 #4 #17 #23）
- **当前可正式写入 ObjectProperty 的 V1 relation 总数：23**

## Deferred semantic relations（不计入 23）

| 关系 | 状态 |
|---|---|
| supports | KEEP semantics / FORMALIZATION DEFER |
| contradicts | KEEP semantics / FORMALIZATION DEFER |
