# Gate 6E-B — Evidence Link Boundary

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. evidence_links（正式表，原 assertion_evidence_links）

字段：link_pk / link_id（NGIQ-ELK）/ evidence_pk（NN）/ assertion_pk（NULL）/ entity_pk（NULL）/ evidence_role / evidence_strength / evidence_directness / claim_scope / is_primary_evidence / record_status / created_at / updated_at / remark。

## 2. XOR target

- `assertion_pk XOR entity_pk`（必须且只能填一个）。
- 未来 Gate 7B 用 DB CHECK constraint 表达。

## 3. entity whitelist（V1）

entity_pk 仅允许 entity_type ∈ {connection, circuit, region_mapping, circuit_connection_membership}。

## 4. claim_scope

- assertion target → claim_scope 可 NULL（Assertion 自身已完整）。
- entity target → claim_scope 必填。
- vocab：entity_overall / existence / identity / direction / connection_type / topology / membership / mapping_identity / mapping_equivalence / mapping_overlap / other（function 已移除）。

## 5. strength / directness

canonical storage = evidence_links（target-specific）；不是 Evidence entity 自身属性。

## 6. ACTIVE Evidence source completeness

record_status=ACTIVE → publication_pk OR scientific_source_pk 必填（study_pk 单独不足；LLM 非 source）。
