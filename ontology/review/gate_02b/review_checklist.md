# Gate 2B Human Review Checklist — NeuroGraphIQ Macro96 ConnectionType

请在 Protégé Desktop 中打开 `ontology/neurographiq_macro96_v1.ttl` 逐项确认。

## 审查清单

- [ ] ConnectionType 下只有三个直接子类
- [ ] StructuralConnection 正确
- [ ] Projection 正确位于 StructuralConnection 下
- [ ] FunctionalConnectivity 正确
- [ ] EffectiveConnectivity 正确
- [ ] 中文 label 正确
- [ ] 英文 label 正确
- [ ] StructuralConnection 定义正确
- [ ] Projection 定义正确
- [ ] FunctionalConnectivity 定义正确
- [ ] EffectiveConnectivity 定义正确
- [ ] FiberTractConnection 未加入
- [ ] Coactivation 未加入
- [ ] AssociationConnection 未加入
- [ ] LocalAnatomicalConnection 未加入
- [ ] Unknown/Uncertain 未加入
- [ ] 没有 ObjectProperty
- [ ] 没有 DataProperty
- [ ] 没有 Individual
- [ ] 没有外部 imports
- [ ] 未进入 CircuitType

## 审查说明

- 若某项不通过，请在对应行标注，并在 `ontology/review/gate_02b/` 下追加意见，**不要修改正式 TTL**。
- 全部通过后，回复 **「Gate 2B 通过」**，方可进入后续 Gate（CircuitType / EvidenceType / ObjectProperty 等）。
