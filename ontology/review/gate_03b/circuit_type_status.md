# Gate 3B — CircuitType 状态说明

Ontology IRI: `https://neurographiq.org/ontology/macro96`
Version: `0.3.0-gate3b`（draft）

---

## CircuitType = reserved extension point

`ngiq:CircuitType` 在 NeuroGraphIQ Macro96 V1 中的正式状态（写入 rdfs:comment）：

- **no subclasses**（无子类）
- **no individuals**（无 individual）
- **not currently used for circuit classification**（当前不用于回路分类）

## 明确非空类

- CircuitType **不是** `owl:Nothing`。
- **没有**写 `owl:equivalentClass owl:Nothing`。
- **没有**通过任何逻辑公理（Restriction / DisjointClass / property chain 等）将其定义为空类。

## 不作为 CircuitType 的拓扑概念

Pathway / Loop / Feedforward / Feedback / Recurrent 在 V1 中**不作为 CircuitType**（它们属于未来 Property Gate 的 topology 特征）。

- 本轮未创建：`ngiq:Loop`、`ngiq:FeedforwardCircuit`、`ngiq:FeedbackCircuit`、`ngiq:RecurrentCircuit`。
- 本轮未创建：`topology_type` / `is_closed_loop` / `has_feedback` / `has_recurrence` Property。

## 去留

- 是否长期保留 `CircuitType`，留待 **Ontology Freeze** 阶段决定。
