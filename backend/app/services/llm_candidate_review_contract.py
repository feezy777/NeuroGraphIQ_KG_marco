"""Phase P0-3A — the Candidate Review DOMAIN CONTRACT.

ONE pure module, and the single code-level authority for the Candidate Review
status vocabulary, the review decision vocabulary, which transitions are legal,
what each status means (and does NOT mean), and the next workflow gate.

It is NOT an implementation. No database access, no SQLAlchemy session, no
FastAPI, no persistence, no write helper: review DECISIONS are not stored by this
phase, and nothing here may be extended into a writer without a separate governed
phase. A contract that could also write would be two things at once, and the
second one would eventually be called by accident.

Owner rulings this module encodes (frozen):
  A. The candidate status vocabulary is gate7b_016's, unchanged.
  B. ``accepted`` means "eligible to ENTER Resolution / Canonicalization" — NOT
     canonicalized, validated, proven, approved, active, promoted, or Final KG.
  C. LLM Discovery and Literature Discovery stay independent channels.
  D. Evidence is NOT required to mark a candidate ``accepted``; it IS required
     before an LLM-derived proposal becomes active / Final KG knowledge.
     ``derivation_type = inferred`` does not substitute for evidence.
  E. MERGE / CREATE / SAME_AS / mapping-to-existing-entity are Resolution
     outcomes, NOT values of ``discovery_candidates.status``.

THE ONE SPELLING COLLISION, stated once and tested (ruling: rename neither side
in this phase):

    discovery_candidates.status == "proposed"  -> a PROPOSAL; no canonical entity
    kg_entities.record_status   == "proposed"  -> a CANONICAL row, not yet accepted

Same word, different field, different row, different authority, different
meaning. This module therefore defines NO canonical-side vocabulary at all.

Resolution is a FUTURE layer. An accepted candidate may later be mapped to an
existing canonical entity, become a new proposed canonical entity, be merged with
another candidate, have its resolution deferred, or be rejected during
resolution. None of that is implemented, and none of it is a candidate status.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final


class CandidateStatus(str, Enum):
    """The review status of a PROPOSAL. Mirrors ck_dc_status (gate7b_016).

    Member names are namespaced by this class, so no bare ``PROPOSED`` can exist
    in the module namespace and be mistaken for the canonical column's value.
    """

    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DEFERRED = "deferred"


CANDIDATE_STATUSES: Final[tuple[str, ...]] = tuple(s.value for s in CandidateStatus)


class CandidateReviewDecision(str, Enum):
    """A human review ACTION, not a status. One decision maps to one status.

    Deliberately absent: REOPEN. No review vocabulary in this repository has a
    reopen action (existing ones are approve/reject/needs_revision/
    request_changes/mark_uncertain) and Rollback is only a Final-KG concept. So
    re-opening a deferral is a TRANSITION (``deferred -> proposed``), not an
    invented fourth decision.
    """

    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    DEFER = "DEFER"


CANDIDATE_REVIEW_DECISIONS: Final[tuple[str, ...]] = tuple(
    d.value for d in CandidateReviewDecision
)

#: Workflow gate names. Explicitly NOT database values: a gate says what happens
#: NEXT, and writing one into ``discovery_candidates.status`` is a category error.
CANDIDATE_GATE_CANDIDATE_REVIEW: Final[str] = "CANDIDATE_REVIEW"
CANDIDATE_GATE_RESOLUTION_CANONICALIZATION: Final[str] = "RESOLUTION_CANONICALIZATION"
CANDIDATE_GATE_TERMINAL: Final[str] = "TERMINAL"

CANDIDATE_GATES: Final[tuple[str, ...]] = (
    CANDIDATE_GATE_CANDIDATE_REVIEW,
    CANDIDATE_GATE_RESOLUTION_CANONICALIZATION,
    CANDIDATE_GATE_TERMINAL,
)

#: The transition graph. A status absent as a KEY is terminal for Candidate
#: Review. ``rejected`` is terminal in this phase: reopening it would need an
#: explicit governed workflow, and none exists.
_ALLOWED_CANDIDATE_TRANSITIONS: Final[dict[CandidateStatus, frozenset[CandidateStatus]]] = {
    CandidateStatus.PROPOSED: frozenset(
        {CandidateStatus.ACCEPTED, CandidateStatus.REJECTED, CandidateStatus.DEFERRED}
    ),
    CandidateStatus.DEFERRED: frozenset({CandidateStatus.PROPOSED}),
    CandidateStatus.ACCEPTED: frozenset(),
    CandidateStatus.REJECTED: frozenset(),
}

_DECISION_STATUS: Final[dict[CandidateReviewDecision, CandidateStatus]] = {
    CandidateReviewDecision.ACCEPT: CandidateStatus.ACCEPTED,
    CandidateReviewDecision.REJECT: CandidateStatus.REJECTED,
    CandidateReviewDecision.DEFER: CandidateStatus.DEFERRED,
}


@dataclass(frozen=True)
class CandidateStatusSemantics:
    """What a status means — and, explicitly, what it never means.

    The negative fields are the point: they turn "accepted does not mean
    canonical" into something a test asserts for EVERY status, so a future edit
    cannot quietly relax it.
    """

    status: CandidateStatus
    next_gate: str
    #: No further Candidate Review transition exists FROM this status.
    terminal_for_review: bool
    #: This status hands the proposal to the future Resolution layer.
    enters_resolution: bool
    #: Never true for a candidate status. Kept as fields so the claim is asserted.
    implies_canonical_knowledge: bool
    implies_validated: bool
    implies_evidence_backed: bool


_SEMANTICS: Final[dict[CandidateStatus, CandidateStatusSemantics]] = {
    CandidateStatus.PROPOSED: CandidateStatusSemantics(
        status=CandidateStatus.PROPOSED,
        next_gate=CANDIDATE_GATE_CANDIDATE_REVIEW,
        terminal_for_review=False,
        enters_resolution=False,
        implies_canonical_knowledge=False,
        implies_validated=False,
        implies_evidence_backed=False,
    ),
    CandidateStatus.ACCEPTED: CandidateStatusSemantics(
        status=CandidateStatus.ACCEPTED,
        next_gate=CANDIDATE_GATE_RESOLUTION_CANONICALIZATION,
        terminal_for_review=True,
        enters_resolution=True,
        implies_canonical_knowledge=False,
        implies_validated=False,
        implies_evidence_backed=False,
    ),
    CandidateStatus.REJECTED: CandidateStatusSemantics(
        status=CandidateStatus.REJECTED,
        next_gate=CANDIDATE_GATE_TERMINAL,
        terminal_for_review=True,
        enters_resolution=False,
        implies_canonical_knowledge=False,
        implies_validated=False,
        implies_evidence_backed=False,
    ),
    CandidateStatus.DEFERRED: CandidateStatusSemantics(
        status=CandidateStatus.DEFERRED,
        next_gate=CANDIDATE_GATE_CANDIDATE_REVIEW,
        terminal_for_review=False,
        enters_resolution=False,
        implies_canonical_knowledge=False,
        implies_validated=False,
        implies_evidence_backed=False,
    ),
}


def _as_status(value: CandidateStatus | str) -> CandidateStatus:
    """Coerce a stored string to a status, failing closed on vocabulary drift."""
    return value if isinstance(value, CandidateStatus) else CandidateStatus(value)


def review_decision_to_status(
    decision: CandidateReviewDecision | str,
) -> CandidateStatus:
    """The ONE status a review decision produces. Unknown decision -> ValueError."""
    return _DECISION_STATUS[
        decision if isinstance(decision, CandidateReviewDecision)
        else CandidateReviewDecision(decision)
    ]


def allowed_transitions_from(
    current: CandidateStatus | str,
) -> frozenset[CandidateStatus]:
    """Every status reachable from ``current`` by a Candidate Review transition."""
    return _ALLOWED_CANDIDATE_TRANSITIONS[_as_status(current)]


def can_transition_candidate_status(
    current: CandidateStatus | str, target: CandidateStatus | str
) -> bool:
    """May Candidate Review move a proposal from ``current`` to ``target``?

    Returns False — never raises — for an unknown endpoint, which is what makes
    the forbidden conflations testable: ``("accepted", "active")`` and
    ``("rejected", "promoted")`` are False because those words are not statuses
    of this machine at all. They do not even belong to it.
    """
    try:
        return _as_status(target) in _ALLOWED_CANDIDATE_TRANSITIONS[_as_status(current)]
    except ValueError:
        return False


def is_terminal_candidate_status(status: CandidateStatus | str) -> bool:
    """No further CANDIDATE REVIEW transition exists from this status.

    Narrower than "the workflow is over": ``accepted`` is terminal here and still
    hands off to Resolution — read ``next_candidate_gate`` for what happens next.
    """
    return semantics_for(status).terminal_for_review


def next_candidate_gate(status: CandidateStatus | str) -> str:
    """The workflow gate that follows this status. Fails closed on drift."""
    return semantics_for(status).next_gate


def semantics_for(status: CandidateStatus | str) -> CandidateStatusSemantics:
    """The frozen meaning of one status. Unknown status -> ValueError."""
    return _SEMANTICS[_as_status(status)]
