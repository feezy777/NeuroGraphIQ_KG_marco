# Gate 6A — 老师 PPT 关系规范化映射 · 第二轮修订

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
本轮状态: **仅映射文档，未修改正式 TTL**

老师 PPT 的 6 个关系**全部保留，不删除、不随意改科学含义**；本轮做规范化解释。

---

## 1. STRUCTURALLY_CONNECTED_TO / 结构连接

- **定义**：两个 BrainRegion 之间存在神经解剖上的物理连接通路。
- **对应 canonical**：StructuralConnection。
- **Domain**：BrainRegion；**Range**：BrainRegion。
- **方向**：默认不简单定义为严格有向（可 directed / reciprocal / direction_unknown，具体方向由 Connection entity 表达）。
- **例子**：Thalamus — Cortex；Hippocampus — PrefrontalCortex（structural connection exists; direction not asserted）。
- **易混**：≠ PROJECTS_TO。结构连接只说明存在通路；Projection 还要求明确 source→target + axonal projection 语义。
- **Role**：Derived / graph projection。

## 2. FUNCTIONALLY_CONNECTED_TO / 功能连接

- **定义**：两个 BrainRegion 的神经活动之间存在统计依赖、相关或时间同步关系。
- **对应 canonical**：FunctionalConnectivity。
- **Domain**：BrainRegion；**Range**：BrainRegion。
- **方向**：V1 默认 non-directional。
- **例子**：PosteriorCingulateCortex — MedialPrefrontalCortex（non-directional statistical dependence）。
- **典型证据**：resting-state fMRI、EEG/MEG coupling。
- **易混**：不意味着 STRUCTURALLY_CONNECTED_TO，也不意味着 PROJECTS_TO。
- **Role**：Derived / graph projection。

## 3. PROJECTS_TO / 投射到

- **定义**：一个 BrainRegion 向另一个 BrainRegion 发出具有明确 source→target 的轴突投射。
- **对应 canonical**：Projection。
- **Domain**：BrainRegion；**Range**：BrainRegion。
- **方向**：DIRECTED。
- **例子**：CA1 → mPFC；Thalamus → Cortex。
- **易混**：是 StructuralConnection 的更具体语义；DTI tractography alone 不能自动生成 `A PROJECTS_TO B`。
- **Role**：Derived / graph projection。

## 4. PARTICIPATES_IN / 参与（恢复 PPT 完整语义）

- **定义**：某个 BrainRegion 参与某个神经回路（Circuit）或神经功能（Function）。
- **Domain**：BrainRegion；**Range**：Circuit OR Function。
- **方向**：Directed（region → circuit/function）。
- **例子 1**：Hippocampus PARTICIPATES_IN PapezCircuit。
- **例子 2**：PrefrontalCortex PARTICIPATES_IN WorkingMemory。
- **易混**：表示 BrainRegion 的参与关系；与 includesRegion 具自然逆语义（本 Gate 不建 owl:inverseOf）。
- **Role**：Canonical candidate。

## 5. MODULATES / 调控

- **定义**：某个生物学实体对 BrainRegion/Circuit/Function 的活动/状态/功能产生调节作用。
- **Domain**：Gene OR Neurotransmitter；**Range**：BrainRegion OR Circuit OR Function。
- **方向**：Directed。
- **例子**：Dopamine MODULATES RewardFunction；某 Gene MODULATES SynapticFunction。
- **易混**：不是 associated_with，也不是 causes；无调控证据时不能使用。
- **Role**：Canonical。

## 6. INCREASES_RISK_OF / 增加风险

- **定义**：某个 Gene 与疾病风险增加之间存在有证据支持的风险关系。
- **Domain**：Gene；**Range**：Disease。
- **方向**：Directed。
- **例子**：APOE INCREASES_RISK_OF AlzheimerDisease。
- **易混**：≠ CAUSES（风险增加不等于疾病必然发生）；associated_with 不能自动升级为 INCREASES_RISK_OF。
- **边界**：APOE ε4 等 allele/variant 级风险关系需未来 GeneticVariant / Allele 模型才能更精确表达，V1 暂不扩展。
- **Role**：Canonical。

---

## 映射总表

| PPT 关系 | 对应 Connection/Class | Role |
|---|---|---|
| STRUCTURALLY_CONNECTED_TO | StructuralConnection | Derived |
| FUNCTIONALLY_CONNECTED_TO | FunctionalConnectivity | Derived |
| PROJECTS_TO | Projection | Derived |
| PARTICIPATES_IN | Circuit / Function 参与 | Canonical |
| MODULATES | Gene/Neurotransmitter 调控 | Canonical |
| INCREASES_RISK_OF | Gene → Disease | Canonical |
