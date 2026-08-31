# Gate 7B-B Phase 2B — Risk Register

## 1. BLOCKER = 0

## 2. 已裁决的设计决策（指令 §十八：按科学语义明确侧实现 + 记录）

| 决策点 | 裁决 | 依据 |
|---|---|---|
| evidence 是否含 evidence_strength/directness | **不含**（属 EvidenceLink target-specific） | 指令 §八 + 冻结 §I + 11 §3「strength/directness 已移到 evidence_links」 |
| evidence.scientific_source_pk | 加入（FK→sources）；ACTIVE 完整性 = publication_pk OR scientific_source_pk | 指令 §五/§六 + 冻结 §P + 11 §3 |
| publications.pmid/pmcid/doi/pii | 保留为 publication 专属检索字段（可 NULL） | 指令 §四例外（CURRENT dict 明确） |
| external_regions.granularity_level/basis | 加入（atlas context，非 canonical truth） | 指令 §十二 + 24_granularity_policy §6 |
| methodological_quality | 加入 evidence（非 target-specific strength/directness） | 11 §3 明确列出 |
| evidence 表记录状态来源 | 从 kg_entities.record_status 读取（trigger 子查询，因 CHECK 无法跨表） | 共享 identity 原则 §三 |

## 3. MODERATE

- evidence 源完整性用触发器而非 DB CHECK 实现（PostgreSQL CHECK 不能引用 kg_entities.record_status）——已在 migration 中以集中函数 + 注释说明。
- dict 18 §23 仍列 `evidence_directness`（历史残留，与冻结 §I 冲突）：本轮**未在 evidence 表实现**，建议后续 Gate 7A 文档同步删除该行（报告而非扩大任务）。

## 4. 无 MAJOR

## 5. 边界（本轮未做）

- 未建 evidence_links / knowledge_assertions / relation_definitions。
- 未建 hierarchy / spatial / aggregation / connection / circuit / region_mappings。
- 未迁 legacy / PubMed / evidence_items / Atlas / Brainnetome / Julich / Allen 数据。
- 未生成测试外真实数据（仅 E2E rollback 测试）。
