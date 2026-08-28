# Gate 6B — 关系学习指南（ObjectProperty）

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
version: `0.6.0-gate6b`

> 每个关系：是什么 / 连接什么 / 例子。箭头：`→` 有向，`—` 无方向。

---

## 最小核心图（先看这张）

```
BrainRegion
   │ participatesIn
   ▼
Circuit
   │ hasConnectionMembership
   ▼
CircuitConnectionMembership
   │ membershipConnection
   ▼
Connection
   ├─ hasEndpointRegion
   ├─ hasSourceRegion
   └─ hasTargetRegion
   ▼
BrainRegion

Circuit ──hasFunction──> Function
BrainRegion ──participatesIn──> Function
```

---

### structurallyConnectedTo / 结构连接
- 是什么：两脑区存在神经解剖物理通路（方向可未知）。
- 连接：BrainRegion — BrainRegion（Derived）。
- 例子：Thalamus — Cortex。

### functionallyConnectedTo / 功能连接
- 是什么：两脑区神经活动统计相关/同步（non-directional）。
- 连接：BrainRegion — BrainRegion（Derived）。
- 例子：PCC — mPFC。

### projectsTo / 投射到
- 是什么：A 向 B 发出轴突投射（directed）。
- 连接：BrainRegion → BrainRegion（Derived）。
- 例子：CA1 → mPFC。是 structurallyConnectedTo 的子属性。

### effectivelyConnectedTo / 有效连接
- 是什么：模型/实验推断的有向影响。
- 连接：BrainRegion → BrainRegion（Derived）。
- 例子：A → B（DCM）。

### participatesIn / 参与
- 是什么：脑区参与回路或功能。
- 连接：BrainRegion → Circuit / Function（Canonical）。
- 例子：Hippocampus → PapezCircuit；PrefrontalCortex → WorkingMemory。

### modulates / 调控
- 是什么：基因/递质调节脑区/回路/功能。
- 连接：Gene/Neurotransmitter → BrainRegion/Circuit/Function（Canonical）。
- 例子：Dopamine → RewardFunction。

### increasesRiskOf / 增加风险
- 是什么：基因增加疾病风险（≠ 必然致病）。
- 连接：Gene → Disease（Canonical）。
- 例子：APOE → AlzheimerDisease。

### hasFunction / 具有功能
- 是什么：回路关联功能。
- 连接：Circuit → Function（Canonical）。
- 例子：PapezCircuit → MemoryRelatedFunction。

### hasSymptom / 具有症状
- 是什么：疾病表现症状。
- 连接：Disease → Symptom（Canonical）。
- 例子：AlzheimerDisease → MemoryImpairment。

### actsOn / 作用于
- 是什么：递质作用于受体。
- 连接：Neurotransmitter → Receptor（Canonical）。
- 例子：Dopamine → D2Receptor。

### hasEndpointRegion / 连接端点脑区
- 是什么：连接涉及哪个脑区（不表方向）。
- 连接：Connection → BrainRegion（Canonical）。
- 例子：FC001 端点为 PCC 和 mPFC。

### hasSourceRegion / 起始脑区
- 是什么：已知连接起点。
- 连接：Connection → BrainRegion（Canonical，方向已知）。是 hasEndpointRegion 子属性。
- 例子：CONN_001（Projection）→ CA1。

### hasTargetRegion / 目标脑区
- 是什么：已知连接终点。
- 连接：Connection → BrainRegion（Canonical，方向已知）。是 hasEndpointRegion 子属性。
- 例子：CONN_001 → mPFC。

### includesRegion / 包含脑区
- 是什么：回路包含脑区。
- 连接：Circuit → BrainRegion（Canonical）。
- 例子：PapezCircuit → Hippocampus。

### hasConnectionMembership / 具有连接成员关系
- 是什么：回路拥有某连接成员关系。
- 连接：Circuit → CircuitConnectionMembership（Canonical）。

### membershipConnection / 成员连接
- 是什么：成员关系指向其连接。
- 连接：CircuitConnectionMembership → Connection（Canonical）。

### hasConnection / 包含连接
- 是什么：回路包含连接的便捷表达。
- 连接：Circuit → Connection（Derived）。

### reportedIn / 报道于
- 是什么：研究结果由文献报道。
- 连接：ResearchStudy → Publication（Canonical）。
- 例子：Study S001 → PMID_xxx。

### providesEvidence / 提供证据
- 是什么：文献提供证据单元。
- 连接：Publication → Evidence（Canonical）。

### definedInAtlas / 定义于图谱
- 是什么：外部脑区来自图谱。
- 连接：ExternalRegion → Atlas（Canonical）。

### mappingSource / 映射源
- 是什么：映射的源外部脑区。
- 连接：RegionMapping → ExternalRegion（Canonical）。

### mappingTarget / 映射目标
- 是什么：映射的目标 canonical 脑区。
- 连接：RegionMapping → BrainRegion（Canonical）。

### mapsTo / 映射到
- 是什么：外部脑区映射到 canonical 脑区的便捷表达。
- 连接：ExternalRegion → BrainRegion（Derived）。
