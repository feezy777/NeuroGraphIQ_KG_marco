# Gate 7B-B Phase 2B — Phase 3 Entry Criteria

## 冻结进入条件

| # | 条件 | 状态 |
|---|---|---|
| 1 | 5 张 Evidence/Atlas 表创建 | ✅ |
| 2 | 18/32 table count（无 >18 或 <18） | ✅ |
| 3 | production/E2E schema parity | ✅ |
| 4 | 5 张 shared-PK + entity_type consistency（复用集中守卫） | ✅ |
| 5 | ResearchStudy / Publication 分离 | ✅ |
| 6 | Evidence source completeness（ACTIVE = publication_pk OR scientific_source_pk；study_pk 单独不足） | ✅ |
| 7 | scientific_source_pk FK → sources；GPT/DeepSeek 非 scientific source | ✅ |
| 8 | evidence_strength/directness 未误放 Evidence | ✅ |
| 9 | Atlas ≠ granularity；ExternalRegion ≠ BrainRegion（无错误合并） | ✅ |
| 10 | clean replay 001→004 = production | ✅ |
| 11 | migration 幂等（repeat → skip） | ✅ |
| 12 | 未迁 legacy / 无 Phase 3+ 表 leak | ✅ |
| 13 | BLOCKER = 0 | ✅ |

## 结论

**Phase 3 Entry Readiness = READY**

（Phase 3 候选：connections / circuits / hierarchy relations / region_mappings / knowledge_assertions / evidence_links 等，具体顺序待人工指示。）
