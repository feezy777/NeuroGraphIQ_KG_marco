# Gate 4A — Assertion 模型（多轴拆分）方案

Ontology IRI: `https://neurographiq.org/ontology/macro96`
本轮状态: **仅方案，未写入正式 TTL**

---

## 1. 核心问题：旧 4 值枚举混了三根正交轴

旧 `assertion_type ∈ { reported_fact, inferred, hypothesis, candidate }` 把三根不同轴混成一个枚举：

| 旧值 | 真实所属轴 | 含义 |
|---|---|---|
| reported_fact | **derivation** | 来源如何产生这条 assertion |
| inferred | **derivation** | 系统如何产生这条 assertion |
| hypothesis | **epistemic status** | 当前认识论状态 |
| candidate | **lifecycle / workflow state** | 工作流状态 |

**必须拆开。**

---

## 2. RECOMMENDED ASSERTION MODEL（多轴，本轮只设计不建 Property）

```
Assertion（一条知识陈述）
├── derivation_type / assertion_origin     ← 如何产生
│   ├── reported   (≡ reported_assertion / reported_claim)
│   └── inferred
│
├── epistemic_status                        ← 当前认识论状态
│   ├── hypothesis（未充分验证的命题）
│   └── [其他值 DEFER，待 Property / Data Dictionary Gate]
│
├── lifecycle_status                         ← 工作流状态（workflow 轴，非通用语义轴）
│   ├── candidate
│   ├── promoted
│   └── rejected
│
├── review_status                            ← 审核进展
│   ├── pending
│   ├── approved
│   ├── rejected
│   └── uncertain
│
└── generation_method / provenance           ← 产生机制/工具
    ├── literature_extraction
    ├── database_import
    ├── rule_inference
    ├── deepseek
    ├── biosebbert
    └── human_manual
```

---

## 3. 关键正交性

### 3.1 inferred 与 hypothesis 正交

- `inferred` 描述「这条 assertion **如何产生**」（derivation）。
- `hypothesis` 描述「这条 assertion **当前是什么认识论状态**」（epistemic status）。

一条规则推导的 missing edge 可以**同时**是：

```
derivation_type = inferred
epistemic_status = hypothesis
```

因此 `hypothesis` **不应**和 `inferred` 放在同一个互斥枚举里。

### 3.2 candidate 不是 derivation，也不是 epistemic status

`candidate` 是 **lifecycle / workflow state**，由 `EvidenceCandidate` / `ConnectionCandidate` / `CircuitCandidate` + `lifecycle_status` 表达。

**不得再出现 `assertion_type = candidate`。**

> **lifecycle_status 是 workflow 轴，不是通用语义轴**：candidate / promoted / rejected 主要适用于 workflow entity。是否挂到其他实体留待 Data Dictionary Gate。**不要求** canonical Connection / Circuit 统一保存 lifecycle_status=promoted。

### 3.3 人工审核只改变 review_status，不改变 derivation

删除「human approved → reported_fact」错误规则。

例如：
```
hierarchical roll-up
  derivation_type = inferred
  review_status = approved   ← 审核通过后仍是 inferred
```

只有**来源本身明确报道**该 assertion，才能是 `reported`。

### 3.4 ModelReview 与 HumanReview 独立

review_status 可作为聚合状态，但 **ModelReview approved ≠ HumanReview approved ≠ 自动 canonical promotion**。正式晋升由后续 governance rule 决定。

---

## 4. reported_fact 命名与来源定义重新审查

**命名问题**：来源明确报道某陈述，不代表系统宣称其为绝对 biological fact。

**推荐命名**：
- 用 `reported`（或 `reported_assertion` / `reported_claim`），**不用** `reported_fact`。

**来源定义（reported = 外部来源明确陈述）**：
- `reported` = **外部来源明确陈述该 assertion**。
- 典型来源：**primary literature / review literature / curated（权威）database resource**。
- **删除**「人工明确报道」表述：`human_manual` 属于 generation_method / provenance；`HumanReview` 属于 review process。
- 专家人工提出、但**无外部来源支持**的 assertion，**不能**仅因人工输入而标记为 `reported`。

**兼容性**：若最终因数据库兼容保留 `reported_fact`，其定义必须明确：
> `reported_fact` = source-reported assertion（来源报道的断言），**not** guaranteed biological ground truth（不保证为绝对生物学事实）。

---

## 5. 保持已正确结论

| 概念 | 去向 |
|---|---|
| generated_by_llm_run | → provenance / generation_method |
| confirmed_by_reviewer | → review_status |
| curated_fact | → 不作为独立 assertion_type（= reported + review_status=approved） |
| composed / reconstructed | → Circuit-specific construction_mode |

---

## 6. 待人工审查的关键决策点

1. derivation_type 取值 `{reported, inferred}` 是否合适？
2. `reported` 是否正名为 `reported_assertion`（弃 `reported_fact`），并限定来源为「外部来源明确陈述」（排除无外部来源的纯人工输入）？
3. epistemic_status 是否只正式确认 `hypothesis`，其他值（fact/established/supported/confirmed）一律 DEFER？
4. lifecycle_status 是否定位为 workflow 轴（仅 workflow entity），不要求 canonical 实体统一保存？
5. review_status 是否作为聚合状态，且 ModelReview / HumanReview 保持独立？
6. 是否同意「人工审核只改 review_status，不改 derivation」？
