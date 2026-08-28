# Gate 6G-A — Ontology Baseline（实际解析结果）

TTL: `ontology/neurographiq_macro96_v1.ttl`
sha256: `7ccc888b3c01a0c7063203e890490ca0fc1c36feac6efbcb3c3f5962ae96cb4d`

---

## 1. 元数据（实际解析）

| 项 | 值 |
|---|---|
| Ontology IRI | https://neurographiq.org/ontology/human-brain |
| version | 0.6.2-gate6d |
| Named Class | 23 |
| ObjectProperty | 26 |
| DataProperty | 0 |
| Named Individual | 0 |
| imports | 0 |

## 2. 结构（实际解析）

- subClassOf：5（StructuralConnection→Connection、Projection→StructuralConnection、FunctionalConnectivity→Connection、EffectiveConnectivity→Connection、CognitiveFunction→Function）
- subPropertyOf：4（projectsTo⊑structurallyConnectedTo、hasSourceRegion⊑hasEndpointRegion、hasTargetRegion⊑hasEndpointRegion、subfieldOf⊑partOf）
- owl:unionOf：3（participatesIn range=Circuit∪Function；modulates domain=Gene∪Neurotransmitter；modulates range=BrainRegion∪Circuit∪Function）

## 3. 结论

基线与冻结清单完全一致，无漂移。
