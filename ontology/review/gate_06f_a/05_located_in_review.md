# Gate 6F-A — locatedIn Review

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. 候选语义

BrainRegion A 空间上位于 B 内。

## 2. 与 partOf 的关系

- CA1 locatedIn Hippocampus 科学上更自然其实是 CA1 subfieldOf Hippocampus。
- locatedIn 若只是"空间 containment"而不表 anatomical partonomy，需要独立稳定示例。
- 若无法提供"A locatedIn B 但 A NOT partOf B"的明确人脑 BrainRegion 场景 → locatedIn 无独立价值。

## 3. 结论

- **locatedIn 不进入 V1 OWL Core**（REMOVE / DEFER）。
- 它会被理解为 partOf 的弱版本，污染 hierarchy reasoning。
- 几何 containment 属于 SpatialRepresentation 层（DB），不建 BrainRegion→BrainRegion locatedIn 关系。

## 4. 禁止

- 不把 locatedIn 设计成"弱包含"的 partOf 版本。
