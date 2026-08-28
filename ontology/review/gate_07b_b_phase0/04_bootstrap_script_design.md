# Gate 7B-B Phase 0 — Bootstrap 脚本设计

## 1. 路径

`backend/scripts/bootstrap_human_brain_v1.py`

## 2. 职责

- 连到 `postgres` 维护库（因为 `CREATE DATABASE` 不能在目标库事务内执行）。
- 幂等创建 `neurographiq_human_brain_v1` + `neurographiq_human_brain_v1_e2e`。
- 永不 DROP、永不触碰 legacy `neurographiq_kg_v3_wb`。

## 3. 关键行为

| 行为 | 实现 |
|---|---|
| 幂等 | `SELECT 1 FROM pg_database WHERE datname=…`；已存在 → `ALREADY_EXISTS` |
| 建库 | `CREATE DATABASE <name>`（autocommit） |
| legacy 守卫 | 仅 `pg_database` 探针确认存在，绝不连接/写 |
| 密码脱敏 | `_redact()` → `<REDACTED>` / `<EMPTY>` |
| dry-run | `--check` 只报告 `WOULD_CREATE`，不落库 |

## 4. 结果枚举

| 返回值 | 含义 |
|---|---|
| `CREATED` | 本轮新建 |
| `ALREADY_EXISTS` | 已存在，跳过 |
| `WOULD_CREATE` | 仅 `--check` 模式，尚未建 |

## 5. 实测输出

```
neurographiq_human_brain_v1: CREATED
neurographiq_human_brain_v1_e2e: CREATED
legacy guard: neurographiq_kg_v3_wb = PRESENT (read-only source, never touched)
```
