# Gate 6E-B — OWL ↔ PostgreSQL Mapping Matrix

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

| Concept | OWL Core | PostgreSQL | Note |
|---|---|---|---|
| ResearchStudy | YES | YES | scientific entity |
| Publication | YES | YES | document carrier |
| Evidence | YES | YES | evidence unit |
| reportedIn | YES | projection | ResearchStudy→Publication |
| providesEvidence | YES | projection | Publication→Evidence |
| KnowledgeAssertion | NO | YES | assertion management |
| supports | NO | evidence_role | DB context |
| contradicts | NO | evidence_role | DB context |
| qualifies | NO | evidence_role | DB context |
| claim_scope | NO | YES | entity claim context |
| evidence_strength | NO | YES | target-specific |
| evidence_directness | NO | YES | target-specific |
| model_confidence | NO | YES | provenance |
| qualifier | NO | YES | deferred rich modeling |
| InferenceRecord | NO | YES/Future Governance | derivation |
| HumanReview | NO | Governance | workflow |
| ModelReview | NO | Governance | workflow |
