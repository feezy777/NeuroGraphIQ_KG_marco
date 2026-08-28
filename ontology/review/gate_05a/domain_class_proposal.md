# Gate 5A — Domain Class Proposal（核心候选领域类逐项裁定）· 第二轮修订

Ontology IRI: `https://neurographiq.org/ontology/macro96`
本轮状态: **仅方案，未写入正式 TTL**

---

## 0. 裁定总表（按五模块）

| # | Canonical Name | 中文 | 裁定 | 模块 | 备注 |
|---|---|---|---|---|---|
| 1 | BrainRegion | 脑区 | **KEEP（定义收紧）** | A | 见 §1 |
| 2 | CellularNeuralStructure | 细胞与亚细胞神经结构 | **ADD（RENAME←NeuralStructure）** | A | 见 §2 |
| 3 | NeurobiologicalProcess | 神经生物学过程 | **ADD（RENAME←NeuralProcess）** | A | 见 §3 |
| 4 | Connection | 连接 | **KEEP（去 Macro96）** | A | Gate 2 语义冻结 |
| 5 | ConnectionType | 连接类型 | **KEEP（表示 BLOCKER）** | A | Gate 2 语义冻结；表示→Gate 5A.1 |
| 6 | Circuit | 回路 | **KEEP（去 Macro96）** | A | Gate 3 语义冻结 |
| 7 | CircuitType | 回路类型 | **KEEP（reserved/未决）** | A | →Gate 5A.1 |
| 8 | Function | 功能 | **KEEP（上位类）** | A | 见 §8 |
| 9 | CognitiveFunction | 认知功能 | **ADD** | A | Function 子类 |
| 10 | Neurotransmitter | 神经递质 | **ADD（扩展节点）** | A | 见 §10 |
| 11 | Receptor | 受体 | **ADD（扩展节点）** | A | 见 §11 |
| 12 | Gene | 基因 | **ADD（扩展节点）** | A | 见 §12 |
| 13 | Disease | 疾病 | **ADD（轻量）** | A | 见 §13 |
| 14 | Symptom | 症状 | **ADD（轻量）** | A | 见 §14 |
| 15 | ResearchStudy | 研究 | **ADD（RENAME←Study）** | B | 见 §15 |
| 16 | Publication | 文献 | **KEEP** | B | — |
| 17 | Evidence | 证据 | **KEEP** | B | Gate 4A |
| 18 | EvidenceType | 证据类型 | **DEFER / REMODEL** | B | 见 §18 |
| 19 | Atlas | 脑图谱 | **KEEP** | C | — |
| 20 | ExternalRegion | 外部脑区 | **KEEP** | C | — |
| 21 | RegionMapping | 脑区映射 | **KEEP** | C | — |

> 模块：A=Neuroscience Domain；B=Scientific Evidence/Provenance；C=Atlas/Integration；D=Modeling/Reification（CircuitConnectionMembership，见 governance 与 modeling 文档）；E=Governance（见 governance_class_review.md）。

---

## 1. BrainRegion — KEEP（定义收紧）

- **Canonical Name:** BrainRegion
- **中文:** 脑区
- **裁定:** KEEP（定义收紧，防误分类）
- **定义（修订）:** "BrainRegion 是在人脑空间中具有可定位、可区分区域身份的解剖/空间实体，其边界或身份可依据宏观解剖、细胞构筑、连接模式、功能特征或标准脑图谱定义；**单纯的功能概念、统计激活簇、网络节点或分析结果本身不自动构成 BrainRegion**。"
- **Ontology Role:** 核心锚点 + 知识发现主入口。
- **Parent:** owl:Thing。
- **Child:** 本轮不建。
- **Inclusion:** 有 spatial / anatomical regional identity 的人脑区域。
- **Exclusion:** functional activation cluster / fMRI hotspot / network node / functional component（除非独立具备空间脑区身份）；Neuron/Axon/Synapse（→CellularNeuralStructure）。
- **Positive Example:** cortical area、cortical parcel、subcortical nucleus、hippocampal subfield、thalamic nucleus、cerebellar region、brainstem nucleus。
- **Counterexample:** 某 task 的 activation cluster（无独立空间脑区身份）。
- **Boundary:** ≠ CellularNeuralStructure（宏观/中观区域 vs 细胞/亚细胞结构）；≠ functional activation cluster；≠ network node（除非独立定义为空间脑区）；≠ ExternalRegion / Atlas。
- **是否适合 Human Brain V1:** ✅ 核心。
- **PPT:** ✅；科学修正：✅（收紧"功能定义"）。

## 2. CellularNeuralStructure — ADD（RENAME←NeuralStructure）

- **Canonical Name:** CellularNeuralStructure（推荐，评估见 revision_summary §2）
- **中文:** 细胞与亚细胞神经结构（或 神经细胞结构）
- **裁定:** ADD（第一轮 NeuralStructure 定义过宽，与本轮 RENAME + REMODEL 收窄）
- **定义:** "神经系统细胞或亚细胞尺度下具有物理结构身份的实体。"
- **Parent:** owl:Thing。
- **Child:** 本轮**不建**子类（Neuron / Axon / Dendrite / DendriticSpine / Synapse 仅作为典型示例列举）。
- **Inclusion:** 细胞/亚细胞尺度结构实体。
- **Exclusion:** 过程（→NeurobiologicalProcess）；宏观区域（→BrainRegion）。
- **Positive Example:** DendriticSpine（树突棘）。
- **Counterexample:** SynapticPruning（→NeurobiologicalProcess）；PFC（→BrainRegion）。
- **Boundary:** **BrainRegion ≠ CellularNeuralStructure**（宏观/中观区域 vs 细胞/亚细胞结构）。
- **是否适合 Human Brain V1:** ✅（轻量顶层）。
- **PPT:** ✅（NeuralStructure 节点）；科学修正：✅ **SPLIT/REMODEL**。

## 3. NeurobiologicalProcess — ADD（RENAME←NeuralProcess）

- **Canonical Name:** NeurobiologicalProcess
- **中文:** 神经生物学过程
- **裁定:** ADD（第一轮 NeuralProcess 语义偏宽，改名为避免误解为 neural computation / signal processing）
- **定义:** "发生于神经系统并涉及神经细胞、突触、神经组织或相关生物学变化的过程。"
- **Parent:** owl:Thing。
- **Child:** 本轮不建（SynapticPruning / Neurogenesis / SynapticPlasticity 仅示例）。
- **Inclusion:** 神经系统的生物学过程/事件。
- **Exclusion:** 结构（→CellularNeuralStructure）。
- **Positive Example:** SynapticPruning（突触修剪）。
- **Counterexample:** DendriticSpine（→CellularNeuralStructure）。
- **Boundary:** **CellularNeuralStructure ≠ NeurobiologicalProcess**。
- **是否适合 Human Brain V1:** ✅（轻量顶层）。
- **PPT:** ✅（隐含于 NeuralStructure）；科学修正：✅ **SPLIT**。

## 4. Connection — KEEP（去 Macro96）

- 保留；移除 Macro96 限定，泛化人脑。Gate 2 科学语义冻结。
- **Parent:** owl:Thing。**Child:** 不建（类型由 ConnectionType 表达）。
- 边界：≠ Circuit；≠ ConnectionCandidate；≠ ConnectionType（实体 vs 类型）。

## 5. ConnectionType — KEEP（表示 BLOCKER）

- 科学语义（Structural / Projection / Functional / Effective）**冻结**。
- OWL 表示（Class hierarchy vs controlled vocabulary）**BLOCKER**，入 Gate 5A.1。
- 本轮**不改变**当前 Gate 2 hierarchy，也不假装其已最终冻结。

## 6. Circuit — KEEP（去 Macro96）

- 保留 Gate 3 科学语义；移除 Macro96 限定；发现路线核心对象。

## 7. CircuitType — KEEP（reserved / 未决）

- 无子类、无 individual；去留/表示四选一入 Gate 5A.1。

## 8. Function — KEEP（上位类）

- 宽定义覆盖 cognitive / sensory / motor / affective / autonomic / homeostatic。
- **Child:** CognitiveFunction（仅此一个子类；不建其他 subtype）。

## 9. CognitiveFunction — ADD（Function 子类）

- memory / language / attention / executive function / decision making。
- **Parent:** Function。

## 10. Neurotransmitter — ADD（扩展节点）

- "参与神经信号传递的化学信号分子类别/实体"（dopamine / glutamate / GABA / serotonin / acetylcholine）。
- **扩展节点，非第一阶段入口**；不导入完整 ChEBI。

## 11. Receptor — ADD（扩展节点）

- "结合神经递质/配体并介导信号转导的受体蛋白类别/实体"（D1 / D2 / NMDA / AMPA）。
- **禁止** Receptor subClassOf Neurotransmitter；不导入完整 IUPHAR。

## 12. Gene — ADD（扩展节点）

- "与人脑结构/功能/疾病/神经递质系统相关的人类基因概念"（APOE / DISC1）。
- 扩展节点，非入口；不导入完整 Gene Ontology。

## 13. Disease — ADD（轻量）

- "神经/精神/神经退行性疾病与障碍（diagnosis/disorder concept）"。
- ≠ Symptom；不建 has_symptom 等 Property。

## 14. Symptom — ADD（轻量）

- "疾病/障碍的临床表现"（memory impairment / hallucination / tremor）。
- ≠ Disease。

## 15. ResearchStudy — ADD（RENAME←Study）

- **Canonical Name:** ResearchStudy
- **中文:** 研究
- **定义:** "一个科学研究、实验、观察、干预或数据分析活动，可产生一个或多个科学结果，并可能由一个或多个 Publication 报道。"
- **Parent:** owl:Thing。
- **Boundary:** ResearchStudy ≠ Publication ≠ Evidence（三分）。

## 16. Publication — KEEP

- "承载/报道研究成果的科学文献载体。"
- ≠ ResearchStudy；≠ Evidence。

## 17. Evidence — KEEP

- "来源中支持、反驳或限定某 assertion 的具体证据单元。"
- Gate 4A 多轴语义；≠ Publication；≠ EvidenceCandidate。

## 18. EvidenceType — DEFER / REMODEL

- Gate 4A 已明确 Evidence 具有多正交维度（source / acquisition modality / analysis method / intervention method / directness / strength / confidence）。
- EvidenceType **不能再视为单一冻结的科学分类**。
- **裁定：DEFER / REMODEL**。当前继续作为历史 placeholder / reserved modeling concept；是否最终保留为 OWL Class、代表什么受控 category，留 Evidence Formalization Gate。
- **禁止**本轮重建 `EvidenceType └─ TracerEvidence / DiffusionMRIEvidence ...` 等 hierarchy。
- **Gate 4A 多轴 Evidence 模型优先于旧单一 EvidenceType taxonomy。**

## 19-21. Atlas / ExternalRegion / RegionMapping — KEEP

- 语义与第一轮一致（见 definition_cards）。

---

## 附：全局 Class vs Individual Policy（TBox / ABox）

- **TBox（Class）** = 类别/概念类型：BrainRegion、Gene、Disease、Symptom、Neurotransmitter、Receptor、Function、Atlas、Publication、Evidence、Connection、Circuit…
- **ABox（Individual）** = 真实 canonical knowledge concept：Hippocampus、CA1、APOE、AlzheimerDisease、Dopamine、D2Receptor、WorkingMemory、JulichBrainAtlas、具体 Publication、具体 Evidence。
- 例：`BrainRegion` 是 Class，`Hippocampus` 是 Individual；`Gene` 是 Class，`APOE` 是 Individual；`Disease` 是 Class，`AlzheimerDisease` 是 Individual；`Neurotransmitter` 是 Class，`Dopamine` 是 Individual。
- 这是 NeuroGraphIQ lightweight ontology 的**默认建模策略**。
- 外部 ontology（MONDO / HPO / ChEBI / Uberon）可能把 biomedical concept 建模为 OWL Class，**NGIQ 不必复制其 Class semantics**；NGIQ canonical concept = Individual，用未来 mapping（external_id / source ontology / exactMatch / closeMatch / mapped_to）表达对应。**禁止未经审查用 owl:equivalentClass 跨 NGIQ Individual 与外部 OWL Class。**
