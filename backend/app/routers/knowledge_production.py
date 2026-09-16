"""Knowledge Production - read-only HTTP surface.

BrainRegion endpoints:

    GET /api/knowledge-production/brain-regions
    GET /api/knowledge-production/brain-regions/summary
    GET /api/knowledge-production/brain-regions/{identifier}

Discovery Run endpoints:

    GET  /api/knowledge-production/brain-regions/{entity_id}/discovery-runs
    GET  /api/knowledge-production/discovery-runs/{run_id}
    POST /api/knowledge-production/brain-regions/{entity_id}/discovery-runs
    POST /api/knowledge-production/discovery-runs/{run_id}/start
    POST /api/knowledge-production/discovery-runs/{run_id}/complete
    POST /api/knowledge-production/discovery-runs/{run_id}/fail
    POST /api/knowledge-production/discovery-runs/{run_id}/cancel
    POST /api/knowledge-production/brain-regions/{entity_id}/llm-discovery/execute

Literature production endpoints (read-only, Phase 3E.2B):

    GET /api/knowledge-production/brain-regions/{entity_id}/literature-runs
    GET /api/knowledge-production/discovery-runs/{run_id}/publications
    GET /api/knowledge-production/publications/{entity_id}

Design boundary:
  * Reads are read-only. The ONLY writes are the lifecycle transitions, and
    they exist solely to move a run through the frozen state graph
    (create / start / complete / fail / cancel).
  * A Discovery Run is workflow/provenance, NOT knowledge: nothing here returns
    or creates a circuit / connection / function / evidence / assertion.
  * No Candidate / Mirror / Final dependency. Touches only Gate7B formal tables
    plus the knowledge_discovery_runs management table.
  * LLM Discovery EXECUTION exists from Phase 3B, on its own endpoint. It drives
    ONE run synchronously and returns typed candidates that live in the response
    only — no candidate is persisted, and no literature search exists. The
    generic Run Create API is unchanged, so the UI buttons stay disabled.
  * Errors: 404 missing, 409 lifecycle conflict / duplicate active run,
    422 malformed or scientifically invalid input. No SQL text is exposed.

The router performs HTTP concerns only; query construction and the state
machine live in ``app.services.knowledge_production_brain_region_service``,
``app.services.knowledge_discovery_run_service`` (read) and
``app.services.knowledge_discovery_run_lifecycle_service`` (write).
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.llm_discovery_views import InvalidDiscoveryView
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.knowledge_production import (
    BrainRegionSeedDetail,
    BrainRegionSeedListResponse,
    BrainRegionSummary,
    DiscoveryRunCompleteRequest,
    DiscoveryRunCreateRequest,
    DiscoveryRunFailRequest,
    DiscoveryRunItem,
    DiscoveryRunListResponse,
    DiscoveryRunStatus,
    DiscoveryType,
    DISCOVERY_TYPES,
    GranularityLevel,
    LiteraturePublicationListResponse,
    LiteratureRunListResponse,
    PublicationDetailResponse,
)
from app.schemas.llm_discovery_execution import LlmDiscoveryExecutionResult
from app.schemas.llm_discovery_views import LlmDiscoveryViewExecuteRequest
from app.services import knowledge_discovery_run_lifecycle_service as lifecycle
from app.services import knowledge_discovery_run_service as run_svc
from app.services import knowledge_production_brain_region_service as svc
from app.services import knowledge_production_literature_service as literature
from app.services import llm_discovery_continuation_service as continuation
from app.services import llm_discovery_execution_service as execution

router = APIRouter(prefix="/api/knowledge-production", tags=["Knowledge Production"])

#: The OpenAPI description for the discovery_type filter. DERIVED from the
#: vocabulary rather than typed out, because a hand-written copy is exactly what
#: went stale: it still advertised two values after the vocabulary reached four.
#: Documentation only -- validation is DiscoveryType's job.
_DISCOVERY_TYPE_DESCRIPTION = " | ".join(DISCOVERY_TYPES)


def _error_detail(code: str, message: str, **extra: Any) -> dict[str, Any]:
    """Structured error body, matching the app-wide {code, message} shape.

    Never carries SQL text, constraint names or other DB internals.
    """
    return {"code": code, "message": message, **extra}


def _require_uuid(run_id: str) -> None:
    """A malformed run_id cannot identify any run -> 404, and never reaches SQL."""
    try:
        uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail=_error_detail("RUN_NOT_FOUND", f"Discovery Run '{run_id}' not found"),
        ) from None


@contextmanager
def _mapped_lifecycle_errors():
    """Translate lifecycle domain errors onto the HTTP error contract (§19).

    404 = missing, 409 = lifecycle conflict, 422 = scientifically invalid
    outcome. Anything else propagates untouched (a genuine failure must stay a
    500 rather than be disguised as a client error).
    """
    try:
        yield
    except lifecycle.DiscoveryRunNotFound as exc:
        raise HTTPException(404, detail=_error_detail("NOT_FOUND", str(exc))) from None
    except lifecycle.DiscoveryRunOutcomeNotAllowed as exc:
        raise HTTPException(
            422,
            detail=_error_detail(
                "OUTCOME_NOT_ALLOWED",
                str(exc),
                discovery_type=exc.discovery_type,
                allowed_outcomes=list(exc.allowed),
            ),
        ) from None
    except lifecycle.DiscoveryRunConflict as exc:
        extra: dict[str, Any] = {}
        if exc.active_run_id is not None:
            # The conflicting run's PUBLIC id — never the internal seed PK.
            extra["active_run_id"] = exc.active_run_id
        raise HTTPException(
            409, detail=_error_detail(exc.code, exc.message, **extra)
        ) from None


@router.get("/brain-regions", response_model=BrainRegionSeedListResponse)
async def list_brain_regions(
    granularity_level: GranularityLevel | None = Query(
        None, description="Gate7B granularity vocabulary (G1_MACRO..G4_MICROSTRUCTURAL_FINE)"
    ),
    source_atlas: str | None = Query(None, description="Atlas name substring"),
    search: str | None = Query(None, description="Substring match on name_en / name_zh / entity_id"),
    limit: int = Query(50, ge=1, le=svc._MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> BrainRegionSeedListResponse:
    """Server-side paginated BrainRegion seed list from the Gate7B authority."""
    return await svc.list_seed_regions(
        db,
        granularity_level=granularity_level,
        source_atlas=source_atlas,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/brain-regions/summary", response_model=BrainRegionSummary)
async def summarize_brain_regions(db: AsyncSession = Depends(get_db)) -> BrainRegionSummary:
    """Counts for the Production Index summary row (one aggregate query).

    Declared BEFORE /brain-regions/{identifier} so 'summary' is not captured
    as an identifier.
    """
    return await svc.summarize_seed_regions(db)


@router.get("/brain-regions/{identifier}", response_model=BrainRegionSeedDetail)
async def get_brain_region(
    identifier: str, db: AsyncSession = Depends(get_db)
) -> BrainRegionSeedDetail:
    """One BrainRegion by Gate7B identity (entity_id, e.g. NGIQ-BR-00000001)."""
    detail = await svc.get_seed_region(db, identifier)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"BrainRegion '{identifier}' not found")
    return detail


# ---------------------------------------------------------------------------
# Phase 2A — Discovery Runs (read-only)
# ---------------------------------------------------------------------------


@router.get(
    "/brain-regions/{entity_id}/discovery-runs",
    response_model=DiscoveryRunListResponse,
)
async def list_brain_region_discovery_runs(
    entity_id: str,
    discovery_type: DiscoveryType | None = Query(
        None, description=_DISCOVERY_TYPE_DESCRIPTION
    ),
    status: DiscoveryRunStatus | None = Query(
        None, description="QUEUED | RUNNING | COMPLETED | FAILED | CANCELLED"
    ),
    limit: int = Query(50, ge=1, le=run_svc._MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> DiscoveryRunListResponse:
    """Discovery Runs recorded for one BrainRegion, newest first.

    404 when the BrainRegion itself does not exist: 'no such region' and 'no runs
    for this region' are different facts and must not be conflated.
    """
    runs = await run_svc.list_discovery_runs_for_region(
        db,
        entity_id=entity_id,
        discovery_type=discovery_type,
        status=status,
        limit=limit,
        offset=offset,
    )
    if runs is None:
        raise HTTPException(status_code=404, detail=f"BrainRegion '{entity_id}' not found")
    return runs


@router.get("/discovery-runs/{run_id}", response_model=DiscoveryRunItem)
async def get_discovery_run(
    run_id: str, db: AsyncSession = Depends(get_db)
) -> DiscoveryRunItem:
    """One Discovery Run by its public run_id (UUID).

    A malformed run_id is reported as 404 (not 422 or 500): it cannot identify
    any run, so 'not found' is the honest answer. Validating here also keeps the
    UUID column comparison from raising a database DataError.
    """
    _require_uuid(run_id)

    run = await run_svc.get_discovery_run(db, run_id)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail=_error_detail("RUN_NOT_FOUND", f"Discovery Run '{run_id}' not found"),
        )
    return run


# ---------------------------------------------------------------------------
# Phase 2B — Discovery Run lifecycle (the only write surface)
# ---------------------------------------------------------------------------
# These endpoints move a run through the frozen state graph. They do NOT
# execute discovery: a created run stays QUEUED until a later execution layer
# advances it. No endpoint here calls an LLM or a literature API.


@router.post(
    "/brain-regions/{entity_id}/discovery-runs",
    response_model=DiscoveryRunItem,
    status_code=201,
)
async def create_discovery_run(
    entity_id: str,
    payload: DiscoveryRunCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> DiscoveryRunItem:
    """Create a QUEUED Discovery Run for one BrainRegion.

    The client may supply ONLY the route. Execution provenance (provider,
    model, prompt, query strategy), run config and audit identity are rejected
    by the request schema — they are written by the layer that produces them.

    409 when an active run already exists for this seed + route.
    """
    with _mapped_lifecycle_errors():
        return await lifecycle.create_discovery_run(
            db, entity_id=entity_id, discovery_type=payload.discovery_type
        )


@router.post("/discovery-runs/{run_id}/start", response_model=DiscoveryRunItem)
async def start_discovery_run(
    run_id: str, db: AsyncSession = Depends(get_db)
) -> DiscoveryRunItem:
    """QUEUED -> RUNNING. Idempotent while already RUNNING."""
    _require_uuid(run_id)
    with _mapped_lifecycle_errors():
        return await lifecycle.start_discovery_run(db, run_id)


@router.post("/discovery-runs/{run_id}/complete", response_model=DiscoveryRunItem)
async def complete_discovery_run(
    run_id: str,
    payload: DiscoveryRunCompleteRequest,
    db: AsyncSession = Depends(get_db),
) -> DiscoveryRunItem:
    """RUNNING -> COMPLETED with a scientific outcome.

    422 when the outcome is not valid for the run's route
    (LLM_DISCOVERY may not report NO_EVIDENCE_FOUND).
    """
    _require_uuid(run_id)
    with _mapped_lifecycle_errors():
        return await lifecycle.complete_discovery_run(db, run_id, payload.outcome)


@router.post("/discovery-runs/{run_id}/fail", response_model=DiscoveryRunItem)
async def fail_discovery_run(
    run_id: str,
    payload: DiscoveryRunFailRequest,
    db: AsyncSession = Depends(get_db),
) -> DiscoveryRunItem:
    """QUEUED | RUNNING -> FAILED with a required explanation."""
    _require_uuid(run_id)
    with _mapped_lifecycle_errors():
        return await lifecycle.fail_discovery_run(
            db,
            run_id,
            error_code=payload.error_code,
            error_message=payload.error_message,
        )


@router.post("/discovery-runs/{run_id}/cancel", response_model=DiscoveryRunItem)
async def cancel_discovery_run(
    run_id: str, db: AsyncSession = Depends(get_db)
) -> DiscoveryRunItem:
    """QUEUED | RUNNING -> CANCELLED. Idempotent while already CANCELLED."""
    _require_uuid(run_id)
    with _mapped_lifecycle_errors():
        return await lifecycle.cancel_discovery_run(db, run_id)


# ---------------------------------------------------------------------------
# Phase 3B — LLM Discovery execution
# ---------------------------------------------------------------------------
# A separate path on purpose: the generic Run Create API above stays untouched
# (§8), and this endpoint is the TRUSTED caller that owns the run it creates.
# Its body is OPTIONAL and carries exactly one field, `discovery_view`: the
# client names the question, and nothing else. Provider / model / prompt /
# prompt-version provenance stay server-owned and cannot be fabricated from the
# outside — the request schema forbids unknown keys outright, and omitting the
# body entirely is the legacy single-pass run, unchanged.


@contextmanager
def _mapped_execution_errors():
    """Translate execution failures (502/422) without masking lifecycle errors.

    A provider or parser failure means the upstream model did not produce a
    usable answer: the run is already FAILED by the time this fires, and the
    body names the failure code so the client can distinguish a bad model
    response from a bad request.

    An unknown Discovery View is neither. It is a bad request, and it is
    answered as one — 422 with its own code — before any run exists.
    """
    try:
        yield
    except InvalidDiscoveryView as exc:
        raise HTTPException(
            422, detail=_error_detail(exc.code, str(exc), discovery_view=exc.value)
        ) from None
    except continuation.ContinuationRunNotFound as exc:
        # The named source run does not exist — a lookup failure, not a conflict.
        raise HTTPException(
            404, detail=_error_detail(exc.code, str(exc), run_id=exc.run_id)
        ) from None
    except continuation.ContinuationError as exc:
        # The source run EXISTS but cannot honestly be continued: another seed,
        # another route, another view, or not completed. 409 — the request is
        # well-formed and conflicts with the state of the run it names.
        raise HTTPException(409, detail=_error_detail(exc.code, str(exc))) from None
    except execution.LlmDiscoveryExecutionError as exc:
        extra: dict[str, Any] = {}
        if exc.run_id is not None:
            # The run's PUBLIC uuid — the client needs it to inspect the
            # failure, and it is not a database key.
            extra["run_id"] = exc.run_id
        raise HTTPException(
            502, detail=_error_detail(exc.code, exc.message, **extra)
        ) from None


@router.post(
    "/brain-regions/{entity_id}/llm-discovery/execute",
    response_model=LlmDiscoveryExecutionResult,
)
async def execute_brain_region_llm_discovery(
    entity_id: str,
    payload: LlmDiscoveryViewExecuteRequest | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
) -> LlmDiscoveryExecutionResult:
    """Run LLM Discovery synchronously for one BrainRegion seed.

    Creates and drives one LLM_DISCOVERY run through the lifecycle service,
    sends the frozen Phase 3A prompt to DeepSeek, and returns the typed
    candidates the Phase 3A parser accepted. Nothing is persisted except the
    run record: candidates exist for this response only.

    The optional body names the Discovery View — the scientific focus of this
    one run. The view is recorded on the run it creates, so a run permanently
    knows which question it asked. Omitting the body is the legacy single-pass
    run: no view instruction, no view recorded, byte-for-byte the previous
    behaviour. One view is one run.

    404 unknown BrainRegion, 409 an active run already exists, 422 the body
    names an unknown view or carries a field the server owns, 502 the model
    response could not be used (timeout / auth / provider / empty / unparseable).
    """
    with _mapped_lifecycle_errors(), _mapped_execution_errors():
        return await execution.execute_llm_discovery(
            db,
            entity_id=entity_id,
            discovery_view=payload.discovery_view if payload else None,
            # The server reads the already-discovered circuits itself; the
            # request carries only WHICH earlier run to continue.
            continuation_from_run_id=(
                payload.continuation_from_run_id if payload else None
            ),
        )


# ---------------------------------------------------------------------------
# Phase 3E.2B — Literature production (read-only)
# ---------------------------------------------------------------------------
# The read side of the literature model. Every route here is a GET and performs
# exactly one class of work: SELECT. No route executes a search, calls a
# provider, or writes a row -- a run with no results is an empty list, never a
# side effect.


@router.get(
    "/brain-regions/{entity_id}/literature-runs",
    response_model=LiteratureRunListResponse,
)
async def list_brain_region_literature_runs(
    entity_id: str,
    limit: int = Query(50, ge=1, le=run_svc._MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> LiteratureRunListResponse:
    """Literature Discovery Runs for one BrainRegion, newest first.

    Only the literature routes (LITERATURE_DISCOVERY / EVIDENCE_SEARCH /
    CITATION_CHAINING) are listed: LLM_DISCOVERY never searches literature.

    404 when the BrainRegion does not exist. A region that exists with no
    literature runs is 200 with an empty page -- "no such region" and "no runs
    yet" are different facts.
    """
    runs = await literature.list_literature_runs_for_region(
        db, entity_id=entity_id, limit=limit, offset=offset
    )
    if runs is None:
        raise HTTPException(status_code=404, detail=f"BrainRegion '{entity_id}' not found")
    return runs


@router.get(
    "/discovery-runs/{run_id}/publications",
    response_model=LiteraturePublicationListResponse,
)
async def list_run_publications(
    run_id: str, db: AsyncSession = Depends(get_db)
) -> LiteraturePublicationListResponse:
    """Publications reached by one run, each with all of its retrieval hits.

    A malformed run_id is 404, not 422 or 500: it cannot identify any run, and
    rejecting it here keeps it away from the uuid column comparison.

    404 unknown run; 200 + empty list for a run that reached nothing.
    """
    _require_uuid(run_id)

    found = await literature.list_publications_for_run(db, run_id=run_id)
    if found is None:
        raise HTTPException(
            status_code=404,
            detail=_error_detail("RUN_NOT_FOUND", f"Discovery Run '{run_id}' not found"),
        )
    return found


@router.get(
    "/publications/{entity_id}",
    response_model=PublicationDetailResponse,
)
async def get_publication(
    entity_id: str, db: AsyncSession = Depends(get_db)
) -> PublicationDetailResponse:
    """One Publication with all of its retrieval provenance, across every run.

    Retrieval provenance only: no Evidence, no KnowledgeAssertion, and no claim
    about what the paper supports.

    404 when no such publication exists.
    """
    publication = await literature.get_publication(db, entity_id=entity_id)
    if publication is None:
        raise HTTPException(
            status_code=404,
            detail=_error_detail("PUBLICATION_NOT_FOUND", f"Publication '{entity_id}' not found"),
        )
    return publication
