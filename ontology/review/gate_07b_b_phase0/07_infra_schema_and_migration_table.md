# Gate 7B-B Phase 0 — infra Schema 与迁移登记表

## 1. infra schema

`CREATE SCHEMA IF NOT EXISTS infra;` — 专门承载迁移与发号基础设施，与科学数据（Phase 1+ 的实体表）隔离。

## 2. infra.schema_migrations 结构

| 列 | 类型 | 说明 |
|---|---|---|
| migration_id | TEXT PK | `gate7b_<NNN>` |
| filename | TEXT NOT NULL | 迁移文件名 |
| checksum_sha256 | TEXT NOT NULL | 文件 SHA-256 |
| applied_at | TIMESTAMPTZ NOT NULL DEFAULT now() | 应用时间 |
| execution_ms | BIGINT | 执行耗时 |
| status | TEXT NOT NULL | Phase 0 只有 `APPLIED` |
| remark | TEXT | 备注（当前 NULL） |

> 这是迁移登记表的**唯一权威定义**（在 `gate7b_001` 中）；runner 内部还有一个 `CREATE TABLE IF NOT EXISTS` 兜底，保证即使 runner 先于 `gate7b_001` 运行也能自举。

## 3. 实测

```
schema_migrations rows: 1
  ('gate7b_001', 'gate7b_001_phase0_bootstrap.sql', 'APPLIED', '7a6c0840…3db6f')
```

## 4. 边界

- `infra.schema_migrations` 是**基础设施表**，不计入 32 张科学表。
- 不承载任何知识实体，只做迁移溯源。
