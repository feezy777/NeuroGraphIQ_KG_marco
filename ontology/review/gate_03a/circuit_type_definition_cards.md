# Gate 3A — CircuitType 候选定义卡（9 个旧草案概念）

模板遵循任务书 §二十。全部 9 个候选均 **非 KEEP**（0 KEEP / 3 REMOVE / 5 REMODEL / 1 DEFER）。
以下逐卡说明「为什么它不是一个 CircuitType」。

---

## Card 1 — Pathway

**Canonical Name:** Pathway
**Chinese Name:** 通路

**Parent:** (拟) 非 CircuitType；未来或独立 `Path`/`Pathway` 实体（本轮及 Gate 3B 禁止新增）

**Recommended Status:** **REMODEL / DEFER**（future）

**Short Definition:** 开放式有向链（A→B→C→D），描述信号传递的路线。

**Scientific Definition:** 一组按方向顺序排列的脑区，由有向连接串成一条开放链路；它是「信号/信息流经的路径」，不必然构成一个功能闭合单元。

**Topology Requirement:** 开放有向链（无闭合要求）
**Biological Requirement:** 不要求功能闭合或生物回路证据（仅路线）
**Minimum Region Count:** ≥2（路径可仅 3 个节点 A→B→C）
**Minimum Connection Count:** ≥2
**Requires Direction:** yes
**Requires Closed Loop:** no

**Inclusion Criteria:** 有向连接串成顺序链路。
**Exclusion Criteria:** 不要求闭合；不要求作为功能单元被生物证据支持。

**Typical Evidence:** 示踪/图谱的连接链；神经解剖通路（如视交叉上核→外侧膝状体→V1）。
**Typical Literature Expressions:** "pathway", "route", "A→B→C pathway", "mesolimbic pathway".

**Positive Example:** A→B→C 一条投射链（三节点开放链）。
**Counterexample:** A→B→C→A 闭合链——这是 circuit（loop），不是 open pathway。

**Relationship to Other Circuit Types:** 与 Circuit 不是子类关系；开放链是「路线」，circuit 是「功能单元」。
**Relationship to Topology:** Pathway 是拓扑形状（open chain），未来可作为 `topology_type` 取值或独立 `Path` 实体。

**Risk of Misclassification:** 把「所有没有闭环的路径」都叫 Circuit（或都叫 FeedforwardCircuit）。开放链默认是 Pathway，除非有功能单元意义。

**Reference Status:** verified
**References:** Felleman DJ, Van Essen DC (1991). *Cereb Cortex* 1(1):1–47. DOI 10.1093/cercor/1.1.1-a.（feedforward/feedback pathway 层级分类）

---

## Card 2 — Loop

**Canonical Name:** Loop
**Chinese Name:** 环路

**Parent:** (拟) 非 CircuitType；未来 `is_closed_loop` / `functional_loop` 属性

**Recommended Status:** **REMODEL**

**Short Definition:** 闭合的有向环路（A→B→C→A）。

**Scientific Definition:** 闭合的 directed topology（closed loop）。仅描述拓扑闭合，**不**声明其是否为文献支持的 biological loop。

**Topology Requirement:** 闭合有向环
**Biological Requirement:** 若作为「functional loop」需功能证据；仅图闭合不充分
**Minimum Region Count:** ≥3
**Minimum Connection Count:** ≥3（闭合环）
**Requires Direction:** yes
**Requires Closed Loop:** yes

**Inclusion Criteria:** 拓扑闭合 + 生物/功能证据。
**Exclusion Criteria:** 仅图拓扑闭合而无生物证据 → 只是 graph cycle，不是 biological Loop。

**Typical Evidence:** 示踪/功能证据 + 闭合拓扑（如 CSTC loop）。
**Typical Literature Expressions:** "closed loop", "feedback loop", "functional loop".

**Positive Example:** CSTC（皮层→纹状体→丘脑→皮层）——闭合 + 文献支持。
**Counterexample:** 任意三条连接恰好 A→B→C→A 但无文献报道——graph cycle，非 Loop circuit。

**Relationship to Other Circuit Types:** Loop 与 Feedback / Recurrent 是不同层级语义：Loop 是「闭合拓扑」，Feedback 是「调节角色」，Recurrent 是「复发连接」。
**Relationship to Topology:** Loop 本质是拓扑属性（`closed_loop = true`），不是独立生物类型。

**Risk of Misclassification:** 只因为拓扑闭合就自动分类为 Loop（任务书 §六：不能只因为 topology 闭合就自动分类）。

**Reference Status:** verified
**References:** Bullmore E, Sporns O (2009). *Nat Rev Neurosci* 10(3):186–198. DOI 10.1038/nrn2575.（图论：closed loop 是拓扑概念）

---

## Card 3 — FeedforwardCircuit

**Canonical Name:** FeedforwardCircuit
**Chinese Name:** 前馈回路

**Parent:** (拟) 非 CircuitType；未来 `topology_type = feedforward` / connection role

**Recommended Status:** **REMODEL**

**Short Definition:** 无反馈边的前馈有向结构。

**Scientific Definition:** 层级式前向信息流（如 A→B→C，或 A→B + A→C + B→C），无显著反馈边。它是 topology motif，而非独立 biological circuit type。

**Topology Requirement:** 有向，无反馈边（可多级、可分支）
**Biological Requirement:** 不要求（motif 本身不是类型）
**Minimum Region Count:** ≥2
**Minimum Connection Count:** ≥1
**Requires Direction:** yes
**Requires Closed Loop:** no

**Inclusion Criteria:** 前向层级、无反馈。
**Exclusion Criteria:** 含反馈边 → 不是 pure feedforward；「所有无闭环路径」不等于 feedforward circuit。

**Typical Evidence:** 层级通路（Felleman & Van Essen 的 feedforward 层级）。
**Typical Literature Expressions:** "feedforward", "hierarchical", "bottom-up".

**Positive Example:** V1→V2→V4 前馈视觉层级。
**Counterexample:** A→B→C→A（含闭环）——不是 feedforward。

**Relationship to Other Circuit Types:** 与 FeedbackCircuit 互补（一个拓扑的两个方向）。
**Relationship to Topology:** Feedforward 本质是 topology motif，未来作 `topology_type` 取值。

**Risk of Misclassification:** 把「所有没有闭环的路径」都叫 FeedforwardCircuit（任务书 §七：重点防止）。

**Reference Status:** verified
**References:** Felleman DJ, Van Essen DC (1991). *Cereb Cortex* 1(1):1–47.（feedforward/feedback 定义源）

---

## Card 4 — FeedbackCircuit

**Canonical Name:** FeedbackCircuit
**Chinese Name:** 反馈回路

**Parent:** (拟) 非 CircuitType；未来 `topology_type = feedback` / connection role

**Recommended Status:** **REMODEL**

**Short Definition:** 含反馈边（自上而下调控）的有向结构。

**Scientific Definition:** 前向通路之上存在反馈/回归边（如 A→B→C 且 C→A）。反馈是「调节角色」，不是「类型」。

**Topology Requirement:** 有向 + 至少一条反馈边
**Biological Requirement:** 不要求（角色而非类型）
**Minimum Region Count:** ≥3
**Minimum Connection Count:** ≥3
**Requires Direction:** yes
**Requires Closed Loop:** 部分（反馈边常形成闭合，但不必完全闭合）

**Inclusion Criteria:** 存在 feedback 边。
**Exclusion Criteria:** 纯前馈无反馈边。

**Typical Evidence:** 皮层层级中的 feedback connection（Felleman & Van Essen）。
**Typical Literature Expressions:** "feedback", "top-down", "recurrent feedback".

**Positive Example:** 视皮层 V4→V2 的 feedback 投射。
**Counterexample:** V1→V2→V4 纯前馈——不是 feedback circuit。

**Relationship to Other Circuit Types:** Feedback ≠ Loop ≠ Recurrent（见 §八 / type_vs_topology）。
**Relationship to Topology:** Feedback 是拓扑/调节角色，未来作 `has_feedback` / `topology_type`。

**Risk of Misclassification:** 把「有反馈」当成独立类型；反馈是角色，不是生物类别。

**Reference Status:** verified
**References:** Felleman DJ, Van Essen DC (1991). *Cereb Cortex* 1(1):1–47.

---

## Card 5 — RecurrentCircuit

**Canonical Name:** RecurrentCircuit
**Chinese Name:** 复发回路

**Parent:** (拟) 非 CircuitType；未来 `has_recurrence` 属性

**Recommended Status:** **REMODEL**

**Short Definition:** 含复发连接（recurrent connectivity）的结构。

**Scientific Definition:** 连接存在回返/复发（recurrent）性质。注意：A↔B（双向）只是 reciprocal connections，**不自动**构成 circuit。

**Topology Requirement:** 存在复发/相互连接
**Biological Requirement:** 不要求（连接性质而非类型）
**Minimum Region Count:** ≥2（A↔B 即有 recurrent 连接）
**Minimum Connection Count:** ≥2
**Requires Direction:** variable（recurrent 常为双向）
**Requires Closed Loop:** no（recurrent 未必闭合）

**Inclusion Criteria:** 存在 recurrent / reciprocal 连接。
**Exclusion Criteria:** 仅有 A→B 单边无复发。

**Typical Evidence:** 层内 recurrent 连接（Douglas & Martin 2004 的 neocortex 复发连接）。
**Typical Literature Expressions:** "recurrent", "reciprocal", "lateral".

**Positive Example:** 皮层内兴奋性神经元间的 recurrent 连接（微回路，超出 Macro96 尺度）。
**Counterexample:** A↔B 一对双向连接——只是 reciprocal connections，不是 circuit（任务书 §九）。

**Relationship to Other Circuit Types:** Recurrent ≠ Loop（复发 ≠ 闭合）；Recurrent ≠ Feedback（复发连接 ≠ 反馈调控）。
**Relationship to Topology:** Recurrence 是连接性质，未来作 `has_recurrence` 属性。

**Risk of Misclassification:** 因为存在 A→B + B→A 就自动建立 Circuit。

**Reference Status:** verified
**References:** Douglas RJ, Martin KAC (2004). *Annu Rev Neurosci* 27:419–451. DOI 10.1146/annurev.neuro.27.070203.144152.

---

## Card 6 — StructuralCircuit

**Canonical Name:** StructuralCircuit
**Chinese Name:** 结构回路

**Parent:** (拟) 非 CircuitType；未来 `circuit_basis` / `evidence_type`

**Recommended Status:** **REMOVE**

**Short Definition:** 以结构（解剖）证据为基础的 circuit。

**Scientific Definition:** 描述 circuit 的**证据基础**（anatomical evidence），不是 circuit 的「种类」。同一 circuit 可同时有结构证据 + 功能证据。

**Topology Requirement:** 无
**Biological Requirement:** 无（证据维度）
**Minimum Region Count:** n/a
**Minimum Connection Count:** n/a
**Requires Direction:** no
**Requires Closed Loop:** no

**Inclusion Criteria:** n/a（非类型）
**Exclusion Criteria:** n/a

**Typical Evidence:** 示踪/组织学证据支持的 circuit。
**Typical Literature Expressions:** "anatomically defined circuit".

**Positive Example:** 一个既有示踪证据又有功能证据的 circuit——不能据此切分成两个互斥类型。
**Counterexample:** 把「有结构证据」当成与「有功能证据」互斥的分类。

**Relationship to Other Circuit Types:** 与 FunctionalCircuit 是同一 circuit 的两个证据面，不是两个类型（任务书 §十）。
**Relationship to Topology:** 无关（证据维度）。

**Risk of Misclassification:** 复制 ConnectionType 的 Structural/Functional 三分到 CircuitType。

**Reference Status:** pending
**References:** （证据基础建模留待 Evidence Gate）

---

## Card 7 — FunctionalCircuit

**Canonical Name:** FunctionalCircuit
**Chinese Name:** 功能回路

**Parent:** (拟) 非 CircuitType；未来 `circuit_basis` / `evidence_basis`

**Recommended Status:** **REMOVE**

**Short Definition:** 以功能证据/功能解释为基础的 circuit。

**Scientific Definition:** 描述 circuit 的**functional evidence basis**（功能证据基础），不是「种类」，也**不是** `has_function`。`has_function` 专门表达 Circuit 参与的认知/行为/生理 Function，与 structural/functional evidence basis 分离。

**Topology Requirement:** 无
**Biological Requirement:** 无（功能维度）
**Minimum Region Count:** n/a
**Minimum Connection Count:** n/a
**Requires Direction:** no
**Requires Closed Loop:** no

**Inclusion Criteria:** n/a（非类型）
**Exclusion Criteria:** n/a

**Typical Evidence:** 功能影像/任务态证据支持的 circuit。
**Typical Literature Expressions:** "functionally defined circuit".

**Positive Example:** 参与记忆的 circuit——「记忆」是 Function，不是 CircuitType。
**Counterexample:** 建 MemoryCircuit / MotorCircuit / RewardCircuit 作为 V1 类型（类型爆炸，任务书 §十四）。

**Relationship to Other Circuit Types:** 与 StructuralCircuit 是同一 circuit 的两个证据面。
**Relationship to Topology:** 无关。

**Risk of Misclassification:** 把功能名建成 CircuitType。

**Reference Status:** pending
**References:** （功能建模留待 Function / Evidence Gate）

---

## Card 8 — NetworkCircuit

**Canonical Name:** NetworkCircuit
**Chinese Name:** 网络回路

**Parent:** (拟) 非 CircuitType；未来独立 `Network` Class

**Recommended Status:** **DEFER**

**Short Definition:** 把 brain network（如 DMN）当作 circuit 的概念混合。

**Scientific Definition:** Network 与 Circuit 是**不同概念**：Network 大规模、分布式、常为统计/功能连接；Circuit 小规模、有向、组织化功能单元。

**Topology Requirement:** 无
**Biological Requirement:** 无
**Minimum Region Count:** n/a
**Minimum Connection Count:** n/a
**Requires Direction:** no
**Requires Closed Loop:** no

**Inclusion Criteria:** n/a（非 CircuitType）
**Exclusion Criteria:** n/a

**Typical Evidence:** 静息态功能连接定义的网络。
**Typical Literature Expressions:** "default mode network", "salience network".

**Positive Example:** Default Mode Network——是 network，不是 circuit。
**Counterexample:** 把 DMN 因「包含多脑区」自动转成 Circuit（任务书 §十一：Network = Circuit 禁止默认映射）。

**Relationship to Other Circuit Types:** 与 Circuit 平级的不同概念。
**Relationship to Topology:** 无关（概念维度）。

**Risk of Misclassification:** Network = Circuit 默认映射。

**Reference Status:** verified
**References:** Bullmore E, Sporns O (2009). *Nat Rev Neurosci* 10(3):186–198.（brain network 概念）

---

## Card 9 — UncertainCircuit

**Canonical Name:** UncertainCircuit
**Chinese Name:** 不确定回路

**Parent:** (拟) 非 CircuitType；未来 `status` / `assertion_type` / `confidence`

**Recommended Status:** **REMOVE**

**Short Definition:** 不确定的 circuit（认识状态，非生物类型）。

**Scientific Definition:** 「不确定」是认识状态（epistemic state），与 Gate 2A 的 UnknownConnection / UncertainConnection 是同类错误。应通过 status / assertion_type / confidence 表达。

**Topology Requirement:** 无
**Biological Requirement:** 无（状态维度）
**Minimum Region Count:** n/a
**Minimum Connection Count:** n/a
**Requires Direction:** no
**Requires Closed Loop:** no

**Inclusion Criteria:** n/a（非类型）
**Exclusion Criteria:** n/a

**Typical Evidence:** n/a
**Typical Literature Expressions:** "uncertain", "proposed", "candidate".

**Positive Example:** 一个 status=proposed 的 circuit。
**Counterexample:** 建 UncertainCircuit 类 = 把状态当类型。

**Relationship to Other Circuit Types:** 无关。
**Relationship to Topology:** 无关。

**Risk of Misclassification:** 把 candidate / proposed / inferred 建成 CircuitType。

**Reference Status:** pending
**References:** （状态建模留待后续 Gate）
