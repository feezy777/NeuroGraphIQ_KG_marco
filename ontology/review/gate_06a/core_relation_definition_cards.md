# Gate 6A — Core Relation Definition Cards（23 候选 + 2 deferred 定义卡）· 第二轮修订

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
本轮状态: **仅关系定义卡，未修改正式 TTL**

格式：Relation / 中文 / 是什么 / Domain / Range / Direction / 例子 / 对应 canonical / Role / 容易混。

> 箭头约定：`→` = directed；`—` = non-directional / direction unknown。

---

## A. PPT Scientific Relations

### STRUCTURALLY_CONNECTED_TO / 结构连接
- 是什么：两脑区间存在神经解剖物理通路。
- Domain: BrainRegion；Range: BrainRegion；Direction: 非严格有向（directed/reciprocal/unknown）。
- 例子: Thalamus — Cortex（direction not asserted）。
- 对应 canonical: StructuralConnection。Role: Derived。
- 容易混: ≠ PROJECTS_TO（不要求方向+轴突语义）。

### FUNCTIONALLY_CONNECTED_TO / 功能连接
- 是什么：两脑区神经活动统计依赖/相关/同步。
- Domain: BrainRegion；Range: BrainRegion；Direction: non-directional。
- 例子: PCC — mPFC（non-directional statistical dependence）。
- 对应 canonical: FunctionalConnectivity。Role: Derived。
- 容易混: 不意味着结构连接或投射。

### PROJECTS_TO / 投射到
- 是什么：A 脑区向 B 脑区发出轴突投射。
- Domain: BrainRegion；Range: BrainRegion；Direction: Directed。
- 例子: CA1 → mPFC。
- 对应 canonical: Projection。Role: Derived。
- 容易混: DTI 单独不能判向。

### PARTICIPATES_IN / 参与
- 是什么：脑区参与某回路或某功能。
- Domain: BrainRegion；Range: Circuit OR Function；Direction: Directed。
- 例子: Hippocampus → PapezCircuit；PrefrontalCortex → WorkingMemory。
- Role: Canonical。
- 容易混: BrainRegion→Function 用 participatesIn（不用 hasFunction）。

### MODULATES / 调控
- 是什么：实体对脑区/回路/功能产生调节作用。
- Domain: Gene OR Neurotransmitter；Range: BrainRegion OR Circuit OR Function；Direction: Directed。
- 例子: Dopamine → RewardFunction。
- Role: Canonical。
- 容易混: ≠ associated_with / causes。

### INCREASES_RISK_OF / 增加风险
- 是什么：基因与疾病风险增加有证据支持的关系。
- Domain: Gene；Range: Disease；Direction: Directed。
- 例子: APOE → AlzheimerDisease。
- Role: Canonical。
- 容易混: ≠ CAUSES；ε4 等 variant 级关系留未来 GeneticVariant 模型。

---

## B. NeuroGraphIQ Scientific Extension

### EFFECTIVELY_CONNECTED_TO / 有效连接（有向影响）
- 是什么：模型/干预/实验推断的有向影响。
- Domain: BrainRegion；Range: BrainRegion；Direction: Directed。
- 例子: A → B（DCM）。
- 对应 canonical: EffectiveConnectivity。Role: Derived。
- 容易混: ≠ Projection（影响 vs 解剖投射）。
- 标记: PROJECT ADDITION。

### HAS_FUNCTION / 具有功能（收窄）
- 是什么：某 Circuit 与某功能存在明确功能关联。
- Domain: Circuit；Range: Function；Direction: Directed。
- 例子: PapezCircuit → MemoryRelatedFunction。
- Role: Canonical。
- 容易混: BrainRegion→Function 用 participatesIn，不用 hasFunction。

### HAS_SYMPTOM / 具有症状
- 是什么：疾病表现为某临床症状。
- Domain: Disease；Range: Symptom；Direction: Directed。
- 例子: AlzheimerDisease → MemoryImpairment。
- Role: Canonical。
- 容易混: 表示常见/报道临床表现，非所有患者必然。

### ACTS_ON / 作用于
- 是什么：神经递质作用于受体。
- Domain: Neurotransmitter；Range: Receptor；Direction: Directed。
- 例子: Dopamine → D2Receptor；Glutamate → NMDAReceptor。
- Role: Canonical。
- 容易混: 不扩展 pharmacology hierarchy。

---

## C. Connection Structural Model

### HAS_ENDPOINT_REGION / 连接端点脑区（新增）
- 是什么：表示参与某 Connection 的脑区端点，不声明方向。
- Domain: Connection；Range: BrainRegion；Direction: 无方向。
- 例子: FC001 hasEndpointRegion PCC；FC001 hasEndpointRegion mPFC。
- Role: Canonical。
- 容易混: source/target 只有在方向已知时才使用。

### HAS_SOURCE_REGION / 起始脑区（仅方向已知）
- 是什么：已知连接起点。
- Domain: Connection；Range: BrainRegion；Direction: Directed。
- 例子: CONN_001（rdf:type Projection）→ CA1。
- Role: Canonical（仅 direction scientifically established）。

### HAS_TARGET_REGION / 目标脑区（仅方向已知）
- 是什么：已知连接终点。
- Domain: Connection；Range: BrainRegion；Direction: Directed。
- 例子: CONN_001 → mPFC。
- Role: Canonical（仅 direction scientifically established）。

---

## D. Circuit Model

### INCLUDES_REGION / 包含脑区
- 是什么：回路包含某脑区。
- Domain: Circuit；Range: BrainRegion；Direction: Directed。
- 例子: PapezCircuit → Hippocampus。
- Role: Canonical。
- 容易混: 是 participatesIn 的逆语义（本 Gate 不建 owl:inverseOf）。

### HAS_CONNECTION_MEMBERSHIP / 具有连接成员关系
- 是什么：回路拥有某 membership。
- Domain: Circuit；Range: CircuitConnectionMembership；Direction: Directed。
- Role: Canonical。

### MEMBERSHIP_CONNECTION / 成员关系指向连接
- 是什么：membership 指向其 Connection。
- Domain: CircuitConnectionMembership；Range: Connection；Direction: Directed。
- Role: Canonical。

### HAS_CONNECTION / 具有连接（derived）
- 是什么：回路包含某连接的便捷表达。
- Domain: Circuit；Range: Connection；Direction: Directed。
- Role: Derived（从 membership 派生）。

---

## E. Provenance

### REPORTED_IN / 报道于
- 是什么：研究结果由某文献报道。
- Domain: ResearchStudy；Range: Publication；Direction: Directed。
- 例子: Study S001 → PMID_xxx。
- Role: Canonical。

### PROVIDES_EVIDENCE / 提供证据
- 是什么：文献提供一个证据单元。
- Domain: Publication；Range: Evidence；Direction: Directed。
- Role: Canonical。

### SUPPORTS / 支持 —— **KEEP SEMANTICS / FORMALIZATION DEFER**
- 语义：证据支持某知识断言。
- 暂缓原因：Range 仅 Connection/Circuit 无法覆盖普通 ObjectProperty assertion；需 assertion-level evidence model（见 evidence_provenance_relations.md）。

### CONTRADICTS / 反驳 —— **KEEP SEMANTICS / FORMALIZATION DEFER**
- 语义：证据与某断言冲突。
- 暂缓原因：同上。

---

## F. Atlas / Mapping

### DEFINED_IN_ATLAS / 定义于图谱
- 是什么：外部脑区来自某图谱。
- Domain: ExternalRegion；Range: Atlas；Direction: Directed。
- 例子: Brainnetome parcel A9m → BrainnetomeAtlas。
- Role: Canonical。

### MAPPING_SOURCE / 映射源
- 是什么：映射的 source 外部脑区。
- Domain: RegionMapping；Range: ExternalRegion；Direction: Directed。
- Role: Canonical。

### MAPPING_TARGET / 映射目标
- 是什么：映射的 target canonical 脑区。
- Domain: RegionMapping；Range: BrainRegion；Direction: Directed。
- Role: Canonical。

### MAPS_TO / 映射到（derived）
- 是什么：外部脑区映射到 canonical 脑区的便捷表达。
- Domain: ExternalRegion；Range: BrainRegion；Direction: Directed。
- Role: Derived（从 RegionMapping 派生）。
