# Gate 6F-A — Spatial Relation Scope

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. 核心判断

空间关系（overlap / adjacency）是**几何事实**，高度依赖 atlas / version / reference space / registration。它不是 BrainRegion 概念的稳定解剖属性。

## 2. 三层概念

- **BrainRegion**：canonical anatomical/scientific concept（稳定）。
- **Atlas**：parcellation/reference resource。
- **SpatialRepresentation**：某 BrainRegion 在具体 atlas/space/version 中的几何表达。

几何 overlap/adjacency 首先属于 SpatialRepresentation 层，而非 BrainRegion concept 本身。

## 3. 结论倾向

若 overlap/adjacency 强依赖 atlas/version/reference space，则留数据库层更科学，不强行进 OWL。
