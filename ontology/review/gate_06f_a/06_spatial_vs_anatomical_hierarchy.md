# Gate 6F-A — Spatial vs Anatomical Hierarchy

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. 严格区分

| 类别 | 语义 | 表达 |
|---|---|---|
| Anatomical hierarchy | CA1 subfieldOf Hippocampus | partOf / subfieldOf（OWL） |
| Spatial relation | A overlaps B / A adjacent B | 几何（DB） |

## 2. 空间 overlap 不等于 anatomical partOf

- G4-A 90% overlap G3-B 不自动 A partOf B。
- 100% geometric containment 也不自动等于 canonical anatomical partOf（除非符合定义+审核）。

## 3. 空间关系不参与 hierarchy traversal

- overlaps / locatedIn / adjacentTo 不参与 ancestor/descendant/hierarchical roll-up。
- 只有 partOf / subfieldOf 是 canonical hierarchy truth。
