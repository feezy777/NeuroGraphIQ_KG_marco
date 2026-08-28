# NeuroGraphIQ Human Brain Ontology — 核心概念学习指南

> 面向学习与 PPT 整理：每个概念只写「是什么 / 例子 / 容易和什么混」。

---

### BrainRegion / 脑区

- **是什么**：在人脑空间中可定位、可区分的解剖或标准脑图谱区域。
- **例子**：Hippocampus、CA1。
- **容易和什么混**：BrainRegion ≠ Circuit / Network / 单纯 activation cluster（激活簇不是脑区）。

### CellularNeuralStructure / 细胞与亚细胞神经结构

- **是什么**：神经系统细胞或亚细胞尺度的结构实体。
- **例子**：Neuron、DendriticSpine。
- **容易和什么混**：≠ BrainRegion（细胞结构 vs 宏观区域）。

### NeurobiologicalProcess / 神经生物学过程

- **是什么**：发生在神经系统中的生物学过程。
- **例子**：SynapticPruning、SynapticPlasticity。
- **容易和什么混**：≠ CellularNeuralStructure（过程 vs 结构）。

### Connection / 连接

- **是什么**：两个脑区之间有明确神经科学语义的关联（结构 / 功能 / 有效）。
- **例子**：CA1–mPFC connection、V1–V2 connection。
- **容易和什么混**：≠ Circuit（连接是边，回路是由边组织的单元）。

### StructuralConnection / 结构连接

- **是什么**：两脑区之间存在物理/神经解剖通路的连接。
- **例子**：corticocortical anatomical connection、thalamocortical structural connection。

### Projection / 投射

- **是什么**：有明确 source→target 和轴突投射语义的结构连接。
- **例子**：CA1 projects to mPFC、thalamus projects to cortex。
- **容易和什么混**：DTI tractography 单独不能判定投射方向。

### FunctionalConnectivity / 功能连接

- **是什么**：两脑区神经活动的统计依赖/相关/时间同步。
- **例子**：PCC 与 mPFC 的静息态 fMRI 相关。
- **容易和什么混**：≠ StructuralConnection（功能相关不意味着结构通路）。

### EffectiveConnectivity / 有效连接

- **是什么**：模型/实验推断的脑区之间有向影响。
- **例子**：DCM 估计的 A→B 影响。
- **容易和什么混**：因果解释依赖方法/模型/实验设计。

### Circuit / 神经回路

- **是什么**：多个脑区及其有组织连接形成的、有生物学/结构/功能意义的神经单元。
- **例子**：Papez circuit、mesolimbic dopamine circuit。
- **容易和什么混**：≠ graph cycle；一般回路不要求闭合环路。

### Function / 功能

- **是什么**：脑区或回路承担的神经生物学功能（比认知功能更广）。
- **例子**：visual processing、motor control。

### CognitiveFunction / 认知功能

- **是什么**：与认知活动相关的功能。
- **例子**：WorkingMemory、Language。
- **容易和什么混**：⊂ Function（Function 更宽，含感觉/运动/情感/自主/稳态）。

### Neurotransmitter / 神经递质

- **是什么**：参与神经细胞间化学信号传递的化学信号分子。
- **例子**：Dopamine、Glutamate。

### Receptor / 受体

- **是什么**：识别并响应神经递质/信号分子的受体实体。
- **例子**：D2 receptor、NMDA receptor。
- **容易和什么混**：≠ Neurotransmitter（递质是分子，受体是蛋白）。

### Gene / 基因

- **是什么**：与人脑结构/功能/疾病/神经过程相关的人类基因。
- **例子**：APOE、DISC1。

### Disease / 疾病

- **是什么**：影响神经系统结构/功能/行为的疾病或精神障碍。
- **例子**：Alzheimer disease、Parkinson disease。

### Symptom / 症状

- **是什么**：疾病/异常状态产生的临床表现。
- **例子**：Memory impairment、Hallucination。
- **容易和什么混**：≠ Disease（症状是表现，疾病是诊断）。

### ResearchStudy / 研究

- **是什么**：科学研究/实验/观察/干预/数据分析活动。
- **例子**：一项 fMRI study、一项 clinical cohort study。
- **容易和什么混**：≠ Publication（研究是活动，文献是载体）。

### Publication / 文献

- **是什么**：报道研究结果的论文或正式科学文献。
- **例子**：PubMed paper、journal article。
- **容易和什么混**：≠ Evidence（文献可含多条证据）。

### Evidence / 证据

- **是什么**：来源中支持/反驳/限定某知识断言的具体证据单元。
- **例子**：论文报道 A projects to B 的实验结果。
- **容易和什么混**：≠ Publication；遵循多轴模型（不做单一 EvidenceType）。

### Atlas / 脑图谱

- **是什么**：提供人脑空间划分/区域定义/坐标参考的标准图谱资源。
- **例子**：Julich-Brain、Brainnetome Atlas。

### ExternalRegion / 外部脑区

- **是什么**：外部图谱/本体定义、尚未 canonicalization 的脑区概念。
- **例子**：某 Julich-Brain parcel、某 Brainnetome parcel。
- **容易和什么混**：≠ canonical BrainRegion。

### RegionMapping / 脑区映射

- **是什么**：记录外部脑区与 canonical 脑区对应关系的映射实体。
- **例子**：Brainnetome region X → canonical mPFC。

### CircuitConnectionMembership / 回路连接成员关系

- **是什么**：某一连接在某一回路中的成员身份与上下文。
- **例子**：Connection C001 在 Circuit A 中是第 2 步、在 Circuit B 中是第 5 步。
- **容易和什么混**：不是 Connection 本身，而是 Connection×Circuit 的成员关系。
