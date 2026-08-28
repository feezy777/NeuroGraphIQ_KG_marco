# Gate 6A — 关系学习指南（适合 PPT 整理）· 第二轮修订

> 每个关系只写：是什么 / 连接 / 例子 / 容易混。
> 箭头约定：`→` = 有向；`—` = 无方向。

---

### STRUCTURALLY_CONNECTED_TO / 结构连接

- 是什么：两脑区间存在神经解剖物理通路。
- 连接：BrainRegion — BrainRegion（方向可未知）。
- 例子：Thalamus — Cortex。
- 容易混：≠ PROJECTS_TO（不要求方向+轴突语义）。

### FUNCTIONALLY_CONNECTED_TO / 功能连接

- 是什么：两个脑区的神经活动存在统计相关或同步关系。
- 连接：BrainRegion — BrainRegion（non-directional）。
- 例子：PCC — mPFC。
- 容易混：不自动意味着结构连接，也没有默认方向。

### PROJECTS_TO / 投射到

- 是什么：A 脑区向 B 脑区发出轴突投射。
- 连接：BrainRegion → BrainRegion（Directed）。
- 例子：CA1 → mPFC。
- 容易混：DTI 单独不能判向。

### EFFECTIVELY_CONNECTED_TO / 有效连接

- 是什么：模型/实验推断的有向影响。
- 连接：BrainRegion → BrainRegion（Directed）。
- 例子：A → B（DCM）。
- 容易混：≠ 投射（影响 vs 解剖投射）。

### PARTICIPATES_IN / 参与

- 是什么：脑区参与某回路或某功能。
- 连接：BrainRegion → Circuit / Function。
- 例子：Hippocampus → PapezCircuit；PrefrontalCortex → WorkingMemory。
- 容易混：脑区关联功能用 participatesIn（不用 hasFunction）。

### MODULATES / 调控

- 是什么：实体调节脑区/回路/功能。
- 连接：Gene/Neurotransmitter → BrainRegion/Circuit/Function。
- 例子：Dopamine → RewardFunction。
- 容易混：≠ 关联、≠ 因果。

### INCREASES_RISK_OF / 增加风险

- 是什么：基因增加疾病风险。
- 连接：Gene → Disease。
- 例子：APOE → AlzheimerDisease。
- 容易混：≠ 必然致病；ε4 等 variant 留未来模型。

### HAS_FUNCTION / 具有功能

- 是什么：回路关联某功能。
- 连接：Circuit → Function。
- 例子：PapezCircuit → MemoryRelatedFunction。
- 容易混：脑区关联功能用 participatesIn。

### HAS_SYMPTOM / 具有症状

- 是什么：疾病表现某症状。
- 连接：Disease → Symptom。
- 例子：AlzheimerDisease → MemoryImpairment。

### ACTS_ON / 作用于

- 是什么：神经递质作用于受体。
- 连接：Neurotransmitter → Receptor。
- 例子：Dopamine → D2Receptor。

### HAS_ENDPOINT_REGION / 连接端点脑区

- 是什么：表示一条 Connection 涉及哪个脑区，不说明方向。
- 连接：Connection → BrainRegion（无方向）。
- 例子：FC001 的两个端点为 PCC 和 mPFC。
- 容易混：source/target 只有在方向已知时使用。

### HAS_SOURCE_REGION / 起始脑区

- 是什么：已知连接起点。
- 连接：Connection → BrainRegion（仅方向已知）。
- 例子：CONN_001（Projection）→ CA1。

### HAS_TARGET_REGION / 目标脑区

- 是什么：已知连接终点。
- 连接：Connection → BrainRegion（仅方向已知）。
- 例子：CONN_001 → mPFC。

### INCLUDES_REGION / 包含脑区

- 是什么：回路包含某脑区。
- 连接：Circuit → BrainRegion。
- 例子：PapezCircuit → Hippocampus。

### HAS_CONNECTION_MEMBERSHIP / 具有连接成员关系

- 是什么：回路拥有某连接成员关系。
- 连接：Circuit → CircuitConnectionMembership。

### MEMBERSHIP_CONNECTION / 成员关系指向连接

- 是什么：成员关系指向其连接。
- 连接：CircuitConnectionMembership → Connection。

### REPORTED_IN / 报道于

- 是什么：研究结果由文献报道。
- 连接：ResearchStudy → Publication。
- 例子：Study S001 → PMID_xxx。

### PROVIDES_EVIDENCE / 提供证据

- 是什么：文献提供一个证据单元。
- 连接：Publication → Evidence。

### DEFINED_IN_ATLAS / 定义于图谱

- 是什么：外部脑区来自某图谱。
- 连接：ExternalRegion → Atlas。

### MAPPING_SOURCE / 映射源

- 是什么：映射的源外部脑区。
- 连接：RegionMapping → ExternalRegion。

### MAPPING_TARGET / 映射目标

- 是什么：映射的目标 canonical 脑区。
- 连接：RegionMapping → BrainRegion。

### MAPS_TO / 映射到

- 是什么：外部脑区映射到 canonical 脑区的便捷表达。
- 连接：ExternalRegion → BrainRegion。
- 容易混：canonical 用 RegionMapping，mapsTo 仅派生。

---

> 注：SUPPORTS / CONTRADICTS 语义保留、暂缓正式化，未列入本学习指南（待 Evidence/Assertion Formalization Gate）。
