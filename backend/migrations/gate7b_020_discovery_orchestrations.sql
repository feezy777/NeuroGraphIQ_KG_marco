-- Gate 7B Phase P0-4A — High-Recall Multi-View Discovery Orchestration
--
-- Creates TWO new tables (the 39th and 40th public tables):
--
--   discovery_orchestrations              — one automatic multi-view run
--   discovery_orchestration_view_states   — per-View control state
--
--     brain_regions (the SEED)
--           |
--     discovery_orchestrations            <- this parent: one orchestration
--           |
--     discovery_orchestration_view_states <- one row per View (A/B/C/D)
--           |
--     knowledge_discovery_runs            — the rounds it drove
--     discovery_circuit_novelty_assessments — the judgements it acted on
--
-- WHY THIS EXISTS
--   The four Discovery Views, continuation and the durable novelty assessor are
--   each validated on their own. This layer is what runs them AUTOMATICALLY:
--   keep a View alive while it still produces semantic novelty, confirm a zero
--   once, and move on after two consecutive zeros. What it stores is CONTROL
--   state — where the loop is, what it decided, and where it may resume.
--
-- Frozen boundaries honored:
--   * Discovery Runs and Novelty Assessments remain the SCIENTIFIC AUTHORITIES.
--     This layer stores no candidate, no verdict, no class count and no circuit
--     universe of its own. Where a count is stored it is a DECISION SNAPSHOT:
--     the number the loop actually acted on, kept so an audit can reconstruct
--     the reasoning without replaying provider calls.
--   * NOT Canonicalization. Nothing here merges across Views, resolves identity,
--     promotes, or changes a candidate's status. Cross-view duplicates are
--     expected and deliberately left alone.
--   * ALIAS and REFORMULATION are not "failures" here: a View whose rounds keep
--     producing only those is exactly a View that has stopped being productive,
--     which is what the zero-streak rule exists to notice.
--   * Idempotent: re-runnable.

-- ===========================================================================
-- 1. public id sequence
-- ===========================================================================
-- Deliberately NOT infra.next_ngiq_id(): that function allocates CANONICAL
-- entity ids from a frozen 29-type registry. An orchestration is workflow, not
-- knowledge. Mirrors gate7b_013 / gate7b_016 / gate7b_017 / gate7b_019.

CREATE SEQUENCE IF NOT EXISTS infra.ngiq_dco_seq;

-- ===========================================================================
-- 2. discovery_orchestrations (parent)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS discovery_orchestrations (
    orchestration_pk  BIGSERIAL   PRIMARY KEY,
    orchestration_id  VARCHAR(32) NOT NULL UNIQUE
        DEFAULT 'NGIQ-DCO-' || lpad(nextval('infra.ngiq_dco_seq')::text, 8, '0'),

    seed_region_pk    BIGINT      NOT NULL,

    -- Which discovery contract this orchestration drives. Stored so an old
    -- orchestration stays interpretable after the contract is revised: the
    -- View order and the View identifiers are theirs, not this table's.
    strategy_family   VARCHAR(32) NOT NULL,
    strategy_version  VARCHAR(32) NOT NULL,

    status            VARCHAR(32) NOT NULL DEFAULT 'READY',
    -- The View the loop is currently working on. NULL before the first step.
    current_view      VARCHAR(64),

    -- Consecutive successful zero-novelty assessments IN THE CURRENT VIEW.
    -- Reset to 0 by any round with semantic novelty, and by moving to a new
    -- View. This is the number the two-zero rule reads.
    zero_streak       INTEGER     NOT NULL DEFAULT 0,

    -- SAFETY BUDGET, not a saturation signal. A budget pause means "this
    -- execution may not spend more"; it says nothing about whether the View is
    -- exhausted, and must never be recorded as saturation.
    discovery_call_budget INTEGER NOT NULL,
    -- Cumulative over the orchestration's whole life, across resumes: the
    -- honest cost ledger.
    discovery_calls_used  INTEGER NOT NULL DEFAULT 0,
    novelty_calls_used    INTEGER NOT NULL DEFAULT 0,

    stop_reason       TEXT,

    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at        TIMESTAMPTZ,
    finished_at       TIMESTAMPTZ,

    CONSTRAINT fk_dco_seed_region
        FOREIGN KEY (seed_region_pk) REFERENCES brain_regions (entity_pk)
        ON DELETE RESTRICT,

    -- The orchestration lifecycle. Deliberately NO global SATURATED: saturation
    -- is a property of one View (see discovery_orchestration_view_states), and
    -- a global one would be a lie the moment there are four Views.
    CONSTRAINT ck_dco_status CHECK (
        status IN ('READY', 'RUNNING', 'PAUSED_BY_BUDGET', 'BLOCKED', 'COMPLETED')
    ),
    -- The frozen safety envelope. A budget of 0 would make the orchestration a
    -- no-op and a budget in the thousands would make it an unbounded process.
    CONSTRAINT ck_dco_budget_range CHECK (
        discovery_call_budget BETWEEN 1 AND 20
    ),
    CONSTRAINT ck_dco_counts_non_negative CHECK (
        discovery_calls_used >= 0 AND novelty_calls_used >= 0 AND zero_streak >= 0
    ),
    -- COMPLETED and BLOCKED carry a reason; the working states need not.
    CONSTRAINT ck_dco_terminal_has_reason CHECK (
        status NOT IN ('COMPLETED', 'BLOCKED') OR stop_reason IS NOT NULL
    )
);

COMMENT ON TABLE discovery_orchestrations IS
    'One automatic multi-view high-recall discovery run over one BrainRegion seed: the control state of '
    'the A->B->C->D loop, its budget and its stop reason. Records decisions, never candidates. NOT '
    'canonical knowledge and NOT a second candidate universe.';

COMMENT ON COLUMN discovery_orchestrations.orchestration_id IS
    'Public orchestration id (NGIQ-DCO-*). Deliberately NOT allocated by infra.next_ngiq_id(), which '
    'issues CANONICAL entity ids that a workflow control row has no standing to hold.';

COMMENT ON COLUMN discovery_orchestrations.status IS
    'READY / RUNNING / PAUSED_BY_BUDGET / BLOCKED / COMPLETED. PAUSED_BY_BUDGET is a SAFETY pause, not '
    'saturation. Saturation is per-View and lives in discovery_orchestration_view_states.';

COMMENT ON COLUMN discovery_orchestrations.zero_streak IS
    'Consecutive successful zero-novelty assessments in the CURRENT View. Two of them saturate the View. '
    'A FAILED round never advances this: a failure is not a zero.';

COMMENT ON COLUMN discovery_orchestrations.discovery_call_budget IS
    'Maximum NEW Discovery provider calls for ONE execution (1..20). Resuming starts a fresh execution '
    'allowance; discovery_calls_used keeps the cumulative ledger.';

COMMENT ON COLUMN discovery_orchestrations.discovery_calls_used IS
    'Cumulative Discovery provider calls over the whole orchestration, across resumes. A call that FAILED '
    'still counts: under-reporting cost is worse than an unflattering number.';

-- ONE ACTIVE ORCHESTRATION PER SEED, enforced by the database rather than by a
-- caller's memory. READY/RUNNING/PAUSED_BY_BUDGET/BLOCKED are all "in flight":
-- a BLOCKED orchestration is one whose defect has not been resolved yet, and
-- starting a second one beside it is exactly the parallel process this forbids.
-- Only COMPLETED frees the seed.
CREATE UNIQUE INDEX IF NOT EXISTS uq_dco_one_active_per_seed
    ON discovery_orchestrations (seed_region_pk)
    WHERE status <> 'COMPLETED';

-- ===========================================================================
-- 3. discovery_orchestration_view_states (child)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS discovery_orchestration_view_states (
    view_state_pk BIGSERIAL   PRIMARY KEY,
    orchestration_pk BIGINT   NOT NULL,

    discovery_view VARCHAR(64) NOT NULL,
    -- The frozen A->B->C->D position. Stored rather than derived from the view
    -- name so "which View comes next" survives a change of vocabulary.
    position       INTEGER     NOT NULL,

    status         VARCHAR(32) NOT NULL DEFAULT 'PENDING',

    zero_streak    INTEGER     NOT NULL DEFAULT 0,

    -- Where this View resumes from. Both are the AUTHORITIES for their data;
    -- this row only points at them.
    latest_successful_run_pk         BIGINT,
    latest_novelty_assessment_pk     BIGINT,

    successful_round_count INTEGER NOT NULL DEFAULT 0,
    failed_attempt_count   INTEGER NOT NULL DEFAULT 0,

    -- DECISION SNAPSHOT: the semantic_new_count the loop last acted on. Kept so
    -- an audit can see what the decision was made from without re-reading (and
    -- possibly re-running) an assessment.
    semantic_new_count     INTEGER,

    stop_reason    TEXT,

    started_at     TIMESTAMPTZ,
    completed_at   TIMESTAMPTZ,

    CONSTRAINT fk_dcovs_orchestration
        FOREIGN KEY (orchestration_pk)
        REFERENCES discovery_orchestrations (orchestration_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_dcovs_latest_run
        FOREIGN KEY (latest_successful_run_pk)
        REFERENCES knowledge_discovery_runs (run_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_dcovs_latest_assessment
        FOREIGN KEY (latest_novelty_assessment_pk)
        REFERENCES discovery_circuit_novelty_assessments (assessment_pk)
        ON DELETE RESTRICT,

    CONSTRAINT uq_dcovs_orchestration_view UNIQUE (orchestration_pk, discovery_view),
    CONSTRAINT uq_dcovs_orchestration_position UNIQUE (orchestration_pk, position),

    -- PENDING / RUNNING / BLOCKED are incomplete; the other two are terminal for
    -- this View. There is deliberately no per-View PAUSED: a budget pause stops
    -- the ORCHESTRATION mid-View, and the View is still RUNNING — saying
    -- "PAUSED" in both places would be one fact stored twice.
    CONSTRAINT ck_dcovs_status CHECK (
        status IN ('PENDING', 'RUNNING', 'SATURATED_BY_ZERO_NOVELTY',
                   'BLOCKED', 'COMPLETE')
    ),
    CONSTRAINT ck_dcovs_position_range CHECK (position BETWEEN 1 AND 4),
    CONSTRAINT ck_dcovs_counts_non_negative CHECK (
        zero_streak >= 0 AND successful_round_count >= 0 AND failed_attempt_count >= 0
        AND (semantic_new_count IS NULL OR semantic_new_count >= 0)
    ),
    -- Saturation is EXACTLY "two consecutive zero-novelty rounds". A row that
    -- claims saturation without the streak cannot be written.
    CONSTRAINT ck_dcovs_saturated_requires_streak CHECK (
        status <> 'SATURATED_BY_ZERO_NOVELTY' OR zero_streak >= 2
    ),
    -- COMPLETE is the whole-orchestration end state for the LAST View; a View
    -- that finished its work by saturating says so.
    CONSTRAINT ck_dcovs_terminal_has_reason CHECK (
        status NOT IN ('SATURATED_BY_ZERO_NOVELTY', 'COMPLETE', 'BLOCKED')
        OR stop_reason IS NOT NULL
    )
);

COMMENT ON TABLE discovery_orchestration_view_states IS
    'Per-View control state of one orchestration: how far the View got, what it last measured, and where '
    'it resumes from. One row per (orchestration, View). Records control state, never candidates.';

COMMENT ON COLUMN discovery_orchestration_view_states.latest_successful_run_pk IS
    'The newest COMPLETED run of this View. This is what the loop continues FROM — never Round 1 — so an '
    'orchestration attaches to discovery history that already exists.';

COMMENT ON COLUMN discovery_orchestration_view_states.latest_novelty_assessment_pk IS
    'The stored assessment the loop last acted on. Its presence is also what makes a resume free: an '
    'existing assessment is reused rather than recomputed.';

COMMENT ON COLUMN discovery_orchestration_view_states.zero_streak IS
    'Consecutive successful zero-novelty rounds in THIS View. Only a SUCCESSFUL assessment can change it '
    '— a failed round or a failed assessment leaves it exactly where it was.';

COMMENT ON COLUMN discovery_orchestration_view_states.semantic_new_count IS
    'The semantic_new_count (NEW + BORDERLINE) the loop last read for this View. A decision snapshot, not '
    'a source of truth: the assessment row remains authoritative.';

-- ===========================================================================
-- 4. indexes
-- ===========================================================================
-- "Every View of this orchestration, in order" — the loop's own read.
CREATE INDEX IF NOT EXISTS idx_dcovs_orchestration
    ON discovery_orchestration_view_states (orchestration_pk, position);

-- "The latest orchestration for this seed" — the API's read. Served by the
-- partial unique index for the active case; this covers the completed history.
CREATE INDEX IF NOT EXISTS idx_dco_seed
    ON discovery_orchestrations (seed_region_pk, created_at DESC);
