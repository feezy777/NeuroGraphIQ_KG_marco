# Gate 3A — CircuitType 边界矩阵

比较 8 个旧候选概念，在 9 个正交维度上的取值，验证「为什么它们都不是 CircuitType」。

## 1. 主矩阵

| 概念 | Biological circuit | Topology concept | Requires direction | Requires closed loop | Requires recurrence | Structural evidence | Functional evidence | Topology feature computable from graph structure alone | Recommended ontology status |
|---|---|---|---|---|---|---|---|---|---|
| **Pathway** | ◐（仅作为路线） | ✅ 是 | ✅ 是 | ❌ 否 | ❌ 否 | ◐ | ◐ | ✅ 可计算 | **future REMODEL / DEFER**（→ 独立 Path 实体） |
| **Loop** | ◐（需证据） | ✅ 是 | ✅ 是 | ✅ **是** | ❌ 否 | ◐ | ◐ | ✅ 可计算（闭合拓扑 ≠ biological loop） | **REMODEL**（→ is_closed_loop） |
| **FeedforwardCircuit** | ❌ 否（motif） | ✅ 是 | ✅ 是 | ❌ 否 | ❌ 否 | ❌ | ❌ | ✅ 可计算 | **REMODEL**（→ topology_type） |
| **FeedbackCircuit** | ❌ 否（角色） | ✅ 是 | ✅ 是 | ◐ 部分 | ❌ 否 | ❌ | ❌ | ✅ 可计算 | **REMODEL**（→ has_feedback） |
| **RecurrentCircuit** | ❌ 否（连接性质） | ✅ 是 | ◐ variable | ❌ 否 | ✅ **是** | ❌ | ❌ | ✅ 可计算 | **REMODEL**（→ has_recurrence） |
| **StructuralCircuit** | ❌ 否（证据面） | ❌ 否 | ❌ 否 | ❌ 否 | ❌ 否 | ✅ 是 | ❌ 否 | ❌ 不适用 | **REMOVE**（→ circuit_basis / evidence_basis = structural） |
| **FunctionalCircuit** | ❌ 否（证据面） | ❌ 否 | ❌ 否 | ❌ 否 | ❌ 否 | ❌ 否 | ✅ 是 | ❌ 不适用 | **REMOVE**（→ circuit_basis / evidence_basis = functional） |
| **NetworkCircuit** | ❌ 否（概念混合） | ❌ 否 | ❌ 否 | ❌ 否 | ❌ 否 | ◐ | ✅ 是 | ❌ 不适用 | **DEFER**（→ 独立 Network Class） |

### 图例

- ✅ = 该维度是本概念的核心特征
- ◐ = 部分/有条件
- ❌ = 该维度不适用或非本概念特征

> **关于「Topology feature computable from graph structure alone」**：graph structure 可自动计算 path / feedforward / feedback / recurrence / closed-loop 等 **topology feature**；但这些 feature **不得单独创建或晋升 biological Circuit / Pathway**。

## 2. 关键判读

### 2.1 三组「拓扑类」概念（Pathway / Loop / Feedforward / Feedback / Recurrent）

这 5 个都在「Topology concept = ✅」且「Biological circuit = ❌/◐」，说明它们是**拓扑形状/性质**，不是生物类型。

- graph structure 可自动计算 path / feedforward / feedback / recurrence / closed-loop 等 **topology feature**；
- 但这些 feature **不得单独创建或晋升 biological Circuit / Pathway**；
- 只有 Loop 还额外需要生物证据，才能从 graph cycle 升格为 biological loop。

### 2.2 两组「证据面」概念（StructuralCircuit / FunctionalCircuit）

两者在「Structural/Functional evidence」维度互斥，但在「Biological circuit」维度都是 ❌——因为它们描述的是**同一 circuit 的两个证据面**，不是两个类型。不能复制 ConnectionType 的三分。

> 注意：Structural / Functional 都属于 **circuit_basis / evidence_basis** 维度；`has_function` 是另一个独立维度，专门表达 Circuit 参与的认知/行为/生理 Function，与 structural/functional evidence basis 分离。

### 2.3 NetworkCircuit

在「Biological circuit」维度为 ❌（概念混合），且「Functional evidence」✅——它是 network 概念，不是 circuit 概念。**Network ≠ Circuit**。

## 3. 结论

- **没有任何一个候选在「Biological circuit = ✅」这一维度上成立**，故 **CircuitType V1 暂不定义任何正式子类**（CircuitType 保留为 reserved extension point，不是 owl:Nothing，也不是形式逻辑上的 empty class）。
- 5 个拓扑概念 → 未来 `topology_type` / `is_closed_loop` / `has_feedback` / `has_recurrence` 属性。
- 2 个证据概念 → 未来 `circuit_basis` / `evidence_basis`。
- 1 个网络概念 → 未来独立 `Network` Class。
- 1 个状态概念（UncertainCircuit）→ 未来 `status`（见 excluded_or_deferred_types.md）。
