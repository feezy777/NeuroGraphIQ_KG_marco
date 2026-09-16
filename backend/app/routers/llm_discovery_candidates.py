"""LLM Discovery candidate API — the HTTP surface of P0-2A (read) and P0-3C1 (review).

Three endpoints, and nothing else:

    GET  /api/knowledge-production/discovery-runs/{run_id}/llm-candidates
    GET  /api/knowledge-production/brain-regions/{entity_id}/llm-candidates
    POST /api/knowledge-production/candidates/{candidate_id}/review

All three are thin: the router validates nothing itself, resolves nothing itself,
sorts nothing itself and writes nothing itself. Every semantic decision — which
run is an LLM run, whether an id exists, what order rows come back in, whether a
decision is legal, what gate follows — belongs to the service layer, which is
the ONLY thing here that touches the database. This module issues no SQL at all.

The review route delegates to ``llm_candidate_review_persistence_service``
(P0-3B), which owns the row lock, the atomic review-record INSERT plus status
UPDATE, and the commit/rollback. The transition vocabulary lives in the P0-3A
contract; this layer merely maps its typed errors onto status codes.

Why a separate router file rather than adding routes to
``knowledge_production``: that module is a PARKED, uncommitted workstream, and
appending to it would make two independent phases land in one diff. The two
routers share the ``/api/knowledge-production`` prefix and coexist; the paths
below are nested exactly like the existing ones (``discovery-runs/{run_id}/
publications`` is their literature counterpart).

Naming: the sub-resource is ``llm-candidates``, not ``candidates``. A bare
"candidate" is already heavily overloaded in this repository (the legacy
Candidate DB, its ``candidate_*`` tables and its ``/api/candidates`` routes), and
these rows are something else entirely — LLM PROPOSALS, not parsing candidates
and not canonical knowledge.

Errors: 404 an id that does not exist (run or BrainRegion), 409 a run that
exists on a different discovery route. A scope that exists but holds no
candidates is 200 with an empty list — "nothing proposed yet" is a fact about
the scope, not a missing resource, and it must never be reported as 404.

No secrets, no raw model response, no reasoning content, no prompt and no
provider payload are reachable from the DTO, so none can leave through here.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import llm_candidate_read_service as read_service
from app.services import llm_candidate_review_persistence_service as review_service
from app.services.llm_candidate_read_service import DiscoveryCandidateReadItem

router = APIRouter(prefix="/api/knowledge-production", tags=["Knowledge Production"])


class LlmCandidateListResponse(BaseModel):
    """A page of candidates. Same envelope as every other list in this family.

    ``items`` carries the P0-2A DTO unchanged — a second schema with its own
    copy of the field semantics is exactly how a read contract drifts from what
    was persisted. ``total`` is the count of THIS page (the service returns the
    whole scope; there is no pagination in this phase).
    """

    items: list[DiscoveryCandidateReadItem]
    total: int


class CandidateReviewRequest(BaseModel):
    """One Candidate Review decision to submit.

    ``decision`` is a plain ``str`` rather than a Literal on purpose: the three
    decisions are a VOCABULARY owned by the P0-3A contract, and a Literal here
    would be a second copy that could drift from it. An unknown decision is
    rejected by the service and mapped to 422 below.

    ``reviewer`` is REQUIRED and caller-supplied. There is no authentication
    layer in this project yet, so the identity cannot be derived from a
    principal — see the route docstring. It is never inferred from hostname, OS
    user, git config or the environment; a review that cannot name its reviewer
    is not an audit record.
    """

    decision: str
    reviewer: str
    reviewer_note: str | None = None


class CandidateReviewResponse(BaseModel):
    """The outcome of one review decision. Public fields only.

    ``next_gate`` is carried straight through from the P0-3B service, which
    derives it from the P0-3A contract. The router holds no gate mapping and
    hard-codes no transition: whatever the contract says is what the client sees.

    Internal keys (``candidate_pk`` / ``review_pk`` / ``discovery_run_pk``) are
    deliberately absent — the public API is id-based.
    """

    candidate_id: str
    review_id: str
    decision: str
    from_status: str
    to_status: str
    reviewer: str
    reviewer_note: str | None = None
    created_at: datetime
    next_gate: str


def _error_detail(code: str, message: str, **extra: Any) -> dict[str, Any]:
    """Structured error body, matching the app-wide {code, message} shape.

    Defined locally rather than imported from the neighbouring Knowledge
    Production router: that module is a parked workstream, and a committed file
    must not depend on an uncommitted one.
    """
    return {"code": code, "message": message, **extra}


@contextmanager
def _mapped_read_errors():
    """Translate P0-2A's typed read errors onto HTTP (the only place that mapping lives).

    The service deliberately never imports FastAPI, so this is where "not an LLM
    run" becomes a status code. 409 rather than 404 for the wrong-route case: the
    run EXISTS, and telling a client "no such run" would be false in a way it
    might act on.
    """
    try:
        yield
    except read_service.DiscoveryCandidateRunNotFound as exc:
        raise HTTPException(
            404, detail=_error_detail("RUN_NOT_FOUND", str(exc))
        ) from None
    except read_service.DiscoveryCandidateRunNotLlm as exc:
        raise HTTPException(
            409,
            detail=_error_detail(
                "NOT_AN_LLM_RUN", str(exc), discovery_type=exc.discovery_type
            ),
        ) from None
    except read_service.DiscoveryCandidateSeedNotFound as exc:
        raise HTTPException(
            404, detail=_error_detail("BRAIN_REGION_NOT_FOUND", str(exc))
        ) from None


@contextmanager
def _mapped_review_errors():
    """Translate P0-3B's typed review errors onto HTTP (the only place that mapping lives).

    The split is deliberate:

    * 404 — the candidate does not exist.
    * 409 — the request is well-formed but CONFLICTS with the candidate's
      current state: it belongs to another discovery channel, or it has already
      been decided. A concurrent reviewer losing the race lands here too, which
      is why it must never surface as a 500.
    * 422 — the request itself is unusable (blank reviewer, unknown decision).

    Messages come from the service and carry no SQL, constraint name or stack
    fragment. An unexpected error is NOT caught here: it propagates to the
    application's normal 500 handling rather than being swallowed.
    """
    try:
        yield
    except review_service.CandidateReviewCandidateNotFound as exc:
        raise HTTPException(
            404, detail=_error_detail("CANDIDATE_NOT_FOUND", str(exc))
        ) from None
    except review_service.CandidateReviewWrongDiscoveryType as exc:
        raise HTTPException(
            409,
            detail=_error_detail(
                "NOT_AN_LLM_CANDIDATE", str(exc), discovery_type=exc.discovery_type
            ),
        ) from None
    except review_service.InvalidCandidateReviewTransition as exc:
        raise HTTPException(
            409,
            detail=_error_detail(
                "INVALID_REVIEW_TRANSITION",
                str(exc),
                from_status=exc.from_status,
                decision=exc.decision,
            ),
        ) from None
    except review_service.CandidateReviewInvalidReviewer as exc:
        raise HTTPException(
            422, detail=_error_detail("INVALID_REVIEWER", str(exc))
        ) from None
    except review_service.CandidateReviewInvalidDecision as exc:
        raise HTTPException(
            422, detail=_error_detail("INVALID_DECISION", str(exc))
        ) from None


@router.get(
    "/discovery-runs/{run_id}/llm-candidates",
    response_model=LlmCandidateListResponse,
)
async def list_run_llm_candidates(
    run_id: str, db: AsyncSession = Depends(get_db)
) -> LlmCandidateListResponse:
    """The candidates one LLM Discovery run proposed, in the service's order.

    The public run uuid is the only identifier accepted; a malformed one is
    reported by the service as "not found" rather than validated again here, so
    there is exactly one place that decides what an unidentifiable run means.

    404 unknown run · 409 the run is not an LLM_DISCOVERY run · 200 + [] for a
    known run that proposed nothing.
    """
    with _mapped_read_errors():
        items = await read_service.list_candidates_for_run(db, run_id=run_id)
    # No sort, no filter, no re-shaping: the order the service chose IS the
    # order the client sees.
    return LlmCandidateListResponse(items=items, total=len(items))


@router.get(
    "/brain-regions/{entity_id}/llm-candidates",
    response_model=LlmCandidateListResponse,
)
async def list_brain_region_llm_candidates(
    entity_id: str, db: AsyncSession = Depends(get_db)
) -> LlmCandidateListResponse:
    """The candidates every LLM Discovery run of one BrainRegion seed proposed.

    Spans runs, newest run first, exactly as the service ordered them.

    404 unknown BrainRegion · 200 + [] for a known region with no LLM
    candidates. Literature runs are excluded by the service, so a
    LITERATURE_DISCOVERY run under the same seed contributes nothing here.
    """
    with _mapped_read_errors():
        items = await read_service.list_candidates_for_seed(db, entity_id=entity_id)
    return LlmCandidateListResponse(items=items, total=len(items))


@router.post(
    "/candidates/{candidate_id}/review",
    response_model=CandidateReviewResponse,
)
async def review_llm_candidate(
    candidate_id: str,
    payload: CandidateReviewRequest,
    db: AsyncSession = Depends(get_db),
) -> CandidateReviewResponse:
    """Submit ONE Candidate Review decision about one LLM Discovery candidate.

    One request, one review operation, one service transaction. The endpoint
    writes nothing itself: it calls ``persist_candidate_review``, which owns the
    row lock, the atomic review-record INSERT + status UPDATE, and the
    commit/rollback. Nothing else is done in this session before that call, so
    there is no foreign write for its transaction to drag along.

    A candidate may be reviewed ONCE. A second decision — any decision, from any
    of the three settled statuses — is a 409 conflict and appends no record and
    changes no status; the first decision stands. Re-opening a deferred
    candidate is deliberately NOT implemented (no governed operation exists).

    AUTH: this project has no authentication layer yet, so the reviewer identity
    CANNOT be derived from a principal. ``reviewer`` is therefore a required
    request field, taken at face value and recorded verbatim as the audit
    identity. It is never inferred from the host, the OS user, git config or the
    environment. When authentication arrives, this field should be replaced by
    the authenticated principal rather than merely accepted alongside it.

    Errors: 404 unknown candidate · 409 wrong discovery channel or already
    decided · 422 blank reviewer or unknown decision.
    """
    with _mapped_review_errors():
        result = await review_service.persist_candidate_review(
            db,
            candidate_id=candidate_id,
            decision=payload.decision,
            reviewer=payload.reviewer,
            reviewer_note=payload.reviewer_note,
        )
    # Straight pass-through: the fields a client sees are exactly the fields the
    # service produced. next_gate in particular is the contract's answer, not
    # anything this layer decided.
    return CandidateReviewResponse(
        candidate_id=result.candidate_id,
        review_id=result.review_id,
        decision=result.decision,
        from_status=result.from_status,
        to_status=result.to_status,
        reviewer=result.reviewer,
        reviewer_note=result.reviewer_note,
        created_at=result.created_at,
        next_gate=result.next_gate,
    )
