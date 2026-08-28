# Gate 6F-B — Freeze Decision

Ontology IRI: `https://neurographiq.org/ontology/human-brain`（version 0.6.2-gate6d）

---

## Gate 6F Spatial Model V1

### OWL expansion：NONE

- 新增 Class：0
- 新增 ObjectProperty：0
- 新增 DataProperty：0

### 正式保留（OWL）

- partOf（BrainRegion → BrainRegion，canonical anatomical hierarchy）
- subfieldOf（BrainRegion → BrainRegion，subfieldOf ⊑ partOf）

### 正式 DB-only / future spatial

- spatiallyOverlaps（DB only / DEFER OWL；future Domain/Range=DEFER，倾向 SpatialRepresentation-level）
- adjacentTo（DB only / DEFER OWL）

### 正式 REMOVE/DEFER

- locatedIn（与 partOf 重复）

## 结论

Gate 6F-B 完成 Spatial Ontology Boundary Freeze；正式 OWL 本体未扩展，version 保持 0.6.2-gate6d。
