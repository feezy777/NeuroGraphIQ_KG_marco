-- Gate 7B Phase 2A — Knowledge Discovery Run (workflow / provenance layer)
--
-- Creates ONLY the 1 management table (33rd table; NOT a scientific table):
--
--   knowledge_discovery_runs — one recorded ATTEMPT to discover candidate
--   knowledge around one canonical BrainRegion seed.
--
--     BrainRegion seed
--           |
--     Discovery Run      <- this table (shared)
--        /        \
--   LLM_DISCOVERY   LITERATURE_DISCOVERY
--
-- Deliberately ONE table: there is NO llm_discovery_runs and NO
-- literature_discovery_runs. Both routes share the same run model; only the
-- route-specific provenance columns differ.
--
-- Frozen boundaries honored:
--   * A Discovery Run is WORKFLOW / PROVENANCE, not knowledge. It must never
--     itself represent a circuit / connection / function / evidence /
--     knowledge_assertion, and it is NOT a kg_entities entity. It therefore
--     gets NO NGIQ public id and NO entry in the frozen 29-type
--     infra.next_ngiq_id() registry (extending that registry would conflate
--     the workflow layer with the canonical knowledge layer).
--     Its public identity is a UUID, matching the repository's WORKFLOW-layer
--     convention (import_batches / raw_parse_runs use UUID PKs), while the
--     SCIENTIFIC layer uses BIGSERIAL + 'NGIQ-*' public ids.
--   * status != outcome. status is the execution lifecycle; outcome is the
--     scientific result of a finished run. status='COMPLETED' with
--     outcome='NO_EVIDENCE_FOUND' is a real, meaningful answer and is NOT the
--     same thing as "never processed" or "execution failed".
--   * No state machine beyond vocabulary CHECKs. Which status may follow which,
--     when outcome becomes mandatory on a terminal run, and when
--     provider/model become mandatory for LLM runs are EXECUTION-level rules
--     and belong to Phase 2B (Discovery Run Lifecycle).
--   * No secrets. There is no api_key / token / credential column and none may
--     be added; provider credentials live in runtime settings only.
--   * No trigger writes any formal KG table. This table is not a shared-PK
--     kg_entities subtype, so it needs no infra.assert_entity_type() guard.
--   * Idempotent: re-runnable.

-- ===========================================================================
-- 1. knowledge_discovery_runs
-- ===========================================================================

CREATE TABLE IF NOT EXISTS knowledge_discovery_runs (
    -- identity -------------------------------------------------------------
    -- run_pk = internal BIGINT PK (Gate7B *_pk convention)
    -- run_id = public UUID identity (workflow layer, not an NGIQ entity id)
    run_pk                 BIGSERIAL PRIMARY KEY,
    run_id                 UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),

    -- seed -----------------------------------------------------------------
    -- Canonical BrainRegion this run is anchored to. FK targets the internal
    -- shared PK (never the public entity_id).
    seed_region_pk         BIGINT NOT NULL,

    -- type / lifecycle -----------------------------------------------------
    discovery_type         VARCHAR(32) NOT NULL,
    status                 VARCHAR(16) NOT NULL DEFAULT 'QUEUED',
    outcome                VARCHAR(32),

    -- route-specific provenance (nullable: only the used route fills these) --
    -- LLM_DISCOVERY:
    provider               VARCHAR(64),
    model_name             VARCHAR(128),
    prompt_key             VARCHAR(128),
    prompt_version         VARCHAR(32),
    -- LITERATURE_DISCOVERY:
    query_strategy_version VARCHAR(32),

    -- common config / provenance (never raw candidate entities) ------------
    parameters_json        JSONB NOT NULL DEFAULT '{}'::jsonb,
    provenance_json        JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- failure --------------------------------------------------------------
    error_code             VARCHAR(64),
    error_message          TEXT,

    -- audit / time ---------------------------------------------------------
    created_by             VARCHAR(64),
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at             TIMESTAMPTZ,
    finished_at            TIMESTAMPTZ,
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT fk_kdr_seed_region
        FOREIGN KEY (seed_region_pk) REFERENCES brain_regions (entity_pk)
        ON DELETE RESTRICT,

    CONSTRAINT ck_kdr_discovery_type CHECK (
        discovery_type IN ('LLM_DISCOVERY', 'LITERATURE_DISCOVERY')
    ),
    CONSTRAINT ck_kdr_status CHECK (
        status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')
    ),
    -- outcome is nullable: a run that has not finished has no outcome yet.
    CONSTRAINT ck_kdr_outcome CHECK (
        outcome IS NULL OR outcome IN (
            'CANDIDATES_FOUND', 'NO_CANDIDATES_FOUND', 'NO_EVIDENCE_FOUND'
        )
    )
);

COMMENT ON TABLE knowledge_discovery_runs IS
    'Workflow/provenance record of ONE discovery attempt against ONE canonical BrainRegion seed. '
    'Shared by both routes (LLM_DISCOVERY / LITERATURE_DISCOVERY) — NOT split per route. '
    'NOT knowledge: a run never represents a circuit/connection/function/evidence/assertion, and '
    'it is not a kg_entities entity (hence a UUID public id, not an NGIQ-* id).';

COMMENT ON COLUMN knowledge_discovery_runs.run_id IS
    'Public run identity (UUID). Deliberately NOT an NGIQ-* id: a Discovery Run is workflow, '
    'not a canonical entity, and must never be confused with one.';

COMMENT ON COLUMN knowledge_discovery_runs.seed_region_pk IS
    'Canonical BrainRegion seed (brain_regions.entity_pk, shared PK with kg_entities). '
    'ON DELETE RESTRICT: a region with discovery history cannot be silently removed.';

COMMENT ON COLUMN knowledge_discovery_runs.status IS
    'Execution lifecycle only: QUEUED / RUNNING / COMPLETED / FAILED / CANCELLED. '
    'Not a scientific judgement — see outcome.';

COMMENT ON COLUMN knowledge_discovery_runs.outcome IS
    'Scientific result of a FINISHED run (nullable): CANDIDATES_FOUND / NO_CANDIDATES_FOUND / '
    'NO_EVIDENCE_FOUND. status != outcome: COMPLETED + NO_EVIDENCE_FOUND is a real answer, '
    'scientifically different from "never processed" or "execution failed".';

COMMENT ON COLUMN knowledge_discovery_runs.provider IS
    'LLM route provenance (nullable). Credentials are NEVER stored here.';

COMMENT ON COLUMN knowledge_discovery_runs.parameters_json IS
    'Run configuration (thresholds, limits, scope). Never raw candidate entities.';

COMMENT ON COLUMN knowledge_discovery_runs.provenance_json IS
    'Run-level provenance metadata. Never raw candidate entities.';

-- ===========================================================================
-- 2. indexes (initially empty table — only what the read paths need)
-- ===========================================================================

-- Covers the primary read: "runs for this seed, newest first".
CREATE INDEX IF NOT EXISTS idx_kdr_seed_region_created
    ON knowledge_discovery_runs (seed_region_pk, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_kdr_discovery_type
    ON knowledge_discovery_runs (discovery_type);

CREATE INDEX IF NOT EXISTS idx_kdr_status
    ON knowledge_discovery_runs (status);
