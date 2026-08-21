-- 20260824_canonical_connection.sql (idempotent)
-- CN1.2-1: Canonical Connection 基础设施。
-- canonical_connections 是连接域的概念中性层：source/target 指向
-- canonical_brain_regions，方向语义由 directionality_policy 表达；
-- 不修改 mirror_region_connections（70,029 行原样保留）、不生成 triple、
-- 不做推理；不建 reverse_connection 表、不双写反向关系。

-- 1) 词表：canonical 连接类型（projection/association/coactivation 已存在于
--    vocab_type='connection_type'；此处补充 canonical 层缺的 3 个 code）
INSERT INTO ontology_vocabularies (code, vocab_type, label_en, label_cn, description, seq) VALUES
('structural','connection_type','structural','结构连接','Canonical connection type (CN1.2): structural connectivity.',90),
('functional','connection_type','functional','功能连接','Canonical connection type (CN1.2): functional connectivity.',100),
('uncertain','connection_type','uncertain','不确定','Canonical connection type (CN1.2): uncertain connection.',110)
ON CONFLICT (code, vocab_type) DO NOTHING;

-- 2) 新词表：directionality_policy（canonical 层专用）
INSERT INTO ontology_vocabularies (code, vocab_type, label_en, label_cn, description, seq) VALUES
('directed','directionality_policy','directed','有向','Connection is directed source->target.',10),
('bidirectional','directionality_policy','bidirectional','双向','Connection exists in both directions.',20),
('undirected','directionality_policy','undirected','无向','Connection has no directional semantics.',30),
('unspecified','directionality_policy','unspecified','未指定','Direction semantics unknown or not declared.',40)
ON CONFLICT (code, vocab_type) DO NOTHING;

-- 3) canonical_connections 表
CREATE TABLE IF NOT EXISTS canonical_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    connection_code VARCHAR(128) NOT NULL UNIQUE,            -- ng:cn:<slug>，稳定逻辑标识
    source_region_id UUID NOT NULL REFERENCES canonical_brain_regions(id) ON DELETE CASCADE,
    target_region_id UUID NOT NULL REFERENCES canonical_brain_regions(id) ON DELETE CASCADE,
    connection_type VARCHAR(32) NOT NULL,
    directionality_policy VARCHAR(32) NOT NULL DEFAULT 'unspecified',
    species VARCHAR(16) NOT NULL DEFAULT 'human',
    granularity_level VARCHAR(64) NOT NULL DEFAULT 'clinical',
    status VARCHAR(16) NOT NULL DEFAULT 'proposed',
    confidence NUMERIC,
    source_summary JSONB NOT NULL DEFAULT '{}',
    evidence_summary JSONB NOT NULL DEFAULT '{}',
    provenance_json JSONB NOT NULL DEFAULT '{}',
    replaced_by_connection_id UUID REFERENCES canonical_connections(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_canonical_connection_not_self CHECK (source_region_id <> target_region_id),
    CONSTRAINT chk_canonical_connection_type CHECK (
        connection_type IN ('structural','functional','projection','association','coactivation','uncertain')
    ),
    CONSTRAINT chk_canonical_connection_directionality CHECK (
        directionality_policy IN ('directed','bidirectional','undirected','unspecified')
    ),
    CONSTRAINT chk_canonical_connection_status CHECK (
        status IN ('proposed','active','deprecated')
    ),
    CONSTRAINT uq_canonical_connection UNIQUE (source_region_id, target_region_id, connection_type)
);

CREATE INDEX IF NOT EXISTS idx_canonical_connection_source ON canonical_connections (source_region_id);
CREATE INDEX IF NOT EXISTS idx_canonical_connection_target ON canonical_connections (target_region_id);
CREATE INDEX IF NOT EXISTS idx_canonical_connection_type ON canonical_connections (connection_type);
CREATE INDEX IF NOT EXISTS idx_canonical_connection_status ON canonical_connections (status);
