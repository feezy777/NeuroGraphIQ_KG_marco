-- 20260831_connection_canonical_grounding.sql (idempotent)
-- CN1 canonical grounding: Mirror Connection → Canonical Connection 正向关系表。
-- 每条 mirror_region_connections 一行（UNIQUE 1:1），记录：
--   * 端点 canonical resolution（source/target region id + resolution method）
--   * connection_type / directionality_policy 标准化结果（复用 frozen rules）
--   * grounding 状态（grounded / unresolved）+ 失败原因
-- 不修改 mirror_region_connections；不执行 roll-up / inference / promotion。

CREATE TABLE IF NOT EXISTS mirror_connection_canonical_grounding (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mirror_connection_id UUID NOT NULL UNIQUE
        REFERENCES mirror_region_connections(id) ON DELETE CASCADE,
    canonical_connection_id UUID
        REFERENCES canonical_connections(id) ON DELETE SET NULL,
    source_region_id UUID
        REFERENCES canonical_brain_regions(id) ON DELETE SET NULL,
    target_region_id UUID
        REFERENCES canonical_brain_regions(id) ON DELETE SET NULL,
    -- resolution method: candidate_grounded | name_canonical_exact |
    -- name_alias_exact | name_normalized_exact | unresolved
    source_resolution_method VARCHAR(32) NOT NULL DEFAULT 'unresolved',
    target_resolution_method VARCHAR(32) NOT NULL DEFAULT 'unresolved',
    -- 标准化后的 canonical 值（frozen rules 映射结果）
    connection_type VARCHAR(32),
    directionality_policy VARCHAR(32),
    status VARCHAR(16) NOT NULL DEFAULT 'unresolved',
    -- unresolved_reason: species_mismatch | no_name_match | self_loop |
    -- missing_candidate | mapping_error | canonical_duplicate
    unresolved_reason VARCHAR(32),
    confidence NUMERIC,
    created_by VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_grounding_status CHECK (status IN ('grounded', 'unresolved')),
    CONSTRAINT chk_grounding_method CHECK (
        source_resolution_method IN (
            'candidate_grounded', 'name_canonical_exact', 'name_alias_exact',
            'name_normalized_exact', 'unresolved'
        )
        AND target_resolution_method IN (
            'candidate_grounded', 'name_canonical_exact', 'name_alias_exact',
            'name_normalized_exact', 'unresolved'
        )
    ),
    CONSTRAINT chk_grounding_not_self CHECK (
        source_region_id IS NULL OR target_region_id IS NULL
        OR source_region_id <> target_region_id
    )
);

CREATE INDEX IF NOT EXISTS idx_grounding_status ON mirror_connection_canonical_grounding (status);
CREATE INDEX IF NOT EXISTS idx_grounding_canonical_conn ON mirror_connection_canonical_grounding (canonical_connection_id);
CREATE INDEX IF NOT EXISTS idx_grounding_unresolved_reason ON mirror_connection_canonical_grounding (unresolved_reason);
