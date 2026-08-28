# Gate 6D Human Review Checklist — Function Hierarchy Ontology

请逐项确认。本 Gate **已正式写入 TTL**（subFunctionOf），等待 Protégé 审查。

---

## 审查清单

- [ ] subFunctionOf 已新增（Domain/Range = Function）
- [ ] subFunctionOf 未使用 rdfs:subClassOf 表达具体 Function hierarchy
- [ ] 未复用 BrainRegion partOf 于 Function
- [ ] partOf Domain/Range 未被修改（仍 BrainRegion → BrainRegion）
- [ ] subFunctionOf 未 subPropertyOf partOf
- [ ] 未新增 functionPartOf / partOfFunction / componentFunctionOf / hasFunctionalComponent
- [ ] 未新增 hasSubFunction
- [ ] 未设置 TransitiveProperty
- [ ] 未设置 inverseOf
- [ ] 未设置 property chain
- [ ] CognitiveFunction rdfs:subClassOf Function 保持不变
- [ ] Function 与 NeurobiologicalProcess 保持区分
- [ ] 未新增 Function Individual（WorkingMemory/Memory 等）
- [ ] version = 0.6.2-gate6d
- [ ] Named Class = 23
- [ ] ObjectProperty = 26
- [ ] DataProperty = 0
- [ ] Named Individual = 0
- [ ] imports = 0
- [ ] 未修改 Gate 7A Data Dictionary
- [ ] 未修改数据库
- [ ] 未 commit / 未 push（Gate 6D 本体变更）

---

## 关键决策点（需人工拍板）

1. **subFunctionOf（Function → Function，ABox semantic hierarchy）**——是否同意？
2. **不复用 partOf，不新增 Function part_of 正式 OWL relation（DEFER）**——是否同意？
3. **不设 TransitiveProperty / inverseOf / property chain**——是否同意？

---

## 审查说明

- 若某项不通过，请在对应行标注，并在 `ontology/review/gate_06d/` 下追加意见。
- 全部通过后，回复 **「Gate 6D 通过」**，方可进入后续（Function–Process / Evidence ontology）。
