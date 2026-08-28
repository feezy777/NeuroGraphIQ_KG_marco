# Gate 7A — Governance Boundary（治理边界与避免重复建模）

本轮状态: **仅设计文档**

---

## 1. Governance 不进入本 schema

以下属 application / governance schema（PostgreSQL 单独 schema），**不**放入本科学数据字典：

- ConnectionCandidate / CircuitCandidate / EvidenceCandidate
- SearchRun / ExtractionRun
- ModelReview / HumanReview
- InferenceRecord / ValidationRecord
- ConceptDefinition / ConnectionAssessment

本数据字典只覆盖 canonical 科学实体 + 证据/断言层。

## 2. reified entity vs ordinary assertion 的边界（关键规则）

| 事实类型 | canonical truth 存放 |
|---|---|
| Connection（复杂 reified） | `connections` 专用表 |
| RegionMapping（复杂 reified） | `region_mappings` 专用表 |
| CircuitConnectionMembership | `circuit_connection_memberships` 专用表 |
| CircuitRegionMembership | `circuit_region_memberships` 专用表 |
| 普通 ObjectProperty（participatesIn / modulates / increasesRiskOf / hasSymptom / actsOn / hasFunction …） | `knowledge_assertions` |
| derived relation（projectsTo / structurallyConnectedTo / functionallyConnectedTo / effectivelyConnectedTo / mapsTo / hasConnection） | **不重复人工存 canonical assertion**（由 reified 实体派生） |

## 3. Connection 不重复存储（关键）

- `CA1 projectsTo mPFC` 的 canonical truth 只在 `connections`（connection_class=projection + source/target）。
- **不在** knowledge_assertions 再独立保存一份 `CA1 projectsTo mPFC`。
- derived relation 由 connections 派生，供 Neo4j / 前端 projection。

## 4. Evidence 如何挂

- **reified entity**（Connection/Circuit/RegionMapping）：通过 `connection_observations` 或专用 evidence 关联挂载。
- **ordinary relation assertion**：通过 `assertion_evidence_links` 挂载（evidence_role=supports/contradicts/qualifies）。

## 5. 一致性保障

- `entity_type`（kg_entities）与 subtype 表一一对应，需用 CHECK / 应用层约束保持一致。
- derived count（evidence_count / publication_count 等）是 DERIVED，非 independent truth，由物化/定时刷新，不人工维护。
