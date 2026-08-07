-- 20260807_paper_evidence.sql (idempotent)
-- Paper-evidence verification fields on mirror_evidence_records (Phase B).

ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS evidence_direction VARCHAR(16);
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS verification_status VARCHAR(16) NOT NULL DEFAULT 'pending';
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS paper_source VARCHAR(32);
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS paper_pmid VARCHAR(64);
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS paper_doi VARCHAR(256);
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS paper_title TEXT;
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS paper_journal VARCHAR(256);
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS paper_year INT;
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS suggested_confidence NUMERIC;
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS confidence_adjustment_status VARCHAR(16) NOT NULL DEFAULT 'none';
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS verification_by VARCHAR(64);
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS verification_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS paper_evidence_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_type VARCHAR(32) NOT NULL,
    scope VARCHAR(32) NOT NULL,
    mode VARCHAR(16) NOT NULL DEFAULT 'function',
    max_papers_per_object INT NOT NULL DEFAULT 3,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS paper_evidence_task_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES paper_evidence_tasks(id) ON DELETE CASCADE,
    target_type VARCHAR(32) NOT NULL,
    target_id UUID NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    pmid VARCHAR(64),
    title TEXT,
    abstract TEXT,
    passage TEXT,
    direction VARCHAR(16),
    confidence NUMERIC,
    evidence_id UUID,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_paper_evidence_task_items_task ON paper_evidence_task_items (task_id, status);
