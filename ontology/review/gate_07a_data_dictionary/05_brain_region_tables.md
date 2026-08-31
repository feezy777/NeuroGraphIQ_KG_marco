# Gate 7A — BrainRegion Tables（脑区表）

本轮状态: **仅设计文档**

---

## 1. brain_regions

| 字段 | 说明 |
|---|---|
| brain_region_pk | 内部主键 |
| entity_id | NGIQ-BR-… |
| region_category | cortical_region / cortical_parcel / gyrus / sulcus_region / subcortical_region / nucleus / hippocampal_subfield / amygdalar_nucleus / thalamic_nucleus / cerebellar_region / brainstem_region / other |
| hemisphere | left / right / bilateral / midline / unspecified |
| granularity_level | G1_MACRO / G2_MESO_ANATOMICAL / G3_MESO_FINE / G4_MICROSTRUCTURAL_FINE |
| anatomical_level | 解剖层级（如 lobe / gyrus / nucleus / subfield） |
| canonical_source_id | 来源 |
| species_taxon_id | 物种（V1 = Homo sapiens） |
| parent_region_pk | 父区域 [DERIVED CACHE]（见 §4） |
| hierarchy_depth | 层级深度 |
| display_order | 展示顺序 |
| color_hex | 颜色 |
| canonical_status | canonical 状态 |
| remark | 备注 |

## 2. brain_region_spatial_representations（空间表示）

一个 BrainRegion 可有多个 atlas/version/reference space/mask/label。

| 字段 | 说明 |
|---|---|
| spatial_pk | 内部主键 |
| spatial_id | NGIQ-SPAT-… |
| brain_region_id | 指向 brain_regions |
| atlas_id | 图谱 |
| reference_space | MNI152 / Colin27 / fsaverage … |
| atlas_version | 版本 |
| hemisphere | 半球 |
| label_index | 标签索引 |
| map_type | 图类型（probabilistic / maximum_probability …） |
| centroid_x_mm / centroid_y_mm / centroid_z_mm | 质心坐标 |
| bbox_json | 包围盒 |
| volume_mm3 | 体积 |
| voxel_count | 体素数 |
| resolution_json | 分辨率 |
| mask_uri / mesh_uri | 掩膜/网格 |
| color_hex | 颜色 |
| source_id | 来源 |
| metadata_json | 元数据 |
| remark | 备注 |

> 不要给 BrainRegion 主表只放一个固定 MNI coordinate。

## 3. brain_region_hierarchy_relations（Round 2 新增，canonical hierarchy truth）

| 字段 | 说明 |
|---|---|
| hierarchy_pk | 内部主键 |
| hierarchy_relation_id | NGIQ-BRH-… |
| parent_region_pk | 上位脑区（→ brain_regions） |
| child_region_pk | 下位脑区（→ brain_regions） |
| relation_type | part_of / subfield_of |
| hierarchy_source | ontology / atlas / curated |
| is_canonical | 是否 canonical |
| confidence | 置信度 |
| source_id | 来源（→ sources） |
| remark | 备注 |

## 4. parent_region_pk：cache 还是 canonical truth？

- **Round 2 修订：hierarchy relation 表 = canonical hierarchy truth。**
- `parent_region_pk`（brain_regions 表内）降为 **DERIVED cache**，便于查询/展示。
- 不得为了"方便"用 parent_region_pk 绕过显式 hierarchy relation 表。
