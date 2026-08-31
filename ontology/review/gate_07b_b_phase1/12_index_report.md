# Gate 7B-B Phase 1 — Index Report

## 1. 索引清单（4 表）

| 表 | 索引 | 类型 |
|---|---|---|
| kg_entities | entity_id | UNIQUE（列约束） |
| kg_entities | idx_kg_entities_entity_type | 普通 |
| kg_entities | idx_kg_entities_record_status | 普通 |
| kg_entities | idx_kg_entities_name_en | 普通 |
| entity_aliases | alias_id | UNIQUE（列约束） |
| entity_aliases | idx_entity_aliases_entity_pk | 普通（FK） |
| entity_aliases | idx_entity_aliases_alias_text_lower | 函数 lower(alias_text) |
| entity_aliases | idx_entity_aliases_source_pk | 普通（FK） |
| entity_xrefs | xref_id | UNIQUE（列约束） |
| entity_xrefs | idx_entity_xrefs_entity_pk | 普通（FK） |
| entity_xrefs | uq_entity_xrefs_resolved_external | 部分 UNIQUE（resolved） |
| entity_xrefs | idx_entity_xrefs_external_lookup | 普通 (source_database, external_id) |
| sources | source_id | UNIQUE（列约束） |
| sources | idx_sources_name_en | 普通 |
| sources | idx_sources_source_type | 普通 |

## 2. 覆盖的查询路径（§26）

- kg_entities：entity_id（唯一查找）、entity_type（类型扫描）、record_status（状态过滤）、name_en（canonical 名查找）。
- aliases：entity_pk（FK join）、lower(alias_text)（别名查找）。
- xrefs：entity_pk（FK join）、(source_database, external_id)（外部 ID 查找 + resolved 唯一）。
- sources：name_en（名称查找）、source_type（类型过滤）。

## 3. 原则

- 无「几十个索引」——按冻结查询路径 + FK 建立，15 项合理。
- canonical names / alias lookup / external identifier lookup / source name lookup 均覆盖。
