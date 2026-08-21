-- O1.2: Function Concept hierarchy — ontology_term_relations (DAG edges).
--
-- Canonical direction: child --subclass_of--> parent.
-- Only `subclass_of` is materialized; broader/narrower/has_subclass are
-- derived by query direction. No parent_id column on ontology_terms — the
-- hierarchy is a DAG (multiple parents allowed), so edges live here.
--
-- subject/object MUST be ontology_terms (Function concepts only for now;
-- Brain Region partonomy deliberately does NOT belong in this table — see
-- O1.1 audit).

CREATE TABLE IF NOT EXISTS ontology_term_relations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    subject_term_id UUID NOT NULL REFERENCES ontology_terms(id) ON DELETE CASCADE,
    predicate       VARCHAR(64) NOT NULL,
    object_term_id  UUID NOT NULL REFERENCES ontology_terms(id) ON DELETE CASCADE,
    status          VARCHAR(16) NOT NULL DEFAULT 'proposed',
    source          VARCHAR(128),
    confidence      NUMERIC,
    provenance_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by      VARCHAR(64),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_ontology_relation_not_self CHECK (subject_term_id <> object_term_id),
    CONSTRAINT uq_ontology_relation_edge UNIQUE (subject_term_id, predicate, object_term_id)
);

CREATE INDEX IF NOT EXISTS idx_ontology_relation_subject
    ON ontology_term_relations(subject_term_id);
CREATE INDEX IF NOT EXISTS idx_ontology_relation_object
    ON ontology_term_relations(object_term_id);
CREATE INDEX IF NOT EXISTS idx_ontology_relation_predicate
    ON ontology_term_relations(predicate);
CREATE INDEX IF NOT EXISTS idx_ontology_relation_status
    ON ontology_term_relations(status);
