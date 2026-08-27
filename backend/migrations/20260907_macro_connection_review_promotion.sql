-- 20260907: Macro Connection Human Review + Promotion
-- Macro Human Canonical Connection 治理闭环:Validation PASS / Review approved
-- → Active Canonical Connection → Final Canonical Connection (Final KG)。
--
-- 1) canonical_connection_review_records    — 人工审查记录(action: approved/rejected/needs_more_evidence)
-- 2) canonical_connection_promotion_runs    — promotion 批次统计
-- 3) final_canonical_connections            — canonical 层 Final 事实表(与 mirror 层
--    final_region_connections 平行,不混淆层语义);canonical_connection_id UNIQUE = 幂等锚
-- 4) canonical_connection_promotion_records — 每 canonical 一条 promotion 结果
--    (reviewer / validation_run_id / evidence_reference / promotion_reason)
--
-- 守卫:promotion 资格由服务层强制(仅 validation PASS 或 review approved);
-- 本 migration 不写任何数据,不删除 mirror / cluster。
-- 幂等:重复执行安全(IF NOT EXISTS)。

-- ============ 1. Review records ============
CREATE TABLE IF NOT EXISTS canonical_connection_review_records (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_connection_id UUID NOT NULL REFERENCES canonical_connections(id) ON DELETE CASCADE,
    validation_run_id       UUID NULL,
    action                  TEXT NOT NULL CHECK (action IN ('approved', 'rejected', 'needs_more_evidence')),
    reviewer                TEXT NOT NULL,
    reviewer_note           TEXT,
    failed_rules_json       JSONB NOT NULL DEFAULT '[]'::jsonb,
    before_json             JSONB NOT NULL DEFAULT '{}'::jsonb,
    after_json              JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_summary_json   JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cc_review_connection ON canonical_connection_review_records (canonical_connection_id);
CREATE INDEX IF NOT EXISTS idx_cc_review_action     ON canonical_connection_review_records (action);
CREATE INDEX IF NOT EXISTS idx_cc_review_reviewer   ON canonical_connection_review_records (reviewer);
CREATE INDEX IF NOT EXISTS idx_cc_review_created    ON canonical_connection_review_records (created_at);

-- ============ 2. Promotion runs ============
CREATE TABLE IF NOT EXISTS canonical_connection_promotion_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    promotion_key   TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'completed' CHECK (status IN ('completed', 'failed')),
    scope_json      JSONB NOT NULL DEFAULT '{}'::jsonb,
    eligible_count  INTEGER NOT NULL DEFAULT 0,
    promoted_count  INTEGER NOT NULL DEFAULT 0,
    skipped_count   INTEGER NOT NULL DEFAULT 0,
    rejected_count  INTEGER NOT NULL DEFAULT 0,
    reviewer        TEXT,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cc_promo_runs_key ON canonical_connection_promotion_runs (promotion_key);

-- ============ 3. Final Canonical Connections (Final KG) ============
CREATE TABLE IF NOT EXISTS final_canonical_connections (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_connection_id UUID UNIQUE REFERENCES canonical_connections(id) ON DELETE SET NULL,
    connection_code         VARCHAR(128) NOT NULL,
    source_region_id        UUID NOT NULL REFERENCES canonical_brain_regions(id) ON DELETE RESTRICT,
    target_region_id        UUID NOT NULL REFERENCES canonical_brain_regions(id) ON DELETE RESTRICT,
    connection_type         VARCHAR(32) NOT NULL,
    directionality_policy   VARCHAR(32) NOT NULL DEFAULT 'unspecified',
    species                 VARCHAR(16) NOT NULL DEFAULT 'human',
    granularity_level       VARCHAR(64) NOT NULL DEFAULT 'clinical',
    confidence              NUMERIC,
    evidence_summary        JSONB NOT NULL DEFAULT '{}'::jsonb,
    provenance_json         JSONB NOT NULL DEFAULT '{}'::jsonb,
    assertion_type          VARCHAR(32) NOT NULL DEFAULT 'reported_fact',
    source_type             VARCHAR(32) NOT NULL DEFAULT 'unknown',
    generation_method       VARCHAR(64) NOT NULL DEFAULT 'unknown',
    evidence_reference      JSONB NOT NULL DEFAULT '[]'::jsonb,
    validation_run_id       UUID NULL,
    review_record_id        UUID NULL REFERENCES canonical_connection_review_records(id) ON DELETE SET NULL,
    promotion_record_id     UUID NULL,  -- FK 在文件末尾追加(避免与 promotion_records 循环依赖)
    final_status            VARCHAR(16) NOT NULL DEFAULT 'active' CHECK (final_status IN
                              ('active', 'deprecated', 'superseded')),
    promoted_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_final_canonical_connection_not_self CHECK (source_region_id <> target_region_id),
    CONSTRAINT chk_final_canonical_connection_type CHECK (
        connection_type IN ('structural','functional','projection','association','coactivation','uncertain')
    ),
    CONSTRAINT chk_final_canonical_connection_directionality CHECK (
        directionality_policy IN ('directed','bidirectional','undirected','unspecified')
    )
);

CREATE INDEX IF NOT EXISTS idx_final_cc_connection ON final_canonical_connections (canonical_connection_id);
CREATE INDEX IF NOT EXISTS idx_final_cc_source     ON final_canonical_connections (source_region_id);
CREATE INDEX IF NOT EXISTS idx_final_cc_target     ON final_canonical_connections (target_region_id);
CREATE INDEX IF NOT EXISTS idx_final_cc_type       ON final_canonical_connections (connection_type);
CREATE INDEX IF NOT EXISTS idx_final_cc_status     ON final_canonical_connections (final_status);

-- ============ 4. Promotion records ============
CREATE TABLE IF NOT EXISTS canonical_connection_promotion_records (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                      UUID NOT NULL REFERENCES canonical_connection_promotion_runs(id)
                                      ON DELETE CASCADE,
    canonical_connection_id     UUID NOT NULL REFERENCES canonical_connections(id) ON DELETE CASCADE,
    final_canonical_connection_id UUID NULL REFERENCES final_canonical_connections(id) ON DELETE SET NULL,
    validation_run_id           UUID NULL,
    review_record_id            UUID NULL REFERENCES canonical_connection_review_records(id)
                                      ON DELETE SET NULL,
    reviewer                    TEXT NOT NULL,
    promotion_reason            TEXT,
    evidence_reference          JSONB NOT NULL DEFAULT '[]'::jsonb,
    status                      TEXT NOT NULL CHECK (status IN
                                  ('promoted', 'skipped_duplicate', 'skipped_ineligible', 'rejected')),
    message                     TEXT,
    before_json                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    after_json                  JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, canonical_connection_id)
);

CREATE INDEX IF NOT EXISTS idx_cc_promo_rec_run        ON canonical_connection_promotion_records (run_id);
CREATE INDEX IF NOT EXISTS idx_cc_promo_rec_connection ON canonical_connection_promotion_records (canonical_connection_id);
CREATE INDEX IF NOT EXISTS idx_cc_promo_rec_status     ON canonical_connection_promotion_records (status);

-- ============ 5. 循环依赖补全 FK(表全部就位后,幂等) ============
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_final_cc_promotion_record') THEN
        ALTER TABLE final_canonical_connections
            ADD CONSTRAINT fk_final_cc_promotion_record
            FOREIGN KEY (promotion_record_id)
            REFERENCES canonical_connection_promotion_records(id) ON DELETE SET NULL;
    END IF;
END $$;

