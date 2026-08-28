# Gate 7B-B Phase 0 — Migration Runner 设计

## 1. 路径

`backend/scripts/gate7b_migrate.py`

## 2. 职责

- 只处理 `backend/migrations/gate7b_*.sql`，**忽略 123 个 legacy migration**。
- 按整数 `NNN` 升序执行（无框架，lexicographic + integer order）。

## 3. 安全性质

| 性质 | 实现 |
|---|---|
| 只认 gate7b | 文件名正则 `^gate7b_(\d{3})_.*\.sql$` |
| 重复 NNN 硬失败 | `_discover()` 遇到同 NNN → `SystemExit` |
| 校验和 fail-closed | 已应用迁移 checksum 失配 → 拒绝继续（exit 3） |
| 幂等 | 已应用迁移 → `skip` |
| dry-run | `--plan` 打印计划不落库 |
| 密码脱敏 | 日志 `<REDACTED>` |

## 4. 登记表写入

执行后写入 `infra.schema_migrations`：

```
(migration_id, filename, checksum_sha256, execution_ms, status='APPLIED', remark=NULL)
```

`migration_id = gate7b_<NNN>`，`execution_ms` 为本次执行耗时。

## 5. 实测

```
discovered: 1 gate7b_*.sql file(s)
apply gate7b_001  gate7b_001_phase0_bootstrap.sql
done.
```

二次运行：`skip gate7b_001 (already applied)`。
