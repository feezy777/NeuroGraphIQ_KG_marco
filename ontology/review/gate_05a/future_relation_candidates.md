# Gate 5A — Future Relation Candidates（未来关系候选，本轮不建）

Ontology IRI: `https://neurographiq.org/ontology/macro96`
本轮状态: **仅记录，禁止写入 TTL / 创建 ObjectProperty**

本 Gate **不设计、不创建任何 ObjectProperty / DataProperty**。以下仅记录老师 PPT 提及 + 本轮识别出的未来关系候选，供后续 Property / Semantic Modeling Gate 评审。

---

## 1. 老师 PPT 提及的关系（候选）

| 候选关系 | 中文 | 潜在 domain → range | 备注 |
|---|---|---|---|
| STRUCTURALLY_CONNECTED_TO | 结构连接 | BrainRegion → BrainRegion | 与 Connection entity model 是否重复待审 |
| FUNCTIONALLY_CONNECTED_TO | 功能连接 | BrainRegion → BrainRegion | 同上 |
| PROJECTS_TO | 投射到 | BrainRegion → BrainRegion | 同上（对应 Projection） |
| PARTICIPATES_IN | 参与 | BrainRegion → Circuit / Function | 归属待审 |
| MODULATES | 调节 | 多 → 多 | 待审 |
| INCREASES_RISK_OF | 增加风险 | Gene → Disease | 待审 |

---

## 2. 本轮新识别的关系候选（非 PPT 直接列出）

| 候选关系 | 中文 | 潜在 domain → range |
|---|---|---|
| has_symptom | 表现症状 | Disease → Symptom |
| expresses | 表达 | Gene → 产物（DEFER） |
| acts_on | 作用于 | Neurotransmitter → Receptor |
| has_type | 类型 | Connection → ConnectionType |
| reported_in | 报道于 | ResearchStudy → Publication |
| provides / contains | 提供/包含 | Publication → Evidence |
| supports / contradicts | 支持/反驳 | Evidence → Assertion |
| maps_to | 映射到 | ExternalRegion → BrainRegion |

---

## 3. 关键待审问题（本轮禁止提前决定）

### 3.1 Connection entity vs direct graph edge

- 当前采用 **Connection entity model**（BrainRegion → Connection → BrainRegion）。
- PPT 用直接关系（BrainRegion STRUCTURALLY_CONNECTED_TO BrainRegion）。
- **两者是否重复建模？** 是否未来同时保留，还是二选一，或 entity 为主 + 关系为快捷推导？
- **本轮禁止决定**，记入 `modeling_issues.md`。

### 3.2 属性是否引入 direction / weight / confidence

- 若建 `STRUCTURALLY_CONNECTED_TO`，方向（directed/reciprocal/unknown）如何表达？
- 是否与 ConnectionType（StructuralConnection → Projection）重叠？
- 留 Property Gate。

---

## 4. 纪律

- 本轮**不创建**任何 ObjectProperty / DataProperty / AnnotationProperty。
- 不写 SHACL / property chain / Restriction。
- 上述候选仅为未来评审清单，**不代表任何建模决定**。
