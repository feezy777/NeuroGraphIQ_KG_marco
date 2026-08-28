# Gate 6A — Core Relation Ontology Design（关系设计总览）· 第二轮修订

Ontology IRI: `https://neurographiq.org/ontology/human-brain`（当前 version `0.5.0-gate5b`）
本轮状态: **仅关系设计文档，未修改正式 TTL**

---

## 1. 本 Gate 性质

- 只设计 **V1 核心关系**（学习友好、易整理 PPT）。
- 不写 TTL、不建 ObjectProperty/DataProperty/Individual。
- 每个关系只给：中英文名、1–2 句定义、Domain、Range、方向、1–2 例、易混区分、Canonical/Derived 标记。

## 2. 两类关系（必须先区分）

### A. Canonical semantic model（Connection entity model）

```
BrainRegion ──(endpoint/source)──> Connection entity ──(endpoint/target)──> BrainRegion
```

`Connection C001 rdf:type Projection` 是 canonical 知识表示。

### B. Direct relation / graph projection

```
CA1 -[:PROJECTS_TO]-> mPFC
```

- 用于 Neo4j 查询、前端图谱展示、与老师 PPT 边类型一致。
- **不是另一份独立 canonical truth**。

**铁律：Connection entity = canonical；STRUCTURALLY_CONNECTED_TO / FUNCTIONALLY_CONNECTED_TO / PROJECTS_TO = 由 Connection entity 派生的直接关系。禁止维护两套互相独立的数据真值。**

## 3. 关系分类（6 类）

| 分类 | 关系 |
|---|---|
| A. PPT Scientific Relations | STRUCTURALLY_CONNECTED_TO、FUNCTIONALLY_CONNECTED_TO、PROJECTS_TO、PARTICIPATES_IN、MODULATES、INCREASES_RISK_OF |
| B. NeuroGraphIQ Scientific Extension | EFFECTIVELY_CONNECTED_TO、HAS_FUNCTION、HAS_SYMPTOM、ACTS_ON |
| C. Connection Structural Model | hasEndpointRegion、hasSourceRegion、hasTargetRegion |
| D. Circuit Model | includesRegion、hasConnectionMembership、membershipConnection（+ derived hasConnection） |
| E. Provenance | reportedIn、providesEvidence（supports/contradicts → DEFER formalization） |
| F. Atlas / Mapping | definedInAtlas、mappingSource、mappingTarget（+ derived mapsTo） |

## 4. 命名规则

- **老师 PPT 名 / Neo4j / 前端显示**：大写蛇形（`PROJECTS_TO`）。
- **OWL ObjectProperty 建议名**：lowerCamelCase（`projectsTo`）。
- 本 Gate 只提命名方案，不写 TTL。

## 5. 数量概览（Round 2 重新统计）

- PPT 原始关系：6
- Canonical current candidates：17
- Derived current candidates：6
- Deferred semantic relations：2（supports、contradicts）
- **当前可正式写入 ObjectProperty 的 V1 relation 总数：23**

## 6. 本轮禁止

- 不修改 TTL；不建 ObjectProperty/DataProperty/Individual；不建 SHACL/Restriction/property chain/owl:inverseOf/owl:SymmetricProperty/owl:TransitiveProperty；不新增 Assertion/RelationAssertion/GeneticVariant/Allele Class；不动 DB/API/frontend/Neo4j/数据导入；不 commit、不 push。
