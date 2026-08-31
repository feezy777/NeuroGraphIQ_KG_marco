# Gate 7B-B Phase 1 — kg_entities Schema

## 1. 列（24 列，依据 18_complete_data_dictionary §1 + §D + §E Final Correction）

| 列 | 类型 | Null | 说明 |
|---|---|---|---|
| entity_pk | BIGSERIAL PK | NN | 内部全局主键（§E shared-PK；字典历史名 `pk` 已校正为 `entity_pk`） |
| entity_id | VARCHAR(32) UNIQUE | NN | public NGIQ ID |
| entity_type | VARCHAR(48) | NN | 受控词表（18 值） |
| name_en | TEXT | NULL | 英文名（proposed 可缺；active 必填） |
| name_zh | TEXT | NULL | 中文名（proposed 可缺；active 必填） |
| abbreviation | VARCHAR(64) | NULL | 缩写 |
| definition_en / definition_zh | TEXT | NULL | 定义 |
| description_en / description_zh | TEXT | NULL | 描述 |
| source_name_original | TEXT | NULL | 原始来源名（不翻译） |
| source_language | VARCHAR(16) | NULL | 来源语言 |
| name_en_source / name_zh_source | VARCHAR(24) | NULL | 名称来源（6 值） |
| translation_review_status | VARCHAR(24) | NULL | 翻译审核状态 |
| record_status | VARCHAR(16) | NN | proposed/active/deprecated/merged |
| review_status | VARCHAR(24) | NULL | pending/approved/rejected/uncertain/needs_revision |
| version | INTEGER | NULL | 版本 |
| created_at / updated_at | TIMESTAMPTZ | NN default now() | 时间戳 |
| created_by_agent / updated_by_agent | VARCHAR(64) | NULL | 操作者（provenance agent，非 scientific source） |
| metadata_json | JSONB | NULL | 不稳定字段 |
| remark | TEXT | NULL | 人工补充 |

## 2. CHECK 约束

| 约束 | 值 |
|---|---|
| ck_kg_entities_entity_type | 18 值（见 08） |
| ck_kg_entities_record_status | proposed/active/deprecated/merged |
| ck_kg_entities_review_status | pending/approved/rejected/uncertain/needs_revision |
| ck_kg_entities_name_en_source / _zh_source | source/human_curated/translated_human/translated_ai/normalized/unknown |
| ck_kg_entities_active_bilingual | `record_status<>'active' OR (name_en IS NOT NULL AND name_zh IS NOT NULL)` |
| ck_kg_entities_active_name_source | active → 双 name source 非空且非 unknown |
| ck_kg_entities_proposed_source | `record_status<>'proposed' OR source_name_original IS NOT NULL` |
| ck_kg_entities_proposed_has_name | `record_status<>'proposed' OR (name_en IS NOT NULL OR name_zh IS NOT NULL)` |

## 3. 索引

- `entity_id`（UNIQUE，自动）
- `idx_kg_entities_entity_type`
- `idx_kg_entities_record_status`
- `idx_kg_entities_name_en`

## 4. 命名校正说明（已按冻结权威消解）

- `pk` → `entity_pk`（§E Final Correction）。
- `created_by/updated_by` → `created_by_agent/updated_by_agent`（§D 冻结字段名，语义=provenance agent）。
- 保留 `review_status`（18 §1 + 03 §1 明确列出；23 §D 为节略）。
- `name_en` 由 NOT NULL → NULL（本轮修订）：与 §F「PROPOSED 可暂缺一种语言」一致；ACTIVE 双语由 `ck_kg_entities_active_bilingual` 显式保证。
