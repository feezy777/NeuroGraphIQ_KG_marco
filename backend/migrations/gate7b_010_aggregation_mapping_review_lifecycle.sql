-- Gate 7B Phase 1F-B — Aggregation Mapping Scientific Review Lifecycle (minimal)
--
-- Adds a HUMAN scientific review lifecycle to brain_region_aggregation_mappings,
-- SEPARATE from the record lifecycle (record_status). This is a deliberate
-- minimal extension:
--   * review_status  VARCHAR(24) NOT NULL DEFAULT 'pending'
--   * reviewed_by    VARCHAR(64)   (reviewer identity)
--   * reviewed_at    TIMESTAMPTZ
-- plus rollup safety:
--   * ck_agg_rollup_requires_contained_in — only mapping_relation='contained_in'
--     may carry rollup_eligible / is_primary_rollup = TRUE. dominant_overlap and
--     partial_overlap remain rollup_eligible=FALSE even when approved.
--   * uq_agg_primary_rollup_active_approved — partial UNIQUE: one source has at
--     most ONE active+approved+primary rollup target (no two hierarchical
--     parents). Proposed / deprecated / non-primary rows are untouched.
--
-- Frozen boundaries honored:
--   * review_status is NOT record_status; record_status stays as the record
--     lifecycle (proposed/active/deprecated/merged).
--   * scientific freeze (NO_G1_ROLLUP / CONFLICT_REVIEW) stays in the decision
--     artifacts; no target_region_pk=NULL rows, no artificial aggregation rows.
--   * No review UI / promotion / candidate importer this round.
--   * Idempotent: re-runnable (ADD COLUMN IF NOT EXISTS + guarded constraints).

-- ===========================================================================
-- 1. review lifecycle columns
-- ===========================================================================

ALTER TABLE brain_region_aggregation_mappings
    ADD COLUMN IF NOT EXISTS review_status VARCHAR(24) NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS reviewed_by   VARCHAR(64),
    ADD COLUMN IF NOT EXISTS reviewed_at   TIMESTAMPTZ;

-- vocabulary identical to knowledge_assertions.review_status / region_mappings.review_status
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_agg_review_status'
          AND conrelid = 'brain_region_aggregation_mappings'::regclass
    ) THEN
        ALTER TABLE brain_region_aggregation_mappings
            ADD CONSTRAINT ck_agg_review_status CHECK (
                review_status IN ('pending', 'approved', 'rejected', 'uncertain', 'needs_revision')
            );
    END IF;
END $$;

-- ===========================================================================
-- 2. rollup safety: only contained_in may roll up (dominant/partial never rollup)
-- ===========================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_agg_rollup_requires_contained_in'
          AND conrelid = 'brain_region_aggregation_mappings'::regclass
    ) THEN
        ALTER TABLE brain_region_aggregation_mappings
            ADD CONSTRAINT ck_agg_rollup_requires_contained_in CHECK (
                rollup_eligible = FALSE AND is_primary_rollup = FALSE
                OR mapping_relation = 'contained_in'
            );
    END IF;
END $$;

-- ===========================================================================
-- 3. primary rollup uniqueness: one source -> at most one active+approved
--    primary hierarchical parent. Proposed / deprecated / non-primary rows
--    are excluded by the partial predicate.
-- ===========================================================================

CREATE UNIQUE INDEX IF NOT EXISTS uq_agg_primary_rollup_active_approved
    ON brain_region_aggregation_mappings (source_region_pk)
    WHERE record_status = 'active'
      AND review_status = 'approved'
      AND rollup_eligible = TRUE
      AND is_primary_rollup = TRUE;

COMMENT ON COLUMN brain_region_aggregation_mappings.review_status IS
    'Human scientific review lifecycle (separate from record_status). '
    'pending on creation; only a human may set approved/rejected/uncertain/needs_revision. '
    'approved = "scientific relation confirmed", NOT a license to auto-roll-up.';

COMMENT ON COLUMN brain_region_aggregation_mappings.reviewed_by IS
    'Identity of the human reviewer who last set review_status.';

COMMENT ON COLUMN brain_region_aggregation_mappings.reviewed_at IS
    'Timestamp of the last human review action.';
