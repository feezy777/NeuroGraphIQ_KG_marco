# Gate 6F-A — Spatial vs Granularity Roll-up

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. 区别

- G4-A 70% overlap G3-X 首先属于 brain_region_aggregation_mappings。
- 不自动投影成 canonical spatial relation。

## 2. 规则

- 空间 overlap 只是 mapping evidence / spatial information。
- 只有 brain_region_aggregation_mappings 中 rollup_eligible=TRUE 才能用于 G4→G3→G2→G1 roll-up。
- spatiallyOverlaps / adjacentTo 不能直接 rollup_eligible。

## 3. 不污染 ontology

- 不让 aggregation mapping 自动污染 OWL spatial relation。
