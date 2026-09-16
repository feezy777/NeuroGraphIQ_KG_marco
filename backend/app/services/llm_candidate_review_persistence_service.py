"""Phase P0-3B — persist ONE Candidate Review decision.

Two writes, one transaction:

    candidate_review_records   INSERT  (append-only: what was decided, by whom)
    discovery_candidates       UPDATE  (status now says what the decision made it)

They are one atomic fact. A review record without the status move, or a status
move without the record, are both forbidden states — a decision nobody can audit,
or an audit trail that does not describe the row it claims to.

Frozen boundaries:
  * ALL review semantics come from ``llm_candidate_review_contract`` (P0-3A).
    This module carries NO decision->status map and NO transition table of its
    own: a second copy is how the contract would stop being the authority.
  * This phase implements only decisions FROM ``proposed`` (ACCEPT / REJECT /
    DEFER). Re-opening a deferred candidate is NOT implemented: no P0-3A decision
    maps to ``proposed``, so there is no governed operation to call yet.
  * A terminal candidate is never silently re-decided. A second review raises.
  * It writes ONLY those two tables and NO canonical knowledge: accepted is
    still only a candidate. Nothing here resolves, canonicalizes or promotes.
  * Concurrency is the database's job: the candidate row is locked FOR UPDATE
    before its status is read, so there is no read-then-write window in which two
    reviewers could both decide the same proposal.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import llm_candidate_review_contract as review_contract

#: The one route a reviewable candidate may belong to.
LLM_DISCOVERY = "LLM_DISCOVERY"


# ===========================================================================
# typed errors — the caller maps these onto its own contract
# ===========================================================================
class CandidateReviewError(Exception):
    """Base for a review-persistence failure. Never carries SQL or DB internals."""


class CandidateReviewCandidateNotFound(CandidateReviewError):
    """No candidate with that public candidate_id."""

    def __init__(self, candidate_id: str) -> None:
        super().__init__(f"Candidate '{candidate_id}' not found")
        self.candidate_id = candidate_id


class CandidateReviewWrongDiscoveryType(CandidateReviewError):
    """The candidate exists but belongs to a non-LLM run.

    Explicit, never silent: reviewing a LITERATURE_DISCOVERY candidate through
    the LLM review path would decide something this contract does not own.
    """

    def __init__(self, candidate_id: str, discovery_type: str) -> None:
        super().__init__(
            f"Candidate '{candidate_id}' belongs to {discovery_type}, not {LLM_DISCOVERY}"
        )
        self.candidate_id = candidate_id
        self.discovery_type = discovery_type


class CandidateReviewInvalidReviewer(CandidateReviewError):
    """The reviewer identity is missing or blank."""


class CandidateReviewInvalidDecision(CandidateReviewError):
    """The decision is not one of the frozen P0-3A review decisions."""


class InvalidCandidateReviewTransition(CandidateReviewError):
    """The decision is legal in general, but not from the candidate's current status.

    Raised for a second review of an already-decided candidate, and for the not
    yet implemented re-opening of a deferred one.
    """

    def __init__(self, candidate_id: str, from_status: str, decision: str) -> None:
        super().__init__(
            f"Candidate '{candidate_id}' is '{from_status}' and cannot be reviewed"
            f" with {decision}"
        )
        self.candidate_id = candidate_id
        self.from_status = from_status
        self.decision = decision


@dataclass(frozen=True)
class CandidateReviewPersistenceResult:
    """What one review decision produced. Public fields only.

    ``next_gate`` is DERIVED from the P0-3A contract on every call and is never
    stored: a gate is a workflow stage, not a column.
    """

    review_id: str
    candidate_id: str
    decision: str
    from_status: str
    to_status: str
    reviewer: str
    reviewer_note: str | None
    created_at: datetime
    next_gate: str


# ===========================================================================
# SQL (module constants — never built from caller input)
# ===========================================================================
# FOR UPDATE OF c locks the CANDIDATE row only, not the run it is joined to:
# the review serializes on the proposal, and nothing else is held.
_LOCK_CANDIDATE_SQL = text(
    """
    SELECT c.candidate_pk, c.status, r.discovery_type
    FROM discovery_candidates c
    JOIN knowledge_discovery_runs r ON r.run_pk = c.discovery_run_pk
    WHERE c.candidate_id = :candidate_id
    FOR UPDATE OF c
    """
)

_INSERT_REVIEW_SQL = text(
    """
    INSERT INTO candidate_review_records
        (candidate_pk, decision, from_status, to_status, reviewer, reviewer_note)
    VALUES
        (:candidate_pk, :decision, :from_status, :to_status, :reviewer, :reviewer_note)
    RETURNING review_id, created_at
    """
)

_UPDATE_STATUS_SQL = text(
    """
    UPDATE discovery_candidates
    SET status = :to_status, updated_at = now()
    WHERE candidate_pk = :candidate_pk
    """
)


def _normalize_reviewer(reviewer: str) -> str:
    """An audit identity must be stated, never inferred.

    Deliberately NOT derived from hostname, OS user, git config or the
    environment: a review that cannot name its reviewer is not an audit record.
    """
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise CandidateReviewInvalidReviewer(
            "reviewer is required and must not be blank"
        )
    return reviewer.strip()


def _normalize_decision(decision: object) -> review_contract.CandidateReviewDecision:
    """Validate through the P0-3A vocabulary, not a local copy of it."""
    try:
        return (
            decision
            if isinstance(decision, review_contract.CandidateReviewDecision)
            else review_contract.CandidateReviewDecision(decision)
        )
    except ValueError:
        raise CandidateReviewInvalidDecision(
            f"'{decision}' is not a candidate review decision"
        ) from None


async def persist_candidate_review(
    session: AsyncSession,
    *,
    candidate_id: str,
    decision: object,
    reviewer: str,
    reviewer_note: str | None = None,
) -> CandidateReviewPersistenceResult:
    """Record one review decision and move the candidate's status atomically.

    ``candidate_id`` is the PUBLIC id; the internal pk is resolved here and never
    returned. The two writes and the commit are one transaction: if either fails,
    both are rolled back and the session is left usable.

    Ordering, all inside that transaction: lock the candidate row, read its
    status, verify the transition against P0-3A, insert the review record, update
    the status, commit. Pure input validation happens before the lock because it
    needs no database state, and taking a row lock to reject a blank reviewer
    would be pointless.
    """
    # 1. Pure input checks first — these must not touch the database.
    reviewer = _normalize_reviewer(reviewer)
    normalized = _normalize_decision(decision)

    try:
        # 2. Lock the candidate. From here to commit, no other transaction can
        #    change this row, so the status read below cannot go stale.
        row = (
            await session.execute(_LOCK_CANDIDATE_SQL, {"candidate_id": candidate_id})
        ).mappings().one_or_none()
        if row is None:
            raise CandidateReviewCandidateNotFound(candidate_id)
        if row["discovery_type"] != LLM_DISCOVERY:
            raise CandidateReviewWrongDiscoveryType(candidate_id, row["discovery_type"])

        from_status = row["status"]

        # 3. Which status this decision produces, and whether it is legal FROM
        #    the status we just locked. Both answers come from P0-3A.
        to_status = review_contract.review_decision_to_status(normalized)
        if not review_contract.can_transition_candidate_status(from_status, to_status):
            raise InvalidCandidateReviewTransition(
                candidate_id, from_status, normalized.value
            )

        # 4. Append the record, then move the status — one transaction, so the
        #    two cannot disagree afterwards.
        inserted = (
            await session.execute(
                _INSERT_REVIEW_SQL,
                {
                    "candidate_pk": row["candidate_pk"],
                    "decision": normalized.value,
                    "from_status": from_status,
                    "to_status": to_status.value,
                    "reviewer": reviewer,
                    "reviewer_note": reviewer_note,
                },
            )
        ).mappings().one()
        await session.execute(
            _UPDATE_STATUS_SQL,
            {"candidate_pk": row["candidate_pk"], "to_status": to_status.value},
        )
        await session.commit()
    except Exception:
        # Both writes, or neither. A rollback failure must not mask the original.
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001
            pass
        raise

    return CandidateReviewPersistenceResult(
        review_id=inserted["review_id"],
        candidate_id=candidate_id,
        decision=normalized.value,
        from_status=from_status,
        to_status=to_status.value,
        reviewer=reviewer,
        reviewer_note=reviewer_note,
        created_at=inserted["created_at"],
        next_gate=review_contract.next_candidate_gate(to_status),
    )
