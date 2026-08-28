# Gate 7A Human Review Checklist — Final Correction / Freeze Review

请逐项确认。本 Gate **仅产出数据字典设计**，未修改 ontology TTL / 数据库 / API / 前端 / Neo4j。

---

## 审查清单（Final Correction）

- [ ] public ID 已全部改为 8 位
- [ ] public ID NEVER REUSED
- [ ] deprecated ID 永久保留
- [ ] BrainRegion hierarchy 不含 overlaps
- [ ] BrainRegion hierarchy 不含 located_in
- [ ] hierarchy truth 使用 relation table
- [ ] parent_region_pk 仅 DERIVED CACHE
- [ ] parent_function_pk 仅 DERIVED CACHE
- [ ] function subclass_of 与 part_of 不混用
- [ ] kg_entities 是唯一 identity truth
- [ ] subtype tables 不维护独立 name truth
- [ ] subtype tables 不维护独立 definition truth
- [ ] *_pk = internal key
- [ ] *_id = public ID
- [ ] 所有 FK 使用 *_pk
- [ ] shared-PK entity/subtype 方案已明确
- [ ] ACTIVE first-class entity 必须具备中英文名
- [ ] PROPOSED 可以暂缺一种语言
- [ ] translation source 被记录
- [ ] technical link rows 不强制造双语名
- [ ] Evidence 定义为证据内容
- [ ] ConnectionObservation 定义为 study-level observation
- [ ] AssertionEvidenceLink 定义为 assertion-specific evidence relation
- [ ] evidence_strength 的 canonical context 已明确
- [ ] evidence_directness 的 canonical context 已明确
- [ ] model_confidence ≠ evidence_strength
- [ ] Governance 审核历史不放 scientific schema
- [ ] review status 仅可作为 snapshot
- [ ] Scientific Source 与 Provenance Agent 分开
- [ ] source_type 不使用 llm 作为科学来源
- [ ] DeepSeek/GPT 不会成为 scientific evidence source
- [ ] reciprocal Projection 使用两条 directed Connection
- [ ] reciprocal 仅作为 derived summary
- [ ] derived count 字段已标记 DERIVED
- [ ] controlled vocab 不全部锁成 ENUM
- [ ] 表总数仍为 32
- [ ] 正式 ontology TTL 未修改
- [ ] 未创建 migration
- [ ] 未修改数据库
- [ ] 未 commit
- [ ] 未 push

---

## 关键决策点（需人工拍板）

1. **public ID 升级为 8 位，永不复用**——是否同意？
2. **kg_entities = 唯一 identity truth，subtype 去双写 name/definition**——是否同意？
3. **shared-PK（Class Table Inheritance）**——是否同意？
4. **`*_pk` 内部主键 / `*_id` public ID，FK 引用 `*_pk`**——是否同意？
5. **Evidence 三层职责 + strength/directness 移到 AssertionEvidenceLink**——是否同意？
6. **Governance 审核历史移出 scientific schema（仅留 status snapshot）**——是否同意？
7. **Scientific Source ≠ Provenance Agent，source_type 删 llm**——是否同意？
8. **reciprocal Projection = 两条 directed Connection（reciprocal 为 derived）**——是否同意？

---

## 审查说明

- 若某项不通过，请在对应行标注，并在 `ontology/review/gate_07a_data_dictionary/` 下追加意见。
- 全部通过后，回复 **「Gate 7A 冻结」**，方可进入 Gate 7B（migration 实施）。
