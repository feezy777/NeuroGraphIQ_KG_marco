# Gate 6F-A — Problem Definition

Ontology IRI: `https://neurographiq.org/ontology/human-brain`（version 0.6.2-gate6d，本轮不改）
本轮状态: **仅科学语义设计，不写 TTL**

---

## 1. 目标

审查 Human BrainRegion 之间的空间关系，决定哪些进入 V1 OWL Core。

候选：spatiallyOverlaps / adjacentTo / locatedIn。

## 2. 必须先区分四类语义

| 类别 | 例子 | 表达 |
|---|---|---|
| A. Anatomical hierarchy | CA1 subfieldOf Hippocampus | partOf / subfieldOf（OWL） |
| B. Spatial relation | A overlaps B / A adjacent B | 几何关系（待审） |
| C. External Atlas Mapping | ExternalRegion → canonical | region_mappings |
| D. Cross-granularity aggregation | G4 → G3 | brain_region_aggregation_mappings |

四类不得混用。

## 3. 关键判断维度

- 语义是否稳定（不随 atlas/version/reference space 变）。
- 是否与 partOf/subfieldOf 重复。
- 是否与 RegionMapping / aggregation mapping 重复。
- 是否需要数值 qualifier（overlap ratio / confidence）。
- 是否误导 hierarchy reasoning。
