# Gate 6F-A Human Review Checklist — BrainRegion Spatial Relations Semantic Review

请逐项确认。本 Gate **仅科学语义设计**，未修改 TTL / Gate 7A / 数据库。

---

## 审查清单

- [ ] spatiallyOverlaps 不进 OWL（DB only）
- [ ] adjacentTo 不进 OWL（DB only）
- [ ] locatedIn 不进 OWL（与 partOf 重复）
- [ ] 空间关系与 anatomical hierarchy（partOf/subfieldOf）严格区分
- [ ] 空间关系与 RegionMapping 严格区分
- [ ] 空间关系与 granularity roll-up 严格区分
- [ ] 空间 overlap 不自动成为 partOf
- [ ] 空间 overlap 不自动 roll-up
- [ ] adjacent 不推导 Connection
- [ ] adjacent 不推导 participatesIn
- [ ] 空间关系不参与 hierarchy traversal
- [ ] 不新增 SpatialRepresentation OWL Class
- [ ] 不新增 DB spatial relation table（本轮）
- [ ] reference_space / atlas_version 必须在 DB 保留
- [ ] spatiallyOverlaps 语义 symmetric、非 transitive
- [ ] adjacentTo 语义 symmetric、非 transitive
- [ ] 正式 TTL 未修改（仍 0.6.2-gate6d）
- [ ] 未新增 Class / ObjectProperty / DataProperty / Individual
- [ ] 未 commit / 未 push

---

## 关键决策点（需人工拍板）

1. **Option C：OWL 不新增任何 spatial relation（全部 PostgreSQL spatial model）**——是否同意？
2. **locatedIn 因与 partOf 重复而不进入 V1（REMOVE/DEFER）**——是否同意？
3. **不新增 SpatialRepresentation OWL Class（DB 表已足够）**——是否同意？

---

## 审查说明

- 若某项不通过，请在对应行标注，并在 `ontology/review/gate_06f_a/` 下追加意见。
- 全部通过后，回复 **「Gate 6F-A 通过」**，方可进入 Gate 6F-B（formalization）。
