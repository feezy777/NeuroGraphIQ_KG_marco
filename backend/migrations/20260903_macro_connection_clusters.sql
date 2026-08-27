-- 20260903: Macro Connection canonical consolidation v1
-- 中间结果表:mirror_connection_clusters
-- 功能:记录 "重复连接识别 → canonical cluster 建立 → evidence 聚合" 的聚类结果。
-- 原则:
--   * 只读镜像 mirror_region_connections(不删除/不修改任何 mirror 行)
--   * 每行 = 一个 cluster(canonical key: src/tgt canonical region + type + direction + modality_norm + species)
--   * hemisphere 侧别在 hemisphere_groups 中保留,不简单合并左右
--   * mirror_connection_ids 全量保留 provenance
-- 幂等:重跑脚本前 TRUNCATE 本表。

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = current_schema()
                   AND tablename = 'mirror_connection_clusters') THEN
        CREATE TABLE mirror_connection_clusters (
            id                  BIGSERIAL PRIMARY KEY,
            cluster_key         TEXT NOT NULL,
            source_region_id    UUID NOT NULL REFERENCES canonical_brain_regions(id),
            target_region_id    UUID NOT NULL REFERENCES canonical_brain_regions(id),
            source_region_name  TEXT NOT NULL,
            target_region_name  TEXT NOT NULL,
            connection_type     TEXT NOT NULL,
            directionality      TEXT NOT NULL,
            modality_norm       TEXT NOT NULL,
            modality_original   JSONB NOT NULL DEFAULT '[]'::jsonb,
            species             TEXT NOT NULL DEFAULT 'human',
            hemisphere_groups   JSONB NOT NULL DEFAULT '[]'::jsonb,
            mirror_connection_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            evidence_count      INTEGER NOT NULL DEFAULT 0,
            merge_reason        TEXT NOT NULL DEFAULT 'single_evidence',
            confidence_distribution JSONB NOT NULL DEFAULT '{}'::jsonb,
            provenance          JSONB NOT NULL DEFAULT '{}'::jsonb,
            status              TEXT NOT NULL DEFAULT 'preview',
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_cluster_key UNIQUE (cluster_key)
        );
        CREATE INDEX idx_clusters_src ON mirror_connection_clusters(source_region_id);
        CREATE INDEX idx_clusters_tgt ON mirror_connection_clusters(target_region_id);
        CREATE INDEX idx_clusters_reason ON mirror_connection_clusters(merge_reason);
    END IF;
END $$;
