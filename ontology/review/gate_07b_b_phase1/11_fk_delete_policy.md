# Gate 7B-B Phase 1 — FK / Delete Policy

## 1. 冻结原则（§24）

- canonical entity 需要长期 identity / lineage。
- 删除 kg_entity **不得静默物理删除** aliases / xrefs（破坏 lineage）。
- record lifecycle 优先 status/deprecation，**非 physical deletion**。

## 2. 实现：ON DELETE RESTRICT

| FK | 行为 |
|---|---|
| `entity_aliases.entity_pk → kg_entities.entity_pk` | RESTRICT |
| `entity_xrefs.entity_pk → kg_entities.entity_pk` | RESTRICT |
| `entity_aliases.source_pk → sources.source_pk` | RESTRICT |

> 默认 NO ACTION 语义相近，但显式写 RESTRICT 更清晰、更符合「立即拒绝」。

## 3. 测试

`test_delete_entity_with_alias_is_restricted`：删除有 alias 的 entity → `RestrictViolation`（SQLSTATE 23001）。✅

## 4. Merge / Deprecated 处理（§25）

- public NGIQ ID 永不复用；DEPRECATED / MERGED 后原 ID 保留。
- 冻结 Gate 7A 尚未落地 `merged_into`/redirect 字段 → 本轮**不**自行新增 merge 表，记录为后续 requirement（见 16 risk register）。
