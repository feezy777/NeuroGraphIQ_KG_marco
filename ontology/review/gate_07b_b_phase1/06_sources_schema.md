# Gate 7B-B Phase 1 — sources Schema

## 1. 列（18 列，依据 18 §4 + 04 §4）

| 列 | 类型 | Null | 说明 |
|---|---|---|---|
| source_pk | BIGSERIAL PK | NN | 内部主键 |
| source_id | VARCHAR(32) UNIQUE | NN | NGIQ-SRC-… |
| name_en | TEXT | NN | 名称 |
| name_zh | TEXT | NN | 名称 |
| abbreviation | VARCHAR(64) | NULL | 缩写 |
| source_type | VARCHAR(32) | NN | atlas/database/ontology/publication_database/literature/manual/import_pipeline |
| provider | VARCHAR(128) | NULL | 提供方 |
| version | VARCHAR(32) | NULL | 版本 |
| species_scope | VARCHAR(64) | NULL | 物种范围 |
| url | TEXT | NULL | 链接 |
| api_url | TEXT | NULL | API |
| license | VARCHAR(64) | NULL | 许可证 |
| citation_text | TEXT | NULL | 引用 |
| description_en / description_zh | TEXT | NULL | 描述 |
| last_checked_at | TIMESTAMPTZ | NULL | 最后核对时间 |
| record_status | VARCHAR(16) | NN | proposed/active/deprecated/merged |
| remark | TEXT | NULL | 备注 |

## 2. CHECK

- `ck_sources_source_type`：**7 值，无 `llm`**（§K 冻结 + 16 §5 Final Correction）。
- `ck_sources_record_status`：proposed/active/deprecated/merged。

## 3. 独立性

`sources` 是**独立 registry**（`source_pk BIGSERIAL`），**不** shared-PK、**不**进 kg_entities.entity_type（§18 指令 + 冻结 dictionary）。

## 4. 时间戳说明

冻结 dictionary 未给 sources 定义 `created_at/updated_at`；`last_checked_at` 承担审计时间戳职责。**未**擅自增列（§8「不要根据本指令自行增加字段」）。

## 5. 索引

- `source_id`（UNIQUE，自动）
- `idx_sources_name_en`
- `idx_sources_source_type`

## 6. 语义边界

- Scientific Source（进 sources）：Julich-Brain / Brainnetome / HCP / PubMed / Europe PMC / HGNC / MONDO / HPO / ChEBI / IUPHAR / 具体 Publication。
- **Provenance Agent（不进 sources）**：GPT / DeepSeek / BioSEPBERT / Human curator / ImportPipeline / RuleEngine。
