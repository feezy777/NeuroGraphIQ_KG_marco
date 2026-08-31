# Gate 7A Identity Lifecycle Amendment（简短 change note）

## 目的

消除 Gate 7A 表结构描述与已冻结语义 §F / Gate 7B-B Phase 1 实现之间的内部冲突。

## 修订内容

- **record_status**：`pending` → `proposed`（仅 record_status；`review_status.pending` 不变）。
- **kg_entities.name_en**：`NOT NULL` → `nullable`。
- **PROPOSED**：允许暂缺一种语言（name_en / name_zh 至少其一非空），且 `source_name_original` 必须非空。
- **ACTIVE**：仍要求双语完整（name_en 与 name_zh 均非空），且 `name_en_source` / `name_zh_source` 均非空、不得为 `unknown`。

## 修改文件

- `16_controlled_vocabularies.md`（record_status 词表）
- `18_complete_data_dictionary.md`（kg_entities.name_en NULL；record_status 两处）
- `13_relation_assertion_tables.md`（evidence_links.record_status）
- `03_common_entity_fields.md`（record_status 说明）
- `23_gate_07a_freeze_candidate.md`（§F ACTIVE/PROPOSED 显式化）

## 未修改

ontology TTL / backend migration / database / tests / Phase 2。
