-- 20260807_paper_evidence_v2.sql (idempotent)
-- Evidence status semantics, passage-level storage, confidence adjustment logs.

-- 1) Verification status semantics.
--    pending: extracted or reviewed not started
--    ai_extracted: DeepSeek extracted, not human-confirmed
--    human_verified: human-confirmed and stored
--    rejected: human judged invalid
--    invalidated: stored evidence later revoked
--    verified_auto: legacy (kept for compatibility; new writes must NOT use it)
ALTER TABLE mirror_evidence_records DROP CONSTRAINT IF EXISTS chk_mirror_evidence_verification_status;
ALTER TABLE mirror_evidence_records ADD CONSTRAINT chk_mirror_evidence_verification_status CHECK (
    verification_status IN (
        'pending', 'ai_extracted', 'human_verified', 'rejected', 'invalidated', 'verified_auto'
    )
);
COMMENT ON COLUMN mirror_evidence_records.verification_status IS
  'pending | ai_extracted | human_verified | rejected | invalidated (verified_auto is legacy, do not write)';

-- 2) Passage-level evidence storage.
CREATE TABLE IF NOT EXISTS mirror_evidence_passages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evidence_id UUID NOT NULL REFERENCES mirror_evidence_records(id) ON DELETE CASCADE,
    source_scope VARCHAR(16) NOT NULL,          -- abstract | fulltext
    section_title TEXT,
    paragraph_index INT,
    passage_text TEXT NOT NULL,
    translation_zh TEXT,
    direction VARCHAR(16) NOT NULL,
    reason TEXT,
    confidence NUMERIC,
    is_selected BOOLEAN NOT NULL DEFAULT FALSE,
    source_locator VARCHAR(256),
    passage_hash VARCHAR(64) NOT NULL,
    source_verified BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_evidence_passage_hash UNIQUE (evidence_id, passage_hash)
);
CREATE INDEX IF NOT EXISTS idx_evidence_passages_evidence ON mirror_evidence_passages (evidence_id);
CREATE INDEX IF NOT EXISTS idx_evidence_passages_hash ON mirror_evidence_passages (passage_hash);

-- 3) Confidence adjustment audit/rollback log.
CREATE TABLE IF NOT EXISTS confidence_adjustment_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_type VARCHAR(32) NOT NULL,
    target_id UUID NOT NULL,
    evidence_id UUID,
    before_confidence NUMERIC,
    suggested_confidence NUMERIC,
    after_confidence NUMERIC,
    direction VARCHAR(16),
    formula_version VARCHAR(64) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'applied',   -- applied | pending | rolled_back
    applied_by VARCHAR(64),
    applied_at TIMESTAMPTZ,
    rolled_back_by VARCHAR(64),
    rolled_back_at TIMESTAMPTZ,
    rollback_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_conf_adjustment_target ON confidence_adjustment_logs (target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_conf_adjustment_evidence ON confidence_adjustment_logs (evidence_id);
