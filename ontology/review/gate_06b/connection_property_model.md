# Gate 6B — Connection Property Model（连接属性模型）

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
version: `0.6.0-gate6b`

---

## 1. Canonical = Connection entity

```
BrainRegion ──(endpoint/source)──> Connection entity ──(endpoint/target)──> BrainRegion
```

Connection entity 是 canonical truth。

## 2. 端点/方向属性

| Property | 语义 | 使用条件 |
|---|---|---|
| hasEndpointRegion | 谁和谁形成连接，不表方向 | direction unknown / non-directional |
| hasSourceRegion | 已知连接起点 | direction scientifically established |
| hasTargetRegion | 已知连接终点 | direction scientifically established |

- hasSourceRegion / hasTargetRegion subPropertyOf hasEndpointRegion。

## 3. 各 Connection 子类模型

| 子类 | 端点表达 | 派生 direct relation |
|---|---|---|
| StructuralConnection（direction unknown） | hasEndpointRegion A/B | A structurallyConnectedTo B |
| FunctionalConnectivity（non-directional） | hasEndpointRegion A/B | A functionallyConnectedTo B |
| Projection（directed） | hasSourceRegion + hasTargetRegion | A projectsTo B |
| EffectiveConnectivity（directed） | hasSourceRegion + hasTargetRegion | A effectivelyConnectedTo B |

## 4. 关键约束

- FunctionalConnectivity **禁止**伪 source/target（用 hasEndpointRegion）。
- direction-unknown StructuralConnection **不伪造** source/target。
- DTI/tractography alone 不能确定 projectsTo 方向。

## 5. Direct derived relations（graph projection）

- structurallyConnectedTo / functionallyConnectedTo / projectsTo / effectivelyConnectedTo 均为 Derived，由 Connection entity 派生。
- 不是第二份 canonical truth。
