# Gate 4A Human Review Checklist — NeuroGraphIQ Macro96 EvidenceType / Assertion 模型

请逐项确认。本 Gate **仅产出方案**，未修改正式 TTL。

## 审查清单

- [ ] Evidence 定义合理
- [ ] Publication ≠ Evidence
- [ ] EvidenceCandidate ≠ accepted Evidence
- [ ] EvidenceType 未混入 review status
- [ ] EvidenceType 未混入 confidence
- [ ] EvidenceType 未混入 LLM provenance
- [ ] EvidenceType = 采集模态轴（非互斥枚举）
- [ ] analysis_method / intervention_method 已独立（非 EvidenceType）
- [ ] FunctionalImagingEvidence 已正名为 FunctionalMRIEvidence（PET 移除）
- [ ] GeneticMolecularEvidence 已 DEFER
- [ ] PET 已 DEFER
- [ ] EffectiveConnectivityModelEvidence 已 REMODEL → analysis_method
- [ ] PerturbationEvidence 已 REMODEL → intervention_method
- [ ] HistologyEvidence 已收紧（connection-relevant）
- [ ] tracer 与 tractography 明确分离
- [ ] primary / review source 层级明确
- [ ] DatabaseEvidence 边界明确
- [ ] ComputationalEvidence 边界明确
- [ ] ManualCuratedEvidence 已重新审查
- [ ] evidence strength ≠ confidence
- [ ] derivation_type 定义合理（reported / inferred）
- [ ] epistemic_status 定义合理（仅 hypothesis 正式确认，其他 DEFER）
- [ ] lifecycle_status 定义合理（workflow 轴，candidate / promoted / rejected）
- [ ] review_status 定义合理（聚合，ModelReview / HumanReview 独立）
- [ ] generation_method / provenance 定义合理
- [ ] inferred 与 hypothesis 正交（不互斥）
- [ ] candidate 未错误作为 assertion_type
- [ ] reported 定义 = 外部来源明确陈述（非纯人工输入）
- [ ] 人工审核不改变 derivation（approved 后仍是 inferred）
- [ ] generated_by_llm_run 未错误作为 assertion_type
- [ ] confirmed_by_reviewer 未错误作为 assertion_type
- [ ] curated_fact 未作为独立 assertion_type
- [ ] composed/reconstructed 已合理归类（construction_mode）
- [ ] ECO / PROV-O 使用边界明确
- [ ] 没有伪造 Reference
- [ ] 正式 TTL 未修改

## 关键决策点（需人工拍板）

1. **EvidenceType = 采集模态轴（5 类）**，analysis_method / intervention_method 独立——是否同意？
2. **EffectiveConnectivityModelEvidence → analysis_method**（DCM/SEM/Granger 非模态类，支持多标签）——是否同意？
3. **FunctionalImagingEvidence → FunctionalMRIEvidence**（PET 移除，DEFER）——是否同意？
4. **GeneticMolecularEvidence DEFER**——是否同意？
5. **HistologyEvidence 收紧**（connection-relevant only）——是否同意？
6. **PerturbationEvidence → intervention_method**（不自动生成 EffectiveConnectivity）——是否同意？
7. **多轴拆分**：derivation_type / epistemic_status / lifecycle_status / review_status / generation_method 五轴分离——是否同意？
2. **candidate 移出 assertion_type**（→ lifecycle_status）——是否同意？
3. **inferred 与 hypothesis 正交**（可同时成立）——是否同意？
4. **reported 来源定义**：reported = 外部来源明确陈述（primary/review literature + curated database），排除无外部来源的纯人工输入——是否同意？
5. **epistemic_status 只正式确认 hypothesis**，其他值（fact/established/supported/confirmed）DEFER——是否同意？
6. **lifecycle_status 是 workflow 轴**（非通用语义轴），不要求 canonical 实体统一保存——是否同意？
7. **review_status 为聚合状态**，ModelReview / HumanReview 独立记录——是否同意？
8. **人工审核只改 review_status，不改 derivation**——是否同意？

## 审查说明

- 若某项不通过，请在对应行标注，并在 `ontology/review/gate_04a/` 下追加意见，**不要修改正式 TTL**。
- 全部通过后，回复 **「Gate 4A 通过」**，方可进入 Gate 4B（正式写入 TTL）。
