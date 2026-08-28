# Gate 6E-A — RDF-star Review

本轮状态: **仅审查，不写 TTL**

---

## 1. RDF-star 思路

```
<<Hippocampus participatesIn Memory>>
    ngiq:hasEvidence E1 ;
    ngiq:confidence 0.9 .
```

可直接在 quoted triple 上挂 Evidence/confidence/provenance。

## 2. 优点

- 语法简洁，直观表达"对某条边的标注"。
- Neo4j/图数据库天然对应（edge property）。

## 3. 缺点

- RDF-star 不是 OWL 2 DL；当前 Protégé / OWL reasoner 支持不稳定。
- 与已冻结的 DB assertion model（knowledge_assertions + assertion_evidence_links）结构不同，需额外映射。
- 作为 V1 core ontology canonical model 风险高。

## 4. 结论

**RDF-star 不采用为 V1 canonical model；列为 future projection / serialization option。** 当前 canonical truth 用 DB assertion + reified entity；未来若需要把 Evidence 直接标注到边，可把 RDF-star 作为 Neo4j/序列化投影（`<<A participatesIn B>>` 带 evidence 元数据），但不是本体真值源。
