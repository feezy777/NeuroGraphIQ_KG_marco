# Gate 6F-B — Anatomical vs Spatial Relations

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. 两类不同命题

| 类别 | 例子 | 语义 |
|---|---|---|
| Anatomical hierarchy | CA1 subfieldOf Hippocampus | 解剖组成 |
| Spatial containment | Geometry A 100% 位于 Geometry B 内 | 几何包含 |

## 2. 关键冻结

- 100% geometric containment 不自动推出 partOf（需 anatomical/canonical evidence + 审核）。
- 90% overlap 不自动 partOf / subfieldOf（overlap ratio 只是 spatial/integration evidence）。

## 3. 边界

- partOf / subfieldOf = canonical anatomical hierarchy（OWL）。
- spatial overlap / adjacency / containment = geometry（DB）。
