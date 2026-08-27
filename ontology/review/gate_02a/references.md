# Gate 2A — References（参考文献）

**引用纪律（严格遵循任务书 §十）：**
- 只记录**经过确认**的来源；未确认的单独列于 Pending References。
- 禁止编造 DOI / PMID / 论文标题。
- 本轮宁可少引用，不伪造引用。

**验证方法：** 以下所有 Verified 引用均通过实时联网检索（WebSearch）核实了标题、期刊、卷期/页码、DOI/PMID。

---

## Verified References（已核实）

### 1. 功能连接 / 有效连接经典定义

**Friston KJ (1994).** Functional and effective connectivity in neuroimaging: a synthesis.
*Human Brain Mapping*, 2(1–2):56–78.
DOI: 10.1002/hbm.460020107.
- 用途：FunctionalConnectivity（"temporal correlations between remote neurophysiological events"）与 EffectiveConnectivity（"the influence one neural system exerts over another"）的**原始定义源**。
- 状态：verified

**Friston KJ (2011).** Functional and effective connectivity: a review.
*Brain Connectivity*, 1(1):13–36.
DOI: 10.1089/brain.2011.0008. PMID: 22432952.
- 用途：FC/EC 20 年综述；DCM、因果建模、有效连接方法学。
- 状态：verified

### 2. 结构连接 / connectome

**Sporns O, Tononi G, Kötter R (2005).** The human connectome: a structural description of the human brain.
*PLoS Computational Biology*, 1(4):e42.
DOI: 10.1371/journal.pcbi.0010042. PMID: 16201007.
- 用途：StructuralConnection 的 connectome「接线图」语义；宏观尺度结构连接是 connectome 草案的可行层次。
- 状态：verified

### 3. 神经解剖示踪（Projection 方向判定的方法学源）

**Lanciego JL, Wouterlood FG (2011).** A half century of experimental neuroanatomical tracing.
*Journal of Chemical Neuroanatomy*, 42(3):157–183.
PMID: 21782932.
- 用途：顺行（anterograde）/逆行（retrograde）示踪方法学；「A projects to B」方向判定的金标准依据。
- 状态：verified

### 4. DTI 纤维追踪的局限性（FiberTract DEFER 的依据）

**Jones DK, Cercignani M (2010).** Twenty-five pitfalls in the analysis of diffusion MRI data.
*NMR in Biomedicine*, 23(7):803–820.
DOI: 10.1002/nbm.1543. PMID: 20886566.
- 用途：论证 DTI 纤维追踪是**间接重建**，存在 crossing fibers / kissing fibers / 部分容积等伪迹，不能等同于经示踪确认的直接解剖连接 → 支持 FiberTractConnection 的 DEFER 结论。
- 状态：verified

### 5. 格兰杰因果（EffectiveConnectivity 方法学源）

**Granger CWJ (1969).** Investigating causal relations by econometric models and cross-spectral methods.
*Econometrica*, 37(3):424–438.
DOI: 10.2307/1912791.
- 用途：Granger causality 的方法学源头，作为 EffectiveConnectivity 证据模态之一。
- 状态：verified

### 6. 共激活 / 元分析连接建模（Coactivation 作为 functional observation / evidence candidate 的依据）

**Langner R, Rottschy C, Laird AR, Fox PT, Eickhoff SB (2014).** Meta-analytic connectivity modeling revisited: controlling for activation base rates.
*NeuroImage*, 99:559–570.
DOI: 10.1016/j.neuroimage.2014.06.007. PMID: 24945668.
- 用途：MACM / ALE / SCALE 跨研究共激活方法；论证 coactivation 是**functional observation / evidence candidate**（不可自动晋升为 FunctionalConnectivity），不是独立连接类型。
- 状态：verified

---

## Pending References（待后续人工/联网确认，本轮不直接用于正式定义）

以下为可能需要补充、但本轮**未联网核实**、因此**不声明为已确认来源**的补充文献。
在正式写入本体（Gate 2B）之前，若需引用，应由人工逐条确认。

1. **Friston KJ, Harrison L, Penny W (2003).** Dynamic causal modelling. *NeuroImage* 19(4):1273–1302. —— DCM 方法原始论文（EffectiveConnectivity 核心方法）。
   - 状态：**pending**（本方案仅在文本中提及 DCM，未直接依赖此条作为定义依据；定义依据已由 Friston 2011 综述覆盖）。

2. **McIntosh AR, Gonzalez-Lima F (1994).** Structural equation modeling and its application to network analysis in functional brain imaging. *Human Brain Mapping* 2(1–2):2–22. —— SEM 在脑成像网络分析的应用。
   - 状态：**pending**（未核实；SEM 已由 Friston 2011 综述覆盖，非本轮必需）。

> 说明：上述两条 Pending 仅作为「未来若需单独引用方法原始论文」的候选，**不影响本轮 4 个 KEEP 类型的定义**，因为所有核心定义均已由 Verified References 中的 Friston (1994/2011)、Sporns et al. (2005)、Lanciego & Wouterlood (2011)、Granger (1969) 覆盖。

---

## 引用诚实性声明

- 本文件 6 条 Verified References 均经过联网核实（标题/期刊/卷期页码/DOI 或 PMID 至少核实其一）。
- **无任何编造 DOI、PMID 或论文标题。**
- 2 条 Pending References 明确标记为 pending，未伪装成已确认来源。
- 若人工审查发现任何一条 Verified 引用细节有误，请在此文件标注并回退为 pending。
