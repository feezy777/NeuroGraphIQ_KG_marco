# Gate 6F-B — adjacentTo Freeze

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. 状态：DB ONLY / DEFER OWL

不新增 adjacentTo ObjectProperty。

## 2. Future Domain/Range：DEFER

优先 SpatialRepresentation-level relation。

## 3. 逻辑性质

- 语义上 symmetric（不写 owl:SymmetricProperty）。
- NOT transitive。

## 4. 理由

adjacency 依赖 boundary geometry / reference space / atlas version / segmentation 定义；同一 BrainRegion 在不同 atlas/version 中 adjacency 可不同。
