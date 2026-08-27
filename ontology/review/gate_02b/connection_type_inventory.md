# Gate 2B ConnectionType Inventory — NeuroGraphIQ Macro96 Ontology

Ontology IRI: `https://neurographiq.org/ontology/macro96`
Namespace: `https://neurographiq.org/ontology/macro96#`（prefix `ngiq:`）
Version: `0.2.0-gate2b`（draft）

| # | IRI | English Label | Chinese Label | Parent | Definition Summary | Status |
|---|---|---|---|---|---|---|
| 1 | ngiq:StructuralConnection | Structural Connection | 结构连接 | ConnectionType | 结构性物理通路；仅断言物理通路存在，≠功能统计相关，≠模型推断有向影响；方向 directed / reciprocal / direction_unknown；突触级 directness 证据未必充分，polysynaptic / indirect pathway 不压缩为单条（应由 Path / Circuit / Inference 表达）。替代术语：anatomical connection | draft |
| 2 | ngiq:Projection | Projection | 投射 | StructuralConnection | 有明确 source→target 且具有 axonal projection 语义/证据的 StructuralConnection 子类；direction_known 是必要但不充分条件；DTI tractography 不能单独判定方向 | draft |
| 3 | ngiq:FunctionalConnectivity | Functional Connectivity | 功能连接 | ConnectionType | 神经活动之间的统计依赖/时间相关；V1 默认 non-directional；不隐含 StructuralConnection；fMRI/EEG/MEG 是证据模态非类型；coactivation 不能仅凭自身自动晋升 | draft |
| 4 | ngiq:EffectiveConnectivity | Effective Connectivity | 有效连接 | ConnectionType | 模型/实验框架下的 model-dependent directed influence / directed coupling；causal interpretation 取决于方法、模型假设与实验设计；≠Projection，≠StructuralConnection | draft |

## 说明

- 以上 4 个 Class 为 Gate 2A 已冻结的分类树（`ConnectionType` 下 3 个直接子类 + `StructuralConnection` 下 1 个子类）。
- 每个 Class 均含英文 label（@en）、中文 label（@zh）、英文 comment（@en）、中文 comment（@zh）。
- `StructuralConnection` 的英文替代术语 `anatomical connection` 以 comment 文本方式记录（未引入 SKOS / 自定义 AnnotationProperty，遵循 Gate 2B 约束）。
- 方向 / directness / source / target / evidence 等概念目前仅存在于 comment 语义中，未建立任何 ObjectProperty / DataProperty（留待后续 Property Gate）。
