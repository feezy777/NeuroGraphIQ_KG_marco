# Gate 7B-B Phase 5 — RegionMapping

## 1. first-class reified（shared-PK）

- `entity_pk BIGINT PK → kg_entities(entity_pk)`，entity_type = `region_mapping`。
- public identity = `kg_entities.entity_id`（NGIQ-RMAP，`infra.ngiq_rmap_seq`）。
- **无**第二套 canonical mapping public ID（测试 `test_region_mapping_shared_pk_no_second_identity`）。

## 2. 核心语义

```
ExternalRegion → RegionMapping → canonical BrainRegion
```

- `external_region_pk → external_regions.entity_pk`（NN）
- `brain_region_pk → brain_regions.entity_pk`（NN）
- entity_type mismatch → 拒绝（测试 `test_region_mapping_wrong_entity_type_rejected`）

## 3. RegionMapping ≠ AggregationMapping（严格分离）

- region_mappings：ExternalRegion → canonical BrainRegion。
- brain_region_aggregation_mappings：canonical finer → canonical coarser（G4→G3→G2→G1 roll-up）。
- 互相禁止代替：
  - RegionMapping 不负责 G4→G3→…→G1 roll-up。
  - AggregationMapping 不负责 ExternalRegion normalization。
- **不**自动从 RegionMapping 推导 partOf；**不**把 mapping_equivalence 变成 canonical entity merge。
- 测试 `test_region_mapping_separate_from_aggregation`：region_mappings 无 source/target_region_pk、rollup_eligible；aggregation 无 external_region_pk。

## 4. 词表

- `mapping_type`（16 §1）：exact / close / broader / narrower / related / overlapping / unresolved。
- `mapping_method`（16 §5）：automatic / manual / hybrid。
- review_status：pending/approved/rejected/uncertain/needs_revision。

## 5. 测试覆盖

- shared-PK / entity_type mismatch / FK / 与 aggregation 分离
- `test_region_mapping_fk` / `test_region_mapping_invalid_external_region_rejected`
