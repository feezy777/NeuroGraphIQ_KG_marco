-- Gate 7B Phase 3A — Hierarchy, Spatial & Granularity Integration (4 tables)
--
--   brain_region_hierarchy_relations   — canonical BrainRegion anatomical hierarchy truth
--   function_hierarchy_relations       — canonical Function concept hierarchy truth
--   brain_region_spatial_representations — a BrainRegion's spatial representation in an atlas context
--   brain_region_aggregation_mappings  — fine -> coarse cross-granularity integration mapping
--
-- These are relation/link/reified tables (NOT kg_entities subtypes): they have their own
-- *_pk and NGIQ *_id, and reference region/function entities by their shared-PK entity_pk.
--
-- Frozen boundaries honored:
--   * partOf/subfieldOf (hierarchy) vs aggregation mapping vs spatial overlap are kept separate;
--     aggregation mapping NEVER auto-creates partOf.
--   * parent_region_pk / parent_function_pk on the entity tables remain DERIVED caches only.
--   * No spatial relation table / no spatiallyOverlaps/adjacentTo/locatedIn rows this round.
--   * No region_mappings (ExternalRegion->RegionMapping->BrainRegion) this round.

-- SPAT public-ID sequence: dict 18 §6 defines NGIQ-SPAT-… but the frozen 29-prefix registry
-- omits it. Added here to support spatial_id (documented as MODERATE; recommend a future
-- prefix-registry amendment to officially include SPAT).
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_spat_seq START WITH 1 INCREMENT BY 1 NO CYCLE;

-- ===========================================================================
-- 1. brain_region_hierarchy_relations (canonical anatomical hierarchy truth)
-- ===========================================================================

CREATE TABLE brain_region_hierarchy_relations (
    hierarchy_pk          BIGSERIAL PRIMARY KEY,
    hierarchy_relation_id VARCHAR(32) NOT NULL UNIQUE
        DEFAULT 'NGIQ-BRH-' || lpad(nextval('infra.ngiq_brh_seq')::text, 8, '0'),
    parent_region_pk      BIGINT      NOT NULL,
    child_region_pk       BIGINT      NOT NULL,
    relation_type         VARCHAR(32) NOT NULL,
    hierarchy_source      VARCHAR(24),
    is_canonical          BOOLEAN     NOT NULL DEFAULT true,
    confidence            DOUBLE PRECISION,
    source_pk             BIGINT,
    remark                TEXT,

    CONSTRAINT fk_brh_parent
        FOREIGN KEY (parent_region_pk) REFERENCES brain_regions (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_brh_child
        FOREIGN KEY (child_region_pk) REFERENCES brain_regions (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_brh_source
        FOREIGN KEY (source_pk) REFERENCES sources (source_pk)
        ON DELETE RESTRICT,
    CONSTRAINT ck_brh_relation_type CHECK (relation_type IN ('part_of', 'subfield_of')),
    CONSTRAINT ck_brh_hierarchy_source CHECK (hierarchy_source IS NULL OR hierarchy_source IN (
        'ontology', 'atlas', 'curated'
    )),
    -- no self relation (A part_of A) — full cycle detection deferred per CURRENT
    CONSTRAINT ck_brh_no_self CHECK (parent_region_pk <> child_region_pk)
);

COMMENT ON TABLE brain_region_hierarchy_relations IS
    'Canonical BrainRegion anatomical hierarchy truth (part_of / subfield_of). '
    'brain_regions.parent_region_pk is only a DERIVED cache, not truth. '
    'Aggregation mappings / spatial overlap do NOT imply part_of.';

CREATE INDEX idx_brh_parent ON brain_region_hierarchy_relations (parent_region_pk);
CREATE INDEX idx_brh_child ON brain_region_hierarchy_relations (child_region_pk);
CREATE INDEX idx_brh_relation_type ON brain_region_hierarchy_relations (relation_type);

-- ===========================================================================
-- 2. function_hierarchy_relations (canonical Function concept hierarchy truth)
-- ===========================================================================

CREATE TABLE function_hierarchy_relations (
    hierarchy_pk          BIGSERIAL PRIMARY KEY,
    hierarchy_relation_id VARCHAR(32) NOT NULL UNIQUE
        DEFAULT 'NGIQ-FHR-' || lpad(nextval('infra.ngiq_fhr_seq')::text, 8, '0'),
    parent_function_pk    BIGINT      NOT NULL,
    child_function_pk     BIGINT      NOT NULL,
    relation_type         VARCHAR(24) NOT NULL,
    hierarchy_source      VARCHAR(24),
    is_canonical          BOOLEAN     NOT NULL DEFAULT true,
    confidence            DOUBLE PRECISION,
    source_pk             BIGINT,
    remark                TEXT,

    CONSTRAINT fk_fhr_parent
        FOREIGN KEY (parent_function_pk) REFERENCES functions (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_fhr_child
        FOREIGN KEY (child_function_pk) REFERENCES functions (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_fhr_source
        FOREIGN KEY (source_pk) REFERENCES sources (source_pk)
        ON DELETE RESTRICT,
    CONSTRAINT ck_fhr_relation_type CHECK (relation_type IN ('subclass_of', 'part_of')),
    CONSTRAINT ck_fhr_hierarchy_source CHECK (hierarchy_source IS NULL OR hierarchy_source IN (
        'ontology', 'curated'
    )),
    CONSTRAINT ck_fhr_no_self CHECK (parent_function_pk <> child_function_pk)
);

COMMENT ON TABLE function_hierarchy_relations IS
    'Canonical Function concept hierarchy truth (subclass_of / part_of). '
    'subclass_of maps to OWL subFunctionOf in projection (NOT rdfs:subClassOf — Function '
    'concepts are ABox Individuals, not OWL Classes). Function part_of is DB-only (OWL DEFER). '
    'functions.parent_function_pk is only a DERIVED cache.';

CREATE INDEX idx_fhr_parent ON function_hierarchy_relations (parent_function_pk);
CREATE INDEX idx_fhr_child ON function_hierarchy_relations (child_function_pk);

-- ===========================================================================
-- 3. brain_region_spatial_representations (a BrainRegion's spatial rep)
-- ===========================================================================

CREATE TABLE brain_region_spatial_representations (
    spatial_pk      BIGSERIAL PRIMARY KEY,
    spatial_id      VARCHAR(32) NOT NULL UNIQUE
        DEFAULT 'NGIQ-SPAT-' || lpad(nextval('infra.ngiq_spat_seq')::text, 8, '0'),
    brain_region_pk BIGINT      NOT NULL,
    atlas_pk        BIGINT,
    reference_space VARCHAR(32),
    atlas_version   VARCHAR(32),
    hemisphere      VARCHAR(16),
    label_index     INTEGER,
    map_type        VARCHAR(32),
    centroid_x_mm   DOUBLE PRECISION,
    centroid_y_mm   DOUBLE PRECISION,
    centroid_z_mm   DOUBLE PRECISION,
    bbox_json       JSONB,
    volume_mm3      DOUBLE PRECISION,
    voxel_count     INTEGER,
    resolution_json JSONB,
    mask_uri        TEXT,
    mesh_uri        TEXT,
    color_hex       VARCHAR(9),
    source_pk       BIGINT,
    metadata_json   JSONB,
    remark          TEXT,

    CONSTRAINT fk_spatial_region
        FOREIGN KEY (brain_region_pk) REFERENCES brain_regions (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_spatial_atlas
        FOREIGN KEY (atlas_pk) REFERENCES atlases (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_spatial_source
        FOREIGN KEY (source_pk) REFERENCES sources (source_pk)
        ON DELETE RESTRICT,
    CONSTRAINT ck_spatial_reference_space CHECK (reference_space IS NULL OR reference_space IN (
        'MNI152', 'Colin27', 'fsaverage', 'native', 'other'
    )),
    CONSTRAINT ck_spatial_hemisphere CHECK (hemisphere IS NULL OR hemisphere IN (
        'left', 'right', 'bilateral', 'midline', 'unspecified'
    )),
    CONSTRAINT ck_spatial_map_type CHECK (map_type IS NULL OR map_type IN (
        'probabilistic', 'maximum_probability', 'label', 'other'
    ))
);

COMMENT ON TABLE brain_region_spatial_representations IS
    'A spatial representation of a canonical BrainRegion in a specific atlas/version/reference-space. '
    'NOT the BrainRegion itself (concept != representation). No spatial-relation table / no '
    'spatiallyOverlaps/adjacentTo/locatedIn this round. Geometry lives here in the DB layer.';

CREATE INDEX idx_spatial_region ON brain_region_spatial_representations (brain_region_pk);
CREATE INDEX idx_spatial_atlas ON brain_region_spatial_representations (atlas_pk);

-- ===========================================================================
-- 4. brain_region_aggregation_mappings (fine -> coarse integration mapping)
-- ===========================================================================

CREATE TABLE brain_region_aggregation_mappings (
    mapping_pk              BIGSERIAL PRIMARY KEY,
    mapping_id              VARCHAR(32) NOT NULL UNIQUE
        DEFAULT 'NGIQ-BRAM-' || lpad(nextval('infra.ngiq_bram_seq')::text, 8, '0'),
    source_region_pk        BIGINT      NOT NULL,
    target_region_pk        BIGINT      NOT NULL,
    mapping_relation        VARCHAR(32) NOT NULL,
    mapping_method          VARCHAR(32),
    source_granularity_level VARCHAR(32),
    target_granularity_level VARCHAR(32),
    source_coverage_ratio   DOUBLE PRECISION,
    target_coverage_ratio   DOUBLE PRECISION,
    spatial_overlap_ratio   DOUBLE PRECISION,
    mapping_confidence      DOUBLE PRECISION,
    rollup_eligible         BOOLEAN     NOT NULL DEFAULT false,
    is_primary_rollup       BOOLEAN     NOT NULL DEFAULT false,
    scientific_source_pk    BIGINT,
    provenance_json         JSONB,
    record_status           VARCHAR(16) NOT NULL,
    remark                  TEXT,

    CONSTRAINT fk_agg_source
        FOREIGN KEY (source_region_pk) REFERENCES brain_regions (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_agg_target
        FOREIGN KEY (target_region_pk) REFERENCES brain_regions (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_agg_scientific_source
        FOREIGN KEY (scientific_source_pk) REFERENCES sources (source_pk)
        ON DELETE RESTRICT,
    CONSTRAINT ck_agg_mapping_relation CHECK (mapping_relation IN (
        'exact_aggregate', 'contained_in', 'dominant_overlap', 'partial_overlap',
        'composite_component', 'approximate', 'manual_curated', 'unresolved'
    )),
    CONSTRAINT ck_agg_mapping_method CHECK (mapping_method IS NULL OR mapping_method IN (
        'authoritative_anatomical_mapping', 'atlas_crosswalk', 'spatial_overlap',
        'hierarchy_inference', 'expert_manual', 'multimodal_consensus', 'hybrid'
    )),
    CONSTRAINT ck_agg_record_status CHECK (record_status IN (
        'proposed', 'active', 'deprecated', 'merged'
    )),
    -- no forced tree: allow 1:1 / N:1 / 1:N / N:N — no UNIQUE on source/target
    CONSTRAINT ck_agg_no_self CHECK (source_region_pk <> target_region_pk)
);

COMMENT ON TABLE brain_region_aggregation_mappings IS
    'Cross-granularity integration mapping: finer canonical BrainRegion -> coarser canonical '
    'BrainRegion. NOT anatomical partOf, NOT ExternalRegion RegionMapping, NOT spatial overlap. '
    'source must be strictly finer than target (G4>G3>G2>G1, enforced by trigger). '
    'rollup_eligible=true is the only path for future Connection/Circuit roll-up; '
    'is_primary_rollup marks the human-vetted preferred path (does not delete other mappings). '
    'Aggregation NEVER auto-creates partOf.';

CREATE INDEX idx_agg_source ON brain_region_aggregation_mappings (source_region_pk);
CREATE INDEX idx_agg_target ON brain_region_aggregation_mappings (target_region_pk);
CREATE INDEX idx_agg_rollup_eligible ON brain_region_aggregation_mappings (rollup_eligible);

-- Granularity direction guard: source strictly finer than target (uses brain_regions.granularity_level
-- as canonical truth; unknown/missing granularity fails closed; same-level and reverse rejected).
CREATE OR REPLACE FUNCTION infra.assert_aggregation_granularity()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_src text;
    v_tgt text;
    v_srank integer;
    v_trank integer;
BEGIN
    SELECT granularity_level INTO v_src FROM brain_regions WHERE entity_pk = NEW.source_region_pk;
    SELECT granularity_level INTO v_tgt FROM brain_regions WHERE entity_pk = NEW.target_region_pk;
    IF v_src IS NULL OR v_tgt IS NULL THEN
        RAISE EXCEPTION 'aggregation mapping requires granularity_level on both source and target'
            ' (source=% target=%)', NEW.source_region_pk, NEW.target_region_pk;
    END IF;
    v_srank := CASE v_src WHEN 'G1_MACRO' THEN 1 WHEN 'G2_MESO_ANATOMICAL' THEN 2
                          WHEN 'G3_MESO_FINE' THEN 3 WHEN 'G4_MICROSTRUCTURAL_FINE' THEN 4 ELSE NULL END;
    v_trank := CASE v_tgt WHEN 'G1_MACRO' THEN 1 WHEN 'G2_MESO_ANATOMICAL' THEN 2
                          WHEN 'G3_MESO_FINE' THEN 3 WHEN 'G4_MICROSTRUCTURAL_FINE' THEN 4 ELSE NULL END;
    IF v_srank IS NULL OR v_trank IS NULL THEN
        RAISE EXCEPTION 'unknown granularity_level on source/target region';
    END IF;
    IF v_srank <= v_trank THEN
        RAISE EXCEPTION 'aggregation source must be strictly finer than target'
            ' (source=% level=% ; target=% level=%)', NEW.source_region_pk, v_src, NEW.target_region_pk, v_tgt;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_agg_granularity
BEFORE INSERT OR UPDATE ON brain_region_aggregation_mappings
FOR EACH ROW EXECUTE FUNCTION infra.assert_aggregation_granularity();
