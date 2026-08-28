# Gate 6F-A — Change Summary（BrainRegion Spatial Relations）

Ontology IRI: `https://neurographiq.org/ontology/human-brain`（version 0.6.2-gate6d，本轮不改）
本轮状态: **仅科学语义设计，不写 TTL**

---

## 1. 本 Gate 产出

- 16 文件 spatial relations 语义审查。
- 推荐 **Option C：OWL 不新增任何 spatial relation**。

## 2. 推荐

| 项 | 推荐 |
|---|---|
| spatiallyOverlaps | DB only（SpatialRepresentation 层） |
| adjacentTo | DB only |
| locatedIn | REMOVE/DEFER（与 partOf 重复） |
| SpatialRepresentation Class | 不新增 |
| DB spatial relation table | 未来 proposal |

## 3. 理由

空间关系依赖 atlas/version/reference space + 数值 qualifier，是 spatial representation 层的几何事实，不是 canonical 解剖稳定属性。

## 4. 未做

- 未修改 TTL（仍 0.6.2-gate6d / 23 Class / 26 ObjectProperty / 0 DataProperty）。
- 未修改 Gate 7A / 数据库 / migration。
- 未新增 Class / ObjectProperty / DataProperty / Individual。
