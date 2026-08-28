# Gate 6A — Atlas / Mapping Relations

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
本轮状态: **仅设计文档，未修改正式 TTL**

---

## 1. 关系设计

| 关系 | Domain | Range | 方向 | Role |
|---|---|---|---|---|
| definedInAtlas | ExternalRegion | Atlas | Directed | Canonical |
| mappingSource | RegionMapping | ExternalRegion | Directed | Canonical |
| mappingTarget | RegionMapping | BrainRegion | Directed | Canonical |
| mapsTo | ExternalRegion | BrainRegion | Directed | Derived |

例子：
- Brainnetome parcel A9m definedInAtlas BrainnetomeAtlas。
- Mapping M001 mappingSource ExternalRegion A9m；Mapping M001 mappingTarget canonical mPFC。

## 2. 为什么用 reification（RegionMapping）

- 不要简单只用 `ExternalRegion mapsTo BrainRegion` 作为 canonical storage。
- 因为未来 mapping 需保存 mapping_type / confidence / evidence / review。
- 因此 canonical 用 reified `RegionMapping` + mappingSource / mappingTarget。
- `mapsTo`（ExternalRegion → BrainRegion）仅作 **Derived convenience relation**。

## 3. 边界

- ExternalRegion ≠ canonical BrainRegion。
- RegionMapping 是 reified mapping entity，不是简单边。
