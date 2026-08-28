# Gate 6A — Evidence / Provenance Relations · 第二轮修订

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
本轮状态: **仅设计文档，未修改正式 TTL**

---

## 1. 研究/文献/证据基础链（保留）

```
ResearchStudy ──reportedIn──> Publication ──providesEvidence──> Evidence
```

| 关系 | Domain | Range | 方向 | Role |
|---|---|---|---|---|
| reportedIn | ResearchStudy | Publication | Directed | Canonical |
| providesEvidence | Publication | Evidence | Directed | Canonical |

> 这两个基础 provenance relation 目前没有 assertion-level 问题，继续作为 V1 Relation Candidate。

## 2. SUPPORTS / CONTRADICTS —— 语义保留，formalization DEFER

第一轮把 Evidence → supports → Connection/Circuit 直接作为 canonical relation，存在建模缺口：

- Evidence 未来不仅支持 Connection/Circuit，还需支持普通 ObjectProperty assertion，例如：
  - Gene INCREASES_RISK_OF Disease
  - Disease HAS_SYMPTOM Symptom
  - Neurotransmitter ACTS_ON Receptor
  - BrainRegion PARTICIPATES_IN Function
  - RegionMapping 等。

若 SUPPORTS Range 只写 Connection/Circuit，则无法覆盖普通 ObjectProperty assertion。

**因此：**

| 关系 | 状态 |
|---|---|
| SUPPORTS | KEEP SEMANTICS / FORMALIZATION DEFER |
| CONTRADICTS | KEEP SEMANTICS / FORMALIZATION DEFER |

- 科学语义保留（证据可支持/反驳断言）。
- 但不作为当前 V1 可直接正式写入 ObjectProperty 的状态。

## 3. Evidence–Assertion 建模问题（记录，不解决）

未来必须解决：Evidence 如何关联「一条具体知识断言」。

候选方向：

- **A**：`Evidence supports Assertion / RelationAssertion`（需新增 Assertion 类）。
- **B**：PostgreSQL relation assertion / evidence attachment record。
- **C**：对已 reified 的实体（Connection / Circuit / RegionMapping）直接关联 Evidence；但普通 direct ObjectProperty assertion 仍需 assertion-level evidence model。

**本轮禁止新增**：Assertion / RelationAssertion / Statement / EdgeAssertion 等 Class。

留 **Future Evidence / Assertion Formalization Gate**。

## 4. 边界

- Evidence 不是 Publication（Evidence 是具体证据单元）。
- reportedIn / providesEvidence 保留；supports / contradicts 暂缓正式化。
