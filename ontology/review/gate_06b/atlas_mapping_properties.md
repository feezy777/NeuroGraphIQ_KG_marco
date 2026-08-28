# Gate 6B — Atlas / Mapping Properties（图谱映射属性）

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
version: `0.6.0-gate6b`

---

## 1. 关系设计

| Property | Domain | Range | Role |
|---|---|---|---|
| definedInAtlas | ExternalRegion | Atlas | Canonical |
| mappingSource | RegionMapping | ExternalRegion | Canonical |
| mappingTarget | RegionMapping | BrainRegion | Canonical |
| mapsTo | ExternalRegion | BrainRegion | Derived |

## 2. Reification

- canonical 用 reified `RegionMapping`（mappingSource + mappingTarget）。
- `mapsTo` 为 Derived convenience relation。
- 不建 property chain（mapsTo 只定义 + comment 说明 canonical source）。

## 3. 例子

- Brainnetome parcel A9m definedInAtlas BrainnetomeAtlas。
- Mapping M001 mappingSource A9m；M001 mappingTarget canonical mPFC。
