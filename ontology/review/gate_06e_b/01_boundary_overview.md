# Gate 6E-B — Evidence / Assertion Ontology Boundary Overview

Ontology IRI: `https://neurographiq.org/ontology/human-brain`（version 0.6.2-gate6d，本轮不改）
本轮状态: **Boundary Freeze，不新增任何 ontology entity**

---

## 1. 核心结论

复杂的 Evidence / Assertion 管理 **不进入 OWL Core**。

- OWL Core：稳定 neuroscience / scientific semantics。
- PostgreSQL：具体 knowledge assertion、evidence association、qualifier、strength/directness、inference provenance、review/governance。

## 2. 本轮 OWL expansion

- 新增 Class = 0
- 新增 ObjectProperty = 0
- 新增 DataProperty = 0
- 新增 Individual = 0

## 3. 为什么

- ordinary relation evidence 已由 PostgreSQL `knowledge_assertions` + `evidence_links` 完整承担。
- 避免 OWL meta-modeling / predicate reification / ObjectProperty-as-individual / 额外 wrapper / truth duplication。

## 4. 冻结基线

- version 0.6.2-gate6d、23 Class、26 ObjectProperty、0 DataProperty、0 Individual、0 imports。
- 正式 Evidence OWL 内容：ResearchStudy / Publication / Evidence + reportedIn / providesEvidence（保持不变）。
