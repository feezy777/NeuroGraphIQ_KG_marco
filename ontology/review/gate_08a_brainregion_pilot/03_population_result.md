# Gate 8A — Population Result（Before / Added / After）

## 1. Before（导入前，production）

sources=0, atlases=0, external_regions=0, brain_regions=0, region_mappings=0, entity_aliases=0, entity_xrefs=0, brain_region_aggregation_mappings=0。

## 2. Added（首轮 --apply）

| 表 | added |
|---|---|
| sources | 1（Human Brainnetome Atlas / BNA246） |
| atlases | 1 |
| external_regions | 20 |
| brain_regions | 20 |
| region_mappings | 20 |
| entity_aliases | 20 |
| entity_xrefs | 20 |
| brain_region_aggregation_mappings | 0 |

## 3. After（production）

sources=1, atlases=1, external_regions=20, brain_regions=20, region_mappings=20, entity_aliases=20, entity_xrefs=20, aggregation=0。

## 4. Rerun（第二次 --apply）

全部 added = 0（source/atlas/external/brain/mapping/alias/xref 均无重复；无第二套 NGIQ entity）。

## 5. 关键属性

- canonical BrainRegion `record_status`：**proposed 20 / active 0**（100% proposed，本轮不自动 ACTIVE）。
- `species_taxon_id`：全部 `9606`（Human-only）。
- `granularity_level`：全部 `G3_MESO_FINE`；`granularity_basis`：全部 `multimodal_parcellation`。
- `source_name_original`：20/20 完整（= circos native_name）。
- NGIQ entity_id 重复：0；Brainnetome external_id 重复：0。
- `mapping_type`：全部 `exact`（每个 canonical candidate 即其 source parcel 的 direct canonicalization，身份一致——见 04）。
