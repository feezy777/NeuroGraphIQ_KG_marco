-- 20260901_circuit_canonical_grounding.sql (idempotent)
-- CR1 canonical grounding: Mirror Circuit → Canonical Circuit 正向关系表。
-- 每条 mirror_region_circuits 一行（UNIQUE 1:1），记录：
--   * circuit 名称标准化（canonical_name_en/cn）
--   * region 成员统计（total / grounded / ungrounded）
--   * connection member 关联（projection memberships → resolved canonical connections）
--   * function association 保留（function_count + provenance）
--   * grounding 状态（grounded / unresolved）+ 失败原因
-- 不创建新的 canonical_circuits；不修改 mirror_region_circuits 及其成员表；
-- 不执行 abstraction / inference / Final promotion。
--
-- 判定顺序（CR1 frozen rules）：
--   1. canonical_circuits.provenance_json->>'source_mirror_circuit_id' 命中 → grounded（回填）
--   2. granularity_level = 'molecular_attr'                    → species_granularity_mismatch
--   3. region 成员数 = 0                                       → no_region_members
--   4. region 成员数 < 2                                       → too_few_regions
--   5. grounded region 成员数 = 0                              → no_grounded_regions
--   6. 其余（≥2 成员但未 canonicalized）                        → unknown_region_role

CREATE TABLE IF NOT EXISTS mirror_circuit_canonical_grounding (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mirror_circuit_id UUID NOT NULL UNIQUE
        REFERENCES mirror_region_circuits(id) ON DELETE CASCADE,
    canonical_circuit_id UUID
        REFERENCES canonical_circuits(id) ON DELETE SET NULL,
    -- 名称标准化结果（strip + 压缩内部空白；grounded 行取 canonical 侧名称）
    canonical_name_en TEXT,
    canonical_name_cn TEXT,
    -- 镜像侧快照（evidence source / 类型 / 粒度）
    granularity_level VARCHAR(32),
    source_atlas VARCHAR(128),
    circuit_type VARCHAR(64),
    -- region 成员统计（成员表 mirror_circuit_regions → candidate → canonical）
    total_region_members INT NOT NULL DEFAULT 0,
    grounded_region_members INT NOT NULL DEFAULT 0,
    ungrounded_region_members INT NOT NULL DEFAULT 0,
    -- connection member 关联（mirror_circuit_projection_memberships）
    projection_membership_count INT NOT NULL DEFAULT 0,
    resolved_connection_count INT NOT NULL DEFAULT 0,
    -- function association 保留
    function_count INT NOT NULL DEFAULT 0,
    mapping_method VARCHAR(64),
    status VARCHAR(16) NOT NULL DEFAULT 'unresolved',
    -- unresolved_reason: species_granularity_mismatch | no_region_members |
    -- too_few_regions | no_grounded_regions | unknown_region_role
    unresolved_reason VARCHAR(32),
    confidence NUMERIC,
    provenance_json JSONB,
    created_by VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_circuit_grounding_status CHECK (status IN ('grounded', 'unresolved')),
    CONSTRAINT chk_circuit_grounding_members CHECK (
        ungrounded_region_members = total_region_members - grounded_region_members
    )
);

CREATE INDEX IF NOT EXISTS idx_circuit_grounding_status
    ON mirror_circuit_canonical_grounding (status);
CREATE INDEX IF NOT EXISTS idx_circuit_grounding_canonical_circuit
    ON mirror_circuit_canonical_grounding (canonical_circuit_id);
CREATE INDEX IF NOT EXISTS idx_circuit_grounding_unresolved_reason
    ON mirror_circuit_canonical_grounding (unresolved_reason);
