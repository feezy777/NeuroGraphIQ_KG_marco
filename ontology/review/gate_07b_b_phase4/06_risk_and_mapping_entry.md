# Gate 7B-B Phase 4 — Risk Register & Next-Phase Entry

## 1. BLOCKER = 0

## 2. MAJOR = 0

## 3. MODERATE

| # | 项 | 说明 |
|---|---|---|
| M1 | dict 18 §12 `membership_pk BIGSERIAL` vs 冻结首类模型 | circuit_connection_memberships 按 shared-PK 实现（entity_type 词表 + registry first-class/evidence-targetable 占优）。dict §12 表达视为历史漂移，建议后续文档同步。非停止条件（CURRENT 首类信号明确）。 |
| M2 | circuit_region_memberships UNIQUE(circuit,region) 限制"同 region 多角色" | 按 §十一"至少防完全相同重复"实现；若未来需要 region 多角色 membership，需放宽（CURRENT 未定义该情况）。 |
| M3 | circuits.granularity_scope | 24 §7 定义为 DERIVED；18 §10 未列。本轮按 connections 同款加入（可空，CHECK G1–G4/MIXED/UNSPECIFIED）。 |

## 4. 无核心语义冲突（未触发停止报告）

- Circuit 科学定义 / closed_loop / cardinality / derivation / hasConnection Derived / 不自动生成：均按冻结语义实现。

## 5. Next-Phase Entry Criteria（RegionMapping/Assertion）

| # | 条件 | 状态 |
|---|---|---|
| 1 | 3 张 Circuit 表创建 | ✅ |
| 2 | 28/32 table count（无 >28 或 <28） | ✅ |
| 3 | production/E2E parity | ✅ |
| 4 | circuits shared-PK + entity_type consistency | ✅ |
| 5 | 无 closed_loop 硬要求 / 无 ≥3+≥2 硬约束 | ✅ |
| 6 | PROPOSED incomplete Circuit 可保存 | ✅ |
| 7 | circuit_region_memberships FK + duplicate 拒绝 | ✅ |
| 8 | circuit_connection_memberships first-class/shared-PK + FK + 无 Connection truth 复制 | ✅ |
| 9 | hasConnection 保持 Derived（无第二 truth 表） | ✅ |
| 10 | graph cycle 不自动生成 Circuit / 不自动补 Connection | ✅ |
| 11 | clean replay 001→007 = production | ✅ |
| 12 | migration 幂等（repeat → skip） | ✅ |
| 13 | 未迁 legacy / 无 RegionMapping+Assertion 表 leak | ✅ |
| 14 | BLOCKER = 0 | ✅ |

**Next Phase（RegionMapping/Assertion）Entry Readiness = READY**

（候选：region_mappings / relation_definitions / knowledge_assertions / evidence_links 等，具体顺序待人工指示。）
