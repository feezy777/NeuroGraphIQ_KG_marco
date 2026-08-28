# Gate 7A — ID Strategy（ID 策略）· Final Correction

本轮状态: **仅设计文档**

---

## 1. 主键

- 数据库内部主键：`BIGSERIAL`（BIGINT）为主，分布式需全局唯一时可用 UUID。
- **不得把内部 PK 当作用户展示 ID。**

## 2. Stable Public ID（Final：8 位）

格式：`NGIQ-<TYPE>-<8位序号>`，例如 `NGIQ-BR-00000001`。

| 实体 | 前缀 | 示例 |
|---|---|---|
| BrainRegion | NGIQ-BR | NGIQ-BR-00000001 |
| CellularNeuralStructure | NGIQ-CNS | NGIQ-CNS-00000001 |
| NeurobiologicalProcess | NGIQ-NBP | NGIQ-NBP-00000001 |
| Connection | NGIQ-CON | NGIQ-CON-00000001 |
| ConnectionObservation | NGIQ-COB | NGIQ-COB-00000001 |
| Circuit | NGIQ-CIR | NGIQ-CIR-00000001 |
| Function | NGIQ-FUN | NGIQ-FUN-00000001 |
| Neurotransmitter | NGIQ-NT | NGIQ-NT-00000001 |
| Receptor | NGIQ-RCP | NGIQ-RCP-00000001 |
| Gene | NGIQ-GEN | NGIQ-GEN-00000001 |
| Disease | NGIQ-DIS | NGIQ-DIS-00000001 |
| Symptom | NGIQ-SYM | NGIQ-SYM-00000001 |
| ResearchStudy | NGIQ-STU | NGIQ-STU-00000001 |
| Publication | NGIQ-PUB | NGIQ-PUB-00000001 |
| Evidence | NGIQ-EVI | NGIQ-EVI-00000001 |
| Atlas | NGIQ-ATL | NGIQ-ATL-00000001 |
| ExternalRegion | NGIQ-XREG | NGIQ-XREG-00000001 |
| RegionMapping | NGIQ-RMAP | NGIQ-RMAP-00000001 |
| CircuitConnectionMembership | NGIQ-CCM | NGIQ-CCM-00000001 |
| CircuitRegionMembership | NGIQ-CRM | NGIQ-CRM-00000001 |
| BrainRegionHierarchyRelation | NGIQ-BRH | NGIQ-BRH-00000001 |
| FunctionHierarchyRelation | NGIQ-FHR | NGIQ-FHR-00000001 |
| BrainRegionAggregationMapping | NGIQ-BRAM | NGIQ-BRAM-00000001 |
| KnowledgeAssertion | NGIQ-AST | NGIQ-AST-00000001 |
| RelationDefinition | NGIQ-PRED | NGIQ-PRED-00000001 |
| Source | NGIQ-SRC | NGIQ-SRC-00000001 |
| Alias | NGIQ-ALS | NGIQ-ALS-00000001 |
| Xref | NGIQ-XRF | NGIQ-XRF-00000001 |
| EvidenceLink | NGIQ-ELK | NGIQ-ELK-00000001 |

> 禁止重复 prefix。Evidence/Assertion/Observation/Membership 未来可达百万级，故用 8 位；ID 一旦公开不再改格式。

## 3. 冻结规则（ID 稳定性）

1. 一经分配永久不变。
2. 不因 name 修改而改变。
3. 不因 entity merge 而重新分配。
4. 不因 deprecated 而释放。
5. 永不复用。
6. 数字部分不编码科学语义。
7. 不把 hemisphere / atlas / type / version 写进 ID。

- deprecated entity：旧 public ID 永久保留。
- merge：旧 ID 指向 canonical replacement，不分配给新实体。

## 4. 内部 vs 展示

| 用途 | 字段 |
|---|---|
| DB 内部主键 | `*_pk BIGSERIAL`（BIGINT） |
| 用户展示/外链 | `*_id`（NGIQ-…） |

- 所有表同时具备内部 PK（`*_pk`）与 stable public ID（`*_id`）。
- **FK 统一引用内部 `*_pk`，不引用 public `*_id`。**
- first-class 实体推荐 shared-PK：`kg_entities.entity_pk` 即 subtype 表 PK（见 03_common_entity_fields.md）。
