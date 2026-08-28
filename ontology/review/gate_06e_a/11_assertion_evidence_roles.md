# Gate 6E-A — Assertion Evidence Roles（supports / contradicts / qualifies）

本轮状态: **仅设计，不写 TTL**

---

## 1. 语义（epistemic role）

| role | 语义 |
|---|---|
| supports | Evidence 支持该 Assertion 为真 |
| contradicts | Evidence 与该 Assertion 冲突/反驳 |
| qualifies | Evidence 限定该 Assertion 成立的条件/范围 |

- 三者描述 Evidence 对一个 Assertion 的 epistemic role，**不是** Publication 对实体的普通关系。
- 例：`Evidence E001 supports Assertion A001`，不是 `Evidence E001 supports Hippocampus`。

## 2. 是否 OWL ObjectProperty 还是 DB evidence_role

**推荐：DB evidence_role（assertion_evidence_links.evidence_role），不进 OWL。**
- 因为 supports/contradicts/qualifies 的目标是 Assertion（DB 层），不是本体实体。
- 进 OWL 需 KnowledgeAssertion Class（meta-modeling 风险）。

## 3. qualifies 的必要性

保留 qualifies（很多 Evidence 是条件性的，非简单支持/反驳）：
- A-B FunctionalConnectivity 只在 task X / age Y / disease Z 成立 → qualifies。

不合并成 "supports + qualifier"（语义更清晰为独立 role）。

## 4. strength / directness 依赖 Assertion context

- evidence_strength / evidence_directness 属 Evidence ↔ Assertion 关系上下文（同一 Evidence 对不同 Assertion 可不同）。
- 存 assertion_evidence_links（不是 Evidence 本体）。

## 5. contradicts 边界

- contradicts 需"明确冲突发现"，禁止"未观察到"自动等于 contradicts。
