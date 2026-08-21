-- 20260812_paper_evidence_extraction_runs.sql (idempotent)
-- Parallel extraction run and per-paper item state.

CREATE TABLE IF NOT EXISTS paper_evidence_extraction_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_type VARCHAR(64) NOT NULL,
    target_id UUID NOT NULL,
    mode VARCHAR(16) NOT NULL DEFAULT 'function',
    status VARCHAR(32) NOT NULL DEFAULT 'queued',
    total_items INT NOT NULL DEFAULT 0,
    completed_items INT NOT NULL DEFAULT 0,
    evidence_hit_items INT NOT NULL DEFAULT 0,
    no_evidence_items INT NOT NULL DEFAULT 0,
    failed_items INT NOT NULL DEFAULT 0,
    requested_concurrency INT NOT NULL DEFAULT 4,
    active_concurrency INT NOT NULL DEFAULT 0,
    cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
    request_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS paper_evidence_extraction_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES paper_evidence_extraction_runs(id) ON DELETE CASCADE,
    item_index INT NOT NULL,
    pmid VARCHAR(32),
    pmcid VARCHAR(32),
    doi VARCHAR(512),
    title TEXT,
    paper_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(32) NOT NULL DEFAULT 'queued',
    progress_percent INT NOT NULL DEFAULT 0,
    attempt_count INT NOT NULL DEFAULT 0,
    result_json JSONB,
    error_code VARCHAR(64),
    error_message TEXT,
    stage_timings_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_paper_evidence_extraction_items_run_index UNIQUE (run_id, item_index)
);

CREATE INDEX IF NOT EXISTS idx_paper_evidence_extraction_runs_status
    ON paper_evidence_extraction_runs (status);
CREATE INDEX IF NOT EXISTS idx_paper_evidence_extraction_items_run_index
    ON paper_evidence_extraction_items (run_id, item_index);
CREATE INDEX IF NOT EXISTS idx_paper_evidence_extraction_items_run_status
    ON paper_evidence_extraction_items (run_id, status);
