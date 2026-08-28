# Gate 5A — Current Ontology Audit（当前正式 TTL 实际状态）

审计对象: `ontology/neurographiq_macro96_v1.ttl`（194 行）
审计时间: 2026-08-28
审计方式: 只读，未修改

---

## 1. 基本元数据

| 项 | 值 |
|---|---|
| ontology version | `0.3.0-gate3b` |
| Ontology IRI | `https://neurographiq.org/ontology/macro96` |
| Namespace | `https://neurographiq.org/ontology/macro96#`（prefix `ngiq:` / `:`） |
| Status | draft — for human review in Protégé |
| 前缀 | `owl:` `rdf:` `rdfs:` `xsd:` |
| 文件行数 | 194 |

## 2. Class 总数

**28** = 24 个顶层 Class（owl:Thing 直接子类）+ 4 个 ConnectionType 子类。

## 3. 顶层 Class（owl:Thing 直接子类，共 24）

按逻辑层预分组（分组本身是本轮 review 建议，非 TTL 现状）：

### Domain（12）
1. BrainRegion
2. Function
3. Connection
4. ConnectionType
5. Circuit
6. CircuitType
7. Publication
8. Evidence
9. EvidenceType
10. Atlas
11. ExternalRegion
12. RegionMapping

### Reification / Modeling（1）
13. CircuitConnectionMembership

### Governance / Knowledge Production（11）
14. ConnectionAssessment
15. ConnectionCandidate
16. CircuitCandidate
17. EvidenceCandidate
18. SearchRun
19. ExtractionRun
20. ModelReview
21. HumanReview
22. InferenceRecord
23. ValidationRecord
24. ConceptDefinition

## 4. ConnectionType hierarchy（Gate 2B 冻结，4 类）

```
ConnectionType
├─ StructuralConnection
│  └─ Projection
├─ FunctionalConnectivity
└─ EffectiveConnectivity
```

- 无 AssociationConnection / Coactivation / LocalAnatomicalConnection / UncertainConnection（已排除，Gate 2A）。
- 本轮**不改变**该结构。

## 5. Circuit / CircuitType 状态

- **Circuit**：存在（Gate 3B 科学定义已写入 rdfs:comment；未新增子类）。
- **CircuitType**：reserved extension point——无子类、无 individual、非 owl:Nothing、无逻辑公理定义空类。
- 未新增 LoopCircuit / FeedforwardCircuit / FeedbackCircuit / RecurrentCircuit 等（Gate 3 已裁定）。

## 6. Evidence / EvidenceType 状态

- **Evidence**：存在（TTL 中定义仍为 Gate 1 原始版；Gate 4A 已审查其多轴语义，未回写 TTL）。
- **EvidenceType**：存在，**无子类**（comment 注明 hierarchy 留待后续 Gate）。

## 7. ObjectProperty 数：**0**

## 8. DataProperty 数：**0**

## 9. Individual 数：**0**

## 10. owl:imports：**无**（注释明确 "must remain empty"）

## 11. 自定义 AnnotationProperty：**0**（仅使用 `rdfs:label` / `rdfs:comment`）

## 12. Gate 4A review 是否已存在：**是**

`ontology/review/gate_04a/`（11 个文件）：
assertion_type_definition_cards.md、assertion_type_proposal.md、evidence_assertion_boundary_matrix.md、evidence_definition.md、evidence_dimensions.md、evidence_type_definition_cards.md、evidence_type_taxonomy_proposal.md、excluded_or_remodeled_terms.md、references.md、review_checklist.md、worked_examples.md

## 13. 当前是否存在未提交修改：**是**

- `M .claude/settings.local.json`
- untracked 文件若干（含 `ontology/review/gate_04a/`、`backend/_*.py`、`frontend/*.mjs` 等）。
- 正式 TTL `ontology/neurographiq_macro96_v1.ttl` **未被修改**（见 `git diff` 验证）。

## 14. git 状态快照

- 当前分支: `main`（与 `origin/main` 同步）。
- 最近 8 条提交均为 Macro96 本体/基线相关，最新 `3775c00 建立Macro96神经回路正式本体语义`。

---

> 说明：以上仅记录现状。本 Gate 的**推荐变更**见 `domain_class_proposal.md` / `governance_class_review.md`，**均未写入 TTL**。
>
> **Round 2 注（2026-08-28）**：正式 TTL 仍未改动（version 仍 `0.3.0-gate3b`、28 Class、0 Property、0 Individual、0 imports）。Round 2 修订为：类命名（CellularNeuralStructure / NeurobiologicalProcess / ResearchStudy）、五模块分层、EvidenceType→DEFER/REMODEL、ConceptDefinition/ConnectionAssessment→REMOVE、ConnectionType OWL 表示→BLOCKER（Gate 5A.1）。详见 `gate_05a_revision_summary.md`。
