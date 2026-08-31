# NeuroGraphIQ Human Brain V1 — Scientific Schema Freeze Declaration

## 冻结记录

| 项 | 值 |
|---|---|
| Database | `neurographiq_human_brain_v1` |
| Scientific tables | **32 / 32** |
| Migration lineage | `gate7b_001` → `gate7b_008` |
| Ontology | `0.9.0-ontology-core-freeze` |
| TTL SHA256 | `37e0e3aff4aca4c4f898fba0f7b1c0b6121fe086725d89517db9601c0fe7b790` |
| PostgreSQL | canonical source of truth |
| Neo4j | downstream projection only |
| Legacy | `neurographiq_kg_v3_wb` READ ONLY migration/source pool |
| **Scientific Schema Status** | **FROZEN FOR DATA POPULATION** |

## FROZEN FOR DATA POPULATION 含义

- 32 张 scientific tables 及其核心 identity / FK / canonical boundary **可作为数据生产基础**。
- **不是**永远不允许修改。
- 未来 schema 修改必须通过 **versioned migration**：
  - 从本次 freeze 起，`gate7b_001`～`gate7b_008` 视为 **immutable migration history**。
  - **禁止**直接编辑旧 SQL + 重写 checksum。
  - 未来修正必须创建新的 `gate7b_009_*.sql`。

## 本轮未做

- 未修改数据库 / migration / ontology TTL。
- 未迁 legacy。
- 未进入数据生产 / 灌入。
