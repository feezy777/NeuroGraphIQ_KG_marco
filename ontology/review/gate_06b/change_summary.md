# Gate 6B — Change Summary（ObjectProperty 正式化变更记录）

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
version: `0.5.0-gate5b` → `0.6.0-gate6b`

---

## 1. 版本升级

- version：`0.5.0-gate5b` → `0.6.0-gate6b`
- 状态 comment：Human Brain Core Classes + Core Object Properties（draft — awaiting Protégé relation review）。

## 2. 新增 23 个 ObjectProperty

17 Canonical + 6 Derived（完整清单见 object_property_matrix.md）。

## 3. 新增 3 条 subPropertyOf

- projectsTo ⊑ structurallyConnectedTo
- hasSourceRegion ⊑ hasEndpointRegion
- hasTargetRegion ⊑ hasEndpointRegion

## 4. unionOf

- participatesIn range：Circuit ∪ Function
- modulates domain：Gene ∪ Neurotransmitter；range：BrainRegion ∪ Circuit ∪ Function

## 5. 未做

- 未新增 DataProperty / Individual / AnnotationProperty / Class。
- 未新增 supports / contradicts（DEFER）。
- 未加 inverseOf / Symmetric / Transitive / Functional / property chain / SHACL。

## 6. Class 未变

- 23 个 Named Class 保持不变；Connection hierarchy（Connection → StructuralConnection → Projection / FunctionalConnectivity / EffectiveConnectivity）不变；Function → CognitiveFunction 不变。
