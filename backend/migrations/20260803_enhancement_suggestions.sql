-- 20260803_enhancement_suggestions.sql
-- Tier 2 enhancement suggestions (LLM-generated content pending human review)

CREATE TABLE IF NOT EXISTS mirror_enhancement_suggestions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    circuit_id UUID NOT NULL,
    validation_run_id UUID,
    field_path TEXT NOT NULL,
    suggested_value JSONB,
    original_value JSONB,
    suggestion_type TEXT NOT NULL,
    suggestion_source TEXT NOT NULL DEFAULT 'deepseek',
    confidence REAL,
    approval_status TEXT NOT NULL DEFAULT 'proposed',
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_enhancement_circuit ON mirror_enhancement_suggestions(circuit_id);
CREATE INDEX IF NOT EXISTS idx_enhancement_status ON mirror_enhancement_suggestions(approval_status);

ALTER TABLE mirror_region_circuits
    ADD COLUMN IF NOT EXISTS quality_score REAL DEFAULT NULL;
