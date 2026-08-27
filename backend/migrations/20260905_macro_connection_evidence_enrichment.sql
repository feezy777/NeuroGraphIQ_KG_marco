-- 20260905: Macro Connection Evidence Enrichment
-- Canonical Connection 证据标准化 + Evidence Quality Score
--
-- 1) evidence_quality_score: high / medium / low 三档分析评分(不改动 confidence)
-- 2) evidence_quality_factors: 评分依据明细(证据量/来源数/一致性等),可审计
--    幂等:脚本全量重算覆盖,无需删除标记

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'canonical_connections' AND column_name = 'evidence_quality_score') THEN
        ALTER TABLE canonical_connections
            ADD COLUMN evidence_quality_score TEXT;  -- high / medium / low
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'canonical_connections' AND column_name = 'evidence_quality_factors') THEN
        ALTER TABLE canonical_connections
            ADD COLUMN evidence_quality_factors JSONB NOT NULL DEFAULT '{}'::jsonb;
    END IF;
END $$;
