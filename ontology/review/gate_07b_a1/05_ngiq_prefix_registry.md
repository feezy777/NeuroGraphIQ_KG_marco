# Gate 7B-A.1 — NGIQ Prefix Registry

---

| entity_type | public prefix | example | first_class_or_link | notes |
|---|---|---|---|---|
| brain_region | NGIQ-BR | NGIQ-BR-00000001 | first-class | — |
| cellular_neural_structure | NGIQ-CNS | NGIQ-CNS-00000001 | first-class | — |
| neurobiological_process | NGIQ-NBP | NGIQ-NBP-00000001 | first-class | — |
| connection | NGIQ-CON | NGIQ-CON-00000001 | first-class | reified |
| connection_observation | NGIQ-COB | NGIQ-COB-00000001 | link/obs | — |
| circuit | NGIQ-CIR | NGIQ-CIR-00000001 | first-class | reified |
| function | NGIQ-FUN | NGIQ-FUN-00000001 | first-class | — |
| neurotransmitter | NGIQ-NT | NGIQ-NT-00000001 | first-class | — |
| receptor | NGIQ-RCP | NGIQ-RCP-00000001 | first-class | — |
| gene | NGIQ-GEN | NGIQ-GEN-00000001 | first-class | — |
| disease | NGIQ-DIS | NGIQ-DIS-00000001 | first-class | — |
| symptom | NGIQ-SYM | NGIQ-SYM-00000001 | first-class | — |
| research_study | NGIQ-STU | NGIQ-STU-00000001 | first-class | — |
| publication | NGIQ-PUB | NGIQ-PUB-00000001 | first-class | — |
| evidence | NGIQ-EVI | NGIQ-EVI-00000001 | first-class | — |
| atlas | NGIQ-ATL | NGIQ-ATL-00000001 | first-class | — |
| external_region | NGIQ-XREG | NGIQ-XREG-00000001 | first-class | — |
| region_mapping | NGIQ-RMAP | NGIQ-RMAP-00000001 | first-class | reified |
| circuit_connection_membership | NGIQ-CCM | NGIQ-CCM-00000001 | first-class | reified, evidence-targetable |
| circuit_region_membership | NGIQ-CRM | NGIQ-CRM-00000001 | first-class | reified |
| brain_region_hierarchy_relation | NGIQ-BRH | NGIQ-BRH-00000001 | link | — |
| function_hierarchy_relation | NGIQ-FHR | NGIQ-FHR-00000001 | link | — |
| brain_region_aggregation_mapping | NGIQ-BRAM | NGIQ-BRAM-00000001 | first-class | reified |
| knowledge_assertion | NGIQ-AST | NGIQ-AST-00000001 | first-class | — |
| relation_definition | NGIQ-PRED | NGIQ-PRED-00000001 | first-class | — |
| evidence_link | NGIQ-ELK | NGIQ-ELK-00000001 | link | evidence-targetable |
| source | NGIQ-SRC | NGIQ-SRC-00000001 | first-class | — |
| alias | NGIQ-ALS | NGIQ-ALS-00000001 | link | — |
| xref | NGIQ-XRF | NGIQ-XRF-00000001 | link | — |
| brain_region_spatial_representation | NGIQ-SPAT | NGIQ-SPAT-00000001 | link | 非 kg_entities subtype（dict 18 §6 明确要求 stable public ID） |

## 结论

- **prefix 项数：30**，无重复/collision。
- kg_entities 不单独发号（见 12 的 shared-PK 规则）；纯 join link（endpoints 等）可选 public ID，不强制造。
- **Amendment（Gate 7B-B Phase 3A closeout）**：新增 `brain_region_spatial_representation` → `NGIQ-SPAT`（29 → 30）。依据：CURRENT dict 18 §6 定义 `spatial_id ... NGIQ-SPAT-…` NN UNIQUE。spatial_representation 为 link 记录，**不**进入 kg_entities subtype。
