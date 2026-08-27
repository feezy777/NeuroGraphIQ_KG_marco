# Gate 3A — Circuit 定义：什么才算神经回路（Circuit）

Ontology IRI: `https://neurographiq.org/ontology/macro96`
Version 背景: Gate 1（24 顶层类，含 `Circuit` / `CircuitType`）→ Gate 2B（ConnectionType 已固化）
本轮状态: **仅科学语义分析，未写入正式 TTL**

---

## 1. Circuit 的定义

### 1.1 Short Definition

**Circuit（神经回路）** = 由多个脑区及其有组织关系的 Connection 构成、并具备生物证据或功能解释的神经功能/结构单元。

### 1.2 Scientific Definition

一个 neural circuit 是一组相互连接的脑区，其 Connection 按一定组织关系构成一个连贯的**计算/功能单元**。General Circuit **不要求闭环**（只有 Loop / closed-loop topology 才以闭合为必要条件但不充分）；方向信息在科学语义需要且证据支持时记录。它由解剖或功能证据（或明确的功能解释）支持，但「功能解释」本身不足以使其成为 confirmed Circuit（见 §4）。

关键：**Circuit 是生物学/功能性概念，不是图论概念。**

### 1.3 Minimum Composition（Macro96 V1 curation policy，非普遍科学定义）

Scientific definition **不规定固定的 region 数量**。

Macro96 V1 curation policy 默认要求：
- **≥3 Macro96 BrainRegion + ≥2 Connection**（目的是避免把普通脑区对误收为 Circuit）。

但允许 **literature-reported exception**：
- 若权威文献明确将**双区域 reciprocal system** 报道为 circuit，可进入人工审核，不应由 ontology definition 自动排除。

> 这是 curation policy / 后续 validation rule 依据，**不是 universal science 的必要条件**，本轮不写入 OWL restriction。

### 1.4 Necessary Conditions（必要条件，与固定 region 数量无关）

1. 有多个脑区参与（数量由 curation policy 决定，非科学硬约束）；
2. 有多个 Connection 按一定**组织关系**（顺序/角色）排列；方向信息在科学语义需要且证据支持时记录；
3. 有**生物证据或功能解释**支撑其作为一个统一单元（confirmed circuit 需 reported / 人工认可的 circuit-level evidence，见 §4）。

### 1.5 Exclusion Criteria（排除条件）

- 一条 Connection（A→B）**不是** Circuit；
- 一组 reciprocal connection（A↔B）**默认不是** Circuit；但若权威文献明确报道为 circuit，可进入人工审核（literature-reported exception）；
- 仅凭图拓扑闭合的 cycle（A→B→C→A，无文献/功能支持）**不是** Circuit；
- 仅凭统计相关的 Network（如静息态网络）**不是** Circuit。

---

## 2. Circuit 与相邻概念的边界

### 2.1 Circuit vs Connection

| | Connection | Circuit |
|---|---|---|
| 粒度 | 两个脑区之间**一条**关系 | 多脑区 + 多连接的**单元** |
| 组成 | 1 source + 1 target | 多 region + 多 connection（curation 默认 ≥3+≥2，允许文献例外） |
| 语义 | 一条边 | 一个有组织、有功能/结构意义的整体 |

### 2.2 Circuit vs Path / Pathway

| | Path / Pathway | Circuit |
|---|---|---|
| 拓扑 | 开放式有向链（A→B→C→D） | 可闭环（Loop），也可开放（Pathway）——不要求闭环 |
| 本质 | 信号传递的**路线** | 计算/功能**单元** |
| 闭环要求 | 否 | 不要求闭环（仅 Loop topology 以闭合为必要条件） |

- **结论**：`A → B → C → D` 这种开放式有向链路**更准确应称 Pathway / Path**，不必然等于 Circuit。
- 只有当其具备「功能单元」意义 + 生物证据时，才可作为 Circuit。

### 2.3 Circuit vs Network

| | Network | Circuit |
|---|---|---|
| 尺度 | 大规模、分布式 | 较小、有向、组织化 |
| 定义基础 | 常为统计/功能连接（静息态） | 组织化 Connection + 拓扑 + 功能单元 |
| 例子 | Default Mode Network、Salience Network | Papez circuit、CSTC loop |

- **结论**：Network ≠ Circuit。不应把 brain network 自动转成 Circuit。

### 2.4 Circuit vs graph cycle

| | graph cycle | biological Circuit |
|---|---|---|
| 判定 | 图结构上的闭合（A→B→C→A） | 闭合拓扑 **+** 生物证据/功能解释 |
| 充分性 | 闭合即成立 | 对 Loop/closed-loop topology：闭合**必要但不充分**；general Circuit 不要求闭合 |

- **结论**：图论 cycle **不能直接等价**为 biological neural circuit。`A → B → C → A` 在图结构上构成 cycle，但不代表它是文献支持的 biological circuit。

---

## 3. Circuit 需要能回答的问题（后续正式 Circuit 的最低信息）

1. 有哪些脑区？
2. 有哪些 Connection？
3. Connection 的组织顺序/拓扑是什么？
4. 为什么这些 Connection 可视为同一 circuit？
5. 有什么文献或功能证据支持？

> 一个「数据库里随便找到的 3 条 Connection」不构成 Circuit。

---

## 4. Circuit 与证据的关系

Circuit 的证据**不能简单等于**「其所有 Connection 都存在」。需区分：

| 概念 | 含义 |
|---|---|
| **reported circuit evidence** | 文献明确报道这是一个 circuit |
| **composed / reconstructed circuit** | 由已确认 Connection 组合重建出的 circuit |
| **inferred circuit** | 由证据推断、但未经文献直接报道 |
| **hypothesis circuit** | 候选/假设性 circuit |

**收紧原则（canonical / confirmed circuit 的门槛）：**

- **Canonical / confirmed Circuit** 需要 **reported circuit evidence**，或**人工认可的权威 circuit-level evidence**。
- 由 Connection + topology + function reasoning 得到的结果，只能先作为 **composed / inferred / hypothesis circuit**，**不得**因为存在「功能解释」就直接晋升 confirmed Circuit。

> 上述边界由后续 assertion_type / Evidence Gate 正式建模，本轮仅给概念边界。

---

## 5. Circuit → Connection 反向推理边界（为后续留规则）

若论文明确报道 `A → B → C → A` 是一个 circuit，但数据库中缺失 `C → A`：

- 缺失 Connection 只能成为 **candidate / hypothesis / targeted-search target**；
- **不能**直接生成 confirmed Connection。

此原则在 Gate 3A 文档中记录，供后续 Evidence / Validation Gate 引用。
