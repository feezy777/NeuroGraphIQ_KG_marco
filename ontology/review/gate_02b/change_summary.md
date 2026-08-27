# Gate 2B Change Summary — NeuroGraphIQ Macro96 Ontology V1.0

Ontology IRI: `https://neurographiq.org/ontology/macro96`
Version: `0.1.0-gate1` → `0.2.0-gate2b`（仍为 draft）

## 本轮新增（Gate 1 → Gate 2B）

- 正式 TTL `ontology/neurographiq_macro96_v1.ttl` 中新增 **ConnectionType 子类层级（4 个 Class）**：
  - `ngiq:StructuralConnection` ⊑ `ngiq:ConnectionType`
  - `ngiq:Projection` ⊑ `ngiq:StructuralConnection`
  - `ngiq:FunctionalConnectivity` ⊑ `ngiq:ConnectionType`
  - `ngiq:EffectiveConnectivity` ⊑ `ngiq:ConnectionType`
- 每个新增 Class 均含：
  - `rdfs:label`（@en + @zh）
  - `rdfs:comment`（@en + @zh，承载 Gate 2A 冻结定义语义）
- 头部注释更新为 Gate 2B 范围说明；`owl:versionInfo` 更新为 `0.2.0-gate2b`；ontology `rdfs:comment` 更新为 Gate 2B 范围（24 顶层类 + 4 个 ConnectionType 子类）。

## 本轮语义要点（遵循 Gate 2A 冻结定义）

- `StructuralConnection`：结构性物理通路；≠功能统计相关；≠模型推断有向影响；方向 directed / reciprocal / direction_unknown；polysynaptic / indirect pathway 不压缩为单条（由 Path / Circuit / Inference 表达）；替代术语 `anatomical connection` 记录于 comment。
- `Projection`：有明确 source→target 且具 axonal projection 语义/证据的 StructuralConnection 子类；direction_known 必要但不充分；DTI 不能单独判向。
- `FunctionalConnectivity`：统计依赖/时间相关；V1 默认 non-directional；不隐含 StructuralConnection；coactivation 不能自动晋升。
- `EffectiveConnectivity`：model-dependent directed influence / directed coupling；causal interpretation 取决于方法/模型假设/实验设计；≠Projection，≠StructuralConnection。

## 本轮没有做

- 没有新增任何 ObjectProperty / DataProperty / 自定义 AnnotationProperty（方向 / directness / source / target / evidence 仅存在于 comment 语义中，留待 Property Gate）。
- 没有引入 SKOS / 外部 ontology import（`owl:imports` 仍为 0）。
- 没有新增 FiberTractConnection / Coactivation / AssociationConnection / LocalAnatomicalConnection / UnknownConnection / UncertainConnection 等任何其它 ConnectionType 子类。
- 没有修改 BrainRegion / CircuitType / EvidenceType，没有建立 Function hierarchy、SHACL、Individual、Macro96 实例。
- 没有 commit / push（Gate 2B 待 Protégé 人工验收后单独 commit）。

## 未进入的后续 Gate

- CircuitType 层级、EvidenceType 层级、ObjectProperty / DataProperty（Property Gate）、BrainRegion hierarchy、SHACL、实例层：均未开始。
