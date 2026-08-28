# Gate 6E-B — 学习版说明（Evidence / Assertion 边界）

---

### Evidence 为什么没有 supports ObjectProperty？

因为 Evidence 支持的是一条具体 claim。普通 claim 存 PostgreSQL KnowledgeAssertion；Connection/Circuit 本身已是 reified scientific object。强行 `Evidence supports Something` 会产生不清晰的 Range 和重复 truth。

### 为什么 Evidence 还在 OWL？

因为 Evidence 是稳定的 scientific concept。但"Evidence 如何作用于具体 claim"属于 database assertion context。

### 为什么这样不矛盾？

- Ontology：定义"世界里有什么概念和稳定关系"。
- Database：保存"某一次具体知识断言、证据、置信度和审核状态"。

### 一句话

OWL 管"稳定的科学语义"；PostgreSQL 管"具体的断言、证据关联、置信度、审核流程"。
