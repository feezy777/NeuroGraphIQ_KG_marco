# Gate 6E-B — Freeze Decision

Ontology IRI: `https://neurographiq.org/ontology/human-brain`（version 0.6.2-gate6d）

---

## Gate 6E Evidence / Assertion V1

### OWL expansion：NONE

Reason：PostgreSQL Hybrid Model 已经完整承担 assertion/evidence context。

### 正式冻结

**OWL Core（保留）**
- ResearchStudy / Publication / Evidence（Class）
- reportedIn（ResearchStudy → Publication）
- providesEvidence（Publication → Evidence）

**PostgreSQL Layer**
- KnowledgeAssertion（knowledge_assertions）
- EvidenceLink（evidence_links，XOR target + whitelist + claim_scope + strength/directness）
- EvidenceRole（supports / contradicts / qualifies）
- Inference lineage（InferenceRecord / premise）
- Governance（review / promotion / rollback / validation）

## 结论

Gate 6E-B 完成 Evidence / Assertion Ontology Boundary Freeze；正式 OWL 本体未扩展，version 保持 0.6.2-gate6d。
