# 多尺度粒度体系架构 (BR3)

> NeuroGraphIQ Brain Region Ontology 五级尺度: **Macro → Meso → Subregion → Cyto → Molecular**
>
> 落盘日期: 2026-08-21 · 分支: `codex/ontology-evidence` · 迁移: `20260826_multiscale_granularity_refactor.sql` + `20260827_multiscale_atlas_layer.sql` (编号排在 `20260822_canonical_brain_region.sql` / `20260823_macro96_canonical_l2.sql` 之后,保证全新库按文件名顺序应用时词表行已存在)

## 1. 粒度词表 (granularity vocab)

`ontology_vocabularies` (vocab_type=`granularity_level`) 新增两列: `level_order` (INT) 与 `source_strategy` (TEXT)。10 个活跃层级按 `level_order` 排序:

| level_order | code | 语义 | source_strategy |
|---|---|---|---|
| 0 | `whole_brain` | LEGACY (L0 全脑) | compat → macro |
| 1 | `macro` | **L1 Macro** 主尺度: 大分区 + Macro96 临床池 | Macro96 96 池 (现状保持) |
| 2 | `clinical` | LEGACY (Macro96 96-pool) | compat → macro |
| 3 | `meso` | **L2 Meso** 主尺度: 中观解剖区 (海马结构/DLPFC…) | Allen HBA 结构本体 + Brainnetome BNA246 (已登记) |
| 4 | `research` | LEGACY (L3) | compat → meso |
| 5 | `subregion` | **L3 Subregion** 主尺度: 亚区/亚核 (CA1/CA3/齿状回…) | Allen 亚区 + Winterburn 2013 (已登记) |
| 6 | `fine` | LEGACY (L4) | compat → cyto |
| 7 | `cyto` | **L4 Cyto** 主尺度: 细胞构筑区 (Julich-Brain) | siibra parser (已登记) |
| 8 | `ultra_fine` | LEGACY (L5) | compat → molecular |
| 9 | `molecular` | **L5 Molecular** 主尺度: 分子层 | 对接既有 molecular_attr 家族 |

### 兼容映射 (`granularity_level_compat_map`)

| legacy_level | canonical_level |
|---|---|
| whole_brain | macro |
| clinical | macro |
| research | meso |
| fine | cyto |
| ultra_fine | molecular |
| parcel | subregion |

**原则**: 旧值全部保留 active (除 `parcel` 保持 deprecated)，既有 canonical/candidate 数据行与测试不受影响；新数据走五级主尺度。schema 层 (`CanonicalRegionCreate`) 与 service 层 fallback 词表 (`_GRANULARITY_LEVEL_ORDER`) 均已同步 10 级；生产环境顺序由 DB 词表 `ORDER BY COALESCE(level_order, seq)` 决定。

## 2. Atlas Resource 数据层

**硬规则**: 外部 atlas 原始数据一律进 `atlas_region_resources`，绝不直接写入 canonical。

```
atlas_resources (来源登记)
   └─ atlas_region_resources (atlas 原生脑区行, atlas-native id 唯一)
         └─ atlas_region_mappings (atlas_region → canonical_region, 可审计)
               └─ canonical_brain_regions (仅经显式 API / 种子脚本写入)
```

- `atlas_region_mappings.mapping_type ∈ {exact, broader, narrower, uncertain}`; `species_relation ∈ {same_species, homology, unknown}`; 跨物种映射必须声明 `homology` (否则 service 拒绝)。
- 冲突守卫: 同一 atlas region 已有 active 映射指向其他 canonical 时，新映射被拒绝 (需先 supersede) → 完整性检查 `ATLAS_MAPPING_CONFLICT`。

### 已登记来源 (atlas_resources)

| resource_code | 数据 | 状态 |
|---|---|---|
| `allen_mouse_p56_structure` | Allen 小鼠 P56 结构本体 (structures.json, 1327 行) | ✅ 已导入 atlas_region_resources |
| `allen_hba_structure` | Allen 人脑结构本体 (ABA API) | ⏳ 已登记, 数据文件待获取 |
| `brainnetome_bna246` | Brainnetome BNA246 (246 区) | ⏳ 已登记, 官方文件开发环境无法下载 (不虚构) |
| `hippocampal_subfield_winterburn` | 海马亚区图谱 (Winterburn 2013) | ⏳ 已登记, 数据文件待获取 |
| `allen_cell_types_database` | Allen 细胞类型库 | ⏳ 已登记 (接口) |
| `julich_brain_siibra` | Julich-Brain 细胞构筑图谱 | ⏳ 已登记 (siibra parser 就绪) |
| `allen_hba_expression` | Allen 人脑基因表达 (既有 molecular_attr) | 保持现状, 不做大规模导入 |

## 3. 各尺度层状态

### Macro — 现状保持
Macro96 96-pool (`clinical` 层 48 canonical 区域, 96/96 candidate 锚定) 未删除、未迁移 ID。本阶段未改 `canonical_brain_regions` / `canonical_region_hierarchy` 中任何既有行，也未触碰连接/回路表。

### Meso — 已接入 (第一优先)
- 新增 curated 锚点 (human, UBERON 支撑, `created_by=seed:multiscale`):
  - `ng:br:hippocampal_formation` part_of `ng:br:hippocampus` (UBERON_0002421)
  - `ng:br:dlpfc` part_of `ng:br:rostral_middle_frontal` (UBERON_0009834)
  - `ng:br:vmpfc` part_of `ng:br:medial_orbitofrontal` (UBERON_0009835)
- Allen 小鼠 P56 结构本体 1327 行导入 atlas 层 (物种如实标记 mouse)；10 条 demo 映射覆盖四种 mapping_type，`species_relation=homology`。
- 诚实说明: structures.json 实为小鼠 P56 本体 (非人脑 HBA)；Allen HBA 与 Brainnetome 数据文件在当前环境不可得，仅登记 + 接口，未虚构任何 BNA/HBA 行。

### Subregion — 接口就绪 (不批量写入)
- 4 个 curated 锚点: `ng:br:ca1` (UBERON_0003881) / `ng:br:ca3` (UBERON_0003882) / `ng:br:dentate_gyrus` (UBERON_0001885) / `ng:br:subiculum` (UBERON_0002191)，均 part_of `ng:br:hippocampal_formation`。
- Winterburn 2013 已登记；批量导入接口 `/api/multiscale/atlas-regions/import` 就绪。

### Cyto — 独立 CellType 接口
- **细胞类型不是 BrainRegion**: `cell_type_registry` (code `ng:ct:*`) + `region_cell_alignment` (region_id, cell_type_id, mapping_type ∈ {contains/enriched/marker/unknown}, confidence, provenance)。
- Allen Cell Types Database 已登记; demo 3 个细胞类型 + 3 条对齐。

### Molecular — 对接 molecular_attr
- **分子实体不是 BrainRegion**: `molecular_entity_registry` (code `ng:mol:*`, entity_type ∈ {gene/protein/neurotransmitter/receptor}) + `region_molecular_alignment` (region_id, molecular_entity, entity_type, confidence, source)。
- 既有 `molecular_attr` 家族保持现状，本阶段不做大规模导入 (仅 demo 4 实体 + 4 对齐)。

## 4. 完整性检查 (extended)

`GET /api/canonical-regions/integrity` 在原有检查 (环/孤儿/重复身份/粒度方向/半球冲突/Macro96 覆盖) 基础上新增:

| code | 触发 | severity |
|---|---|---|
| `ORPHAN_ATLAS_PARENT` | atlas 行 parent_region_id 在本 atlas 内无法解析 | medium |
| `ATLAS_CROSS_SPECIES_MAPPING` | atlas↔canonical 物种不一致 | high (未声明 homology) / medium (已声明) |
| `ATLAS_MAPPING_CONFLICT` | 同一 atlas region 多条 active 映射指向不同 canonical | high |
| `MERGED_REGION_ALIGNMENT` | cell/molecular 对齐仍指向 merged 区域 (经 replaced_by 链可追溯) | low |

新增 counts: `meso_count` / `subregion_count` / `cyto_count` / `molecular_count` / `atlas_region_rows` / `atlas_mapping_rows` / `atlas_orphan_parents` / `atlas_cross_species_mappings` / `merged_region_alignments`。

## 5. 身份合并 (merge)

`POST /api/canonical-regions/merge` — source 保留 region_code (身份不迁移)，置 `status=merged` + `replaced_by_region_id` → target；part_of 边在粒度方向允许且无重复时重指向 target；active atlas 映射重指向 target 并在 provenance 记录 `merged_from` (去重守卫: target 已映射同一 atlas 行时 source 映射置 superseded,保证一 atlas 行最多一条 active 映射)；cell/molecular 对齐同样重指向 (唯一键冲突的行留在 merged 行上,可经 `replaced_by_region_id` 追溯,完整性检查以 `MERGED_REGION_ALIGNMENT` 提示)。

## 6. API

前缀 `/api/multiscale`: `GET /sources` · `POST /atlas-regions/import` · `GET /atlas-regions` · `POST|GET /atlas-mappings` · `POST /atlas-mappings/{id}/supersede` · `POST|GET /cell-types` · `POST|GET /region-cell-alignments` · `POST|GET /molecular-entities` · `POST|GET /region-molecular-alignments`

## 7. 本阶段禁止项 (严格遵守)

- ❌ 未修改 `mirror_region_connections` / `canonical_connections` / `canonical_circuits`
- ❌ 未生成任何推理结果
- ❌ 未自动生成不存在的脑区 (BNA/HBA 无数据即不写行)
- ❌ 未大规模导入 `molecular_attr`
- ❌ 完成后停止, 不进入 Connection/Circuit 推理
