# Gate 7A — Consistency Audit（最终一致性审计）

审计时间: 2026-08-28
审计范围: `ontology/review/gate_07a_data_dictionary/` 全部文档
审计性质: 只修文档一致性，不重设计、不进 Gate 7B

---

## A. ID Consistency

- 正式 public ID 格式：`NGIQ-<TYPE>-<8位>`（如 `NGIQ-BR-00000001`）。
- 8 位、永不复用、deprecated 永久保留、merge 后旧 ID 保留 lineage/redirect、数字不编码科学意义。
- 已修正历史 6 位示例：`NGIQ-PRED-000001 → NGIQ-PRED-00000001`、`NGIQ-AST-000001 → NGIQ-AST-00000001`（13_relation_assertion_tables.md）。
- 结论：**已无有效 6 位规范文本**。

## B. Table Count Consistency

- 最终科学表总数 = **32**（Governance 独立 schema，不计入）。
- 模块：Identity 4 / Scientific Entity 14 / Hierarchy 2 / Spatial 1 / Granularity Integration 1 / Connection 3 / Circuit 3 / Atlas Mapping 1 / Assertion 3 = 32。
- 已修正所有残留 31（01/19/21/22/23/revision_summary）；22 历史 29→31 已标 HISTORICAL。
- 结论：**核心文档均为 32，无标题 31/正文 32 冲突**。

## C. Hierarchy Consistency

- BrainRegion hierarchy relation_type 仅：`part_of`、`subfield_of`（subfield_of 是更具体 part_of）。
- 已修正 01_architecture_overview.md（删除 overlaps/located_in）、18_complete_data_dictionary.md（relation_type 仅 part_of/subfield_of）。
- `overlaps` / `located_in` / `adjacent_to` 当前状态 = **DEFER**（未来 Spatial Relation Model），不参与 ancestor/descendant/hierarchical roll-up，非 BrainRegion hierarchy canonical truth。
- Function hierarchy：`subclass_of` / `part_of`，traversal 显式选择 relation_type。

## D. Granularity Consistency

- G1_MACRO=Macro96；G2_MESO_ANATOMICAL=AAL3；G3_MESO_FINE=Human Brainnetome（HCP-MMP/Schaefer supplementary）；G4_MICROSTRUCTURAL_FINE=Julich-Brain；BigBrain=spatial reference only。
- 全库统一，无冲突。

## E. Aggregation Consistency

- source_region_pk = 较细，target_region_pk = 较粗。
- 合法：G4→G3/G2/G1、G3→G2/G1、G2→G1；非法：G1→G2/G4、G2→G3。
- 允许 skip-level；允许 N→1 与 1→N；不强制 strict tree；drill-down 用反向查询。

## F. Truth-source Consistency

- `brain_regions.granularity_level` = canonical granularity truth。
- aggregation mapping 的 source/target_granularity_level = **DERIVED / SNAPSHOT**（自动复制，非独立 truth）。
- `parent_region_pk` / `parent_function_pk` = DERIVED cache。
- 各 derived count（evidence_count 等）标 DERIVED。

## G. Roll-up Consistency

- coarse Connection = derivation_type=inferred + inference_type=hierarchical_rollup。
- coarse Circuit = derivation_type=inferred + construction_mode=hierarchical_rollup。
- Macro96 = inferred roll-up（不伪装 reported）。
- self-loop collapse → intra_region_collapsed_connection（非普通 Connection）。
- duplicate coarse Connection → 单个 inferred canonical + supporting_fine_connection_count。

## H. Species Consistency

- Homo sapiens = NCBI taxon 9606。
- Allen Mouse = production_eligible FALSE，excluded。
- Allen Human = 仅验证 9606 后为 auxiliary source。

---

## 结论

- **blocking inconsistency 数：0**。
- 正式 TTL 未修改；未创建 migration；未修改数据库；未 commit/push。
- 全部文档已统一到：32 表、8 位 ID、G1–G4、part_of/subfield_of、aggregation fine→coarse、roll-up=inferred、human-only 9606。
