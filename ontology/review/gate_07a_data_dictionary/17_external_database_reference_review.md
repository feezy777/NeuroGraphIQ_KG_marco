# Gate 7A — External Database / Knowledge Base Reference Review（外部资源字段设计借鉴）

本轮状态: **仅设计文档**

> 借鉴成熟资源的设计思路，不整套复制别人 schema。命名空间/稳定 ID 引用沿用 Gate 5A 已核实的来源；字段设计借鉴为概念层面，不逐条复制。

---

## 1. 借鉴的资源与思路

| 资源 | 借鉴思路 |
|---|---|
| Wikidata | multilingual labels、aliases、statements + qualifiers + references 结构（→ kg_entities + aliases + knowledge_assertions + qualifiers_json + evidence link） |
| MONDO / OBO | stable identifiers、synonyms、xrefs、mappings（→ entity_aliases + entity_xrefs + region_mappings） |
| Allen Brain Atlas | structure id、acronym、parent、hierarchy path、display order（→ brain_regions 的 abbreviation/parent/hierarchy_depth/display_order） |
| EBRAINS / siibra | atlas/parcellation、version、reference space、maps（→ atlases + brain_region_spatial_representations） |
| HGNC | 稳定 ID、approved symbol/name、previous symbols、aliases、external IDs（→ genes + entity_aliases + entity_xrefs） |
| NCBI Gene | GeneID、symbol、description、chromosome/location（→ genes） |
| IUPHAR/GtoPdb | receptor/target、family、gene、external identifiers（→ receptors） |
| ChEBI | chemical ID、names、formula、mass（→ neurotransmitters） |
| MONDO/HPO | disease/phenotype IDs、labels、synonyms、xrefs（→ diseases/symptoms） |
| PubMed / Europe PMC | PMID、PMCID、DOI、title、abstract、authors、journal、date、publication type、MeSH、full-text（→ publications） |

## 2. 引用纪律

- 命名空间/稳定 ID（HGNC、MONDO、ChEBI、IUPHAR、Uberon、HPO、GO、DO 等）沿用 Gate 5A `references.md` 已核实来源。
- 字段设计为**概念借鉴**，不复制外部 schema 的精确列名/约束。
- 未编造字段或 ID。

## 3. 原则：不要机械追求字段数量

- 判断标准：科学意义稳定、跨来源常见、需查询/筛选、前端常展示、后续验证/推理需要 → 正式列。
- 来源高度特异、低频、结构不稳定 → metadata_json。
- 不设计不可维护的 300 列超级表。
