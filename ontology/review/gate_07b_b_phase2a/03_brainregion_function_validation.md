# Gate 7B-B Phase 2A — BrainRegion / Function 校验

## 1. brain_regions.granularity_level（canonical granularity truth）

使用冻结 G1–G4：

```
G1_MACRO / G2_MESO_ANATOMICAL / G3_MESO_FINE / G4_MICROSTRUCTURAL_FINE
```

- CHECK：`granularity_level IS NULL OR granularity_level IN (4 值)`。
- 非法值（如 `G5_BOGUS`）→ CHECK violation。
- 注：dict 18 §5 的 `granularity VARCHAR(16) macro/meso/fine/unknown` 与冻结 granularity framework（16 §7、27 §D、23 §O）冲突；依 Phase 2A 指令 §7 使用 `granularity_level` + G1–G4。

## 2. 其他受控词表（brain_regions）

- hemisphere：left/right/bilateral/midline/unspecified（16 §2）→ CHECK。
- region_category：cortical_region/…/other（16 §2）→ CHECK。
- species_taxon_id：V1=Homo sapiens（9606）；本轮不插 mouse 数据。

## 3. parent_region_pk = DERIVED CACHE ONLY

- `parent_region_pk BIGINT REFERENCES brain_regions(entity_pk) ON DELETE SET NULL`。
- 标注为 DERIVED display cache，**不是** hierarchy truth。
- 未创建 `brain_region_hierarchy_relations`（Phase 2B+）。

## 4. functions

- `function_category VARCHAR(16) NOT NULL`：general / cognitive（16 §4）→ CHECK。
- `parent_function_pk`：DERIVED cache（`ON DELETE SET NULL`）。
- 未创建 `function_hierarchy_relations`；未用 rdfs:subClassOf 概念建 SQL 层级。
- 具体 function concept 后续经 `functions + function_hierarchy_relations` 表达。

## 5. 测试覆盖

- `test_brain_region_valid_granularity`：G1_MACRO 插入 OK。
- `test_brain_region_invalid_granularity_rejected`：G5_BOGUS → 拒绝。
- `test_brain_region_invalid_hemisphere_rejected`：'north' → 拒绝。
