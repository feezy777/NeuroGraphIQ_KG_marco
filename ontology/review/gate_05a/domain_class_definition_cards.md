# Gate 5A — Domain Class Definition Cards（最终 KEEP / ADD 类定义卡）· 第二轮修订

Ontology IRI: `https://neurographiq.org/ontology/macro96`
本轮状态: **仅方案，未写入正式 TTL**

每个最终 KEEP / ADD 类一张卡。Parent 均为「建议 OWL 父类」，本轮不实际写入。

---

## 模块 A — Neuroscience Domain

### 卡 1 — BrainRegion（KEEP，定义收紧）
- **Parent:** owl:Thing
- **定义:** 人脑空间中具有可定位、可区分区域身份的解剖/空间实体；边界/身份可依宏观解剖、细胞构筑、连接模式、功能特征或标准脑图谱定义；**单纯功能概念、统计激活簇、网络节点或分析结果本身不自动构成 BrainRegion**。
- **Include:** cortical area / cortical parcel / subcortical nucleus / hippocampal subfield / thalamic nucleus / cerebellar region / brainstem nucleus。
- **Exclude:** functional activation cluster / fMRI hotspot / network node / functional component（无独立空间脑区身份时）；Neuron/Axon/Synapse/DendriticSpine（CellularNeuralStructure）。

### 卡 2 — CellularNeuralStructure（ADD，RENAME←NeuralStructure）
- **Parent:** owl:Thing
- **定义:** 神经系统细胞或亚细胞尺度下具有物理结构身份的实体。
- **典型（仅示例，不建子类）:** Neuron / Axon / Dendrite / DendriticSpine / Synapse。
- **Exclude:** 过程（NeurobiologicalProcess）；宏观区域（BrainRegion）。

### 卡 3 — NeurobiologicalProcess（ADD，RENAME←NeuralProcess）
- **Parent:** owl:Thing
- **定义:** 发生于神经系统并涉及神经细胞、突触、神经组织或相关生物学变化的过程。
- **典型（仅示例）:** SynapticPruning / Neurogenesis / SynapticPlasticity。
- **Exclude:** 结构（CellularNeuralStructure）。

### 卡 4 — Connection（KEEP）
- **Parent:** owl:Thing
- **定义:** 两个脑区/神经系统节点之间的、已晋升 canonical 的连接实体（structural/functional/effective 由 ConnectionType 表达）。
- **注意:** 移除 Macro96 限定；Gate 2 科学语义冻结。

### 卡 5 — ConnectionType（KEEP，表示 BLOCKER）
- **Parent:** owl:Thing
- **定义:** 连接类型的受控词表类。
- **当前子类（临时保留，表示未决）:** StructuralConnection → Projection；FunctionalConnectivity；EffectiveConnectivity。
- **状态:** 科学语义冻结；OWL 表示 → Gate 5A.1（BLOCKER）。

### 卡 6 — Circuit（KEEP）
- **Parent:** owl:Thing
- **定义:** 由多个 BrainRegion 及其有组织 Connection 构成、具有生物学/结构/功能意义的统一神经单元（Gate 3 完整语义）。
- **注意:** 移除 Macro96 限定；Gate 3 语义冻结。

### 卡 7 — CircuitType（KEEP，reserved/未决）
- **Parent:** owl:Thing
- **定义:** 回路类型保留扩展点。
- **V1:** 无子类、无 individual；去留/表示 → Gate 5A.1。

### 卡 8 — Function（KEEP，上位类）
- **Parent:** owl:Thing
- **定义:** 脑区/回路执行的生物学/认知功能（宽泛：cognitive / sensory / motor / affective / autonomic / homeostatic）。
- **Child:** CognitiveFunction（仅此一个）。

### 卡 9 — CognitiveFunction（ADD）
- **Parent:** Function
- **定义:** 记忆、语言、注意、执行功能、决策等认知功能。
- **Exclude:** 感觉/运动/情感/自主/稳态功能。

### 卡 10 — Neurotransmitter（ADD，扩展节点）
- **Parent:** owl:Thing
- **定义:** 参与神经信号传递的化学信号分子类别/实体。
- **例:** dopamine / glutamate / GABA / serotonin / acetylcholine。

### 卡 11 — Receptor（ADD，扩展节点）
- **Parent:** owl:Thing
- **定义:** 结合神经递质/配体并介导信号转导的受体蛋白类别/实体。
- **例:** D1 / D2 / NMDA / AMPA。**禁止 subClassOf Neurotransmitter。**

### 卡 12 — Gene（ADD，扩展节点）
- **Parent:** owl:Thing
- **定义:** 与人脑结构/功能/疾病/神经递质系统相关的人类基因概念。
- **例:** APOE / DISC1。

### 卡 13 — Disease（ADD，轻量）
- **Parent:** owl:Thing
- **定义:** 神经/精神/神经退行性疾病与障碍（diagnosis/disorder concept）。
- **Exclude:** Symptom。

### 卡 14 — Symptom（ADD，轻量）
- **Parent:** owl:Thing
- **定义:** 疾病/障碍的临床表现。
- **Exclude:** Disease。

---

## 模块 B — Scientific Evidence / Provenance

### 卡 15 — ResearchStudy（ADD，RENAME←Study）
- **Parent:** owl:Thing
- **定义:** 一个科学研究、实验、观察、干预或数据分析活动，可产生一个或多个科学结果，并可能由一个或多个 Publication 报道。

### 卡 16 — Publication（KEEP）
- **Parent:** owl:Thing
- **定义:** 承载/报道研究成果的科学文献载体。

### 卡 17 — Evidence（KEEP）
- **Parent:** owl:Thing
- **定义:** 来源中支持、反驳或限定某 assertion 的具体证据单元。

### 卡 18 — EvidenceType（DEFER / REMODEL）
- **Parent:** owl:Thing（历史占位）
- **定义:** 历史 placeholder / reserved modeling concept；是否最终保留为 OWL Class、代表什么受控 category 未定。
- **状态:** Gate 4A 多轴模型优先；表示 → Evidence Formalization Gate / Gate 5A.1。
- **禁止:** 本轮重建 TracerEvidence / DiffusionMRIEvidence 等 hierarchy。

---

## 模块 C — Atlas / Integration

### 卡 19 — Atlas（KEEP）
- **定义:** 外部脑图谱/资源（Julich-Brain / Brainnetome / HCP）。

### 卡 20 — ExternalRegion（KEEP）
- **定义:** 外部 atlas/ontology 中的区域概念（映射前）。

### 卡 21 — RegionMapping（KEEP）
- **定义:** ExternalRegion 与 canonical BrainRegion 之间的映射记录/语义对象。

---

## 统计

- KEEP 12 + ADD 9 = 21 个领域概念落点（ResearchStudy 替换 Study；CellularNeuralStructure 替换 NeuralStructure；NeurobiologicalProcess 替换 NeuralProcess）。
- ADD 9 = CellularNeuralStructure、NeurobiologicalProcess、CognitiveFunction、Neurotransmitter、Receptor、Gene、Disease、Symptom、ResearchStudy。
- 唯一子类关系：`Function └─ CognitiveFunction`。
- EvidenceType 由 KEEP 改为 **DEFER / REMODEL**（不计入"冻结 KEEP"）。
- CircuitConnectionMembership 移入 Modeling / Reification 模块（见 governance 文档）。
