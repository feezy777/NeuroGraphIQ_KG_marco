# Gate 7B-B Phase 0 — Change Summary

本轮状态：**首个实现门禁——已建库 + 建基础设施，但未 commit/push，未建科学表**

## 1. 产出

| 类型 | 文件 |
|---|---|
| 新建 | `backend/scripts/bootstrap_human_brain_v1.py` |
| 新建 | `backend/scripts/gate7b_migrate.py` |
| 新建 | `backend/migrations/gate7b_001_phase0_bootstrap.sql` |
| 新建 | `backend/tests/test_gate7b_phase0.py`（12 用例） |
| 修改 | `app/config.py`, `app/database_guard.py`, `.env`, `.env.example`, `scripts/_db_env.ps1` |
| 修改 | `tests/conftest.py`, `tests/test_database_admin.py`, `tests/test_database_guard.py` |

## 2. 数据库实际变更

- 新建 `neurographiq_human_brain_v1` + `neurographiq_human_brain_v1_e2e`。
- 新建 `infra` schema、`infra.schema_migrations`、29 个 sequence。

## 3. 明确未做

- 未建 `kg_entities` 及任何科学表（Phase 1+）。
- 未写 legacy `neurographiq_kg_v3_wb`。
- 未修改本体 TTL（hash 不变）。
- 未 commit / 未 push。

## 4. 下一步（Phase 1，待本轮验收后）

- `kg_entities` / `entity_aliases` / `entity_xrefs` / `sources` 四表（shared-PK 落地）。
- legacy coarse_* 数据回填迁移。
