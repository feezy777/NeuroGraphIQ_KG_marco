# Gate 6F-A — spatiallyOverlaps Review

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. 候选语义

两个 BrainRegion 的空间范围存在非零重叠，任一方都不必完全包含另一方。

## 2. 分析

| 维度 | 结论 |
|---|---|
| 是否进入 OWL Core | **否（DB only）** |
| 是否只用于 canonical BrainRegion | 概念上，但重叠事实属于 spatial representation |
| 是否允许同 atlas / 跨 atlas | 跨 atlas 需 registration，重叠随 space 变 |
| 是否只表达 verified overlap | 需 overlap metric / confidence |
| overlap ratio | 数值，属 PostgreSQL |
| symmetric | 语义上 symmetric |
| transitive | **否** |
| 参与 hierarchy | **否** |

## 3. 为什么不进 OWL

- 重叠随 atlas/version/reference space/registration 变化，不是稳定 canonical 解剖事实。
- 需要 overlap ratio / method / confidence 等数值 qualifier，属 DB。
- 两个 canonical region 在 atlas A 重叠、atlas B 不重叠 → BrainRegion-level overlaps 不稳定。

## 4. 结论

spatiallyOverlaps → **PostgreSQL spatial model**（若未来建 brain_region_spatial_relations），不进 OWL V1。
