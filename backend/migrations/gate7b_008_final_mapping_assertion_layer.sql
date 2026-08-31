-- Gate 7B Phase 5 — Region Mapping & Assertion / Evidence Link Layer (final 4 tables)
--
--   region_mappings       — first-class reified RegionMapping (ExternalRegion -> canonical BrainRegion)
--   relation_definitions  — PostgreSQL predicate registry (participatesIn / modulates / …)
--   knowledge_assertions  — DB-only ordinary relation claims (NOT OWL Core)
--   evidence_links        — Evidence -> assertion OR Evidence -> allowed reified entity target (XOR)
--
-- Completes the frozen 32-table scientific schema.
--
-- Frozen boundaries honored:
--   * RegionMapping (ExternalRegion->BrainRegion) is SEPARATE from brain_region_aggregation_mappings
--     (fine canonical -> coarse canonical). No auto partOf / no auto merge.
--   * KnowledgeAssertion is DB-only; Connection/Circuit/RegionMapping/CCM already have canonical
--     reified models and are NOT duplicated as assertions.
--   * EvidenceLink XOR is DB-enforced (exactly one of assertion_pk / entity_pk).
--   * Entity evidence whitelist = connection / circuit / region_mapping / circuit_connection_membership
--     (enforced by trigger against kg_entities.entity_type).
--   * evidence_strength / evidence_directness live in evidence_links (target-specific context).
--   * No evidence inheritance; no assertion_evidence_links.

-- ===========================================================================
-- 1. relation_definitions (predicate registry)
-- ===========================================================================

CREATE TABLE relation_definitions (
    predicate_pk        BIGSERIAL PRIMARY KEY,
    predicate_id        VARCHAR(32) NOT NULL UNIQUE
        DEFAULT 'NGIQ-PRED-' || lpad(nextval('infra.ngiq_pred_seq')::text, 8, '0'),
    predicate_key       VARCHAR(64) NOT NULL UNIQUE,
    name_en             TEXT NOT NULL,
    name_zh             TEXT NOT NULL,
    description_en      TEXT,
    description_zh      TEXT,
    domain_class        VARCHAR(64),
    range_description   TEXT,
    is_directional      BOOLEAN NOT NULL,
    representation_role VARCHAR(16) NOT NULL,
    owl_iri             TEXT,
    is_active           BOOLEAN NOT NULL DEFAULT true,
    display_order       INTEGER,
    remark              TEXT,

    CONSTRAINT ck_relation_defs_representation_role CHECK (representation_role IN (
        'canonical', 'derived'
    ))
);

COMMENT ON TABLE relation_definitions IS
    'PostgreSQL predicate registry for ordinary knowledge relations (participatesIn / modulates / '
    'increasesRiskOf / hasSymptom / actsOn / hasFunction / ...). NOT a ConnectionType/CircuitType/'
    'EvidenceType taxonomy and NOT a new OWL taxonomy. Adding a row never modifies the ontology TTL.';

CREATE INDEX idx_relation_defs_representation_role ON relation_definitions (representation_role);

-- ===========================================================================
-- 2. knowledge_assertions (DB-only ordinary relation claims)
-- ===========================================================================

CREATE TABLE knowledge_assertions (
    assertion_pk      BIGSERIAL PRIMARY KEY,
    assertion_id      VARCHAR(32) NOT NULL UNIQUE
        DEFAULT 'NGIQ-AST-' || lpad(nextval('infra.ngiq_ast_seq')::text, 8, '0'),
    subject_entity_pk BIGINT NOT NULL,
    predicate_pk      BIGINT NOT NULL,
    object_entity_pk  BIGINT NOT NULL,
    display_name_en   TEXT,
    display_name_zh   TEXT,
    derivation_type   VARCHAR(16) NOT NULL,
    assertion_status  VARCHAR(24),
    confidence        DOUBLE PRECISION,
    qualifiers_json   JSONB,
    condition_en      TEXT,
    condition_zh      TEXT,
    source_scope      VARCHAR(32),
    valid_from        TIMESTAMPTZ,
    valid_to          TIMESTAMPTZ,
    review_status     VARCHAR(24),
    reviewer          VARCHAR(64),
    reviewed_at       TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    remark            TEXT,

    CONSTRAINT fk_ka_subject
        FOREIGN KEY (subject_entity_pk) REFERENCES kg_entities (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_ka_predicate
        FOREIGN KEY (predicate_pk) REFERENCES relation_definitions (predicate_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_ka_object
        FOREIGN KEY (object_entity_pk) REFERENCES kg_entities (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT ck_ka_derivation_type CHECK (derivation_type IN ('reported', 'inferred')),
    CONSTRAINT ck_ka_review_status CHECK (review_status IS NULL OR review_status IN (
        'pending', 'approved', 'rejected', 'uncertain', 'needs_revision'
    ))
);

COMMENT ON TABLE knowledge_assertions IS
    'DB-only ordinary relation claim (BrainRegion participatesIn Function, Gene increasesRiskOf '
    'Disease, Disease hasSymptom Symptom, Neurotransmitter actsOn Receptor, Circuit hasFunction '
    'Function). NOT in OWL Core. Connection/Circuit/RegionMapping/CCM have their own canonical '
    'reified models and are NOT duplicated as assertions. derivation_type: reported = external '
    'source reported; inferred = derived by rules (human review affects lifecycle, NOT derivation '
    'origin).';

CREATE INDEX idx_ka_subject ON knowledge_assertions (subject_entity_pk);
CREATE INDEX idx_ka_predicate ON knowledge_assertions (predicate_pk);
CREATE INDEX idx_ka_object ON knowledge_assertions (object_entity_pk);

-- ===========================================================================
-- 3. region_mappings (first-class reified, shared-PK)
-- ===========================================================================

CREATE TABLE region_mappings (
    entity_pk           BIGINT PRIMARY KEY,
    external_region_pk  BIGINT NOT NULL,
    brain_region_pk     BIGINT NOT NULL,
    mapping_type        VARCHAR(16) NOT NULL,
    mapping_method      VARCHAR(24),
    spatial_overlap     DOUBLE PRECISION,
    name_similarity     DOUBLE PRECISION,
    semantic_similarity DOUBLE PRECISION,
    hierarchy_similarity DOUBLE PRECISION,
    overall_confidence  DOUBLE PRECISION,
    mapping_source      VARCHAR(24),
    review_status       VARCHAR(24),
    reviewer            VARCHAR(64),
    reviewed_at         TIMESTAMPTZ,
    evidence_summary_en TEXT,
    evidence_summary_zh TEXT,
    remark              TEXT,

    CONSTRAINT fk_rm_entity
        FOREIGN KEY (entity_pk) REFERENCES kg_entities (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_rm_external_region
        FOREIGN KEY (external_region_pk) REFERENCES external_regions (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_rm_brain_region
        FOREIGN KEY (brain_region_pk) REFERENCES brain_regions (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT ck_rm_mapping_type CHECK (mapping_type IN (
        'exact', 'close', 'broader', 'narrower', 'related', 'overlapping', 'unresolved'
    )),
    CONSTRAINT ck_rm_mapping_method CHECK (mapping_method IS NULL OR mapping_method IN (
        'automatic', 'manual', 'hybrid'
    )),
    CONSTRAINT ck_rm_review_status CHECK (review_status IS NULL OR review_status IN (
        'pending', 'approved', 'rejected', 'uncertain', 'needs_revision'
    ))
);

COMMENT ON TABLE region_mappings IS
    'First-class reified RegionMapping (shared-PK, entity_type=region_mapping, public ID = '
    'kg_entities.entity_id NGIQ-RMAP). ExternalRegion -> RegionMapping -> canonical BrainRegion. '
    'SEPARATE from brain_region_aggregation_mappings (fine canonical -> coarse canonical). '
    'Never auto-derives partOf; never auto-merges canonical entities on mapping_equivalence.';

CREATE INDEX idx_rm_external_region ON region_mappings (external_region_pk);
CREATE INDEX idx_rm_brain_region ON region_mappings (brain_region_pk);

CREATE TRIGGER trg_region_mappings_entity_type
BEFORE INSERT ON region_mappings
FOR EACH ROW EXECUTE FUNCTION infra.assert_entity_type('region_mapping');

-- ===========================================================================
-- 4. evidence_links (Evidence -> assertion XOR entity target)
-- ===========================================================================

CREATE TABLE evidence_links (
    link_pk             BIGSERIAL PRIMARY KEY,
    link_id             VARCHAR(32) NOT NULL UNIQUE
        DEFAULT 'NGIQ-ELK-' || lpad(nextval('infra.ngiq_elk_seq')::text, 8, '0'),
    evidence_pk         BIGINT      NOT NULL,
    assertion_pk        BIGINT,
    entity_pk           BIGINT,
    evidence_role       VARCHAR(16) NOT NULL,
    evidence_strength   VARCHAR(16),
    evidence_directness VARCHAR(16),
    claim_scope         VARCHAR(32),
    is_primary_evidence BOOLEAN     NOT NULL DEFAULT false,
    record_status       VARCHAR(16) NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    remark              TEXT,

    CONSTRAINT fk_elink_evidence
        FOREIGN KEY (evidence_pk) REFERENCES evidence (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_elink_assertion
        FOREIGN KEY (assertion_pk) REFERENCES knowledge_assertions (assertion_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_elink_entity
        FOREIGN KEY (entity_pk) REFERENCES kg_entities (entity_pk)
        ON DELETE RESTRICT,
    -- XOR: exactly one of assertion_pk / entity_pk (both NULL or both set -> rejected)
    CONSTRAINT ck_elink_xor CHECK (
        (assertion_pk IS NOT NULL AND entity_pk IS NULL)
        OR (assertion_pk IS NULL AND entity_pk IS NOT NULL)
    ),
    -- entity target must carry claim_scope; assertion target may leave it NULL
    CONSTRAINT ck_elink_claim_scope CHECK (entity_pk IS NULL OR claim_scope IS NOT NULL),
    CONSTRAINT ck_elink_evidence_role CHECK (evidence_role IN (
        'supports', 'contradicts', 'qualifies'
    )),
    CONSTRAINT ck_elink_strength CHECK (evidence_strength IS NULL OR evidence_strength IN (
        'strong', 'moderate', 'weak', 'unknown'
    )),
    CONSTRAINT ck_elink_directness CHECK (evidence_directness IS NULL OR evidence_directness IN (
        'direct', 'indirect'
    )),
    CONSTRAINT ck_elink_claim_scope_vocab CHECK (claim_scope IS NULL OR claim_scope IN (
        'entity_overall', 'existence', 'identity', 'direction', 'connection_type',
        'topology', 'membership', 'mapping_identity', 'mapping_equivalence',
        'mapping_overlap', 'other'
    )),
    CONSTRAINT ck_elink_record_status CHECK (record_status IN (
        'proposed', 'active', 'deprecated', 'merged'
    ))
);

COMMENT ON TABLE evidence_links IS
    'Evidence -> assertion (knowledge_assertions) OR Evidence -> allowed reified entity target '
    '(connection / circuit / region_mapping / circuit_connection_membership). XOR enforced by CHECK '
    '(fail closed). evidence_strength / evidence_directness are target-specific context here (NOT on '
    'evidence, NOT to be confused with connection_observations.strength_reported). Entity target '
    'requires claim_scope. No evidence inheritance: fine-level evidence never auto-becomes coarse '
    'direct evidence.';

CREATE INDEX idx_elink_evidence ON evidence_links (evidence_pk);
CREATE INDEX idx_elink_assertion ON evidence_links (assertion_pk);
CREATE INDEX idx_elink_entity ON evidence_links (entity_pk);

-- Entity evidence whitelist guard (reads kg_entities.entity_type; fail closed).
CREATE OR REPLACE FUNCTION infra.assert_evidence_link_entity_whitelist()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_type text;
BEGIN
    IF NEW.entity_pk IS NOT NULL THEN
        SELECT entity_type INTO v_type FROM kg_entities WHERE entity_pk = NEW.entity_pk;
        IF v_type IS NULL OR v_type NOT IN (
            'connection', 'circuit', 'region_mapping', 'circuit_connection_membership'
        ) THEN
            RAISE EXCEPTION
                'entity_pk % (entity_type=%) is not an allowed direct evidence target '
                '(allowed: connection / circuit / region_mapping / circuit_connection_membership)',
                NEW.entity_pk, v_type;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_elink_entity_whitelist
BEFORE INSERT OR UPDATE ON evidence_links
FOR EACH ROW EXECUTE FUNCTION infra.assert_evidence_link_entity_whitelist();
