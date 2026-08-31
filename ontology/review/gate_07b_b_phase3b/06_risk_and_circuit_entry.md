# Gate 7B-B Phase 3B — Risk Register & Circuit Phase Entry

## 1. BLOCKER = 0

## 2. MAJOR = 0

## 3. MODERATE

| # | 项 | 说明 |
|---|---|---|
| M1 | `NGIQ-EP` 前缀不在冻结 30-prefix registry | dict 18 §8 定义 endpoint_id = NGIQ-EP-… NN UNIQUE。本轮新增 `infra.ngiq_ep_seq`（seqs 31）+ registry amendment（30→31，`connection_endpoint` → `NGIQ-EP`）。与 SPAT 同款 Case B。 |
| M2 | dict 18 §9 `observation_id = NGIQ-OBS` 与冻结 registry `connection_observation = NGIQ-COB` 冲突 | 以 registry 为准（COB，sequence 已有）。observation_id 默认 `NGIQ-COB-…`。建议后续 dict §9 修正为 COB（文档漂移，非语义冲突）。 |
| M3 | dict 18 §7 `directionality` 列表含 `reciprocal` | 27 audit §H 已冻结 V1 directionality = directed/non_directional/direction_unknown（reciprocal = DERIVED display）。CHECK 用 3 值；reciprocal 用两条 directed Connection 表达。 |
| M4 | Projection "恰好一个 source + 一个 target" 未做 DB 跨行计数 | 按 §十五允许应用层 validation；DB 只防 duplicate + self-endpoint。 |

## 4. 无核心语义冲突（未触发停止报告）

- directionality / Projection 定义 / endpoint canonical truth / FC direction / Observation vs Evidence / canonical vs derived：均按冻结语义实现，无不可消解冲突。

## 5. Circuit Phase Entry Criteria

| # | 条件 | 状态 |
|---|---|---|
| 1 | 3 张 Connection 表创建 | ✅ |
| 2 | 25/32 table count（无 >25 或 <25） | ✅ |
| 3 | production/E2E parity | ✅ |
| 4 | connections shared-PK + entity_type consistency | ✅ |
| 5 | 四类 connection_class 受控 | ✅ |
| 6 | connection_endpoints = canonical endpoint truth（connections 无重复 FK） | ✅ |
| 7 | endpoint_role 词表 + duplicate/self-endpoint 拒绝 | ✅ |
| 8 | FC 保持 non-directional；EC ≠ Projection；directed Structural 不自动变 Projection | ✅ |
| 9 | Observation ≠ Evidence（无 evidence_strength/directness） | ✅ |
| 10 | 无 direct-edge canonical duplication | ✅ |
| 11 | clean replay 001→006 = production | ✅ |
| 12 | migration 幂等（repeat → skip） | ✅ |
| 13 | 未迁 legacy / 无 Circuit+ 表 leak | ✅ |
| 14 | BLOCKER = 0 | ✅ |

**Circuit Phase Entry Readiness = READY**

（Circuit 候选：circuits / circuit_region_memberships / circuit_connection_memberships 等，具体顺序待人工指示。）
