# Gate 6E-A.1 — Evidence Database Alignment Amendment

本轮状态: **仅数据字典 minimal amendment，不修改 TTL / 数据库 / migration**

---

## 1. Why amendment is needed

Gate 6E-A 通过 Hybrid Evidence Model：普通 Assertion 走 knowledge_assertions，reified scientific entity（Connection/Circuit/RegionMapping）直接挂 Evidence。但当前 `assertion_evidence_links` 只能自然关联 KnowledgeAssertion，无法直接关联 reified entity；且 Evidence provenance 偏 Publication，无法表达外部数据库/atlas 来源。

## 2. assertion_evidence_links limitation

- 只有一个 `assertion_id` target，无法指向 Connection/Circuit/RegionMapping。
- 没有统一 evidence role 层承载 entity-level Evidence。

## 3. evidence_links unified model

`assertion_evidence_links` 改名 `evidence_links`（总表数保持 32，不新增第 33 表）。统一表达 Evidence 对 Assertion 或 reified entity 的 epistemic 作用。

## 4. XOR target

每条 link 必须且只能有一个 target：
- `assertion_pk IS NOT NULL` + `entity_pk IS NULL`（普通 assertion）
- `assertion_pk IS NULL` + `entity_pk IS NOT NULL`（reified entity）
- 非法：两者都 NULL / 两者都 NOT NULL。

未来 Gate 7B 用 CHECK constraint 表达 XOR；本轮只写设计。

## 5. assertion target

`evidence_links.assertion_pk → knowledge_assertions`（普通 ObjectProperty assertion）。

## 6. entity target

`evidence_links.entity_pk → kg_entities.entity_pk`（统一 identity truth），而非分别引用 connections/circuits/region_mappings。

## 7. allowed reified entities（V1）

Connection、Circuit、RegionMapping（及后续明确允许的 evidence-backed canonical entity）。普通 BrainRegion participatesIn Function 仍走 knowledge_assertions，不把 Evidence 直接挂 BrainRegion。

## 8. claim_scope

限定 Evidence 针对 reified entity 的哪部分 claim。V1 词表：entity_overall / existence / identity / direction / connection_type / topology / membership / function / mapping_identity / mapping_equivalence / mapping_overlap / other。claim_scope 不是 ontology property，是 DB evidence-link contextual field；assertion target 一般允许 NULL。

## 9. evidence_role

supports（明确支持）/ contradicts（明确冲突）/ qualifies（限定条件范围）。

## 10. evidence_strength / directness

canonical storage = evidence_links（target-specific context；同一 Evidence 对不同 target 可不同）。evidence 表不再保留同义 strength/directness truth（可保留 methodological_quality 等不同语义字段）。

## 11. Publication provenance

`evidence.publication_pk`（Publication providesEvidence Evidence）。study_pk 可选；scientific_source_pk 可 NULL 或指向 registry。

## 12. database / atlas provenance

`evidence.scientific_source_pk → sources`（HGNC/MONDO/Julich-Brain/IUPHAR 等）。publication_pk/study_pk NULL。source_record_id / source_record_uri 复用现有 source-location 字段或 provenance_json，不新增表。

## 13. scientific_source_pk

Evidence 表增加 `scientific_source_pk`（非 Publication 科学来源）。publication_pk / study_pk / scientific_source_pk 均 nullable；一个 Evidence unit 可同时有 source registry context + publication carrier（不冲突）。

## 14. Connection evidence

Evidence → evidence_links.entity_pk → Connection（不创建 existence Assertion wrapper）。claim_scope：entity_overall / direction / connection_type。connection_observations 仍负责 study-level 定量观测，不替代 evidence_link。

## 15. Circuit evidence

Evidence → evidence_links.entity_pk → Circuit（entity_overall / topology / membership）。CircuitConnectionMembership 若为 first-class entity 可挂 membership claim；Circuit hasFunction 走 knowledge_assertions（普通 assertion）。

## 16. RegionMapping evidence

Evidence → evidence_links.entity_pk → RegionMapping（mapping_identity / mapping_equivalence / mapping_overlap）。

## 17. inferred knowledge

inferred reified entity（如 G1 roll-up）依据 derivation lineage（source Connection + mappings + InferenceRecord），不是 direct Evidence。不自动把 G4 Evidence 复制成 G1 direct supports。

## 18. no direct evidence inheritance

粗粒度 roll-up 展示 "upstream evidence / supporting_source_count"，但不得写成 direct supports coarse claim。

## 19. 32-table preservation

只重命名 `assertion_evidence_links → evidence_links`，不新增 entity_evidence_links / evidence_target_links / 第 33 表。

## 20. Gate 6E-B consequence

Evidence/Assertion semantic model 已由 PostgreSQL hybrid layer 完整承担。Gate 6E-B：
- 推荐新增 OWL Class = 0
- 推荐新增 OWL ObjectProperty = 0

本体不需为 Evidence Association 新增 KnowledgeAssertion / supports / contradicts / qualifies / hasSubject / hasPredicate / hasObject。Gate 6E-B 建议改为 **Evidence / Assertion Ontology Boundary Freeze**（只冻结哪些语义属 OWL core，哪些属 DB assertion/evidence layer）。
