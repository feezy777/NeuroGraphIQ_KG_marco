# Gate 4A — EvidenceType vs Assertion 多轴边界矩阵

防止后续数据库字段把不同轴重新混起来。

## 1. 主矩阵

| 概念 | EvidenceType（modality） | derivation_type | epistemic_status | lifecycle_status | review_status | generation_method / provenance | 其他 |
|---|---|---|---|---|---|---|---|
| **TracerEvidence** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | — |
| **reported** | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | — |
| **inferred** | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | — |
| **hypothesis** | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | — |
| **candidate** | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | — |
| **promoted** | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | — |
| **DeepSeek generated** | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | — |
| **human approved** | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | — |
| **Database import** | ❌ | ❌ | ❌ | ❌ | ❌ | ✅（database_import） | — |
| **Review statement** | ❌ | ❌ | ❌ | ❌ | ❌ | ✅（literature_extraction, secondary） | — |
| **composed / reconstructed** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ construction_mode（Circuit-specific） |
| **curated_fact** | ❌ | ❌（REMOVE） | ❌ | ❌ | ❌ | ❌ | = reported + review_status=approved |

## 2. 关键判定规则（多轴）

1. **EvidenceType** = 证据的**采集模态**（TracerEvidence / HistologyEvidence / DiffusionMRIEvidence / FunctionalMRIEvidence / ElectrophysiologyEvidence）。analysis_method（tractography/DCM/SEM/Granger/coherence）与 intervention_method（lesion/TMS/DBS/optogenetics）是独立子轴，**非** EvidenceType。
2. **derivation_type** = 断言如何产生（reported / inferred）。
3. **epistemic_status** = 当前认识论状态（hypothesis，其他待审）。
4. **lifecycle_status** = 工作流状态（candidate / promoted / rejected）；**workflow 轴**，主要适用于 workflow entity，是否挂到其他实体留待 Data Dictionary Gate。
5. **review_status** = 审核进展（pending / approved / rejected / uncertain）；**聚合状态**，ModelReview approved ≠ HumanReview approved ≠ 自动晋升。
6. **generation_method / provenance** = 产生机制/工具（deepseek / rule_inference / database_import / …）。
7. **construction_mode** = Circuit 组装方式（composed / reconstructed），非全局轴。

## 3. 关键正交组合（合法示例）

- `derivation_type = inferred` + `epistemic_status = hypothesis`（规则推导的 missing edge）✅
- `derivation_type = inferred` + `review_status = approved`（roll-up 已通过审核，仍是 inferred）✅
- `derivation_type = reported` + `generation_method = deepseek`（DeepSeek 抽取的文献报道事实）✅

## 4. 反例提醒（旧系统曾混）

- `candidate` 曾被当作 assertion_type → 实为 lifecycle_status。
- `generated_by_llm_run` 曾被当作 assertion_type → 实为 generation_method。
- `confirmed_by_reviewer` 曾被当作 assertion_type → 实为 review_status。
- `curated_fact` 曾被当作 assertion_type → 实为 reported + review_status=approved。
- `reported_fact` 曾把「来源报道」与「绝对事实」绑定 → 正名 reported_assertion。
- `direct/indirect/context/contradictory` 曾被塞进 evidence_type → 实为 directness / strength。
