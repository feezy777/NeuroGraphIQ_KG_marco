-- 20260805_ontology_layer.sql (idempotent)
-- Ontology layer Phase 1: vocabulary registry, term registry, synonyms,
-- external mappings, grounding mapping; business-table term_id anchors.

CREATE TABLE IF NOT EXISTS ontology_vocabularies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(128) NOT NULL,
    vocab_type VARCHAR(32) NOT NULL,
    label_cn VARCHAR(256),
    label_en VARCHAR(256),
    description TEXT,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    seq INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_ontology_vocab_code_type UNIQUE (code, vocab_type)
);

CREATE TABLE IF NOT EXISTS ontology_terms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    term_code VARCHAR(128) NOT NULL UNIQUE,
    canonical_term_en VARCHAR(512) NOT NULL,
    canonical_term_cn VARCHAR(512),
    term_type VARCHAR(32) NOT NULL DEFAULT 'function',
    category VARCHAR(128),
    domain VARCHAR(128),
    role VARCHAR(128),
    effect_type VARCHAR(128),
    description TEXT,
    status VARCHAR(16) NOT NULL DEFAULT 'proposed',
    created_by VARCHAR(64) NOT NULL DEFAULT 'manual',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ontology_terms_status ON ontology_terms (status);

CREATE TABLE IF NOT EXISTS ontology_term_synonyms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    term_id UUID NOT NULL REFERENCES ontology_terms(id) ON DELETE CASCADE,
    synonym_text VARCHAR(512) NOT NULL,
    lang VARCHAR(8) NOT NULL DEFAULT 'en',
    match_type VARCHAR(16) NOT NULL,
    confidence NUMERIC,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_ontology_synonym UNIQUE (term_id, synonym_text, lang)
);

CREATE TABLE IF NOT EXISTS ontology_term_external_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    term_id UUID NOT NULL REFERENCES ontology_terms(id) ON DELETE CASCADE,
    external_system VARCHAR(64) NOT NULL,
    external_iri VARCHAR(512) NOT NULL,
    match_type VARCHAR(16) NOT NULL,
    confidence NUMERIC,
    verified_by VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_ontology_external UNIQUE (term_id, external_system, external_iri)
);

CREATE TABLE IF NOT EXISTS ontology_term_groundings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_type VARCHAR(32) NOT NULL,
    target_id UUID NOT NULL,
    term_id UUID REFERENCES ontology_terms(id) ON DELETE SET NULL,
    grounded_by VARCHAR(16) NOT NULL,
    confidence NUMERIC,
    created_by VARCHAR(64),
    grounded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_ontology_grounding_target UNIQUE (target_type, target_id)
);

ALTER TABLE mirror_circuit_functions ADD COLUMN IF NOT EXISTS term_id UUID REFERENCES ontology_terms(id);
ALTER TABLE mirror_projection_functions ADD COLUMN IF NOT EXISTS term_id UUID REFERENCES ontology_terms(id);
ALTER TABLE mirror_region_functions ADD COLUMN IF NOT EXISTS term_id UUID REFERENCES ontology_terms(id);
CREATE INDEX IF NOT EXISTS idx_mirror_circuit_functions_term ON mirror_circuit_functions (term_id);
CREATE INDEX IF NOT EXISTS idx_mirror_projection_functions_term ON mirror_projection_functions (term_id);
CREATE INDEX IF NOT EXISTS idx_mirror_region_functions_term ON mirror_region_functions (term_id);

ALTER TABLE candidate_brain_regions ADD COLUMN IF NOT EXISTS uberon_iri VARCHAR(512);
ALTER TABLE candidate_brain_regions ADD COLUMN IF NOT EXISTS nifstd_iri VARCHAR(512);
ALTER TABLE candidate_brain_regions ADD COLUMN IF NOT EXISTS alignment_status VARCHAR(32) NOT NULL DEFAULT 'not_aligned';

INSERT INTO ontology_vocabularies (code, vocab_type, label_en, seq) VALUES
('involved_in','relation_type','involved_in',10),
('associated_with','relation_type','associated_with',20),
('necessary_for','relation_type','necessary_for',30),
('modulates','relation_type','modulates',40),
('participates_in','relation_type','participates_in',50),
('uncertain_association','relation_type','uncertain_association',60),
('unknown','relation_type','unknown',70),
('motor','category','motor',10),
('sensory','category','sensory',20),
('visual','category','visual',30),
('auditory','category','auditory',40),
('language','category','language',50),
('memory','category','memory',60),
('emotion','category','emotion',70),
('executive_control','category','executive_control',80),
('attention','category','attention',90),
('autonomic','category','autonomic',100),
('default_mode','category','default_mode',110),
('salience','category','salience',120),
('reward','category','reward',130),
('cognitive','category','cognitive',140),
('unknown','category','unknown',150),
('structurally_connects_to','predicate','structurally_connects_to',10),
('functionally_connects_to','predicate','functionally_connects_to',20),
('effectively_connects_to','predicate','effectively_connects_to',30),
('projects_to','predicate','projects_to',40),
('associated_with','predicate','associated_with',50),
('coactivates_with','predicate','coactivates_with',60),
('has_uncertain_connection_to','predicate','has_uncertain_connection_to',70),
('has_participant_region','predicate','has_participant_region',80),
('has_ordered_participant','predicate','has_ordered_participant',90),
('instance_of_circuit_type','predicate','instance_of_circuit_type',100),
('associated_with_function','predicate','associated_with_function',110),
('involved_in_function','predicate','involved_in_function',120),
('necessary_for_function','predicate','necessary_for_function',130),
('modulates_function','predicate','modulates_function',140),
('participates_in_process','predicate','participates_in_process',150),
('close_match','predicate','close_match',160),
('partial_match','predicate','partial_match',170),
('related_to','predicate','related_to',180),
('not_same_as','predicate','not_same_as',190),
('supported_by_evidence','predicate','supported_by_evidence',200),
('generated_by_llm_run','predicate','generated_by_llm_run',210),
('confirmed_by_reviewer','predicate','confirmed_by_reviewer',220)
ON CONFLICT (code, vocab_type) DO NOTHING;

UPDATE mirror_region_functions SET function_category='unknown'
WHERE function_category NOT IN ('motor','sensory','visual','auditory','language','memory','emotion','executive_control','attention','autonomic','default_mode','salience','reward','cognitive','unknown');
UPDATE mirror_region_functions SET relation_type='unknown'
WHERE relation_type NOT IN ('involved_in','associated_with','necessary_for','modulates','participates_in','uncertain_association','unknown');
UPDATE mirror_projection_functions SET function_category='unknown'
WHERE function_category NOT IN ('motor','sensory','visual','auditory','language','memory','emotion','executive_control','attention','autonomic','default_mode','salience','reward','cognitive','unknown');
UPDATE mirror_projection_functions SET relation_type='unknown'
WHERE relation_type NOT IN ('involved_in','associated_with','necessary_for','modulates','participates_in','uncertain_association','unknown');

ALTER TABLE mirror_region_functions DROP CONSTRAINT IF EXISTS chk_mirror_function_category;
ALTER TABLE mirror_region_functions DROP CONSTRAINT IF EXISTS chk_mirror_function_relation_type;
ALTER TABLE mirror_projection_functions DROP CONSTRAINT IF EXISTS chk_mirror_projection_function_category;
ALTER TABLE mirror_projection_functions DROP CONSTRAINT IF EXISTS chk_mirror_projection_function_relation_type;
