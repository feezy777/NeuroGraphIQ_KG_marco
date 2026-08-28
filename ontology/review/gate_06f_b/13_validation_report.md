# Gate 6F-B — Validation Report

对 `ontology/neurographiq_macro96_v1.ttl` 的验证结果（本轮不改 TTL）。

---

## 1. 元数据

| 项 | 期望 | 实际 |
|---|---|---|
| version | 0.6.2-gate6d | ✅ |
| Named Class | 23 | ✅ |
| ObjectProperty | 26 | ✅ |
| DataProperty | 0 | ✅ |
| Named Individual | 0 | ✅ |
| imports | 0 | ✅ |

## 2. 未新增（验证通过）

- [x] 无 spatiallyOverlaps / adjacentTo / locatedIn ObjectProperty
- [x] 无 SpatialRepresentation Class
- [x] partOf / subfieldOf 保持（subfieldOf ⊑ partOf）

## 3. 结论

**Gate 6F-B Spatial Ontology Boundary Freeze：正式 OWL 未扩展，version 保持 0.6.2-gate6d。**
