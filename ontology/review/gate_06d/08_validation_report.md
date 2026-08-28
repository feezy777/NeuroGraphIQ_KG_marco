# Gate 6D — Validation Report

对 `ontology/neurographiq_macro96_v1.ttl` 的验证结果。

---

## 1. 元数据

| 项 | 期望 | 实际 |
|---|---|---|
| Ontology IRI | `https://neurographiq.org/ontology/human-brain` | ✅ |
| version | `0.6.2-gate6d` | ✅ |
| Named Class | 23 | ✅ |
| ObjectProperty | 26 | ✅ |
| DataProperty | 0 | ✅ |
| Named Individual | 0 | ✅ |
| imports | 0 | ✅ |

## 2. 新增 ObjectProperty

- [x] subFunctionOf（Domain Function / Range Function）

## 3. Property hierarchy（4 条，不变）

- [x] projectsTo ⊑ structurallyConnectedTo
- [x] hasSourceRegion ⊑ hasEndpointRegion
- [x] hasTargetRegion ⊑ hasEndpointRegion
- [x] subfieldOf ⊑ partOf
- [x] subFunctionOf **无** subPropertyOf（独立）

## 4. 不存在（验证通过）

- [x] 无 functionPartOf / partOfFunction / hasSubFunction / componentFunctionOf / hasFunctionalComponent
- [x] 无 subFunctionOf subPropertyOf partOf
- [x] 无 owl:TransitiveProperty / inverseOf / propertyChainAxiom

## 5. 结论

**Gate 6D Function Hierarchy Ontology 写入完成（0.6.2-gate6d），等待 Protégé 人工审查。**
