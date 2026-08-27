-- 20260908_macro_connection_symmetry_candidates.sql
-- Macro Connection A1 Hemisphere Symmetry Candidate Generation V1
--
-- macro_connection_candidates 表:由双侧对称性推理(A1 高可信镜像缺失)生成的候选连接。
--
-- 治理定位(硬边界):
--   * assertion_type = 'candidate' —— 不是 reported_fact,不进入 canonical active,
--     不写入 final_canonical_connections
--   * generation_method = 'hemisphere_symmetry_v1' —— 仅基于已有 mirror 连接推断,
--     source_connection_id 必填
--   * 禁止:LLM 生成、外部数据库、自动 promotion / Final KG 写入
--
-- 幂等锚:UNIQUE NULLS NOT DISTINCT(source_region_id, target_region_id,
--                 connection_type, source_connection_id)
-- —— 同一 mirror 源连接只生成一次;region 未映射(池细分概念,id 为 NULL)时
--    NULLS NOT DISTINCT 保证仍唯一。

DROP TABLE IF EXISTS macro_connection_candidates;

CREATE TABLE macro_connection_candidates (
    id                      UUID PRIMARY KEY,
    source_region_id        UUID REFERENCES canonical_brain_regions(id),
    target_region_id        UUID REFERENCES canonical_brain_regions(id),
    source_region_name      TEXT,
    target_region_name      TEXT,
    connection_type         TEXT NOT NULL,
    direction               TEXT,
    modality                TEXT,
    source_connection_id    UUID REFERENCES mirror_region_connections(id),
    generation_method       TEXT NOT NULL DEFAULT 'hemisphere_symmetry_v1',
    assertion_type          TEXT NOT NULL DEFAULT 'candidate',
    confidence              NUMERIC,
    provenance_json         JSONB NOT NULL DEFAULT '{}',
    status                  TEXT NOT NULL DEFAULT 'candidate',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_macro_conn_candidate UNIQUE NULLS NOT DISTINCT
        (source_region_id, target_region_id, connection_type,
         source_connection_id)
);

CREATE INDEX IF NOT EXISTS ix_macro_conn_candidate_source
    ON macro_connection_candidates (source_region_id);
CREATE INDEX IF NOT EXISTS ix_macro_conn_candidate_target
    ON macro_connection_candidates (target_region_id);
CREATE INDEX IF NOT EXISTS ix_macro_conn_candidate_source_conn
    ON macro_connection_candidates (source_connection_id);
