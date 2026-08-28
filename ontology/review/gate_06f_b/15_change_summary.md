# Gate 6F-B — Change Summary（Spatial Ontology Boundary Freeze）

Ontology IRI: `https://neurographiq.org/ontology/human-brain`（version 0.6.2-gate6d，本轮不改）
本轮状态: **Boundary Freeze，无 ontology entity 变化**

---

## 1. 本轮产出

- 16 文件 Spatial Boundary Freeze review。
- OWL 零扩展。

## 2. 冻结边界

| 层 | 内容 |
|---|---|
| OWL Core | BrainRegion + partOf/subfieldOf（canonical anatomical hierarchy） |
| PostgreSQL | brain_region_spatial_representations + 未来 brain_region_spatial_relations |

## 3. 状态

- spatiallyOverlaps / adjacentTo：DB ONLY / DEFER OWL。
- locatedIn：REMOVE / DEFER。
- SpatialRepresentation：V1 不新增 OWL Class。

## 4. 未做

- 未修改 TTL（仍 0.6.2-gate6d / 23 Class / 26 ObjectProperty / 0 DataProperty）。
- 未新增 Class / ObjectProperty / DataProperty / Individual。
- 未新增表 / 未改数据库。
