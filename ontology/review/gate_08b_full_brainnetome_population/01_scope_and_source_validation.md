# Gate 8B — Scope & Source Validation

## 1. 本轮范围

将 Gate 8A 已冻结 importer 扩展为完整 Human Brainnetome BNA246 全量数据生产（复用同一 canonicalization 核心，不复制第二套逻辑）。

目标：246 ExternalRegion → 246 proposed canonical BrainRegion → 246 RegionMapping → 246 native alias → 246 Brainnetome xref。现有 20 条 Pilot 复用，预计新增 226。

## 2. Source validation（写库前强制）

- authoritative source：`backend/data/atlases/brainnetome/BNA246_regions_circos.tsv`（Human Brainnetome Atlas，BNA246 (2016)，Homo sapiens）。
- `_validate_source()` **fail closed**（FULL_IMPORT_BLOCKED）：band=246、native code 唯一、无空 code、hemisphere 可解析、所有 anatomical category 均能由 `_BNA_ANATOMICAL_NAMES`（25 项，仓库既有 BNA 映射）解析；未知缩写 → 停止，无 fallback 名称。
- 实测：246 parcels，**left=123 right=123**，**25 anatomical categories**，全部通过。

## 3. importer 重构

- `backend/scripts/import_brainnetome_pilot.py` 增加 `--mode pilot|full`（默认 pilot，Gate 8A 行为兼容）。
- pilot = Gate 8A 确定性 20；full = 全部 246。**共用同一命名/映射/复用核心**，无第二套逻辑。
- 保留 audit 链：review 文档注明 rename 兼容（文件名未改，仅加 mode）。

## 4. 冻结 policy 沿用（不重新设计）

Gate 8A naming policy（Priority 2 stable constructed）：
- EN：`Left|Right <anatomical region>, Brainnetome <n>_<idx>`；ZH：`左侧|右侧<脑区>（Brainnetome <n>-<idx>）`。
- `name_en_source='normalized'`、`name_zh_source='normalized'`。
- native identity 保留：`source_name_original`=native code；alias=native code（atlas_label）；xref=Brainnetome numeric code。
- mapping_type='exact'、mapping_method='automatic'、mapping_source='brainnetome_direct'、review_status='pending'、similarity/confidence 全 NULL。
