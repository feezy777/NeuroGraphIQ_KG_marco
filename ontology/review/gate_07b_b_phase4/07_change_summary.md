# Gate 7B-B Phase 4 — Change Summary

本轮状态：**3 张 Circuit 科学表已建（28/32），未 commit/push，未迁 legacy，未建 RegionMapping/Assertion 表**

## 1. 产出

| 类型 | 文件 |
|---|---|
| 新建 | `backend/migrations/gate7b_007_circuit_core.sql` |
| 新建 | `backend/tests/test_gate7b_phase4_circuit.py`（18 用例） |
| 修改 | `backend/tests/test_gate7b_phase3b_connection.py`（count→子集；leak 收敛到 RegionMapping/Assertion） |
| 修改 | `backend/tests/test_gate7b_phase3a_hierarchy_spatial.py`、`test_gate7b_phase2b_evidence_atlas.py`、`test_gate7b_phase2a_scientific.py`（leak 收敛） |
| 新建 | `ontology/review/gate_07b_b_phase4/`（7 文件） |

## 2. 数据库实际变更

- production + E2E 各应用 `gate7b_007`。
- 新增 3 张表。

## 3. 明确未做

- 未 commit / 未 push。
- 未建 RegionMapping/Assertion 表（region_mappings / relation_definitions / knowledge_assertions / evidence_links）。
- 未建 CircuitType ontology taxonomy / circuit_types。
- 未实现 Circuit 自动生成 / Connection 自动补全 / graph-cycle 检测生成。
- 未迁 legacy（coarse_circuits / circuit_steps / mirror / molecular_attr / 旧候选）。
- 未插入真实业务数据。
- 未修改 ontology TTL（hash 不变）。

## 4. 下一步（RegionMapping/Assertion Phase，待人工指示）

- region_mappings / relation_definitions / knowledge_assertions / evidence_links 等。
