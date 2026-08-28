# Gate 5A.1 — Ontology IRI / Namespace 决策

Ontology IRI（当前）: `https://neurographiq.org/ontology/macro96`
本轮状态: **仅决策文档，未修改正式 TTL（不执行 migration）**

---

## 1. 问题

项目范围已正式改变：只做人脑；知识发现从 Fine Human BrainRegion 开始；Macro96 仅是 high-level mapping / aggregation layer。因此 `macro96` 继续存在于 ontology IRI 中与实际范围不一致。

当前 ontology 尚处于 0 ObjectProperty / 0 DataProperty / 0 Individual，是修改 namespace **成本最低**的时期。

## 2. 三方案比较

| 方案 | IRI | 优点 | 缺点 |
|---|---|---|---|
| A | 保持 `.../macro96` | 兼容历史 | 未来所有 canonical entity IRI 都带 macro96，与实际 human-brain-wide 范围不一致 |
| B | `.../human-brain` | 与范围完全一致；明确 human-only；Macro96 作为 mapping layer | 需 major-scope migration（但当前风险低） |
| C | `.../core` | 名称稳定；可扩展 | 不显式表达 human-only；未来又可能范围含糊 |

## 3. 推荐：方案 B — MIGRATE

- **新 IRI:** `https://neurographiq.org/ontology/human-brain`
- **新 namespace:** `https://neurographiq.org/ontology/human-brain#`
- **Ontology name:** NeuroGraphIQ Human Brain Ontology

## 4. Gate 5B 需执行的 major-scope migration

旧 → 新：

| 旧 | 新 |
|---|---|
| `https://neurographiq.org/ontology/macro96` | `https://neurographiq.org/ontology/human-brain` |
| `https://neurographiq.org/ontology/macro96#` | `https://neurographiq.org/ontology/human-brain#` |

Gate 5B 需同步更新：Ontology IRI、prefix namespace、rdfs:label、rdfs:comment、versionInfo、所有 `ngiq:*` IRI namespace。

> 当前无 Individuals/Properties，migration 风险低（见 namespace_migration_impact.md）。

## 5. 关键澄清：human-brain namespace ≠ human species data

- `human-brain` 表示 **ontology scope**。
- 未来具体 scientific entity 仍可拥有 species/organism provenance，但当前 policy = Homo sapiens only。
- **不要**因 IRI 写 human-brain，就在 Property 层提前设计 species。

## 6. 结论

| 项 | 决策 |
|---|---|
| Ontology IRI | **MIGRATE** → `https://neurographiq.org/ontology/human-brain` |
| Namespace | `https://neurographiq.org/ontology/human-brain#` |
| 本轮是否执行 | 否（Gate 5B 执行 major-scope migration） |
