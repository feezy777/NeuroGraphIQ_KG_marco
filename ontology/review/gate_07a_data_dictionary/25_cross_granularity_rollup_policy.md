# Gate 7A — Cross-Granularity Roll-up Policy（跨颗粒度聚合策略）

本轮状态: **仅设计文档，未修改正式 TTL**

---

## 1. 为什么需要 roll-up

细粒度（G4/G3）的 BrainRegion / Connection / Circuit 需要能聚合到粗粒度（G2/G1，尤其 Macro96）用于临床展示、全局浏览、macro 查询与全脑 summary。roll-up 是 NeuroGraphIQ 核心能力之一。

## 2. Stepwise roll-up

默认路径：G4 → G3 → G2 → G1，前提每一级存在 verified + rollup_eligible 的 mapping。

## 3. Direct skip-level roll-up

允许跳级（G4→G2、G4→G1、G3→G1），若某级 mapping 缺失但可可靠确定属于更粗 region。必须记录 rollup_path，不假装经过了不存在的中间 mapping。

## 4. 不是严格树

Atlas 之间定义方法/边界/reference space/coverage 不同，不能假定严格嵌套。roll-up 依赖显式 mapping，不依赖名称匹配。

## 5. 三类关系必须分开

| 类别 | 语义 | 表 |
|---|---|---|
| A. Anatomical hierarchy | CA1 subfieldOf Hippocampus | brain_region_hierarchy_relations |
| B. External Atlas mapping | Julich external → canonical BrainRegion | region_mappings |
| C. Canonical cross-granularity aggregation | 多个 canonical G4 → canonical G3 | brain_region_aggregation_mappings |

三类不能混。

## 6. brain_region_aggregation_mappings（新增第 32 表）

Integration / Granularity Roll-up Layer。表示一个 canonical BrainRegion 如何映射/贡献到另一个更粗 canonical BrainRegion。是 **NeuroGraphIQ cross-granularity integration truth**，不是 OWL anatomical truth。

字段：mapping_pk、mapping_id（NGIQ-BRAM-00000001）、source_region_pk（较细）、target_region_pk（较粗）、mapping_relation、mapping_method、source_granularity_level、target_granularity_level、source_coverage_ratio、target_coverage_ratio、spatial_overlap_ratio、mapping_confidence、rollup_eligible、is_primary_rollup、scientific_source_pk、provenance_json、record_status、remark。

> **source_granularity_level / target_granularity_level = DERIVED / SNAPSHOT**（= 对应 BrainRegion.granularity_level 自动复制，便于审计/历史快照/导出/前端展示/roll-up debugging；非独立 SCIENTIFIC CANONICAL TRUTH，不得由调用方任意提交）。canonical granularity truth 在 `brain_regions.granularity_level`。

## 7. source/target direction（固定）

source = 较细，target = 较粗。允许 G4→G3/G2/G1、G3→G2/G1、G2→G1。禁止 G1→G4 作为 roll-up（drill-down 反向查询即可）。

## 8. mapping_relation（候选）

exact_aggregate / contained_in / dominant_overlap / partial_overlap / composite_component / approximate / manual_curated / unresolved。partial_overlap 默认 rollup_eligible=FALSE。

## 9. mapping_method（候选）

authoritative_anatomical_mapping / atlas_crosswalk / spatial_overlap / hierarchy_inference / expert_manual / multimodal_consensus / hybrid。不全部锁 ENUM（reference vocabulary 或 VARCHAR + validation）。

## 10. coverage 字段

source_coverage_ratio（source 被 target 覆盖比例）、target_coverage_ratio（target 被 source 覆盖比例）、spatial_overlap_ratio（统一 reference space 后的 overlap）。均 nullable（非所有 mapping 有 voxel mask）。

## 11. N→1 拼成粗脑区

G4-A/B/C 都映射 G3-X → 允许多条 mapping。但存在三条 mapping 不自动宣称 G3-X 几何 = G4-A ∪ G4-B ∪ G4-C。

## 12. 1→N overlap

G4-A 70% overlap G3-X、30% overlap G3-Y → 不能伪造成 G4-A partOf G3-X（除非有明确 anatomical containment evidence）。

## 13. rollup_eligible

只有 TRUE 的 mapping 才能进入 Connection/Circuit roll-up / Macro96 aggregation。unresolved / weak partial_overlap / low-confidence 默认不 roll-up。

## 14. primary roll-up path

一个 G4 region 可映射多个 G3，但可指定 is_primary_rollup=TRUE 表示审核后的首选聚合路径。primary 不删除其他 mapping。

## 15. geometry policy

- 若 target G3/G2/G1 已有权威 Atlas/canonical spatial definition，优先用 target 自己的 canonical geometry，不用 fine parcel union 覆盖。
- 只有明确创建 derived aggregate spatial representation 时，才 union finer masks，并标 geometry_derivation=aggregated、derivation_type=inferred、source mappings 完整保留。

## 16. Connection roll-up

- 原始 G4 Connection = reported。
- 所有 coarse Connection = derivation_type=inferred、inference_type=hierarchical_rollup、记录 source_connection_pk / rollup_mapping_path / inference_record。
- 不把 coarse Connection 伪装成来源直接报告。

## 17. Connection deduplication

10 条 G4 connections roll-up 都得到 G1-A→G1-B → 生成一个 inferred canonical coarse Connection，记录 supporting_fine_connection_count / source_connection_ids / evidence roll-up summary。fine-level evidence 保持原始 provenance。

## 18. self-loop collapse

若 roll-up 后 source 与 target 属同一 G1 region → intra_region_collapsed_connection，不创建普通 inter-region Connection，保留 inference trace/statistics。

## 19. Circuit roll-up

G4 Circuit → G3/G2/G1 representation，标 derivation_type=inferred、construction_mode=hierarchical_rollup、保留 source_circuit_pk / source_memberships / rollup_mapping_path。

## 20. Circuit member collapse

多个 G4 members roll-up 成同一 G1 region → deduplicate coarse member nodes，保留 fine_member_count / source_member_ids 作为 lineage。

## 21. inferred provenance

所有 coarse roll-up 产物标 inferred + rollup lineage；reported 只属于 fine-level 原始证据。

## 22. Macro96 roll-up

Macro96 = NeuroGraphIQ internal high-level aggregation layer。G1 Connection/Circuit 均由 fine → Macro roll-up 产生，derivation_type=inferred，不伪装 reported。

## 23. rollback / recompute principle

roll-up 产物可重算/回滚（由 source fine 数据 + mapping 重新派生），不把 derived coarse 当独立 truth。

## 24. future granularity extension

未来如需 G5 或更细，需新 mapping relation + policy review，不在 V1 硬编码。
