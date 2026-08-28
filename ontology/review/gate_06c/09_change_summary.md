# Gate 6C — Change Summary（BrainRegion Hierarchy Ontology）

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
version: `0.6.0-gate6b` → `0.6.1-gate6c`

---

## 1. 新增 2 个 ObjectProperty

- `partOf`（BrainRegion → BrainRegion，canonical anatomical hierarchy）。
- `subfieldOf`（BrainRegion → BrainRegion，partOf 的更具体形式）。

## 2. 新增 1 条 subPropertyOf

- `subfieldOf rdfs:subPropertyOf partOf`。

## 3. 版本/统计

| 项 | 旧 | 新 |
|---|---|---|
| version | 0.6.0-gate6b | 0.6.1-gate6c |
| ObjectProperty | 23 | 25 |
| Named Class | 23 | 23 |
| DataProperty | 0 | 0 |
| Named Individual | 0 | 0 |
| imports | 0 | 0 |

## 4. 补充 human-only comment

- BrainRegion hierarchy 实例（partOf / subfieldOf）仅限 Homo sapiens（NCBI 9606），不导入 Allen Mouse hierarchy。

## 5. 未做

- 未新增 Function hierarchy / Evidence ontology / Assertion Class / Spatial Relation / DataProperty / Individual / domain class。
- 未新增 TransitiveProperty。
- 未修改数据库 / migration / API / 前端 / Neo4j。
