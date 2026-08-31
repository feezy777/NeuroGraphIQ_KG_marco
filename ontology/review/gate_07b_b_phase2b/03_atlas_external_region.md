# Gate 7B-B Phase 2B — Atlas / ExternalRegion

## 1. Atlas

- `atlases` = Atlas 科学资源/图谱实体（未来 Brainnetome / Julich-Brain / HCP-MMP / AAL3）。
- **Atlas ≠ granularity**：`atlases` 表**无** granularity_level 列（测试 `test_atlas_is_not_granularity`）。
- Atlas parcel count 不决定 biological granularity；不硬编码 AAL3=N / Julich=N（version-specific）。
- 本轮只建 schema，不插真实 Atlas 数据。

## 2. ExternalRegion

- 外部 Atlas / database 定义的 region concept，**不是** canonical BrainRegion。
- 保留 source atlas context：`atlas_pk`（NN FK→atlases）、`source_region_id`（atlas-native 标签，如 Brainnetome "A8m"）、`label_index`、`version context`。
- 未来关系：`ExternalRegion → RegionMapping → BrainRegion`（本轮**不**创建 region_mappings）。

## 3. ExternalRegion 与 BrainRegion 分离

- 无错误直接 FK / canonical 合并。
- entity_type 守卫：external_region 实体无法插入 brain_regions（测试 `test_external_region_not_mergeable_into_brain_region`）。
- 禁止假设"所有 Atlas parcel = canonical BrainRegion"。

## 4. granularity（atlas context only）

- `external_regions.granularity_level`：G1–G4（CHECK），来自 source atlas context，**非 canonical truth**。
- `granularity_basis`：9 值词表（CHECK，NULL-able）。
- 非法值（G5_BOGUS）→ 拒绝（测试 `test_external_region_invalid_granularity_rejected`）。
