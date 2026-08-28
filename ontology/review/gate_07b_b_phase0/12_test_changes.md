# Gate 7B-B Phase 0 — 测试改动

## 1. 修改的测试文件

| 文件 | 改动 |
|---|---|
| `tests/conftest.py` | 注释 + 守卫报错文案（Macro96 → human-brain；`neurographiq_macro96_v1_e2e` → `neurographiq_human_brain_v1_e2e`） |
| `tests/test_database_admin.py` | `test_parse_database_name_from_async_url` 的 URL 断言改为 `…human_brain_v1_e2e` |
| `tests/test_database_guard.py` | 测试名/docstring 去 Macro96；`neurographiq_macro96_v1_test` → `neurographiq_human_brain_v1_test` |

## 2. 新增 `tests/test_gate7b_phase0.py`（12 用例）

| 用例 | 覆盖 |
|---|---|
| `test_filename_re_accepts_gate7b_three_digit` | 正则接受合法名 |
| `test_filename_re_rejects_legacy_prefix` | 拒绝 `001_legacy.sql` / 日期式 |
| `test_filename_re_rejects_non_numeric_or_short_nnn` | 拒绝 `00a` / `1` / `0001` |
| `test_discover_orders_by_integer_ignoring_legacy` | 整数排序 + 忽略 legacy |
| `test_discover_rejects_duplicate_nnn` | 重复 NNN 硬失败 |
| `test_discover_empty_dir_returns_empty` | 空目录 → 空列表 |
| `test_sha256_matches_stdlib` | checksum 与 stdlib 一致 |
| `test_bootstrap_target_constants_frozen` | 库名常量冻结 |
| `test_redact_never_leaks_password` | 密码脱敏 |
| `test_guard_freezes_human_brain_names` | guard 新库名 |
| `test_guard_rejects_old_macro96_name` | 旧主库名不再放行 |
| `test_config_defaults_freeze_human_brain_name` | config 默认库名 |

## 3. 实测

```
28 passed, 1 warning  (Phase 0 + guard + admin 三文件)
```

> 1 warning 为既有 DB 写测试门禁提示（默认 .env 指向主库 `human_brain_v1`，门禁按设计提示「非隔离测试库」；单元测试不依赖真实库，写测试自然隔离）。
