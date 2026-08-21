"""Canonical BrainRegion API (BR1: L0/L1 Macro Backbone).

Route order matters here: all static routes MUST be registered before the
dynamic ``/{region_id}`` group at the bottom, otherwise the UUID converter
swallows them (e.g. ``GET /integrity`` would 422 on UUID parse).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.canonical_region import (
    CanonicalRegionCreate,
    CanonicalRegionHierarchyCreate,
    CanonicalRegionHierarchyRead,
    CanonicalRegionMergeRequest,
    CanonicalRegionMergeResponse,
    CanonicalRegionMultiscaleView,
    CanonicalRegionRead,
    CanonicalRegionTreeItem,
    CandidateGroundingRequest,
    RegionCandidateRead,
    RegionCircuitRead,
    RegionConnectionRead,
    RegionFunctionRead,
)
from app.services import canonical_multiscale_service as cms
from app.services import canonical_region_service as crs

router = APIRouter()


def _http(exc: crs.CanonicalRegionError) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": "CANONICAL_REGION_ERROR", "message": str(exc)})


@router.post("", response_model=CanonicalRegionRead)
async def create_canonical_region(
    body: CanonicalRegionCreate,
    session: AsyncSession = Depends(get_db),
):
    try:
        region = await crs.create_canonical_region(session, body)
    except crs.CanonicalRegionError as exc:
        raise _http(exc)
    await session.commit()
    await session.refresh(region)
    return region


@router.get("", response_model=list[CanonicalRegionRead])
async def list_canonical_regions(
    granularity_level: str | None = Query(default=None),
    status: str | None = Query(default=None),
    species: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    return await crs.list_canonical_regions(
        session, granularity_level=granularity_level, status=status, species=species
    )


@router.post("/hierarchy", response_model=CanonicalRegionHierarchyRead)
async def add_part_of_edge(
    body: CanonicalRegionHierarchyCreate,
    session: AsyncSession = Depends(get_db),
):
    try:
        edge = await crs.add_part_of_edge(session, body)
    except crs.CanonicalRegionError as exc:
        raise _http(exc)
    await session.commit()
    await session.refresh(edge)
    return edge


@router.post("/ground-candidate")
async def ground_candidate(body: CandidateGroundingRequest, session: AsyncSession = Depends(get_db)):
    try:
        result = await crs.ground_candidate(
            session,
            candidate_id=body.candidate_id,
            canonical_region_id=body.canonical_region_id,
            match_type=body.match_type,
            confidence=body.confidence,
            match_details=body.match_details,
        )
    except crs.CanonicalRegionError as exc:
        raise _http(exc)
    await session.commit()
    return result


@router.post("/alignment-candidate")
async def create_alignment_candidate(
    body: CandidateGroundingRequest,
    session: AsyncSession = Depends(get_db),
):
    try:
        row = await crs.create_alignment_candidate(
            session,
            candidate_id=body.candidate_id,
            canonical_region_id=body.canonical_region_id,
            match_type=body.match_type,
            confidence=body.confidence,
            match_details=body.match_details,
        )
    except crs.CanonicalRegionError as exc:
        raise _http(exc)
    await session.commit()
    await session.refresh(row)
    return {
        "id": str(row.id),
        "target_type": row.target_type,
        "target_id": str(row.target_id),
        "external_iri": row.external_iri,
        "match_type": row.match_type,
        "status": row.status,
    }


@router.get("/resolve-candidate/{candidate_id}")
async def resolve_candidate(candidate_id: uuid.UUID, session: AsyncSession = Depends(get_db)):
    canonical = await crs.resolve_candidate_to_canonical(session, candidate_id)
    if canonical is None:
        return {"resolved": False}
    return {
        "resolved": True,
        "canonical_region_id": str(canonical.id),
        "region_code": canonical.region_code,
        "canonical_name_en": canonical.canonical_name_en,
    }


@router.get("/integrity")
async def canonical_region_integrity(session: AsyncSession = Depends(get_db)):
    return await crs.check_canonical_brain_region_integrity(session)


@router.post("/merge", response_model=CanonicalRegionMergeResponse)
async def merge_canonical_region(
    body: CanonicalRegionMergeRequest,
    session: AsyncSession = Depends(get_db),
):
    """Merge source region into target (BR3): identity preserved via replaced_by chain."""
    try:
        result = await crs.merge_canonical_region(
            session,
            source_region_id=body.source_region_id,
            target_region_id=body.target_region_id,
        )
    except crs.CanonicalRegionError as exc:
        raise _http(exc)
    await session.commit()
    return result


@router.get("/readiness/connection/{connection_id}")
async def connection_endpoint_readiness(connection_id: uuid.UUID, session: AsyncSession = Depends(get_db)):
    from app.models.mirror_kg import MirrorRegionConnection

    connection = await session.get(MirrorRegionConnection, connection_id)
    if connection is None:
        raise HTTPException(status_code=404, detail="connection not found")
    return await crs.resolve_connection_endpoints_to_canonical(session, connection)


@router.get("/readiness/circuit")
async def circuit_participant_readiness(session: AsyncSession = Depends(get_db)):
    return await crs.circuit_participant_readiness(session)


@router.get("/roots", response_model=list[CanonicalRegionRead])
async def list_region_roots(session: AsyncSession = Depends(get_db)):
    """Top-level regions (no active parent edge) for the tree explorer."""
    return await crs.get_roots(session)


# --------------------------------------------------------------------------- #
# Dynamic routes — keep LAST (see module docstring).
# --------------------------------------------------------------------------- #


@router.get("/{region_id}", response_model=CanonicalRegionRead)
async def get_canonical_region(region_id: uuid.UUID, session: AsyncSession = Depends(get_db)):
    region = await crs.get_canonical_region(session, region_id)
    if region is None:
        raise HTTPException(status_code=404, detail="canonical region not found")
    return region


@router.get("/{region_id}/ancestors", response_model=list[CanonicalRegionTreeItem])
async def get_ancestors(region_id: uuid.UUID, session: AsyncSession = Depends(get_db)):
    return await crs.get_ancestors(session, region_id)


@router.get("/{region_id}/descendants", response_model=list[CanonicalRegionTreeItem])
async def get_descendants(region_id: uuid.UUID, session: AsyncSession = Depends(get_db)):
    return await crs.get_descendants(session, region_id)


@router.get("/{region_id}/parent", response_model=CanonicalRegionRead | None)
async def get_parent(region_id: uuid.UUID, session: AsyncSession = Depends(get_db)):
    parents = await crs.get_parents(session, region_id)
    return parents[0] if parents else None


@router.get("/{region_id}/children", response_model=list[CanonicalRegionRead])
async def get_children(region_id: uuid.UUID, session: AsyncSession = Depends(get_db)):
    return await crs.get_children(session, region_id)


@router.get("/{region_id}/connections", response_model=list[RegionConnectionRead])
async def get_region_connections(region_id: uuid.UUID, session: AsyncSession = Depends(get_db)):
    return await crs.get_region_connections(session, region_id)


@router.get("/{region_id}/circuits", response_model=list[RegionCircuitRead])
async def get_region_circuits(region_id: uuid.UUID, session: AsyncSession = Depends(get_db)):
    return await crs.get_region_circuits(session, region_id)


@router.get("/{region_id}/functions", response_model=list[RegionFunctionRead])
async def get_region_functions(region_id: uuid.UUID, session: AsyncSession = Depends(get_db)):
    return await crs.get_region_functions(session, region_id)


@router.get("/{region_id}/candidates", response_model=list[RegionCandidateRead])
async def get_region_candidates(region_id: uuid.UUID, session: AsyncSession = Depends(get_db)):
    return await crs.get_region_candidates(session, region_id)


@router.get("/{region_id}/multiscale", response_model=CanonicalRegionMultiscaleView)
async def get_region_multiscale(region_id: uuid.UUID, session: AsyncSession = Depends(get_db)):
    """Unified multiscale view: partonomy + finer-level buckets + cross-layer
    cell types / molecular entities aligned to this region (BR4)."""
    view = await cms.get_multiscale_region_view(session, region_id)
    if view is None:
        raise HTTPException(status_code=404, detail="canonical region not found")
    return view
