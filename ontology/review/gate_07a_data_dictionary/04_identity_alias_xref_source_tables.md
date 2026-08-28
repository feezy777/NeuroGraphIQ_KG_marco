# Gate 7A — Identity / Alias / Xref / Source Tables

本轮状态: **仅设计文档**

---

## 1. kg_entities

统一 canonical entity identity layer（字段见 03_common_entity_fields.md）。`entity_type` 取值与各 subtype 表一一对应，需保持一致（风险见 open_questions）。

## 2. entity_aliases（别名）

| 字段 | 说明 |
|---|---|
| alias_pk | 内部主键 |
| alias_id | NGIQ-ALIAS-… |
| entity_id | 指向 kg_entities |
| alias_text | 别名文本 |
| language | 语言 |
| alias_type | exact / abbreviation / historical / atlas_label / previous_name / narrow / broad / related |
| source_id | 来源 |
| source_record_id | 来源记录 ID |
| is_preferred | 是否首选 |
| created_at | 时间戳 |
| remark | 备注 |

> alias ≠ new canonical entity。参考 OBO synonym scope 思路。

## 3. entity_xrefs（外部 ID 映射）

| 字段 | 说明 |
|---|---|
| xref_pk | 内部主键 |
| xref_id | NGIQ-XREF-… |
| entity_id | 指向 kg_entities |
| source_database | 来源数据库（HGNC / MONDO / ChEBI …） |
| external_id | 外部 ID |
| external_uri | 外部 URI |
| match_type | exact / close / broader / narrower / related / unresolved |
| is_primary | 是否主映射 |
| source_version | 来源版本 |
| retrieved_at | 抓取时间 |
| remark | 备注 |

> 不在各实体表无限加 `uberon_id / mondo_id / chebi_id / hgnc_id …`。若某 external ID 特别核心且高频展示，可在扩展表保留缓存字段，但 xrefs 表仍是统一外部映射层。

## 4. sources（来源注册表）

| 字段 | 说明 |
|---|---|
| source_pk | 内部主键 |
| source_id | NGIQ-SRC-… |
| name_en / name_zh | 名称 |
| abbreviation | 缩写 |
| source_type | atlas / database / ontology / publication_database / literature / manual / import_pipeline |
| provider | 提供方 |
| version | 版本 |
| species_scope | 物种范围 |
| url / api_url | 链接 |
| license | 许可证 |
| citation_text | 引用文本 |
| description_en / description_zh | 描述 |
| last_checked_at | 最后核对时间 |
| record_status | 状态 |
| remark | 备注 |

典型来源：Julich-Brain、Brainnetome、HCP、PubMed、Europe PMC、HGNC、MONDO、ChEBI、IUPHAR。

## 5. Scientific Source ≠ Provenance Agent（Final Correction）

- **Scientific Source**（进入 sources）= 知识/数据真正来自哪里：Julich-Brain、Brainnetome、HCP、PubMed、Europe PMC、HGNC、MONDO、HPO、ChEBI、IUPHAR、具体 Publication。
- **Provenance Agent**（不进入 sources）= DeepSeek / GPT / BioSEPBERT / Human curator / ImportPipeline / RuleEngine，表示谁抽取/翻译/归一化/审核/推理。
- `sources.source_type` **不使用 `llm`**。
- **LLM 不得作为 Evidence scientific source**：Evidence 记 publication=PMID，extraction agent=DeepSeek，二者分离。
