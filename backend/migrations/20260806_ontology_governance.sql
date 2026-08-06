-- 20260806_ontology_governance.sql (idempotent)
-- Ontology governance workbench: soft-merge columns, alignment candidate
-- review table, and ontology change audit log.

ALTER TABLE ontology_terms ADD COLUMN IF NOT EXISTS replaced_by_term_id UUID REFERENCES ontology_terms(id);
ALTER TABLE ontology_terms ADD COLUMN IF NOT EXISTS merged_at TIMESTAMPTZ;
ALTER TABLE ontology_terms ADD COLUMN IF NOT EXISTS merged_by VARCHAR(64);
CREATE INDEX IF NOT EXISTS idx_ontology_terms_replaced_by ON ontology_terms (replaced_by_term_id);

CREATE TABLE IF NOT EXISTS ontology_alignment_candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_type VARCHAR(32) NOT NULL,
    target_id UUID NOT NULL,
    external_system VARCHAR(64) NOT NULL,
    external_id VARCHAR(256),
    external_iri VARCHAR(512) NOT NULL,
    external_label VARCHAR(512),
    match_type VARCHAR(16) NOT NULL,
    match_score NUMERIC,
    match_details JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    reviewed_by VARCHAR(64),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_ontology_alignment_candidate UNIQUE (target_type, target_id, external_system, external_iri)
);
CREATE INDEX IF NOT EXISTS idx_ontology_alignment_status ON ontology_alignment_candidates (status);

CREATE TABLE IF NOT EXISTS ontology_change_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action_type VARCHAR(64) NOT NULL,
    entity_type VARCHAR(64) NOT NULL,
    entity_id UUID NOT NULL,
    before_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    after_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    operator_id VARCHAR(64),
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ontology_change_logs_entity ON ontology_change_logs (entity_type, entity_id);
