# Gate 5A.1 Human Review Checklist — Core Semantic Modeling Decision

请逐项确认。本 Gate **仅产出决策文档**，未修改正式 TTL。

---

## 审查清单

- [ ] ConnectionType 推荐 REMOVE（subtype model）已明确
- [ ] Connection hierarchy（StructuralConnection→Projection / Functional / Effective）合理
- [ ] connection_type 字段与 OWL Class 解耦原则已明确
- [ ] CircuitType 推荐 REMOVE from V1 已明确
- [ ] Circuit topology 由 future properties 表达已记录
- [ ] EvidenceType 推荐 REMOVE from V1 已明确
- [ ] Evidence multi-axis model 未被推翻
- [ ] Ontology IRI 推荐 MIGRATE human-brain 已明确
- [ ] namespace migration 影响面已分析
- [ ] 无硬编码 IRI 风险已确认（代码层 0 命中）
- [ ] Governance 推荐 database-first 已明确
- [ ] Governance 不进入 core ontology 已明确
- [ ] ResearchStudy / Publication / Evidence 保留在 scientific ontology
- [ ] Atlas / ExternalRegion / RegionMapping 保留在 Human Brain ontology
- [ ] Connection canonical = reified entity 已明确
- [ ] Neo4j direct edge = derived projection only 已明确
- [ ] TBox / ABox policy 保持（canonical concept = Individual）
- [ ] Gate 2 科学语义未改变
- [ ] Gate 3 科学语义未改变
- [ ] Gate 4A 科学语义未改变
- [ ] future target hierarchy 已输出（23 类）
- [ ] 正式 TTL 未修改
- [ ] ObjectProperty 仍为 0
- [ ] DataProperty 仍为 0
- [ ] Individual 仍为 0
- [ ] owl:imports 仍为空
- [ ] 未 commit
- [ ] 未 push

---

## 关键决策点（需人工拍板）

1. **ConnectionType → REMOVE，采用 Connection subtype model（方案 A）**——是否同意？
2. **CircuitType → REMOVE from V1**——是否同意？
3. **EvidenceType → REMOVE from V1，multi-axis model**——是否同意？
4. **Ontology IRI → MIGRATE human-brain**（Gate 5B 执行）——是否同意？
5. **Governance → database-first，移出 core ontology**——是否同意？
6. **Connection canonical = reified entity，Neo4j direct edge 仅投影**——是否同意？
7. **connection_type DB 字段保留、映射到 rdf:type（≠ OWL Class）**——是否同意？

---

## 审查说明

- 若某项不通过，请在对应行标注，并在 `ontology/review/gate_05a1/` 下追加意见，**不要修改正式 TTL**。
- 全部通过后，回复 **「Gate 5A.1 通过」**，方可进入 Gate 5B。
- 未经人工明确回复「Gate 5A.1 通过」，禁止进入 Gate 5B。
