# Gate 6G-A — Validation Report

对 `ontology/neurographiq_macro96_v1.ttl` 的验证结果（本轮不改 TTL）。

---

## 1. 元数据

| 项 | 期望 | 实际 |
|---|---|---|
| Ontology IRI | https://neurographiq.org/ontology/human-brain | ✅ |
| version | 0.6.2-gate6d | ✅ |
| Named Class | 23 | ✅ |
| ObjectProperty | 26 | ✅ |
| DataProperty | 0 | ✅ |
| Named Individual | 0 | ✅ |
| imports | 0 | ✅ |

## 2. 结构

- subClassOf：5 ✅
- subPropertyOf：4 ✅
- owl:unionOf：3 ✅
- 无 legacy Class / production mouse / KnowledgeAssertion / supports / spatial relation / 复杂逻辑公理 ✅

## 3. TTL hash

- 前后一致：`7ccc888b3c01a0c7063203e890490ca0fc1c36feac6efbcb3c3f5962ae96cb4d`。

## 4. 结论

**Gate 6G-A 全局一致性审查通过；正式 TTL 未修改。**
