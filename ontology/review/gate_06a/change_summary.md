# Gate 6A — Change Summary（关系设计变更记录）· 第二轮修订

Ontology IRI: `https://neurographiq.org/ontology/human-brain`（version `0.5.0-gate5b`，未改）
本轮状态: **仅关系设计，未写入 TTL**

---

## 1. 本 Gate 产出

- 23 个当前可正式写入 ObjectProperty 的 V1 关系候选（17 canonical + 6 derived）。
- 2 个 deferred semantic relations（supports、contradicts）。
- 老师 PPT 6 个关系全部保留并规范化。

## 2. 第二轮修订（相对第一轮）

| 项 | 第一轮 | 第二轮 |
|---|---|---|
| PARTICIPATES_IN | BrainRegion → Circuit | BrainRegion → Circuit OR Function（恢复 PPT 语义） |
| HAS_FUNCTION | BrainRegion/Circuit → Function | Circuit → Function（收窄） |
| 连接端点 | 统一 source/target | 新增 hasEndpointRegion；source/target 仅方向已知 |
| SUPPORTS/CONTRADICTS | Canonical | KEEP 语义 / FORMALIZATION DEFER |
| APOE 示例 | APOE ε4 | APOE（ε4 留未来 GeneticVariant） |
| 无方向示例 | 单向箭头 → | 改用 — |

## 3. 关系数量（Round 2）

- PPT relations：6
- Canonical current：17
- Derived current：6
- Deferred semantic：2（supports、contradicts）
- 当前可正式写入 ObjectProperty 的 V1 relation 总数：23

## 4. 保持不动的结论

- Circuit membership reification（hasConnectionMembership + membershipConnection；hasConnection derived）。
- Atlas reification（mappingSource/mappingTarget；mapsTo derived）。
- Connection entity 仍是 canonical truth；direct graph relations 仍非 canonical truth。
- MODULATES 不扩宽。

## 5. 未做（留后续 Property Gate）

- 未写 TTL；未建 ObjectProperty/DataProperty/Individual。
- 未建 owl:inverseOf / Symmetric / Transitive。
- 未新增 Assertion / GeneticVariant / Allele Class。
- 未做 DB/API/frontend/Neo4j 实现。
