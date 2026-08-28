# Gate 6F-A — Spatial vs Region Mapping

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. 区别

- RegionMapping.mapping_type=overlapping：ExternalRegion 与 canonical BrainRegion 的 integration mapping。
- spatiallyOverlaps：两个 canonical BrainRegion 的空间关系。

## 2. 规则

- 不因 ExternalRegion overlaps BrainRegion 就自动产生 canonical BrainRegion spatiallyOverlaps BrainRegion。
- 需独立验证（独立 reference space / registration / confidence）。

## 3. 不混淆

RegionMapping 是 ExternalRegion→canonical 的 reified mapping；spatial relation 是 canonical↔canonical 的几何事实。
