# Gate 7B-B Phase 5 — EvidenceLink

## 1. 正式表名 + public ID

- 正式表名：`evidence_links`（**未**创建 assertion_evidence_links）。
- `link_pk BIGSERIAL` + `link_id NGIQ-ELK`（`infra.ngiq_elk_seq`）。
- EvidenceLink **不是** kg_entities subtype（未强加 shared-PK）。

## 2. XOR（本轮最高优先级约束，DB CHECK 强制 fail closed）

```
evidence_pk NOT NULL
AND 恰好一个：
  assertion_pk（knowledge_assertions）
  或 entity_pk（kg_entities）
```

- `ck_elink_xor`：`(assertion_pk IS NOT NULL AND entity_pk IS NULL) OR (assertion_pk IS NULL AND entity_pk IS NOT NULL)`。
- 两个都 NULL → 拒绝；两个都非 NULL → 拒绝。

## 3. FK（真实 FK，不用 target_type+target_id）

- evidence_pk → evidence.entity_pk（NN）
- assertion_pk → knowledge_assertions.assertion_pk
- entity_pk → kg_entities.entity_pk

## 4. Entity evidence whitelist（trigger 强制）

`entity_pk` 非空时，`kg_entities.entity_type` 仅允许：

```
connection / circuit / region_mapping / circuit_connection_membership
```

- brain_region / function / gene / disease / symptom / publication / external_region / evidence 等 **禁止**直接作为 entity Evidence target（这些走 KnowledgeAssertion → EvidenceLink）。
- `infra.assert_evidence_link_entity_whitelist()` 读取 kg_entities.entity_type，非白名单 → RAISE（fail closed）。

## 5. claim_scope

- Entity target：claim_scope **必须非空**（`ck_elink_claim_scope`：entity_pk IS NULL OR claim_scope IS NOT NULL）。
- Assertion target：claim_scope 允许 NULL。
- vocab（16 §5，无 function）：entity_overall / existence / identity / direction / connection_type / topology / membership / mapping_identity / mapping_equivalence / mapping_overlap / other。
- Circuit hasFunction → KnowledgeAssertion（不走 claim_scope=function）。

## 6. evidence_role / strength / directness

- `evidence_role` CHECK：supports / contradicts / qualifies（无对应 OWL ObjectProperty）。
- `evidence_strength`（strong/moderate/weak/unknown）、`evidence_directness`（direct/indirect）**位于 evidence_links**（target-specific context）。
- **不**放回 evidence 表；**不**与 connection_observations.strength_reported 混淆。
- 测试 `test_elink_strength_directness_location`：evidence_links 有、evidence 无。

## 7. 无 evidence inheritance

- 禁止 fine-level Connection/Circuit Evidence 自动变成 coarse hierarchical_rollup 的 direct Evidence。
- 原 Evidence 只能作 premise/upstream context；除非新 target 自建 EvidenceLink。
- 本轮无 evidence inheritance trigger。

## 8. 测试覆盖

- evidence_pk 必填 / assertion-only 合法 / entity-only 合法 / 双目标拒绝 / 双 NULL 拒绝
- whitelist 4 类允许 / BrainRegion 拒绝 / entity claim_scope 必填 / assertion claim_scope NULL 允许
- evidence_role vocab / public ID（NGIQ-ELK）/ strength-directness 位置 / 无 assertion_evidence_links
