# Gate 6F-B — Spatial vs Aggregation Mapping

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. 冻结

- G4-A 70% overlap G3-B 首先属 brain_region_aggregation_mappings 的 mapping evidence / overlap metric。
- 是否 roll-up 仍由 rollup_eligible=TRUE 决定；不因 overlap 超阈值自动 roll-up。

## 2. 反向

- 存在 aggregation mapping 不自动生成 G4 spatiallyOverlaps G3 OWL relation。两套模型分离。

## 3. 结论

spatial overlap 只是 spatial/integration evidence，不自动成为 partOf / roll-up / OWL spatial relation。
