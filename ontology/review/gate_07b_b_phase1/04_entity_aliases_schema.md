# Gate 7B-B Phase 1 — entity_aliases Schema

## 1. 列（11 列，依据 18 §2 + Final Correction）

| 列 | 类型 | Null | 说明 |
|---|---|---|---|
| alias_pk | BIGSERIAL PK | NN | 内部主键 |
| alias_id | VARCHAR(32) UNIQUE | NN | NGIQ-ALS-… |
| entity_pk | BIGINT | NN (FK) | → kg_entities.entity_pk（字典历史列名 `entity_id` 已按 Final Correction 读作内部 `*_pk`） |
| alias_text | TEXT | NN | 别名文本 |
| language | VARCHAR(8) | NULL | 语言 |
| alias_type | VARCHAR(24) | NN | exact/abbreviation/historical/atlas_label/previous_name/narrow/broad/related |
| source_pk | BIGINT | NULL (FK) | → sources.source_pk |
| source_record_id | VARCHAR(64) | NULL | 来源记录 ID |
| is_preferred | BOOLEAN | NN default false | 是否首选 |
| created_at | TIMESTAMPTZ | NN default now() | 时间戳 |
| remark | TEXT | NULL | 备注 |

## 2. FK

- `fk_entity_aliases_entity`：entity_pk → kg_entities.entity_pk **ON DELETE RESTRICT**。
- `fk_entity_aliases_source`：source_pk → sources.source_pk **ON DELETE RESTRICT**。

## 3. CHECK

- `ck_entity_aliases_alias_type`：8 值（exact/abbreviation/historical/atlas_label/previous_name/narrow/broad/related）。

## 4. Alias 去重策略

- 冻结 dictionary **未定义**硬 UNIQUE（除 alias_id）。
- 故**不**强加 `UNIQUE(entity_pk, alias_text, language, alias_type)`——那会破坏「不同 source / 不同语义 alias」的保留（§13「不要用过度强的 UNIQUE」）。
- 重复保护 = **应用层软策略**（写入前查重），DB 层仅提供查询索引。

## 5. 索引

- `idx_entity_aliases_entity_pk`
- `idx_entity_aliases_alias_text_lower`（lower(alias_text)）
- `idx_entity_aliases_source_pk`

## 6. 语义

alias ≠ 新 canonical entity（参考 OBO synonym scope）。`海马` / `Hippocampus` / `hippocampal formation` 是同一 canonical entity 的独立 alias rows。
