# Gate 8A — Scope & Authoritative Source

## 1. 本轮范围

使用 Human Brainnetome Atlas 做 **20 个代表性脑区**真实入库 Pilot，跑通：

```
Scientific Source → Atlas → ExternalRegion → proposed canonical BrainRegion → Alias/Xref → RegionMapping
```

- 不导入全部 246；不做 Circuit/Connection；不处理旧数据；不改 frontend/Neo4j/schema。
- 不 commit/push，等待人工数据审查。

## 2. Authoritative Brainnetome source（真实文件，非 LLM 记忆）

| 项 | 值 |
|---|---|
| source file path | `backend/data/atlases/brainnetome/BNA246_regions_circos.tsv` |
| source origin | Human Brainnetome Atlas 官方 circos band 文件（atlas.brainnetome.org） |
| atlas / version | BNA246（2016） |
| species | Homo sapiens（NCBI:9606） |
| region count | 246（123 left + 123 right） |
| source-native ID | band_id（1–246 数值） |
| source-native name | `native_name`（如 `SFG_L_7_1` =  gyrus_hemi_n_idx） |

- 每 band 含：gyrus 缩写、hemisphere（L/R）、n/idx、lobe（14 个 circos lobe 定义）。
- 25 个唯一 gyrus，均双半球。
- 未命中 `MISSING_AUTHORITATIVE_BRAINNETOME_SOURCE`（source 存在且可追溯）。

## 3. 命名来源说明（非伪造）

- `name_en` = 官方 gyrus 全名 + BNA 编号（如 "Superior frontal gyrus BNA 7_1"），gyrus 全名来自仓库内既有 BNA 缩写映射（`brainnetome_importer.py` GYRUS_PARENT / 本 importer _GYRUS_NAMES），非 LLM 生成。
- `name_zh` = 同一映射的既有中文 gyrus 名（translated_human，可追溯）。
- `source_name_original` = circos `native_name`（源文件原文）。

## 4. 非 scientific source 排除

GPT / DeepSeek / Claude / BioSEPBERT / ImportPipeline / Human curator / RuleEngine 均为 provenance agent，未进入 sources。
