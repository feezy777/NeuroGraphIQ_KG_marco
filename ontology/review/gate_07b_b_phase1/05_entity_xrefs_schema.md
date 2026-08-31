# Gate 7B-B Phase 1 — entity_xrefs Schema

## 1. 列（11 列，依据 18 §3 + Final Correction）

| 列 | 类型 | Null | 说明 |
|---|---|---|---|
| xref_pk | BIGSERIAL PK | NN | 内部主键 |
| xref_id | VARCHAR(32) UNIQUE | NN | NGIQ-XRF-… |
| entity_pk | BIGINT | NN (FK) | → kg_entities.entity_pk（字典历史列名 `entity_id` 已校正为内部 `*_pk`） |
| source_database | VARCHAR(64) | NN | 来源库（HGNC/MONDO/ChEBI…） |
| external_id | VARCHAR(64) | NN | 外部 ID |
| external_uri | TEXT | NULL | 外部 URI |
| match_type | VARCHAR(24) | NN | exact/close/broader/narrower/related/unresolved |
| is_primary | BOOLEAN | NN default false | 主映射 |
| source_version | VARCHAR(32) | NULL | 来源版本 |
| retrieved_at | TIMESTAMPTZ | NULL | 抓取时间 |
| remark | TEXT | NULL | 备注 |

## 2. FK

- `fk_entity_xrefs_entity`：entity_pk → kg_entities.entity_pk **ON DELETE RESTRICT**。

## 3. CHECK

- `ck_entity_xrefs_match_type`：6 值（exact/close/broader/narrower/related/unresolved）。
  > 注：不含 `overlapping`（那是 region_mappings.mapping_type 的词表，xrefs.match_type 只有 6 值）。

## 4. Xref 唯一性策略（§15）

- **resolved**（match_type ≠ unresolved）：`(source_database, external_id)` 部分唯一索引 `uq_entity_xrefs_resolved_external`，防「无意 double-bind」。
- **unresolved**：允许同一 (source_database, external_id) 映射到多个 entity（歧义映射合法）。

## 5. 索引

- `idx_entity_xrefs_entity_pk`
- `uq_entity_xrefs_resolved_external`（partial unique，resolved only）
- `idx_entity_xrefs_external_lookup`（(source_database, external_id) 全量查询）

## 6. 语义

外部 ID（Brainnetome / Julich / HCP label / HGNC / MONDO / HPO）进 xrefs，**不塞进 alias**；不在各实体表无限加 `uberon_id/mondo_id/...`。
