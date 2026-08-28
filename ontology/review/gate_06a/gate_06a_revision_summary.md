# Gate 6A — 第二轮修订摘要（Revision Summary）

Ontology IRI: `https://neurographiq.org/ontology/human-brain`（version `0.5.0-gate5b`，未改）
修订时间: 2026-08-28
修订性质: 人工审查后第二轮修订（Round 2），整体架构不变，仅修正 5 个明确问题
本轮状态: **仅 review 文档，未修改正式 TTL**

---

## 0. 人工审查结论回顾

整体架构正确，不需要重做。只修正 5 个明确问题。

## 1. 本轮全部修订清单

| # | 修订项 | 第一轮 | 第二轮 | 性质 |
|---|---|---|---|---|
| 1 | PARTICIPATES_IN | BrainRegion → Circuit（收窄） | **恢复 BrainRegion → Circuit OR Function**（PPT 完整语义） | 恢复 |
| 2 | HAS_FUNCTION | BrainRegion/Circuit → Function | **收窄 Circuit → Function**（BrainRegion→Function 用 participatesIn） | 收窄 |
| 3 | 连接端点 | 统一 source/target（方案 B） | **新增 hasEndpointRegion**；source/target 仅方向已知时用 | 修正 |
| 4 | SUPPORTS / CONTRADICTS | Canonical（Range=Connection/Circuit） | **KEEP 语义 / FORMALIZATION DEFER**（assertion-level 缺口） | 暂缓 |
| 5 | APOE ε4 示例 | APOE ε4 → AlzheimerDisease | **APOE → AlzheimerDisease**（ε4 是 variant，V1 无 GeneticVariant） | 修正 |
| 6 | 无方向示例箭头 | 用 `→` | **改用 `—`**（non-directional 不写单向箭头） | 修正 |

## 2. 关系数量重新统计

| 统计项 | 数量 |
|---|---|
| PPT relations | 6 |
| Canonical current candidates | 17 |
| Derived current candidates | 6 |
| Deferred semantic relations | 2（supports、contradicts） |
| **当前可正式写入 ObjectProperty 的 V1 relation 总数** | **23** |

> 不再沿用第一轮「24 relations」口径：新增 hasEndpointRegion（+1 canonical），supports/contradicts 从 canonical 转 DEFER（-2）。

## 3. 关键规则

- `hasEndpointRegion` = 谁和谁形成连接，不表方向。
- `hasSourceRegion` / `hasTargetRegion` = 已知道谁到谁，表真实方向。
- Direction unknown / non-directional → hasEndpointRegion。
- Direction established → hasSourceRegion + hasTargetRegion。
- 数据库排序需求不写进 ontology semantics（放 application/database 层）。

## 4. Evidence–Assertion 建模问题（记录，不解决）

- supports/contradicts 语义保留，但 Range 仅 Connection/Circuit 无法覆盖普通 ObjectProperty assertion（如 participatesIn、increasesRiskOf、hasSymptom、actsOn）。
- 未来需 assertion-level evidence model（Assertion / RelationAssertion / attachment record / reified entity 关联），本轮**禁止新增 Assertion 等 Class**。
- 留 Future Evidence / Assertion Formalization Gate。

## 5. 保持不动的结论

- Circuit membership reification（hasConnectionMembership + membershipConnection）。
- Atlas reification（mappingSource / mappingTarget；mapsTo derived）。
- direct graph relations 仍非 canonical truth；Connection entity 仍是 canonical truth。
- MODULATES 不扩宽。
