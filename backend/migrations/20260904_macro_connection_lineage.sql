-- 20260904: Macro Connection canonical consolidation Pipeline 第 3 层
-- Cluster → Canonical Connection + Evidence Summary + Lineage
--
-- 1) canonical_connections 增加 evidence 上卷列(evidence_summary/source_summary 已有)
-- 2) 新表 canonical_connection_lineage:canonical → cluster → mirror 完整追溯
--    幂等:重跑脚本时按 cluster_id 重建本批 lineage 行

DO $$
BEGIN
    -- 1) evidence 列
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'canonical_connections' AND column_name = 'evidence_count') THEN
        ALTER TABLE canonical_connections
            ADD COLUMN evidence_count INTEGER NOT NULL DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'canonical_connections' AND column_name = 'confidence_statistics') THEN
        ALTER TABLE canonical_connections
            ADD COLUMN confidence_statistics JSONB NOT NULL DEFAULT '{}'::jsonb;
    END IF;

    -- 2) lineage 表
    IF NOT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = current_schema()
                   AND tablename = 'canonical_connection_lineage') THEN
        CREATE TABLE canonical_connection_lineage (
            id                  BIGSERIAL PRIMARY KEY,
            canonical_id        UUID NOT NULL REFERENCES canonical_connections(id),
            cluster_id          BIGINT NOT NULL REFERENCES mirror_connection_clusters(id),
            mirror_connection_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            cluster_size        INTEGER NOT NULL DEFAULT 0,
            merge_reason        TEXT NOT NULL DEFAULT 'single_evidence',
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_lineage_canonical_cluster UNIQUE (canonical_id, cluster_id)
        );
        CREATE INDEX idx_lineage_canonical ON canonical_connection_lineage(canonical_id);
        CREATE INDEX idx_lineage_cluster ON canonical_connection_lineage(cluster_id);
    END IF;
END $$;
