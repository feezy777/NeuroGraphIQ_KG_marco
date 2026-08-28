# Gate 7B-B Phase 0 — 范围与边界

## 1. 本阶段定位

Phase 0 是 Gate 7B（PostgreSQL 建库）的**基础设施阶段**。它只负责把「数据库、迁移轨道、发号机制」立起来，**不建任何科学表**。

## 2. 本阶段允许做（授权范围）

| 项 | 内容 |
|---|---|
| 建库 | 创建 `neurographiq_human_brain_v1`（正式）+ `neurographiq_human_brain_v1_e2e`（E2E） |
| 迁移轨道 | 建 `infra` schema + `infra.schema_migrations` 迁移登记表 |
| 发号机制 | 29 个 per-type NGIQ public-ID sequence |
| 迁移 runner | 新建 Gate 7B 专用 runner，只处理 `gate7b_*.sql` |
| 配置/守卫 | 8 处旧库名引用 `neurographiq_macro96_v1` → `neurographiq_human_brain_v1` |

## 3. 本阶段禁止做（红线）

| 禁止 | 说明 |
|---|---|
| ❌ 建 32 张科学表 | `kg_entities` / `entity_aliases` / `entity_xrefs` / `sources` 等，属于 Phase 1+ |
| ❌ 写 legacy `neurographiq_kg_v3_wb` | 只读迁移源，永不触碰 |
| ❌ 修改本体 TTL | `neurographiq_macro96_v1.ttl` 保持冻结 0.9.0 |
| ❌ 运行 123 个 legacy migration | runner 只识别 `gate7b_*.sql` |
| ❌ MAX+1 发号 | 一律 per-type sequence |
| ❌ commit / push | 等待人工验收 |

## 4. 产出清单

| 类型 | 路径 |
|---|---|
| bootstrap 脚本 | `backend/scripts/bootstrap_human_brain_v1.py` |
| 迁移 runner | `backend/scripts/gate7b_migrate.py` |
| 首个 migration | `backend/migrations/gate7b_001_phase0_bootstrap.sql` |
| 配置改动 | `app/config.py`, `app/database_guard.py`, `.env`, `.env.example`, `scripts/_db_env.ps1` |
| 测试改动 | `tests/conftest.py`, `tests/test_database_admin.py`, `tests/test_database_guard.py`, 新增 `tests/test_gate7b_phase0.py` |

## 5. 明确「未做」

- 未建任何科学表（public tables = 0）。
- 未 commit、未 push。
- 未修改本体 TTL（hash 不变）。
- 未触碰 legacy `neurographiq_kg_v3_wb`。
