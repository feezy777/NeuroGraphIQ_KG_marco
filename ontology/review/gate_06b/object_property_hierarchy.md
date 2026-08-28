# Gate 6B — ObjectProperty Hierarchy（对象属性层级）

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
version: `0.6.0-gate6b`

本 Gate 仅写入 3 条 `rdfs:subPropertyOf`，无 owl:inverseOf / Symmetric / Transitive / property chain。

---

## 1. BrainRegion direct/derived relations

```
structurallyConnectedTo
└─ projectsTo
```

- `projectsTo subPropertyOf structurallyConnectedTo`：A projectsTo B ⇒ 至少 A 与 B 存在 structural connection。

## 2. Connection structural properties

```
hasEndpointRegion
├─ hasSourceRegion
└─ hasTargetRegion
```

- `hasSourceRegion subPropertyOf hasEndpointRegion`：source 必然也是 connection endpoint。
- `hasTargetRegion subPropertyOf hasEndpointRegion`：target 必然也是 connection endpoint。
- 通过 reasoning 可从 source/target 得到 endpoint，无需人工重复维护。

## 3. 无层级关系（并列）

- effectivelyConnectedTo 与 projectsTo **不**建立 subProperty 关系（一个是 model/experimental influence，一个是 anatomical projection）。
- participatesIn 与 includesRegion 具自然逆语义，但**不**设 owl:inverseOf。
