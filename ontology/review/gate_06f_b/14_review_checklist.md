# Gate 6F-B Human Review Checklist — Spatial Ontology Boundary Freeze

请逐项确认。本 Gate **未扩展正式 OWL 本体**。

---

## 审查清单

- [ ] 未修改 TTL（version 仍 0.6.2-gate6d）
- [ ] Named Class = 23
- [ ] ObjectProperty = 26
- [ ] DataProperty = 0
- [ ] spatiallyOverlaps 不进 OWL
- [ ] adjacentTo 不进 OWL
- [ ] locatedIn 不进 OWL
- [ ] SpatialRepresentation 不进 OWL
- [ ] partOf 保持 canonical anatomical hierarchy
- [ ] subfieldOf 保持（subfieldOf ⊑ partOf）
- [ ] spatial relation 不参与 hierarchy
- [ ] overlap 不自动 partOf
- [ ] overlap 不自动 roll-up
- [ ] adjacency 不自动 Connection
- [ ] spatial relation 不自动 aggregation mapping
- [ ] aggregation mapping 不自动 spatial relation
- [ ] reference_space / atlas_version 标为 spatial 必需上下文
- [ ] future Domain/Range 已改为 DEFER（SpatialRepresentation-level）
- [ ] Gate 7A 仍 32 表，未新增 brain_region_spatial_relations
- [ ] 未 commit / 未 push

---

## 关键决策点（需人工拍板）

1. **OWL 不新增任何 spatial relation（Option C，DB only）**——是否同意？
2. **locatedIn REMOVE/DEFER（与 partOf 重复）**——是否同意？
3. **不新增 SpatialRepresentation OWL Class**——是否同意？

---

## 审查说明

- 若某项不通过，请在对应行标注，并在 `ontology/review/gate_06f_b/` 下追加意见。
- 全部通过后，回复 **「Gate 6F-B 通过」**，方可进入后续。
