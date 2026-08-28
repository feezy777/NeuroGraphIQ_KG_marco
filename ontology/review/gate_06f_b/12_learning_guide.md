# Gate 6F-B — 学习版说明（Spatial Ontology Boundary）

---

### BrainRegion
- 是什么：一个稳定的脑区概念。
- 例：Hippocampus。

### SpatialRepresentation
- 是什么：这个脑区在某个具体 atlas/space/version 里的几何样子。
- 例：Hippocampus 在 MNI152 中的 mask。

### partOf
- 是什么：真正的 anatomical hierarchy。
- 例：CA1 subfieldOf Hippocampus。

### spatiallyOverlaps
- 是什么：两个几何表示发生空间重叠。
- 为什么不进 V1 OWL：依赖具体 geometry/reference space/version。

### adjacentTo
- 是什么：两个几何表示边界相邻。
- 为什么不等于 Connection：空间上挨着不代表存在神经纤维/功能连接/投射。

### locatedIn
- 为什么不用：BrainRegion→BrainRegion 时容易和 partOf/subfieldOf 重复。
