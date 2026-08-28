# Gate 4A — Assertion 模型定义卡（多轴）

旧单一 `assertion_type` 枚举已拆为多轴。以下按轴给出定义卡。

---

## Axis 1 — derivation_type / assertion_origin

### Card 1a — reported（≡ reported_assertion / reported_claim）

- **Canonical Name:** reported（reported_assertion / reported_claim）
- **中文:** 来源报道
- **Axis:** derivation_type
- **Status:** KEEP
- **定义:** 外部来源（primary literature / review literature / curated 权威 database resource）明确陈述该 assertion。**不宣称**其为绝对 biological ground truth。
- **Distinguishes From:** inferred（系统推导，非来源报道）。
- **来源边界:** `human_manual` 属于 generation_method / provenance；`HumanReview` 属于 review process。专家人工提出但**无外部来源支持**的 assertion，**不能**仅因人工输入标记为 `reported`。
- **Positive Example:** 论文 tracer 明确报道 A→B → derivation_type = reported。
- **Counterexample:** 子区连接 roll-up → derivation_type = inferred（非 reported）。
- **命名注意:** 弃 `reported_fact`（「fact」过度宣称）。若兼容保留 `reported_fact`，必须定义为 source-reported assertion，不保证生物学事实。

### Card 1b — inferred

- **Canonical Name:** inferred
- **中文:** 规则推导
- **Axis:** derivation_type
- **Status:** KEEP
- **定义:** 系统依据已知知识 + 规则推导出的 assertion（roll-up / abstraction / graph inference）。
- **Distinguishes From:** reported（来源报道）。
- **Positive Example:** Hippocampus 子区→PFC roll-up → derivation_type = inferred。
- **注意:** inferred 与 epistemic_status=hypothesis **可同时成立**（见 Axis 2）。

---

## Axis 2 — epistemic_status

### Card 2a — hypothesis

- **Canonical Name:** hypothesis
- **中文:** 科学假设
- **Axis:** epistemic_status
- **Status:** KEEP
- **定义:** 尚未获得充分证据支持、需验证的候选命题。
- **Distinguishes From:** 不是 derivation（inferred 可与 hypothesis 并存）；不是 lifecycle（candidate）。
- **Positive Example:** 规则推导的 missing edge C→A → derivation_type = inferred, epistemic_status = hypothesis。
- **DEFER:** 本 Gate **只正式确认 hypothesis**。不新增 fact / established / supported / confirmed（可能与 evidence_strength / review_status / validation_status 重叠）。其他 epistemic_status 值标记 **DEFER**，留待 Property / Data Dictionary Gate。

---

## Axis 3 — lifecycle_status

> **workflow 轴（非通用语义轴）**：candidate / promoted / rejected 主要适用于 workflow entity（EvidenceCandidate / ConnectionCandidate / CircuitCandidate）。是否挂到其他实体留待 Data Dictionary Gate。**不要求** canonical Connection / Circuit 统一保存 lifecycle_status=promoted。

### Card 3a — candidate

- **Canonical Name:** candidate
- **中文:** 待验证候选
- **Axis:** lifecycle_status（**非** assertion_type / derivation）
- **定义:** 工作流中尚未验证/晋升的候选状态（由 EvidenceCandidate / ConnectionCandidate / CircuitCandidate 表达）。
- **Distinguishes From:** 不是 derivation，不是 epistemic status。
- **Positive Example:** DeepSeek 抽取未验证的 A→B → lifecycle_status = candidate。

### Card 3b — promoted

- **Canonical Name:** promoted
- **中文:** 已晋升
- **Axis:** lifecycle_status
- **定义:** 已晋升到 canonical 层。

### Card 3c — rejected

- **Canonical Name:** rejected
- **中文:** 已驳回
- **Axis:** lifecycle_status
- **定义:** 已驳回。

---

## Axis 4 — review_status

| 值 | 中文 | 说明 |
|---|---|---|
| pending | 待审核 | 未审核 |
| approved | 已通过（聚合） | ModelReview / HumanReview 的聚合状态 |
| rejected | 已拒绝 | 被驳回 |
| uncertain | 不确定 | 审核结论不确定 |

> **ModelReview 与 HumanReview 独立**：review_status 可作为聚合状态，但 **ModelReview approved ≠ HumanReview approved ≠ 自动 canonical promotion**。正式晋升由后续 governance rule 决定。
> **注意**：review_status **不改变** derivation_type。`inferred + approved` 审核通过后仍是 inferred。

---

## Axis 5 — generation_method / provenance

| 值 | 说明 |
|---|---|
| literature_extraction | 文献抽取 |
| database_import | 数据库导入 |
| rule_inference | 规则推理 |
| deepseek | DeepSeek 生成 |
| biosebbert | BioSEPBERT 生成 |
| human_manual | 人工/手动 |

> 注意：generation_method 描述「用什么工具/机制产生」，**不是** derivation_type（reported/inferred 是认识论来源，generation_method 是机制）。

---

## 已移除的旧单一枚举值

| 旧值 | 新归属 |
|---|---|
| reported_fact | → derivation_type = reported（正名 reported_assertion） |
| inferred | → derivation_type = inferred |
| hypothesis | → epistemic_status = hypothesis |
| candidate | → lifecycle_status = candidate |
