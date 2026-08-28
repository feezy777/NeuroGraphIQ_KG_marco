# Gate 6F-B — Spatial vs Region Mapping

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. 区别

- RegionMapping.mapping_type=overlapping：ExternalRegion → canonical BrainRegion integration mapping。
- spatial overlap：几何事实（representation 层）。

## 2. 冻结

- mapping_method 含 spatial overlap 仍属 integration mapping evidence。
- 不自动生成 canonical BrainRegion spatiallyOverlaps BrainRegion。
- 需独立验证（reference space / registration / confidence）。
