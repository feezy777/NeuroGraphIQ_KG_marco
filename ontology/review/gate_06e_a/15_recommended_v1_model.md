# Gate 6E-A — Recommended V1 Model（推荐模型）

本轮状态: **推荐方案，不写 TTL（Gate 6E-B 才 formalize）**

---

## 1. 核心推荐：Hybrid Model

| 知识类型 | Evidence 模型 |
|---|---|
| 普通 ObjectProperty assertion | KnowledgeAssertion（DB）+ assertion_evidence_links |
| Reified scientific entity（Connection/Circuit/RegionMapping） | 直接 evidence 关联（自身即 first-class knowledge object） |

- 普通 edge 需要 assertion 节点；复杂 reified fact 自身就是 knowledge object。
- evidence_role（supports/contradicts/qualifies）统一在 link 层。

## 2. 逐项回答

1. **是否新增 KnowledgeAssertion Class**：**否**（保留在 PostgreSQL 层，不进 OWL core，避免 meta-modeling）。
2. **是否新增 supports relation（OWL）**：**否**（保留为 DB evidence_role）。
3. **是否新增 contradicts（OWL）**：**否**。
4. **是否新增 qualifies（OWL）**：**否**。
5. **supports 的 Domain**：Evidence（若未来进 OWL）；当前 DB evidence_role。
6. **supports 的 Range**：Assertion OR reified entity（DB 层）。
7. **普通 assertion 挂 Evidence**：knowledge_assertions → assertion_evidence_links → evidence。
8. **Connection 挂 Evidence**：connection_observations（观测级）+ 直接 evidence link（实体级）。
9. **Circuit 挂 Evidence**：Circuit 直接 evidence link + membership/observation 层（需 Gate 6E-B 补 schema）。
10. **inferred knowledge**：derivation provenance（InferenceRecord/premise lineage），非 direct Evidence。
11. **external database evidence**：provenance = Source（registry），未来 DEFER Source→Evidence 属性。
12. **是否修改 Gate 7A**：非本轮；Gate 6E-B 前提出最小修订（统一 evidence link target）。

## 3. 概念图

普通关系：
```
Publication P1 ──providesEvidence──> Evidence E1 ──(DB evidence_role: supports)──> Assertion A1
                                                                            A1 = Hippocampus participatesIn Memory
```
（`represents` 只是概念说明，本轮**不**新增 represents ObjectProperty。）

Connection：
```
Model 1: Publication → Evidence → connection_observations → Connection
Model 2: Publication → Evidence → Connection（直接 link）
```

## 4. 为什么不进 OWL

- KnowledgeAssertion 进 OWL 需 predicate reification（hasPredicate 指向 ObjectProperty），有 OWL DL / punning 风险。
- 当前 23 Class + 26 ObjectProperty 保持轻量；Evidence/Assertion 语义由 DB 层承载（已冻结）。
- 本体层只需：reportedIn / providesEvidence（已有）+ 科学 ObjectProperty（已有）。
