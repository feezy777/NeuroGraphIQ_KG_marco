# Gate 6F-B — BrainRegion vs SpatialRepresentation

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. BrainRegion

稳定的 canonical anatomical/scientific concept。例：Hippocampus、CA1、Amygdala。

## 2. SpatialRepresentation

某 BrainRegion 在具体 atlas/version/reference space/mask/label/surface 中的空间表达。同一个 Hippocampus 可在 MNI152 / Julich-Brain / Brainnetome / AAL3 有不同 representations。

## 3. 结论

- BrainRegion identity ≠ specific geometry。
- V1 不新增 SpatialRepresentation OWL Class（brain_region_spatial_representations 数据表已足够）。
