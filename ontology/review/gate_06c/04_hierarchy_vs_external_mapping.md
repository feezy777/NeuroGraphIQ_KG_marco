# Gate 6C — Hierarchy vs External Mapping

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. 三类关系严格区分

| 关系 | 语义 | 表达 |
|---|---|---|
| Anatomical hierarchy | CA1 subfieldOf Hippocampus | OWL partOf / subfieldOf |
| External Atlas mapping | Julich external → canonical BrainRegion | OWL mapsTo（derived）+ DB region_mappings |
| Canonical cross-granularity aggregation | 多个 canonical G4 → canonical G3 | DB brain_region_aggregation_mappings（不在 OWL） |

## 2. mapsTo 保持原语义

- `mapsTo`：ExternalRegion → BrainRegion，derived convenience mapping。
- **不**改为 BrainRegion mapsTo BrainRegion。
- canonical BrainRegion roll-up 由 DB `brain_region_aggregation_mappings` 负责，不进 OWL。

## 3. aggregation mapping 不写成 partOf

- brain_region_aggregation_mappings 不自动对应 partOf。
- 若只是 70% spatial overlap，不能写 X partOf Y。
- 只有真正 anatomical containment 有科学依据，才写 partOf / subfieldOf。

## 4. 不新增 aggregatesTo / rollsUpTo / mapsToGranularity

这些属 integration/knowledge-production 语义，不是稳定 anatomical ontology relation。当前放 PostgreSQL integration layer。
