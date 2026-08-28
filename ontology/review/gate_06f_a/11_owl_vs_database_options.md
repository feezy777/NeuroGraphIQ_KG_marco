# Gate 6F-A — OWL vs Database Options

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. 方案比较

| 方案 | 内容 | 评估 |
|---|---|---|
| A | OWL：spatiallyOverlaps + adjacentTo；locatedIn DEFER | 空间关系 atlas 依赖强，不适合 OWL |
| B | OWL：仅 spatiallyOverlaps；adjacentTo/locatedIn DB | 仍需 ratio/version，OWL 不稳 |
| C | OWL：不新增 spatial relation；全部 PostgreSQL | ✅ 科学合理 |
| D | 其他 minimal model | — |

## 2. 推荐：Option C

- OWL V1 不新增任何 spatial relation。
- overlap / adjacency / containment 全部放 PostgreSQL spatial model。
- 不新增 SpatialRepresentation OWL Class。

## 3. 判断标准（进 OWL 须满足）

1. 语义稳定；2. BrainRegion domain 合理；3. 不与 partOf/subfieldOf 重复；4. 不依赖过多数值 qualifier；5. 有明确 scientific use case；6. 可独立理解；7. 不误导 hierarchy；8. 对 query/reasoning 长期有价值。

spatiallyOverlaps / adjacentTo / locatedIn 均**不满足**这些标准（依赖 atlas/version/space + 数值 qualifier）。
