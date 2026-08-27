# Gate 2A — 排除（REMOVE）与暂缓（DEFER）类型

本文件记录本轮裁定为「不应进入 Macro96 V1 ConnectionType 词表」的概念，及其原因。
每个概念按任务书 §七的四个问题给出结论。

---

## 1. Coactivation（共激活）— REMOVE

| 问题 | 结论 |
|---|---|
| A. 是严格意义的 ConnectionType 吗？ | **否**。共激活是「跨研究任务态激活协同」的统计现象，不是一种「连接类型」。 |
| B. 更适合作为？ | **functional observation / evidence candidate**（MACM/ALE 跨研究共激活，Langner et al. 2014），不可自动晋升为 FC。 |
| C. 语义污染？ | **高**。把「两个脑区共同激活」直接建成正式 brain connection，会把任务态的观察性共现当成既定连接。 |
| D. 裁定 | **REMOVE** |

**为什么排除：** 共激活（coactivation）是一种 **functional observation / evidence candidate**，不是独立于 FC 的连接类型。任务书明确：「两个脑区共同激活，不能因为存在 coactivation 就自动建立正式 brain connection。」因此 coactivation 至多作为**证据候选**进入审查流程，不能仅凭自身自动晋升为 FunctionalConnectivity，更绝不作为 ConnectionType 子类。

---

## 2. AssociationConnection（统计关联义）— REMOVE

| 问题 | 结论 |
|---|---|
| A. 是严格意义的 ConnectionType 吗？ | **否**（在旧系统「association」的用法下，指统计关联）。 |
| B. 更适合作为？ | 要么归入 **FunctionalConnectivity**（若指统计关联），要么正名为 **association fibers（联合纤维）** 这一**解剖纤维分类**（见 §6）。 |
| C. 语义污染？ | **极高**。「association」一义双关：既可能是统计关联，又可能是解剖学的「联合纤维」。保留它必然造成歧义。 |
| D. 裁定 | **REMOVE**（统计义直接删除；纤维义转 DEFER，见 §6） |

**为什么排除：** 旧系统 `association` 字段与三元组设计中的 `associated_with` 谓词，本质是「统计/功能关联」的宽松表述，已被 FunctionalConnectivity 覆盖。若有人把它理解为「联合纤维」，那是另一套正交的纤维分类，也不应作为连接类型混入。两个义项都不适合保留为 ConnectionType。

---

## 3. LocalAnatomicalConnection（局部/内在解剖连接）— REMOVE

| 问题 | 结论 |
|---|---|
| A. 是严格意义的 ConnectionType 吗？ | **否**（对 Macro96 而言）。局部/内在连接是**空间尺度**概念，不是连接类型。 |
| B. 更适合作为？ | 微观/介观尺度（within-region / 短程 U-fiber）的空间属性；可用「连接距离/长度」属性表达。 |
| C. 语义污染？ | **中**。在宏观尺度固定（96 个脑区）的连接图上，「局部 vs 长程」不是类型之别，而是尺度之别。 |
| D. 裁定 | **REMOVE** |

**为什么排除：** Macro96 固定在宏观尺度，所有连接都是「脑区 ↔ 脑区」的。局部/内在连接本质是介观/微观尺度概念（单个脑区内部或极短程），不在本图谱范围内。若未来需要，应建模为**属性**（如 connection_length / local vs long-range 轴），而非一个新的 ConnectionType。任务书要求「不要默认加入」。

---

## 4. UnknownConnection / UncertainConnection — REMOVE

| 问题 | 结论 |
|---|---|
| A. 是严格意义的 ConnectionType 吗？ | **否**。「未知 / 不确定」是**认知状态**，不是生物学连接类型。 |
| B. 更适合作为？ | `review_status` / `connection_status` / `assessment_status` / `confidence` / `uncertainty_reason`。 |
| C. 语义污染？ | **高**。把状态当成类型，会让「一个不确定的连接」被误分类为「一种不确定类型的连接」。 |
| D. 裁定 | **REMOVE** |

**为什么排除：** 旧系统的 `uncertain_connection` / `unknown` / `possibly_connects_to` 应全部迁移到状态字段。建立一个 `UnknownConnection` 类等于在生物学类型里塞入一个非生物学范畴，违反任务书 §八「优先考虑通过 review_status / connection_status / assessment_status 表达」。

---

## 5. NOT_CONNECTION_TYPES（明确清单，供 DeepSeek / BioSEPBERT 分类提示词使用）

以下概念**容易被误当成 ConnectionType，但都不是**，应在后续分类提示词中显式排除：

| 概念 | 为什么不是 ConnectionType | 正确归属 |
|---|---|---|
| **coactivation**（共激活） | 任务态跨研究共激活，是统计现象 | FunctionalConnectivity 的 evidence |
| **correlation**（相关） | 一种统计量/度量，不是类型 | FunctionalConnectivity 的度量值 |
| **association**（统计关联） | 与「联合纤维」歧义；宽松统计关联 | FunctionalConnectivity（或纤维分类，见 §6） |
| **unknown / uncertain**（未知/不确定） | 认知状态，非生物学范畴 | review_status / connection_status / confidence |
| **evidence method**（DTI / tracer / fMRI / DCM / Granger） | 证据模态/方法，不是连接类型 | EvidenceType 或 evidence 属性 |
| **fiber tract**（纤维束 / WhiteMatterTract） | 是解剖实体，不是连接类型；DTI tractography 是观测它的方法/证据 | StructuralConnection 的解剖实现（实体） |
| **local / intrinsic**（局部/内在） | 空间尺度，非类型 | 连接长度/尺度属性 |

---

## 6. DEFER（暂缓，未来 Gate 再议，不进 V1）

| 概念 | 说明 | 为什么 DEFER 而非 REMOVE |
|---|---|---|
| **FiberTractConnection** | 指「白质纤维束（WhiteMatterTract）」这一物理实现。 | WhiteMatterTract 是**解剖实体**，DTI tractography 是**方法/证据**；「FiberTract」不是「本身就是证据」，而是「一个由 DTI 等方法重建/定义的解剖实体」。它是 StructuralConnection 的可能「实现子类」候选，但 V1 阶段不建，避免把「解剖实体」与「连接类型」、把「方法」与「证据」混为一谈。 |
| **纤维三分：projection / association / commissural fibers** | 经典白质纤维分类（投射/联合/连合纤维）。 | 是真实的解剖分类，但它是**纤维通路**的分类，正交于「结构/功能/有效」三分，且与统计「association」同名易混。作为未来 `StructuralConnection` 的**属性/子分类**维度再议，不进 V1。 |

---

## 7. RENAME 总结

| 旧名/旧草案 | 裁定 | 说明 |
|---|---|---|
| `structural_connection` | RENAME → `StructuralConnection`（+ altLabel `anatomical connection`） | 正名并对齐标准术语 |
| `association`（统计义） | REMOVE（不保留任何名字） | 已并入 FunctionalConnectivity |
| `association`（纤维义） | DEFER，未来若建则正名为 `AssociationFiberTract` | 与统计义彻底脱钩 |

---

## 8. 裁定总表

| 概念 | 裁定 |
|---|---|
| StructuralConnection | KEEP |
| Projection | KEEP（⊑ StructuralConnection） |
| FunctionalConnectivity | KEEP |
| EffectiveConnectivity | KEEP |
| Coactivation | **REMOVE**（functional observation / evidence candidate） |
| AssociationConnection（统计义） | **REMOVE** |
| LocalAnatomicalConnection | **REMOVE** |
| UnknownConnection / UncertainConnection | **REMOVE**（→ 状态字段） |
| FiberTractConnection | **DEFER** |
| 纤维三分（projection/association/commissural fibers） | **DEFER** |
