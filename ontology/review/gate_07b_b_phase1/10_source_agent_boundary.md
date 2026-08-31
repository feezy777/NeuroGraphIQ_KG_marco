# Gate 7B-B Phase 1 — Source / Agent Boundary

## 1. 冻结边界（§K + 04 §5）

| 类别 | 含义 | 进入 sources？ |
|---|---|---|
| **Scientific Source** | 知识/数据真正来源：Julich-Brain、Brainnetome、HCP、PubMed、Europe PMC、HGNC、MONDO、HPO、ChEBI、IUPHAR、具体 Publication | ✅ |
| **Provenance Agent** | 谁抽取/翻译/归一化/审核/推理：DeepSeek、GPT、BioSEPBERT、Human curator、ImportPipeline、RuleEngine | ❌ |

## 2. 实现

- `sources.source_type` 词表 **不含 `llm`**：atlas/database/ontology/publication_database/literature/manual/import_pipeline（7 值）。
- 测试 `test_llm_not_a_scientific_source`：`source_type='llm'` → CHECK violation。✅

## 3. Human curator 不入 sources

Human curator 是 provenance/review agent，不是 Scientific Source；不向 sources 插入 "Human Curator" 这类记录。

## 4. Publication 不等于 source

- `sources` 可注册 PubMed / Europe PMC 这类 **source system**。
- `Publication`（具体文献实体）Phase 2+ 才建，本轮**不**建 `publications` 表。

## 5. kg_entities 侧

`kg_entities.created_by_agent / updated_by_agent`（VARCHAR(64)）记录 **provenance agent**（如 DeepSeek / human curator），非 scientific source。
