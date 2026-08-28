# Gate 7B-B Phase 0 — ID 分配机制决议

## 1. 结论：per-type PostgreSQL sequence（禁 MAX+1）

## 2. 为什么不能 MAX+1

两条任务同时创建实体时，`SELECT max(pk)+1` 会拿到相同编号（读-改-写竞态）。PostgreSQL sequence 是并发安全的发号器，`nextval()` 原子递增。

## 3. 为什么 per-type 而不是单一全局 sequence

- 每种实体（脑区 / 连接 / 回路 / 功能 / 证据…）有独立前缀（`NGIQ-BR` / `NGIQ-CON` …）。
- 单一全局 sequence 会打乱「同一前缀内编号连续」的可读性，且不同类型频率差异大（脑区远少于证据条目），独立发号避免头部编号被高频类型耗尽。

## 4. 序列特性

| 特性 | 值 |
|---|---|
| 起点 | 1 |
| 步长 | 1 |
| 循环 | NO CYCLE |
| 位置 | `infra` schema |

## 5. 与 shared-PK 的关系

`kg_entities.entity_pk = 子类型 PK`（Class Table Inheritance / shared-PK）。子类型 PK 由各自 sequence 供给，entity 主键复用子类型主键，保证全局唯一（因为前缀不同 + 数值独立）。

> 注意：shared-PK 的正式落地在 Phase 1（建 `kg_entities` 时），Phase 0 只把 sequence 就位。
