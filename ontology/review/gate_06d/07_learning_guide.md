# Gate 6D — 学习版说明（Function Hierarchy）

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
version: `0.6.2-gate6d`

---

### subFunctionOf / 下位功能属于

- 是什么：一个更具体的功能概念属于一个更宽泛的功能概念。
- 例子：Working Memory → Memory；Selective Attention → Attention。
- 容易混：不是脑区 partOf；不是 BrainRegion participatesIn Function；不是 OWL rdfs:subClassOf。

### 为什么不用 rdfs:subClassOf

- 因为 WorkingMemory、Memory 未来是 Function entities / Individuals，不是新的 ontology Class。

### function part_of

- 当前 DEFER。
- 原因：功能组成关系容易与 NeurobiologicalProcess / 任务步骤 / 认知操作混淆。
