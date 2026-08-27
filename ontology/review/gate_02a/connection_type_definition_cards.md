# Gate 2A — ConnectionType Definition Cards

每个候选保留类型一张定义卡。模板严格遵循任务书 §九。共 4 张卡：
`StructuralConnection`、`Projection`、`FunctionalConnectivity`、`EffectiveConnectivity`。

---

## Card 1 — StructuralConnection

--------------------------------------------------
**Canonical Name:** StructuralConnection
**Chinese Name:** 结构连接

**Parent:** ConnectionType

**Recommended Status:** KEEP

**Short Definition:**
两个脑区之间存在物理的轴突/纤维通路，即存在真实的神经解剖连接。

**Scientific Definition:**
两个神经群体/脑区之间由物理轴突/纤维通路构成的解剖连接。它是「脑连接」这一抽象概念中最底层、最不依赖统计或模型假设的一类——连接是否成立由「是否存在物理通路」这一事实判定，而非由时间序列相关或有向影响模型判定。

> 注意：StructuralConnection 表示两脑区之间存在**结构性物理通路**，但证据可能不足以确认突触级 directness。由多个中间脑区介导的 polysynaptic / indirect pathway **不应压缩成单条 StructuralConnection**，应由 Path / Circuit / Inference 表达；是否新增 synaptic_directness 属性留到 Property Gate 决定。基于 DTI 的结构连接是间接重建，须保留间接性与误差边界。

**Directionality:** directed / reciprocal / direction_unknown（区分 biological direction 与 evidence-known direction；不使用「undirected」描述生物学结构方向）

**Biological Meaning:**
结构连接是脑网络的物理骨架（physical substrate）。它对应 connectome 意义上的「接线图」（Sporns, Tononi & Kötter 2005）。结构连接提供了信号可沿其传播的物理基础，因而在概念上先于、并约束了功能连接与有效连接。

**Inclusion Criteria:**
- 存在独立的结构证据（逆行/顺行示踪、组织学、DTI 纤维重建、已确认图谱通路）支持两个脑区之间物理通路的存在。
- 连接的方向可以是 directed、reciprocal 或 direction_unknown，只要「物理通路存在」这一事实成立。

**Exclusion Criteria:**
- 仅凭时间序列相关、共激活或统计关联而**没有**独立结构证据的「连接」不属于本类型（那是 FunctionalConnectivity）。
- 仅凭模型推断的有向影响而**没有**独立结构证据的「连接」不属于本类型（那是 EffectiveConnectivity）。

**Typical Evidence:**
- 逆行示踪（retrograde tracer）、顺行示踪（anterograde tracer）
- 组织学 / 神经元染色重建
- DTI / 高角分辨率扩散成像的纤维束追踪（间接，需注意重建伪迹）
- 权威图谱/文献中已确立的纤维通路

**Typical Literature Expressions:**
- "anatomically connected", "structurally connected", "axonal projection pathway", "fiber pathway", "white-matter connection"

**Positive Example:**
胼胝体（corpus callosum）连接左右半球同名皮层区——存在明确的物理纤维束。

**Counterexample:**
两个脑区在静息态 BOLD 时间序列上呈 0.6 的相关，但没有任何示踪/组织学/纤维证据——这是 FunctionalConnectivity，不是 StructuralConnection。

**Relationship to Other Connection Types:**
- 是 `Projection` 的父类（Projection = 有向的结构连接）。
- 与 `FunctionalConnectivity` / `EffectiveConnectivity` 是并列兄弟，互不蕴含。

**Risk of Misclassification:**
把「DTI 纤维追踪重建的流线」直接等同于「经示踪确认的解剖通路」。DTI 是间接重建，存在 crossing fibers / kissing fibers / 部分容积等伪迹（Jones & Cercignani 2010）；应将其视为**结构连接的证据之一**，而非结构性连接的充分证明。另注意：不可把由中间脑区介导的 polysynaptic / indirect pathway 压缩成单条 StructuralConnection——该类多级通路应由 Path / Circuit / Inference 表达。

**Reference Status:** verified

**References:**
1. Sporns O, Tononi G, Kötter R (2005). The human connectome: a structural description of the human brain. *PLoS Comput Biol* 1(4):e42. DOI 10.1371/journal.pcbi.0010042.
2. Lanciego JL, Wouterlood FG (2011). A half century of experimental neuroanatomical tracing. *J Chem Neuroanat* 42(3):157–183. PMID 21782932.
3. Jones DK, Cercignani M (2010). Twenty-five pitfalls in the analysis of diffusion MRI data. *NMR Biomed* 23(7):803–820. DOI 10.1002/nbm.1543.
--------------------------------------------------

---

## Card 2 — Projection

--------------------------------------------------
**Canonical Name:** Projection
**Chinese Name:** 投射

**Parent:** StructuralConnection

**Recommended Status:** KEEP

**Short Definition:**
从源脑区发出并终止于目标脑区的**轴突投射型**有向结构连接（具有明确 source→target 方向）。

**Scientific Definition:**
一组轴突自**源脑区**（神经元胞体/起始处）发出，沿可确认的通路行进并**终止于目标脑区**的有向结构连接。它是「轴突投射型」的结构连接：方向明确是必要条件，但**仅 direction_known 不足以自动分类为 Projection**，仍需 axonal projection 语义/证据。

**Directionality:** directed（always；必有 source→target）

**Biological Meaning:**
「A projects to B」表示 A 向 B 发出传出纤维并形成终止。投射是脑区之间信息单向传递的解剖基础，也是回路（circuit）描述中「步骤 → 步骤」的基本构件。

**Inclusion Criteria:**
- 满足 StructuralConnection 的全部条件（存在物理通路），并且
- 方向可由示踪/已知解剖确定（source 与 target 明确），并且
- 具有 axonal projection 语义/证据（示踪显示轴突自 source 发出并终止于 target）。

**Exclusion Criteria:**
- 物理通路存在但方向无法确定的连接——可记为 `StructuralConnection`，**不可**记为 `Projection`（避免污染方向信息）。
- 仅有模型推断的「有向影响」而无物理通路证据——那是 `EffectiveConnectivity`，不是 Projection。

**Typical Evidence:**
- **顺行示踪**：注入 A → 标记 A 的传出末梢 → B 见标记 ⇒ A→B。
- **逆行示踪**：注入 B → 逆行标记胞体 → A 见标记胞体 ⇒ A→B。
- 顺行 + 逆行联合，或权威图谱已确立的投射通路。

> **关于 DTI / tractography**：纤维追踪可以**辅助支持候选结构通路的存在**，但**不能单独判定 A→B 的轴突投射方向**。afferent / efferent 方向必须依赖 tracer 等**明确方向性证据**。

**Typical Literature Expressions:**
- "A projects to B", "efferent projection from A to B", "A → B projection", "thalamocortical projection", "corticospinal tract"

**Positive Example:**
「左侧海马 → 左侧乳头体」投射：顺行示踪标记海马传出纤维在乳头体见终止；逆行示踪在乳头体注入后在海马见标记胞体——双侧证据共同确认方向。

**Counterexample:**
胼胝体两侧同区连接——两侧相互投射（reciprocal），不具单一 source→target 的轴突投射语义，应记为 reciprocal 的 StructuralConnection，而非 Projection。

**Relationship to Other Connection Types:**
- 是 `StructuralConnection` 的子类（轴突投射型、有明确 source→target 的结构连接）。
- **不等于** `EffectiveConnectivity`：投射是有向的**物理通路**；有效连接是有向的**影响/耦合（模型推断）**，可能是多突触/间接的，二者不可互换。

**Risk of Misclassification:**
把「有向的统计/影响关系」（如 Granger 因果指向 A→B）直接记为 Projection。方向相同不等于物理通路存在；只有独立结构证据才能把方向坐实为投射。

**Reference Status:** verified

**References:**
1. Lanciego JL, Wouterlood FG (2011). A half century of experimental neuroanatomical tracing. *J Chem Neuroanat* 42(3):157–183. PMID 21782932.（顺行/逆行示踪判定方向的方法学依据）
2. Sporns O, Tononi G, Kötter R (2005). The human connectome. *PLoS Comput Biol* 1(4):e42. DOI 10.1371/journal.pcbi.0010042.
--------------------------------------------------

---

## Card 3 — FunctionalConnectivity

--------------------------------------------------
**Canonical Name:** FunctionalConnectivity
**Chinese Name:** 功能连接

**Parent:** ConnectionType

**Recommended Status:** KEEP

**Short Definition:**
两个脑区神经活动之间的统计依赖（时间相关），不隐含物理通路存在。

**Scientific Definition:**
远隔神经生理事件之间的**时间相关性**（Friston 1994: "temporal correlations between remote neurophysiological events"）。它描述的是两个脑区活动在时间上是否协同变化，是对「统计依赖」的刻画，**不声明任何物理/解剖通路**。

**Directionality:** non-directional（V1 默认；核心语义是 statistical dependence）

**Biological Meaning:**
功能连接刻画两个脑区是否「一起工作」，是静息态网络、任务态协同、疾病相关网络改变等研究中的核心度量。它是**观察性/统计性**的，可能由直接结构连接、间接通路、共同输入或共同功能驱动共同导致。

**Inclusion Criteria:**
- 存在统计依赖证据：Pearson 相关、相干（coherence）、偏相关、互信息、相位耦合、包络相关等。
- 模态不限：静息态 fMRI（BOLD 相关）、任务态 fMRI、EEG/MEG 耦合等，均属同一上位概念。

**Exclusion Criteria:**
- 若存在独立结构证据（示踪/组织学/纤维），则该连接应同时/主要记为 `StructuralConnection`（二者可并存，但 FunctionalConnectivity 本身不声明结构）。
- 仅有**有向影响模型**（DCM/Granger）而不声明统计相关的情形——那是 `EffectiveConnectivity`。

**Typical Evidence:**
- 静息态 fMRI 的种子相关 / ICA / 图论度中心性
- 任务态 fMRI 的 PPI（心理生理交互）
- EEG/MEG 的相干、相位同步、包络相关
- MACM/ALE 任务态**跨研究共激活**（coactivation，属 functional observation / evidence candidate，需审查后方可支撑 FC，不可自动晋升）

**Typical Literature Expressions:**
- "functionally connected", "functional coupling", "BOLD correlation", "coherent activity", "co-activation across studies"

**Positive Example:**
静息态下左右初级运动皮层的 BOLD 时间序列高度相关——典型的功能连接（其结构基础很可能是胼胝体，但 FC 证据本身不证明这一点）。

**Counterexample:**
把「BOLD 相关 0.6」直接登记为「结构连接」——错误，功能相关 ≠ 结构通路（除非另有独立结构证据）。

**Relationship to Other Connection Types:**
- 与 `StructuralConnection` 并列，互不蕴含：**FunctionalConnectivity ≠ StructuralConnection**（除非另有独立结构证据）。
- 与 `EffectiveConnectivity` 并列：FC 是「无方向的统计依赖」，EC 是「有方向的模型影响/耦合」。

**Risk of Misclassification:**
1) 把功能连接自动解释为解剖连接（最常见的语义污染）；2) 把「共激活」（coactivation）建成独立类型——它是 FC 的证据形式，不是新类型。

**Reference Status:** verified

**References:**
1. Friston KJ (1994). Functional and effective connectivity in neuroimaging: a synthesis. *Hum Brain Mapp* 2(1–2):56–78. DOI 10.1002/hbm.460020107.
2. Friston KJ (2011). Functional and effective connectivity: a review. *Brain Connectivity* 1(1):13–36. DOI 10.1089/brain.2011.0008.
3. Langner R, Rottschy C, Laird AR, Fox PT, Eickhoff SB (2014). Meta-analytic connectivity modeling revisited: controlling for activation base rates. *NeuroImage*. DOI 10.1016/j.neuroimage.2014.06.007.（coactivation 作为 FC 元分析证据）
--------------------------------------------------

---

## Card 4 — EffectiveConnectivity

--------------------------------------------------
**Canonical Name:** EffectiveConnectivity
**Chinese Name:** 有效连接

**Parent:** ConnectionType

**Recommended Status:** KEEP

**Short Definition:**
一个神经系统对另一个系统施加的有向影响（directed influence / directed coupling），以交互模型的形式表达。

**Scientific Definition:**
「一个神经系统对另一个神经系统施加的影响，直接的或间接的，以系统间交互模型的形式表达」（Friston 1994: "the influence one neural system exerts over another, either directly or indirectly, in terms of a model of the interactions"）。它是**模型依赖的、有向的**影响/耦合（directed influence / directed coupling）描述，回答「A 是否影响 B」而非「A 与 B 是否物理相连」。causal interpretation 取决于具体方法、模型假设与实验设计。

**Directionality:** directed（always；有向影响/耦合有方向）

**Biological Meaning:**
有效连接刻画的是脑区之间的**有向影响/耦合关系**，是理解信息在脑网络中的定向流动、以及疾病状态下定向通路改变的关键。它建立在特定生成模型或时间模型之上；causal interpretation 取决于具体方法、模型假设与实验设计。

**Inclusion Criteria:**
- 存在模型驱动的有向影响/耦合证据：DCM、Granger causality、结构方程模型 SEM、干预/扰动（TMS、损伤、光遗传/化学遗传）。
- 结果是「A 对 B 的有向影响」这一陈述。

**Exclusion Criteria:**
- 仅有物理通路证据而无有向影响模型——那是 `StructuralConnection` / `Projection`。
- 仅有无方向统计相关——那是 `FunctionalConnectivity`。

**Typical Evidence:**
- DCM（动态因果建模）
- Granger causality（格兰杰因果）
- SEM（结构方程模型）
- 干预/扰动：TMS、病变-行为映射、光遗传、化学遗传

**Typical Literature Expressions:**
- "effective connectivity", "causal influence", "directed influence", "A drives B", "Granger-causal from A to B"

**Positive Example:**
DCM 模型显示视觉区 V1 对 V5 存在有向的调制影响——这是 EffectiveConnectivity（有向影响/耦合），但不声明 V1 与 V5 之间是否有直接解剖投射。

**Counterexample:**
把「DCM 显示 A→B 有向影响」直接登记为「A→B 的解剖投射（Projection）」——错误，有向影响可能是多突触/间接的。

**Relationship to Other Connection Types:**
- **EffectiveConnectivity ≠ Projection**（有向影响/耦合 ≠ 有向解剖投射）。
- **EffectiveConnectivity ≠ StructuralConnection**（除非另有独立结构证据）。
- 与 `FunctionalConnectivity` 并列（FC 无方向统计 / EC 有方向模型）。

**Risk of Misclassification:**
把有向有效连接自动解释为结构连接或投射。模型推断的是「影响」，不是「通路」；二者必须用独立证据分别判定。

**Reference Status:** verified

**References:**
1. Friston KJ (1994). Functional and effective connectivity in neuroimaging: a synthesis. *Hum Brain Mapp* 2(1–2):56–78. DOI 10.1002/hbm.460020107.
2. Friston KJ (2011). Functional and effective connectivity: a review. *Brain Connectivity* 1(1):13–36. DOI 10.1089/brain.2011.0008.（DCM / 有效连接综述）
3. Granger CWJ (1969). Investigating causal relations by econometric models and cross-spectral methods. *Econometrica* 37(3):424–438. DOI 10.2307/1912791.（Granger causality 方法学源）
--------------------------------------------------
