# Gate 8A — Identity & Mapping Validation

## 1. Alias / Xref 分离（§九）

- **entity_aliases**（20 条）：`alias_type='atlas_label'`，alias_text = circos `native_name`（如 `SFG_L_7_1`），挂在 canonical BrainRegion 上。
- **entity_xrefs**（20 条）：`source_database='Brainnetome'`，external_id = **数值 band_id**（如 `1`），match_type='exact'，is_primary=true，source_version='BNA246 (2016)'。
- **禁止混用**：数值 code 只在 xref；标签只在 alias。已验证 alias_type={'atlas_label'}、xref_source_database={'Brainnetome'}。

## 2. ExternalRegion ≠ canonical BrainRegion

- ExternalRegion（20）保留：`atlas_pk`、`source_region_id`（native_name）、`label_index`（band_id）、`hemisphere`、`granularity_level=G3_MESO_FINE`、`granularity_basis=multimodal_parcellation`。
- canonical BrainRegion（20，proposed）经 RegionMapping 关联，二者独立实体。

## 3. RegionMapping（20，first-class shared-PK）

- `entity_pk → kg_entities`（entity_type='region_mapping'），public ID = NGIQ-RMAP。
- `external_region_pk → external_regions.entity_pk`；`brain_region_pk → brain_regions.entity_pk`（坏目标 = 0）。
- **mapping_type 全部 'exact' 的说明**：本轮 pilot 中每个 canonical BrainRegion candidate 都是其 source parcel 的 **direct canonicalization**（同 gyrus + n + idx + hemisphere 派生），身份一致 → exact 是可解释的正确选择，非机械赋值。全量 246 导入时，对已存在 canonical 的 parcel 将按实际关系区分 exact/close/related/unresolved。
- `mapping_method='automatic'`，`overall_confidence=0.9`，`review_status='pending'`。

## 4. 与 AggregationMapping 严格分离（§十一）

- `brain_region_aggregation_mappings` 新增 **0**。
- ExternalRegion→BrainRegion = RegionMapping，不是 G3→G2/G1 roll-up。
- 未自动生成 partOf / subfieldOf（hierarchy 表未写）。

## 5. Human-only

- 全部 species_taxon_id=9606；无 mouse/rat/macaque/chimpanzee/Allen Mouse；无 NEEDS_REVIEW 行。
