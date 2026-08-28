# Gate 6F-A — 学习版说明（Spatial Relations）

---

### partOf / subfieldOf

- 表示真正的脑区解剖层级。
- 例：CA1 subfieldOf Hippocampus。

### spatiallyOverlaps

- 表示空间范围部分重叠。
- 但：重叠 ≠ partOf（重叠随 atlas/version 变，不进 OWL）。

### adjacentTo

- 表示空间边界相邻。
- 但：相邻 ≠ neural connection；相邻随 atlas 边界变。

### locatedIn

- 当前需审查：是否与 partOf 重复。
- 若只是"空间 containment"且无独立稳定语义 → V1 不保留。

### 一句话

空间关系（重叠/相邻/包含）是几何事实，依赖 atlas/版本/参考空间，放数据库；OWL 只保留稳定的解剖层级（partOf/subfieldOf）。
