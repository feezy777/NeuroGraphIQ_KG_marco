# Gate 5A — Scientific Boundaries（关键概念边界）· 第二轮修订

Ontology IRI: `https://neurographiq.org/ontology/macro96`
本轮状态: **仅记录，未写入正式 TTL**

---

## 1. 核心边界清单

| 边界 | 说明 |
|---|---|
| **BrainRegion ≠ CellularNeuralStructure** | 宏观/中观区域 vs 细胞/亚细胞结构 |
| **CellularNeuralStructure ≠ NeurobiologicalProcess** | 结构 vs 过程 |
| **BrainRegion ≠ functional activation cluster** | 区域需 spatial/anatomical regional identity |
| **BrainRegion ≠ network node**（除非独立定义为空间脑区） | 网络节点 ≠ 空间脑区 |
| **Connection ≠ Circuit** | 边 vs 由边组织的单元 |
| **Circuit ≠ Network** | 生物学/功能组织单元 vs 松散网络 |
| **Function ≠ CognitiveFunction** | Function 更宽（认知/感觉/运动/情感/自主/稳态） |
| **Neurotransmitter ≠ Receptor** | 化学信号分子 vs 受体蛋白 |
| **Gene ≠ Neurotransmitter** | 基因 vs 化学分子 |
| **Disease ≠ Symptom** | diagnosis/disorder vs clinical manifestation |
| **ResearchStudy ≠ Publication** | 研究活动 vs 文献载体 |
| **Publication ≠ Evidence** | 文献 vs 证据单元 |
| **Evidence ≠ EvidenceCandidate** | 已验证证据 vs 待验证候选（Gate 4A） |
| **EvidenceType ≠ evidence modality necessarily** | EvidenceType 表示未定；多轴模型优先 |
| **Domain knowledge ≠ Governance record** | 科学实体 vs 知识生产过程 |
| **reported ≠ inferred** | derivation_type（Gate 4A） |
| **candidate ≠ hypothesis** | lifecycle_status vs epistemic_status（Gate 4A） |
| **review_status ≠ derivation_type** | 审核进展 vs 产生方式（Gate 4A） |
| **ConnectionType ontology class ≠ automatically valid property value** | Class 与 controlled vocabulary value 的语义鸿沟（BLOCKER，Gate 5A.1） |

---

## 2. 每个边界的判定标准

### 2.1 BrainRegion vs CellularNeuralStructure

- BrainRegion = 人脑空间中**宏观/中观**的区域实体。
- CellularNeuralStructure = **细胞/亚细胞**尺度结构实体。
- 判据：尺度 + 是否区域身份。若 NeuralStructure 定义过宽，会吞掉 BrainRegion。

### 2.2 CellularNeuralStructure vs NeurobiologicalProcess

- 结构：占据空间、可指认实体（DendriticSpine）。
- 过程：随时间发生（SynapticPruning）。

### 2.3 BrainRegion vs functional activation cluster / network node

- BrainRegion 必须有 spatial/anatomical regional identity。
- task activation cluster / fMRI hotspot / network node / functional component **不自动**构成 BrainRegion。
- 判据：能否独立定位为空间脑区。

### 2.4 Connection vs Circuit vs Network

- Connection = 两节点连接断言。
- Circuit = 有组织连接单元 + circuit-level 意义/证据。
- Network = 图论/系统层连接集合（V1 不建）。

### 2.5 Function vs CognitiveFunction

- Function ⊃ CognitiveFunction。

### 2.6 Neurotransmitter vs Receptor vs Gene

- Neurotransmitter：dopamine/glutamate/GABA（小分子）。
- Receptor：D1/D2/NMDA/AMPA（蛋白）。
- Gene：APOE/DISC1（核酸序列概念）。

### 2.7 Disease vs Symptom

- Disease：诊断/障碍。
- Symptom：临床表现。本轮不建 has_symptom。

### 2.8 ResearchStudy vs Publication vs Evidence

- ResearchStudy：研究/实验/分析活动。
- Publication：承载成果的文献。
- Evidence：支持/反驳/限定 assertion 的证据单元。
- 链（未来）：ResearchStudy → reported in Publication → provides Evidence → supports assertion。

### 2.9 EvidenceType vs evidence modality

- EvidenceType 是历史占位；Gate 4A 多轴模型（modality / analysis / intervention / directness / strength / confidence）优先。
- 不把 EvidenceType 当作已冻结单一分类。

---

## 3. 禁止的错误合并 / 父子关系（防回归）

- 不得把 DendriticSpine 与 SynapticPruning 归为一类。
- 不得把 Receptor 归入 Neurotransmitter。
- 不得把 Symptom 归入 Disease。
- 不得把 Publication 归入 ResearchStudy。
- 不得把 Evidence 归入 Publication。
- 不得把 candidate 当作 assertion_type。
- 不得把 review_status 当作 derivation_type。
- 不得把 CellularNeuralStructure 与 BrainRegion 混为一类。
