# Gate 6E-B — Reified Entity Evidence

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. Reified scientific entity 直接挂 Evidence

Connection / Circuit / RegionMapping / CircuitConnectionMembership 是 first-class reified knowledge object，不额外创建 "X exists" Assertion，Evidence 直接通过 `evidence_links.entity_pk` 关联。

## 2. Connection Evidence

- entity-level target；claim_scope：entity_overall / existence / direction / connection_type。
- 只有真实外部 Evidence 直接支持该 claim 才建 EvidenceLink。

## 3. Circuit Evidence

- entity-level target；claim_scope：entity_overall / existence / topology。
- Circuit hasFunction Function 仍走 knowledge_assertions（不走 entity claim_scope=function）。

## 4. CircuitConnectionMembership Evidence

- entity-level target；claim_scope=membership（支持某 Connection 确实属于某 Circuit）。

## 5. RegionMapping Evidence

- entity-level target；claim_scope：entity_overall / mapping_identity / mapping_equivalence / mapping_overlap。
- 不与 brain_region_aggregation_mappings 的 inference provenance 混淆。

## 6. ConnectionObservation ≠ EvidenceLink

- connection_observations 负责 study-level 定量观测（sample_size/metric/p/CI…），可关联 Connection + Evidence，但不替代 evidence_link epistemic role。
