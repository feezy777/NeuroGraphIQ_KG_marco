# Gate 6E-B — Source vs Agent Boundary

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. Scientific Source

Publication / Julich-Brain / Human Brainnetome / HGNC / MONDO / HPO / IUPHAR / ChEBI / PubMed / Europe PMC / 其他 verified scientific database。

## 2. Provenance Agent

GPT / DeepSeek / BioSEPBERT / Human curator / ImportPipeline / RuleEngine。

## 3. 禁止互换

- LLM 不能因"模型生成了这条 Evidence"就成为 scientific source。
- Evidence 是 DeepSeek 从 PMID 文献抽取 → scientific source = Publication/PubMed，extraction agent = DeepSeek。

## 4. External database evidence

- publication_pk NULL、study_pk NULL、scientific_source_pk → sources.source_pk（HGNC/MONDO/Julich-Brain/IUPHAR）。
- 若同时有 Publication，publication_pk 与 scientific_source_pk 可同时存在。
