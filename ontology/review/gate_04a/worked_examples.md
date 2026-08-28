# Gate 4A — 工作示例（多轴模型）

9 个真实风格示例，展示各概念轴如何组合。所有示例遵守多轴模型。

> epistemic_status 仅正式确认 `hypothesis`；非 hypothesis 示例中该行标为「暂无正式值（DEFER）」。

---

## 例 1：论文 tracer 明确报道 A→B

- **EvidenceType:** TracerEvidence（modality = tracer）；source_level = primary；strength = strong
- **Assertion:** Connection A→B
- **derivation_type:** reported（来源报道）
- **epistemic_status:** （除 hypothesis 外暂无正式值，DEFER）
- **review_status:** approved（若人工已确认）
- **generation_method:** literature_extraction

## 例 2：由 Hippocampus 子区连接向 Macro96 roll-up

- **Evidence:** 原始 reported evidence（子区连接）
- **Assertion:** Hippocampus→PFC
- **derivation_type:** inferred（规则 roll-up）
- **inference_type:** hierarchical_rollup
- **epistemic_status:** hypothesis（若未充分验证）／其他值 DEFER
- **review_status:** 视审核

## 例 3：Circuit 缺失边

- **Evidence:** circuit-level evidence 表明 A→B→C→A，但缺 C→A
- **Assertion:** C→A
- **derivation_type:** inferred（由 circuit-level evidence 推导）
- **epistemic_status:** hypothesis（未充分验证）
- **lifecycle_status:** candidate
- **（不能）:** derivation_type = generated_by_llm_run

## 例 4：DTI 结构连接

- **EvidenceType:** DiffusionMRIEvidence（modality = diffusion_mri）＋ analysis_method = tractography；indirect；strength = moderate
- **Assertion:** StructuralConnection A→B
- **derivation_type:** reported（若来自文献）或 inferred（若本系统 tractography 复算）
- **epistemic_status:** （除 hypothesis 外暂无正式值，DEFER）
- **direction:** 不可由 DTI 单独判定

## 例 5：fMRI 功能连接

- **EvidenceType:** FunctionalMRIEvidence（modality = functional_mri）
- **Assertion:** FunctionalConnectivity A→B
- **derivation_type:** reported（若来自文献）
- **epistemic_status:** （除 hypothesis 外暂无正式值，DEFER）
- **注意:** 不隐含 StructuralConnection

## 例 6：DCM 有效连接

- **EvidenceType:** FunctionalMRIEvidence（modality = functional_mri）＋ analysis_method = DCM
- **Assertion:** EffectiveConnectivity A→B
- **derivation_type:** reported（若来自文献）或 inferred（若本系统复算）
- **epistemic_status:** （除 hypothesis 外暂无正式值，DEFER）

## 例 7：综述论文陈述

- **EvidenceType:** literature statement（method = literature；source_level = secondary；strength = weak）
- **Assertion:** Connection A→B
- **derivation_type:** reported（来源报道，但 directness/strength 弱于 primary）
- **generation_method:** literature_extraction

## 例 8：数据库导入断言

- **EvidenceType:** database record（source_type = database）
- **Assertion:** Connection A→B
- **derivation_type:** reported（来源报道）
- **generation_method:** database_import
- **要求:** 尽量追原始 evidence/reference；不能「database says yes」等同 primary tracer evidence

## 例 9：DeepSeek 审核的证据候选

- **Evidence:** DeepSeek 抽取的 A→B（尚未验证）
- **Assertion:** A→B（mirror 层）
- **derivation_type:** reported 或 inferred（视抽取语义）
- **epistemic_status:** 视抽取结论
- **lifecycle_status:** candidate（**非** derivation_type）
- **generation_method:** deepseek（**非** assertion 轴）
- **review_status:** pending
- **去向:** EvidenceCandidate → ModelReview → HumanReview

---

## 关键组合总结

| 组合 | 是否合法 |
|---|---|
| inferred + hypothesis | ✅（规则推导的未验证命题） |
| inferred + approved | ✅（roll-up 已审核，仍是 inferred） |
| reported + deepseek | ✅（DeepSeek 抽取的文献报道事实） |
| reported + rejected | ✅（来源报道但被驳回） |
| candidate 作为 derivation_type | ❌（candidate 是 lifecycle） |
| generated_by_llm_run 作为 derivation_type | ❌（是 generation_method） |
