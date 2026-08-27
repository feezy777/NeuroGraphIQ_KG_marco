# Gate 2A — ConnectionType 科学分类方案（候选方案，待人工审查）

Ontology IRI: `https://neurographiq.org/ontology/macro96`
Namespace: `https://neurographiq.org/ontology/macro96#`（prefix `ngiq:`）
本轮状态: **仅方案，未写入正式 TTL**（`neurographiq_macro96_v1.ttl` 未修改）
适用范围: Macro96（宏观尺度 96 脑区）连接知识图谱的 ConnectionType 受控词表

---

## 0. 本轮结论速览

| 项目 | 结论 |
|---|---|
| 推荐保留 ConnectionType | **4 个**（3 个顶层 + 1 个子类） |
| 顶层命名 | `StructuralConnection` / `FunctionalConnectivity` / `EffectiveConnectivity` |
| 唯一子类 | `Projection` ⊑ `StructuralConnection` |
| REMOVE（不建类型） | Coactivation、AssociationConnection（统计义）、LocalAnatomicalConnection、Unknown/Uncertain Connection |
| DEFER（暂不建，未来再议） | FiberTractConnection、纤维三分（projection/association/commissural fibers） |
| 是否修改正式 TTL | **否** |

---

## 1. RECOMMENDED TAXONOMY（方案 A，正式推荐）

```
ConnectionType                                    (Gate 1 已有根类)
├─ StructuralConnection                           [KEEP]
│   └─ Projection                                 [KEEP — 有向结构连接]
├─ FunctionalConnectivity                         [KEEP]
└─ EffectiveConnectivity                          [KEEP]
```

即：

```text
ConnectionType
├─ StructuralConnection（结构连接）
│   └─ Projection（投射）
├─ FunctionalConnectivity（功能连接）
└─ EffectiveConnectivity（有效连接）
```

**总类型数：4。** 其中 3 个是神经科学公认的三分（结构 / 功能 / 有效），第 4 个 `Projection` 是 `StructuralConnection` 的唯一子类，用于表达「有明确 source→target 方向的结构通路」。

### 1.1 每个类型的本体位置与方向性

| Canonical Name | 中文 | Parent | Directionality |
|---|---|---|---|
| StructuralConnection | 结构连接 | ConnectionType | directed / reciprocal / direction_unknown（区分 biological direction 与 evidence-known direction） |
| Projection | 投射 | StructuralConnection | **directed**（必有 source→target） |
| FunctionalConnectivity | 功能连接 | ConnectionType | **non-directional**（V1 默认；核心语义是 statistical dependence） |
| EffectiveConnectivity | 有效连接 | ConnectionType | **directed**（必有方向） |

---

## 2. 设计总原则（本轮分类的约束）

本分类优先保证 8 条硬约束（对应任务书 §二）：

1. **神经科学概念成立** —— 每个类型都必须对应一个文献中公认、可独立定义的现象。
2. **语义标准清楚（但不互斥）** —— 每个类型由「物理通路 vs 统计关系 vs 模型推断有向影响」三个正交维度之一唯一界定其**语义标准**；但类型之间**不互斥**，同一脑区对可同时存在 StructuralConnection、FunctionalConnectivity 与 EffectiveConnectivity。
3. **不混关系** —— 结构、功能、有效三种连接回答的是三个不同的问题，不把它们压缩成一个 `Connection` 通吃。
4. **支持证据审查** —— 每个类型对证据模态（tracer / DTI / fMRI / DCM / Granger）有明确的可支持/不可支持关系。
5. **支持有向连接** —— `Projection` 与 `EffectiveConnectivity` 天然有向。
6. **支持 Macro96** —— 宏观尺度固定，因此排除「局部/内在连接」这类微观尺度概念。
7. **不制造无必要类型** —— 只保留 4 个；纤维分类、证据方法、不确定性状态一律不建成类型。
8. **不混淆四类边界** —— evidence type ≠ connection type；统计关联 ≠ 解剖连接；有效连接（有向影响）≠ 结构连接。

---

## 3. 命名决策：AnatomicalConnection vs StructuralConnection vs StructuralConnectivity

**最终推荐：`StructuralConnection`（Canonical Name）**，同时以 `rdfs:label` / 备选标签携带 `anatomical connection` 与 `structural connectivity` 两个同义/近义表述。

### 3.1 为什么不选 `StructuralConnectivity`

- 文献中 `structural connectivity` 一词既可用于 **pairwise 层级**（「A 与 B 之间存在 structural connectivity」，即一条结构连接），也可用于 **network 层级**（整张 connectome 的 SC 矩阵）。两者都是合法用法。
- 本项目 `ConnectionType` 描述的是**单条 `Connection`**（一个脑区对之间的一条连接）。作为受控词表项，`StructuralConnection`（单条、单数）比 `StructuralConnectivity`（易被读作 network 层级的性质）更贴合词表语义。
- 因此正式类型名选 `StructuralConnection`；`structural connectivity` 作为 altLabel 保留，以覆盖文献中的 pairwise 用法。

### 3.2 为什么不选 `AnatomicalConnection` 作为主名

- 「anatomical connection」在示踪/动物神经解剖文献中是最精确的表述（直接物理解剖通路），但在**人类宏观连接组学**里，「structural connection / structural connectivity (SC)」才是主导术语（Sporns 等 2005）。
- `StructuralConnection` 与旧系统字段 `structural_connection` 完全对齐（兼容性参考，见 §6），降低迁移成本。
- `Structural` 与另外两个兄弟类型 `FunctionalConnectivity` / `EffectiveConnectivity` 在语义上形成标准三分 SC/FC/EC，读者可一眼识别。
- `Anatomical` 语义上强调「物理通路」这一正确含义，可作为**精确同义标签**保留（`skos:altLabel "anatomical connection"@en`），不丢失示踪文献用语的召回能力。

### 3.3 为什么兄弟类型保留了 `-Connectivity` 后缀（有意的不对称）

- `FunctionalConnectivity` 与 `EffectiveConnectivity` 是 Friston（1994, 2011）原文的固定术语，无法在不违背文献的前提下改名为 `FunctionalConnection` / `EffectiveConnection`（后者在文献中几乎不存在）。
- 因此出现「StructuralConnection（-Connection）vs FunctionalConnectivity（-Connectivity）」的不对称。**这是有意为之且可辩护**：SC 一词在「连接类型」语境下读作「一条结构连接」是自然的；而 FC/EC 是学科标准名，强行对称改名反而制造语义漂移。
- 若人工审查者更偏好**完全对称**，两个对称替代方案见 §4（方案 B1/B2），但本方案**不推荐**它们（理由见下）。

---

## 4. 替代方案（方案 B，供审查者比较）

### 方案 B1 —— 全 `-Connection` 对称

```
ConnectionType
├─ StructuralConnection
├─ FunctionalConnection
└─ EffectiveConnection
```

- 优点：与根类 `Connection` 完全对称、语法统一。
- 缺点：`FunctionalConnection` 与 `EffectiveConnection` 偏离 Friston 固定术语，与主流文献、与 DeepSeek/BioSEPBERT 训练语料中高频出现的 `functional connectivity` / `effective connectivity` 不一致，可能降低 LLM 分类召回。**不推荐。**

### 方案 B2 —— 全 `-Connectivity` 对称

```
ConnectionType
├─ StructuralConnectivity
├─ FunctionalConnectivity
└─ EffectiveConnectivity
```

- 优点：三个名字都是文献标准名，无不对称。
- 缺点：`StructuralConnectivity` 易被读作 network 层级的性质，不如 `StructuralConnection` 贴合「单条 Connection」的词表语义（见 §3.1）；且旧系统字段为 `structural_connection`，改名破坏兼容性。**不推荐。**

> 结论：方案 A（本文 §1）是「文献忠实度 + 本体范畴正确 + 旧系统兼容」三者的最优平衡。

---

## 5. 三大核心概念的科学定位

### 5.1 StructuralConnection（结构连接 / 解剖连接）

- **科学定义**：两个脑区之间存在**物理的轴突/纤维通路**，即存在真实的神经解剖连接。
- **本质**：physical pathway（物理通路）。
- **directness（synaptic directness）**：StructuralConnection 表示两脑区之间存在**结构性物理通路**，但具体证据可能不足以确认突触级 directness（monosynaptic vs polysynaptic）。由多个中间脑区介导的 **polysynaptic / indirect pathway 不应直接压缩成单条 StructuralConnection**，应由 Path / Circuit / Inference 表达。是否新增 `synaptic_directness` 属性留到后续 Property Gate 决定；基于 DTI 的结构连接是**间接重建**，须保留其间接性与误差边界（crossing fibers / kissing fibers 等），不可与 tracer 确认的直接解剖通路等同。
- **方向性**：directed / reciprocal / direction_unknown。区分 **biological direction**（物理通路本身的有向性：A→B 单向 或 A↔B 相互）与 **evidence-known direction**（依据证据所知的方向）。tractography 无法判定 afferent/efferent 时，记为 direction_unknown。
- **证据模态**：逆行/顺行示踪（金标准）、组织学、DTI 纤维追踪（间接重建，见 5.4）、已知图谱通路。
- **关键边界**：结构连接 ≠ 统计相关（见 5.2）；结构连接 ≠ 模型推断有向影响（见 5.3）。结构连接是唯一「可隐含物理解剖联系」的类型。polysynaptic / indirect pathway 由中间脑区介导时，不应压缩成单条 StructuralConnection，而应由 Path / Circuit / Inference 表达。

### 5.2 FunctionalConnectivity（功能连接）

- **科学定义**（Friston 1994）：**「远隔神经生理事件之间的时间相关性」**（"temporal correlations between remote neurophysiological events"）。
- **本质**：statistical dependence（统计依赖）。
- **方向性**：V1 默认建模为 **non-directional**；核心语义是 statistical dependence（统计依赖）。不写成绝对的「inherently symmetric」。
- **证据模态**：静息态 fMRI（BOLD 相关）、任务态 fMRI、EEG/MEG（相干、相位耦合、包络相关）等——**所有这些是同一上位概念，只是模态/方法不同，属于证据层差异，不构成新类型**。
- **关键边界**：FunctionalConnectivity **不等于** StructuralConnection。两个区域功能相关，不代表存在直接解剖连接；除非另有独立结构证据。
- 任务态 coactivation（MACM/ALE 跨研究共激活）是一种 **functional observation / evidence candidate**，见 §7.1；它不能仅凭自身自动晋升为 FunctionalConnectivity。

### 5.3 EffectiveConnectivity（有效连接）

- **科学定义**（Friston 1994, 2011）：**「一个神经系统对另一个神经系统施加的影响（直接或间接），以交互模型的形式表达」**（"the influence one neural system exerts over another, either directly or indirectly, in terms of a model of the interactions"）。
- **本质**：model-dependent directed influence / directed coupling（模型依赖的有向影响 / 有向耦合）。causal interpretation 取决于具体方法、模型假设与实验设计。
- **方向性**：directed（必有方向）。
- **证据模态**：DCM、Granger causality、结构方程模型 SEM、干预/扰动（TMS、损伤、光遗传）等。
- **关键边界**：EffectiveConnectivity **不等于** Projection（有向有效影响 ≠ 有向解剖投射，可能是多突触/间接的）；EffectiveConnectivity **不等于** StructuralConnection（除非另有独立结构证据）。

### 5.4 Projection（投射）—— StructuralConnection 的唯一子类

- **科学定义**：一组轴突从**源脑区**发出并终止于**目标脑区**的**轴突投射型**有向结构连接（"A projects to B" = A 向 B 发出传出纤维）。
- **本质**：directed structural/anatomical connection。
- **方向性**：directed（always）。
- **为什么是子类而非兄弟**：`Projection` 是结构连接中**具有明确 source→target 的轴突投射型**子集。方向明确是**必要条件**，但**仅 direction_known 不足以自动分类为 Projection**——仍需 axonal projection 语义/证据（如示踪显示轴突终止于 target）。
- **方向如何判定（tracer evidence）**：
  - **顺行示踪（anterograde）**：示踪剂注入 A，标记 A 的传出纤维末端 → 在 B 观察到标记，证明 **A→B**。
  - **逆行示踪（retrograde）**：示踪剂注入 B，被 B 的传入纤维末梢摄取并逆行到胞体 → 在 A 观察到标记胞体，证明 **A→B**。
  - 顺行 + 逆行联合（或已知解剖）是「投射」方向判定的金标准。
- **关键边界（呼应任务书 §四）**：
  - 无法确定方向的物理解剖连接，**仍可称为 `StructuralConnection`，但不能称为 `Projection`**。因为 `Projection` 的语义内在地包含方向；把方向未知的结构连接标为 Projection 会污染方向信息。
  - 方向明确（direction_known）是 `Projection` 的**必要条件，但不充分**：仅知道 direction 不足以自动分类为 Projection，仍需 **axonal projection 语义/证据**（如示踪显示轴突终止于 target）。
  - 「projects to」应解释为「发出传出轴突并终止于」，是对**物理通路 + 方向**的陈述，不是对功能影响的陈述。

---

## 6. 与旧 NeuroGraphIQ schema 的兼容性对照（仅作参考，不构成保留义务）

旧系统 `connection_type` 取值（来自 `backend/_batch_verify_macro.py` 与 `backend/migrations/20260918_macro_candidate_llm_review.sql`）：

| 旧值 | 本轮裁定 | 理由 |
|---|---|---|
| `structural_connection` | → `StructuralConnection`（KEEP，命名对齐） | 语义正确，保留并正名 |
| `functional_connectivity` | → `FunctionalConnectivity`（KEEP） | 语义正确，保留 |
| `projection` | → `Projection`（KEEP，归入 StructuralConnection 子类） | 语义正确，保留并明确层级 |
| `effective_connectivity` | → `EffectiveConnectivity`（KEEP） | 语义正确，保留 |
| `association` | **REMOVE**（见 §7.2） | 统计关联，或与「联合纤维」歧义 |
| `coactivation` | **REMOVE**（见 §7.1） | functional observation / evidence candidate，不得仅凭 coactivation 自动晋升 FunctionalConnectivity |
| `uncertain_connection` | **REMOVE**（见 §8） | 认知状态，非生物学类型 |
| `unknown` | **REMOVE**（见 §8） | 认知状态，非生物学类型 |

> 旧字段仅为兼容性参考。旧系统存在某类型，不代表新 Ontology V1 必须保留。Gate 2A 重新定义语义。

---

## 7. 三个旧草案概念的重审结论（详见 excluded_or_deferred_types.md）

| 旧草案概念 | 严格 ConnectionType? | 更适合的归属 | 语义污染风险 | 裁定 |
|---|---|---|---|---|
| Coactivation（共激活） | 否 | **functional observation / evidence candidate**（MACM/ALE 任务态共激活），不可自动晋升为 FC | 高（会把统计共激活当成正式脑连接） | **REMOVE** |
| AssociationConnection（统计关联义） | 否 | 与 FunctionalConnectivity 重复；或与「association fibers（联合纤维）」歧义 | 极高（一义双关） | **REMOVE** |
| LocalAnatomicalConnection（局部/内在解剖连接） | 否（对 Macro96） | 微观/介观尺度的空间概念；Macro96 固定在宏观尺度 | 中（尺度错位） | **REMOVE** |

---

## 8. Unknown / Uncertain 不建为类型

「未知 / 不确定」不是生物学连接类型，而是**认知状态（epistemic state）**。应通过以下属性表达，而非建立一个 `ConnectionType` 子类：

- `review_status`（未审/已审/通过/驳回）
- `connection_status`（candidate/confirmed/rejected）
- `assessment_status` / `confidence`（置信度）
- `uncertainty_reason`（为什么不确定）

旧系统的 `uncertain_connection` / `unknown` / `possibly_connects_to` 应全部迁移到这些状态字段。**不建立** `UnknownConnection` / `UncertainConnection` / `AssociationConnection` 作为 ConnectionType。

---

## 9. 类型数量的克制（为什么只有 4 个）

- 神经科学界公认的「连接三分」只有结构/功能/有效三类。任何超过这三类的「第 N 类」，要么是这三类的**观察/证据候选**（coactivation→FC 的 evidence candidate；fiber tract→SC 的解剖实体，DTI tractography 是其方法/证据），要么是状态（unknown/uncertain），要么是尺度（local→非宏观）。
- `Projection` 是唯一例外：它是具有明确 source→target 且具有 axonal projection 语义/证据的 StructuralConnection 子类（direction_known 是必要条件但不是充分条件），且在示踪/Allen 图谱语料中高频独立出现，值得作为子类单独命名。
- 因此 4 个是「充分且不冗余」的最小集合。再增加任何类型都属于过度扩张（违反任务书 §二.7）。

---

## 10. 待人工审查的 4 个关键决策点

1. **命名不对称**：是否接受「StructuralConnection（-Connection）+ FunctionalConnectivity / EffectiveConnectivity（-Connectivity）」的有意不对称？（推荐接受；对称替代见 §4）
2. **Projection 层级**：`Projection` 作为 `StructuralConnection` 子类（推荐）还是与 `StructuralConnection` 并列的兄弟类型？
3. **FiberTractConnection 的 DEFER**：是否同意「纤维束」作为证据/通路描述而非连接类型，暂不建类？
4. **Coactivation / Association / Local 的 REMOVE**：是否同意三者均不进入 V1？

---

## 11. 涉及文件

- 本文件：`connection_type_taxonomy_proposal.md`
- 定义卡：`connection_type_definition_cards.md`
- 边界矩阵：`connection_type_boundary_matrix.md`
- 排除/暂缓：`excluded_or_deferred_types.md`
- 参考文献：`references.md`
- 审查清单：`review_checklist.md`

---

## 12. 本轮未做（严格对照任务书 §十五）

- 未修改 `neurographiq_macro96_v1.ttl`
- 未新增任何 OWL Class / ObjectProperty / DataProperty / AnnotationProperty / Individual
- 未修改 BrainRegion / CircuitType / EvidenceType，未建立 Function hierarchy
- 未导入 Macro96，未修改 PostgreSQL / migration / API / frontend / Neo4j
- 未 commit / push
