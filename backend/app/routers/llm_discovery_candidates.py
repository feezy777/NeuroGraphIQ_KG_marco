"""LLM Discovery candidate READ API — the HTTP surface of P0-2A.

Two GET endpoints, and nothing else:

    GET /api/knowledge-production/discovery-runs/{run_id}/llm-candidates
    GET /api/knowledge-production/brain-regions/{entity_id}/llm-candidates

Both are thin: the router validates nothing itself, resolves nothing itself and
sorts nothing itself. Every semantic decision — which run is an LLM run, whether
an id exists, what order the rows come back in — belongs to
``llm_candidate_read_service`` (P0-2A), which is the ONLY thing here that touches
the database. This module issues no SQL at all.

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
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import llm_candidate_read_service as read_service
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
