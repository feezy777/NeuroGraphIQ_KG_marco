# Gate 6C — BrainRegion Hierarchy Relation Overview

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
version: `0.6.0-gate6b` → `0.6.1-gate6c`
本轮状态: **已正式写入 TTL，等待 Protégé 人工审查**

---

## 1. 本轮新增

只增加 2 个 ObjectProperty：

| 关系 | 中文 | 说明 |
|---|---|---|
| partOf | 属于 / 是……的一部分 | canonical anatomical hierarchy |
| subfieldOf | 亚区属于 | partOf 的更具体形式 |

## 2. Property hierarchy（新增 1 条）

```
partOf
└─ subfieldOf
```

- `subfieldOf rdfs:subPropertyOf partOf`：CA1 subfieldOf Hippocampus ⇒ CA1 partOf Hippocampus。

## 3. 完整 ObjectProperty hierarchy（Gate 6B + 6C）

```
partOf
└─ subfieldOf

structurallyConnectedTo
└─ projectsTo

hasEndpointRegion
├─ hasSourceRegion
└─ hasTargetRegion
```

其他 Gate 6B ObjectProperty 保持不变。

## 4. 明确不新增（本轮）

- 不新增 Function hierarchy relation、Evidence ontology relation、Assertion ontology Class、Spatial Relation（overlaps/locatedIn/adjacentTo）、DataProperty、Named Individual、新 domain class。
- 不新增 aggregatesTo / rollsUpTo / mapsToGranularity / granularityLevel / hasGranularity（这些属 integration/knowledge-production 语义，放 PostgreSQL integration layer）。

## 5. 不增加 TransitiveProperty

partOf / subfieldOf 均不设为 owl:TransitiveProperty。transitivity / property chains / roll-up inference 留未来 reasoning gate。

## 6. 版本与统计

| 项 | 值 |
|---|---|
| version | 0.6.1-gate6c |
| Named Class | 23 |
| ObjectProperty | 25 |
| DataProperty | 0 |
| Named Individual | 0 |
| imports | 0 |
