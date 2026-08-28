# Gate 7B-B Phase 0 — Migration Namespace

## 1. 命名规范

```
gate7b_<NNN>_<slug>.sql
```

- `NNN`：三位整数，严格 `\d{3}`。
- `slug`：小写 snake_case 描述。

## 2. 为什么独立 namespace

- 既有 123 个 legacy migration 使用 `NNN_*.sql`（含 `034` 重复 3 次、`20260520_*` 日期式）。
- Gate 7B 是全新库的全新轨道，独立 `gate7b_*` 前缀可物理隔离，runner 只认这一前缀。

## 3. 已有条目

| migration_id | 文件 | 状态 |
|---|---|---|
| `gate7b_001` | `gate7b_001_phase0_bootstrap.sql` | APPLIED |

## 4. 规则

- ❌ 不修改、不重命名历史 legacy migration（`034` 重复保持原样）。
- ❌ 不把 legacy migration 混入 `gate7b_*` 轨道。
- ✅ 后续 Phase 1+ 按 `gate7b_002_*`, `gate7b_003_*` … 递增。
