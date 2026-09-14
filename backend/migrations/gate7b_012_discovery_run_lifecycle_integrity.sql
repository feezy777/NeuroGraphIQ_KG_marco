-- Gate 7B Phase 2B — Discovery Run Lifecycle Integrity
--
-- Strengthens knowledge_discovery_runs (created in gate7b_011) with the
-- lifecycle invariants that Phase 2B's controlled transitions depend on.
-- Adds NO table, NO column, NO trigger, and touches NO scientific table.
--
-- Phase 2B is the correct point for this: the table is empty, so every
-- constraint below can be validated without rewriting a single row.
--
-- Frozen lifecycle (docs/KNOWLEDGE_PRODUCTION_ARCHITECTURE.md §14):
--
--     CREATE → QUEUED ──start──→ RUNNING ──complete──→ COMPLETED
--                     │               ├──fail────→ FAILED
--                     │               └──cancel──→ CANCELLED
--                     ├──fail────→ FAILED
--                     └──cancel──→ CANCELLED
--
--     COMPLETED / FAILED / CANCELLED are TERMINAL and immutable.
--
-- Frozen boundaries honored:
--   * ONLY structural invariants live in SQL. The state machine itself (which
--     transition is legal from which state, and idempotency) is enforced in
--     the lifecycle service inside one locked transaction — a CHECK cannot
--     express "you may not move COMPLETED → RUNNING", only "this row is
--     well-formed".
--   * discovery_type ↔ outcome compatibility is deliberately NOT a SQL
--     constraint: it is a function of discovery_type and belongs in the
--     lifecycle service (LLM_DISCOVERY is not an evidence-search route, so it
--     may not complete with NO_EVIDENCE_FOUND).
--   * No giant SQL state machine.
--   * Idempotent: re-runnable (guarded constraint adds + IF NOT EXISTS index).

-- ===========================================================================
-- 1. Outcome ⇄ status consistency
-- ===========================================================================
-- outcome is the SCIENTIFIC result of a finished run. A run that has not
-- completed has no scientific result yet, and a completed run must state one.
-- This is the structural half of "status != outcome": the two are independent
-- vocabularies but not independently optional.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_kdr_outcome_matches_status'
          AND conrelid = 'knowledge_discovery_runs'::regclass
    ) THEN
        ALTER TABLE knowledge_discovery_runs
            ADD CONSTRAINT ck_kdr_outcome_matches_status CHECK (
                (status = 'COMPLETED' AND outcome IS NOT NULL)
                OR (status <> 'COMPLETED' AND outcome IS NULL)
            );
    END IF;
END $$;

-- ===========================================================================
-- 2. finished_at by status
-- ===========================================================================
-- Only a terminal state has finished. FAILED and CANCELLED may occur before
-- execution begins (QUEUED → FAILED / CANCELLED) or after it started, so
-- started_at stays free for them.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_kdr_finished_at_by_status'
          AND conrelid = 'knowledge_discovery_runs'::regclass
    ) THEN
        ALTER TABLE knowledge_discovery_runs
            ADD CONSTRAINT ck_kdr_finished_at_by_status CHECK (
                (status IN ('QUEUED', 'RUNNING') AND finished_at IS NULL)
                OR (status IN ('COMPLETED', 'FAILED', 'CANCELLED') AND finished_at IS NOT NULL)
            );
    END IF;
END $$;

-- ===========================================================================
-- 3. started_at required once execution has begun
-- ===========================================================================
-- RUNNING and COMPLETED both mean "execution started", so started_at must be
-- present. The ck_kdr_finished_at_by_status constraint above already requires
-- finished_at for COMPLETED, so COMPLETED ends up requiring BOTH stamps.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_kdr_started_at_required_after_start'
          AND conrelid = 'knowledge_discovery_runs'::regclass
    ) THEN
        ALTER TABLE knowledge_discovery_runs
            ADD CONSTRAINT ck_kdr_started_at_required_after_start CHECK (
                status NOT IN ('RUNNING', 'COMPLETED') OR started_at IS NOT NULL
            );
    END IF;
END $$;

-- ===========================================================================
-- 4. At most ONE active run per (BrainRegion seed, discovery type)
-- ===========================================================================
-- Frozen invariant (§15): for one seed_region_pk + discovery_type there may be
-- at most one run with status IN ('QUEUED','RUNNING'). Terminal history never
-- blocks a new run.
--
-- This is a PARTIAL UNIQUE INDEX, not an application pre-check, because
-- "SELECT then INSERT" is race-prone: two concurrent creates can both observe
-- "no active run" and both insert. The index makes the database the final
-- authority, and the lifecycle service converts the resulting IntegrityError
-- into 409 Conflict.

CREATE UNIQUE INDEX IF NOT EXISTS uq_kdr_active_per_seed_type
    ON knowledge_discovery_runs (seed_region_pk, discovery_type)
    WHERE status IN ('QUEUED', 'RUNNING');

COMMENT ON INDEX uq_kdr_active_per_seed_type IS
    'At most one active (QUEUED/RUNNING) Discovery Run per BrainRegion seed + discovery type. '
    'Terminal runs (COMPLETED/FAILED/CANCELLED) are excluded, so history never blocks a new run. '
    'Races are resolved by the database, not by a SELECT-then-INSERT pre-check.';
