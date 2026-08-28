# Gate 6F-A — Recommended V1 Model

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. 最终推荐

| 项 | 推荐 |
|---|---|
| spatiallyOverlaps | 不进 OWL（DB only，SpatialRepresentation 层） |
| adjacentTo | 不进 OWL（DB only） |
| locatedIn | 不进 OWL（与 partOf 重复，REMOVE/DEFER） |
| SpatialRepresentation Class | 不新增（DB 表已足够） |
| DB spatial relation table | 未来 proposal（brain_region_spatial_relations），本轮不新增 |

## 2. 逐项回答

1. spatiallyOverlaps 是否进 OWL V1：否。
2. adjacentTo 是否进 OWL V1：否。
3. locatedIn 是否进 OWL V1：否。
4. 是否新增 SpatialRepresentation Class：否。
5. 是否新增 DB spatial relation table：未来（Gate 7A amendment proposal）。
6. BrainRegion-level spatial relation 是否稳定：否（representation-level 才稳定）。
7. DB only：spatiallyOverlaps / adjacentTo / geometric containment。
8. DEFER：locatedIn（或 REMOVE）、SpatialRepresentation Class、brain_region_spatial_relations 表。
9. Gate 6F-B 正式新增 ObjectProperty：0。
10. 新增 Class：0。

## 3. 理由

空间关系依赖 atlas/version/reference space + 数值 qualifier（overlap ratio / confidence），是 spatial representation 层的几何事实，不是 canonical 解剖稳定属性。OWL 不为了数量强行加关系。

> **Future Domain/Range = DEFER**（Gate 6F-B 冻结）：不把 spatiallyOverlaps / adjacentTo 的未来 Domain/Range 冻结为 BrainRegion → BrainRegion；未来更可能建模为 SpatialRepresentation → SpatialRepresentation。此处 BrainRegion→BrainRegion 仅作 CANDIDATE CONSIDERED，NOT FROZEN。
