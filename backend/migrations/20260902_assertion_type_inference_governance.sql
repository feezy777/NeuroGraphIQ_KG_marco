-- 20260902_assertion_type_inference_governance.sql (idempotent)
-- 统一推理治理基础设施:建立 assertion_type 体系 + provenance metadata。
--
-- 目标:为后续 Connection roll-up / Circuit abstraction / graph inference
-- 提供事实/推理分层基础。本 migration 只做基础设施 —— 不执行任何 roll-up /
-- abstraction / promotion,不修改既有数据行。
--
-- 默认值语义(诚实初始化):
--   assertion_type     = 'reported_fact'  — 现有 canonical 数据均经 review/promotion,
--                                           属于"报告事实"层(论文/数据库/人工确认)。
--   source_type        = 'unknown'        — 历史行未记录来源类型,迁移后由 grounding /
--                                           inference 写入时回填。
--   generation_method  = 'unknown'        — 同上;方法名是开放集(如 'cn1_connection_grounding_v1')。
--   evidence_reference = '[]'             — 证据引用数组(evidence id / DOI / source 文件),
--                                           历史行无显式引用,空数组 = 无引用。

-- ============ 1. assertion_type 词表 ============
INSERT INTO ontology_vocabularies (code, vocab_type, label_en, label_cn, description, status, seq) VALUES
('reported_fact', 'assertion_type', 'reported_fact', '报告事实',
 '论文、数据库、人工确认的事实。canonical 层经 review/promotion 的数据默认值。', 'active', 10),
('inferred', 'assertion_type', 'inferred', '规则推理',
 '知识图谱规则推理结果(Connection roll-up / Circuit abstraction / graph inference 产出)。', 'active', 20),
('hypothesis', 'assertion_type', 'hypothesis', '科学假设',
 '候选科学假设,未经充分证据验证。', 'active', 30),
('candidate', 'assertion_type', 'candidate', '待验证候选',
 'LLM 抽取但未验证(mirror 层数据)。', 'active', 40)
ON CONFLICT (code, vocab_type) DO NOTHING;

-- ============ 2. canonical_connections ============
ALTER TABLE canonical_connections
    ADD COLUMN IF NOT EXISTS assertion_type varchar(32) NOT NULL DEFAULT 'reported_fact',
    ADD COLUMN IF NOT EXISTS source_type varchar(32) NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS generation_method varchar(64) NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS evidence_reference jsonb NOT NULL DEFAULT '[]'::jsonb;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_canonical_connections_assertion_type') THEN
        ALTER TABLE canonical_connections ADD CONSTRAINT ck_canonical_connections_assertion_type
            CHECK (assertion_type IN ('reported_fact', 'inferred', 'hypothesis', 'candidate'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_canonical_connections_source_type') THEN
        ALTER TABLE canonical_connections ADD CONSTRAINT ck_canonical_connections_source_type
            CHECK (source_type IN ('literature', 'database', 'expert_review', 'llm_extraction',
                                   'rule_inference', 'human_curation', 'unknown'));
    END IF;
END $$;

-- ============ 3. canonical_circuits ============
ALTER TABLE canonical_circuits
    ADD COLUMN IF NOT EXISTS assertion_type varchar(32) NOT NULL DEFAULT 'reported_fact',
    ADD COLUMN IF NOT EXISTS source_type varchar(32) NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS generation_method varchar(64) NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS evidence_reference jsonb NOT NULL DEFAULT '[]'::jsonb;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_canonical_circuits_assertion_type') THEN
        ALTER TABLE canonical_circuits ADD CONSTRAINT ck_canonical_circuits_assertion_type
            CHECK (assertion_type IN ('reported_fact', 'inferred', 'hypothesis', 'candidate'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_canonical_circuits_source_type') THEN
        ALTER TABLE canonical_circuits ADD CONSTRAINT ck_canonical_circuits_source_type
            CHECK (source_type IN ('literature', 'database', 'expert_review', 'llm_extraction',
                                   'rule_inference', 'human_curation', 'unknown'));
    END IF;
END $$;

-- ============ 4. canonical_circuit_functions (Function relation) ============
ALTER TABLE canonical_circuit_functions
    ADD COLUMN IF NOT EXISTS assertion_type varchar(32) NOT NULL DEFAULT 'reported_fact',
    ADD COLUMN IF NOT EXISTS source_type varchar(32) NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS generation_method varchar(64) NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS evidence_reference jsonb NOT NULL DEFAULT '[]'::jsonb;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_canonical_circuit_functions_assertion_type') THEN
        ALTER TABLE canonical_circuit_functions ADD CONSTRAINT ck_canonical_circuit_functions_assertion_type
            CHECK (assertion_type IN ('reported_fact', 'inferred', 'hypothesis', 'candidate'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_canonical_circuit_functions_source_type') THEN
        ALTER TABLE canonical_circuit_functions ADD CONSTRAINT ck_canonical_circuit_functions_source_type
            CHECK (source_type IN ('literature', 'database', 'expert_review', 'llm_extraction',
                                   'rule_inference', 'human_curation', 'unknown'));
    END IF;
END $$;

-- ============ 5. atlas_region_mappings (BrainRegion mapping) ============
ALTER TABLE atlas_region_mappings
    ADD COLUMN IF NOT EXISTS assertion_type varchar(32) NOT NULL DEFAULT 'reported_fact',
    ADD COLUMN IF NOT EXISTS source_type varchar(32) NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS generation_method varchar(64) NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS evidence_reference jsonb NOT NULL DEFAULT '[]'::jsonb;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_atlas_region_mappings_assertion_type') THEN
        ALTER TABLE atlas_region_mappings ADD CONSTRAINT ck_atlas_region_mappings_assertion_type
            CHECK (assertion_type IN ('reported_fact', 'inferred', 'hypothesis', 'candidate'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_atlas_region_mappings_source_type') THEN
        ALTER TABLE atlas_region_mappings ADD CONSTRAINT ck_atlas_region_mappings_source_type
            CHECK (source_type IN ('literature', 'database', 'expert_review', 'llm_extraction',
                                   'rule_inference', 'human_curation', 'unknown'));
    END IF;
END $$;
