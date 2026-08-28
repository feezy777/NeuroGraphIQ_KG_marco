# Gate 6G-A — Evidence Boundary Audit

---

## 结果：PASS（0 issue）

- OWL Core 仅：ResearchStudy / Publication / Evidence + reportedIn / providesEvidence。
- 无 KnowledgeAssertion / Assertion / supports / contradicts / qualifies / hasSubject / hasPredicate / hasObject 进入 OWL。
- supports/contradicts/qualifies 属 DB evidence_role（evidence_links）。
- Publication ≠ Evidence；LLM ≠ scientific source。
