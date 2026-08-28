# Gate 7B-B Phase 0 — 执行摘要

## 1. 本轮实际执行动作

| # | 动作 | 结果 |
|---|---|---|
| 1 | 建库 `neurographiq_human_brain_v1` | CREATED |
| 2 | 建库 `neurographiq_human_brain_v1_e2e` | CREATED |
| 3 | 应用 `gate7b_001_phase0_bootstrap.sql` | APPLIED（status=APPLIED） |
| 4 | 建 `infra` schema | 存在 |
| 5 | 建 `infra.schema_migrations` | 存在（1 行登记） |
| 6 | 建 29 个 NGIQ sequence | 29 / 29 |
| 7 | 切换 8 处旧库名引用 | 完成 |
| 8 | 新增 12 个 Phase 0 单测 | 28 相关测试全绿 |

## 2. 冻结不变量

| 项 | 值 |
|---|---|
| 本体版本 | 0.9.0-ontology-core-freeze |
| TTL SHA256 | `37e0e3aff4aca4c4f898fba0f7b1c0b6121fe086725d89517db9601c0fe7b790`（未变） |
| 科学表数量 | 0 |
| legacy 库 | `neurographiq_kg_v3_wb` 34 张 public 表，未被触碰 |

## 3. 关键校验点

- 迁移 runner 幂等：二次运行输出 `skip gate7b_001 (already applied)`。
- 重复 NNN 保护：`gate7b_<NNN>` 重复 → 硬失败。
- 校验和失配：已应用迁移 checksum 变化 → fail closed。
- 密码脱敏：脚本日志统一 `<REDACTED>` / `<EMPTY>`。

## 4. 未做（等待后续阶段）

- 未建 `kg_entities` 及任何科学表（Phase 1+）。
- 未 commit / 未 push。
