# Gate 6C — subfieldOf Definition

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## subfieldOf / 亚区属于

- **IRI**：`https://neurographiq.org/ontology/human-brain#subfieldOf`
- **类型**：owl:ObjectProperty
- **English label**：subfield of
- **中文 label**：是……的亚区 / 亚区属于
- **Domain**：BrainRegion
- **Range**：BrainRegion
- **定义**：一个 BrainRegion 是另一个较大 BrainRegion 具有明确解剖学意义的细分亚区。
- **Representation Role**：CANONICAL
- **例子**：CA1 subfieldOf Hippocampus

## 与 partOf 的关系

- `subfieldOf rdfs:subPropertyOf partOf`。
- CA1 subfieldOf Hippocampus ⇒ CA1 partOf Hippocampus。

## 边界

- 不设 TransitiveProperty；不表示 overlap / atlas mapping / aggregation。
