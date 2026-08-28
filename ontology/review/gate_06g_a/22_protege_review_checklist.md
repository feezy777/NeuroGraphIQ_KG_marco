# Gate 6G-A — Protégé Review Checklist

## 人工 Protégé 检查

- [ ] Ontology IRI = https://neurographiq.org/ontology/human-brain
- [ ] Version = 0.6.2-gate6d
- [ ] Classes = 23（见 03_class_matrix）
- [ ] Object properties = 26（见 04_object_property_matrix）
- [ ] Class hierarchy：Connection→StructuralConnection→Projection / FunctionalConnectivity / EffectiveConnectivity；Function→CognitiveFunction
- [ ] Object property hierarchy：projectsTo⊑structurallyConnectedTo；hasSourceRegion/hasTargetRegion⊑hasEndpointRegion；subfieldOf⊑partOf
- [ ] participatesIn range = Circuit ∪ Function（unionOf 正确显示）
- [ ] modulates domain/range unionOf 正确显示
- [ ] 无 DataProperty / Individual / imports
- [ ] 无 supports/contradicts/qualifies/spatial relation
- [ ] 每个 Class/Property 有 en+zh label
