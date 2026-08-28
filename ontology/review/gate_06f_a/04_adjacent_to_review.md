# Gate 6F-A — adjacentTo Review

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. 候选语义

两个 BrainRegion 空间边界相邻/直接接触，无明显包含关系。

## 2. 分析

| 维度 | 结论 |
|---|---|
| 是否进入 OWL Core | **否（DB only）** |
| 是否稳定 scientific relation | 弱（强依赖 atlas 边界） |
| 是否依赖 atlas/reference space | 是 |
| 是否 symmetric | 语义上 symmetric |
| 是否 transitive | **否** |
| 是否随 atlas version 改变 | 是 |
| 是否适合 canonical BrainRegion | 不稳定 |
| 前端/推理是否真的需要 | 可能，但可由 DB 几何查询得出 |

## 3. 为什么不进 OWL

- adjacency 高度依赖 atlas 划分边界，随 version 改变。
- 属于 spatial representation 层，不是 canonical 解剖稳定属性。

## 4. 结论

adjacentTo → **PostgreSQL spatial model**，不进 OWL V1。
