# Gate 7B-B Phase 3B — Change Summary

本轮状态：**3 张 Connection 科学表已建（25/32），未 commit/push，未迁 legacy，未建 Circuit/Assertion 表**

## 1. 产出

| 类型 | 文件 |
|---|---|
| 新建 | `backend/migrations/gate7b_006_connection_core.sql` |
| 新建 | `backend/tests/test_gate7b_phase3b_connection.py`（19 用例） |
| 修改 | `backend/tests/test_gate7b_phase3a_hierarchy_spatial.py`（count→子集；leak 收敛到 Circuit+） |
| 修改 | `backend/tests/test_gate7b_phase2b_evidence_atlas.py`、`test_gate7b_phase2a_scientific.py`（leak 收敛到 Circuit+） |
| 修改 | `ontology/review/gate_07b_a1/05_ngiq_prefix_registry.md`（新增 connection_endpoint → NGIQ-EP，30→31） |
| 新建 | `ontology/review/gate_07b_b_phase3b/`（7 文件） |

## 2. 数据库实际变更

- production + E2E 各应用 `gate7b_006`。
- 新增 3 张表 + `infra.ngiq_ep_seq` + `infra.assert_no_self_endpoint()` 触发器。

## 3. 明确未做

- 未 commit / 未 push。
- 未建 Circuit/Assertion 表（circuits / circuit_* / region_mappings / assertion / evidence_links）。
- 未建 direct-edge canonical table（structurallyConnectedTo 等）。
- 未实现 Connection roll-up / hierarchical_rollup。
- 未迁 legacy（kg_connections / mirror / Macro / molecular_attr connection）。
- 未插入真实业务数据。
- 未修改 ontology TTL（hash 不变）。

## 4. 下一步（Circuit Phase，待人工指示）

- circuits / circuit_region_memberships / circuit_connection_memberships 等。
