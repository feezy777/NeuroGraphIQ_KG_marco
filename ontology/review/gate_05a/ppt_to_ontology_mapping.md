# Gate 5A — 老师 PPT 节点类型 → NeuroGraphIQ 映射矩阵 · 第二轮修订

Ontology IRI: `https://neurographiq.org/ontology/macro96`
本轮状态: **仅映射文档，未写入正式 TTL**

映射标记：**UNCHANGED** / **EXPANDED** / **SPLIT** / **REMODELED** / **ADDED**。

---

## 1. 主映射矩阵

| 老师 PPT 节点 | NeuroGraphIQ 推荐 Class | 映射标记 | 说明 |
|---|---|---|---|
| BrainRegion | BrainRegion | **UNCHANGED**（定义收紧） | 防 functional cluster / network node 误分类 |
| NeuralStructure（树突棘、突触修剪…） | CellularNeuralStructure + NeurobiologicalProcess | **SPLIT / REMODEL** | 树突棘→CellularNeuralStructure；突触修剪→NeurobiologicalProcess |
| Circuit | Circuit（+ CircuitType reserved） | **UNCHANGED** | 保留 Gate 3 裁定 |
| CognitiveFunction | Function └─ CognitiveFunction | **EXPANDED** | 不删 Function，扩为父子层级 |
| Neurotransmitter（神经递质/受体） | Neurotransmitter + Receptor | **SPLIT** | 递质与受体拆为两个独立类 |
| Disease | Disease | **ADDED**（与 Symptom SPLIT） | Disease ≠ Symptom |
| Gene | Gene | **ADDED**（扩展节点） | 非入口，不引入完整 GO |
| Symptom | Symptom | **ADDED**（与 Disease SPLIT） | clinical manifestation ≠ diagnosis |
| Study（文献/证据来源） | ResearchStudy + Publication + Evidence | **SPLIT** | 研究/文献/证据三分 |

---

## 2. 关键拆分详解

### 2.1 PPT「NeuralStructure（树突棘、突触修剪）」→ SPLIT / REMODEL

| 原始表述 | 科学归属 | 结论 |
|---|---|---|
| 树突棘（DendriticSpine） | **CellularNeuralStructure**（结构） | 改名/收窄 |
| 突触修剪（SynapticPruning） | **NeurobiologicalProcess**（过程） | 改名 |

> PPT 将「亚细胞结构」与「神经过程」混在同一节点，是**必须修正的科学错误**。同时 NeuralStructure 原义过宽（会与 BrainRegion 重叠），故 RENAME 为 CellularNeuralStructure。

### 2.2 PPT「神经递质 / 受体」→ SPLIT

| 原始表述 | 科学归属 |
|---|---|
| dopamine / glutamate / GABA | Neurotransmitter |
| D1 / D2 / NMDA / AMPA | Receptor |

> Receptor 不是 Neurotransmitter 子类。

### 2.3 PPT「Study（文献 / 证据来源）」→ SPLIT

| 原始表述 | 科学归属 |
|---|---|
| 研究/实验/分析活动 | **ResearchStudy** |
| 承载成果的文献 | **Publication** |
| 支持/反驳断言的具体证据单元 | **Evidence** |

### 2.4 PPT「CognitiveFunction」→ EXPANDED

- 不删除既有 `Function`；推荐 `Function └─ CognitiveFunction`。

---

## 3. PPT 隐含关系（本轮不建 Property，仅记录）

| PPT 关系 | 处理 |
|---|---|
| STRUCTURALLY_CONNECTED_TO / FUNCTIONALLY_CONNECTED_TO / PROJECTS_TO | → future_relation_candidates（与 Connection entity model 冲突待审） |
| PARTICIPATES_IN / MODULATES / INCREASES_RISK_OF | → future_relation_candidates |

---

## 4. 映射原则

1. PPT 节点是**候选起点**，非机械照抄模板。
2. 每节点问：结构 / 过程 / 实体 / 活动 / 载体 / 证据中的哪一类？
3. 已通过审查的 Connection / Circuit / Evidence 设计原则**优先于** PPT 表述。
4. 拆分优先于合并。
