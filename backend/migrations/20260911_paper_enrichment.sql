-- Macro Paper Knowledge Enrichment V1
-- paper_sources 增加 enrichment_json(jsonb) —— Europe PMC 元数据富化容器。
-- (注:注释内使用全角冒号,避免 text() 绑定参数解析)
--
-- 设计(用户要求):
-- * 不覆盖已有非空字段 —— journal 等已有列只填空(见脚本 COALESCE 语义)
-- * 保留原始 metadata_json —— 富化数据写入新列 enrichment_json,不动 metadata_json
-- * 新增字段必须记录溯源 —— enrichment_json 内含
--   metadata_source='pubmed_enrichment_v1' / retrieved_at / pmid
--
-- 字段(6 项 + 溯源):
--   abstract, journal, publication_type, keywords, mesh_terms,
--   authors(结构化), metadata_source, retrieved_at, pmid
--
-- 幂等 —— 脚本以 enrichment_json IS DISTINCT FROM 检测变化 → 复跑 update=0。

ALTER TABLE paper_sources
    ADD COLUMN IF NOT EXISTS enrichment_json jsonb;

COMMENT ON COLUMN paper_sources.enrichment_json IS
    'Europe PMC 元数据富化(metadata_source=pubmed_enrichment_v1)'
    ' abstract/journal/publication_type/keywords/mesh_terms/authors 结构化 + 溯源';
