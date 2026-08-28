# Gate 4A — Evidence 维度拆分方案

Evidence 必须拆成多个**独立维度**，不能全压进 EvidenceType。本轮只提出方案，不建立 Property。

---

## 1. 六条独立维度

### 1.1 source（来源 / provenance）

证据来自哪里。

| 取值（候选） | 说明 |
|---|---|
| primary_literature | 原始实验论文 |
| review_literature | 综述 |
| database | Allen / Brainnetome / BAMS 等 |
| manual_curation | 人工整理 |
| computational / llm | 模型/LLM 产出 |
| rule_inference | 规则推理产出 |

> 注意：source 轴不等于 EvidenceType（方法轴）。一条 `TracerEvidence` 可以来自 primary_literature，也可以来自 database。

### 1.2 method 维度（三子轴，不互斥）

Evidence 方法维度拆为三根子轴：

| 子轴 | 取值 | 说明 |
|---|---|---|
| acquisition modality（= EvidenceType） | tracer / histology / diffusion_mri / functional_mri / electrophysiology | 采集模态 |
| analysis_method | tractography / correlation / coherence / DCM / SEM / Granger | 分析方式 |
| intervention_method | lesion / TMS / DBS / optogenetics | 干预方式 |

> 一条 Evidence 可同时具有 modality + analysis_method（如 functional_mri + DCM）。PET / genetic_molecular → DEFER。

### 1.3 directness（直接性）

| 取值 | 说明 |
|---|---|
| direct | 直接证据（如 tracer 直接显示 A→B） |
| indirect | 间接证据（如从综述/roll-up 间接推得） |

### 1.4 strength（证据力度）

证据本身的科学支撑力度。

| 取值 | 说明 |
|---|---|
| strong | 强（多项独立实验一致） |
| moderate | 中 |
| weak | 弱 |
| unknown | 未知 |

### 1.5 confidence（系统置信度）

系统对「抽取/映射/判断结果」的置信程度（0–1 或枚举）。

### 1.6 review_status（审核状态）

pending / approved / rejected / needs_revision / not_required。

---

## 2. 关键区分：strength ≠ confidence

| | evidence strength | confidence |
|---|---|---|
| 语义 | 证据**本身**的科学支撑力度 | 系统对**抽取/映射/判断结果**的置信程度 |
| 来源 | 证据固有属性 | 系统计算/评估 |
| 示例 | tracer 金标准 = strong | LLM 抽取 A→B 的置信 0.8 |

**两者必须分开，不能互相当作。**

---

## 3. 关键区分：source ≠ method

| | source | method |
|---|---|---|
| 语义 | 证据来自哪里 | 证据用什么方法获得 |
| 示例 | database（Allen） | tracer |
| 组合 | 一条 database 记录 + tracer method | — |

---

## 4. 关键区分：EvidenceType（method）≠ derivation_type / epistemic_status

| | EvidenceType（method） | derivation_type |
|---|---|---|
| 语义 | 证据的方法类型 | 断言如何产生 |
| 示例 | TracerEvidence | reported（≡ reported_assertion） |

一条 `reported`（来源报道的 Connection）可由多条不同 `EvidenceType`（TracerEvidence + HistologyEvidence）共同支持。

---

## 5. 未来建模建议（本轮不建 Property）

```
Evidence
├── has_source_type : source_type 词表（primary_literature / ...）
├── has_modality : EvidenceType 词表（tracer / histology / diffusion_mri / functional_mri / electrophysiology）
├── has_analysis_method : tractography / correlation / coherence / DCM / SEM / Granger
├── has_intervention_method : lesion / TMS / DBS / optogenetics
├── has_directness : direct / indirect
├── has_strength : strong / moderate / weak / unknown
├── has_confidence : 数值或枚举
└── has_review_status : pending / approved / ...
```

其中 `modality` 轴即推荐作为 **EvidenceType** 的受控词表；analysis_method / intervention_method 及其他是独立 Property（留待 Property Gate）。
