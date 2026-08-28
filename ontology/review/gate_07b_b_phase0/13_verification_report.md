# Gate 7B-B Phase 0 — 验证报告

## 1. 建库

| 库 | 结果 |
|---|---|
| `neurographiq_human_brain_v1` | CREATED |
| `neurographiq_human_brain_v1_e2e` | CREATED |

## 2. infra 基础设施

| 检查 | 期望 | 实测 |
|---|---|---|
| `infra` schema | 存在 | 存在 |
| `infra.schema_migrations` | 1 行 | 1 行（`gate7b_001` / APPLIED） |
| NGIQ sequence | 29 | 29 |
| `public` 科学表 | 0 | 0 |

## 3. 科学表 = 0

| 表 | 实测 |
|---|---|
| `kg_entities` | 不存在（`to_regclass` = NULL） |
| `entity_aliases` | 不存在 |
| `entity_xrefs` | 不存在 |
| `sources` | 不存在 |

## 4. 幂等性

二次运行 `gate7b_migrate.py` → `skip gate7b_001 (already applied)`。

## 5. 本体不变

| 项 | 值 |
|---|---|
| TTL SHA256 | `37e0e3aff4aca4c4f898fba0f7b1c0b6121fe086725d89517db9601c0fe7b790` |
| 匹配 | ✅ MATCH |

## 6. 结论

Phase 0 全部校验通过；Gate 7B-B Phase 0 进入人工验收。
