"""BR3 multiscale service: atlas resource layer + cell/molecular alignment layers.

Hard rule (BR3): atlas rows are NEVER promoted into canonical_brain_regions
by this layer — promotion to canonical happens only through the explicit
canonical-region API / seed scripts, and atlas_region_mappings is the
auditable link in between.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical_region import CanonicalBrainRegion
from app.models.multiscale import (
    AtlasRegionMapping,
    AtlasRegionResource,
    CellTypeRegistry,
    MolecularEntityRegistry,
    RegionCellAlignment,
    RegionMolecularAlignment,
)
from app.models.resource import AtlasResource
from app.schemas.multiscale import (
    AtlasRegionBatchImport,
    AtlasRegionMappingCreate,
    CellTypeCreate,
    MolecularEntityCreate,
    RegionCellAlignmentCreate,
    RegionMolecularAlignmentCreate,
)


class MultiscaleError(ValueError):
    """Domain error for multiscale layer operations."""


# ──── atlas region resources ────────────────────────────────────────────────


async def import_atlas_regions(
    session: AsyncSession, payload: AtlasRegionBatchImport
) -> dict[str, Any]:
    """Bulk-import raw atlas rows (idempotent on atlas-native identity)."""
    # one existence query per (atlas_name, atlas_version) group instead of N+1
    groups: dict[tuple[str, str], list[str]] = {}
    for row in payload.rows:
        groups.setdefault((row.atlas_name, row.atlas_version), []).append(row.atlas_region_id)
    existing_ids: set[tuple[str, str, str]] = set()
    for (name, version), ids in groups.items():
        found = (
            await session.execute(
                select(AtlasRegionResource.atlas_region_id).where(
                    AtlasRegionResource.atlas_name == name,
                    AtlasRegionResource.atlas_version == version,
                    AtlasRegionResource.atlas_region_id.in_(ids),
                )
            )
        ).scalars().all()
        existing_ids.update((name, version, str(i)) for i in found)

    inserted = 0
    skipped = 0
    seen: set[tuple[str, str, str]] = set(existing_ids)
    for row in payload.rows:
        key = (row.atlas_name, row.atlas_version, row.atlas_region_id)
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        session.add(
            AtlasRegionResource(
                atlas_name=row.atlas_name,
                atlas_version=row.atlas_version,
                atlas_region_id=row.atlas_region_id,
                region_name=row.region_name,
                region_acronym=row.region_acronym,
                parent_region_id=row.parent_region_id,
                species=row.species,
                hemisphere=row.hemisphere,
                source_file=payload.source_file or row.source_file,
                provenance={**row.provenance, "created_by": payload.created_by},
                status=row.status,
            )
        )
        inserted += 1
    await session.flush()
    return {"inserted": inserted, "skipped": skipped, "total": inserted + skipped}


async def list_atlas_regions(
    session: AsyncSession,
    *,
    atlas_name: str | None = None,
    species: str | None = None,
    limit: int = 500,
) -> list[AtlasRegionResource]:
    stmt = select(AtlasRegionResource).order_by(
        AtlasRegionResource.atlas_name, AtlasRegionResource.atlas_region_id
    )
    if atlas_name:
        stmt = stmt.where(AtlasRegionResource.atlas_name == atlas_name)
    if species:
        stmt = stmt.where(AtlasRegionResource.species == species)
    return list((await session.execute(stmt.limit(limit))).scalars().all())


async def get_atlas_region(session: AsyncSession, atlas_region_row_id: uuid.UUID) -> AtlasRegionResource | None:
    return await session.get(AtlasRegionResource, atlas_region_row_id)


# ──── atlas -> canonical mappings ───────────────────────────────────────────


async def create_atlas_mapping(
    session: AsyncSession, payload: AtlasRegionMappingCreate
) -> AtlasRegionMapping:
    atlas_row = await session.get(AtlasRegionResource, payload.atlas_region_id)
    if atlas_row is None:
        raise MultiscaleError("atlas region row not found")
    canonical = await session.get(CanonicalBrainRegion, payload.canonical_region_id)
    if canonical is None:
        raise MultiscaleError("canonical region not found")
    if (
        atlas_row.species not in (None, "unknown")
        and canonical.species not in (None, "unknown")
        and atlas_row.species != canonical.species
        and payload.species_relation != "homology"
    ):
        raise MultiscaleError(
            f"cross-species mapping ({atlas_row.species} -> {canonical.species}) requires "
            "species_relation='homology'"
        )
    conflicts = list(
        (
            await session.execute(
                select(AtlasRegionMapping).where(
                    AtlasRegionMapping.atlas_region_id == payload.atlas_region_id,
                    AtlasRegionMapping.status == "active",
                    AtlasRegionMapping.canonical_region_id != payload.canonical_region_id,
                )
            )
        ).scalars().all()
    )
    if conflicts:
        raise MultiscaleError(
            f"atlas region already has {len(conflicts)} active mapping(s) to other canonical regions; "
            "supersede them first (ATLAS_MAPPING_CONFLICT guard)"
        )
    mapping = AtlasRegionMapping(
        atlas_region_id=payload.atlas_region_id,
        canonical_region_id=payload.canonical_region_id,
        mapping_type=payload.mapping_type,
        confidence=payload.confidence,
        species_relation=payload.species_relation,
        match_details=payload.match_details,
        provenance=payload.provenance,
        created_by=payload.created_by,
    )
    session.add(mapping)
    await session.flush()
    return mapping


async def supersede_atlas_mapping(session: AsyncSession, mapping_id: uuid.UUID) -> AtlasRegionMapping:
    mapping = await session.get(AtlasRegionMapping, mapping_id)
    if mapping is None:
        raise MultiscaleError("atlas mapping not found")
    mapping.status = "superseded"
    await session.flush()
    return mapping


async def list_atlas_mappings(
    session: AsyncSession, *, canonical_region_id: uuid.UUID | None = None
) -> list[AtlasRegionMapping]:
    stmt = select(AtlasRegionMapping).order_by(AtlasRegionMapping.created_at)
    if canonical_region_id:
        stmt = stmt.where(AtlasRegionMapping.canonical_region_id == canonical_region_id)
    return list((await session.execute(stmt)).scalars().all())


# ──── sources registry ──────────────────────────────────────────────────────


async def list_atlas_sources(session: AsyncSession) -> list[AtlasResource]:
    return list(
        (
            await session.execute(
                select(AtlasResource)
                .where(AtlasResource.deleted_at.is_(None))
                .order_by(AtlasResource.source_atlas)
            )
        ).scalars().all()
    )


# ──── cell types (independent registry — NOT BrainRegions) ─────────────────


async def create_cell_type(session: AsyncSession, payload: CellTypeCreate) -> CellTypeRegistry:
    existing = (
        await session.execute(
            select(CellTypeRegistry).where(CellTypeRegistry.cell_type_code == payload.cell_type_code)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise MultiscaleError(f"cell_type_code already exists: {payload.cell_type_code}")
    row = CellTypeRegistry(**payload.model_dump())
    session.add(row)
    await session.flush()
    return row


async def list_cell_types(session: AsyncSession) -> list[CellTypeRegistry]:
    return list(
        (await session.execute(select(CellTypeRegistry).order_by(CellTypeRegistry.cell_type_code))).scalars().all()
    )


async def create_region_cell_alignment(
    session: AsyncSession, payload: RegionCellAlignmentCreate
) -> RegionCellAlignment:
    if await session.get(CanonicalBrainRegion, payload.region_id) is None:
        raise MultiscaleError("canonical region not found")
    if await session.get(CellTypeRegistry, payload.cell_type_id) is None:
        raise MultiscaleError("cell type not found")
    dup = (
        await session.execute(
            select(RegionCellAlignment).where(
                RegionCellAlignment.region_id == payload.region_id,
                RegionCellAlignment.cell_type_id == payload.cell_type_id,
                RegionCellAlignment.mapping_type == payload.mapping_type,
            )
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise MultiscaleError("region-cell alignment already exists")
    row = RegionCellAlignment(**payload.model_dump())
    session.add(row)
    await session.flush()
    return row


async def list_region_cell_alignments(
    session: AsyncSession,
    *,
    region_id: uuid.UUID | None = None,
    cell_type_id: uuid.UUID | None = None,
) -> list[RegionCellAlignment]:
    stmt = select(RegionCellAlignment).order_by(RegionCellAlignment.created_at)
    if region_id:
        stmt = stmt.where(RegionCellAlignment.region_id == region_id)
    if cell_type_id:
        stmt = stmt.where(RegionCellAlignment.cell_type_id == cell_type_id)
    return list((await session.execute(stmt)).scalars().all())


# ──── molecular entities (independent registry — NOT BrainRegions) ──────────


async def create_molecular_entity(
    session: AsyncSession, payload: MolecularEntityCreate
) -> MolecularEntityRegistry:
    existing = (
        await session.execute(
            select(MolecularEntityRegistry).where(
                MolecularEntityRegistry.entity_code == payload.entity_code
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise MultiscaleError(f"entity_code already exists: {payload.entity_code}")
    row = MolecularEntityRegistry(**payload.model_dump())
    session.add(row)
    await session.flush()
    return row


async def list_molecular_entities(session: AsyncSession) -> list[MolecularEntityRegistry]:
    return list(
        (
            await session.execute(
                select(MolecularEntityRegistry).order_by(MolecularEntityRegistry.entity_code)
            )
        ).scalars().all()
    )


async def create_region_molecular_alignment(
    session: AsyncSession, payload: RegionMolecularAlignmentCreate
) -> RegionMolecularAlignment:
    if await session.get(CanonicalBrainRegion, payload.region_id) is None:
        raise MultiscaleError("canonical region not found")
    entity = await session.get(MolecularEntityRegistry, payload.molecular_entity_id)
    if entity is None:
        raise MultiscaleError("molecular entity not found")
    dup = (
        await session.execute(
            select(RegionMolecularAlignment).where(
                RegionMolecularAlignment.region_id == payload.region_id,
                RegionMolecularAlignment.molecular_entity_id == payload.molecular_entity_id,
                RegionMolecularAlignment.evidence_type == payload.evidence_type,
            )
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise MultiscaleError("region-molecular alignment already exists")
    row = RegionMolecularAlignment(
        region_id=payload.region_id,
        molecular_entity_id=payload.molecular_entity_id,
        entity_type=entity.entity_type,
        evidence_type=payload.evidence_type,
        confidence=payload.confidence,
        source=payload.source,
        provenance=payload.provenance,
    )
    session.add(row)
    await session.flush()
    return row


async def list_region_molecular_alignments(
    session: AsyncSession,
    *,
    region_id: uuid.UUID | None = None,
    molecular_entity_id: uuid.UUID | None = None,
) -> list[RegionMolecularAlignment]:
    stmt = select(RegionMolecularAlignment).order_by(RegionMolecularAlignment.created_at)
    if region_id:
        stmt = stmt.where(RegionMolecularAlignment.region_id == region_id)
    if molecular_entity_id:
        stmt = stmt.where(RegionMolecularAlignment.molecular_entity_id == molecular_entity_id)
    return list((await session.execute(stmt)).scalars().all())
