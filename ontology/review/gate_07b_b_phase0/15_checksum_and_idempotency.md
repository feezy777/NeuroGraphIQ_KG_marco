# Gate 7B-B Phase 0 — 校验和与幂等性

## 1. 校验和机制

- 每个 `gate7b_*.sql` 的 SHA-256 在应用时写入 `infra.schema_migrations.checksum_sha256`。
- 已应用迁移的 checksum 在后续运行中重新计算并与登记值比对。
- **失配 → fail closed**（exit code 3），拒绝继续，防止迁移文件被事后篡改后静默漂移。

## 2. 幂等性

- 已应用的 `migration_id` 跳过，输出 `skip … (already applied)`。
- `gate7b_001` 内部使用 `IF NOT EXISTS`（schema / table / sequence），重复执行安全。

## 3. 重复 NNN 保护

- `_discover()` 按 `NNN` 建字典，同 NNN 命中即 `SystemExit`，杜绝「顺序歧义」。

## 4. 实测

| 场景 | 结果 |
|---|---|
| 首次运行 | `apply gate7b_001` → done |
| 二次运行 | `skip gate7b_001 (already applied)` |
| `--plan` | 打印计划，不落库 |

## 5. 约束

- ❌ 不重命名历史 legacy migration，避免破坏既有迁移记录。
- ❌ 校验和失配绝不「自动修复」，一律人工介入。
