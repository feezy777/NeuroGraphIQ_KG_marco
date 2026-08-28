# Gate 5A — 第二轮修订摘要（Revision Summary）

Ontology IRI: `https://neurographiq.org/ontology/macro96`
修订时间: 2026-08-28
修订性质: 人工审查后第二轮修订（Round 2），形成 **Gate 5A Final Review Candidate**
本轮状态: **仅 review 文档，未修改正式 TTL**

---

## 0. 人工审查结论回顾

| 维度 | 结论 |
|---|---|
| 科学范围 | 基本通过 |
| 顶层架构 | 有条件通过 |
| 正式写入 TTL | 暂缓 |

---

## 1. 本轮全部修订清单

| # | 修订项 | 第一轮 | 第二轮 | 性质 |
|---|---|---|---|---|
| 1 | 分层粒度 | Domain / Governance 二分 | 五模块（Neuroscience / Evidence / Atlas / Modeling / Governance） | 重构 |
| 2 | NeuralStructure | ADD（顶层） | **RENAME → CellularNeuralStructure** | 改名/收窄 |
| 3 | NeuralProcess | ADD（顶层） | **RENAME → NeurobiologicalProcess** | 改名 |
| 4 | BrainRegion 定义 | 过宽（含"功能定义"） | 收紧，防 functional cluster / network node 误分类 | 重塑 |
| 5 | Study | ADD | **RENAME → ResearchStudy** | 改名 |
| 6 | EvidenceType | KEEP | **DEFER / REMODEL**（Gate 4A 多轴优先） | 重审 |
| 7 | CircuitConnectionMembership | DEFER | **KEEP AS MODELING / REIFICATION（formalization DEFER）** | 升级 |
| 8 | ConnectionAssessment | REMOVE | 继续 **REMOVE**（确认） | 确认 |
| 9 | ConceptDefinition | DEFER | **REMOVE**（推荐，理由见 governance review） | 决策 |
| 10 | Class vs Individual | 仅提 Neurotransmitter/Receptor/Gene | **全局 TBox/ABox policy**（canonical concept = Individual） | 新增策略 |
| 11 | 外部 ontology 语义 | 未明确 | 明确**不复制外部 Class semantics，不用 owl:equivalentClass 跨 Individual/Class** | 新增 |
| 12 | ConnectionType OWL 表示 | DEFER | **BLOCKER**，双方案，入 Gate 5A.1 | 升级 |
| 13 | CircuitType | reserved | 入 Gate 5A.1（保留/删除/受控词表/子类四选一） | 明确 |
| 14 | EvidenceType 表示 | 不建 hierarchy | 入 Gate 5A.1 / Evidence Formalization | 明确 |
| 15 | Connection entity vs direct edge | DEFER | 记录为 storage vs projection，入 Gate 5A.1 / Property Gate | 明确 |
| 16 | Ontology IRI 遗留 | 未提 | 新增 ISSUE：IRI 仍含 macro96 | 新增 |
| 17 | Gate 3B comment 遗留 | 未提 | 新增：comment 含 legacy Macro96 curation 文本 | 新增 |

---

## 2. 关键命名裁决

| 旧名 | 新名（推荐） | 中文 | 理由 |
|---|---|---|---|
| NeuralStructure | **CellularNeuralStructure** | 细胞与亚细胞神经结构 | 明确 cellular/subcellular 尺度，避免与 BrainRegion（宏观区域）语义重叠 |
| NeuralProcess | **NeurobiologicalProcess** | 神经生物学过程 | 明确 biological process，避免误解为 neural computation / signal processing |
| Study | **ResearchStudy** | 研究 | 明确"科学研究活动"，与 Publication / Evidence 严格区分 |

命名评估（NeuralStructure）：**CellularNeuralStructure** 优于 **NeuralCellularStructure**——
- "Cellular" 作为尺度限定词前置，读作"细胞尺度的神经结构"，符合 OBO 命名习惯（限定语 + 中心名词，如 GO 的 Cellular Component）；
- "NeuralCellularStructure" 语序别扭，可被误读为"神经-细胞结构"（主体漂移）；
- 与未来同级 `NeurobiologicalProcess`（尺度中性）形成对照。

---

## 3. 修订后的逻辑模块（非 OWL hierarchy）

见 `proposed_class_hierarchy.md`。五模块：A Neuroscience Domain / B Scientific Evidence & Provenance / C Atlas & Integration / D Modeling & Reification / E Knowledge Production & Governance。**本轮不建任何模块父类。**

---

## 4. 修订后的类统计口径

| 统计项 | 数量 |
|---|---|
| 当前正式 TTL Class | 28（24 顶层 + 4 ConnectionType 子类） |
| Neuroscience Domain 推荐类 | 14 |
| Evidence / Provenance 推荐类 | 4（含 EvidenceType[REMODEL]） |
| Atlas / Integration 推荐类 | 3 |
| Modeling / Reification 推荐类 | 1 |
| Governance 推荐类（KEEP） | 9 |
| REMOVE | 2（ConnectionAssessment、ConceptDefinition） |
| DEFER / REMODEL（表示形式未定） | EvidenceType；ConnectionType / CircuitType 表示 → Gate 5A.1 |

> 不再沿用第一轮"Domain Class 总数 25"口径。ConnectionType 的 4 个子类仍计入 current formal state，但在 future proposed state 标为 **pending Gate 5A.1 modeling decision**。

---

## 5. 尚未解决、需 Gate 5A.1 决定的 BLOCKER

- ConnectionType 的 OWL Class vs controlled-vocabulary Individual（**BLOCKER**，双方案见 `modeling_issues.md`）。
- CircuitType 去留与表示。
- EvidenceType 最终表示形式（Gate 4A 多轴模型优先）。
- 在 Gate 5A.1 通过之前，**禁止建立 ObjectProperty**。

---

## 6. 保持冻结的科学语义（不受本轮影响）

- **Gate 2** ConnectionType 科学语义（Structural / Projection / Functional / Effective）**不变**；只讨论 OWL 表示，不重新讨论其科学存在性。
- **Gate 3** Circuit 科学语义（not graph cycle / 不要求 closed loop / circuit-level evidence / missing edge only candidate）**不变**。
- **Gate 4A** Evidence 多轴模型（modality / analysis / intervention / derivation / epistemic / lifecycle / review / provenance）**不变**，并**优先于**旧单一 EvidenceType taxonomy。
