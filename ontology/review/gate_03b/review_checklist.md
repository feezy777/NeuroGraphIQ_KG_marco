# Gate 3B Human Review Checklist — NeuroGraphIQ Macro96 Circuit / CircuitType

请在 Protégé Desktop 中打开 `ontology/neurographiq_macro96_v1.ttl` 逐项确认。

## 审查清单

- [ ] Circuit Class 层级未改变
- [ ] Circuit 中文/英文 label 正确
- [ ] Circuit 科学定义正确
- [ ] Circuit 不要求 closed loop
- [ ] graph cycle ≠ biological Circuit
- [ ] Circuit 不要求所有 Connection direction known
- [ ] confirmed Circuit 需要 circuit-level evidence
- [ ] inferred/composed/hypothesis 不自动晋升 confirmed
- [ ] ≥3 Region + ≥2 Connection 只是 Macro96 curation policy
- [ ] literature-reported exception 已保留
- [ ] CircuitType 无子类
- [ ] CircuitType 无 Individual
- [ ] CircuitType 是 reserved extension point
- [ ] CircuitType 不是 owl:Nothing
- [ ] Pathway 未新增
- [ ] Loop 未新增
- [ ] FeedforwardCircuit 未新增
- [ ] FeedbackCircuit 未新增
- [ ] RecurrentCircuit 未新增
- [ ] StructuralCircuit 未新增
- [ ] FunctionalCircuit 未新增
- [ ] NetworkCircuit 未新增
- [ ] UncertainCircuit 未新增
- [ ] ObjectProperty = 0
- [ ] DataProperty = 0
- [ ] Individual = 0
- [ ] ConnectionType hierarchy 未改变
- [ ] 未进入 Gate 4

## 审查说明

- 若某项不通过，请在对应行标注，并在 `ontology/review/gate_03b/` 下追加意见，**不要修改正式 TTL**。
- 全部通过后，回复 **「Gate 3B 通过」**，方可进入后续 Gate（EvidenceType / ObjectProperty / DataProperty 等）。
