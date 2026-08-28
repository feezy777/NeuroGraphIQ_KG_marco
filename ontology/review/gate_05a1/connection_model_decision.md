# Gate 5A.1 — ConnectionType OWL 表达决策

Ontology IRI（当前）: `https://neurographiq.org/ontology/macro96`
本轮状态: **仅决策文档，未修改正式 TTL**

---

## 1. 前提：Gate 2 科学语义冻结，不重审

以下科学语义**保持不变**（只讨论 OWL 表达，不重审其存在性）：

- StructuralConnection（结构性物理通路；方向 directed/reciprocal/unknown；polysynaptic 不压缩为单条）
- Projection（有 axonal projection 语义/证据的 StructuralConnection 子类；DTI 不能单独判向）
- FunctionalConnectivity（统计依赖/时间相关；non-directional 默认；不隐含结构）
- EffectiveConnectivity（model-dependent directed influence；≠Projection，≠StructuralConnection）

## 2. 冲突根源

当前 TTL：Connection 是 Class；ConnectionType 也是 Class；StructuralConnection/Projection/FunctionalConnectivity/EffectiveConnectivity 是 ConnectionType 下 OWL Class。

未来：`NGIQ_CONN_000001` 将是 Connection **Individual**，直觉需 `hasConnectionType Projection`。但 Projection 当前是 OWL Class，不是 ObjectProperty 可自然指向的 controlled-vocabulary Individual。**存在 class-vs-individual 冲突。**

## 3. 方案 A — Connection subtype model

```
Connection
├─ StructuralConnection
│  └─ Projection
├─ FunctionalConnectivity
└─ EffectiveConnectivity
```

实例：`NGIQ_CONN_000001 rdf:type Projection`；OWL reasoner 自动推出其也是 StructuralConnection、Connection。

**优点**：
- OWL 语义自然，类型继承直接（rdfs:subClassOf 链）。
- 不需要额外 hasConnectionType。
- Projection 在科学语义上本质就是一类 Connection。
- 与 TBox/ABox policy 一致（Individual 的 rdf:type 指向 Class）。
- 后续 reasoning 简单，元模型层最少。

**缺点**：
- 需重构 Gate 2B 当前 hierarchy（StructuralConnection 的父从 ConnectionType 改为 Connection）。
- ConnectionType 顶层 Class 将被删除。
- 数据库前端可能仍保留 `connection_type` 字段，但它不再等于 OWL ConnectionType Class（见 §6）。

## 4. 方案 B — Controlled vocabulary model

保持 Connection、ConnectionType；将 StructuralConnectionType/ProjectionType/FunctionalConnectivityType/EffectiveConnectivityType 建成 ConnectionType 的 Individuals；`NGIQ_CONN_000001 hasConnectionType ProjectionType`。

**优点**：
- 数据库枚举直观；hasConnectionType 结构清楚；类型词表可独立治理。

**缺点**：
- 增加额外元模型层（Connection + ConnectionType 双层体系）。
- OWL hierarchy 推理不如 subtype 直接。
- Projection 科学上就是一种 Connection，被降为"类型值"反而削弱语义。
- 需维护 Connection + ConnectionType 双层。

## 5. 推荐：方案 A（Connection subtype model）

从 OWL DL 语义、reasoning、canonical entity model 三方面，subtype model 更贴合「Projection 是 Connection 的一类」这一科学事实，且元模型最少、推理最直接。

- **ConnectionType → REMOVE FROM FORMAL V1 ONTOLOGY**。
- 未来正式结构：
```
Connection
├─ StructuralConnection └─ Projection
├─ FunctionalConnectivity
└─ EffectiveConnectivity
```

## 6. connection_type 字段与 OWL Class 不冲突（关键原则）

即使未来正式 OWL 删除 ConnectionType，**数据库与 API 仍可保留 `connection_type` 字段**（值：projection / structural_connection / functional_connectivity / effective_connectivity）。

该字段是 **serialization / application-level classification**，映射到 `rdf:type`：

```
connection_type = projection  →  rdf:type ngiq:Projection
```

**原则：数据库字段叫 `connection_type` ≠ OWL 必须存在 ConnectionType Class。** 二者解耦。

## 7. 结论

| 项 | 决策 |
|---|---|
| ConnectionType | **REMOVE** |
| Connection hierarchy | Connection └─ StructuralConnection └─ Projection / FunctionalConnectivity / EffectiveConnectivity |
| connection_type 字段 | 保留为 application-level serialization，映射到 rdf:type |
| 是否重审 Gate 2 科学语义 | 否（只改 subClassOf 上层表达） |
