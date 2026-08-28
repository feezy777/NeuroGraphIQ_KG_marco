# Gate 6C Human Review Checklist — BrainRegion Hierarchy Ontology

请逐项确认。本 Gate **已正式写入 TTL**（partOf / subfieldOf），等待 Protégé 审查。

---

## 审查清单

- [ ] partOf 已新增（Domain/Range = BrainRegion）
- [ ] subfieldOf 已新增（Domain/Range = BrainRegion）
- [ ] subfieldOf rdfs:subPropertyOf partOf
- [ ] partOf 不表示 overlap / atlas mapping / aggregation / functional participation
- [ ] mapsTo 保持 ExternalRegion → BrainRegion（未改）
- [ ] 未新增 BrainRegion mapsTo BrainRegion
- [ ] 未新增 aggregatesTo / rollsUpTo / mapsToGranularity
- [ ] 未新增 overlaps / locatedIn / adjacentTo
- [ ] 未新增 TransitiveProperty
- [ ] 未新增 granularity DataProperty
- [ ] 未新增 Function hierarchy / Evidence ontology / Assertion Class
- [ ] 未新增 Named Individual
- [ ] version = 0.6.1-gate6c
- [ ] Named Class = 23
- [ ] ObjectProperty = 25
- [ ] DataProperty = 0
- [ ] imports = 0
- [ ] human-only comment（Homo sapiens / NCBI 9606，不导入 Allen Mouse hierarchy）
- [ ] 未 commit
- [ ] 未 push

---

## 关键决策点（需人工拍板）

1. **新增 partOf / subfieldOf（subfieldOf ⊑ partOf）**——是否同意？
2. **aggregation mapping 不写成 partOf**（仅 DB brain_region_aggregation_mappings）——是否同意？
3. **不新增 aggregatesTo / rollsUpTo / Spatial Relation / granularity DataProperty**——是否同意？
4. **partOf/subfieldOf 不设 TransitiveProperty**——是否同意？

---

## 审查说明

- 若某项不通过，请在对应行标注，并在 `ontology/review/gate_06c/` 下追加意见。
- 全部通过后，回复 **「Gate 6C 通过」**，方可进入后续（Function hierarchy / Evidence ontology / Gate 7B migration）。
