# Gate 6E-B — Validation Report

对 `ontology/neurographiq_macro96_v1.ttl` 的验证结果（本轮不改 TTL）。

---

## 1. 元数据

| 项 | 期望 | 实际 |
|---|---|---|
| version | 0.6.2-gate6d | ✅ |
| Named Class | 23 | ✅ |
| ObjectProperty | 26 | ✅ |
| DataProperty | 0 | ✅ |
| Named Individual | 0 | ✅ |
| imports | 0 | ✅ |

## 2. OWL Evidence 内容（保持）

- [x] ResearchStudy / Publication / Evidence（Class）
- [x] reportedIn（ResearchStudy → Publication）
- [x] providesEvidence（Publication → Evidence）

## 3. 未新增（验证通过）

- [x] 无 KnowledgeAssertion / Assertion / RelationAssertion Class
- [x] 无 supports / contradicts / qualifies ObjectProperty
- [x] 无 hasSubject / hasObject / hasPredicate

## 4. 结论

**Gate 6E-B Boundary Freeze：正式 OWL 未扩展，version 保持 0.6.2-gate6d。**
