# Gate 6E-B — OWL Core Scope

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. OWL Core 保留的 Evidence 模块

| 类型 | 名称 | 说明 |
|---|---|---|
| Class | ResearchStudy | 研究活动 |
| Class | Publication | 文献/载体 |
| Class | Evidence | 具体证据单元 |
| ObjectProperty | reportedIn | ResearchStudy → Publication |
| ObjectProperty | providesEvidence | Publication → Evidence |

## 2. 不再增加其他 Evidence ObjectProperty

- 不新增 supports / contradicts / qualifies（DB evidence_role）。
- 不新增 hasSubject / hasObject / hasPredicate。
- 不新增 KnowledgeAssertion / Assertion Class。

## 3. OWL Core 职责

稳定 neuroscience / scientific semantics：BrainRegion、Connection、Circuit、Function、Gene、Disease、Neurotransmitter 等 + 其稳定关系。Evidence 只保留"证据单元"这个稳定科学概念与 Publication/Study 的稳定溯源关系。
