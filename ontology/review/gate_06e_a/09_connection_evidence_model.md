# Gate 6E-A — Connection Evidence Model（核心难点）

本轮状态: **仅设计，不写 TTL**

---

## 1. 难点

Connection CON-001（CA1 → mPFC，rdf:type Projection）已含 source/target/class/direction。Evidence 到底支持：

- A. Connection entity 本身？
- B. "CON-001 exists" assertion？
- C. CON-001 的某属性 assertion（hasSourceRegion CA1）？
- D. ConnectionObservation 中间层？

## 2. 推荐：把 Connection 视作 reified proposition（= A，不经 B/C wrapper）

- Connection entity 自身就是一条 **reified scientific claim object**（source + target + type 组合构成"存在 A→B axonal projection"这条命题）。
- Evidence **直接支持 Connection entity**，不额外创建 existence Assertion。
- 无需把 Connection 再包一层 KnowledgeAssertion（避免无意义 wrapper + 双写 truth）。

## 3. Evidence 路径（两种，互补）

```
Model 1（观测级）:  Evidence → connection_observations → Connection
Model 2（实体级）:  Evidence → connection_evidence_link → Connection
```

- **connection_observations**：study-level 结构化观测（sample_size / method / metric / p / condition / population），可 reference Evidence。
- **直接 evidence 关联**：当 Evidence 直接支撑 Connection 的 canonical claim（source/target/type 组合）时，可直接 link。

## 4. 不双写 truth

- `connections` 表 = canonical Connection truth。
- **不得**在 knowledge_assertions 再存一份 `CA1 projectsTo mPFC`。
- Neo4j `A -[:PROJECTS_TO]-> B` 只是 derived projection。

## 5. contradicts 语义边界

- Evidence contradicts Connection = 有明确冲突发现（如 A 与 B 无该投射的实验证据）。
- **禁止**把"未观察到"自动等于 contradicts。
