# Gate 7B-B Phase 3A — Scope & Schema

## 1. 本轮范围

创建 4 张 Hierarchy / Spatial / Granularity Integration 表（18/32 → 22/32）。

| # | 表 | 角色 |
|---|---|---|
| 1 | brain_region_hierarchy_relations | BrainRegion 解剖层级 canonical truth |
| 2 | function_hierarchy_relations | Function 概念层级 canonical truth |
| 3 | brain_region_spatial_representations | BrainRegion 在 atlas/space 的空间表示 |
| 4 | brain_region_aggregation_mappings | fine → coarse 跨颗粒度 integration mapping |

## 2. 未创建（Phase 3B+）

connections / connection_endpoints / connection_observations / circuits / circuit_* / region_mappings / relation_definitions / knowledge_assertions / evidence_links 等。

## 3. 建模：非 kg_entities subtype

这 4 张是 **relation / spatial / reified 表**（不在 18 值 entity_type 词表内），各自有独立 `*_pk BIGSERIAL` + NGIQ `*_id`：

- `hierarchy_relation_id`：NGIQ-BRH-…（infra.ngiq_brh_seq）
- `hierarchy_relation_id`：NGIQ-FHR-…（infra.ngiq_fhr_seq）
- `spatial_id`：NGIQ-SPAT-…（新增 infra.ngiq_spat_seq，见风险）
- `mapping_id`：NGIQ-BRAM-…（infra.ngiq_bram_seq）

## 4. 关键 FK

| 表 | FK |
|---|---|
| BRH | parent_region_pk / child_region_pk → brain_regions(entity_pk)；source_pk → sources |
| FHR | parent_function_pk / child_function_pk → functions(entity_pk)；source_pk → sources |
| Spatial | brain_region_pk → brain_regions(entity_pk)；atlas_pk → atlases(entity_pk)；source_pk → sources |
| Aggregation | source_region_pk / target_region_pk → brain_regions(entity_pk)；scientific_source_pk → sources |

全部 `ON DELETE RESTRICT`（lineage 保留）。

## 5. migration

`backend/migrations/gate7b_005_hierarchy_spatial_granularity.sql`，同一文件应用于 production 与 E2E。
