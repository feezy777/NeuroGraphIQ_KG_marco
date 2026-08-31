# Gate 7A Granularity Field Amendment（简短 change note）

## 目的

统一 BrainRegion 颗粒度字段表达，消除 Gate 7A CURRENT 文档中旧 `granularity` 字段与冻结 `granularity_level` 之间的命名/词表漂移。

## 正式规则（冻结）

| 字段 | Role | 说明 |
|---|---|---|
| `brain_regions.granularity_level` | SCIENTIFIC（canonical truth） | 允许值：`G1_MACRO / G2_MESO_ANATOMICAL / G3_MESO_FINE / G4_MICROSTRUCTURAL_FINE` |
| `granularity_basis` | SCIENTIFIC/PROVENANCE | 科学依据 / granularity provenance（CURRENT 已定义，保留） |
| `granularity_rank` | DERIVED | 1 / 2 / 3 / 4 |
| `is_finest_available` | DERIVED | 当前 lineage 是否最细可靠 canonical representation |
| `parent_region_pk` | DERIVED CACHE | 非 hierarchy truth（未来 brain_region_hierarchy_relations） |
| `parent_function_pk` | DERIVED CACHE | 非 hierarchy truth（未来 function_hierarchy_relations） |

> 说明：granularity_basis / granularity_rank / is_finest_available 定义于 `24_granularity_policy.md`；本轮为纯文档修订，**不**改动已冻结的 `gate7b_003` schema（其中仅含 granularity_level）。

## 修订内容

- `18_complete_data_dictionary.md`：brain_regions `granularity`（macro/meso/fine/unknown）→ `granularity_level`（G1–G4）。
- `16_controlled_vocabularies.md`：BrainRegion 词表 `granularity` → `granularity_level`（旧值标记为历史漂移）。
- `05_brain_region_tables.md`：brain_regions `granularity` → `granularity_level`。
- `15_field_role_and_frontend_display.md`：DETAIL 展示字段 `granularity` → `granularity_level`。

## 未改动

- Macro96 / AAL3 / Brainnetome / HCP-MMP / Julich-Brain 均为 **Atlas / anchor / source context**，不是 granularity vocabulary（不进入 granularity_level 值）。
- anatomical hierarchy（partOf/subfieldOf）、external atlas mapping（ExternalRegion→RegionMapping→BrainRegion）、cross-granularity aggregation（BrainRegion→brain_region_aggregation_mappings→coarser）三类关系边界保持独立。
- 数据库 / migration / ontology TTL：未修改。
