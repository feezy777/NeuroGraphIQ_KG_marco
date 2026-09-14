"""Knowledge Production - read-only HTTP surface.

BrainRegion endpoints:

    GET /api/knowledge-production/brain-regions
    GET /api/knowledge-production/brain-regions/summary
    GET /api/knowledge-production/brain-regions/{identifier}

Discovery Run endpoints (Phase 2A — READ ONLY, no lifecycle):

    GET /api/knowledge-production/brain-regions/{entity_id}/discovery-runs
    GET /api/knowledge-production/discovery-runs/{run_id}

Design boundary:
  * Everything here is READ-ONLY. There is NO POST/PATCH/DELETE endpoint. Run
    lifecycle transitions (create / start / complete / fail / cancel) belong to
    Phase 2B and are deliberately absent.
  * A Discovery Run is workflow/provenance, NOT knowledge: nothing here returns
    a circuit / connection / function / evidence / assertion.
  * No Candidate / Mirror / Final dependency. Reads only Gate7B formal tables
    plus the knowledge_discovery_runs management table.
  * Discovery EXECUTION does not exist yet: no LLM call, no literature search,
    and no endpoint here triggers one. The UI buttons stay disabled.

The router performs HTTP concerns only; query construction lives in
``app.services.knowledge_production_brain_region_service`` and
``app.services.knowledge_discovery_run_service``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.knowledge_production import (
    BrainRegionSeedDetail,
    BrainRegionSeedListResponse,
    BrainRegionSummary,
    DiscoveryRunItem,
    DiscoveryRunListResponse,
    DiscoveryRunStatus,
    DiscoveryType,
    GranularityLevel,
)
from app.services import knowledge_discovery_run_service as run_svc
from app.services import knowledge_production_brain_region_service as svc

router = APIRouter(prefix="/api/knowledge-production", tags=["Knowledge Production"])


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
    try:
        uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Discovery Run '{run_id}' not found")

    run = await run_svc.get_discovery_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Discovery Run '{run_id}' not found")
    return run
