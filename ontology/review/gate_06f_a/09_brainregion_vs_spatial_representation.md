# Gate 6F-A — BrainRegion vs SpatialRepresentation

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. 三层

- **BrainRegion**：canonical anatomical/scientific concept（稳定）。
- **Atlas**：parcellation/reference resource。
- **SpatialRepresentation**：某 BrainRegion 在具体 atlas/space/version 中的几何表达。

## 2. 关键问题

spatial relation 究竟是 BrainRegion-level 还是 SpatialRepresentation-level？

若同一 BrainRegion 在 representation A 中 adjacent、representation B 中不 adjacent，则 BrainRegion-level adjacentTo 不稳定。

## 3. 结论

- 几何 overlap/adjacency 属于 SpatialRepresentation 层。
- BrainRegion-level 空间关系**不稳定**。
- **V1 不新增 SpatialRepresentation OWL Class**（当前 brain_region_spatial_representations 是数据表，已足够）。
