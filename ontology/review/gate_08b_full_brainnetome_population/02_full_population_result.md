# Gate 8B — Full Population Result

## 1. Before（Gate 8A baseline）

sources=1, atlases=1, external_regions=20, brain_regions=20, region_mappings=20, entity_aliases=20, entity_xrefs=20, aggregation=0。

## 2. Full --apply（--mode full）

| 表 | added | after |
|---|---|---|
| sources | 0（复用 NGIQ-SRC-00000001） | 1 |
| atlases | 0（复用 NGIQ-ATL-00000001） | 1 |
| external_regions | **226** | **246** |
| brain_regions | **226** | **246** |
| region_mappings | **226** | **246** |
| entity_aliases | **226** | **246** |
| entity_xrefs | **226** | **246** |
| brain_region_aggregation_mappings | 0 | 0 |

## 3. Rerun（第二次 --mode full --apply）

全部 added/updated = **0**（完全 idempotent，无第二套 NGIQ entity）。

## 4. Hemisphere / category coverage

- DB left=123 / right=123，与 source 完全一致（无 unknown/bilateral/mixed）。
- 25 anatomical categories：source vs DB 逐类一致（mismatch=NONE）。

## 5. Key attributes（全部 246）

- BrainRegion `record_status`：**proposed 246 / active 0**（本轮不偷跑 promotion）。
- `species_taxon_id`：全部 9606（Human-only）。
- `granularity_level`：全部 G3_MESO_FINE。
- mapping：exact ×246 / automatic ×246 / brainnetome_direct ×246 / pending ×246；similarity+confidence 全 NULL。
- alias 246（atlas_label=native code）；xref 246（Brainnetome numeric，唯一）。
