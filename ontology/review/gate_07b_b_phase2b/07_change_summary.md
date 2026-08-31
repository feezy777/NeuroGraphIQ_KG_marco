# Gate 7B-B Phase 2B — Change Summary

本轮状态：**5 张 Evidence/Atlas 科学实体表已建（18/32），未 commit/push，未迁 legacy，未建 Phase 3+ 表**

## 1. 产出

| 类型 | 文件 |
|---|---|
| 新建 | `backend/migrations/gate7b_004_evidence_atlas_entities.sql` |
| 新建 | `backend/tests/test_gate7b_phase2b_evidence_atlas.py`（16 用例） |
| 修改 | `backend/tests/test_gate7b_phase2a_scientific.py`（2 处阶段耦合断言收敛：13 表子集 + Phase 3+ leak 列表） |
| 新建 | `ontology/review/gate_07b_b_phase2b/`（7 文件） |

## 2. 数据库实际变更

- production + E2E 各应用 `gate7b_004`。
- 新增 5 张 subtype 表 + `infra.assert_evidence_active_source()` 触发器。

## 3. 明确未做

- 未 commit / 未 push。
- 未建 Phase 3+ 表（hierarchy/spatial/aggregation/connection/circuit/mapping/assertion/evidence_links）。
- 未迁 legacy 数据。
- 未插入真实业务数据。
- 未修改 ontology TTL（hash 不变）。

## 4. 下一步（Phase 3，待人工指示）

- Connection / Circuit / hierarchy relations / RegionMapping / Assertion / EvidenceLink 等。
