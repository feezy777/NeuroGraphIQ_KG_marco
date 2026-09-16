-- Gate 7B Phase P0-3B — Candidate Review Records (append-only)
--
-- Creates ONE new table (the 36th public table):
--
--   candidate_review_records — one human review DECISION about one candidate.
--
--     discovery_candidates (the PROPOSAL)
--           |
--     candidate_review_records      <- this table: what a reviewer decided, when
--
-- Frozen boundaries honored:
--   * APPEND-ONLY. There is deliberately NO updated_at and no record_status: a
--     review record is a historical fact. A decision that is later changed is a
--     NEW record, never an edit of the old one. Nothing in this table is ever
--     updated or deleted.
--   * A review record is NOT the candidate's status. This table says what a
--     reviewer decided and when; discovery_candidates.status holds the
--     materialized CURRENT status. Both are written in ONE transaction by the
--     persistence service — neither is derived from the other at read time.
--   * A review record is NOT a kg_entities entity and gets NO entry in the
--     frozen infra.next_ngiq_id() registry: a decision about a proposal has no
--     standing to hold a canonical id. Its public id follows the Gate7B
--     WORKFLOW-layer convention (publication_discovery_hits NGIQ-PDH-,
--     discovery_candidates NGIQ-DC-).
--   * NO canonical side. There is deliberately NO FK to kg_entities, evidence,
--     knowledge_assertions, publications, entity_aliases, entity_xrefs, or any
--     resolution / promotion table. `accepted` is still only a candidate; this
--     phase resolves, canonicalizes and promotes nothing.
--   * The two status columns constrain the STORED VOCABULARY only. Which
--     transition is legal is owned by the P0-3A contract, not by a CHECK: a
--     CHECK can say "this row is well-formed", never "this move was allowed".
--   * Idempotent: re-runnable.

-- ===========================================================================
-- 1. public id sequence
-- ===========================================================================
-- Deliberately NOT infra.next_ngiq_id(): that function allocates CANONICAL
-- entity ids from a frozen 29-type registry. Mirrors gate7b_013 / gate7b_016.

CREATE SEQUENCE IF NOT EXISTS infra.ngiq_cr_seq;

-- ===========================================================================
-- 2. candidate_review_records
-- ===========================================================================

CREATE TABLE IF NOT EXISTS candidate_review_records (
    -- identity -------------------------------------------------------------
    review_pk      BIGSERIAL   PRIMARY KEY,
    review_id      VARCHAR(32) NOT NULL UNIQUE
        DEFAULT 'NGIQ-CR-' || lpad(nextval('infra.ngiq_cr_seq')::text, 8, '0'),

    -- which proposal was reviewed (internal key; never returned to a caller) --
    candidate_pk   BIGINT      NOT NULL,

    -- the decision, and the status move it produced -------------------------
    -- decision is the REVIEW ACTION (P0-3A CandidateReviewDecision).
    decision       VARCHAR(16) NOT NULL,
    -- from_status / to_status are CANDIDATE statuses (P0-3A CandidateStatus).
    -- Kept because "what did this decision actually change" must be answerable
    -- from the record alone, without replaying every earlier record.
    from_status    VARCHAR(16) NOT NULL,
    to_status      VARCHAR(16) NOT NULL,

    -- who decided, and why --------------------------------------------------
    reviewer       TEXT        NOT NULL,
    reviewer_note  TEXT,

    -- audit / time ----------------------------------------------------------
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT fk_crr_candidate
        FOREIGN KEY (candidate_pk) REFERENCES discovery_candidates (candidate_pk)
        ON DELETE RESTRICT,

    CONSTRAINT ck_crr_decision CHECK (
        decision IN ('ACCEPT', 'REJECT', 'DEFER')
    ),
    CONSTRAINT ck_crr_from_status CHECK (
        from_status IN ('proposed', 'accepted', 'rejected', 'deferred')
    ),
    CONSTRAINT ck_crr_to_status CHECK (
        to_status IN ('proposed', 'accepted', 'rejected', 'deferred')
    ),
    -- The service rejects a blank reviewer before it touches the database; this
    -- is the same rule held by the storage layer, so an anonymous decision
    -- cannot exist even if a future writer forgets to validate.
    CONSTRAINT ck_crr_reviewer_not_blank CHECK (btrim(reviewer) <> ''),
    -- A review that moves a candidate nowhere is not a review. P0-3A makes every
    -- terminal status non-reviewable, so no legal transition is a no-op and this
    -- guard cannot block a future governed path.
    CONSTRAINT ck_crr_status_moved CHECK (from_status <> to_status)
);

COMMENT ON TABLE candidate_review_records IS
    'APPEND-ONLY history of Candidate Review decisions: what a reviewer decided about one proposal, '
    'and when. Never updated, never deleted — a corrected decision is a NEW row. NOT the candidate''s '
    'current status (that is discovery_candidates.status) and NOT canonical knowledge.';

COMMENT ON COLUMN candidate_review_records.review_id IS
    'Public review id (NGIQ-CR-*). Deliberately NOT allocated by infra.next_ngiq_id(), which issues '
    'CANONICAL entity ids that a decision about a proposal has no standing to hold.';

COMMENT ON COLUMN candidate_review_records.candidate_pk IS
    'The reviewed proposal (discovery_candidates.candidate_pk). ON DELETE RESTRICT: a candidate with '
    'review history cannot be silently removed.';

COMMENT ON COLUMN candidate_review_records.decision IS
    'The review ACTION (ACCEPT / REJECT / DEFER). Uppercase on purpose: it is a decision, not a status, '
    'and must never be mistaken for a value of discovery_candidates.status.';

COMMENT ON COLUMN candidate_review_records.from_status IS
    'Candidate status BEFORE this decision. Stored so the record alone answers "what did this change".';

COMMENT ON COLUMN candidate_review_records.to_status IS
    'Candidate status AFTER this decision. Legality of the move is owned by the P0-3A contract.';

COMMENT ON COLUMN candidate_review_records.reviewer IS
    'Explicit caller-supplied audit identity. Never derived from hostname, OS user, git config or env.';

COMMENT ON COLUMN candidate_review_records.reviewer_note IS
    'Optional reviewer comment. Contents are never written to logs.';

-- ===========================================================================
-- 3. indexes
-- ===========================================================================
-- The one real read: a candidate's review history, newest first. (review_id has
-- its own UNIQUE index, which serves lookups by public id.)

CREATE INDEX IF NOT EXISTS idx_crr_candidate
    ON candidate_review_records (candidate_pk, created_at DESC);
