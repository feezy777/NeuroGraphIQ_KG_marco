# Gate 6A Human Review Checklist — 第二轮（Core Relation Ontology Design）

请逐项确认。本 Gate **仅产出关系设计文档**，未修改正式 TTL。

---

## 审查清单（Round 2）

- [ ] PPT 6 个 relation 仍完整保留
- [ ] PARTICIPATES_IN = BrainRegion → Circuit OR Function
- [ ] HAS_FUNCTION 已收窄为 Circuit → Function
- [ ] BrainRegion→Function 不存在两套 canonical relation
- [ ] HAS_ENDPOINT_REGION 已增加
- [ ] FunctionalConnectivity 使用 endpoint
- [ ] FunctionalConnectivity 不使用伪 source/target
- [ ] direction-unknown StructuralConnection 使用 endpoint
- [ ] Projection 使用 source/target
- [ ] EffectiveConnectivity 有方向时使用 source/target
- [ ] SUPPORTS semantics 保留但 formalization DEFER
- [ ] CONTRADICTS semantics 保留但 formalization DEFER
- [ ] assertion-level evidence 问题已记录
- [ ] 未新增 Assertion 类
- [ ] APOE ε4 已从 Gene 示例移除
- [ ] GeneticVariant/Allele 仅记录为 future extension
- [ ] FUNCTIONALLY_CONNECTED_TO 示例没有单向箭头
- [ ] STRUCTURALLY_CONNECTED_TO 无方向示例没有单向箭头
- [ ] PROJECTS_TO 保持有向
- [ ] EFFECTIVELY_CONNECTED_TO 保持有向
- [ ] Circuit membership model 未改变
- [ ] Atlas reification model 未改变
- [ ] direct graph relations 仍不是 canonical truth
- [ ] Connection entity 仍是 canonical truth
- [ ] Relation 数量已重新统计
- [ ] 正式 TTL 未修改
- [ ] ObjectProperty = 0
- [ ] DataProperty = 0
- [ ] Individual = 0
- [ ] 未 commit
- [ ] 未 push

---

## 关键决策点（需人工拍板，Round 2）

1. **PARTICIPATES_IN 恢复为 BrainRegion → Circuit OR Function**——是否同意？
2. **HAS_FUNCTION 收窄为 Circuit → Function**（BrainRegion→Function 用 participatesIn）——是否同意？
3. **新增 HAS_ENDPOINT_REGION**（不表方向）；source/target 仅方向已知时用——是否同意？
4. **FunctionalConnectivity 禁止伪 source/target，用 hasEndpointRegion**——是否同意？
5. **SUPPORTS / CONTRADICTS → KEEP 语义 / FORMALIZATION DEFER**（assertion-level 缺口）——是否同意？
6. **APOE ε4 示例改为 APOE；GeneticVariant/Allele 留未来**——是否同意？
7. **non-directional 示例改用 `—`（不写单向箭头）**——是否同意？

---

## 审查说明

- 若某项不通过，请在对应行标注，并在 `ontology/review/gate_06a/` 下追加意见，**不要修改正式 TTL**。
- 全部通过后，回复 **「Gate 6A 通过」**，方可进入正式 ObjectProperty 写入（Gate 6B）。
