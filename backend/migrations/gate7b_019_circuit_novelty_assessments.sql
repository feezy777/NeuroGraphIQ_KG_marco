-- Gate 7B Phase P0-3C — Circuit Semantic Novelty Assessment (durable)
--
-- Creates TWO new tables (the 37th and 38th public tables):
--
--   discovery_circuit_novelty_assessments — one assessment of one COMPLETED
--                                           discovery run
--   discovery_circuit_novelty_verdicts    — what each Circuit in that run got
--
--     knowledge_discovery_runs (the RUN)
--           |
--     discovery_circuit_novelty_assessments   <- this parent: the judgement
--           |
--     discovery_circuit_novelty_verdicts      <- this child: one row per Circuit
--           |
--     discovery_candidates (the PROPOSAL, referenced twice: the judged circuit
--                          and the earlier circuit it was matched against)
--
-- WHY THIS EXISTS
--   The semantic novelty assessor answers one question — "of the circuits this
--   round found, how many are genuinely new?" — and that number is intended to
--   decide whether an automatic multi-round discovery loop continues or stops.
--   A knowledge-production decision may not rest on an ephemeral model reply, so
--   the judgement is stored with enough context to re-derive it: which run, which
--   prior pool, which provider and model, which prompt version, and what each
--   circuit received and why.
--
-- Frozen boundaries honored:
--   * APPEND-ONLY. There is deliberately NO updated_at: an assessment is a
--     historical fact about a run. Re-assessing the same run under the same
--     prompt version and model returns the EXISTING row (see the UNIQUE below);
--     it never edits it. Nothing here is ever updated or deleted.
--   * NO status column, deliberately. Persistence happens in ONE transaction
--     after the model reply has been fully validated, so a row cannot be
--     observed half-written and every row is complete by construction. A status
--     vocabulary would either be single-valued dead weight or contradict the
--     UNIQUE constraint below — a "SUPERSEDED" state can never coexist with
--     "one assessment per (run, prompt version, model)". A future versioned
--     reassessment is a NEW prompt version or model, i.e. a new row.
--   * NO completed_at, deliberately. It would always equal created_at, because
--     the row is written once, at completion. Storing the same instant twice is
--     duplication, not auditability.
--   * The assessor is NOT a reviewer. This table moves NO candidate status, is
--     NOT candidate_review_records, and produces no review decision. Every
--     circuit it calls an ALIAS stays exactly as the model produced it.
--   * NOT canonical knowledge. There is deliberately NO FK to kg_entities,
--     evidence, knowledge_assertions or any resolution/promotion table. A
--     verdict is a diagnostic annotation over proposals; `semantic_new_count`
--     measures novelty, it does not assert truth.
--   * Idempotent: re-runnable.

-- ===========================================================================
-- 1. public id sequence
-- ===========================================================================
-- Deliberately NOT infra.next_ngiq_id(): that function allocates CANONICAL
-- entity ids from a frozen 29-type registry. An assessment of a proposal has no
-- standing to hold one. Mirrors gate7b_013 / gate7b_016 / gate7b_017.

CREATE SEQUENCE IF NOT EXISTS infra.ngiq_dcna_seq;

-- ===========================================================================
-- 2. discovery_circuit_novelty_assessments (parent)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS discovery_circuit_novelty_assessments (
    -- identity -------------------------------------------------------------
    assessment_pk  BIGSERIAL   PRIMARY KEY,
    assessment_id  VARCHAR(32) NOT NULL UNIQUE
        DEFAULT 'NGIQ-DCN-' || lpad(nextval('infra.ngiq_dcna_seq')::text, 8, '0'),

    -- WHAT was assessed (internal keys; never returned to a caller) ---------
    target_run_pk  BIGINT      NOT NULL,
    -- Denormalized from the run, exactly as discovery_candidates does, so a read
    -- path can scope by seed without joining through the run. Both values are
    -- read from the SAME run row by the writer, so the seed recorded here is the
    -- run's own seed and cannot disagree with it.
    seed_region_pk BIGINT      NOT NULL,

    -- THE COMPARISON SCOPE. These two columns are what make the prior pool
    -- auditable: re-running the assessor's own query with this seed and this
    -- strategy reproduces the pool exactly, because the pool is every EARLIER
    -- COMPLETED run of that (seed, view) pair — and "earlier" is pinned by the
    -- target run's own position in the run history.
    discovery_view         VARCHAR(64) NOT NULL,
    query_strategy_version VARCHAR(32) NOT NULL,

    -- WHO judged (route provenance; credentials are NEVER stored) -----------
    provider               VARCHAR(64)  NOT NULL,
    model_name             VARCHAR(128) NOT NULL,
    -- The assessor prompt identity, so a stored judgement can always be traced
    -- to the exact instructions that produced it. Bumping either yields a new
    -- row rather than replacing an old one.
    assessor_prompt_key    VARCHAR(128) NOT NULL,
    assessor_prompt_version VARCHAR(32) NOT NULL,

    -- WHAT IT FOUND --------------------------------------------------------
    raw_circuit_count  INTEGER NOT NULL,
    new_count          INTEGER NOT NULL,
    alias_count        INTEGER NOT NULL,
    reformulation_count INTEGER NOT NULL,
    borderline_count   INTEGER NOT NULL,
    -- NEW + BORDERLINE, held by a CHECK below. This is the recall-first rule at
    -- the storage layer: a judgement that leaves a possibly-distinct circuit
    -- uncounted cannot be written, by any writer.
    semantic_new_count INTEGER NOT NULL,

    -- THE PRIOR POOL, in numbers. Membership is deliberately NOT materialized:
    -- it is exactly reproducible from (seed_region_pk, query_strategy_version,
    -- target_run_pk) by the assessor's own chain query, and a later run can
    -- never enter it because the pool is restricted to runs created BEFORE the
    -- target. Copying those rows here would create a second, driftable truth.
    prior_completed_run_count INTEGER NOT NULL,
    prior_circuit_count       INTEGER NOT NULL,

    -- audit / time ---------------------------------------------------------
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT fk_dcna_run
        FOREIGN KEY (target_run_pk) REFERENCES knowledge_discovery_runs (run_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_dcna_seed_region
        FOREIGN KEY (seed_region_pk) REFERENCES brain_regions (entity_pk)
        ON DELETE RESTRICT,

    -- IDEMPOTENCY, held by the database rather than by a caller's memory: one
    -- completed assessment per (run, prompt version, model). A second POST for
    -- the same triple cannot spend a provider call AND cannot write a second
    -- row — it must return the existing one.
    CONSTRAINT uq_dcna_target_run_prompt_model
        UNIQUE (target_run_pk, assessor_prompt_version, model_name),

    -- The four frozen novelty classes. Mirrors app/schemas/circuit_novelty.py.
    CONSTRAINT ck_dcna_class_counts_non_negative CHECK (
        raw_circuit_count >= 0 AND new_count >= 0 AND alias_count >= 0
        AND reformulation_count >= 0 AND borderline_count >= 0
        AND semantic_new_count >= 0
    ),
    -- The four class counts PARTITION the target's circuits: every circuit gets
    -- exactly one class, so the parts must sum to the whole.
    CONSTRAINT ck_dcna_class_counts_sum CHECK (
        raw_circuit_count = new_count + alias_count + reformulation_count
                            + borderline_count
    ),
    -- recall-first: semantic novelty is NEW + BORDERLINE, and nothing else.
    CONSTRAINT ck_dcna_semantic_new_is_new_plus_borderline CHECK (
        semantic_new_count = new_count + borderline_count
    ),
    -- A pool is made of runs; a run holds circuits. Neither can be negative, and
    -- an empty pool is legitimate (the first round of a view has none).
    CONSTRAINT ck_dcna_prior_counts_non_negative CHECK (
        prior_completed_run_count >= 0 AND prior_circuit_count >= 0
    ),
    CONSTRAINT ck_dcna_prompt_identity_not_blank CHECK (
        btrim(assessor_prompt_key) <> '' AND btrim(assessor_prompt_version) <> ''
        AND btrim(model_name) <> '' AND btrim(provider) <> ''
    )
);

COMMENT ON TABLE discovery_circuit_novelty_assessments IS
    'APPEND-ONLY record of one semantic novelty assessment of one COMPLETED discovery run: how many of '
    'its Circuit candidates were genuinely new relative to every EARLIER completed run of the same seed '
    'and discovery view. Never updated, never deleted. NOT a review decision, NOT canonical knowledge, '
    'and never a mutation of any candidate.';

COMMENT ON COLUMN discovery_circuit_novelty_assessments.assessment_id IS
    'Public assessment id (NGIQ-DCN-*). Deliberately NOT allocated by infra.next_ngiq_id(), which issues '
    'CANONICAL entity ids that an assessment of a proposal has no standing to hold.';

COMMENT ON COLUMN discovery_circuit_novelty_assessments.target_run_pk IS
    'The assessed discovery run (knowledge_discovery_runs.run_pk). Unique per (run, prompt version, '
    'model). ON DELETE RESTRICT: a run with assessment history cannot be silently removed.';

COMMENT ON COLUMN discovery_circuit_novelty_assessments.seed_region_pk IS
    'Canonical BrainRegion seed (brain_regions.entity_pk), denormalized from the run so a read path need '
    'not join through the run to scope by seed. Read from the same run row by the writer.';

COMMENT ON COLUMN discovery_circuit_novelty_assessments.discovery_view IS
    'The discovery view whose circuits were compared. Derivable from query_strategy_version, and stored '
    'anyway so that "was the pool confined to ONE view?" is answerable from the row alone, without an '
    'application function — the same reason candidate_review_records keeps from_status/to_status.';

COMMENT ON COLUMN discovery_circuit_novelty_assessments.query_strategy_version IS
    'The stored strategy identifier (e.g. G4HR1/NAMED_CLASSIC_CIRCUITS). Together with seed_region_pk it '
    'IS the comparison scope: it reproduces the exact prior pool when replayed.';

COMMENT ON COLUMN discovery_circuit_novelty_assessments.model_name IS
    'The model that judged. Part of the idempotency key, so a judgement by a different model is a new row.';

COMMENT ON COLUMN discovery_circuit_novelty_assessments.semantic_new_count IS
    'NEW + BORDERLINE, enforced by CHECK. The recall-first counting rule: ALIAS and REFORMULATION are the '
    'only classes claiming a circuit was already known, so they are the only ones that do not count.';

COMMENT ON COLUMN discovery_circuit_novelty_assessments.prior_completed_run_count IS
    'How many runs the prior pool drew on. Membership is not materialized: it is exactly reproducible '
    'from (seed_region_pk, query_strategy_version, target_run_pk) via the assessor chain query.';

-- ===========================================================================
-- 3. discovery_circuit_novelty_verdicts (child)
-- ===========================================================================
-- No public id: a verdict is a COMPONENT of one assessment, not an addressable
-- artifact. Callers address the assessment; the verdicts come with it.
CREATE TABLE IF NOT EXISTS discovery_circuit_novelty_verdicts (
    verdict_pk     BIGSERIAL   PRIMARY KEY,
    assessment_pk  BIGINT      NOT NULL,

    -- the Circuit that was judged (the target run's proposal) ----------------
    candidate_pk   BIGINT      NOT NULL,

    -- the judgement ---------------------------------------------------------
    novelty_class  VARCHAR(16) NOT NULL,
    -- The earlier circuit this one was claimed to match. A relational key, not
    -- free text: a claim about the past must point at a row that exists. Its
    -- RUN is not stored — that is discovery_candidates.discovery_run_pk, one
    -- join away, and copying it would be a second truth to keep in sync.
    matched_prior_candidate_pk BIGINT,

    -- WHY. One sentence from the model. Never written to logs.
    short_reason   TEXT        NOT NULL,

    CONSTRAINT fk_dcnv_assessment
        FOREIGN KEY (assessment_pk)
        REFERENCES discovery_circuit_novelty_assessments (assessment_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_dcnv_candidate
        FOREIGN KEY (candidate_pk) REFERENCES discovery_candidates (candidate_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_dcnv_matched_prior_candidate
        FOREIGN KEY (matched_prior_candidate_pk)
        REFERENCES discovery_candidates (candidate_pk)
        ON DELETE RESTRICT,

    -- One verdict per judged circuit, per assessment.
    CONSTRAINT uq_dcnv_assessment_candidate UNIQUE (assessment_pk, candidate_pk),

    CONSTRAINT ck_dcnv_novelty_class CHECK (
        novelty_class IN ('NEW', 'ALIAS', 'REFORMULATION', 'BORDERLINE')
    ),
    -- A claim about the PAST must name what it matched; a claim of novelty must
    -- not name anything; a hedge may name the one circuit it was unsure about.
    -- This is the parser's rule held by the storage layer, so a row contradicting
    -- itself cannot exist even if a future writer forgets to validate.
    CONSTRAINT ck_dcnv_match_rule CHECK (
        CASE novelty_class
            WHEN 'NEW' THEN matched_prior_candidate_pk IS NULL
            WHEN 'ALIAS' THEN matched_prior_candidate_pk IS NOT NULL
            WHEN 'REFORMULATION' THEN matched_prior_candidate_pk IS NOT NULL
            ELSE TRUE
        END
    ),
    -- A circuit is never its own prior art.
    CONSTRAINT ck_dcnv_not_self_match CHECK (
        matched_prior_candidate_pk IS NULL OR matched_prior_candidate_pk <> candidate_pk
    ),
    -- The service rejects a blank reason; this is the same rule in storage.
    CONSTRAINT ck_dcnv_reason_not_blank CHECK (btrim(short_reason) <> '')
);

COMMENT ON TABLE discovery_circuit_novelty_verdicts IS
    'APPEND-ONLY per-Circuit verdicts of one novelty assessment: the class, the earlier circuit it was '
    'matched against (if any), and the reason. Never updated, never deleted. Moves no candidate status, '
    'merges nothing, and rejects nothing.';

COMMENT ON COLUMN discovery_circuit_novelty_verdicts.candidate_pk IS
    'The judged proposal (discovery_candidates.candidate_pk) — a Circuit of the assessed run. ON DELETE '
    'RESTRICT: a candidate with verdict history cannot be silently removed.';

COMMENT ON COLUMN discovery_circuit_novelty_verdicts.matched_prior_candidate_pk IS
    'The EARLIER circuit this one was judged to be an alias or reformulation of. NULL for NEW. Its run '
    'is reachable via discovery_candidates.discovery_run_pk and is deliberately not duplicated here.';

COMMENT ON COLUMN discovery_circuit_novelty_verdicts.short_reason IS
    'The model''s one-sentence justification. Contents are never written to logs.';

-- ===========================================================================
-- 4. indexes
-- ===========================================================================
-- The one real read: "the latest assessment of this run" (the orchestrator's
-- question, and the GET endpoint's). The UNIQUE constraint on
-- (target_run_pk, assessor_prompt_version, model_name) already serves the
-- idempotency lookup.
CREATE INDEX IF NOT EXISTS idx_dcna_target_run
    ON discovery_circuit_novelty_assessments (target_run_pk, created_at DESC);

-- Reading one assessment's verdicts, in the target run's own circuit order.
CREATE INDEX IF NOT EXISTS idx_dcnv_assessment
    ON discovery_circuit_novelty_verdicts (assessment_pk, candidate_pk);

-- "Which assessments matched this earlier circuit?" — a reverse lookup used when
-- a future layer asks what a stored circuit was ever claimed to duplicate.
CREATE INDEX IF NOT EXISTS idx_dcnv_matched_prior
    ON discovery_circuit_novelty_verdicts (matched_prior_candidate_pk)
    WHERE matched_prior_candidate_pk IS NOT NULL;
