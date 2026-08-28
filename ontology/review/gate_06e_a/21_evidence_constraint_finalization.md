# Gate 6E-A.2 — Evidence Constraint Finalization

本轮状态: **仅约束冻结文档，不修改 TTL / 数据库 / migration**

---

## 1. EvidenceLink target model

`evidence_links` 统一表达 Evidence 对 KnowledgeAssertion 或 reified scientific entity 的 epistemic 作用。

## 2. XOR constraint

`assertion_pk XOR entity_pk`：每条 link 必须且只能指向一个 target。

## 3. Entity whitelist（V1 冻结）

仅允许以下 entity_type 直接作为 entity-level Evidence target：

- connection
- circuit
- region_mapping
- circuit_connection_membership

## 4. Why ordinary entities are excluded

BrainRegion / Function / Gene / Disease / Symptom / Neurotransmitter / Receptor 不得因存在于 kg_entities 就直接挂普通关系证据。它们的事实应走 knowledge_assertions。

## 5. claim_scope required rule

- `assertion_pk IS NOT NULL` → claim_scope 可 NULL（Assertion 自身已是明确 claim）。
- `entity_pk IS NOT NULL` → claim_scope 必须 NOT NULL（须说明支持该 entity 的哪部分 claim）。

## 6. claim_scope vocabulary（V1，function 已移除）

entity_overall / existence / identity / direction / connection_type / topology / membership / mapping_identity / mapping_equivalence / mapping_overlap / other。

- `function`：**已移除 / DEPRECATED**（Circuit hasFunction Function 走 knowledge_assertions，不用 entity-level claim_scope=function）。

## 7. entity_overall semantic

Evidence 支持该 reified scientific object 作为完整 scientific claim（如 tracer study 直接报告 A→B projection）。若只支持 direction 则用 direction，不全部标 entity_overall。

## 8. existence semantic

支持该科学对象代表的现象/知识存在；**不是**"数据库里存在这行记录"（record existence ≠ scientific existence claim）。

## 9. ACTIVE Evidence source rule

`record_status = ACTIVE` 必须满足：`publication_pk IS NOT NULL` OR `scientific_source_pk IS NOT NULL`。

## 10. PROPOSED Evidence rule

PROPOSED 允许 publication_pk / scientific_source_pk 均 NULL，但须保留 extraction provenance 并进入 source resolution / evidence review；不得 promotion 为 ACTIVE。

## 11. Publication evidence

publication_pk = P1，scientific_source_pk = NULL → 合法。

## 12. Database evidence

publication_pk = NULL，scientific_source_pk = HGNC → 合法。

## 13. Atlas evidence

publication_pk = P3，scientific_source_pk = Julich-Brain → 合法（可同时存在）。

## 14. Naked LLM evidence rejection

publication_pk = NULL，scientific_source_pk = NULL，extracted_by = GPT，ACTIVE → **非法**（GPT/DeepSeek 是 Provenance Agent，非 Scientific Source）。

## 15. reported evidence requirement

reported Assertion/Connection/Circuit 晋升 active/canonical 须有 direct scientific Evidence 或已审核 authoritative source provenance；Human review 不把 inferred 改成 reported。

## 16. inferred derivation rule

inferred 主要依据 InferenceRecord / premise lineage / source entities / aggregation mappings / inference rule，不要求 direct EvidenceLink。

## 17. upstream evidence rule

fine Evidence 不自动 EvidenceLink → coarse inferred entity 作为 direct supports；前端展示 inherited/upstream evidence，标 premise evidence。

## 18. Gate 7A alignment

总表数保持 32；只补三项约束，不新增表/字段。

## 19. Future Gate 7B validation recommendations

- entity_pk NOT NULL → 校验 kg_entities.entity_type ∈ whitelist。
- entity_pk NOT NULL → claim_scope NOT NULL。
- ACTIVE Evidence → publication_pk OR scientific_source_pk 必填。
（本轮只写设计，不建 trigger/migration。）

## 20. Freeze decision candidate

- Evidence/Assertion 数据模型冻结：evidence_links（XOR target + whitelist + claim_scope + source completeness）。
- Gate 6E-B = Evidence / Assertion Ontology Boundary Freeze（新增 OWL Class=0 / ObjectProperty=0 / DataProperty=0）。
