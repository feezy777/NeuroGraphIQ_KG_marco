# Gate 7B-B Phase 2A — Phase 2B Entry Criteria

## 冻结进入条件

| # | 条件 | 状态 |
|---|---|---|
| 1 | 9 张 core scientific entity 表创建 | ✅ |
| 2 | 13/32 table count（无 >13 或 <13） | ✅ |
| 3 | production/E2E schema parity | ✅ |
| 4 | shared-PK + entity_type consistency（集中守卫函数 + 9 触发器） | ✅ |
| 5 | 无第二 public ID / 无独立 serial PK | ✅ |
| 6 | brain_regions.granularity_level G1–G4 + 非法值拒绝 | ✅ |
| 7 | parent_region_pk / parent_function_pk 仅 DERIVED cache（未建 hierarchy 表） | ✅ |
| 8 | external IDs 由 entity_xrefs 管理（subtype 不复制） | ✅ |
| 9 | migration 幂等（repeat → skip） | ✅ |
| 10 | clean replay 001→002→003 = production | ✅ |
| 11 | 未迁 legacy / 无 Phase 2B+ 表 leak | ✅ |
| 12 | BLOCKER = 0 | ✅ |

## 结论

**Phase 2B Entry Readiness = READY**

（Phase 2B 候选：atlases / external_regions / region_mappings / evidence / publications / research_studies / connections / circuits 等，具体顺序待人工指示。）
