# Gate 7B-B Phase 3A — Granularity Aggregation

## 1. brain_region_aggregation_mappings

表达 canonical finer BrainRegion → canonical coarser BrainRegion 的跨颗粒度 integration mapping。
**不是** anatomical partOf、**不是** ExternalRegion RegionMapping、**不是** spatial overlap。

## 2. 颗粒度方向约束（canonical truth = brain_regions.granularity_level）

触发器 `infra.assert_aggregation_granularity()`（BEFORE INSERT OR UPDATE）：

- 查 source / target 的 `brain_regions.granularity_level`。
- rank 映射：G1=1 / G2=2 / G3=3 / G4=4。
- **source rank 必须严格 > target rank**（G4→G3/G2/G1、G3→G2/G1、G2→G1 合法）。
- 禁止：reverse（G3→G4）、**same-level**（G3→G3）。
- source/target granularity 为 NULL（无法验证）→ fail closed。
- 不通过 Atlas parcel count 判断颗粒度。

## 3. Cardinality：不强制为树

- 允许 1:1 / N:1 / 1:N / N:N。
- **无** source_region UNIQUE / target_region UNIQUE（测试 `test_agg_not_forced_tree_and_n_to_one` 验证 N:1 可行 + 无唯一约束）。

## 4. rollup_eligible / is_primary_rollup

- `rollup_eligible`（NN default false）：仅 TRUE 的 mapping 未来可用于 Connection/Circuit roll-up；弱匹配、unresolved 默认不可用于自动 roll-up。
- `is_primary_rollup`（NN default false）：人工审核后的优选路径，**不删除**其他 mapping。

## 5. 不自动生成 partOf

- Aggregation mapping 即使 `spatial_overlap_ratio` 很高，也**不自动**创建 `brain_region_hierarchy_relations.part_of`（测试 `test_agg_does_not_auto_create_partof`）。

## 6. 未实现 Connection roll-up

- 本轮只建 mapping infrastructure；未创建 coarse Connection / hierarchical_rollup / Circuit roll-up / intra_region_collapsed_connection。
- 未创建 `region_mappings`（ExternalRegion→RegionMapping→BrainRegion 属后续 phase）。

## 7. 测试覆盖

- `test_agg_fine_to_coarse_allowed`（G4→G3 OK）
- `test_agg_reverse_direction_rejected`（G3→G4 拒绝）
- `test_agg_same_level_rejected`（G3→G3 拒绝）
- `test_agg_requires_granularity_level`（NULL granularity fail closed）
- `test_agg_source_target_must_be_brain_region`（非脑区 pk 拒绝）
- `test_agg_rollup_eligible_and_primary`（default false；显式 true 生效）
