# Gate 3A — 排除（REMOVE）/ 暂缓（DEFER）/ 重塑（REMODEL）类型

本文件记录 Gate 3A 对 9 个旧候选 CircuitType 的完整裁定。

---

## 1. REMOVE（不建类型，用状态/证据属性表达）

| 概念 | 为什么不是 CircuitType | 正确归属 |
|---|---|---|
| **StructuralCircuit** | 描述 circuit 的「结构证据面」，不是「种类」；同一 circuit 可同时有结构+功能证据 | 未来 `circuit_basis` / `evidence_basis = structural` |
| **FunctionalCircuit** | 描述 circuit 的「功能证据面」，不是「种类」；属于 circuit evidence/basis 维度（非 has_function） | 未来 `circuit_basis` / `evidence_basis = functional` |
| **UncertainCircuit** | 「不确定」是认识状态，与 Gate 2A 的 Unknown/UncertainConnection 是同类错误 | 未来 `status` / `assertion_type` / `confidence` |

> 特别注意：不要复制 ConnectionType 的 Structural / Functional / Effective 三分到 CircuitType（任务书 §十）。

---

## 2. REMODEL（概念真实，但属于拓扑/连接性质，应重塑为属性或独立实体）

| 概念 | 重塑去向 | 说明 |
|---|---|---|
| **Pathway** | 未来或独立 `Path`/`Pathway` 实体（future REMODEL / DEFER） | 开放有向链是「路线」，不是 Circuit 子类；本轮及 Gate 3B 禁止新增 Pathway OWL Class |
| **Loop** | 未来 `is_closed_loop` / `functional_loop` 属性 | 闭合拓扑；需生物证据才升格为 functional loop |
| **FeedforwardCircuit** | 未来 `topology_type = feedforward` / connection role | 无反馈前向 motif，不是类型 |
| **FeedbackCircuit** | 未来 `topology_type = feedback` / connection role | 反馈是调节角色，不是类型 |
| **RecurrentCircuit** | 未来 `has_recurrence` 属性 | 复发连接性质；A↔B 只是 reciprocal connections |

---

## 3. DEFER（暂缓，未来再议）

| 概念 | 说明 | 去向 |
|---|---|---|
| **NetworkCircuit** | Network 与 Circuit 是不同概念，不应混合 | 未来独立 `Network` Class（非 Circuit 子类） |

---

## 4. 裁定总表

| 概念 | 裁定 |
|---|---|
| Pathway | **REMODEL / DEFER**（→ future 独立 Path 实体；禁止本轮/Gate 3B 新增） |
| Loop | **REMODEL**（→ is_closed_loop 属性） |
| FeedforwardCircuit | **REMODEL**（→ topology_type） |
| FeedbackCircuit | **REMODEL**（→ has_feedback） |
| RecurrentCircuit | **REMODEL**（→ has_recurrence） |
| StructuralCircuit | **REMOVE**（→ circuit_basis） |
| FunctionalCircuit | **REMOVE**（→ circuit_basis / evidence_basis） |
| NetworkCircuit | **DEFER**（→ 独立 Network Class） |
| UncertainCircuit | **REMOVE**（→ status） |

**KEEP：0。**

---

## 5. NOT_CIRCUIT_TYPES（明确清单，供后续分类提示词使用）

以下概念**不应成为 CircuitType**：

| 概念 | 为什么不是 CircuitType | 正确归属 |
|---|---|---|
| **unknown / uncertain / candidate / inferred**（状态） | 认识状态，非生物类型 | status / assertion_type / confidence |
| **network**（网络） | 与 Circuit 是不同概念 | 独立 Network Class |
| **function 名**（memory / motor / reward / emotion） | 功能，非类型 | has_function → Function |
| **disease 名**（PD / AD 相关回路） | 疾病关联，非类型 | 疾病关联属性 |
| **named circuits**（Papez / CSTC / mesolimbic） | 实例，非类型 | Circuit ABox（individual） |
| **evidence 方法**（tracer / fMRI / DTI） | 证据模态，非类型 | EvidenceType / evidence 属性 |
| **topology-only**（loop / feedforward / feedback / recurrent） | 拓扑形状/性质，非类型 | topology 属性 |

---

## 6. 与旧 schema 的兼容性对照（仅参考）

旧系统 `circuit_type` 取值混入了多个正交维度：

| 旧值 | 维度 | 本轮裁定 |
|---|---|---|
| `sensory_circuit` / `motor_circuit` / `limbic_circuit` / `cognitive_control_circuit` | 功能 | → has_function，非类型 |
| `default_mode_related` / `salience_related` | 网络 | → 独立 Network Class，非类型 |
| `memory_related` / `reward_related` / `language_related` / `attention_related` | 功能 | → has_function，非类型 |
| `network` / `pathway` / `reflex` / `functional_loop` | 拓扑/结构 | → topology 属性 / 独立实体，非类型 |
| `feedforward` / `feedback`（role） | 拓扑/角色 | → connection role / topology，非类型 |
| `uncertain` / `uncertain_circuit` / `unknown` | 状态 | → status，非类型 |
| `closed_loop`（boolean） | 拓扑 | → is_closed_loop 属性 |

> 旧字段仅为兼容性参考。Gate 3A 重新定义 Circuit 语义，不因旧系统存在某值就保留某类型。
