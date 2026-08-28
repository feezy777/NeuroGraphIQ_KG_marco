# Gate 6B Human Review Checklist — Core ObjectProperty Formalization

请逐项确认。本 Gate **已正式写入 TTL**，等待 Protégé 审查。

---

## 审查清单

- [ ] Ontology IRI 保持 `https://neurographiq.org/ontology/human-brain`
- [ ] version 已升级为 `0.6.0-gate6b`
- [ ] Named Class 仍为 23
- [ ] ObjectProperty 为 23
- [ ] DataProperty 为 0
- [ ] Named Individual 为 0
- [ ] owl:imports 为 0
- [ ] 17 个 Canonical ObjectProperty 正确
- [ ] 6 个 Derived ObjectProperty 正确
- [ ] projectsTo subPropertyOf structurallyConnectedTo
- [ ] hasSourceRegion subPropertyOf hasEndpointRegion
- [ ] hasTargetRegion subPropertyOf hasEndpointRegion
- [ ] participatesIn range 使用 owl:unionOf（Circuit ∪ Function）
- [ ] modulates domain 使用 owl:unionOf（Gene ∪ Neurotransmitter）
- [ ] modulates range 使用 owl:unionOf（BrainRegion ∪ Circuit ∪ Function）
- [ ] hasFunction 仅 Circuit → Function
- [ ] FunctionalConnectivity 不伪造 source/target（用 hasEndpointRegion）
- [ ] supports 未写入 TTL
- [ ] contradicts 未写入 TTL
- [ ] 无 ConnectionType / CircuitType / EvidenceType
- [ ] 无 Governance Classes
- [ ] 无 owl:inverseOf
- [ ] 无 owl:SymmetricProperty
- [ ] 无 property chain
- [ ] 无 DataProperty / Individual / AnnotationProperty
- [ ] Connection entity 仍为 canonical truth
- [ ] direct graph relation 仍为 derived
- [ ] 未 commit
- [ ] 未 push

---

## 关键决策点（需人工拍板）

1. **23 个 ObjectProperty 已正式写入，version 0.6.0-gate6b**——是否同意？
2. **仅 3 条 subPropertyOf**（projectsTo、hasSourceRegion、hasTargetRegion）——是否同意？
3. **participatesIn / modulates 用 owl:unionOf**——是否同意？
4. **supports / contradicts 未写入（DEFER）**——是否同意？
5. **未加入 inverseOf / Symmetric / Transitive / property chain**——是否同意？

---

## 审查说明

- 若某项不通过，请在对应行标注，并在 `ontology/review/gate_06b/` 下追加意见。
- 全部通过后，回复 **「Gate 6B 通过」**，方可进入后续 Gate（DataProperty / 关系约束）。
