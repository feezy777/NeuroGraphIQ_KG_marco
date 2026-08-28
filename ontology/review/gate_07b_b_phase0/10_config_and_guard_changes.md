# Gate 7B-B Phase 0 — 配置与守卫改动

## 1. app/config.py

| 项 | 旧值 | 新值 |
|---|---|---|
| `postgres_db` | `neurographiq_macro96_v1` | `neurographiq_human_brain_v1` |
| `database_url` | `…/neurographiq_macro96_v1` | `…/neurographiq_human_brain_v1` |
| 注释 | Macro96 | Human Brain KG |

## 2. app/database_guard.py

| 项 | 旧值 | 新值 |
|---|---|---|
| `MAIN_DATABASE` | `neurographiq_macro96_v1` | `neurographiq_human_brain_v1` |
| `E2E_DATABASE` | `neurographiq_macro96_v1_e2e` | `neurographiq_human_brain_v1_e2e` |
| `FORBIDDEN_DB_PREFIXES` | 不变 | `neurographiq_kg_v3`, `NeuroGraphIQ_KG`, `NeuroGraphIQ_Workbench` |
| docstring / 错误消息 | Macro96 runtime | human-brain runtime |

> `FORBIDDEN_DB_PREFIXES` 与 legacy 拒绝逻辑不变——禁止 legacy V3 库的语义保持原样。

## 3. 校验

`assert_allowed_database` 仍拒绝 legacy V3 库与未知库，只放行 `human_brain_v1`（main）或 `_e2e`/`TEST_DB_SUFFIXES`（test）。
