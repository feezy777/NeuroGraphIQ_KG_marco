-- 20260806_ontology_layer_fix_columns.sql (idempotent)
-- Align ontology_term_synonyms / ontology_term_external_mappings with ORM models.

ALTER TABLE ontology_term_synonyms ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE ontology_term_external_mappings ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
