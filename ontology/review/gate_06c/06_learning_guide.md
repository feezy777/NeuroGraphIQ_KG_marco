# Gate 6C — 学习版说明（BrainRegion Hierarchy）

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
version: `0.6.1-gate6c`

---

### partOf / 属于

- 是什么：一个脑区在解剖结构上是另一个更大脑区的一部分。
- 例：Hippocampus partOf Medial Temporal Region。
- 容易混：不是 Atlas mapping，也不是 70% spatial overlap。

### subfieldOf / 亚区属于

- 是什么：一个脑区是另一个脑区具有明确科学意义的更细亚区。
- 例：CA1 subfieldOf Hippocampus。
- 关系：subfieldOf 是 partOf 的更具体形式（CA1 subfieldOf Hippocampus ⇒ CA1 partOf Hippocampus）。

### aggregation mapping / 颗粒度聚合映射

- 是什么：NeuroGraphIQ 为了 G4→G3→G2→G1 知识聚合建立的 integration mapping。
- 它不等于 anatomical partOf。
- 只存在数据库 integration layer（brain_region_aggregation_mappings）。

### 快速区分表

| 说法 | 属于哪类 |
|---|---|
| CA1 subfieldOf Hippocampus | anatomical hierarchy（OWL） |
| Julich Region X mapsTo canonical BrainRegion | external atlas mapping（OWL derived + DB） |
| G4 regions aggregate to G3 | granularity roll-up（DB only） |
