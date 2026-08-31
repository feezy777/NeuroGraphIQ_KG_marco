# Gate 7B-B Phase 3A — Change Summary

本轮状态：**4 张 Hierarchy/Spatial/Granularity 表已建（22/32），未 commit/push，未迁 legacy，未建 Phase 3B+ 表**

## 1. 产出

| 类型 | 文件 |
|---|---|
| 新建 | `backend/migrations/gate7b_005_hierarchy_spatial_granularity.sql` |
| 新建 | `backend/tests/test_gate7b_phase3a_hierarchy_spatial.py`（23 用例） |
| 修改 | `backend/tests/test_gate7b_phase2b_evidence_atlas.py`（count→子集；leak 列表收敛到 Phase 3B+） |
| 修改 | `backend/tests/test_gate7b_phase2a_scientific.py`（leak 列表收敛到 Phase 3B+） |
| 新建 | `ontology/review/gate_07b_b_phase3a/`（7 文件） |

## 2. 数据库实际变更

- production + E2E 各应用 `gate7b_005`。
- 新增 4 张表 + `infra.assert_aggregation_granularity()` 触发器 + `infra.ngiq_spat_seq`。

## 3. 明确未做

- 未 commit / 未 push。
- 未建 Phase 3B+ 表（connections/circuits/region_mappings/assertion/evidence_links）。
- 未迁 legacy 数据（旧 hierarchy / Macro96 / Brainnetome / Julich mapping / coordinates_mni / kg_mappings）。
- 未插入真实业务数据。
- 未修改 ontology TTL（hash 不变）。

## 4. 下一步（Phase 3B，待人工指示）

- Connection / Circuit / RegionMapping / Assertion / EvidenceLink 等。
