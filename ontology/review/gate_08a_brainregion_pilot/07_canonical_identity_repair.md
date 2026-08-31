# Gate 8A — Canonical Identity Repair（简短）

## 1. 原问题

BrainRegion canonical `name_en` 左右碰撞：`SFG_L_7_1` 与 `SFG_R_7_1` 均得 `Superior frontal gyrus BNA 7_1`。

**canonical name 原始来源**：importer / repository 构造的 display name（B，非官方 subdivision name）。circos 源文件仅含 native code（`SFG_L_7_1`）+ gyrus 缩写 + lobe，无官方英文 parcel subdivision 名称；`_GYRUS_NAMES`（来自既有 `brainnetome_importer.py` BNA 缩写映射）提供 gyrus 级解剖名。

## 2. 修复前

**9 组左右侧 name_en collision**：

```
Superior frontal gyrus BNA 7_1       (BR-1 / BR-2)
Inferior frontal gyrus BNA 6_1       (BR-3 / BR-4)
Superior temporal gyrus BNA 6_1      (BR-5 / BR-6)
Middle temporal gyrus BNA 4_1        (BR-7 / BR-8)
Superior parietal lobule BNA 5_1     (BR-9 / BR-10)
Inferior parietal lobule BNA 6_1     (BR-11 / BR-12)
Insular gyrus BNA 6_1                (BR-13 / BR-14)
Medioventral occipital cortex BNA 5_1(BR-15 / BR-16)
Hippocampus BNA 2_1                  (BR-17 / BR-18)
```

## 3. Naming policy（Priority 2：stable constructed form）

权威 source 无官方 subdivision 英文名 → 使用稳定构造名，**hemisphere 显式进入 canonical identity expression**：

```
Left <anatomical region>, Brainnetome <n>_<idx>      / Right <anatomical region>, Brainnetome <n>_<idx>
左侧<脑区>（Brainnetome <n>-<idx>）                   / 右侧<脑区>（Brainnetome <n>-<idx>）
```

例：`Left Superior frontal gyrus, Brainnetome 7_1` / `Right Superior frontal gyrus, Brainnetome 7_1`。

- `name_en_source='normalized'`（构造/规范化名），`name_zh_source='translated_human'`（来自仓库既有 BNA 中文映射，**非** authoritative Brainnetome；未伪装）。
- **BNA numeric ID 不伪造**（band_id 保持 `1 / 2 / 29 / 30...`，未造 `L1/R2`）。

## 4. 修复方式（idempotent repair，非重建）

- 保留 `entity_pk` / `entity_id`（NGIQ-BR / NGIQ-XREG / RMAP 全不变）。
- 更新 canonical BrainRegion `name_en`/`name_zh`/name_source。
- 补 mapping provenance（`mapping_source` + `evidence_summary_en`）+ mapping entity display name。
- 不重复 Alias / Xref / Mapping。

## 5. exact mapping rationale（保留 exact）

关系 = Brainnetome ExternalRegion → 同一 BNA parcel 的 proposed canonical BrainRegion（**direct canonicalization**，非 fuzzy atlas matching）。`mapping_method='automatic'` 保留；`mapping_source='brainnetome_direct'` + `evidence_summary_en`（"Direct canonicalization of BNA246 parcel <native> into its proposed canonical BrainRegion..."）。
**未伪造 similarity score**（name_similarity / semantic_similarity / spatial_overlap 均 NULL）。

## 6. 修复前后结果

| 项 | before | after |
|---|---|---|
| duplicate canonical name groups | 9 | **0** |
| brain_regions / external_regions / mappings | 20 / 20 / 20 | 20 / 20 / 20 |
| NGIQ-BR / XREG IDs | — | **全部不变** |
| xref / alias / source_name_original | — | **全部不变** |
| record_status | proposed | proposed（无 ACTIVE） |
| mapping_type / method | exact / automatic | exact / automatic |
| aggregation 新增 | 0 | 0 |
| 第三次 rerun 新增/更新 | — | **0 / 0** |

## 7. 验证（20 项）

全部通过：数量不变、ID 不变、duplicate=0、L/R 显式、proposed 100%、provenance 非空、similarity 未伪造、aggregation=0、schema 32/32、TTL 不变、legacy 无写。全量测试 **166 passed**。

## 8. public IDs unchanged

- NGIQ-BR / NGIQ-XREG / NGIQ-RMAP / source / atlas IDs 均未重分配。

## 9. Final Semantic Cleanup（本轮 MODERATE 修复）

### 9.1 overall_confidence：0.9 → NULL

- 原 0.9 为 importer 固定值，**无计算依据**（exact 来自 deterministic identity/canonicalization rule，非 probabilistic mapping model）。
- 修复后全部 **NULL**（20/20）；importer 未来 direct canonicalization 默认 NULL；不写 1.0、不生成假 confidence。

### 9.2 name_zh_source：translated_human → normalized

- **诊断**：中文 canonical name（"左侧额上回（Brainnetome 7-1）"）= 仓库 BNA 中文 gyrus 字典（`_GYRUS_NAMES`）+ deterministic 构造（hemisphere 前缀 + 字典词 + parcel code），**非真实人工逐条翻译/确认**。
- CURRENT `name_zh_source` 词表：source / human_curated / translated_human / translated_ai / normalized / unknown。
- **最终采用 'normalized'**（deterministic normalized/constructed name 的 CURRENT 等价值；与 name_en_source='normalized' 一致）。
- **未新增 vocabulary**（无 gap，无需 blocker 报告）。

### 9.3 修复后验证（20 项全过）

brain_regions=20 / external=20 / mappings=20；EN/ZH duplicate=0；mapping_type=exact×20、method=automatic×20、source=brainnetome_direct×20；overall_confidence NULL×20；name/semantic/spatial_similarity NULL×20；review_status=pending×20；record_status=proposed×20；xref/alias 不变；schema 32/32；TTL 不变；legacy 无写；全量测试 166 passed；第三次 rerun 新增/更新=0。
