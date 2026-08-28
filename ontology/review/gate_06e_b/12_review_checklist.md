# Gate 6E-B Human Review Checklist — Evidence / Assertion Ontology Boundary Freeze

请逐项确认。本 Gate **未扩展正式 OWL 本体**。

---

## 审查清单

- [ ] 未修改 TTL（version 仍 0.6.2-gate6d）
- [ ] Named Class = 23
- [ ] ObjectProperty = 26
- [ ] DataProperty = 0
- [ ] Named Individual = 0
- [ ] OWL Evidence Classes：ResearchStudy / Publication / Evidence（保持）
- [ ] OWL Evidence ObjectProperties：reportedIn / providesEvidence（保持）
- [ ] KnowledgeAssertion 不进入 OWL
- [ ] supports 不进入 OWL
- [ ] contradicts 不进入 OWL
- [ ] qualifies 不进入 OWL
- [ ] EvidenceLink 存储层 = PostgreSQL（evidence_links）
- [ ] entity whitelist：connection/circuit/region_mapping/circuit_connection_membership
- [ ] claim_scope 属 DB；entity target 必填
- [ ] strength/directness 属 DB（evidence_links，target-specific）
- [ ] ACTIVE Evidence 须 publication_pk OR scientific_source_pk
- [ ] LLM 非 scientific source
- [ ] reported/inferred 分离
- [ ] inference premise ≠ Evidence
- [ ] upstream evidence 不自动变 direct
- [ ] Gate 7A 表总数 32；current 表名 evidence_links
- [ ] 历史旧表名 assertion_evidence_links 已标 SUPERSEDED
- [ ] 未创建 migration / 未改数据库
- [ ] 未 commit / 未 push

---

## 关键决策点（需人工拍板）

1. **Evidence/Assertion 边界冻结：OWL 零扩展，复杂 assertion/evidence 语义归 PostgreSQL**——是否同意？
2. **KnowledgeAssertion / supports / contradicts / qualifies 均不进 OWL**——是否同意？
3. **entity whitelist 仅 connection/circuit/region_mapping/circuit_connection_membership**——是否同意？

---

## 审查说明

- 若某项不通过，请在对应行标注，并在 `ontology/review/gate_06e_b/` 下追加意见。
- 全部通过后，回复 **「Gate 6E-B 通过」**，方可进入后续（Spatial Relations / Gate 7B migration）。
