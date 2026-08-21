-- O1.3-A: Function hierarchy PARENT CANDIDATES (NOT formal relations).
--
-- This table stores deterministic retrieval candidates for human/LLM
-- judgment. It is deliberately separate from ontology_term_relations:
-- only after judgment may a candidate become a proposed hierarchy edge.
-- Never used as the hierarchy source of truth.

CREATE TABLE IF NOT EXISTS ontology_hierarchy_candidates (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    child_term_id        UUID NOT NULL REFERENCES ontology_terms(id) ON DELETE CASCADE,
    parent_term_id       UUID NOT NULL REFERENCES ontology_terms(id) ON DELETE CASCADE,
    candidate_score      NUMERIC,
    generation_method    VARCHAR(128),
    generation_reasons_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    lexical_score        NUMERIC,
    metadata_score       NUMERIC,
    usage_score          NUMERIC,
    synonym_score        NUMERIC,
    parent_status        VARCHAR(16),
    status               VARCHAR(24) NOT NULL DEFAULT 'pending',
    calibration_label    VARCHAR(32),
    generation_version   VARCHAR(64),
    created_by           VARCHAR(64),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_hierarchy_candidate_not_self CHECK (child_term_id <> parent_term_id),
    CONSTRAINT uq_hierarchy_candidate UNIQUE (child_term_id, parent_term_id, generation_version)
);

CREATE INDEX IF NOT EXISTS idx_hierarchy_candidate_child
    ON ontology_hierarchy_candidates(child_term_id);
CREATE INDEX IF NOT EXISTS idx_hierarchy_candidate_parent
    ON ontology_hierarchy_candidates(parent_term_id);
CREATE INDEX IF NOT EXISTS idx_hierarchy_candidate_status
    ON ontology_hierarchy_candidates(status);
CREATE INDEX IF NOT EXISTS idx_hierarchy_candidate_version
    ON ontology_hierarchy_candidates(generation_version);
