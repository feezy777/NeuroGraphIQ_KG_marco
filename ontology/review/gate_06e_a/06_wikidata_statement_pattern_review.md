# Gate 6E-A — Wikidata-style Statement Pattern Review

本轮状态: **仅审查（借鉴思路），不写 TTL**

---

## 1. Wikidata statement 模式

```
entity
  → statement node（可带 qualifier / reference / rank）
     → value
```

- statement node 是实体与其值之间的"可标注的中间节点"。
- qualifier = 限定该 statement 的条件。
- reference = 该 statement 的证据来源。
- rank = 首选/普通/废弃。

## 2. 借鉴价值

NeuroGraphIQ 的 `knowledge_assertions`（DB）本质上就是这个模式：
- statement node ≈ knowledge_assertions 行（subject + predicate + object）。
- qualifier ≈ qualifiers_json / condition。
- reference ≈ assertion_evidence_links → evidence。
- rank ≈ is_primary / record_status / review_status。

## 3. 结论

**借鉴其"statement 节点 + qualifier + reference"思想，已由 DB knowledge_assertions 实现；不复制 Wikidata schema。** 无需新增 OWL 结构——该模式在数据层已充分表达，本体层保持轻量（Class + ObjectProperty + 科学语义）。
