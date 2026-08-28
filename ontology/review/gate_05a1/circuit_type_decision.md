# Gate 5A.1 — CircuitType 去留决策

Ontology IRI（当前）: `https://neurographiq.org/ontology/macro96`
本轮状态: **仅决策文档，未修改正式 TTL**

---

## 1. 前提：Gate 3 科学语义冻结

Circuit 定义**完全保持**：biological/functional concept；not graph cycle；not necessarily closed loop；circuit-level evidence 必需；missing edge 仅 candidate/hypothesis。本轮只处理 CircuitType 是否删除。

## 2. 当前状态

- CircuitType = reserved extension point；subclasses=0；individuals=0；不参与 classification。
- Gate 3 已审查旧候选 Loop / Feedforward / Feedback / Recurrent / Structural / Functional / Network / Uncertain，分别属于 topology / evidence basis / network concept / status，**均不适合作为 V1 Circuit subtype**。

## 3. 四方案比较

| 方案 | 说明 | 评估 |
|---|---|---|
| A | KEEP reserved placeholder | 空占位，无实际语义 |
| B | **REMOVE from V1** | 当前无真实 subclass/individual/use case |
| C | Controlled vocabulary | 无分类需求，暂不需要词表 |
| D | 未来重建科学稳定的 subtype hierarchy | 留未来 ontology version |

## 4. 推荐：方案 B — REMOVE CircuitType FROM V1

理由：
- 当前没有真实 subclass、individual、classification use case。
- topology 已决定由 future properties 表达。
- 空 placeholder 不提供实际语义。
- 未来需要时可在新 ontology version 中重新增加。

## 5. 关键澄清：REMOVE CircuitType ≠ Circuit 没有 topology

未来仍可有（本轮不建 Property）：

- is_closed_loop
- has_feedback
- has_recurrence
- topology_type
- construction_mode

## 6. 结论

| 项 | 决策 |
|---|---|
| CircuitType | **REMOVE from V1** |
| Circuit | KEEP（Gate 3 语义冻结） |
| Circuit topology | 未来由 Property 表达（is_closed_loop / has_feedback / topology_type / construction_mode） |
| 是否重审 Gate 3 科学语义 | 否 |
