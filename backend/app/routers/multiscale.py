"""BR3 multiscale API: atlas resource layer + cell/molecular alignment layers."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.multiscale import (
    AtlasRegionBatchImport,
    AtlasRegionImportResult,
    AtlasRegionMappingCreate,
    AtlasRegionMappingRead,
    AtlasRegionRead,
    AtlasSourceRead,
    CellTypeCreate,
    CellTypeRead,
    MolecularEntityCreate,
    MolecularEntityRead,
    RegionCellAlignmentCreate,
    RegionCellAlignmentRead,
    RegionMolecularAlignmentCreate,
    RegionMolecularAlignmentRead,
)
from app.services import multiscale_service as ms

router = APIRouter()


def _http(exc: ms.MultiscaleError) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": "MULTISCALE_ERROR", "message": str(exc)})


# ──── sources registry ──────────────────────────────────────────────────────


@router.get("/sources", response_model=list[AtlasSourceRead])
async def list_sources(session: AsyncSession = Depends(get_db)):
    return await ms.list_atlas_sources(session)


# ──── atlas region resources ────────────────────────────────────────────────


@router.post("/atlas-regions/import", response_model=AtlasRegionImportResult)
async def import_atlas_regions(body: AtlasRegionBatchImport, session: AsyncSession = Depends(get_db)):
    try:
        result = await ms.import_atlas_regions(session, body)
    except ms.MultiscaleError as exc:
        raise _http(exc)
    await session.commit()
    return result


@router.get("/atlas-regions", response_model=list[AtlasRegionRead])
async def list_atlas_regions(
    atlas_name: str | None = Query(default=None),
    species: str | None = Query(default=None),
    limit: int = Query(default=500, le=5000),
    session: AsyncSession = Depends(get_db),
):
    return await ms.list_atlas_regions(session, atlas_name=atlas_name, species=species, limit=limit)


# ──── atlas -> canonical mappings ───────────────────────────────────────────


@router.post("/atlas-mappings", response_model=AtlasRegionMappingRead)
async def create_atlas_mapping(body: AtlasRegionMappingCreate, session: AsyncSession = Depends(get_db)):
    try:
        row = await ms.create_atlas_mapping(session, body)
    except ms.MultiscaleError as exc:
        raise _http(exc)
    await session.commit()
    await session.refresh(row)
    return row


@router.post("/atlas-mappings/{mapping_id}/supersede", response_model=AtlasRegionMappingRead)
async def supersede_atlas_mapping(mapping_id: uuid.UUID, session: AsyncSession = Depends(get_db)):
    try:
        row = await ms.supersede_atlas_mapping(session, mapping_id)
    except ms.MultiscaleError as exc:
        raise _http(exc)
    await session.commit()
    return row


@router.get("/atlas-mappings", response_model=list[AtlasRegionMappingRead])
async def list_atlas_mappings(
    canonical_region_id: uuid.UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    return await ms.list_atlas_mappings(session, canonical_region_id=canonical_region_id)


# ──── cell types (NOT BrainRegions) ─────────────────────────────────────────


@router.post("/cell-types", response_model=CellTypeRead)
async def create_cell_type(body: CellTypeCreate, session: AsyncSession = Depends(get_db)):
    try:
        row = await ms.create_cell_type(session, body)
    except ms.MultiscaleError as exc:
        raise _http(exc)
    await session.commit()
    await session.refresh(row)
    return row


@router.get("/cell-types", response_model=list[CellTypeRead])
async def list_cell_types(session: AsyncSession = Depends(get_db)):
    return await ms.list_cell_types(session)


@router.post("/region-cell-alignments", response_model=RegionCellAlignmentRead)
async def create_region_cell_alignment(
    body: RegionCellAlignmentCreate, session: AsyncSession = Depends(get_db)
):
    try:
        row = await ms.create_region_cell_alignment(session, body)
    except ms.MultiscaleError as exc:
        raise _http(exc)
    await session.commit()
    await session.refresh(row)
    return row


@router.get("/region-cell-alignments", response_model=list[RegionCellAlignmentRead])
async def list_region_cell_alignments(
    region_id: uuid.UUID | None = Query(default=None),
    cell_type_id: uuid.UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    return await ms.list_region_cell_alignments(
        session, region_id=region_id, cell_type_id=cell_type_id
    )


# ──── molecular entities (NOT BrainRegions) ─────────────────────────────────


@router.post("/molecular-entities", response_model=MolecularEntityRead)
async def create_molecular_entity(body: MolecularEntityCreate, session: AsyncSession = Depends(get_db)):
    try:
        row = await ms.create_molecular_entity(session, body)
    except ms.MultiscaleError as exc:
        raise _http(exc)
    await session.commit()
    await session.refresh(row)
    return row


@router.get("/molecular-entities", response_model=list[MolecularEntityRead])
async def list_molecular_entities(session: AsyncSession = Depends(get_db)):
    return await ms.list_molecular_entities(session)


@router.post("/region-molecular-alignments", response_model=RegionMolecularAlignmentRead)
async def create_region_molecular_alignment(
    body: RegionMolecularAlignmentCreate, session: AsyncSession = Depends(get_db)
):
    try:
        row = await ms.create_region_molecular_alignment(session, body)
    except ms.MultiscaleError as exc:
        raise _http(exc)
    await session.commit()
    await session.refresh(row)
    return row


@router.get("/region-molecular-alignments", response_model=list[RegionMolecularAlignmentRead])
async def list_region_molecular_alignments(
    region_id: uuid.UUID | None = Query(default=None),
    molecular_entity_id: uuid.UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    return await ms.list_region_molecular_alignments(
        session, region_id=region_id, molecular_entity_id=molecular_entity_id
    )
