# Gate 8A — Risk Register & Full Import Readiness

## 1. BLOCKER = 0

## 2. MAJOR = 0

## 3. 风险处置

| # | 项 | 状态 | 说明 |
|---|---|---|---|
| M1 | source provenance / atlases 无 `scientific_source_pk` 列 | **RESOLVED** | sources.provider / citation_text / last_checked_at 已补（Gate 8A closeout）。Atlas→Source 关联记录在 atlas 的 `kg_entities.metadata_json`（`{"scientific_source":"<NGIQ-SRC>"}`）；atlases 无 source FK 列为 schema 既定（未改）。license=NULL（无正式 mapping 规则不自行填）；description 保持 NULL（不为填满生成低价值描述）。 |
| M2 | 全部 mapping_type='exact' | **ACCEPTED** | deterministic direct canonicalization：ExternalRegion → 同一 BNA parcel 的 proposed canonical BrainRegion，身份一致；mapping_method='automatic'、overall_confidence=NULL（非 probabilistic model）。全量导入时对已存在 canonical 的 parcel 需按实际关系细分。 |
| M3 | name_en/name_zh 由仓库内既有 BNA 缩写映射确定性构造 | **ACCEPTED** | `_BNA_ANATOMICAL_NAMES` 取自 `brainnetome_importer.py`（既有 curated 映射），非 LLM、非逐条人工翻译；`name_en_source='normalized'`、`name_zh_source='normalized'`（未新增 vocabulary）。 |

> **Final Semantic Cleanup（本轮）**：`overall_confidence` 0.9 → **NULL**（无计算依据的固定值，exact 为 deterministic rule）；`name_zh_source` `translated_human` → **normalized**（确定性构造，非真实人工翻译）。详见 `07_canonical_identity_repair.md` §9。

## 4. 验证结果汇总（§十七 17 项）

1. pilot=20 ✅  2. external=20/brain=20 ✅  3. proposed=100% ✅  4. active 新增=0 ✅
5. Human-only（9606）✅  6. granularity=G3_MESO_FINE ✅  7. source_name_original 完整 ✅
8. NGIQ 唯一 ✅  9. Brainnetome external ID 唯一 ✅  10. alias/xref 分离 ✅
11. mapping target 正确 ✅  12. mapping_type 合法（7-value）✅  13. aggregation=0 ✅
14. rerun 0 新增 ✅  15. schema 32/32 ✅  16. legacy write=0 ✅  17. TTL 不变 ✅

## 5. Full Brainnetome Import Readiness

| # | 条件 | 状态 |
|---|---|---|
| 1 | pilot 链路（Source→Atlas→External→proposed→Alias/Xref→Mapping）跑通 | ✅ |
| 2 | importer 可复现 / duplicate-safe / rerun 0 新增 | ✅ |
| 3 | Human-only + G3_MESO_FINE + proposed 策略 | ✅ |
| 4 | alias/xref 分离 + mapping_type 受控 | ✅ |
| 5 | aggregation=0 / schema 32/32 / TTL 不变 / legacy 无写 | ✅ |
| 6 | BLOCKER=0 | ✅ |

**Gate 8A 状态：PASS**

**Full Brainnetome Import Readiness = READY FOR FULL BRAINNETOME POPULATION**

（Gate 8A 已正式通过并冻结：canonical naming collision 已修（0 重复）、exact provenance 已补、overall_confidence NULL、name sources normalized、source provenance 补全、public IDs 不变、schema 32/32。全量 246 导入前置：对已存在 canonical 的 parcel 需按实际关系细分 mapping_type；先由下一 Gate 执行。）

> 详见 `07_canonical_identity_repair.md`。
