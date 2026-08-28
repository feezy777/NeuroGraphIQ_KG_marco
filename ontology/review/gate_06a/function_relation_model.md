# Gate 6A — Function Relation Model（功能关系模型）· 第二轮修订

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
本轮状态: **仅设计文档，未修改正式 TTL**

---

## 1. PARTICIPATES_IN（恢复 PPT 完整语义）

- **Domain**：BrainRegion。
- **Range**：Circuit OR Function。
- **方向**：Directed。
- **例子**：Hippocampus PARTICIPATES_IN PapezCircuit；PrefrontalCortex PARTICIPATES_IN WorkingMemory。
- **Role**：Canonical。

## 2. HAS_FUNCTION（收窄为 Circuit → Function）

- **Domain**：Circuit。
- **Range**：Function。
- **方向**：Directed。
- **例子**：PapezCircuit HAS_FUNCTION MemoryRelatedFunction。
- **Role**：Canonical。

## 3. 去重规则（Round 2）

- **BrainRegion → Function** 的 canonical relation = `participatesIn`。
- **Circuit → Function** 的 canonical relation = `hasFunction`。
- **不再**把 `BrainRegion hasFunction Function` 作为 V1 canonical relation。

即：

| 关联 | 关系 |
|---|---|
| BrainRegion → Function | participatesIn |
| Circuit → Function | hasFunction |

避免 `BrainRegion participatesIn Function` 与 `BrainRegion hasFunction Function` 同时作为 canonical truth。

## 4. 结论

| 关系 | Domain | Range | 语义 | Role |
|---|---|---|---|---|
| participatesIn | BrainRegion | Circuit OR Function | 参与回路/功能 | Canonical |
| hasFunction | Circuit | Function | 回路关联功能 | Canonical |
