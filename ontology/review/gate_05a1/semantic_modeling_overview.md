# Gate 5A.1 — Semantic Modeling Overview（核心语义建模总览）

Ontology IRI（当前）: `https://neurographiq.org/ontology/macro96`
本轮状态: **仅决策文档，未修改正式 TTL**

---

## 1. 本 Gate 的性质

Gate 5A.1 是 Gate 5A 之后的**短 Gate**，只解决一个功能：

> 已经人工审查通过的科学概念（Connection / Circuit / Evidence），在 OWL 中应该用 **Class / Individual / Property / 受控词表 / 其他** 的哪一种方式表达。

**不做**：重新讨论科学定义。Gate 2 / Gate 3 / Gate 4A 的科学语义**必须保持不变**。

## 2. 本 Gate 必须解决的 5 个核心问题

| # | 问题 | 推荐基线（待审计反证） |
|---|---|---|
| 1 | ConnectionType 的 OWL 表达 | REMOVE → Connection subtype hierarchy |
| 2 | CircuitType 去留 | REMOVE from V1 |
| 3 | EvidenceType 去留/表达 | REMOVE from V1 → multi-axis model |
| 4 | Ontology IRI/namespace 是否升级 | MIGRATE → `human-brain` |
| 5 | Governance 是否与 Domain 同 ontology | database-first（移出 core ontology） |

外加一个**原则性**决定（不落到具体 Property）：

| # | 问题 | 推荐 |
|---|---|---|
| 6 | Connection entity vs Neo4j direct edge | reified Connection entity 为 canonical；direct edge 仅 projection |

## 3. 决策的判据维度

每个 Type Class 决策都从以下维度评估：

1. **OWL DL 语义**（class typing / punning 风险）
2. **Reasoning**（subClassOf 继承 vs 显式 has_type）
3. **PostgreSQL 实现**（枚举/外键字段）
4. **API**（字段 vs 资源）
5. **Frontend**（显示/筛选）
6. **Neo4j**（投影节点/关系）
7. **Import/Export**（序列化）
8. **Backward compatibility**（旧数据/旧字段）
9. **现有 Gate docs**（Gate 2/3/4A 是否需改写）
10. **canonical entity model**（TBox/ABox 一致性）

## 4. 本 Gate 严格禁止事项

- 不修改 `ontology/neurographiq_macro96_v1.ttl`。
- 不新增/删除 OWL Class、Property、Individual、axiom、SHACL、owl:imports。
- 不修改 namespace / Ontology IRI。
- 不做 PostgreSQL migration / API / frontend / Neo4j 实现。
- 不 commit、不 push。

## 5. 输出文件

见 decision_summary.md；14 个文件组成 Gate 5A.1 review 包。
