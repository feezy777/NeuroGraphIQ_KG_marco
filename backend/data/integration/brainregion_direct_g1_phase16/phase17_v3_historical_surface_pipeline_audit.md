# 历史 STG / LOcC direct-looking surface overlap pipeline 审计

## 数据来源
- 文件: backend/data/integration/g3_surface_dk_audits/g3_to_dk_surface_overlap_full.csv
  (同时存在于 data/integration/1/g3_to_dk_surface_overlap_full.csv 与
   data/integration/1/single_seed_surface_overlap_validation.csv 等历史副本)
- 列: hemisphere, g3_entity_id, official_code, official_modified_name, seed_mask_code,
  seed_type, g3_vertex_count, dk_label_name/id, dk_vertex_count, intersection_vertex_count,
  source_coverage_ratio, target_coverage_ratio, g1_entity_id, g1_name_en, g1_alignment_status

## source geometry
- Brainnetome (BNA246) 官方 parcel 表面 seed mask (FreeSurfer 表面, fsaverage)

## G1 geometry
- FreeSurfer Desikan-Killiany 表面 label (fsaverage)，作为 cortical G1 宏脑回几何

## 坐标/representation
- 同一 fsaverage 表面；vertex-based overlap；无需 transform/registration（同表面空间）

## 指标
- intersection_vertex_count；source_coverage_ratio (=intersection/g3_vertex_count)，
  target_coverage_ratio (=intersection/dk_vertex_count)

## 是否真正 direct source→G1
- 对 G3→G1：是 —— BN parcel surface 与 DK(G1 gyri) surface 直接同表面比较，
  未经过 G3→G1 mapping 表（DK 即 G1 概念的几何源）。
- 对 G4→G1：否 —— 历史 pipeline 不包含 Julich volume；STG/LOcC 数值是 G3(BN)→DK 结果。

## 是否依赖 Brainnetome G3→G1 mapping / 循环论证
- 否。DK label 为独立权威 G1 几何；overlap 全在表面完成，未用 aggregation 表。
  但当前 canonical G1 集合(Macro96)是否与所用 DK 子标签逐一对齐需要另行核对。

## 数值语义示例 (来自文件 official codes)
- STG_6_1 (seed STG, composite): 与 DK STG label 的 source_coverage 等指标见原文件；
- LOcC_2_x: 原文件中 g1_name_en 命中的 DK label 决定其 G1 alignment。

## 结论
- DIRECT_GEOMETRY_PIPELINE_REUSABLE? 部分可复用（仅针对 G3↔DK 表面；不是 G4 volume↔G1）。
- 对 G4→G1 direct validation 不适用 —— 需另建 Julich(volume,MNI2009c) ↔ G1 geometry 的直接比较。
