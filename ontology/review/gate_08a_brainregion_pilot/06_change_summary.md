# Gate 8A — Change Summary

本轮状态：**Brainnetome BNA246 20-parcel 真实入库 Pilot 完成（production），未 commit/push，未改 schema/legacy**

## 1. 产出

| 类型 | 文件 |
|---|---|
| 新建 | `backend/scripts/import_brainnetome_pilot.py`（--plan / --apply，rerun-safe，密码脱敏） |
| 新建 | `ontology/review/gate_08a_brainregion_pilot/`（6 文件） |

## 2. 数据库实际变更（production，非 schema）

- 新增 Scientific Source ×1、Atlas ×1、ExternalRegion ×20、proposed canonical BrainRegion ×20、RegionMapping ×20、Alias ×20、Xref ×20。
- aggregation mappings 新增 **0**。
- E2E 库未动（测试隔离）。

## 3. 明确未做

- 未全量导入 246 / 未做 Circuit / Connection。
- 未改 32-table schema / gate7b_001–008 / ontology TTL。
- 未迁 legacy；未写 Neo4j / frontend。
- 未 commit / 未 push。

## 4. 下一步（待人工数据审查 + 指示）

- 审查 20 个 proposed canonical BrainRegion 身份 / 双语名 / mapping_type。
- 通过后考虑全量 246 导入（需区分 mapping_type）或其他 Atlas 数据源。
