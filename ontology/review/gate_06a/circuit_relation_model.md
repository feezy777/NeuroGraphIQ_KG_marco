# Gate 6A — Circuit Relation Model（回路关系模型）

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
本轮状态: **仅设计文档，未修改正式 TTL**

---

## 1. Circuit → BrainRegion

- **推荐 canonical**：`includesRegion`（Circuit → BrainRegion）。
- 例子：PapezCircuit includesRegion Hippocampus。
- 方向：Directed（circuit → region）。
- 逆语义：`BrainRegion participatesIn Circuit`（本 Gate 不建 owl:inverseOf，仅记录互逆语义）。

| 关系 | Domain | Range | Role |
|---|---|---|---|
| includesRegion | Circuit | BrainRegion | Canonical |
| participatesIn | BrainRegion | Circuit | Canonical |

## 2. Circuit → Connection（reification 思路）

Circuit 由多个 Connection 组成，但已有 `CircuitConnectionMembership`（reification），不能简单忽略。

两方案：

- **A**：`Circuit hasConnection Connection`（简单直接）。
- **B**：`Circuit hasConnectionMembership CircuitConnectionMembership` + `CircuitConnectionMembership membershipConnection Connection`（reification）。

**推荐：B（canonical detailed model 用 reification）。**

理由：membership 后续需保存 step_order / role / membership evidence / topology context（同一 Connection 在不同 Circuit 中 step 不同），这些信息属于 membership，不属于 Connection 本身。

| 关系 | Domain | Range | Role |
|---|---|---|---|
| hasConnectionMembership | Circuit | CircuitConnectionMembership | Canonical |
| membershipConnection | CircuitConnectionMembership | Connection | Canonical |
| hasConnection | Circuit | Connection | Derived（convenience） |

例子：
- Circuit A hasConnectionMembership M1；M1 membershipConnection C001（step_order=2）。
- Circuit B hasConnectionMembership M2；M2 membershipConnection C001（step_order=5）。

## 3. 禁止重复建模

- `hasConnection`（direct）仅作 derived convenience，canonical 以 reification 为准。
- 同一 Connection 在多个 Circuit 的上下文信息只存 membership，不重复存 Connection。
