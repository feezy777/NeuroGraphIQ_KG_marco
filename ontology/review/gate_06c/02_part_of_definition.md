# Gate 6C — partOf Definition

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## partOf / 属于

- **IRI**：`https://neurographiq.org/ontology/human-brain#partOf`
- **类型**：owl:ObjectProperty
- **English label**：part of
- **中文 label**：属于 / 是……的一部分
- **Domain**：BrainRegion
- **Range**：BrainRegion
- **定义**：一个 canonical human BrainRegion 在解剖组成或 canonical anatomical hierarchy 中构成另一个更高层 BrainRegion 的一部分。
- **Representation Role**：CANONICAL
- **例子**：Hippocampus partOf MedialTemporalRegion

## 边界（partOf 不表示）

- 不是 overlap（70% spatial overlap 不写 partOf）。
- 不是 atlas mapping。
- 不是 cross-granularity approximate aggregation。
- 不是 functional participation。

## 逻辑特性

- 本轮**不设** owl:TransitiveProperty；transitivity 留未来 reasoning gate。
