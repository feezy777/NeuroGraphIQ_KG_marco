# Gate 8B — Rerun & Risk

## 0. 状态

**Gate 8B = FROZEN / READY FOR GATE 8C**

## 1. Rerun / Idempotency

- 第二次 `--mode full --apply`：source/atlas/external/brain/mapping/alias/xref **全部 0**；brain_region_updated=0、mapping_updated=0。
- 第三次同（已多次验证）。

## 2. BLOCKER = 0

## 3. MAJOR = 0

## 4. MODERATE

| # | 项 | 说明 |
|---|---|---|
| M1 | 全量 246 canonical BrainRegion 仍为 **proposed 候选**（非 ACTIVE registry） | 按 Gate 8B §二十四：本轮回建立 Candidate Registry；promotion 决策留待 **Gate 8C**（全量质量验收 + 分层人工抽样 + 是否批量 promotion）。 |
| M2 | `_gate8a_baseline.json`（Pilot 身份快照）为 backend/ 下的审计工件 | 供 Pilot ID regression 测试使用；未 commit。 |
| M3 | source circos 无官方英文 subdivision 名 | naming 为 Gate 8A Priority 2 stable constructed（normalized），已冻结。 |

## 5. 未做（本轮明确不做）

- 未 ACTIVE 任何 BrainRegion；未做 Gate 8C promotion。
- 未导入其他 Atlas；未做 Circuit / Connection / AggregationMapping。
- 未迁 legacy；未写 Neo4j / frontend；未改 schema / migration / TTL。
