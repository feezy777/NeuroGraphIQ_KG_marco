# Gate 6F-B — spatiallyOverlaps Freeze

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. 状态：DB ONLY / DEFER OWL

不新增 spatiallyOverlaps ObjectProperty。

## 2. Future Domain/Range：DEFER

不再冻结为 BrainRegion → BrainRegion。未来若建 spatial ontology，更科学的模型可能是 SpatialRepresentation → spatiallyOverlaps → SpatialRepresentation。

## 3. 逻辑性质

- 语义上 symmetric（但不写 owl:SymmetricProperty）。
- NOT transitive（A overlaps B、B overlaps C 不推 A overlaps C）。

## 4. 理由

依赖 atlas / version / reference space / registration / geometry，属 representation-dependent 而非 canonical 稳定语义。
