# Gate 7B-B Phase 5 — Scope & 32-Table Completion

## 1. 本轮范围（最后 4 张）

创建 final mapping / assertion / evidence-link 层（28/32 → **32/32**）。

| # | 表 | 角色 |
|---|---|---|
| 1 | region_mappings | first-class reified RegionMapping（shared-PK） |
| 2 | relation_definitions | PostgreSQL predicate registry |
| 3 | knowledge_assertions | DB-only 普通关系 claim |
| 4 | evidence_links | Evidence → assertion XOR entity target |

## 2. 未创建

assertion_evidence_links / brain_region_spatial_relations / connection_types / circuit_types / evidence_types（任何第 33 张 scientific table 都不存在）。

## 3. 建模

- **region_mappings** = shared-PK（entity_type='region_mapping'，public ID = kg_entities.entity_id NGIQ-RMAP）。
- **relation_definitions / knowledge_assertions / evidence_links** = standalone（各自 BIGSERIAL PK + NGIQ *_id：PRED / AST / ELK）。
- EvidenceLink **不**是 kg_entities subtype（§十六）。

## 4. 关键 FK

| 表 | FK |
|---|---|
| region_mappings | entity_pk → kg_entities；external_region_pk → external_regions；brain_region_pk → brain_regions |
| relation_definitions | —（registry，self） |
| knowledge_assertions | subject_entity_pk / object_entity_pk → kg_entities；predicate_pk → relation_definitions |
| evidence_links | evidence_pk → evidence；assertion_pk → knowledge_assertions；entity_pk → kg_entities |

## 5. 冻结边界（本轮落实）

- RegionMapping（ExternalRegion→BrainRegion）与 AggregationMapping（fine→coarse canonical）**严格分离**；不自动 partOf / 不自动 merge。
- KnowledgeAssertion DB-only；Connection/Circuit/RegionMapping/CCM 已有 canonical reified model，不重复断言。
- EvidenceLink XOR（DB CHECK 强制，fail closed）。
- Entity evidence whitelist = connection / circuit / region_mapping / circuit_connection_membership（trigger 强制）。
- evidence_strength / evidence_directness 位于 evidence_links（target-specific）。
- 无 evidence inheritance trigger。

## 6. migration

`backend/migrations/gate7b_008_final_mapping_assertion_layer.sql`，同一文件应用于 production 与 E2E。未改 gate7b_001–007。
