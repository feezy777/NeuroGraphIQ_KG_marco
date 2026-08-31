-- Gate 7B Phase 2A — Core Scientific Entity subtypes (9 tables)
--
-- Adds 9 first-class scientific entity subtype tables on top of the Phase 1
-- Identity Foundation:
--   brain_regions, cellular_neural_structures, neurobiological_processes,
--   functions, neurotransmitters, receptors, genes, diseases, symptoms
--
-- Modeling (Gate 7A freeze §D/§E): ALL 9 are shared-PK subtypes.
--   entity_pk BIGINT PRIMARY KEY -> kg_entities(entity_pk)
-- No second public ID, no own serial PK, no duplicated name/definition/status —
-- kg_entities remains the single identity / name / lifecycle truth.
--
-- External-database identifiers (HGNC/MONDO/HPO/ChEBI/ncbi/uniprot…) are NOT
-- duplicated here; they belong to entity_xrefs (Phase 1).
--
-- Shared subtype/entity_type consistency is enforced by ONE centralized trigger
-- function (infra.assert_entity_type) called by 9 one-line triggers.
--
-- FK delete policy: RESTRICT on kg_entities (lineage preserved); subtype-local
-- DERIVED-cache parents use ON DELETE SET NULL.

-- ===========================================================================
-- 1. Centralized subtype/entity_type consistency guard
-- ===========================================================================

CREATE OR REPLACE FUNCTION infra.assert_entity_type()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_type text;
BEGIN
    SELECT entity_type INTO v_type FROM kg_entities WHERE entity_pk = NEW.entity_pk;
    IF v_type IS NULL THEN
        RAISE EXCEPTION 'entity_pk % does not exist in kg_entities', NEW.entity_pk;
    END IF;
    IF v_type <> TG_ARGV[0] THEN
        RAISE EXCEPTION 'entity_type mismatch: entity_pk=% is type=% but % requires %',
            NEW.entity_pk, v_type, TG_TABLE_NAME, TG_ARGV[0];
    END IF;
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION infra.assert_entity_type() IS
    'Centralized shared-PK guard: BEFORE INSERT on each subtype table verifies that '
    'kg_entities.entity_type matches the expected subtype type (TG_ARGV[0]). Fail closed.';

-- ===========================================================================
-- 2. brain_regions
-- ===========================================================================

CREATE TABLE brain_regions (
    entity_pk           BIGINT PRIMARY KEY,
    region_category     VARCHAR(32),
    hemisphere          VARCHAR(16),
    granularity_level   VARCHAR(32),
    anatomical_level    VARCHAR(32),
    canonical_source_pk BIGINT,
    species_taxon_id    VARCHAR(32),
    parent_region_pk    BIGINT,
    hierarchy_depth     INTEGER,
    display_order       INTEGER,
    color_hex           VARCHAR(9),
    canonical_status    VARCHAR(24),
    remark              TEXT,

    CONSTRAINT fk_brain_regions_entity
        FOREIGN KEY (entity_pk) REFERENCES kg_entities (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_brain_regions_source
        FOREIGN KEY (canonical_source_pk) REFERENCES sources (source_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_brain_regions_parent
        FOREIGN KEY (parent_region_pk) REFERENCES brain_regions (entity_pk)
        ON DELETE SET NULL,
    CONSTRAINT ck_brain_regions_granularity_level CHECK (granularity_level IS NULL OR granularity_level IN (
        'G1_MACRO', 'G2_MESO_ANATOMICAL', 'G3_MESO_FINE', 'G4_MICROSTRUCTURAL_FINE'
    )),
    CONSTRAINT ck_brain_regions_hemisphere CHECK (hemisphere IS NULL OR hemisphere IN (
        'left', 'right', 'bilateral', 'midline', 'unspecified'
    )),
    CONSTRAINT ck_brain_regions_region_category CHECK (region_category IS NULL OR region_category IN (
        'cortical_region', 'cortical_parcel', 'gyrus', 'sulcus_region', 'subcortical_region',
        'nucleus', 'hippocampal_subfield', 'amygdalar_nucleus', 'thalamic_nucleus',
        'cerebellar_region', 'brainstem_region', 'other'
    ))
);

COMMENT ON TABLE brain_regions IS
    'Shared-PK subtype for entity_type=brain_region. Canonical identity/names/lifecycle live in kg_entities.';
COMMENT ON COLUMN brain_regions.granularity_level IS
    'Canonical granularity level: G1_MACRO / G2_MESO_ANATOMICAL / G3_MESO_FINE / G4_MICROSTRUCTURAL_FINE.';
COMMENT ON COLUMN brain_regions.parent_region_pk IS
    'DERIVED display cache only (not the hierarchy truth — that is a future brain_region_hierarchy_relations table).';

CREATE INDEX idx_brain_regions_granularity_level ON brain_regions (granularity_level);
CREATE INDEX idx_brain_regions_region_category ON brain_regions (region_category);
CREATE INDEX idx_brain_regions_canonical_source ON brain_regions (canonical_source_pk);

CREATE TRIGGER trg_brain_regions_entity_type
BEFORE INSERT ON brain_regions
FOR EACH ROW EXECUTE FUNCTION infra.assert_entity_type('brain_region');

-- ===========================================================================
-- 3. cellular_neural_structures
-- ===========================================================================

CREATE TABLE cellular_neural_structures (
    entity_pk          BIGINT PRIMARY KEY,
    structure_category VARCHAR(32),
    canonical_status   VARCHAR(24),
    remark             TEXT,
    CONSTRAINT fk_cns_entity
        FOREIGN KEY (entity_pk) REFERENCES kg_entities (entity_pk)
        ON DELETE RESTRICT
);

CREATE TRIGGER trg_cns_entity_type
BEFORE INSERT ON cellular_neural_structures
FOR EACH ROW EXECUTE FUNCTION infra.assert_entity_type('cellular_neural_structure');

-- ===========================================================================
-- 4. neurobiological_processes
-- ===========================================================================

CREATE TABLE neurobiological_processes (
    entity_pk          BIGINT PRIMARY KEY,
    process_category   VARCHAR(32),
    canonical_status   VARCHAR(24),
    remark             TEXT,
    CONSTRAINT fk_nbp_entity
        FOREIGN KEY (entity_pk) REFERENCES kg_entities (entity_pk)
        ON DELETE RESTRICT
);

CREATE TRIGGER trg_nbp_entity_type
BEFORE INSERT ON neurobiological_processes
FOR EACH ROW EXECUTE FUNCTION infra.assert_entity_type('neurobiological_process');

-- ===========================================================================
-- 5. functions
-- ===========================================================================

CREATE TABLE functions (
    entity_pk          BIGINT PRIMARY KEY,
    function_category  VARCHAR(16) NOT NULL,
    function_level     VARCHAR(24),
    parent_function_pk BIGINT,
    canonical_status   VARCHAR(24),
    remark             TEXT,

    CONSTRAINT fk_functions_entity
        FOREIGN KEY (entity_pk) REFERENCES kg_entities (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_functions_parent
        FOREIGN KEY (parent_function_pk) REFERENCES functions (entity_pk)
        ON DELETE SET NULL,
    CONSTRAINT ck_functions_category CHECK (function_category IN ('general', 'cognitive'))
);

COMMENT ON TABLE functions IS
    'Shared-PK subtype for entity_type=function. Function entity only — hierarchy is a future function_hierarchy_relations table; parent_function_pk is a DERIVED cache.';
COMMENT ON COLUMN functions.parent_function_pk IS
    'DERIVED display cache only (not the hierarchy truth).';

CREATE INDEX idx_functions_category ON functions (function_category);

CREATE TRIGGER trg_functions_entity_type
BEFORE INSERT ON functions
FOR EACH ROW EXECUTE FUNCTION infra.assert_entity_type('function');

-- ===========================================================================
-- 6. neurotransmitters
-- ===========================================================================

CREATE TABLE neurotransmitters (
    entity_pk              BIGINT PRIMARY KEY,
    chemical_formula       VARCHAR(64),
    molecular_weight       DOUBLE PRECISION,
    neurotransmitter_class VARCHAR(32),
    remark                 TEXT,
    CONSTRAINT fk_neurotransmitters_entity
        FOREIGN KEY (entity_pk) REFERENCES kg_entities (entity_pk)
        ON DELETE RESTRICT
);

CREATE TRIGGER trg_neurotransmitters_entity_type
BEFORE INSERT ON neurotransmitters
FOR EACH ROW EXECUTE FUNCTION infra.assert_entity_type('neurotransmitter');

-- ===========================================================================
-- 7. receptors
-- ===========================================================================

CREATE TABLE receptors (
    entity_pk          BIGINT PRIMARY KEY,
    receptor_family    VARCHAR(64),
    receptor_type      VARCHAR(64),
    remark             TEXT,
    CONSTRAINT fk_receptors_entity
        FOREIGN KEY (entity_pk) REFERENCES kg_entities (entity_pk)
        ON DELETE RESTRICT
);

CREATE TRIGGER trg_receptors_entity_type
BEFORE INSERT ON receptors
FOR EACH ROW EXECUTE FUNCTION infra.assert_entity_type('receptor');

-- ===========================================================================
-- 8. genes
-- ===========================================================================

CREATE TABLE genes (
    entity_pk            BIGINT PRIMARY KEY,
    approved_symbol      VARCHAR(32) NOT NULL,
    approved_name        TEXT,
    locus_group          VARCHAR(32),
    locus_type           VARCHAR(32),
    chromosome           VARCHAR(32),
    cytogenetic_location VARCHAR(32),
    gene_group           VARCHAR(64),
    hgnc_status          VARCHAR(24),
    remark               TEXT,
    CONSTRAINT fk_genes_entity
        FOREIGN KEY (entity_pk) REFERENCES kg_entities (entity_pk)
        ON DELETE RESTRICT
);

COMMENT ON TABLE genes IS
    'Shared-PK subtype for entity_type=gene. External gene IDs (HGNC/ncbi/ensembl/uniprot) live in entity_xrefs, not here.';

CREATE INDEX idx_genes_approved_symbol ON genes (approved_symbol);

CREATE TRIGGER trg_genes_entity_type
BEFORE INSERT ON genes
FOR EACH ROW EXECUTE FUNCTION infra.assert_entity_type('gene');

-- ===========================================================================
-- 9. diseases
-- ===========================================================================

CREATE TABLE diseases (
    entity_pk         BIGINT PRIMARY KEY,
    disease_category  VARCHAR(32),
    remark            TEXT,
    CONSTRAINT fk_diseases_entity
        FOREIGN KEY (entity_pk) REFERENCES kg_entities (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT ck_diseases_category CHECK (disease_category IS NULL OR disease_category IN (
        'neurodegenerative', 'psychiatric', 'neurological', 'other'
    ))
);

CREATE TRIGGER trg_diseases_entity_type
BEFORE INSERT ON diseases
FOR EACH ROW EXECUTE FUNCTION infra.assert_entity_type('disease');

-- ===========================================================================
-- 10. symptoms
-- ===========================================================================

CREATE TABLE symptoms (
    entity_pk         BIGINT PRIMARY KEY,
    symptom_category  VARCHAR(32),
    remark            TEXT,
    CONSTRAINT fk_symptoms_entity
        FOREIGN KEY (entity_pk) REFERENCES kg_entities (entity_pk)
        ON DELETE RESTRICT
);

CREATE TRIGGER trg_symptoms_entity_type
BEFORE INSERT ON symptoms
FOR EACH ROW EXECUTE FUNCTION infra.assert_entity_type('symptom');
