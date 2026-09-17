-- Gate 7B Phase P0-4B — bounded automatic recovery from an EMPTY provider response
--
-- Adds ONE column to an existing table:
--
--   discovery_orchestration_view_states.consecutive_empty_response_failures
--
-- WHY THIS EXISTS
--   A live Round-13 attempt failed with LLM_EMPTY_RESPONSE: the provider returned
--   no content before its output budget ran out. The round immediately before it
--   succeeded with the same model, prompt and contract, so the event is
--   INTERMITTENT — and under the previous policy every occurrence stopped the
--   whole orchestration until a human resumed it.
--
--   One identical retry is worth trying before redesigning generation. This
--   column is what makes "one" enforceable across a process restart or a resume:
--   without durable state, a resume would hand out a fresh retry every time and
--   an unresolved intermittent failure could be retried forever.
--
-- Frozen boundaries honored:
--   * It is NOT zero_streak. A novelty zero is a scientific result ("this View
--     found nothing new"); a provider-empty is an operational event ("no answer
--     arrived"). Overloading one counter with both would make a transport hiccup
--     look like saturation.
--   * It counts CONSECUTIVE events only. Any successful Discovery resets it, so
--     an isolated hiccup hours apart never accumulates toward the limit.
--   * It is per VIEW: the streak belongs to the View whose rounds are failing.
--   * Adds no table and no other column. Idempotent: re-runnable.

-- ===========================================================================
-- 1. the column
-- ===========================================================================
ALTER TABLE discovery_orchestration_view_states
    ADD COLUMN IF NOT EXISTS consecutive_empty_response_failures
        INTEGER NOT NULL DEFAULT 0;

-- The CHECK is re-created rather than assumed, so a re-run converges on the
-- same constraint instead of erroring or silently skipping it.
ALTER TABLE discovery_orchestration_view_states
    DROP CONSTRAINT IF EXISTS ck_dcovs_empty_response_failures_non_negative;
ALTER TABLE discovery_orchestration_view_states
    ADD CONSTRAINT ck_dcovs_empty_response_failures_non_negative
        CHECK (consecutive_empty_response_failures >= 0);

-- The policy permits exactly ONE automatic retry, i.e. the orchestration may act
-- on a streak of 1 and must stop at 2. A value above 2 could only mean the guard
-- was bypassed, so storage refuses to hold one.
ALTER TABLE discovery_orchestration_view_states
    DROP CONSTRAINT IF EXISTS ck_dcovs_empty_response_failures_bounded;
ALTER TABLE discovery_orchestration_view_states
    ADD CONSTRAINT ck_dcovs_empty_response_failures_bounded
        CHECK (consecutive_empty_response_failures <= 2);

COMMENT ON COLUMN discovery_orchestration_view_states.consecutive_empty_response_failures IS
    'CONSECUTIVE LLM_EMPTY_RESPONSE failures for this View. 0 after any successful Discovery; 1 '
    'permits exactly one automatic retry; 2 BLOCKS. Durable so a restart or resume cannot hand out '
    'unlimited retries for one unresolved empty-response chain. Unrelated to zero_streak, which '
    'counts scientific novelty zeros.';
