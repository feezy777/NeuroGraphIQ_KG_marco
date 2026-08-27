# Gate 3A — CircuitType vs CircuitTopology

本节专门分析「CircuitType」与「CircuitTopology」应如何区分。

---

## 1. 核心判断

**CircuitType（类型）和 CircuitTopology（拓扑）是两层正交语义，不应混在同一个 OWL 层级里。**

- **CircuitType** 回答：「这是一个什么**种类**的回路？」（生物/语义维度）
- **CircuitTopology** 回答：「这个回路**长成什么样** / 怎么连接？」（结构/图维度）

旧草案把大量 topology 词（Pathway / Loop / Feedforward / Feedback / Recurrent）直接当成 CircuitType，属于**把拓扑当成类型**。

---

## 2. 每个词的分层判定

| 概念 | biological type? | topology? | 结论 |
|---|---|---|---|
| Pathway | 否 | 是（open chain） | topology（或独立 Path 实体） |
| Loop | 否 | 是（closed loop） | topology（is_closed_loop） |
| Feedforward | 否 | 是（无反馈前向） | topology（topology_type / role） |
| Feedback | 否 | 是（含反馈边） | topology（has_feedback / role） |
| Recurrent | 否 | 是（复发连接） | topology（has_recurrence） |
| StructuralCircuit | 否 | 否 | 证据维度（circuit_basis） |
| FunctionalCircuit | 否 | 否 | 证据维度（circuit_basis / evidence_basis） |
| NetworkCircuit | 否 | 否 | 概念维度（独立 Network Class） |

---

## 3. 未来更科学的建模方式（本轮只分析，禁止新增 Property）

```
Circuit
├── (future) topology_type : enum { feedforward, feedback, recurrent, loop }
├── (future) is_closed_loop : boolean
├── (future) has_feedback : boolean
├── (future) has_recurrence : boolean
├── (future) directionality : enum { directed, reciprocal, ... }
├── (future) circuit_basis : enum { structural, functional, both }
├── (future) has_function → Function
└── (future) status / assertion_type / confidence
```

- `topology_type` / `is_closed_loop` / `has_feedback` / `has_recurrence` → 描述拓扑，不建 OWL Class。
- `circuit_basis` → 描述证据面，不建 StructuralCircuit / FunctionalCircuit。
- `has_function` → 描述功能，不建 MemoryCircuit / MotorCircuit。
- `status` → 描述状态，不建 UncertainCircuit。

---

## 4. 为什么不为了「分类树看起来丰富」而建类型

- 建一堆 topology 类，会让 LLM 分类提示词把「拓扑形状」和「生物回路」混为一谈。
- 拓扑是可计算、可判定、可组合的**属性**；类型是难以严格判定的**语义类别**。
- 保留 Circuit 为单一 Class + 未来属性，比建立 5+ 个语义重叠的 CircuitType 子类更科学、更利于证据审查。

---

## 5. 待审查结论

- 建议：**V1 暂不定义任何 CircuitType 正式子类**（CircuitType 保留为 reserved extension point，非 owl:Nothing）；topology / evidence / function / status 全部留待 Property Gate 以属性建模。
