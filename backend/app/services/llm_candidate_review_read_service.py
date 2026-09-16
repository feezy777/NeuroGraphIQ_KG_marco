"""Phase P0-3C2 — read-only Candidate Review HISTORY for one candidate.

The read side of what Phase P0-3B made writable:

    discovery_candidates        (the PROPOSAL)
      -> candidate_review_records   (append-only: what a reviewer decided, when)

Tables read (SELECT only):

    candidate_review_records    the review history
    discovery_candidates        candidate identity
    knowledge_discovery_runs    the discovery channel

This module is STRICTLY READ-ONLY: SELECT only, never a write, never a commit,
never even a rollback. Writing belongs to
``llm_candidate_review_persistence_service`` (P0-3B), which is the only author
of a review record; this layer only reads back what that one stored. A GET must
not be able to move a candidate's status, append or alter a review record, or
touch a run.

Why this is NOT a function on the persistence service: a writer and a history
reader are different concerns with different lifetimes. The writer owns a row
lock and a transaction; the reader owns neither and must not be able to acquire
one. Splitting them keeps "can this read change anything?" answerable by reading
one small module.

Errors are DELIBERATELY the P0-3B types, imported rather than re-declared.
"candidate absent" and "wrong discovery channel" mean exactly the same thing to
a reader as to a reviewer, so the two endpoints must fail IDENTICALLY — same
class, same status, same body. A second pair of look-alike classes would make
that identity a coincidence maintained by two mappings instead of a fact.

Boundaries:
  * The history is a LIST, always returned in full. No deduplication, no
    collapsing, no "latest only": an append-only audit trail whose reader hides
    earlier records is not an audit trail. The order is chronological — earliest
    first — so the trail reads as the sequence of events it records.
  * Current P0-3A/P0-3B semantics allow at most one review per candidate (a
    decided candidate cannot be reviewed again; nothing returns it to
    ``proposed``). That is a fact about the CURRENT transition contract, NOT an
    API limit: nothing here assumes or requires exactly one row, so a future
    governed re-open needs no change on this side.
  * No canonical side. A review record is a decision about a PROPOSAL; nothing
    here resolves, canonicalizes or promotes anything.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

#: Reused, not re-declared — see the module docstring. Identical errors on both
#: the review action and the review history endpoints is the point.
from app.services.llm_candidate_review_persistence_service import (
    LLM_DISCOVERY,
    CandidateReviewCandidateNotFound,
    CandidateReviewWrongDiscoveryType,
)

__all__ = [
    "CandidateReviewHistoryItem",
    "list_reviews_for_candidate",
    "CandidateReviewCandidateNotFound",
    "CandidateReviewWrongDiscoveryType",
    "LLM_DISCOVERY",
]


# ===========================================================================
# read DTO — public fields only
# ===========================================================================
class CandidateReviewHistoryItem(BaseModel):
    """One review record, as a reader may see it.

    Internal keys are deliberately absent: ``review_pk`` and ``candidate_pk``
    are storage details and the public API is id-based. ``review_pk`` is not
    even SELECTed below — it appears only as the ORDER BY tie-break, so it
    cannot leak by accident.

    ``decision`` / ``from_status`` / ``to_status`` stay ``str`` rather than a
    Literal: their vocabulary is owned by the P0-3A contract and the database
    CHECK, and a third copy here would be a second authority that could drift
    from both.
    """

    model_config = ConfigDict(extra="forbid")

    review_id: str
    decision: str
    from_status: str
    to_status: str
    reviewer: str
    reviewer_note: str | None = None
    created_at: datetime


# ===========================================================================
# SQL (module constants — never built from caller input)
# ===========================================================================
# Resolves the candidate AND its discovery channel in one statement, so the
# endpoint can answer "absent" / "wrong channel" without a second round trip.
_SCOPE_SQL = text(
    """
    SELECT c.candidate_pk, r.discovery_type
    FROM discovery_candidates c
    JOIN knowledge_discovery_runs r ON r.run_pk = c.discovery_run_pk
    WHERE c.candidate_id = :candidate_id
    """
)

#: Chronological: earliest review first, so the list reads as the sequence of
#: events it records. ``review_pk`` is the tie-break and is NOT projected: two
#: records written in one transaction share ``created_at`` (it defaults to
#: ``now()``, the transaction start time), and a stable order must not depend on
#: a column the caller can see. Unique, so the order is total.
_HISTORY_SQL = text(
    """
    SELECT review_id,
           decision,
           from_status,
           to_status,
           reviewer,
           reviewer_note,
           created_at
    FROM candidate_review_records
    WHERE candidate_pk = :candidate_pk
    ORDER BY created_at ASC, review_pk ASC
    """
)


def _row_to_item(row: Mapping[str, Any]) -> CandidateReviewHistoryItem:
    """Map one history row to the public DTO. Pure function (unit-testable)."""
    return CandidateReviewHistoryItem(
        review_id=row["review_id"],
        decision=row["decision"],
        from_status=row["from_status"],
        to_status=row["to_status"],
        reviewer=row["reviewer"],
        reviewer_note=row["reviewer_note"],
        created_at=row["created_at"],
    )


async def list_reviews_for_candidate(
    session: AsyncSession, *, candidate_id: str
) -> list[CandidateReviewHistoryItem]:
    """Every review record of ONE LLM Discovery candidate. SELECT only.

    Two statements, neither of them per-record and neither of them bounded by a
    LIMIT: the channel check, then ALL the records for that candidate.

    Raises CandidateReviewCandidateNotFound for an unknown candidate_id — which
    is a different fact from "this candidate has not been reviewed yet", and the
    two must never look alike. Raises CandidateReviewWrongDiscoveryType when the
    candidate exists on another discovery channel: a literature candidate is not
    reviewable through the LLM review contract, so its history is not readable
    through it either. A known, correctly-routed candidate with no records yet
    returns an empty list.

    The caller is responsible for mapping these onto HTTP; this module imports
    no web framework, so a read failure is not silently reported as an empty
    history.
    """
    scope = (
        await session.execute(_SCOPE_SQL, {"candidate_id": candidate_id})
    ).mappings().one_or_none()
    if scope is None:
        raise CandidateReviewCandidateNotFound(candidate_id)
    if scope["discovery_type"] != LLM_DISCOVERY:
        raise CandidateReviewWrongDiscoveryType(candidate_id, scope["discovery_type"])

    # ``.all()`` — never ``.first()`` / ``.one_or_none()`` / ``[0]`` / ``[-1]``.
    # Every record is returned; nothing is collapsed to the newest decision.
    rows = (
        await session.execute(_HISTORY_SQL, {"candidate_pk": scope["candidate_pk"]})
    ).mappings().all()
    return [_row_to_item(row) for row in rows]
