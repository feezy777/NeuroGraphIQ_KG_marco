# Gate 3A — CircuitType 科学分类方案（候选，待人工审查）

Ontology IRI: `https://neurographiq.org/ontology/macro96`
本轮状态: **仅方案，未写入正式 TTL**（`neurographiq_macro96_v1.ttl` 未修改）

---

## 0. 结论速览

| 项目 | 结论 |
|---|---|
| 推荐 CircuitType 子类数 | **0 个正式子类**（CircuitType 保留为 reserved extension point，非 owl:Nothing，也非形式逻辑 empty class） |
| `Circuit` 类 | 保持 Gate 1 单一 Class，不再展开子层级 |
| `CircuitType` 状态 | **reserved extension point in V1**（无子类、无 individual、当前不用于分类）；Ontology Freeze 再决定保留或删除 |
| 旧草案 9 个候选 | 全部 **REMOVE / REMODEL / DEFER**，无一 KEEP |
| 拓扑 / 证据 / 功能 / 状态 | 留待后续 Property / Relation Gate 建模 |
| 是否修改正式 TTL | **否** |

---

## 1. 核心判断：CircuitType 是否需要子类型？

**结论：不需要。**

理由：

1. **Circuit 是一个单元概念，而非一个「种类谱系」概念。** Connection 之所以需要分类型，是因为「脑区之间的关系」在物理/统计/因果三个正交维度上**本质不同**（Gate 2A）。但 Circuit 之间的差异，几乎全部落在：拓扑（前馈/反馈/闭环）、证据基础（结构/功能）、功能（记忆/运动/奖赏）、状态（proposed/confirmed）——这些**都是属性/关系维度，不是类型维度**。

2. **拓扑不是类型。** Pathway / Loop / Feedforward / Feedback / Recurrent 描述的是「circuit 长成什么样」，应建模为 topology 属性，而非 OWL Class。

3. **证据不是类型。** Structural / Functional 描述的是「这个 circuit 靠什么证据成立」，一个 circuit 可同时有结构证据 + 功能证据，不能互斥地当成类型（任务书 §十）。

4. **功能不是类型。** Memory / Motor / Reward 是 CircuitFunction，不是 CircuitType（任务书 §十四）。

5. **实例不是类型。** Papez / CSTC / mesolimbic 是 named circuit 实例，属于未来 Circuit ABox（任务书 §十五）。

6. **状态不是类型。** Uncertain 与 Gate 2A 的 UnknownConnection 是同类错误（任务书 §十二）。

---

## 2. RECOMMENDED CIRCUIT MODEL

```
Circuit                                    (Gate 1 已有根类)
   —— V1 暂不定义任何正式子类（reserved extension point）——

CircuitType（受控词表类）
   —— V1 reserved extension point：无子类、无 individual、当前不用于分类 ——
```

> **CircuitType 状态说明**：V1 中 `CircuitType` 是 **reserved extension point**——暂不定义任何正式子类、无 individual、当前不用于分类；它**不是 owl:Nothing，也不是形式逻辑上的 empty class**。是否最终保留或删除，留待 **Ontology Freeze** 阶段决定。

### 2.1 未来建模方向（本轮只分析，禁止新增 Property/Class）

```
Circuit
├── (future Property) has_region / has_connection / has_membership   — 组成
├── (future Property) has_function → Function                         — 功能（≠ 类型）
├── (future Property) topology_type                                   — feedforward / feedback / recurrent / loop
├── (future Property) is_closed_loop : boolean                        — 拓扑
├── (future Property) has_feedback / has_recurrence : boolean         — 拓扑
├── (future Property) circuit_basis / evidence_type                   — structural / functional（证据，≠ 类型）
└── (future Property) status / assertion_type / confidence            — 认识状态（≠ 类型）
```

> 上述 Property 本轮**禁止实际建立**。只是记录未来更科学的建模方式。`Pathway` 的独立实体方案标记为 **future REMODEL / DEFER**，本轮及 Gate 3B **禁止自行新增 Pathway OWL Class**。

---

## 3. 旧草案 9 个候选的裁定

| 旧草案概念 | 本质 | 裁定 | 去向 |
|---|---|---|---|
| Pathway | 开放有向链（路线） | **future REMODEL / DEFER** | 未来或独立 `Path`/`Pathway` 实体，非 CircuitType；本轮及 Gate 3B 禁止新增 Pathway OWL Class |
| Loop | 闭合拓扑 | **REMODEL** | 未来 `is_closed_loop` / `functional_loop` 属性 |
| FeedforwardCircuit | 无反馈开放 motif | **REMODEL** | 未来 `topology_type = feedforward` / connection role |
| FeedbackCircuit | 含反馈边 | **REMODEL** | 未来 `topology_type = feedback` / connection role |
| RecurrentCircuit | 复发连接 | **REMODEL** | 未来 `has_recurrence` 属性 |
| StructuralCircuit | 结构证据基础 | **REMOVE** | 用 `circuit_basis` / `evidence_type` 表达 |
| FunctionalCircuit | 功能证据基础 | **REMOVE** | 用 `circuit_basis` / `evidence_basis = functional` 表达 |
| NetworkCircuit | Network 概念 | **DEFER** | 未来独立 `Network` Class（非 Circuit 子类） |
| UncertainCircuit | 认识状态 | **REMOVE** | 用 `status` / `assertion_type` 表达 |

**KEEP：0 个。** 这是科学分析的自然结果，而非为了精简而精简。

---

## 4. 与 Gate 2A ConnectionType 的对照

| 维度 | ConnectionType（Gate 2B，已固化） | CircuitType（Gate 3A） |
|---|---|---|
| 是否有子类型 | 有（4 个） | **暂不定义正式子类**（reserved extension point） |
| 为什么 | 连接在物理/统计/因果上**本质三分类** | 回路差异落在属性/关系维度，非类型维度 |
| 拓扑建模 | 方向性（directed/reciprocal/direction_unknown）写在 comment | 未来 topology 属性 |

> **不要**简单把 ConnectionType 的 Structural / Functional / Effective 三分复制到 CircuitType（任务书 §十）。

---

## 5. 待人工审查的关键决策点

1. **CircuitType V1 无正式子类**：是否同意暂不定义任何 CircuitType 子类（保留为 reserved extension point，非 owl:Nothing，也非形式逻辑 empty class）？
2. **Pathway 独立实体**：是否同意 Pathway 作为未来独立 `Path` 概念（而非 Circuit 子类）？
3. **Network 独立 Class**：是否同意 Network 未来单独建类（而非 Circuit 子类）？
4. **拓扑/证据/功能/状态全部走 Property**：是否同意本轮不建立任何 Property，留待后续 Property Gate？

---

## 6. 涉及文件

- `circuit_definition.md` — Circuit 定义与边界
- `circuit_type_taxonomy_proposal.md`（本文件）
- `circuit_type_definition_cards.md` — 9 个候选的完整定义卡
- `circuit_type_boundary_matrix.md` — 边界矩阵
- `type_vs_topology.md` — CircuitType vs CircuitTopology 分析
- `excluded_or_deferred_types.md` — REMOVE / DEFER / REMODEL 明细
- `references.md` — 参考文献
- `review_checklist.md` — 审查清单
