# Gate 6B — Validation Report（正式化验证报告）

对 `ontology/neurographiq_macro96_v1.ttl` 的验证结果。

---

## 1. 元数据

| 项 | 期望 | 实际 |
|---|---|---|
| Ontology IRI | `https://neurographiq.org/ontology/human-brain` | ✅ |
| version | `0.6.0-gate6b` | ✅ |
| Named Class | 23 | ✅ |
| ObjectProperty | 23 | ✅ |
| DataProperty | 0 | ✅ |
| Named Individual | 0 | ✅ |
| owl:imports | 0 | ✅ |

## 2. Property hierarchy（3 条）

- [x] projectsTo subPropertyOf structurallyConnectedTo
- [x] hasSourceRegion subPropertyOf hasEndpointRegion
- [x] hasTargetRegion subPropertyOf hasEndpointRegion

## 3. 不存在（验证通过）

- [x] 无 supports / contradicts
- [x] 无 ConnectionType / CircuitType / EvidenceType
- [x] 无 ConnectionAssessment / ConceptDefinition
- [x] 无 Governance Classes（Candidate/SearchRun/ExtractionRun/ModelReview/HumanReview/InferenceRecord/ValidationRecord）

## 4. unionOf 正确性

- [x] participatesIn range = Circuit ∪ Function（owl:unionOf，非多 rdfs:range）
- [x] modulates domain = Gene ∪ Neurotransmitter（owl:unionOf）
- [x] modulates range = BrainRegion ∪ Circuit ∪ Function（owl:unionOf）

## 5. 未加入的复杂特性

- [x] 无 owl:inverseOf / SymmetricProperty / TransitiveProperty / FunctionalProperty / propertyChainAxiom / cardinality / SHACL

## 6. Canonical / Derived 统计

- Canonical：17；Derived：6；总计：23。

## 7. 结论

**Gate 6B Core ObjectProperty 正式写入完成（0.6.0-gate6b），等待 Protégé 人工审查。**
