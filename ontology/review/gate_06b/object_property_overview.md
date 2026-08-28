# Gate 6B — ObjectProperty Overview（对象属性总览）

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
version: `0.6.0-gate6b`
本轮状态: **已正式写入 TTL，等待 Protégé 人工审查**

---

## 1. 本轮成果

把 Gate 6A 已批准的 23 个 Relation 正式写入 Human Brain Ontology TTL，成为 OWL ObjectProperty。

| 统计 | 数量 |
|---|---|
| Named Class | 23 |
| ObjectProperty | 23 |
| Canonical ObjectProperty | 17 |
| Derived ObjectProperty | 6 |
| DataProperty | 0 |
| Named Individual | 0 |
| owl:imports | 0 |

## 2. 命名规范

- OWL canonical property 名：lowerCamelCase（`projectsTo`）。
- 老师 PPT / 前端 / Neo4j 显示：UPPER_SNAKE_CASE（`PROJECTS_TO`）。

## 3. Canonical / Derived 标记方式

本轮**不创建**额外 AnnotationProperty（如 `ngiq:representationRole`）。Canonical / Derived 通过 `rdfs:comment` 记录。

## 4. 允许的简单 Property hierarchy（仅 3 条）

```
structurallyConnectedTo
└─ projectsTo

hasEndpointRegion
├─ hasSourceRegion
└─ hasTargetRegion
```

## 5. 未加入的复杂 OWL 特性

- 未加 owl:inverseOf / SymmetricProperty / TransitiveProperty / FunctionalProperty / propertyChainAxiom / cardinality / SHACL。
- 逻辑特性留后续关系约束 Gate。

## 6. 禁止正式写入

- supports / contradicts（留 Evidence/Assertion Formalization Gate）。
- 未新增 DataProperty / Individual / Class / AnnotationProperty。
