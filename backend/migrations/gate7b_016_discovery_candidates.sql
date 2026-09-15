-- Gate 7B Phase P0-1 — LLM Discovery candidate persistence
--
-- ONE new table (the 35th public table):
--
--   discovery_candidates — one PROPOSAL produced by one LLM Discovery run.
--
-- A candidate is a PROPOSAL: not a canonical BrainRegion / Connection / Circuit /
-- Function, not Evidence, not a KnowledgeAssertion, not Final KG knowledge. This
-- is a Knowledge Production STAGING layer that nothing else reads as truth.
--
-- Frozen boundaries honored:
--   * NOT a kg_entities entity, and NO entry in the frozen 29-type
--     infra.next_ngiq_id() registry: handing a staging proposal a canonical id
--     is exactly the confusion this layer must not create. The public id
--     follows the WORKFLOW-layer convention of publication_discovery_hits
--     (gate7b_013): a dedicated sequence, outside the canonical registry.
--   * NO canonical-entity reference. Candidate-to-candidate references
--     (region_refs / source_ref / target_ref) are RUN-LOCAL coordinates and stay
--     inside payload_json; turning them into FKs would assert a resolution that
--     has not happened.
--   * local_id is a LABEL, not an identity: ck_dc_local_id_pattern makes a
--     canonical-shaped id in that column a hard database error.
--   * NO raw model output. payload_json holds the PARSED typed candidate; the
--     raw response, reasoning content, prompt and provider payload are absent.
--   * NO review workflow: no reviewer, no reviewed_at, no promotion state
--     machine. This phase persists proposals, and nothing here accepts, rejects,
--     merges or canonicalizes one.
--   * NO secrets, and no trigger writes any formal KG table (not a kg_entities
--     subtype, so no infra.assert_entity_type() guard is needed).
--   * ONE structural authority. The Phase 3A parser decides whether a candidate
--     is well-formed; this table constrains only identity, idempotency,
--     run-scoping and referential integrity — never a content rule of the typed
--     contract, because a second authority would reject what the parser accepted.
--   * Idempotent: re-runnable.

-- 1. public id sequence — deliberately NOT infra.next_ngiq_id() (see above).
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_dc_seq;

-- 2. discovery_candidates. Design-policy notes live in the COMMENTs below.
CREATE TABLE IF NOT EXISTS discovery_candidates (
    candidate_pk       BIGSERIAL   PRIMARY KEY,
    candidate_id       VARCHAR(32) NOT NULL UNIQUE
        DEFAULT 'NGIQ-DC-' || lpad(nextval('infra.ngiq_dc_seq')::text, 8, '0'),

    -- Both internal FKs are read from the SAME run row by the writer, so the
    -- seed recorded here is the run's own seed, not a re-resolved one.
    discovery_run_pk   BIGINT      NOT NULL,
    seed_region_pk     BIGINT      NOT NULL,

    candidate_type     VARCHAR(16) NOT NULL,
    -- TEXT, not VARCHAR(n): the contract caps local_id by PATTERN, not by
    -- length, so any length cap here would be an invented second rule.
    local_id           TEXT        NOT NULL,
    name               TEXT        NOT NULL,
    payload_json       JSONB       NOT NULL,
    -- DOUBLE PRECISION: the Gate7B convention for every confidence column, and
    -- lossless for a Python float. NUMERIC scale would silently quantize a
    -- parsed 0.123456789 to 0.123 — i.e. recalculate a value stored as parsed.
    confidence         DOUBLE PRECISION,

    status             VARCHAR(16) NOT NULL DEFAULT 'proposed',
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT fk_dc_discovery_run
        FOREIGN KEY (discovery_run_pk) REFERENCES knowledge_discovery_runs (run_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_dc_seed_region
        FOREIGN KEY (seed_region_pk) REFERENCES brain_regions (entity_pk)
        ON DELETE RESTRICT,

    CONSTRAINT ck_dc_candidate_type CHECK (
        candidate_type IN ('region', 'connection', 'circuit', 'function')
    ),
    -- Reserved vocabulary: only 'proposed' is written this phase, and no review
    -- transition exists. Widening a CHECK over live rows is its own migration.
    CONSTRAINT ck_dc_status CHECK (
        status IN ('proposed', 'accepted', 'rejected', 'deferred')
    ),
    -- Depends only on this row, so it belongs in SQL. Mirrors the frozen
    -- LOCAL_ID_PATTERN in app/schemas/llm_discovery.py: '<kind>_<n>'.
    CONSTRAINT ck_dc_local_id_pattern CHECK (
        local_id ~ '^(region|connection|function|circuit)_[0-9]+$'
    ),
    -- Mirrors the contract's `confidence: float = Field(ge=0.0, le=1.0)`.
    -- Range only: the VALUE is stored exactly as parsed.
    CONSTRAINT ck_dc_confidence_range CHECK (
        confidence IS NULL OR (confidence >= 0 AND confidence <= 1)
    )
);

COMMENT ON TABLE discovery_candidates IS 'PROPOSAL staging: one Region/Connection/Circuit/Function candidate from one LLM Discovery run. Not canonical knowledge — no kg_entities row, no canonical FK, no evidence, no assertion. Candidate-to-candidate refs stay inside payload_json as run-local coordinates.';
COMMENT ON COLUMN discovery_candidates.candidate_id IS 'Public candidate id (NGIQ-DC-*). Deliberately NOT allocated by infra.next_ngiq_id(), which issues CANONICAL entity ids that a proposal has no standing to hold.';
COMMENT ON COLUMN discovery_candidates.discovery_run_pk IS 'The LLM Discovery run that produced this proposal. ON DELETE RESTRICT: a run with candidate history cannot be silently removed.';
COMMENT ON COLUMN discovery_candidates.seed_region_pk IS 'Canonical BrainRegion seed (brain_regions.entity_pk). Denormalized from the run so the later candidate read path need not join through the run to scope by seed.';
COMMENT ON COLUMN discovery_candidates.local_id IS 'The model''s RUN-LOCAL label (region_1 / circuit_3): a LABEL, not an identity, and deliberately not globally unique — the same string in two runs is two unrelated proposals. TEXT, because the contract constrains its shape by pattern only; no length cap is invented here.';
COMMENT ON COLUMN discovery_candidates.name IS 'Human-readable projection derived from the typed candidate, for listing and debugging. Never a key, never unique, never matched on. NOT NULL but deliberately not blank-checked: whether a candidate may have an empty name is the parser''s decision, not this table''s.';
COMMENT ON COLUMN discovery_candidates.payload_json IS 'The complete PARSED typed candidate object. Never the raw model response, the reasoning content, the prompt or a provider payload.';
COMMENT ON COLUMN discovery_candidates.confidence IS 'The model''s own discovery confidence in [0,1], stored EXACTLY as parsed — never recalculated, never quantized. DOUBLE PRECISION (the Gate7B convention) so a Python float round-trips losslessly.';
COMMENT ON COLUMN discovery_candidates.status IS 'Proposal lifecycle. Only ''proposed'' is written in this phase; accepted / rejected / deferred are reserved vocabulary.';

-- 3. Idempotency: which run proposed which local label of which kind. Scoped BY
--    RUN on purpose — two runs may legitimately propose the same concept.
CREATE UNIQUE INDEX IF NOT EXISTS uq_dc_run_type_local_id
    ON discovery_candidates (discovery_run_pk, candidate_type, local_id);

COMMENT ON INDEX uq_dc_run_type_local_id IS 'Candidate-persistence idempotency, scoped to the run. NOT a claim that two runs cannot propose the same concept.';

-- 4. Listing ONE run's proposals is already served by the unique index prefix;
--    this serves the other read: everything proposed around one seed.
CREATE INDEX IF NOT EXISTS idx_dc_seed_region
    ON discovery_candidates (seed_region_pk, created_at DESC);
