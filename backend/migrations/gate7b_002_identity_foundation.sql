-- Gate 7B Phase 1 — Identity Foundation
--
-- Creates ONLY the 4 Identity Foundation scientific tables (4 / 32):
--   1. kg_entities     — global identity truth (shared-PK base)
--   2. entity_aliases  — canonical entity aliases / synonyms / historical names
--   3. entity_xrefs    — cross-references to external DB/ontology identifiers
--   4. sources         — scientific source registry (NOT provenance agents)
--
-- No Phase 2 subtype tables (brain_regions / functions / connections / …) here.
--
-- Authority: Gate 7A frozen data dictionary
--   (18_complete_data_dictionary.md, 19_er_model.md, 23_gate_07a_freeze_candidate.md,
--    27_gate_07a_consistency_audit.md, 16_controlled_vocabularies.md)
--   + gate_07b_a1/05_ngiq_prefix_registry.md.
--
-- Naming rule (Final Correction §E): `*_pk` = internal BIGINT PK/FK target;
-- `*_id` = public NGIQ ID. All FK reference internal `*_pk`, never public `*_id`.

-- ===========================================================================
-- 1. NGIQ public-ID generator (frozen 29-entry registry, fail-closed)
-- ===========================================================================

CREATE OR REPLACE FUNCTION infra.next_ngiq_id(p_type text)
RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    v_prefix text;
    v_num    bigint;
BEGIN
    -- Frozen entity_type -> prefix mapping (29 entries, no user-supplied sequence).
    v_prefix := CASE p_type
        WHEN 'brain_region'                     THEN 'BR'
        WHEN 'cellular_neural_structure'        THEN 'CNS'
        WHEN 'neurobiological_process'          THEN 'NBP'
        WHEN 'connection'                       THEN 'CON'
        WHEN 'connection_observation'           THEN 'COB'
        WHEN 'circuit'                          THEN 'CIR'
        WHEN 'function'                         THEN 'FUN'
        WHEN 'neurotransmitter'                 THEN 'NT'
        WHEN 'receptor'                         THEN 'RCP'
        WHEN 'gene'                             THEN 'GEN'
        WHEN 'disease'                          THEN 'DIS'
        WHEN 'symptom'                          THEN 'SYM'
        WHEN 'research_study'                   THEN 'STU'
        WHEN 'publication'                      THEN 'PUB'
        WHEN 'evidence'                         THEN 'EVI'
        WHEN 'atlas'                            THEN 'ATL'
        WHEN 'external_region'                  THEN 'XREG'
        WHEN 'region_mapping'                   THEN 'RMAP'
        WHEN 'circuit_connection_membership'    THEN 'CCM'
        WHEN 'circuit_region_membership'        THEN 'CRM'
        WHEN 'brain_region_hierarchy_relation'  THEN 'BRH'
        WHEN 'function_hierarchy_relation'      THEN 'FHR'
        WHEN 'brain_region_aggregation_mapping' THEN 'BRAM'
        WHEN 'knowledge_assertion'              THEN 'AST'
        WHEN 'relation_definition'              THEN 'PRED'
        WHEN 'evidence_link'                    THEN 'ELK'
        WHEN 'source'                           THEN 'SRC'
        WHEN 'alias'                            THEN 'ALS'
        WHEN 'xref'                             THEN 'XRF'
        ELSE NULL
    END;

    IF v_prefix IS NULL THEN
        RAISE EXCEPTION 'unknown NGIQ entity type: %', p_type;
    END IF;

    -- Allocate from the per-type sequence (nextval is transaction/concurrency-safe).
    v_num := CASE p_type
        WHEN 'brain_region'                     THEN nextval('infra.ngiq_br_seq')
        WHEN 'cellular_neural_structure'        THEN nextval('infra.ngiq_cns_seq')
        WHEN 'neurobiological_process'          THEN nextval('infra.ngiq_nbp_seq')
        WHEN 'connection'                       THEN nextval('infra.ngiq_con_seq')
        WHEN 'connection_observation'           THEN nextval('infra.ngiq_cob_seq')
        WHEN 'circuit'                          THEN nextval('infra.ngiq_cir_seq')
        WHEN 'function'                         THEN nextval('infra.ngiq_fun_seq')
        WHEN 'neurotransmitter'                 THEN nextval('infra.ngiq_nt_seq')
        WHEN 'receptor'                         THEN nextval('infra.ngiq_rcp_seq')
        WHEN 'gene'                             THEN nextval('infra.ngiq_gen_seq')
        WHEN 'disease'                          THEN nextval('infra.ngiq_dis_seq')
        WHEN 'symptom'                          THEN nextval('infra.ngiq_sym_seq')
        WHEN 'research_study'                   THEN nextval('infra.ngiq_stu_seq')
        WHEN 'publication'                      THEN nextval('infra.ngiq_pub_seq')
        WHEN 'evidence'                         THEN nextval('infra.ngiq_evi_seq')
        WHEN 'atlas'                            THEN nextval('infra.ngiq_atl_seq')
        WHEN 'external_region'                  THEN nextval('infra.ngiq_xreg_seq')
        WHEN 'region_mapping'                   THEN nextval('infra.ngiq_rmap_seq')
        WHEN 'circuit_connection_membership'    THEN nextval('infra.ngiq_ccm_seq')
        WHEN 'circuit_region_membership'        THEN nextval('infra.ngiq_crm_seq')
        WHEN 'brain_region_hierarchy_relation'  THEN nextval('infra.ngiq_brh_seq')
        WHEN 'function_hierarchy_relation'      THEN nextval('infra.ngiq_fhr_seq')
        WHEN 'brain_region_aggregation_mapping' THEN nextval('infra.ngiq_bram_seq')
        WHEN 'knowledge_assertion'              THEN nextval('infra.ngiq_ast_seq')
        WHEN 'relation_definition'              THEN nextval('infra.ngiq_pred_seq')
        WHEN 'evidence_link'                    THEN nextval('infra.ngiq_elk_seq')
        WHEN 'source'                           THEN nextval('infra.ngiq_src_seq')
        WHEN 'alias'                            THEN nextval('infra.ngiq_als_seq')
        WHEN 'xref'                             THEN nextval('infra.ngiq_xrf_seq')
        ELSE NULL
    END;

    IF v_num IS NULL THEN
        RAISE EXCEPTION 'no sequence for NGIQ entity type: %', p_type;
    END IF;

    -- 8-digit capacity guard: never silently expand to 9 digits.
    IF v_num > 99999999 THEN
        RAISE EXCEPTION 'NGIQ sequence exhausted (> 8 digits) for type: %', p_type;
    END IF;

    RETURN 'NGIQ-' || v_prefix || '-' || lpad(v_num::text, 8, '0');
END;
$$;

COMMENT ON FUNCTION infra.next_ngiq_id(text) IS
    'Frozen per-type NGIQ public-ID generator. Accepts only registry types; '
    'unknown type -> exception (fail closed); >99,999,999 -> exception (no silent 9-digit expansion).';

-- ===========================================================================
-- 2. kg_entities — canonical entity identity truth
-- ===========================================================================

CREATE TABLE kg_entities (
    entity_pk                BIGSERIAL PRIMARY KEY,
    entity_id                VARCHAR(32) NOT NULL UNIQUE,
    entity_type              VARCHAR(48) NOT NULL,
    name_en                  TEXT,
    name_zh                  TEXT,
    abbreviation             VARCHAR(64),
    definition_en            TEXT,
    definition_zh            TEXT,
    description_en           TEXT,
    description_zh           TEXT,
    source_name_original     TEXT,
    source_language          VARCHAR(16),
    name_en_source           VARCHAR(24),
    name_zh_source           VARCHAR(24),
    translation_review_status VARCHAR(24),
    record_status            VARCHAR(16) NOT NULL,
    review_status            VARCHAR(24),
    version                  INTEGER,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by_agent         VARCHAR(64),
    updated_by_agent         VARCHAR(64),
    metadata_json            JSONB,
    remark                   TEXT,

    CONSTRAINT ck_kg_entities_entity_type CHECK (entity_type IN (
        'brain_region', 'cellular_neural_structure', 'neurobiological_process',
        'connection', 'circuit', 'function', 'neurotransmitter', 'receptor',
        'gene', 'disease', 'symptom', 'research_study', 'publication',
        'evidence', 'atlas', 'external_region', 'region_mapping',
        'circuit_connection_membership'
    )),
    CONSTRAINT ck_kg_entities_record_status CHECK (record_status IN (
        'proposed', 'active', 'deprecated', 'merged'
    )),
    CONSTRAINT ck_kg_entities_review_status CHECK (review_status IS NULL OR review_status IN (
        'pending', 'approved', 'rejected', 'uncertain', 'needs_revision'
    )),
    CONSTRAINT ck_kg_entities_name_en_source CHECK (name_en_source IS NULL OR name_en_source IN (
        'source', 'human_curated', 'translated_human', 'translated_ai', 'normalized', 'unknown'
    )),
    CONSTRAINT ck_kg_entities_name_zh_source CHECK (name_zh_source IS NULL OR name_zh_source IN (
        'source', 'human_curated', 'translated_human', 'translated_ai', 'normalized', 'unknown'
    )),
    -- Frozen bilingual display policy (§F): ACTIVE requires both name_en AND name_zh.
    CONSTRAINT ck_kg_entities_active_bilingual
        CHECK (record_status <> 'active' OR (name_en IS NOT NULL AND name_zh IS NOT NULL)),
    CONSTRAINT ck_kg_entities_active_name_source
        CHECK (record_status <> 'active'
               OR (name_en_source IS NOT NULL AND name_zh_source IS NOT NULL
                   AND name_en_source <> 'unknown' AND name_zh_source <> 'unknown')),
    CONSTRAINT ck_kg_entities_proposed_source
        CHECK (record_status <> 'proposed' OR source_name_original IS NOT NULL),
    -- §F: PROPOSED may lack one language, but at least one of name_en/name_zh must exist.
    CONSTRAINT ck_kg_entities_proposed_has_name
        CHECK (record_status <> 'proposed' OR (name_en IS NOT NULL OR name_zh IS NOT NULL))
);

COMMENT ON TABLE kg_entities IS
    'Global identity truth for all first-class canonical entities (shared-PK base). '
    'Every BrainRegion/Connection/Circuit/Function/Gene/Disease/Evidence/… obtains its '
    'single internal identity (entity_pk) and public NGIQ ID (entity_id) here.';
COMMENT ON COLUMN kg_entities.entity_pk IS
    'Internal global PK (BIGSERIAL). Future subtype tables reuse this as their PK (shared-PK); no second *_pk.';
COMMENT ON COLUMN kg_entities.entity_id IS
    'Stable public NGIQ ID (NGIQ-<TYPE>-<8 digits>). NOT NULL, UNIQUE, never reused.';
COMMENT ON COLUMN kg_entities.entity_type IS
    'Controlled entity type (18 values). Drives shared-PK subtype, public-ID prefix allocation, evidence whitelist.';

CREATE INDEX idx_kg_entities_entity_type ON kg_entities (entity_type);
CREATE INDEX idx_kg_entities_record_status ON kg_entities (record_status);
CREATE INDEX idx_kg_entities_name_en ON kg_entities (name_en);

-- ===========================================================================
-- 3. sources — scientific source registry (NOT provenance agents)
-- ===========================================================================

CREATE TABLE sources (
    source_pk        BIGSERIAL PRIMARY KEY,
    source_id        VARCHAR(32) NOT NULL UNIQUE,
    name_en          TEXT        NOT NULL,
    name_zh          TEXT        NOT NULL,
    abbreviation     VARCHAR(64),
    source_type      VARCHAR(32) NOT NULL,
    provider         VARCHAR(128),
    version          VARCHAR(32),
    species_scope    VARCHAR(64),
    url              TEXT,
    api_url          TEXT,
    license          VARCHAR(64),
    citation_text    TEXT,
    description_en   TEXT,
    description_zh   TEXT,
    last_checked_at  TIMESTAMPTZ,
    record_status    VARCHAR(16) NOT NULL,
    remark           TEXT,

    CONSTRAINT ck_sources_source_type CHECK (source_type IN (
        'atlas', 'database', 'ontology', 'publication_database',
        'literature', 'manual', 'import_pipeline'
    )),
    CONSTRAINT ck_sources_record_status CHECK (record_status IN (
        'proposed', 'active', 'deprecated', 'merged'
    ))
);

COMMENT ON TABLE sources IS
    'Scientific Source registry: where knowledge/data truly originates '
    '(Julich-Brain, Brainnetome, HCP, PubMed, Europe PMC, HGNC, MONDO, HPO, IUPHAR…). '
    'NOT provenance agents (GPT/DeepSeek/BioSEPBERT/Human curator/ImportPipeline/RuleEngine).';
COMMENT ON COLUMN sources.source_type IS
    'Scientific source category. `llm` is intentionally absent — LLMs are provenance agents, not scientific sources.';

CREATE INDEX idx_sources_name_en ON sources (name_en);
CREATE INDEX idx_sources_source_type ON sources (source_type);

-- ===========================================================================
-- 4. entity_aliases — aliases / synonyms / historical names
-- ===========================================================================

CREATE TABLE entity_aliases (
    alias_pk         BIGSERIAL PRIMARY KEY,
    alias_id         VARCHAR(32) NOT NULL UNIQUE,
    entity_pk        BIGINT      NOT NULL,
    alias_text       TEXT        NOT NULL,
    language         VARCHAR(8),
    alias_type       VARCHAR(24) NOT NULL,
    source_pk        BIGINT,
    source_record_id VARCHAR(64),
    is_preferred     BOOLEAN     NOT NULL DEFAULT false,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    remark           TEXT,

    CONSTRAINT fk_entity_aliases_entity
        FOREIGN KEY (entity_pk) REFERENCES kg_entities (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_entity_aliases_source
        FOREIGN KEY (source_pk) REFERENCES sources (source_pk)
        ON DELETE RESTRICT,
    CONSTRAINT ck_entity_aliases_alias_type CHECK (alias_type IN (
        'exact', 'abbreviation', 'historical', 'atlas_label',
        'previous_name', 'narrow', 'broad', 'related'
    ))
);

COMMENT ON TABLE entity_aliases IS
    'Aliases / synonyms / historical names of a canonical entity. An alias is NOT a new canonical identity.';
COMMENT ON COLUMN entity_aliases.entity_pk IS
    'FK -> kg_entities.entity_pk (internal PK). Deletion RESTRICT to preserve lineage.';

CREATE INDEX idx_entity_aliases_entity_pk ON entity_aliases (entity_pk);
CREATE INDEX idx_entity_aliases_alias_text_lower ON entity_aliases (lower(alias_text));
CREATE INDEX idx_entity_aliases_source_pk ON entity_aliases (source_pk);

-- ===========================================================================
-- 5. entity_xrefs — external database/ontology cross-references
-- ===========================================================================

CREATE TABLE entity_xrefs (
    xref_pk         BIGSERIAL PRIMARY KEY,
    xref_id         VARCHAR(32) NOT NULL UNIQUE,
    entity_pk       BIGINT      NOT NULL,
    source_database VARCHAR(64) NOT NULL,
    external_id     VARCHAR(64) NOT NULL,
    external_uri    TEXT,
    match_type      VARCHAR(24) NOT NULL,
    is_primary      BOOLEAN     NOT NULL DEFAULT false,
    source_version  VARCHAR(32),
    retrieved_at    TIMESTAMPTZ,
    remark          TEXT,

    CONSTRAINT fk_entity_xrefs_entity
        FOREIGN KEY (entity_pk) REFERENCES kg_entities (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT ck_entity_xrefs_match_type CHECK (match_type IN (
        'exact', 'close', 'broader', 'narrower', 'related', 'unresolved'
    ))
);

COMMENT ON TABLE entity_xrefs IS
    'Cross-reference between a canonical entity and an external database/ontology identifier '
    '(Brainnetome / HGNC / MONDO / HPO / ChEBI…). External IDs are never folded into aliases.';
COMMENT ON COLUMN entity_xrefs.entity_pk IS
    'FK -> kg_entities.entity_pk (internal PK). Deletion RESTRICT to preserve lineage.';

-- Uniqueness policy: a resolved (non-unresolved) (source_database, external_id)
-- must not be unintentionally bound to multiple entities; 'unresolved' mappings
-- may legitimately be ambiguous (allowed to repeat).
CREATE UNIQUE INDEX uq_entity_xrefs_resolved_external
    ON entity_xrefs (source_database, external_id)
    WHERE match_type <> 'unresolved';
CREATE INDEX idx_entity_xrefs_entity_pk ON entity_xrefs (entity_pk);
CREATE INDEX idx_entity_xrefs_external_lookup ON entity_xrefs (source_database, external_id);
