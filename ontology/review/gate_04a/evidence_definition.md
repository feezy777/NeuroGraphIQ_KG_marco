# Gate 4A — Evidence 定义

Ontology IRI: `https://neurographiq.org/ontology/macro96`
本轮状态: **仅科学语义分析，未写入正式 TTL**

---

## 1. 必须区分的概念轴（多轴）

| 轴 | 含义 | 示例 |
|---|---|---|
| **Evidence** | 一条具体证据记录 | 论文 X 的 tracer 结果支持 A→B |
| **EvidenceType** | 证据的采集模态（acquisition modality） | TracerEvidence、DiffusionMRIEvidence |
| **derivation_type / assertion_origin** | 断言如何产生 | reported / inferred |
| **epistemic_status** | 当前认识论状态 | hypothesis |
| **lifecycle_status** | 工作流状态 | candidate / promoted / rejected |
| **provenance / generation source** | 记录从哪里、经什么流程产生 | DeepSeek、rule_inference、manual |
| **review / validation status** | 审核进展 | pending、approved、rejected |

**关键结论：这些轴不是一回事，不能混在同一个字段里。**

- TracerEvidence → **EvidenceType**（方法）
- reported / inferred → **derivation_type**
- hypothesis → **epistemic_status**
- candidate → **lifecycle_status**
- DeepSeek → **provenance / model**，不是 derivation_type
- human reviewed → **review_status**，不是 derivation_type
- high confidence → **confidence**，不是 derivation_type

---

## 2. Evidence 定义

**Evidence（证据）** = 某个来源中的**具体证据单元**，用于支持或反驳某个 Connection / Circuit / Mapping / Function assertion。

- Evidence **不是** PMID / DOI / 整篇论文 / 数据库名称。
- Evidence 更接近「某来源中支持某条断言的具体证据片段」。

### 2.1 Evidence 最低语义（未来建模，本轮不新增 Property）

- Publication / source（来源）
- evidence text / context（证据文本/上下文）
- method（方法，如 tracer / fMRI）
- species（物种）
- source region / target region（源/目标脑区）
- direction（方向，若适用）
- evidence strength（证据力度）
- supports / contradicts（支持/反驳）
- review status（审核状态）

---

## 3. 三个关键区分

### 3.1 Publication ≠ Evidence

一篇 Publication 可以产生**多条 Evidence**（不同脑区对、不同方法、不同结论）。

### 3.2 EvidenceCandidate ≠ accepted Evidence

- **EvidenceCandidate** = 待验证的候选证据（如 LLM 抽取但未经验证）。
- **Evidence**（accepted）= 已通过验证、可用于支持断言的证据记录。

### 3.3 Evidence ≠ assertion（被支持的对象）

Evidence 支持 assertion（Connection/Circuit/Mapping/Function），但本身不是 assertion。

---

## 4. 与 ECO 的对齐（参考，不 import）

Evidence & Conclusion Ontology（ECO）自身把 evidence 分为两大高层类：
- **evidence** —— "a type of information used to support an assertion"
- **assertion method** —— "a means by which a statement is made about an entity"

这印证了本方案：**证据的「内容/方法」与「产生方式/来源」是两个不同轴**，不应混在同一个 EvidenceType 树里。
