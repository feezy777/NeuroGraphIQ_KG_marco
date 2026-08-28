# Gate 6F-B — locatedIn Freeze

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. 状态：REMOVE / DEFER

V1 不进入 OWL。

## 2. 原因

BrainRegion→BrainRegion 的 locatedIn 容易成为 partOf 的弱化版本（CA1 locatedIn Hippocampus 不如 CA1 subfieldOf Hippocampus 清楚）。若仅表 geometric containment，则属 SpatialRepresentation 层。

## 3. 禁止污染 hierarchy

- 禁止 locatedIn subPropertyOf partOf（及反向）。
- locatedIn 不属于 V1 relation vocabulary。
