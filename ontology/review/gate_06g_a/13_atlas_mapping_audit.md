# Gate 6G-A — Atlas / Mapping Audit

---

## 结果：PASS（0 issue）

- definedInAtlas ExternalRegion→Atlas；mappingSource RegionMapping→ExternalRegion；mappingTarget RegionMapping→BrainRegion；mapsTo ExternalRegion→BrainRegion（derived）。
- 无 BrainRegion mapsTo BrainRegion。
- RegionMapping（ExternalRegion→BrainRegion）与 aggregation mapping（canonical→coarser）严格分离。
