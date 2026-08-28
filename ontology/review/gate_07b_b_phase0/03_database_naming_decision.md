# Gate 7B-B Phase 0 — 数据库命名决议

## 1. 冻结名称

| 角色 | 库名 |
|---|---|
| 正式开发库 | `neurographiq_human_brain_v1` |
| E2E 隔离测试库 | `neurographiq_human_brain_v1_e2e` |
| legacy 只读迁移源 | `neurographiq_kg_v3_wb`（永不触碰） |

## 2. 为什么从 macro96 改名为 human_brain

Macro96 只是知识图谱的一层（G1_MACRO）。目标库要承载 G1–G4、Connection、Circuit、Function、Evidence、Atlas，`human_brain_v1` 比 `macro96_v1` 更准确。

## 3. 旧名处理

| 旧名 | 处理 |
|---|---|
| `neurographiq_macro96_v1` | 废弃，不再作为主库默认值 |
| `neurographiq_macro96_v1_e2e` | 废弃；`_e2e` 后缀仍属测试库约定，但不再作为默认名 |

> 注：`database_guard.is_allowed_test_database` 通过 `_e2e` 后缀识别测试库，因此 `neurographiq_macro96_v1_e2e` 这类名字若作为测试库仍会被放行——这是后缀约定的预期行为，不是漏洞。

## 4. 禁止项

- ❌ 禁止回退到 legacy V3 前缀库（`neurographiq_kg_v3*`、`NeuroGraphIQ_KG*`、`NeuroGraphIQ_Workbench`）。
- ❌ 禁止运行时切换到上述任一 legacy 库（switch 已禁用）。
