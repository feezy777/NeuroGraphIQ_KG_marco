# Gate 7A Spatial Public ID Amendment（简短 change note）

## 裁决：NGIQ-SPAT = KEEP（Case B）

**CURRENT 明确要求 public ID**：dict 18 §6 定义 `spatial_id | 空间表示 ID | VARCHAR(32) | NN(UNIQUE) | ID | A | NGIQ-SPAT-…`（18 §6 / 05 §2）。这是明确的 CURRENT 字段定义，非自行推断。

因此：

- **保留** `NGIQ-SPAT` 前缀 + `infra.ngiq_spat_seq`。
- **prefix registry 最小 amendment：29 → 30**（`gate_07b_a1/05_ngiq_prefix_registry.md` 新增 `brain_region_spatial_representation` → `NGIQ-SPAT`）。
- sequence 总数 = 30。

## SpatialRepresentation 非 kg_entities subtype

- `brain_region_spatial_representations` **保持独立 link 表**（`spatial_pk BIGSERIAL` + `spatial_id`）。
- 未增加 `entity_pk` shared-PK。
- 未新增 OWL SpatialRepresentation Class（DB layer only，冻结 §9）。
- 科学边界：BrainRegion = canonical concept；SpatialRepresentation = 特定 atlas/version/reference-space 的几何表示。

## 相关文档修正（*_id → *_pk，按 §E Final Correction）

- `18_complete_data_dictionary.md`：§30 `child_region_id` → `child_region_pk`、`source_id` → `source_pk`；§31 `child_function_id` → `child_function_pk`、`source_id` → `source_pk`。
- `05_brain_region_tables.md`：BRH `source_id` → `source_pk`。
- `08_function_process_structure_tables.md`：FHR `child_function_id` → `child_function_pk`、`source_id` → `source_pk`。

## 未修改

gate7b_005 migration（Case B 无需改库）；ontology TTL；legacy；Phase 0–2B 冻结 migration。
