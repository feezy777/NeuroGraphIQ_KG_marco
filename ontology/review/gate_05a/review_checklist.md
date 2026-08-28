# Gate 5A Human Review Checklist — 第二轮（Final Review Candidate）

请逐项确认。本 Gate **仅产出 review 文档**，未修改正式 TTL。

---

## 审查清单（Round 2 修订）

- [ ] Human-only scope 保持
- [ ] Macro96 已明确降为 high-level mapping layer
- [ ] Domain 已拆为 neuroscience / evidence / integration / governance 模块
- [ ] 没有建立额外模块父类
- [ ] NeuralStructure 已重新审查
- [ ] 推荐 CellularNeuralStructure 命名
- [ ] NeuralProcess 已重新审查
- [ ] 推荐 NeurobiologicalProcess 命名
- [ ] BrainRegion 定义已避免 functional cluster 误分类
- [ ] Study 已改为 ResearchStudy
- [ ] ResearchStudy / Publication / Evidence 三分明确
- [ ] EvidenceType 已改为 DEFER / REMODEL
- [ ] Gate 4A Evidence 多轴模型未被推翻
- [ ] CircuitConnectionMembership 保留为 modeling concept
- [ ] ConnectionAssessment 继续 REMOVE
- [ ] ConceptDefinition 已重新审查
- [ ] 全局 TBox / ABox policy 已定义
- [ ] BrainRegion canonical concept 默认 Individual
- [ ] Gene canonical concept 默认 Individual
- [ ] Disease canonical concept 默认 Individual
- [ ] Neurotransmitter canonical concept 默认 Individual
- [ ] 外部 ontology Class 不强迫 NGIQ 复制其 class semantics
- [ ] ConnectionType OWL 表示已标记为 BLOCKER
- [ ] CircuitType 已加入 semantic modeling decision
- [ ] EvidenceType 已加入 semantic modeling decision
- [ ] Connection entity vs direct edge 已记录
- [ ] CircuitConnectionMembership reification 已记录
- [ ] 当前 ontology IRI macro96 遗留问题已记录
- [ ] Gate 2 scientific semantics 未被修改
- [ ] Gate 3 scientific semantics 未被修改
- [ ] 正式 TTL 未修改
- [ ] ObjectProperty 仍为 0
- [ ] DataProperty 仍为 0
- [ ] Individual 仍为 0
- [ ] owl:imports 仍为空
- [ ] 未 commit
- [ ] 未 push

---

## 关键决策点（需人工拍板，Round 2 更新）

1. **五模块逻辑分层**（neuroscience / evidence / integration / modeling / governance，不建父类）——是否同意？
2. **NeuralStructure → CellularNeuralStructure**（改名+收窄，避免与 BrainRegion 重叠）——是否同意？
3. **NeuralProcess → NeurobiologicalProcess**（改名，避免误解为 computation/signal processing）——是否同意？
4. **BrainRegion 定义收紧**（排除 functional cluster / network node）——是否同意？
5. **Study → ResearchStudy**——是否同意？
6. **EvidenceType → DEFER / REMODEL**（Gate 4A 多轴优先）——是否同意？
7. **CircuitConnectionMembership → KEEP AS MODELING（formalization DEFER）**——是否同意？
8. **ConnectionAssessment → REMOVE**——是否同意？
9. **ConceptDefinition → REMOVE**（推荐；定义版本化放治理数据库层）——是否同意？
10. **全局 TBox/ABox policy**（canonical concept = Individual）——是否同意？
11. **外部 ontology 不复制 Class semantics、不用 owl:equivalentClass 跨 Individual/Class**——是否同意？
12. **ConnectionType OWL 表示列为 BLOCKER，交由 Gate 5A.1 决定**（双方案 A/B）——是否同意？
13. **Gate 5A.1 通过前禁止建 ObjectProperty**——是否同意？
14. **Ontology IRI 仍含 macro96 的遗留问题已记录，本轮不改**——是否同意？

---

## 审查说明

- 若某项不通过，请在对应行标注，并在 `ontology/review/gate_05a/` 下追加意见，**不要修改正式 TTL**。
- 全部通过后，回复 **「Gate 5A 通过」**，方可进入 Gate 5A.1 或 Gate 5B。
- 未经人工明确回复「Gate 5A 通过」，禁止进入 Gate 5A.1 或 Gate 5B。
