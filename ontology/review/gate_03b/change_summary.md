# Gate 3B Change Summary — NeuroGraphIQ Macro96 Ontology V1.0

Ontology IRI: `https://neurographiq.org/ontology/macro96`
Version: `0.2.0-gate2b` → `0.3.0-gate3b`（仍为 draft）

## 本轮修改（Gate 2B → Gate 3B）

正式 TTL `ontology/neurographiq_macro96_v1.ttl` 仅做了**语义写入**，**未新增任何 Class**：

1. **头部注释**更新为 Gate 3B 范围说明。
2. **ontology `rdfs:comment`** 更新为 Gate 3B 范围（新增 Circuit / CircuitType 语义定义，无新类）。
3. **`owl:versionInfo`** 更新为 `0.3.0-gate3b`。
4. **`ngiq:Circuit`** 新增 @en + @zh `rdfs:comment`，写入 Gate 3A 已确认的科学定义（biological/functional 概念、不要求 closed loop、不要求全部 direction known、graph cycle ≠ Circuit、confirmed 需 circuit-level evidence、curation policy、missing-edge 推理边界）。
5. **`ngiq:CircuitType`** 新增 @en + @zh `rdfs:comment`，写入 reserved extension point 状态（无子类、无 individual、当前不用于分类、非 owl:Nothing、Pathway/Loop/Feedforward/Feedback/Recurrent 不作为 CircuitType）。

## 本轮没有做

- **没有新增任何 Class**（业务 Class 总数保持 28 = 24 Gate 1 + 4 Gate 2B）。
- 没有新增 Pathway / Path / Loop / FeedforwardCircuit / FeedbackCircuit / RecurrentCircuit / StructuralCircuit / FunctionalCircuit / NetworkCircuit / Network / UncertainCircuit。
- 没有新增 ObjectProperty / DataProperty / 自定义 AnnotationProperty / Individual / Restriction / EquivalentClass / DisjointClass / SHACL / imports。
- 没有把 curation policy 写成 OWL cardinality / restriction / SHACL。
- 没有把 topology 写成 CircuitType，也没有新增 topology Property。
- 没有修改任何 Gate 2B ConnectionType 语义。
- 没有 commit / push（Gate 3B 待 Protégé 人工验收后单独 commit）。

## 未进入的后续 Gate

- EvidenceType 层级、ObjectProperty / DataProperty（Property Gate）、BrainRegion hierarchy、SHACL、实例层、Validation / SHACL Gate：均未开始。
