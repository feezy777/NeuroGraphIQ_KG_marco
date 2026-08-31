-- Gate 7B Phase 2B — Evidence & Atlas Scientific Entities (5 tables)
--
-- Adds 5 first-class scientific entity subtype tables on top of Phase 1+2A:
--   research_studies, publications, evidence, atlases, external_regions
--
-- Modeling (Gate 7A freeze §D/§E): all 5 are shared-PK subtypes —
--   entity_pk BIGINT PRIMARY KEY -> kg_entities(entity_pk) ON DELETE RESTRICT.
-- No second public ID / serial PK / duplicated name/status; kg_entities is the
-- single identity truth. Entity/type consistency reuses infra.assert_entity_type().
--
-- Frozen boundaries honored here:
--   * ResearchStudy != Publication (study activity vs document carrier).
--   * PMID/DOI are publication-specific retrieval fields (kept per CURRENT dict);
--     other external identifiers still live in entity_xrefs.
--   * Evidence is a concrete evidence unit, NOT a publication / PMID / LLM output.
--   * evidence_strength / evidence_directness are NOT evidence global attributes
--     (they are EvidenceLink target-specific context, deferred) — NOT added here.
--   * No evidence_links / knowledge_assertions / relation_definitions this round.
--   * Atlas is not granularity; external_regions stay separate from canonical
--     brain_regions (mapping is a later RegionMapping phase).

-- ===========================================================================
-- 1. research_studies (entity_type=research_study)
-- ===========================================================================

CREATE TABLE research_studies (
    entity_pk                 BIGINT PRIMARY KEY,
    study_design              VARCHAR(32),
    study_type                VARCHAR(32),
    population_description_en TEXT,
    population_description_zh TEXT,
    sample_size               INTEGER,
    species_scope             VARCHAR(64),
    condition_en              TEXT,
    condition_zh              TEXT,
    modality_summary          TEXT,
    study_start_date          DATE,
    study_end_date            DATE,
    remark                    TEXT,

    CONSTRAINT fk_research_studies_entity
        FOREIGN KEY (entity_pk) REFERENCES kg_entities (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT ck_research_studies_design CHECK (study_design IS NULL OR study_design IN (
        'cross-sectional', 'cohort', 'case-control', 'longitudinal', 'other'
    ))
);

CREATE TRIGGER trg_research_studies_entity_type
BEFORE INSERT ON research_studies
FOR EACH ROW EXECUTE FUNCTION infra.assert_entity_type('research_study');

-- ===========================================================================
-- 2. publications (entity_type=publication)
-- ===========================================================================

CREATE TABLE publications (
    entity_pk            BIGINT PRIMARY KEY,
    original_title       TEXT,
    original_language    VARCHAR(16),
    pmid                 VARCHAR(64),
    pmcid                VARCHAR(64),
    doi                  VARCHAR(64),
    pii                  VARCHAR(64),
    journal_name         TEXT,
    journal_abbreviation VARCHAR(32),
    issn                 VARCHAR(16),
    eissn                VARCHAR(16),
    volume               VARCHAR(32),
    issue                VARCHAR(32),
    pages                VARCHAR(32),
    publication_date     DATE,
    publication_year     INTEGER,
    publication_type     VARCHAR(32),
    abstract_en          TEXT,
    abstract_zh          TEXT,
    authors_text         TEXT,
    authors_json         JSONB,
    affiliations_json    JSONB,
    mesh_terms_json      JSONB,
    keywords_json        JSONB,
    grant_info_json      JSONB,
    conflict_of_interest TEXT,
    is_open_access       BOOLEAN,
    full_text_url        TEXT,
    citation_count       INTEGER,
    source_database      VARCHAR(32),
    remark               TEXT,

    CONSTRAINT fk_publications_entity
        FOREIGN KEY (entity_pk) REFERENCES kg_entities (entity_pk)
        ON DELETE RESTRICT
);

COMMENT ON TABLE publications IS
    'Shared-PK subtype for entity_type=publication. Document carrier (PubMed/Europe PMC). '
    'pmid/pmcid/doi/pii are publication-specific retrieval fields (may be NULL); '
    'other external IDs live in entity_xrefs.';

CREATE INDEX idx_publications_pmid ON publications (pmid);

CREATE TRIGGER trg_publications_entity_type
BEFORE INSERT ON publications
FOR EACH ROW EXECUTE FUNCTION infra.assert_entity_type('publication');

-- ===========================================================================
-- 3. evidence (entity_type=evidence)
-- ===========================================================================

CREATE TABLE evidence (
    entity_pk             BIGINT PRIMARY KEY,
    evidence_summary_en   TEXT,
    evidence_summary_zh   TEXT,
    publication_pk        BIGINT,
    study_pk              BIGINT,
    scientific_source_pk  BIGINT,
    evidence_text_original TEXT,
    evidence_text_zh      TEXT,
    source_section        TEXT,
    source_page           TEXT,
    source_paragraph      TEXT,
    source_sentence       TEXT,
    source_table          TEXT,
    source_figure         TEXT,
    acquisition_modality  VARCHAR(24),
    analysis_method       VARCHAR(24),
    intervention_method   VARCHAR(24),
    methodological_quality VARCHAR(24),
    sample_size           INTEGER,
    effect_size           DOUBLE PRECISION,
    effect_size_type      VARCHAR(32),
    p_value               DOUBLE PRECISION,
    ci_lower              DOUBLE PRECISION,
    ci_upper              DOUBLE PRECISION,
    model_confidence      DOUBLE PRECISION,
    extraction_method     TEXT,
    extractor_name        TEXT,
    extractor_version     TEXT,
    extraction_run_id     TEXT,
    human_review_status   VARCHAR(24),
    reviewer              VARCHAR(64),
    reviewed_at           TIMESTAMPTZ,
    provenance_json       JSONB,
    remark                TEXT,

    CONSTRAINT fk_evidence_entity
        FOREIGN KEY (entity_pk) REFERENCES kg_entities (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_evidence_publication
        FOREIGN KEY (publication_pk) REFERENCES publications (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_evidence_study
        FOREIGN KEY (study_pk) REFERENCES research_studies (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_evidence_scientific_source
        FOREIGN KEY (scientific_source_pk) REFERENCES sources (source_pk)
        ON DELETE RESTRICT,
    CONSTRAINT ck_evidence_acquisition_modality CHECK (acquisition_modality IS NULL OR acquisition_modality IN (
        'tracer', 'histology', 'diffusion_mri', 'functional_mri', 'electrophysiology'
    )),
    CONSTRAINT ck_evidence_analysis_method CHECK (analysis_method IS NULL OR analysis_method IN (
        'tractography', 'correlation', 'coherence', 'DCM', 'SEM', 'Granger'
    )),
    CONSTRAINT ck_evidence_intervention_method CHECK (intervention_method IS NULL OR intervention_method IN (
        'lesion', 'TMS', 'DBS', 'optogenetics'
    ))
);

COMMENT ON TABLE evidence IS
    'Shared-PK subtype for entity_type=evidence. A concrete evidence unit, not a publication/PMID/LLM output. '
    'evidence_strength/directness are NOT here (EvidenceLink target-specific, deferred). '
    'Scientific source = sources registry (LLM/provenance agents excluded).';

CREATE INDEX idx_evidence_publication_pk ON evidence (publication_pk);
CREATE INDEX idx_evidence_study_pk ON evidence (study_pk);
CREATE INDEX idx_evidence_scientific_source_pk ON evidence (scientific_source_pk);

CREATE TRIGGER trg_evidence_entity_type
BEFORE INSERT ON evidence
FOR EACH ROW EXECUTE FUNCTION infra.assert_entity_type('evidence');

-- ACTIVE Evidence source completeness (frozen §P):
-- record_status='active' requires publication_pk OR scientific_source_pk;
-- study_pk alone is insufficient; LLM/provenance agents are never scientific sources.
CREATE OR REPLACE FUNCTION infra.assert_evidence_active_source()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_status text;
BEGIN
    SELECT record_status INTO v_status FROM kg_entities WHERE entity_pk = NEW.entity_pk;
    IF v_status = 'active'
       AND NEW.publication_pk IS NULL
       AND NEW.scientific_source_pk IS NULL THEN
        RAISE EXCEPTION
            'ACTIVE evidence % requires publication_pk or scientific_source_pk (study_pk alone is insufficient)',
            NEW.entity_pk;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_evidence_active_source
BEFORE INSERT OR UPDATE ON evidence
FOR EACH ROW EXECUTE FUNCTION infra.assert_evidence_active_source();

-- ===========================================================================
-- 4. atlases (entity_type=atlas)
-- ===========================================================================

CREATE TABLE atlases (
    entity_pk               BIGINT PRIMARY KEY,
    atlas_family            VARCHAR(64),
    atlas_version           VARCHAR(32),
    species                 VARCHAR(64),
    parcellation_method     VARCHAR(64),
    reference_space         VARCHAR(32),
    resolution_json         JSONB,
    map_type                VARCHAR(32),
    region_count            INTEGER,
    release_date            DATE,
    release_year            INTEGER,
    publisher_or_institution TEXT,
    source_url              TEXT,
    download_url            TEXT,
    license                 VARCHAR(64),
    citation_pmid           TEXT,
    citation_doi            TEXT,
    remark                  TEXT,

    CONSTRAINT fk_atlases_entity
        FOREIGN KEY (entity_pk) REFERENCES kg_entities (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT ck_atlases_reference_space CHECK (reference_space IS NULL OR reference_space IN (
        'MNI152', 'Colin27', 'fsaverage', 'native', 'other'
    )),
    CONSTRAINT ck_atlases_map_type CHECK (map_type IS NULL OR map_type IN (
        'probabilistic', 'maximum_probability', 'label', 'other'
    ))
);

COMMENT ON TABLE atlases IS
    'Shared-PK subtype for entity_type=atlas. Scientific atlas resource (Brainnetome/Julich/HCP-MMP/AAL3...). '
    'An atlas is NOT a granularity level; G1-G4 are granularity vocabulary, not atlas types.';

CREATE INDEX idx_atlases_atlas_family ON atlases (atlas_family);

CREATE TRIGGER trg_atlases_entity_type
BEFORE INSERT ON atlases
FOR EACH ROW EXECUTE FUNCTION infra.assert_entity_type('atlas');

-- ===========================================================================
-- 5. external_regions (entity_type=external_region)
-- ===========================================================================

CREATE TABLE external_regions (
    entity_pk                 BIGINT PRIMARY KEY,
    atlas_pk                  BIGINT NOT NULL,
    source_region_id          VARCHAR(64),
    label_index               INTEGER,
    hemisphere                VARCHAR(16),
    parent_external_region_pk BIGINT,
    structure_path            TEXT,
    hierarchy_depth           INTEGER,
    display_order             INTEGER,
    reference_space           VARCHAR(32),
    granularity_level         VARCHAR(32),
    granularity_basis         VARCHAR(32),
    centroid_x_mm             DOUBLE PRECISION,
    centroid_y_mm             DOUBLE PRECISION,
    centroid_z_mm             DOUBLE PRECISION,
    volume_mm3                DOUBLE PRECISION,
    color_hex                 VARCHAR(9),
    metadata_json             JSONB,
    remark                    TEXT,

    CONSTRAINT fk_external_regions_entity
        FOREIGN KEY (entity_pk) REFERENCES kg_entities (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_external_regions_atlas
        FOREIGN KEY (atlas_pk) REFERENCES atlases (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_external_regions_parent
        FOREIGN KEY (parent_external_region_pk) REFERENCES external_regions (entity_pk)
        ON DELETE SET NULL,
    CONSTRAINT ck_external_regions_hemisphere CHECK (hemisphere IS NULL OR hemisphere IN (
        'left', 'right', 'bilateral', 'midline', 'unspecified'
    )),
    CONSTRAINT ck_external_regions_granularity_level CHECK (granularity_level IS NULL OR granularity_level IN (
        'G1_MACRO', 'G2_MESO_ANATOMICAL', 'G3_MESO_FINE', 'G4_MICROSTRUCTURAL_FINE'
    )),
    CONSTRAINT ck_external_regions_granularity_basis CHECK (granularity_basis IS NULL OR granularity_basis IN (
        'macro_anatomical', 'anatomical_parcellation', 'connectivity_parcellation',
        'multimodal_parcellation', 'functional_parcellation', 'cytoarchitectonic',
        'microstructural', 'manual_canonical', 'other'
    ))
);

COMMENT ON TABLE external_regions IS
    'Shared-PK subtype for entity_type=external_region. A region concept as defined by an external '
    'atlas/database (atlas-native label/context), NOT a canonical BrainRegion. Mapping to canonical '
    'BrainRegion is a later RegionMapping phase. granularity_level here = source atlas context only.';

CREATE INDEX idx_external_regions_atlas_pk ON external_regions (atlas_pk);
CREATE INDEX idx_external_regions_source_region_id ON external_regions (source_region_id);

CREATE TRIGGER trg_external_regions_entity_type
BEFORE INSERT ON external_regions
FOR EACH ROW EXECUTE FUNCTION infra.assert_entity_type('external_region');
