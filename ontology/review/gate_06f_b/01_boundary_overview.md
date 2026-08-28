# Gate 6F-B — Spatial Ontology Boundary Overview

Ontology IRI: `https://neurographiq.org/ontology/human-brain`（version 0.6.2-gate6d，本轮不改）
本轮状态: **Boundary Freeze，不新增任何 ontology entity**

---

## 1. 核心结论

V1 OWL Core 不新增任何 spatial relation。空间关系属 representation-dependent spatial knowledge，非 BrainRegion canonical concept 的稳定本体语义。

## 2. 本轮 OWL expansion

- 新增 Class = 0
- 新增 ObjectProperty = 0
- 新增 DataProperty = 0
- 新增 Individual = 0

## 3. 冻结状态

| 概念 | 状态 |
|---|---|
| spatiallyOverlaps | DB ONLY / DEFER OWL |
| adjacentTo | DB ONLY / DEFER OWL |
| locatedIn | REMOVE / DEFER |
| SpatialRepresentation | V1 不新增 OWL Class |
| partOf / subfieldOf | 保持 canonical anatomical hierarchy |

## 4. 不修改 TTL

version 保持 0.6.2-gate6d（TTL 无变化，不虚假升级版本）。
