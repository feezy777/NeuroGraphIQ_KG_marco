-- Gate 7B Phase 3B — Connection Core (3 tables)
--
--   connections            — first-class reified Connection entity (shared-PK)
--   connection_endpoints   — canonical endpoint truth (connection <-> brain_region + role)
--   connection_observations— structured study-level observation of a Connection
--
-- Modeling (Gate 7A freeze §7/§E/§H):
--   * connections is a shared-PK subtype (entity_pk -> kg_entities, entity_type='connection').
--   * Canonical endpoint truth lives ONLY in connection_endpoints; connections does NOT
--     duplicate source_region/target_region FKs.
--   * derived BrainRegion->BrainRegion edges (structurallyConnectedTo / projectsTo /
--     functionallyConnectedTo / effectivelyConnectedTo) are projections — NOT created here.
--   * No circuits / region_mappings / assertion tables this round.

-- EP public-ID sequence: dict 18 §8 defines endpoint_id = NGIQ-EP-… (NN UNIQUE). Like SPAT,
-- this is a clear CURRENT public-ID requirement -> keep + add sequence + registry amendment.
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_ep_seq START WITH 1 INCREMENT BY 1 NO CYCLE;

-- ===========================================================================
-- 1. connections (shared-PK, entity_type='connection')
-- ===========================================================================

CREATE TABLE connections (
    entity_pk            BIGINT PRIMARY KEY,
    connection_class     VARCHAR(32) NOT NULL,
    directionality       VARCHAR(24) NOT NULL,
    laterality_relation  VARCHAR(24),
    granularity_scope    VARCHAR(32),
    derivation_type      VARCHAR(16) NOT NULL,
    canonical_status     VARCHAR(24),
    summary_en           TEXT,
    summary_zh           TEXT,
    evidence_count       INTEGER,
    publication_count    INTEGER,
    observation_count    INTEGER,
    confidence_summary   VARCHAR(64),
    first_reported_year  INTEGER,
    latest_evidence_year INTEGER,
    remark               TEXT,

    CONSTRAINT fk_connections_entity
        FOREIGN KEY (entity_pk) REFERENCES kg_entities (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT ck_connections_class CHECK (connection_class IN (
        'structural_connection', 'projection', 'functional_connectivity', 'effective_connectivity'
    )),
    CONSTRAINT ck_connections_directionality CHECK (directionality IN (
        'directed', 'non_directional', 'direction_unknown'
    )),
    CONSTRAINT ck_connections_derivation_type CHECK (derivation_type IN (
        'reported', 'inferred'
    )),
    CONSTRAINT ck_connections_granularity_scope CHECK (granularity_scope IS NULL OR granularity_scope IN (
        'G1_MACRO', 'G2_MESO_ANATOMICAL', 'G3_MESO_FINE', 'G4_MICROSTRUCTURAL_FINE',
        'CROSS_GRANULARITY', 'UNSPECIFIED'
    ))
);

COMMENT ON TABLE connections IS
    'Shared-PK subtype for entity_type=connection (first-class reified Connection). '
    'connection_class distinguishes structural_connection / projection / functional_connectivity / '
    'effective_connectivity. directionality V1 = directed / non_directional / direction_unknown '
    '(reciprocal is DERIVED display, expressed as two directed connections, not stored here). '
    'NO source/target region FKs — canonical endpoint truth lives in connection_endpoints. '
    'granularity_scope is DERIVED (from endpoint regions / aggregation context), not canonical truth.';

CREATE INDEX idx_connections_class ON connections (connection_class);
CREATE INDEX idx_connections_directionality ON connections (directionality);

CREATE TRIGGER trg_connections_entity_type
BEFORE INSERT ON connections
FOR EACH ROW EXECUTE FUNCTION infra.assert_entity_type('connection');

-- ===========================================================================
-- 2. connection_endpoints (canonical endpoint truth)
-- ===========================================================================

CREATE TABLE connection_endpoints (
    endpoint_pk     BIGSERIAL PRIMARY KEY,
    endpoint_id     VARCHAR(32) NOT NULL UNIQUE
        DEFAULT 'NGIQ-EP-' || lpad(nextval('infra.ngiq_ep_seq')::text, 8, '0'),
    connection_pk   BIGINT      NOT NULL,
    brain_region_pk BIGINT      NOT NULL,
    endpoint_role   VARCHAR(16) NOT NULL,
    display_order   INTEGER,
    remark          TEXT,

    CONSTRAINT fk_endpoint_connection
        FOREIGN KEY (connection_pk) REFERENCES connections (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_endpoint_region
        FOREIGN KEY (brain_region_pk) REFERENCES brain_regions (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT ck_endpoint_role CHECK (endpoint_role IN ('endpoint', 'source', 'target')),
    -- no exact duplicate (same connection, same region, same role)
    CONSTRAINT uq_endpoint_unique UNIQUE (connection_pk, brain_region_pk, endpoint_role)
);

COMMENT ON TABLE connection_endpoints IS
    'Canonical endpoint truth: which BrainRegions a Connection connects, and their roles. '
    'endpoint = no known biological direction; source/target = direction scientifically known. '
    'Record order is NOT source/target. Duplicate (connection,region,role) rejected; a region used '
    'in 2+ roles for one connection (obvious self-endpoint) rejected by trigger.';

CREATE INDEX idx_endpoint_connection ON connection_endpoints (connection_pk);
CREATE INDEX idx_endpoint_region ON connection_endpoints (brain_region_pk);

-- Obvious self-endpoint guard: no region may hold 2+ distinct roles within one connection
-- (e.g. source AND target). Runs AFTER the row is present so the full set is visible.
CREATE OR REPLACE FUNCTION infra.assert_no_self_endpoint()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_conflicts integer;
BEGIN
    SELECT count(*) INTO v_conflicts
    FROM (
        SELECT brain_region_pk
        FROM connection_endpoints
        WHERE connection_pk = NEW.connection_pk
        GROUP BY brain_region_pk
        HAVING count(DISTINCT endpoint_role) > 1
    ) x;
    IF v_conflicts > 0 THEN
        RAISE EXCEPTION
            'connection % has a brain region used in 2+ endpoint roles (self-endpoint not allowed)',
            NEW.connection_pk;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_no_self_endpoint
AFTER INSERT OR UPDATE ON connection_endpoints
FOR EACH ROW EXECUTE FUNCTION infra.assert_no_self_endpoint();

-- ===========================================================================
-- 3. connection_observations (study-level structured observation of a Connection)
-- ===========================================================================

CREATE TABLE connection_observations (
    observation_pk             BIGSERIAL PRIMARY KEY,
    observation_id             VARCHAR(32) NOT NULL UNIQUE
        DEFAULT 'NGIQ-COB-' || lpad(nextval('infra.ngiq_cob_seq')::text, 8, '0'),
    connection_pk              BIGINT      NOT NULL,
    study_pk                   BIGINT,
    publication_pk             BIGINT,
    evidence_pk                BIGINT,
    acquisition_modality       VARCHAR(24),
    analysis_method            VARCHAR(24),
    intervention_method        VARCHAR(24),
    condition_name_en          TEXT,
    condition_name_zh          TEXT,
    population_description_en  TEXT,
    population_description_zh  TEXT,
    sample_size                INTEGER,
    metric_name                TEXT,
    metric_value               TEXT,
    metric_unit                TEXT,
    effect_size                DOUBLE PRECISION,
    effect_size_type           VARCHAR(24),
    p_value                    DOUBLE PRECISION,
    ci_lower                   DOUBLE PRECISION,
    ci_upper                   DOUBLE PRECISION,
    direction_reported         VARCHAR(24),
    strength_reported          VARCHAR(24),
    source_text_original       TEXT,
    source_text_zh             TEXT,
    source_section             TEXT,
    source_page                TEXT,
    source_paragraph           TEXT,
    source_sentence            TEXT,
    source_table               TEXT,
    source_figure              TEXT,
    metadata_json              JSONB,
    remark                     TEXT,

    CONSTRAINT fk_observation_connection
        FOREIGN KEY (connection_pk) REFERENCES connections (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_observation_study
        FOREIGN KEY (study_pk) REFERENCES research_studies (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_observation_publication
        FOREIGN KEY (publication_pk) REFERENCES publications (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_observation_evidence
        FOREIGN KEY (evidence_pk) REFERENCES evidence (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT ck_observation_acquisition_modality CHECK (acquisition_modality IS NULL OR acquisition_modality IN (
        'tracer', 'histology', 'diffusion_mri', 'functional_mri', 'electrophysiology'
    )),
    CONSTRAINT ck_observation_analysis_method CHECK (analysis_method IS NULL OR analysis_method IN (
        'tractography', 'correlation', 'coherence', 'DCM', 'SEM', 'Granger'
    )),
    CONSTRAINT ck_observation_intervention_method CHECK (intervention_method IS NULL OR intervention_method IN (
        'lesion', 'TMS', 'DBS', 'optogenetics'
    ))
);

COMMENT ON TABLE connection_observations IS
    'Study-level structured observation/measurement of a Connection (Connection -> Observation -> '
    'Study/Evidence context). NOT the Connection itself, NOT an Evidence unit. '
    'direction_reported / strength_reported = the values the study REPORTED (observation measurement); '
    'they are NOT evidence_strength / evidence_directness (EvidenceLink target-specific, deferred). '
    'Scientific references only: research_studies / publications / evidence / sources.';

CREATE INDEX idx_observation_connection ON connection_observations (connection_pk);
CREATE INDEX idx_observation_study ON connection_observations (study_pk);
