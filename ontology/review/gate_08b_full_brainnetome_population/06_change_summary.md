# Gate 8B — Change Summary

本轮状态：**Brainnetome BNA246 全量 246 数据生产完成（production）并冻结；状态 = FROZEN / READY FOR GATE 8C；未改 schema/legacy**

## 1. 产出

| 类型 | 文件 |
|---|---|
| 修改 | `backend/scripts/import_brainnetome_pilot.py`（--mode pilot/full 共用核心；_BNA_ANATOMICAL_NAMES 补全 25 项；_validate_source fail-closed；Plan 增强） |
| 新建 | `backend/tests/test_gate8b_full_population.py`（17 用例） |
| 新建 | `ontology/review/gate_08b_full_brainnetome_population/`（6 文件） |
| 审计工件 | `backend/_gate8a_baseline.json`（Pilot 身份快照，供 regression；未 commit） |

## 2. 数据库实际变更（production，非 schema）

- 新增 ExternalRegion ×226、proposed BrainRegion ×226、RegionMapping ×226、Alias ×226、Xref ×226 → 各 246 总数。
- 复用 source（NGIQ-SRC-00000001）/ atlas（NGIQ-ATL-00000001）/ 既有 20 Pilot。
- aggregation mappings 保持 0。

## 3. 明确未做

- 已 commit / push（Gate 8B FROZEN / READY FOR GATE 8C）。
- 未 ACTIVE / 未做 Gate 8C promotion。
- 未改 schema / gate7b_001–008 / TTL / legacy。
- 未做 Circuit / Connection / 其他 Atlas。

## 4. 下一步（Gate 8C，待人工验收 + 指示）

- 全量质量验收 + 分层人工抽样 + 是否批量 promotion 决策。
