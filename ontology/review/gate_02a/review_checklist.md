# Gate 2A Human Review Checklist — NeuroGraphIQ Macro96 ConnectionType

请逐项确认。本 Gate **仅产出方案**，未修改正式 TTL。

## 审查清单

- [ ] ConnectionType 根概念合理（仍是 Gate 1 的一级 Class，作为连接类型的受控词表根）
- [ ] Anatomical/Structural 命名合理（推荐 `StructuralConnection`，altLabel 保留 `anatomical connection`）
- [ ] Projection 定义合理（有向结构连接，⊑ StructuralConnection）
- [ ] Projection 的方向语义明确（必有 source→target；方向未知不得记为 Projection；且方向明确也不足——仍需 axonal projection 语义/证据）
- [ ] FiberTractConnection 是否需要合理（本轮建议 **DEFER**，视为证据/通路描述而非类型）
- [ ] FunctionalConnectivity 定义合理（统计依赖/时间相关，Friston 1994）
- [ ] FunctionalConnectivity 与结构连接明确分离（FC 不隐含直接解剖连接）
- [ ] EffectiveConnectivity 定义合理（模型依赖的有向影响/耦合，Friston 1994/2011）
- [ ] EffectiveConnectivity 与 Projection 明确分离（有向影响/耦合 ≠ 有向解剖投射）
- [ ] Coactivation 是否应排除已经审查（REMOVE，functional observation / evidence candidate，不可自动晋升为 FC）
- [ ] AssociationConnection 是否应排除已经审查（REMOVE，统计义并入 FC / 纤维义转 DEFER）
- [ ] LocalAnatomicalConnection 是否有必要已经审查（REMOVE，宏观尺度下无此类型之别）
- [ ] unknown / uncertain 没有被错误建成生物学类型（→ review_status / connection_status / confidence）
- [ ] 类型数量没有过度扩张（仅 4 个：StructuralConnection / Projection / FunctionalConnectivity / EffectiveConnectivity）
- [ ] 所有定义具有清晰 inclusion criteria（见 definition_cards）
- [ ] 所有定义具有清晰 exclusion criteria（见 definition_cards）
- [ ] 没有伪造 Reference（6 条 verified 均联网核实；2 条 pending 明确标注）
- [ ] 当前正式 TTL 没有被修改（`git diff -- ontology/neurographiq_macro96_v1.ttl` 为空）

## 关键决策点（需人工拍板）

1. **命名不对称**：接受 `StructuralConnection`（-Connection）+ `FunctionalConnectivity` / `EffectiveConnectivity`（-Connectivity）的有意不对称？对称替代见 taxonomy_proposal §4。
2. **Projection 层级**：作为 StructuralConnection 子类（推荐）还是顶层兄弟？
3. **FiberTractConnection DEFER**：同意暂不建类？
4. **Coactivation / Association / Local 三 REMOVE**：同意不进 V1？

## 审查说明

- 若某项不通过，请在对应行标注，并在 `ontology/review/gate_02a/` 下追加意见，**不要修改正式 TTL**。
- 全部通过后，回复 **「Gate 2A 通过」**，方可进入 Gate 2B（正式写入 TTL）。
