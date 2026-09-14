"""Phase 1 Knowledge Production - read-only HTTP surface.

Endpoints (both strictly read-only):

    GET /api/knowledge-production/brain-regions
    GET /api/knowledge-production/brain-regions/{identifier}

Design boundary for Phase 1:
  * Discovery is NOT implemented - there is no Discovery Run table and none is
    created here. Nothing in this module returns a discovery status.
  * No Candidate / Mirror / Final dependency. Reads only Gate7B formal tables.
  * No LLM Discovery / Literature Discovery endpoint exists (they are disabled
    placeholders in the UI and must not be faked by an endpoint).

The router performs HTTP concerns only; query construction lives in
``app.services.knowledge_production_brain_region_service``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.knowledge_production import (
    BrainRegionSeedDetail,
    BrainRegionSeedListResponse,
    BrainRegionSummary,
    GranularityLevel,
)
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
