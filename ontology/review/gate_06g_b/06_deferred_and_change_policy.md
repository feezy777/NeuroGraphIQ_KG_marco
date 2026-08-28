# Gate 6G-B — Deferred Vocabulary & Change Policy

---

## 1. Deferred Vocabulary（DEFER / future，非 V1 blocker）

- Function part_of
- RDF-star
- RDF reification
- qualifier ontology
- condition ontology
- Source→Evidence OWL relation
- PROV-O alignment
- ECO alignment
- Evidence modality subclasses
- SpatialRepresentation OWL Class
- spatiallyOverlaps
- adjacentTo
- locatedIn
- brain_region_spatial_relations（DB 表）
- ontology TTL 文件名重命名（macro96 → human-brain）
- 复杂 OWL reasoning axioms（TransitiveProperty / SymmetricProperty / inverseOf / propertyChainAxiom）

## 2. Ontology Change Policy

FROZEN ≠ 永远不可修改。后续 Core ontology 修改必须通过**版本化变更**，且至少记录：

- scientific reason（科学理由）
- backward compatibility（向后兼容）
- database impact（数据库影响）
- migration impact（迁移影响）
- Neo4j impact（图投影影响）
- human approval（人工批准）

禁止直接偷偷修改 TTL；每次变更须走版本化 Gate 流程并升级 versionInfo。
