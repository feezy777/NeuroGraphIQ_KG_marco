# Gate 7B-B Phase 5 — Relation Definitions & Knowledge Assertions

## 1. relation_definitions（PostgreSQL predicate registry）

- 描述普通知识关系：participatesIn / modulates / increasesRiskOf / hasSymptom / actsOn / hasFunction 等。
- `predicate_pk BIGSERIAL` + `predicate_id NGIQ-PRED`（`infra.ngiq_pred_seq`）+ `predicate_key UNIQUE`。
- `representation_role`：canonical / derived。
- **不是** ConnectionType / CircuitType / EvidenceType；**不是**新 OWL taxonomy。
- 新增 relation_definition **不**自动修改 ontology TTL。

## 2. knowledge_assertions（DB-only）

- 普通 relation claim：BrainRegion participatesIn Function、Gene increasesRiskOf Disease、Disease hasSymptom Symptom、Neurotransmitter actsOn Receptor、Circuit hasFunction Function。
- **只属于 PostgreSQL，不进入 OWL Core**。
- `assertion_pk BIGSERIAL` + `assertion_id NGIQ-AST`（`infra.ngiq_ast_seq`）。
- subject / object → kg_entities.entity_pk；predicate → relation_definitions.predicate_pk。

## 3. reported / inferred 分离

- `derivation_type` CHECK：reported / inferred。
- reported = 外部科学 source 明确报告；inferred = 系统规则/知识推导。
- **人工审核通过不能把 inferred 改成 reported**——审核影响 lifecycle，不改变 derivation origin。

## 4. 不重复 reified canonical truth（§七）

Connection / Circuit / RegionMapping / CircuitConnectionMembership 已有 canonical reified model：

- Connection A→B：canonical truth = connections + connection_endpoints。
- 不额外维护独立 canonical `A projectsTo B` KnowledgeAssertion。

Derived query/projection 后续可生成，但不能双写 canonical truth。
测试 `test_assertion_no_connection_truth_duplication`：knowledge_assertions 无 connection_class / directionality / source/target_region_pk。

## 5. 测试覆盖

- `test_relation_definition_fk`（predicate FK）
- `test_assertion_reported_inferred_vocab`（reported/inferred 合法；非法值拒绝）
