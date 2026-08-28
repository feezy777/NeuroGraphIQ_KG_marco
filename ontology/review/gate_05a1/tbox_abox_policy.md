# Gate 5A.1 — TBox / ABox Policy（延续 Gate 5A，不得推翻）

Ontology IRI（当前）: `https://neurographiq.org/ontology/macro96`
本轮状态: **仅记录，未修改正式 TTL**

---

## 1. 原则

- **TBox（Class）** = ontology category（概念类型）。
- **ABox（Individual）** = canonical knowledge concept（真实实例）。

## 2. 实例策略对照表

| Class | Individual 示例 |
|---|---|
| BrainRegion | CA1 |
| Connection | CONN_001（rdf:type Projection） |
| Circuit | PapezCircuit |
| Gene | APOE |
| Disease | AlzheimerDisease |
| Neurotransmitter | Dopamine |
| Receptor | D2Receptor |
| Function（CognitiveFunction） | WorkingMemory |
| Atlas | JulichBrainAtlas |
| Publication / Evidence | 具体 PMID / 具体 Evidence |

## 3. 与本 Gate 决策的一致性

- Connection subtype model 与 TBox/ABox 一致：CONN_001 是 Individual，`rdf:type Projection`（Class）。
- 删除 ConnectionType / CircuitType / EvidenceType 后，不再需要「类型词表 Individual」的 punning。
- 外部 ontology（MONDO/HPO/ChEBI/Uberon）可能把 biomedical concept 建模为 OWL Class；**NGIQ 不必复制其 Class semantics**。NGIQ canonical concept = Individual，用未来 mapping（external_id / source ontology / exactMatch / closeMatch / mapped_to）表达对应。

## 4. 禁止

- 禁止未经审查用 `owl:equivalentClass` 跨 NGIQ Individual 与外部 OWL Class。
- 禁止在 Gate 5A.1 推翻此 TBox/ABox policy。

## 5. 结论

| 项 | 决策 |
|---|---|
| TBox/ABox policy 是否保持 | 是 |
| BrainRegion instance policy | Individual（CA1） |
| Connection instance policy | Individual（CONN_001 rdf:type Projection） |
| Circuit instance policy | Individual（PapezCircuit） |
| Gene/Disease/Neurotransmitter/Receptor | Individual（APOE / AlzheimerDisease / Dopamine / D2Receptor） |
