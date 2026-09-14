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

Design boundary:
  * Reads are read-only. The ONLY writes are the five lifecycle transitions
    above, and they exist solely to move a run through the frozen state graph
    (create / start / complete / fail / cancel).
  * A Discovery Run is workflow/provenance, NOT knowledge: nothing here returns
    or creates a circuit / connection / function / evidence / assertion.
  * No Candidate / Mirror / Final dependency. Touches only Gate7B formal tables
    plus the knowledge_discovery_runs management table.
  * Discovery EXECUTION does not exist: no LLM call, no literature search, and
    no endpoint triggers one. A created run stays QUEUED until a later
    execution layer advances it, so the UI buttons remain disabled.
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

from fastapi import APIRouter, Depends, HTTPException, Query
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
    GranularityLevel,
)
from app.services import knowledge_discovery_run_lifecycle_service as lifecycle
from app.services import knowledge_discovery_run_service as run_svc
from app.services import knowledge_production_brain_region_service as svc

router = APIRouter(prefix="/api/knowledge-production", tags=["Knowledge Production"])


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
        None, description="LLM_DISCOVERY | LITERATURE_DISCOVERY"
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
