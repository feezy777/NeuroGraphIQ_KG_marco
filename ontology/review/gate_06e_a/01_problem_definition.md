# Gate 6E-A — Problem Definition

Ontology IRI: `https://neurographiq.org/ontology/human-brain`（version 0.6.2-gate6d，本轮不改）
本轮状态: **仅科学语义设计与建模审查，不写 TTL**

---

## 1. 核心问题

当前 ontology 能表达 `Publication providesEvidence Evidence`，但**无法回答"Evidence 到底支持哪条知识"**。

Evidence E001 可能支持：
- Hippocampus participatesIn Memory（普通 ObjectProperty assertion）
- APOE increasesRiskOf AlzheimerDisease（普通 assertion）
- Connection CON-001（reified entity）
- Circuit CIR-001（reified entity）

## 2. 两种知识表达必须区分

| 类型 | 例子 | 表达 |
|---|---|---|
| A. 普通 relation assertion | Hippocampus participatesIn Memory | ObjectProperty |
| B. Reified scientific entity | Connection / Circuit / RegionMapping | 已是实体 |

- Connection 是 canonical reified entity；不能把 `A projectsTo B` 既存 Connection truth 又存另一份独立 assertion truth。

## 3. 本轮要解决的 8 个问题

1. Evidence 支持什么对象？
2. 普通 ObjectProperty assertion 如何挂 Evidence？
3. Connection/Circuit reified entity 如何挂 Evidence？
4. Publication/ResearchStudy/Evidence/Assertion 如何串起来？
5. supports/contradicts/qualifies 是本体关系还是 DB evidence-role？
6. KnowledgeAssertion 是否进入核心 OWL ontology？
7. 若进入，如何避免破坏 OWL DL / TBox-ABox？
8. 如何与已冻结的 PostgreSQL assertion model 对齐？

## 4. 冻结基线

- version 0.6.2-gate6d、23 Class、26 ObjectProperty、0 DataProperty、0 Individual、0 imports。
- reportedIn（ResearchStudy → Publication）、providesEvidence（Publication → Evidence）已冻结，本轮不修改。
- Gate 7A 的 knowledge_assertions / relation_definitions / assertion_evidence_links 已冻结为 DB baseline。
