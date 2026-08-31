# Gate 7B-B Phase 3A — Risk Register & Phase 3B Entry

## 1. BLOCKER = 0

## 2. MAJOR = 0

## 3. MODERATE

| # | 项 | 说明 |
|---|---|---|
| M1 | `NGIQ-SPAT` 前缀不在冻结 29-prefix registry | dict 18 §6 定义 spatial_id = NGIQ-SPAT-…，但 Phase 1 冻结的 29 前缀注册表未含 SPAT。本轮在 gate7b_005 新增 `infra.ngiq_spat_seq` 以支持（infra seqs 30）。建议后续前缀注册表 amendment 正式纳入 SPAT。 |
| M2 | aggregation 颗粒度用触发器而非 DB CHECK | PostgreSQL CHECK 无法跨表读 brain_regions.granularity_level，故用 `infra.assert_aggregation_granularity()` 触发器实现方向约束（fail closed）。已在 migration 注释说明。 |
| M3 | dict 18 §30/§31 的 `child_region_id` / `child_function_id` / `source_id` 列名 | 按 §E Final Correction 读作内部 `*_pk`（child_region_pk / child_function_pk / source_pk）。非语义冲突，属命名校正。 |

## 4. 已落实的边界（无核心语义冲突）

- partOf/subfieldOf（hierarchy） vs aggregation vs spatial overlap：**保持独立**。
- RegionMapping（ExternalRegion→BrainRegion） vs aggregation（BrainRegion→coarser BrainRegion）：**保持分离**，本轮未建 region_mappings。
- rollup_eligible：默认 false，仅 TRUE 可 roll-up。

## 5. Phase 3B Entry Criteria

| # | 条件 | 状态 |
|---|---|---|
| 1 | 4 张 Hierarchy/Spatial/Aggregation 表创建 | ✅ |
| 2 | 22/32 table count（无 >22 或 <22） | ✅ |
| 3 | production/E2E parity | ✅ |
| 4 | BRH/FHR FK + self relation 拒绝 + relation_type 受控 | ✅ |
| 5 | parent_region_pk / parent_function_pk 仅 DERIVED CACHE | ✅ |
| 6 | function subclass_of 未误建 OWL Class hierarchy（对应 subFunctionOf） | ✅ |
| 7 | SpatialRepresentation ≠ BrainRegion；无 spatial relation table | ✅ |
| 8 | aggregation 方向约束（reverse/same-level 拒绝；fail closed） | ✅ |
| 9 | rollup_eligible / is_primary_rollup 实现 | ✅ |
| 10 | aggregation 不自动生成 partOf | ✅ |
| 11 | clean replay 001→005 = production | ✅ |
| 12 | migration 幂等（repeat → skip） | ✅ |
| 13 | 未迁 legacy / 无 Phase 3B+ 表 leak | ✅ |
| 14 | BLOCKER = 0 | ✅ |

**Phase 3B Entry Readiness = READY**

（Phase 3B 候选：connections / circuits / region_mappings / relation_definitions / knowledge_assertions / evidence_links 等，具体顺序待人工指示。）
