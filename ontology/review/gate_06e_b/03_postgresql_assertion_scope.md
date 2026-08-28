# Gate 6E-B — PostgreSQL Assertion Scope

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. PostgreSQL Layer 负责

- knowledge_assertions（subject/predicate/object + derivation_type + qualifiers）
- relation_definitions（谓词 vocabulary）
- evidence_links（evidence_pk + XOR target + evidence_role + strength/directness + claim_scope）
- connection_observations（study-level 观测）
- InferenceRecord / derivation lineage（后续 Governance/Reasoning schema）

以及语义：
- supports / contradicts / qualifies（evidence_role）
- claim_scope
- evidence_strength / evidence_directness
- model_confidence
- qualifiers / condition
- source resolution / review status / human/model review history / promotion / rollback / validation

## 2. KnowledgeAssertion 不进入 OWL

- 不新增 KnowledgeAssertion / Assertion / RelationAssertion / EntityAssertion OWL Class。
- 普通 relation evidence 由 PostgreSQL knowledge_assertions + evidence_links 完整承担。

## 3. 普通 relation assertion 路径

```
Hippocampus participatesIn Memory
  → knowledge_assertions（subject=Hippocampus, predicate=participatesIn, object=Memory）
  → evidence_links.assertion_pk
  → Evidence
```

- 不写 `Evidence → Hippocampus` 或 `Evidence → Memory`（Evidence 支持的是"海马参与记忆"这条 assertion）。
