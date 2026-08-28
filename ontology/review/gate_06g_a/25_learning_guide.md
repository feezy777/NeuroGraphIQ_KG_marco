# Gate 6G-A — 学习版说明（Global Audit）

---

### Class
- 是什么：知识图谱中的"类别"。
- 例：BrainRegion。

### Individual
- 是什么：一个具体东西。
- 例（未来）：Hippocampus。

### ObjectProperty
- 是什么：两个东西之间的语义关系。
- 例：CA1 subfieldOf Hippocampus。

### Canonical relation
- 是什么：数据库真正保存的一手知识结构。

### Derived relation
- 是什么：为了查询/Neo4j 展示，从 canonical 数据计算出来的方便关系。

### 为什么做 Global Audit
- 单个关系看起来都对，组合起来仍可能互相矛盾。
- 本轮就是检查整套本体放在一起后是否仍科学一致。
