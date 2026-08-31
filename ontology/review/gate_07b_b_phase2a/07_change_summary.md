# Gate 7B-B Phase 2A — Change Summary

本轮状态：**9 张 core scientific entity 表已建（13/32），未 commit/push，未迁 legacy，未建 Phase 2B/3+ 表**

## 1. 产出

| 类型 | 文件 |
|---|---|
| 新建 | `backend/migrations/gate7b_003_core_scientific_entities.sql` |
| 新建 | `backend/tests/test_gate7b_phase2a_scientific.py`（15 用例） |
| 修改 | `backend/tests/test_gate7b_phase1_identity.py`（`test_table_count_is_exactly_four` → `test_identity_four_tables_present`，适配 13 表） |
| 新建 | `ontology/review/gate_07b_b_phase2a/`（7 文件） |

## 2. 数据库实际变更

- production + E2E 各应用 `gate7b_003`。
- 新增 9 张 subtype 表 + 集中式 `infra.assert_entity_type()` 守卫函数 + 9 个触发器。

## 3. 明确未做

- 未 commit / 未 push。
- 未建 Phase 2B/3+ 表（atlases/evidence/connections/circuits/hierarchy/…）。
- 未迁 legacy 数据。
- 未插入真实业务数据。
- 未修改 ontology TTL（hash 不变）。

## 4. 下一步（Phase 2B，待人工指示）

- Atlas / ExternalRegion / RegionMapping / Evidence / Publication / ResearchStudy / Connection / Circuit 等。
