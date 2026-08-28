# Gate 6A — Canonical vs Derived（canonical 与派生关系的区分）· 第二轮修订

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
本轮状态: **仅设计文档，未修改正式 TTL**

---

## 1. 三个 Representation Role

| Role | 含义 |
|---|---|
| **CANONICAL** | 正式知识真值；存入知识图谱 canonical 层；有 provenance/evidence/review |
| **DERIVED** | 由 canonical 实体派生；用于查询/展示，不作为独立真值 |
| **APPLICATION / GRAPH PROJECTION** | Neo4j/前端投影，可由 DERIVED 复用 |

## 2. 逐关系标记（Round 2）

### Canonical（17）

- participatesIn、modulates、increasesRiskOf
- hasFunction、hasSymptom、actsOn
- hasEndpointRegion、hasSourceRegion、hasTargetRegion
- includesRegion、hasConnectionMembership、membershipConnection
- reportedIn、providesEvidence
- definedInAtlas、mappingSource、mappingTarget

### Derived / Graph Projection（6）

- structurallyConnectedTo（← StructuralConnection entity）
- functionallyConnectedTo（← FunctionalConnectivity entity）
- projectsTo（← Projection entity）
- effectivelyConnectedTo（← EffectiveConnectivity entity）
- hasConnection（← CircuitConnectionMembership）
- mapsTo（← RegionMapping）

### Deferred（2，语义保留、暂缓正式化）

- supports、contradicts

## 3. 核心原则

- 老师 PPT 的边类型完整保留，但标记为 **Derived**。
- **不产生两套 canonical truth**：direct edge 由 Connection entity 派生。
- Connection entity 仍是 canonical truth。

## 4. 示例

- Canonical: `Connection C001 rdf:type Projection; hasSourceRegion CA1; hasTargetRegion mPFC`。
- Derived: `CA1 projectsTo mPFC`（由 C001 派生，用于图谱展示）。
- Non-directional canonical: `FC001 rdf:type FunctionalConnectivity; hasEndpointRegion PCC; hasEndpointRegion mPFC` → derived `PCC functionallyConnectedTo mPFC`。
