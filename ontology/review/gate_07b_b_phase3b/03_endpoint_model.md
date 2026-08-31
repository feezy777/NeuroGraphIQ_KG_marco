# Gate 7B-B Phase 3B — Endpoint Model

## 1. connection_endpoints = canonical endpoint truth

- `connection_pk → connections.entity_pk`
- `brain_region_pk → brain_regions.entity_pk`（**不**直接 FK kg_entities，保 subtype integrity）
- **connections 表无 source_region_pk / target_region_pk**（§九：不重复保存 endpoint truth）

## 2. endpoint_role 词表

```
endpoint / source / target
```

- `endpoint` = 无已知生物方向的连接端点。
- `source` / `target` = 方向科学上已知。
- 记录顺序 ≠ source/target。

## 3. 无向连接（FC / direction_unknown Structural）

- A↔B 保存为两个 `endpoint` role，**不**伪造 source/target。

## 4. 有向连接（Projection / directed Structural / directed EC）

- Projection：通常恰好一个 source + 恰好一个 target（严格数量校验归应用层 validation，本轮 DB 不跨行统计数量）。
- direction_unknown Structural：不强迫生成方向。

## 5. DB 层防错（§十五）

| 规则 | 实现 |
|---|---|
| duplicate endpoint（同 connection + 同 region + 同 role） | `UNIQUE (connection_pk, brain_region_pk, endpoint_role)` |
| obvious self-endpoint（同 region 兼 source+target） | `infra.assert_no_self_endpoint()` 触发器（AFTER INSERT/UPDATE，查询该 connection 内 region 的 distinct role 数 >1 → 拒绝） |

## 6. 测试覆盖

- `test_endpoint_connection_region_fk`（FK 正确）
- `test_endpoint_invalid_region_rejected`（非法 region 拒绝）
- `test_endpoint_duplicate_rejected`（重复拒绝）
- `test_endpoint_self_source_target_rejected`（self-endpoint 拒绝）

## 7. Validation Boundary（DB integrity vs Scientific promotion）

**Database integrity layer（本轮 DB 已实现）**

| 规则 | 实现 |
|---|---|
| connection_class 合法 | CHECK |
| directionality 合法 | CHECK |
| endpoint_role 合法 | CHECK |
| endpoint FK 合法 | FK |
| duplicate endpoint 拒绝 | UNIQUE(connection,region,role) |
| 同一 BrainRegion 占多个 endpoint role 拒绝 | `infra.assert_no_self_endpoint()` trigger |

**Scientific promotion validation layer（后续 Validation / Promotion rule 的明确责任）**

- promoted / ACTIVE Projection 必须恰好 1 source + 1 target。
- FunctionalConnectivity 不得因存储顺序伪造 source/target。
- direction_unknown StructuralConnection 不得伪造生物方向。
- EffectiveConnectivity 的 directed semantics ≠ Projection。
- directed StructuralConnection 不自动升级为 Projection。

> **本轮不新增 Projection cardinality DB trigger**——严格 cardinality / promotion 校验是 Validation / Promotion rule 的明确责任，不在 DB integrity 层实现。
