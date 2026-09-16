-- Gate 7B Phase P0-3B.1 — Candidate Review audit integrity hardening
--
-- Two ADDITIVE guards on candidate_review_records. Neither changes P0-3B
-- behaviour: every review the service performs still succeeds, and nothing it
-- does is newly rejected. These are the LAST line of defence for a writer that
-- bypasses the service and speaks SQL directly.
--
--   1. the decision must match the transition it claims   (a CHECK)
--   2. a review record may never be updated or deleted    (a trigger)
--
-- gate7b_017 is NOT modified: its SHA-256 is already in the migration ledger.
-- This migration adds no table, no column, and touches no other table.
--
-- Idempotent: re-runnable, using this repository's existing idioms —
-- the guarded pg_constraint DO block (gate7b_012) and DROP TRIGGER IF EXISTS
-- before CREATE TRIGGER (the legacy updated_at triggers).

-- ===========================================================================
-- 1. decision ⇄ transition consistency
-- ===========================================================================
-- The service asks the P0-3A contract whether a move is legal. This constraint
-- states the same three moves in SQL, so a record claiming a transition the
-- contract does not allow cannot exist — even one INSERTed by hand.
--
-- Deliberately absent: any ACCEPT/REJECT/DEFER that starts from a status other
-- than 'proposed'. Re-opening a deferred candidate has no governed operation
-- yet (no P0-3A decision produces 'proposed'), so no such row may be written.
--
-- This makes ck_crr_status_moved (gate7b_017) redundant, since all three legal
-- branches already differ in status. That constraint is left in place rather
-- than dropped: gate7b_017 is frozen, and a redundant guard costs nothing.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_crr_decision_matches_transition'
          AND conrelid = 'candidate_review_records'::regclass
    ) THEN
        ALTER TABLE candidate_review_records
            ADD CONSTRAINT ck_crr_decision_matches_transition CHECK (
                (decision = 'ACCEPT' AND from_status = 'proposed' AND to_status = 'accepted')
                OR (decision = 'REJECT' AND from_status = 'proposed' AND to_status = 'rejected')
                OR (decision = 'DEFER' AND from_status = 'proposed' AND to_status = 'deferred')
            );
    END IF;
END $$;

COMMENT ON CONSTRAINT ck_crr_decision_matches_transition ON candidate_review_records IS
    'A review record must claim a transition the P0-3A contract allows: ACCEPT/REJECT/DEFER each '
    'move proposed to exactly one status. Direct SQL cannot manufacture a contradictory record.';

-- ===========================================================================
-- 2. append-only guard
-- ===========================================================================
-- A review record is a historical fact. "Append-only" was enforced only by the
-- service's own restraint; this makes the DATABASE refuse the mutation, so the
-- property survives a future writer, a manual fix-up, or a stray DELETE.
--
-- BEFORE, not AFTER: the row must not be touched at all, not touched and then
-- complained about.
--
-- Deliberately NOT blocked: INSERT (the whole point), FK checks, and
-- transaction rollback — a rolled-back transaction is not a DELETE.

CREATE OR REPLACE FUNCTION infra.forbid_review_record_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'candidate_review_records is append-only: % is not permitted (review_id=%)',
        TG_OP, COALESCE(OLD.review_id, '<unknown>');
END;
$$;

COMMENT ON FUNCTION infra.forbid_review_record_mutation() IS
    'Rejects UPDATE and DELETE on candidate_review_records. A corrected review is a NEW record.';

DROP TRIGGER IF EXISTS trg_crr_append_only ON candidate_review_records;

CREATE TRIGGER trg_crr_append_only
BEFORE UPDATE OR DELETE ON candidate_review_records
FOR EACH ROW EXECUTE FUNCTION infra.forbid_review_record_mutation();
