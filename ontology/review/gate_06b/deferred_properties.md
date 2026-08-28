# Gate 6B — Deferred Properties（暂缓属性）

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
version: `0.6.0-gate6b`

---

## 1. 明确 DEFER（未写入 TTL）

| Property | 状态 | 原因 |
|---|---|---|
| supports | DEFER | Range 应为 assertion/relation assertion，非仅 Connection/Circuit entity |
| contradicts | DEFER | 同上 |

## 2. 未来需解决的 Evidence–Assertion 建模

- Evidence 如何关联「一条具体知识断言」。
- 候选：Assertion/RelationAssertion Class；PostgreSQL evidence attachment record；reified entity 直接关联。
- 留 Future Evidence / Assertion Formalization Gate。

## 3. 未加入的 OWL 特性（留后续关系约束 Gate）

- owl:inverseOf、SymmetricProperty、TransitiveProperty、FunctionalProperty、InverseFunctionalProperty、propertyChainAxiom、cardinality restriction、SHACL、DisjointProperty。

## 4. 未新增的 Class

- Assertion / RelationAssertion / Statement / EdgeAssertion / GeneticVariant / Allele。
