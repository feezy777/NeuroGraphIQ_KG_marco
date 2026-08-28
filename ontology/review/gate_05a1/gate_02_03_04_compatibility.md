# Gate 5A.1 — Gate 2/3/4A 科学语义兼容性确认

Ontology IRI（当前）: `https://neurographiq.org/ontology/macro96`
本轮状态: **仅确认，未修改正式 TTL**

---

## 1. Gate 2 — ConnectionType 科学语义

- **是否改变**：否。
- StructuralConnection / Projection / FunctionalConnectivity / EffectiveConnectivity 定义**完全保持**。
- 只改变 `rdfs:subClassOf` 的上层表达：父类从 ConnectionType 改为 Connection（subtype model）。
- 具体科学定义（Projection 需 axonal projection 语义、DTI 不能单独判向、EffectiveConnectivity ≠ Projection 等）不变。

## 2. Gate 3 — Circuit 科学语义

- **是否改变**：否。
- 完全保持：biological/functional concept；not graph cycle；not necessarily closed loop；circuit-level evidence 必需；missing edge 仅 candidate/hypothesis。
- 只处理 CircuitType 是否删除（→ REMOVE）。

## 3. Gate 4A — Evidence 多轴模型

- **是否改变**：否。
- 多轴模型（source / acquisition_modality / analysis_method / intervention_method / directness / strength / confidence）保持。
- 只处理 EvidenceType 是否删除（→ REMOVE，多轴优先）。

## 4. 结论

| Gate | 科学语义是否改变 |
|---|---|
| Gate 2 | **否** |
| Gate 3 | **否** |
| Gate 4A | **否** |

本 Gate 5A.1 只决定 OWL 表达方式（Class/Individual/受控词表/Property），不重审任何科学定义。
