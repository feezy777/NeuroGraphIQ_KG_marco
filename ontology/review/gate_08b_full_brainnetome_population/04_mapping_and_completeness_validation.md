# Gate 8B — Mapping & Completeness Validation

## 1. RegionMapping（246，first-class shared-PK）

- `entity_pk → kg_entities`（entity_type='region_mapping'），public ID = NGIQ-RMAP。
- `external_region_pk → external_regions.entity_pk`；`brain_region_pk → brain_regions.entity_pk`。
- mapping_type='exact'（ExternalRegion → 同一 BNA parcel 的 proposed canonical BrainRegion，direct canonicalization，非 fuzzy matching）。
- mapping_method='automatic'；mapping_source='brainnetome_direct'；review_status='pending'（未自动 approved）。
- name_similarity / semantic_similarity / spatial_overlap / overall_confidence 全 **NULL**（deterministic rule，无 probabilistic score）。
- `evidence_summary_en` 说明 "Direct canonicalization of BNA246 parcel <native> ..."。

## 2. 完整性（246/246）

- external_regions=246、brain_regions=246、region_mappings=246、entity_aliases=246、entity_xrefs=246。
- 每 1 个 BrainRegion 都有 native alias + Brainnetome xref + RegionMapping（missing=0）。
- 无 multiple mapping for same ExternalRegion→same BrainRegion（dup=0）。

## 3. RegionMapping ≠ AggregationMapping

- `brain_region_aggregation_mappings` = **0**（未自动生成 G3→G2/G1 roll-up / partOf / subfieldOf）。

## 4. Transactional integrity

- **rollback test PASS**：scratch DB 上注入失败（第 6 parcel 抛错）→ sources/atlases/external/brain/mapping/alias/xref **全部 0**（完整回滚，无半成品）。
- 不允许"成功 180 失败 66 留下半成品"。

## 5. Rerun safety

- 第二次 `--mode full --apply`：new/updated 全 0（稳定生产级实现）。
