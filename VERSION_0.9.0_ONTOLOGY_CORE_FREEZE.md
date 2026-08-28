# NeuroGraphIQ Human Brain Ontology Core — 0.9.0

状态：**FROZEN FOR DATA IMPLEMENTATION**

这是 NeuroGraphIQ 人脑知识图谱 V1 的核心本体冻结版本。当前阶段已完成本体科学语义设计、关系边界审查与全局一致性验证，后续工作将以该版本为稳定基础进入 PostgreSQL Schema / Migration 与真实知识数据生产。

## 本版本包含

- 23 个核心 Class
- 26 个核心 ObjectProperty
- 0 个 DataProperty
- 0 个 Named Individual
- 0 个 OWL imports
- Production scope：**Homo sapiens（NCBI Taxonomy 9606）**

核心知识对象包括 BrainRegion、Connection、Circuit、Function、Gene、Disease、Evidence、Atlas、RegionMapping 等。

## 关键设计原则

- Connection 采用 reified entity 作为 canonical truth；脑区之间的直接连接关系主要作为查询/Neo4j 派生投影。
- StructuralConnection、Projection、FunctionalConnectivity、EffectiveConnectivity 保持严格科学语义区分。
- Circuit 表示生物学/功能性神经回路，不等同于图论中的闭环。
- BrainRegion 解剖层级使用 `partOf` / `subfieldOf`；Atlas mapping、跨颗粒度 aggregation 和空间几何关系与解剖层级严格分离。
- Function 层级使用 `subFunctionOf` 表达具体功能概念之间的下位关系。
- Evidence 是具体证据单元，Publication 不等于 Evidence；KnowledgeAssertion、EvidenceLink、supports/contradicts/qualifies 等复杂上下文保留在 PostgreSQL 层。
- V1 不将 `spatiallyOverlaps`、`adjacentTo`、`locatedIn` 纳入 OWL Core，空间关系保留在具体 SpatialRepresentation / 数据层处理。
- 当前核心本体为 Human-only；非人类数据不进入 production canonical knowledge。

## 冻结记录

- Ontology IRI：`https://neurographiq.org/ontology/human-brain`
- Freeze version：`0.9.0-ontology-core-freeze`
- Freeze commit：`0722009`
- Freeze documentation commit：`fa222a5`
- TTL SHA256：`37e0e3aff4aca4c4f898fba0f7b1c0b6121fe086725d89517db9601c0fe7b790`
- 语义校验：排除版本元数据后 `semantic_diff_count = 0`

## 下一阶段

进入 PostgreSQL Schema / Migration Implementation：依据已冻结的数据字典和本体边界实现 32 张科学表、主外键与约束，并开始 canonical instance、Evidence、Connection、Circuit 等真实知识数据生产。

> 本次冻结并不意味着本体永久不可修改。后续核心本体变更需要通过版本化 Ontology Change Proposal，并评估科学理由、兼容性、数据库迁移与下游图谱影响。
