# Gate 5A — Governance / Knowledge Production Class Review（治理层逐项审查）· 第二轮修订

Ontology IRI: `https://neurographiq.org/ontology/macro96`
本轮状态: **仅方案，未写入正式 TTL**

核心原则：这些类**不代表真实人脑中的生物学实体**，而是 knowledge production / workflow / review / inference / validation / governance。本轮只做逻辑分组，**不在 OWL 新建父类**。

裁定符号：**KEEP AS GOVERNANCE** / **REMODEL** / **DEFER** / **REMOVE** / **KEEP AS MODELING**。

---

## 1. 裁定总表

| # | Class | 中文 | 裁定 | 理由 |
|---|---|---|---|---|
| 1 | ConnectionCandidate | 连接候选 | **KEEP AS GOVERNANCE** | 工作流候选实体 |
| 2 | CircuitCandidate | 回路候选 | **KEEP AS GOVERNANCE** | 工作流候选实体 |
| 3 | EvidenceCandidate | 证据候选 | **KEEP AS GOVERNANCE** | 工作流候选实体（Gate 4A：≠ Evidence） |
| 4 | SearchRun | 检索运行 | **KEEP AS GOVERNANCE** | workflow |
| 5 | ExtractionRun | 抽取运行 | **KEEP AS GOVERNANCE** | workflow |
| 6 | ModelReview | 模型审核 | **KEEP AS GOVERNANCE** | review |
| 7 | HumanReview | 人工审核 | **KEEP AS GOVERNANCE** | review |
| 8 | InferenceRecord | 推断记录 | **KEEP AS GOVERNANCE** | governance |
| 9 | ValidationRecord | 验证记录 | **KEEP AS GOVERNANCE** | governance |
| 10 | ConceptDefinition | 概念定义 | **REMOVE**（推荐） | 见 §2.10 |
| 11 | ConnectionAssessment | 连接评估 | **REMOVE** | 旧 9,120 pair 路线废弃（见 §2.11） |
| 12 | CircuitConnectionMembership | 回路连接成员关系 | **KEEP AS MODELING（formalization DEFER）** | reification（见 §2.12） |

---

## 2. 逐项审查

### 2.1–2.3 ConnectionCandidate / CircuitCandidate / EvidenceCandidate — KEEP AS GOVERNANCE

- 工作流候选实体（lifecycle_status=candidate 载体，Gate 4A）。
- 非生物学实体，不放入 Domain。

### 2.4–2.5 SearchRun / ExtractionRun — KEEP AS GOVERNANCE（workflow）

- 文献检索 / LLM 抽取运行记录；provenance / workflow 实体。

### 2.6–2.7 ModelReview / HumanReview — KEEP AS GOVERNANCE（review）

- 自动模型审核 / 人工审核记录。Gate 4A：ModelReview approved ≠ HumanReview approved ≠ 自动晋升。

### 2.8–2.9 InferenceRecord / ValidationRecord — KEEP AS GOVERNANCE

- 推断记录（roll-up / graph inference）、验证决定/规则检查记录。

### 2.10 ConceptDefinition — REMOVE（推荐）

- **问题：** 正式 ontology concept 的 definition / label / comment 本身可用 `rdfs:comment` / SKOS definition / annotation / versioned metadata 表达，不必建模为运行时一等 OWL Class。
- **两方案评估：**
  - A. **REMOVE**：若它只是重复本体 annotation → 删除。
  - B. **KEEP AS GOVERNANCE**：若未来需版本化定义记录（definition_version / review history / definition source / human approval）→ 保留为治理记录。
- **推荐结论：REMOVE（从正式本体）**。理由：
  1. 当前与近期生产**没有**需要实例化 ConceptDefinition 的需求；
  2. 定义版本化/审核历史若将来需要，属**治理数据库层**的元数据记录（≈ ValidationRecord 邻接的表），而非描述"人脑/证据世界"的本体 Class；
  3. "不要因为旧系统存在就保留"——概念定义用 annotation 表达即可。
- 若未来确需版本化定义审批，可在**治理数据库层**实现，不必占用本体 TBox。

### 2.11 ConnectionAssessment — REMOVE（确认）

- 服务于旧路线：Macro96 96×95 = 9,120 directed pair systematic assessment。
- 新路线：Fine Human BrainRegion → Circuit Discovery → Circuit normalization → Circuit-driven discovery → normalization → ontology mapping。
- **REMOVE FROM FUTURE FORMAL ONTOLOGY**。
- 后续 targeted search 由 SearchRun + ConnectionCandidate + ValidationRecord 表达。
- 本轮不修改 TTL。

### 2.12 CircuitConnectionMembership — KEEP AS MODELING / REIFICATION（formalization DEFER）

- 未来一个 Connection 可同时属于多个 Circuit，且在不同 Circuit 中可具有：step_order / role / entry-exit position / membership evidence / membership confidence / local topology context。
- 这些属于 **Circuit × Connection membership**，不是 Connection 本身。
- 例：Connection C001 在 Circuit A step_order=2，在 Circuit B step_order=5。
- **因此 CircuitConnectionMembership 很可能是必要的 reification entity。**
- **裁定：KEEP 概念；formalization DEFER**（禁止本轮建属性/约束）。
- 归属：Modeling / Reification 模块。

---

## 3. 逻辑分组（不建父类）

```
[Knowledge Production / Governance —— 逻辑分组]
├─ Workflow:      SearchRun, ExtractionRun, *Candidate (Connection/Circuit/Evidence)
├─ Review:        ModelReview, HumanReview
├─ Governance:    InferenceRecord, ValidationRecord
├─ Modeling:      CircuitConnectionMembership  (KEEP concept, formalization DEFER)
├─ REMOVE:        ConceptDefinition, ConnectionAssessment
```

---

## 4. 关键边界提醒

- DomainEntity ≠ GovernanceEntity（是否建父类留后续 Gate）。
- reported ≠ inferred；candidate ≠ hypothesis；review_status ≠ derivation_type（Gate 4A）。
- 治理类不参与脑区/回路/连接科学语义，只记录"谁、何时、经何流程、如何判定"。
