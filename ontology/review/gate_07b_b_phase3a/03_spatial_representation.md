# Gate 7B-B Phase 3A — Spatial Representation

## 1. BrainRegion concept ≠ SpatialRepresentation

`brain_region_spatial_representations` 表示某个 canonical BrainRegion 在特定 Atlas / Atlas version / reference space 中的**具体空间表示**，不是 BrainRegion 本身。

## 2. 字段（按 CURRENT dict 18 §6）

- `brain_region_pk`（NN FK→brain_regions）
- `atlas_pk`（FK→atlases）、`atlas_version`、`reference_space`（CHECK：MNI152/Colin27/fsaverage/native/other）
- `hemisphere`（CHECK）、`label_index`、`map_type`（CHECK）
- geometry/mask：`mask_uri` / `mesh_uri`
- `centroid_x/y/z_mm`、`bbox_json`、`volume_mm3`、`voxel_count`、`resolution_json`
- provenance：`source_pk`（FK→sources）、`metadata_json`
- `remark`（全局默认）

> 注：CURRENT §6 未定义 `record_status`（spatial 为技术表示，无独立生命周期），故未加列（"不要自行扩字段"）；`remark` 按 header 全局默认加入。

## 3. 禁止新增 Spatial Relation

- **未创建** `brain_region_spatial_relations` 表（测试 `test_no_spatial_relation_table`）。
- **未创建** `spatiallyOverlaps` / `adjacentTo` / `locatedIn` 对应表/OWL relation。
- 冻结：SpatialRepresentation 在 DB 层保存几何；空间重叠**不能**自动变 partOf；邻接**不能**自动变 Connection。

## 4. 测试覆盖

- `test_spatial_requires_valid_brain_region`：非合法 brain_region → 拒绝
- `test_spatial_atlas_context_ok`：atlas + reference_space context 正确
- `test_spatial_invalid_reference_space_rejected`：非法 space → 拒绝
