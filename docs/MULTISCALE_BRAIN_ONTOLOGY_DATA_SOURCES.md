# 多尺度脑知识本体 — 数据源登记体系

> 分支 `codex/ontology-evidence` · 外部数据接入（10 部分任务）的第 1 部分交付。
> 配套文档：[MULTISCALE_GRANULARITY_ARCHITECTURE.md](./MULTISCALE_GRANULARITY_ARCHITECTURE.md)（五级粒度体系 + atlas 层）

## 1. 登记原则

所有外部数据必须经过治理链，**禁止**直接把外部数据写入 canonical：

```
External Resource（数据源登记）
    ↓
Mapping（atlas_region_resources → atlas_region_mappings / *_alignment 表）
    ↓
Canonical Entity（canonical_brain_regions / cell_type_registry / molecular_entity_registry）
```

- 每个导入器脚本幂等（可重复运行，不产生重复行）。
- 每条 mapping 记录 `mapping_type`（exact / broader / narrower / uncertain）+ 置信度 + 溯源（source 字段），跨物种映射有专门的守卫（见 BR3 架构文档）。
- 左右半球信息存 `laterality` 字段，**不创建** `left_xxx` / `right_xxx` 实体（`region_code` 中 `_l/_r` 后缀仅为保证 code 唯一）。
- Cell Type 与 Gene **永不进入** `canonical_brain_regions` / `canonical_region_hierarchy`——分别登记在 `cell_type_registry` / `molecular_entity_registry`，通过 alignment 表与脑区对齐。
- Fine 粒度导入**永不覆盖**已有 canonical 区域。

## 2. 数据源清单

### 2.1 脑区本体数据源（Brain Region Ontology）

| 数据源 | 版本/引用 | 物种 | 获取方式 | 导入脚本 | 登记行数 | 映射到 canonical |
|---|---|---|---|---|---|---|
| AAL3 / Macro96 标准池（既有，BR3 基线） | Macro96 96 脑区池 | human | 项目内既有数据 | `seed_macro96_canonical_l2.py` | — | clinical 48 区 + macro 4 系 |
| Brainnetome Atlas | BNA246 (2016) | human | 官方 circos 带文件 `data/atlases/brainnetome/BNA246_regions_circos.tsv`（brainnetome.org 官方站点在当前环境不可达，使用官方 circos 文件） | `scripts/brainnetome_importer.py` | 246（210 皮层 + 36 皮层下） | 246 条 exact → meso 246 区 |
| HCP MMP1.0 | Glasser 2016, 360-parcel | human | 官方标签文件 `data/atlases/hcp_mmp/glasser360NodeNames.txt` | `scripts/hcp_mmp_importer.py` | 360 | 360 条 exact → meso 360 区 |
| Hippocampal Subfield Atlas | Winterburn 2013, NeuroImage 74:254-265 | human | 无机器可读标签文件，按已发表图谱描述人工整理 6 标签 × L/R | `scripts/hippocampal_subregion_importer.py` | 12 | 5 条 exact（CA1/CA2/CA3/CA4-DG/Subiculum）；SRLM 为层结构**故意不映射** |
| Julich-Brain (siibra) | Amunts & Zilles, Science 348:1421-1422, 2015 | human | 批量数据不可达（见 §4）；经典 Brodmann 分区作为 curated fine 锚点（**无** atlas 行，不伪造） | `scripts/fine_region_importer.py` | 0（预留路径 `data/atlases/julich/`） | 15 curated Brodmann fine 锚点（直连 canonical，无 atlas 行） |
| Allen Mouse Brain Atlas | P56 structure ontology | mouse | `data/allen/`（BR3 导入） | BR3 导入脚本 | 1327 | 5 条跨物种 demo 映射（broader 1 / narrower 2 / uncertain 2，homology 守卫） |

### 2.2 生物层数据源（Biological Layer）

| 数据源 | 版本/引用 | 物种 | 获取方式 | 导入脚本 | 登记行数 | 对齐 |
|---|---|---|---|---|---|---|
| Allen Cell Types Database | Hodge 2019 (human MTG SMART-seq), Nature 573:61-68 | human | `celltypes.brain-map.org` API 不可达（见 §4）；按已发表 taxonomy 人工整理 18 类 + BR3 既有 3 条 demo | `scripts/cell_type_importer.py` | 21（cell_type_registry） | 23 条 region_cell_alignment（contains 22 / marker 1） |
| GTEx v10 | `GTEx_Analysis_v10_RNASeQCv2.4.2_gene_median_tpm.gct.gz`（adult-gtex 官方桶） | human | `data/atlases/gtex/gene_median_tpm_v10.gct.gz`，13 个脑组织 | `scripts/molecular_importer.py` | 15（molecular_entity_registry，每组织 top-10 基因去重） | 90 条 region_molecular_alignment（evidence_type=expression） |
| Allen HBA expression（既有 molecular_attr 家族） | BR3 基线 | human | 项目内既有 | BR3 既有 | — | 4 条既有 alignment（保留原样） |

## 3. 当前数据规模（2026-08-21 实测）

### canonical_brain_regions — 682 区

| granularity_level | 数量 | 来源 |
|---|---|---|
| whole_brain (L0) | 1 | BR3 基线 |
| macro (L1) | 4 | BR3 基线 |
| clinical (L2) | 48 | Macro96 池 |
| meso (L3) | 609 | BNA246 (246) + HCP-MMP (360) + BR3 锚点 (3) |
| subregion (L5) | 5 | BR3 锚点 4 + Winterburn CA2 (1) |
| fine (L6) | 15 | curated Brodmann 锚点 |

### 登记表

| 表 | 行数 |
|---|---|
| atlas_resources | 4（BNA246 / MMP1.0 / Winterburn / Allen P56） |
| atlas_region_resources | 1945（Allen 1327 + BNA 246 + MMP 360 + Winterburn 12） |
| atlas_region_mappings | 626（exact 621 / broader 1 / narrower 2 / uncertain 2） |
| cell_type_registry | 21 |
| region_cell_alignment | 24（contains 23 / marker 1） |
| molecular_entity_registry | 15 |
| region_molecular_alignment | 95（GTEx 90 + BR3 demo「Allen HBA 家族」5，含旗舰示例 BDNF@hippocampus） |

## 4. 缺失数据源 / 诚实限制（不伪造数据）

| 缺口 | 说明 | 影响 |
|---|---|---|
| Julich-Brain 批量数据 | siibra 数据在开发环境不可达；`fine_region_importer.py` 已实现完整批量导入路径（`data/atlases/julich/` 下 JSON/TSV/CSV），一旦拿到文件即可运行 | fine 粒度目前仅 15 个 curated Brodmann 锚点（无 atlas 行） |
| Allen celltypes API | `celltypes.brain-map.org` 不可达 | cell type 集为 curated Hodge 2019 taxonomy，非全量 |
| GTEx 3 个组织未对齐 | hypothalamus / spinal cord / substantia nigra 无 1:1 canonical 区域 | 已如实报告为 unaligned，未强行映射 |
| Winterburn 无机器可读文件 | 标签为按论文人工整理 | 已注明 curated |

## 5. 导入器清单（backend/scripts/）

| 脚本 | 作用 | 幂等 |
|---|---|---|
| `brainnetome_importer.py` | BNA246 → atlas → meso canonical（`part_of` 回旋父区，父区映射显式记录） | ✅ |
| `hcp_mmp_importer.py` | MMP1.0 360 → atlas → meso canonical（`part_of` cerebrum，官方文件无回旋信息——如实记录） | ✅ |
| `hippocampal_subregion_importer.py` | Winterburn 6×2 → atlas → subregion（仅新建 CA2；SRLM 不映射） | ✅ |
| `fine_region_importer.py` | Julich-Brain 批量路径（预留）+ curated Brodmann fine 锚点；不覆盖已有区域 | ✅ |
| `cell_type_importer.py` | Hodge 2019 → cell_type_registry + region_cell_alignment | ✅ |
| `molecular_importer.py` | GTEx v10 → molecular_entity_registry + region_molecular_alignment | ✅ |
| `seed_multiscale_ontology.py` | BR3 基线：7 canonical 锚点 + 10 demo 映射 + 五级词表 | ✅ |

运行方式（backend/ 目录下）：

```powershell
.venv\Scripts\python.exe scripts\brainnetome_importer.py   # 其余脚本同理
```

## 6. 关联 API

| API | 说明 |
|---|---|
| `GET /api/canonical-regions?granularity_level=` | 按粒度层级列出 canonical 区域 |
| `GET /api/canonical-regions/{id}/multiscale` | 统一多尺度视图（region/parents/children/meso/subregions/fine/cell_types/molecules） |
| `GET /api/multiscale/cell-types` | Cell Type 登记表 |
| `GET /api/multiscale/molecular-entities` | 分子实体登记表 |
| `GET /api/multiscale/region-cell-alignments?region_id=&cell_type_id=` | 双向过滤的细胞对齐 |
| `GET /api/multiscale/region-molecular-alignments?region_id=&molecular_entity_id=` | 双向过滤的分子对齐 |
