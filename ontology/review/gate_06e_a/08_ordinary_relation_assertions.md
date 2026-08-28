# Gate 6E-A — Ordinary Relation Assertions（普通关系断言）

本轮状态: **仅设计，不写 TTL**

---

## 1. 模型

普通 ObjectProperty assertion（participatesIn / increasesRiskOf / hasSymptom / actsOn / hasFunction 等）用 DB `knowledge_assertions` 表达：

```
Hippocampus participatesIn Memory
  → knowledge_assertions（subject=Hippocampus, predicate=participatesIn, object=Memory）
  → assertion_evidence_links（evidence_role=supports/contradicts/qualifies）
     → evidence
```

## 2. 每条 assertion 的 Evidence

每一条具体 assertion 拥有：
- 0..N supports evidence
- 0..N contradicts evidence
- 0..N qualifying evidence

## 3. 示例验证

| assertion | Evidence 来源 |
|---|---|
| Hippocampus participatesIn Memory | Publication P1 某研究结果 |
| APOE increasesRiskOf AlzheimerDisease | Publication P2 |
| Dopamine actsOn D2Receptor | database / publication |
| Disease hasSymptom Symptom | clinical literature |

## 4. 关键点

- supports/contradicts/qualifies 是 **DB evidence_role**，不是 OWL ObjectProperty。
- assertion 本体不在 OWL 中（避免 meta-modeling）；本体层只保留 ObjectProperty（participatesIn 等）+ reportedIn/providesEvidence。
