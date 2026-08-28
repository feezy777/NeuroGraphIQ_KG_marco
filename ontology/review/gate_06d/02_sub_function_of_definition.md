# Gate 6D — subFunctionOf Definition

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## subFunctionOf / 是……的下位功能

- **IRI**：`https://neurographiq.org/ontology/human-brain#subFunctionOf`
- **Local name**：subFunctionOf
- **English label**：subfunction of
- **中文 label**：是……的下位功能 / 属于更宽泛功能
- **类型**：owl:ObjectProperty
- **Domain**：Function（不写 CognitiveFunction，一般 Function 也需层级）
- **Range**：Function
- **Representation Role**：CANONICAL

## 定义

- 英文：Relates a canonical Function concept to a broader Function concept when the former represents a more specific functional category or specialization of the latter.
- 中文：一个 canonical Function 概念是另一个更宽泛 Function 概念的更具体功能类别或功能特化。

## 核心语义

narrower function → broader function。

例：
- WorkingMemory subFunctionOf Memory
- SelectiveAttention subFunctionOf Attention
- EpisodicMemory subFunctionOf Memory

## 关键区分

- **subFunctionOf ≠ rdfs:subClassOf**（WorkingMemory/Memory 是 Individual，非 OWL Class）。
- **不复用 partOf**（partOf 已冻结为 BrainRegion anatomical partonomy，Domain/Range = BrainRegion）。
- **不设 TransitiveProperty / inverseOf / propertyChainAxiom**。
