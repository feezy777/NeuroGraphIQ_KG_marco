-- 20260825_canonical_circuit.sql (idempotent)
-- CI1.1: Canonical Circuit 实体基础建设。
-- canonical_circuits 是回路域的概念中性层：成员 region 指向
-- canonical_brain_regions、成员 connection 指向 canonical_connections、
-- 成员 function 指向 ontology_terms；生命周期 proposed→active→deprecated，
-- merge 通过 replaced_by_circuit_id 表达。
-- 不修改 mirror_region_circuits/mirror_circuit_*（53,562 回路原样保留）、
-- 不修改 triple、不修改 promotion 流程、不做推理、不自动生成真实 circuit。

-- 1) 词表：circuit_type 追加 canonical 结构分类码（与 mirror 层功能分类码
--    sensory_circuit 等并存于同一 vocab_type，seq 从 130 起）
INSERT INTO ontology_vocabularies (code, vocab_type, label_en, label_cn, description, seq) VALUES
('network','circuit_type','network','网络','Canonical circuit type (CI1.1): distributed network.',130),
('pathway','circuit_type','pathway','通路','Canonical circuit type (CI1.1): stepwise pathway.',140),
('reflex','circuit_type','reflex','反射','Canonical circuit type (CI1.1): reflex arc.',150),
('functional_loop','circuit_type','functional loop','功能环路','Canonical circuit type (CI1.1): closed functional loop.',160),
('uncertain','circuit_type','uncertain','不确定','Canonical circuit type (CI1.1): uncertain circuit classification.',170)
ON CONFLICT (code, vocab_type) DO NOTHING;

-- 2) 词表：circuit_region_role 追加 canonical 成员角色码（seq 从 80 起）
INSERT INTO ontology_vocabularies (code, vocab_type, label_en, label_cn, description, seq) VALUES
('core_region','circuit_region_role','core region','核心脑区','Canonical circuit region role (CI1.1): core member.',80),
('input','circuit_region_role','input','输入','Canonical circuit region role (CI1.1): input node.',90),
('output','circuit_region_role','output','输出','Canonical circuit region role (CI1.1): output node.',100),
('intermediate','circuit_region_role','intermediate','中间站','Canonical circuit region role (CI1.1): intermediate node.',110)
ON CONFLICT (code, vocab_type) DO NOTHING;

-- 3) 新词表：circuit_connection_role（canonical 层专用）
INSERT INTO ontology_vocabularies (code, vocab_type, label_en, label_cn, description, seq) VALUES
('feedforward','circuit_connection_role','feedforward','前馈','Canonical circuit connection role (CI1.1): feedforward.',10),
('feedback','circuit_connection_role','feedback','反馈','Canonical circuit connection role (CI1.1): feedback.',20),
('supporting','circuit_connection_role','supporting','支撑','Canonical circuit connection role (CI1.1): supporting.',30)
ON CONFLICT (code, vocab_type) DO NOTHING;

-- 4) canonical_circuits 表
CREATE TABLE IF NOT EXISTS canonical_circuits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    circuit_code VARCHAR(128) NOT NULL UNIQUE,               -- ng:ci:<slug>，稳定逻辑标识
    canonical_name_en TEXT NOT NULL,
    canonical_name_cn TEXT,
    species VARCHAR(16) NOT NULL DEFAULT 'human',
    granularity_level VARCHAR(64) NOT NULL DEFAULT 'clinical',
    circuit_type VARCHAR(32) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'proposed',
    description TEXT,
    confidence NUMERIC,
    source_summary JSONB NOT NULL DEFAULT '{}',
    provenance_json JSONB NOT NULL DEFAULT '{}',
    replaced_by_circuit_id UUID REFERENCES canonical_circuits(id) ON DELETE SET NULL,
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_canonical_circuit_type CHECK (
        circuit_type IN ('network','pathway','reflex','functional_loop','uncertain')
    ),
    CONSTRAINT chk_canonical_circuit_status CHECK (
        status IN ('proposed','active','deprecated')
    ),
    CONSTRAINT chk_canonical_circuit_not_self_merge CHECK (
        replaced_by_circuit_id IS NULL OR replaced_by_circuit_id <> id
    )
);

-- 5) canonical_circuit_regions 成员表
CREATE TABLE IF NOT EXISTS canonical_circuit_regions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    circuit_id UUID NOT NULL REFERENCES canonical_circuits(id) ON DELETE CASCADE,
    region_id UUID NOT NULL REFERENCES canonical_brain_regions(id) ON DELETE CASCADE,
    role VARCHAR(32) NOT NULL DEFAULT 'core_region',
    order_index INTEGER NOT NULL DEFAULT 0,
    confidence NUMERIC,
    provenance_json JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_canonical_circuit_region_role CHECK (
        role IN ('core_region','input','output','intermediate')
    ),
    CONSTRAINT uq_canonical_circuit_region UNIQUE (circuit_id, region_id)
);

-- 6) canonical_circuit_connections 成员表
CREATE TABLE IF NOT EXISTS canonical_circuit_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    circuit_id UUID NOT NULL REFERENCES canonical_circuits(id) ON DELETE CASCADE,
    connection_id UUID NOT NULL REFERENCES canonical_connections(id) ON DELETE CASCADE,
    role VARCHAR(32) NOT NULL DEFAULT 'supporting',
    confidence NUMERIC,
    provenance_json JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_canonical_circuit_connection_role CHECK (
        role IN ('feedforward','feedback','supporting')
    ),
    CONSTRAINT uq_canonical_circuit_connection UNIQUE (circuit_id, connection_id)
);

-- 7) canonical_circuit_functions 成员表
CREATE TABLE IF NOT EXISTS canonical_circuit_functions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    circuit_id UUID NOT NULL REFERENCES canonical_circuits(id) ON DELETE CASCADE,
    function_term_id UUID NOT NULL REFERENCES ontology_terms(id) ON DELETE CASCADE,
    relation_type VARCHAR(32) NOT NULL DEFAULT 'associated_with',
    confidence NUMERIC,
    provenance_json JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_canonical_circuit_function_relation CHECK (
        relation_type IN (
            'involved_in','associated_with','necessary_for','modulates',
            'participates_in','uncertain_association','unknown'
        )
    ),
    CONSTRAINT uq_canonical_circuit_function UNIQUE (circuit_id, function_term_id)
);

-- 8) indexes
CREATE INDEX IF NOT EXISTS idx_canonical_circuit_status ON canonical_circuits (status);
CREATE INDEX IF NOT EXISTS idx_canonical_circuit_type ON canonical_circuits (circuit_type);
CREATE INDEX IF NOT EXISTS idx_canonical_circuit_replaced_by ON canonical_circuits (replaced_by_circuit_id);
CREATE INDEX IF NOT EXISTS idx_canonical_circuit_regions_region ON canonical_circuit_regions (region_id);
CREATE INDEX IF NOT EXISTS idx_canonical_circuit_connections_conn ON canonical_circuit_connections (connection_id);
CREATE INDEX IF NOT EXISTS idx_canonical_circuit_functions_term ON canonical_circuit_functions (function_term_id);
