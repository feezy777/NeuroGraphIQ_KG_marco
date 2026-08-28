# Gate 7B-B Phase 0 — Legacy 库完整性

## 1. 结论

Legacy `neurographiq_kg_v3_wb` **未被本轮任何动作触碰**。

## 2. 为什么可保证

| 脚本 | 对 legacy 的访问 |
|---|---|
| `bootstrap_human_brain_v1.py` | 仅 `SELECT 1 FROM pg_database WHERE datname='neurographiq_kg_v3_wb'` 探针，不连接、不写 |
| `gate7b_migrate.py` | 只连目标库 `human_brain_v1`，与 legacy 无交互 |
| 本阶段所有 SQL | 只作用于 `neurographiq_human_brain_v1` |

## 3. 实测 legacy 现状（保持不变）

- schema：`public`（34 张表）
- 关键表仍在：`coarse_brain_regions`、`kg_regions`、`kg_connections`、`kg_functions`、`kg_mappings`、`kg_terms`、`staging_*`、`evidence_items`、`evidence_sources`、`atlas_resources` 等。

> 说明：早期审计笔记中「coarse_grain schema」是笔误——legacy 表实际位于 `public` schema，本轮实测校正。

## 4. 后续用途

legacy 库作为 Phase 1+ 的**只读迁移源**（coarse_* 数据回填），绝不写入。
