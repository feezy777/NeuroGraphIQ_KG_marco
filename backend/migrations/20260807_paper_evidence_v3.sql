-- 20260807_paper_evidence_v3.sql (idempotent)
-- Phase C: batch pre-processing state machine, validation-center records, audit support.

-- 1) paper_evidence_tasks: progress + control timestamps
ALTER TABLE paper_evidence_tasks ADD COLUMN IF NOT EXISTS total_items INT NOT NULL DEFAULT 0;
ALTER TABLE paper_evidence_tasks ADD COLUMN IF NOT EXISTS processed_items INT NOT NULL DEFAULT 0;
ALTER TABLE paper_evidence_tasks ADD COLUMN IF NOT EXISTS awaiting_review_items INT NOT NULL DEFAULT 0;
ALTER TABLE paper_evidence_tasks ADD COLUMN IF NOT EXISTS failed_items INT NOT NULL DEFAULT 0;
ALTER TABLE paper_evidence_tasks ADD COLUMN IF NOT EXISTS paused_at TIMESTAMPTZ;
ALTER TABLE paper_evidence_tasks ADD COLUMN IF NOT EXISTS resumed_at TIMESTAMPTZ;
ALTER TABLE paper_evidence_tasks ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ;
ALTER TABLE paper_evidence_tasks ADD COLUMN IF NOT EXISTS config JSONB NOT NULL DEFAULT '{}'::jsonb;

-- 2) paper_evidence_task_items: draft storage + review fields
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS label TEXT;
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS current_confidence NUMERIC;
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS paper_json JSONB;
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS passages_json JSONB;
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS raw_response TEXT;
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS source_text_hash VARCHAR(64);
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS parse_status VARCHAR(32);
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS retry_count INT NOT NULL DEFAULT 0;
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS reviewed_by VARCHAR(64);
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ;
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS last_error TEXT;

-- 3) one active evidence pre-processing item per target at a time
CREATE UNIQUE INDEX IF NOT EXISTS uq_evidence_task_item_active_target
  ON paper_evidence_task_items (target_type, target_id)
  WHERE status NOT IN ('completed', 'skipped', 'failed', 'cancelled');

-- 4) validation-center records for paper evidence rules
CREATE TABLE IF NOT EXISTS evidence_validation_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evidence_id UUID REFERENCES mirror_evidence_records(id) ON DELETE CASCADE,
    task_id UUID,
    rule_code VARCHAR(64) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    target_type VARCHAR(32) NOT NULL,
    target_id UUID NOT NULL,
    direction VARCHAR(16),
    paper_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    resolved_by VARCHAR(64),
    resolution_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_evidence_validation_records_status
  ON evidence_validation_records (status, rule_code);
CREATE INDEX IF NOT EXISTS idx_evidence_validation_records_target
  ON evidence_validation_records (target_type, target_id);
