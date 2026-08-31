# Gate 7B-B Phase 1 — Change Summary

本轮状态：**已建 4/32 Identity Foundation 科学表 + public ID 发号器，未 commit/push，未迁 legacy，未建 Phase 2 表**

## 1. 产出

| 类型 | 文件 |
|---|---|
| 新建 | `backend/migrations/gate7b_002_identity_foundation.sql` |
| 新建 | `backend/tests/test_gate7b_phase1_identity.py`（22 用例） |
| 修改 | `backend/scripts/gate7b_migrate.py`（checksum 换行归一化） |
| 修改 | `backend/tests/test_gate7b_phase0.py`（sha256 归一化断言） |
| 新建 | `ontology/review/gate_07b_b_phase1/`（20 文件） |

## 2. 数据库实际变更

- production + E2E 各应用 `gate7b_002`。
- 新增 4 张表 + `infra.next_ngiq_id` 函数。

## 3. 明确未做

- 未 commit / 未 push（等待人工验收）。
- 未建第 5 张科学表 / 未建 subtype 表。
- 未从 legacy backfill。
- 未插入真实科学数据。
- 未修改本体 TTL（hash 不变）。

## 4. 下一步（Phase 2，待本轮验收后）

- BrainRegion / Function / Connection / Circuit 等 subtype 表（shared-PK 落地）。
- legacy coarse_* 数据 salvage（单独 Gate）。
