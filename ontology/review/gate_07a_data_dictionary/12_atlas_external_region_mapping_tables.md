# Gate 7A — Atlas / ExternalRegion / RegionMapping Tables

本轮状态: **仅设计文档**

---

## 1. atlases

| 字段 | 说明 |
|---|---|
| atlas_pk | 内部主键 |
| atlas_id | NGIQ-ATL-… |
| name_en / name_zh | 名称 |
| abbreviation | 缩写 |
| atlas_family | 家族 |
| atlas_version | 版本 |
| species | 物种 |
| parcellation_method | 划分方法 |
| reference_space | 参考空间 |
| resolution_json | 分辨率 |
| map_type | 图类型 |
| region_count | 区域数 |
| release_date / release_year | 发布日期/年份 |
| publisher_or_institution | 发布机构 |
| source_url / download_url | 链接 |
| license | 许可证 |
| citation_pmid / citation_doi | 引用 |
| description_en / description_zh | 描述 |
| remark | 备注 |

## 2. external_regions（与 canonical BrainRegion 分开）

| 字段 | 说明 |
|---|---|
| external_region_pk | 内部主键 |
| external_region_id | NGIQ-XREG-… |
| name_en / name_zh | 名称 |
| source_name_original | 原始来源名 |
| abbreviation | 缩写 |
| atlas_id | 图谱 |
| source_region_id | 来源区域 ID |
| label_index | 标签索引 |
| hemisphere | 半球 |
| parent_external_region_id | 父外部区域 |
| structure_path | 结构路径 |
| hierarchy_depth | 层级深度 |
| display_order | 展示顺序 |
| reference_space | 参考空间 |
| centroid_x_mm / centroid_y_mm / centroid_z_mm | 质心 |
| volume_mm3 | 体积 |
| color_hex | 颜色 |
| metadata_json | 元数据 |
| remark | 备注 |

## 3. region_mappings（reified）

| 字段 | 说明 |
|---|---|
| mapping_pk | 内部主键 |
| region_mapping_id | NGIQ-RMAP-… |
| name_en / name_zh | 名称 |
| external_region_id | 外部脑区 |
| brain_region_id | canonical 脑区 |
| mapping_type | exact / close / broader / narrower / related / overlapping / unresolved |
| mapping_method | 方法 |
| spatial_overlap | 空间重叠 |
| name_similarity | 名称相似度 |
| semantic_similarity | 语义相似度 |
| hierarchy_similarity | 层级相似度 |
| overall_confidence | 总体置信度 |
| mapping_source | 来源 |
| review_status / reviewer / reviewed_at | 审核 |
| evidence_summary_en / evidence_summary_zh | 证据摘要 |
| remark | 备注 |
