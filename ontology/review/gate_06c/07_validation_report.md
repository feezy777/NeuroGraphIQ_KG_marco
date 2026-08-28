# Gate 6C — Validation Report

对 `ontology/neurographiq_macro96_v1.ttl` 的验证结果。

---

## 1. 元数据

| 项 | 期望 | 实际 |
|---|---|---|
| Ontology IRI | `https://neurographiq.org/ontology/human-brain` | ✅ |
| version | `0.6.1-gate6c` | ✅ |
| Named Class | 23 | ✅ |
| ObjectProperty | 25 | ✅ |
| DataProperty | 0 | ✅ |
| Named Individual | 0 | ✅ |
| imports | 0 | ✅ |

## 2. 新增 ObjectProperty

- [x] partOf（Domain BrainRegion / Range BrainRegion）
- [x] subfieldOf（Domain BrainRegion / Range BrainRegion）
- [x] subfieldOf rdfs:subPropertyOf partOf

## 3. Property hierarchy（4 条）

- [x] projectsTo ⊑ structurallyConnectedTo
- [x] hasSourceRegion ⊑ hasEndpointRegion
- [x] hasTargetRegion ⊑ hasEndpointRegion
- [x] subfieldOf ⊑ partOf

## 4. 不存在（验证通过）

- [x] 无 overlaps / locatedIn / adjacentTo
- [x] 无 aggregatesTo / rollsUpTo / mapsToGranularity
- [x] 无 granularityLevel / hasGranularity（DataProperty）
- [x] 无 owl:TransitiveProperty

## 5. 结论

**Gate 6C BrainRegion Hierarchy Ontology 写入完成（0.6.1-gate6c），等待 Protégé 人工审查。**
