-- 20260806_ontology_audit_runs.sql (idempotent)
-- Track ontology audit runs (dashboard "last audit" + progress).

CREATE TABLE IF NOT EXISTS ontology_audit_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status VARCHAR(16) NOT NULL DEFAULT 'running',
    granularity_level VARCHAR(32),
    summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    created_by VARCHAR(64),
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_ontology_audit_runs_status ON ontology_audit_runs (status);
