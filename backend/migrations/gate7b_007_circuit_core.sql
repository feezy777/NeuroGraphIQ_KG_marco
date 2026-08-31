-- Gate 7B Phase 4 — Circuit Core (3 tables)
--
--   circuits                     — first-class reified Circuit entity (shared-PK)
--   circuit_region_memberships   — which BrainRegions a Circuit includes (link table)
--   circuit_connection_memberships — which canonical Connections a Circuit includes
--                                    (SHARED-PK first-class, evidence-targetable)
--
-- Modeling:
--   * circuits is a shared-PK subtype (entity_type='circuit'); public NGIQ ID = kg_entities.entity_id.
--   * circuit_connection_membership is in the frozen entity_type vocabulary (16 §1), the prefix
--     registry marks it first-class/reified/evidence-targetable, the OWL manifest has
--     CircuitConnectionMembership as a formal Class, and the Evidence entity-target whitelist
--     requires it to be an identity-bearing kg_entities entity. Therefore it is implemented as a
--     shared-PK subtype (entity_pk -> kg_entities, entity_type='circuit_connection_membership').
--     The dict 18 §12 "membership_pk BIGSERIAL" representation is treated as historical drift.
--   * circuit_region_membership is NOT in the entity_type vocabulary -> plain link table
--     (membership_pk + NGIQ-CRM id).
--   * Circuit = biological/functional circuit, NOT a graph cycle: no closed_loop requirement,
--     no ">=3 regions / >=2 connections" hard constraint, no auto-generation from graph cycles.

-- ===========================================================================
-- 1. circuits (shared-PK, entity_type='circuit')
-- ===========================================================================

CREATE TABLE circuits (
    entity_pk            BIGINT PRIMARY KEY,
    construction_mode    VARCHAR(24),
    derivation_type      VARCHAR(16) NOT NULL,
    granularity_scope    VARCHAR(32),
    topology_summary_en  TEXT,
    topology_summary_zh  TEXT,
    is_closed_loop       BOOLEAN,
    has_feedback         BOOLEAN,
    has_recurrence       BOOLEAN,
    region_count         INTEGER,
    connection_count     INTEGER,
    evidence_count       INTEGER,
    publication_count    INTEGER,
    canonical_status     VARCHAR(24),
    confidence_summary   VARCHAR(64),
    first_reported_year  INTEGER,
    latest_evidence_year INTEGER,
    remark               TEXT,

    CONSTRAINT fk_circuits_entity
        FOREIGN KEY (entity_pk) REFERENCES kg_entities (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT ck_circuits_construction_mode CHECK (construction_mode IS NULL OR construction_mode IN (
        'composed', 'reconstructed'
    )),
    CONSTRAINT ck_circuits_derivation_type CHECK (derivation_type IN (
        'reported', 'inferred'
    )),
    CONSTRAINT ck_circuits_granularity_scope CHECK (granularity_scope IS NULL OR granularity_scope IN (
        'G1_MACRO', 'G2_MESO_ANATOMICAL', 'G3_MESO_FINE', 'G4_MICROSTRUCTURAL_FINE',
        'MIXED', 'UNSPECIFIED'
    ))
);

COMMENT ON TABLE circuits IS
    'Shared-PK subtype for entity_type=circuit. A biological/functional neural circuit — NOT a graph '
    'cycle. is_closed_loop / region_count / connection_count are descriptive/derived attributes only; '
    'no closed_loop requirement and no >=3 regions / >=2 connections hard constraint. derivation_type '
    'reported/inferred distinguishes source-reported vs inferred candidate. granularity_scope is DERIVED.';

CREATE INDEX idx_circuits_construction_mode ON circuits (construction_mode);
CREATE INDEX idx_circuits_derivation_type ON circuits (derivation_type);

CREATE TRIGGER trg_circuits_entity_type
BEFORE INSERT ON circuits
FOR EACH ROW EXECUTE FUNCTION infra.assert_entity_type('circuit');

-- ===========================================================================
-- 2. circuit_region_memberships (link table, NGIQ-CRM)
-- ===========================================================================

CREATE TABLE circuit_region_memberships (
    membership_pk         BIGSERIAL PRIMARY KEY,
    membership_id         VARCHAR(32) NOT NULL UNIQUE
        DEFAULT 'NGIQ-CRM-' || lpad(nextval('infra.ngiq_crm_seq')::text, 8, '0'),
    circuit_pk            BIGINT      NOT NULL,
    brain_region_pk       BIGINT      NOT NULL,
    role_en               TEXT,
    role_zh               TEXT,
    sequence_order        INTEGER,
    is_core_member        BOOLEAN,
    membership_confidence DOUBLE PRECISION,
    remark                TEXT,

    CONSTRAINT fk_crm_circuit
        FOREIGN KEY (circuit_pk) REFERENCES circuits (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_crm_region
        FOREIGN KEY (brain_region_pk) REFERENCES brain_regions (entity_pk)
        ON DELETE RESTRICT,
    -- prevent exact-duplicate membership (a region is a member of a circuit at most once)
    CONSTRAINT uq_crm_membership UNIQUE (circuit_pk, brain_region_pk)
);

COMMENT ON TABLE circuit_region_memberships IS
    'Canonical Circuit -> includesRegion -> BrainRegion membership (link table). '
    'Circuit membership does NOT imply BrainRegion partOf / parent_region_pk changes. '
    'Duplicate (circuit, region) membership rejected.';

CREATE INDEX idx_crm_circuit ON circuit_region_memberships (circuit_pk);
CREATE INDEX idx_crm_region ON circuit_region_memberships (brain_region_pk);

-- ===========================================================================
-- 3. circuit_connection_memberships (SHARED-PK first-class, evidence-targetable)
-- ===========================================================================

CREATE TABLE circuit_connection_memberships (
    entity_pk             BIGINT PRIMARY KEY,
    circuit_pk            BIGINT      NOT NULL,
    connection_pk         BIGINT      NOT NULL,
    step_order            INTEGER,
    branch_group          VARCHAR(32),
    role_en               TEXT,
    role_zh               TEXT,
    is_required           BOOLEAN,
    is_core_connection    BOOLEAN,
    membership_confidence DOUBLE PRECISION,
    remark                TEXT,

    CONSTRAINT fk_ccm_entity
        FOREIGN KEY (entity_pk) REFERENCES kg_entities (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_ccm_circuit
        FOREIGN KEY (circuit_pk) REFERENCES circuits (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_ccm_connection
        FOREIGN KEY (connection_pk) REFERENCES connections (entity_pk)
        ON DELETE RESTRICT,
    -- a canonical Connection participates in a Circuit at most once
    CONSTRAINT uq_ccm_membership UNIQUE (circuit_pk, connection_pk)
);

COMMENT ON TABLE circuit_connection_memberships IS
    'SHARED-PK first-class membership (entity_pk -> kg_entities, entity_type='
    'circuit_connection_membership). Canonical Circuit -> hasConnectionMembership -> '
    'CircuitConnectionMembership, and membership -> membershipConnection -> Connection. '
    'It is the ONLY circuit->connection canonical truth (hasConnection is a derived convenience). '
    'Does NOT copy Connection endpoint/class/directionality truth. Evidence-targetable.';

CREATE INDEX idx_ccm_circuit ON circuit_connection_memberships (circuit_pk);
CREATE INDEX idx_ccm_connection ON circuit_connection_memberships (connection_pk);

CREATE TRIGGER trg_ccm_entity_type
BEFORE INSERT ON circuit_connection_memberships
FOR EACH ROW EXECUTE FUNCTION infra.assert_entity_type('circuit_connection_membership');
