-- P1.3: Final function relation tables gain canonical function identity (term_id).
--
-- Design (P1.2): canonical Function identity lives in ontology_terms
-- (term_type='function', term_code 'ng:func:*'). Final function rows reference
-- it so promotion can carry term grounding instead of only function text.
--
-- Idempotent. Run via: psql -f 20260819_final_function_term_id.sql
-- (or the backend's apply-migration script). Final tables are currently empty
-- (0 rows), so no data backfill is needed.

ALTER TABLE final_region_functions
    ADD COLUMN IF NOT EXISTS term_id UUID REFERENCES ontology_terms(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_final_region_functions_term_id
    ON final_region_functions(term_id);

ALTER TABLE final_projection_functions
    ADD COLUMN IF NOT EXISTS term_id UUID REFERENCES ontology_terms(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_final_projection_functions_term_id
    ON final_projection_functions(term_id);

ALTER TABLE final_circuit_functions
    ADD COLUMN IF NOT EXISTS term_id UUID REFERENCES ontology_terms(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_final_circuit_functions_term_id
    ON final_circuit_functions(term_id);

-- NOTE: idx_ontology_terms_type_status deliberately NOT added.
-- Verified 2026-08-19: all 7,860 ontology_terms rows are term_type='function'
-- and idx_ontology_terms_status already covers the grounding lookup.
