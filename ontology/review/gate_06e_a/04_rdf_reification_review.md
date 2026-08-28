# Gate 6E-A — RDF Reification Review

本轮状态: **仅审查，不写 TTL**

---

## 1. rdf:Statement 结构

```
:stmt rdf:type rdf:Statement ;
      rdf:subject :Hippocampus ;
      rdf:predicate :participatesIn ;
      rdf:object :Memory .
```

## 2. 优点

- RDF 标准；技术上可表达任意三元组的 statement。
- 生态兼容（部分工具）。

## 3. 缺点

- rdf:Statement 不是 OWL Class，OWL reasoning 基本不处理 reified statement。
- Protégé UX 差，四元组抽象难读。
- Evidence 要挂到 statement 还需额外 reification 层（statement → evidence）。
- 与已冻结的 DB knowledge_assertions 结构重复（DB 已有 subject/predicate/object + evidence_link）。

## 4. 结论

**不采用 rdf:Reification 作为 V1 canonical model。** 它更适合作为未来序列化/互操作格式，而非 NeuroGraphIQ 的核心断言模型。NeuroGraphIQ 已有更直接、更对齐 DB 的 assertion 模型（knowledge_assertions）。
