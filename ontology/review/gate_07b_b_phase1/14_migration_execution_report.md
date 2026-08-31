# Gate 7B-B Phase 1 — Migration Execution Report

## 1. 迁移文件

`backend/migrations/gate7b_002_identity_foundation.sql`

## 2. 执行顺序

```
gate7b_001 (Phase 0 bootstrap) → gate7b_002 (Identity Foundation)
```

## 3. 执行结果

| 库 | gate7b_001 | gate7b_002 |
|---|---|---|
| neurographiq_human_brain_v1 | APPLIED | APPLIED |
| neurographiq_human_brain_v1_e2e | APPLIED | APPLIED |

- 每库 `infra.schema_migrations` = 2 行。
- 重复执行 → `skip`（幂等，由 checksum + migration_id 保障）。

## 4. Runner 修复（checksum 换行归一化）

执行中发现：`git core.autocrlf=true` 在 commit/rebase 后把工作区文件换行从 LF 转成 CRLF，导致已应用迁移 `gate7b_001` 的 raw-bytes SHA256 漂移（runner 按设计 fail-closed 拒绝）。

修复：`gate7b_migrate.py` 的 `_sha256` 与 `_apply` 统一 `_read_normalized()`（CRLF→LF），使 checksum 反映 **SQL 内容**而非平台换行风格。归一化后 `gate7b_001` checksum 与 Phase 0 登记值完全一致。

## 5. 迁移内容（4 表 + 1 函数）

- `infra.next_ngiq_id(text)`（29-entry 发号器）
- `kg_entities`（24 列）
- `sources`（18 列）
- `entity_aliases`（11 列）
- `entity_xrefs`（11 列）
