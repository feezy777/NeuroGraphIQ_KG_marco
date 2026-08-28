# Gate 6E-A Human Review Checklist — Evidence / Assertion Semantic Model

请逐项确认。本 Gate **仅科学语义设计**，未修改 TTL / Gate 7A / 数据库。

---

## 审查清单

- [ ] Evidence ≠ Publication
- [ ] ResearchStudy reportedIn Publication（保持）
- [ ] Publication providesEvidence Evidence（保持）
- [ ] 普通 ObjectProperty assertion 用 knowledge_assertions（DB）
- [ ] reified Connection/Circuit 直接关联 Evidence（不包 existence wrapper）
- [ ] supports/contradicts/qualifies 定位为 DB evidence_role（非 OWL ObjectProperty）
- [ ] evidence_strength / evidence_directness 属 Evidence↔Assertion 上下文
- [ ] model_confidence ≠ evidence_strength
- [ ] reported vs inferred 区分明确
- [ ] inference premise ≠ Evidence
- [ ] Connection 不双写 truth（connections + knowledge_assertions 各存一套）
- [ ] ConnectionObservation 角色明确
- [ ] Circuit Evidence 分层明确（整体/成员/connection/hasFunction）
- [ ] contradicts 不等同于"未观察到"
- [ ] external database evidence provenance 已记录（不伪装 Publication）
- [ ] RDF reification / RDF-star 不采用为 V1 canonical
- [ ] PROV-O / ECO 仅 reference
- [ ] KnowledgeAssertion 不进入 OWL core（避免 meta-modeling）
- [ ] 正式 TTL 未修改（仍 0.6.2-gate6d）
- [ ] Gate 7A 未修改
- [ ] 未新增 Class / ObjectProperty / DataProperty / Individual
- [ ] 未创建 migration / 未改数据库
- [ ] 未 commit / 未 push

---

## 关键决策点（需人工拍板）

1. **Hybrid Model**（普通 assertion → DB KnowledgeAssertion；reified entity 直接关联 Evidence）——是否同意？
2. **KnowledgeAssertion 不进 OWL core**（避免 meta-modeling）——是否同意？
3. **supports/contradicts/qualifies 保持 DB evidence_role（非 OWL 关系）**——是否同意？
4. **Connection 视作 reified proposition，直接挂 Evidence（不包 existence assertion）**——是否同意？
5. **Gate 6E-B 前需最小修订 Circuit/RegionMapping evidence link**——是否同意？

---

## 审查说明

- 若某项不通过，请在对应行标注，并在 `ontology/review/gate_06e_a/` 下追加意见。
- 全部通过后，回复 **「Gate 6E-A 通过」**，方可进入 Gate 6E-B（formalization）。
