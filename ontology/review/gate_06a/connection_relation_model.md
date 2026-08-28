# Gate 6A — Connection Relation Model（连接关系模型）· 第二轮修订

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
本轮状态: **仅设计文档，未修改正式 TTL**

---

## 1. Canonical model 保持 Connection entity

```
BrainRegion ──(endpoint/source)──> Connection entity ──(endpoint/target)──> BrainRegion
```

`C001 rdf:type Projection` 承载具体连接类型与方向。**Connection entity = canonical truth。**

## 2. 端点关系（Round 2 新增 hasEndpointRegion）

| 关系 | 语义 | 使用条件 | Role |
|---|---|---|---|
| hasEndpointRegion | 谁和谁形成这条连接，不表方向 | direction unknown / non-directional | Canonical |
| hasSourceRegion | 已知连接起点 | direction scientifically established | Canonical |
| hasTargetRegion | 已知连接终点 | direction scientifically established | Canonical |

### 清晰规则

- **hasEndpointRegion** = "谁和谁形成这条连接"，不表达方向。
- **hasSourceRegion / hasTargetRegion** = "已经知道谁到谁"，表达真实方向。

推荐逻辑：

- Direction unknown / non-directional → `hasEndpointRegion`。
- Direction scientifically established → `hasSourceRegion` + `hasTargetRegion`。

> 不要把数据库排序需求写进 ontology semantics。数据库 canonical ordering 如以后需要，应在 application/database 层处理，**不是用 source/target 伪装**。

## 3. 各 Connection 子类的端点/方向模型

| 子类 | 端点表达 | 派生 direct relation |
|---|---|---|
| StructuralConnection（direction unknown） | hasEndpointRegion A/B | A STRUCTURALLY_CONNECTED_TO B（direction not asserted） |
| StructuralConnection（direction known） | hasSourceRegion + hasTargetRegion | （可判向） |
| FunctionalConnectivity（non-directional） | hasEndpointRegion A/B | A FUNCTIONALLY_CONNECTED_TO B（non-directional） |
| Projection（directed） | hasSourceRegion + hasTargetRegion | A PROJECTS_TO B |
| EffectiveConnectivity（directed） | hasSourceRegion + hasTargetRegion | A EFFECTIVELY_CONNECTED_TO B |

### 关键约束

- FunctionalConnectivity **禁止**使用 hasSourceRegion / hasTargetRegion 作为排序字段。
- StructuralConnection 方向未知时**不要伪造** source/target。

## 4. Direct derived relations（graph projection）

| 派生关系 | 对应 Connection subtype |
|---|---|
| STRUCTURALLY_CONNECTED_TO | StructuralConnection |
| PROJECTS_TO | Projection |
| FUNCTIONALLY_CONNECTED_TO | FunctionalConnectivity |
| EFFECTIVELY_CONNECTED_TO | EffectiveConnectivity |

- 这些是 **Derived / graph projection**，用于 Neo4j 查询与前端展示。
- **不是第二份 canonical truth**；由 Connection entity 派生，禁止独立维护。

## 5. 禁止重复建模

- 不得同时维护 `(A)-[:PROJECTS_TO]->(B)` 与独立的 Connection entity 两套真值。
- direct edge 只是 canonical Connection entity 的投影/派生。
