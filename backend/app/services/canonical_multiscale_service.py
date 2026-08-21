"""Unified multiscale view of one canonical region (BR4).

`get_multiscale_region_view(region_id)` answers: what is this region, where does
it sit in the partonomy, which finer-level regions hang below it (meso /
subregion / fine buckets), and which cell types / molecular entities align to
it (cross-layer registries — never part of the brain hierarchy).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical_region import CanonicalBrainRegion
from app.models.multiscale import (
    CellTypeRegistry,
    MolecularEntityRegistry,
    RegionCellAlignment,
    RegionMolecularAlignment,
)
from app.services import canonical_region_service as crs


async def get_multiscale_region_view(
    session: AsyncSession, region_id: uuid.UUID
) -> dict[str, Any] | None:
    """None when the region does not exist; otherwise the full multiscale view."""
    region = await crs.get_canonical_region(session, region_id)
    if region is None:
        return None

    parents = await crs.get_ancestors(session, region_id)  # nearest-first
    children = await crs.get_children(session, region_id)
    descendants = await crs.get_descendants(session, region_id)

    # Bucket descendants by main-scale level (depth-preserving order)
    depth_by_id = {item["id"]: item["depth"] for item in descendants}
    desc_ids = list(depth_by_id.keys())
    regions_by_level: dict[str, list[CanonicalBrainRegion]] = {
        "meso": [],
        "subregion": [],
        "fine": [],
    }
    if desc_ids:
        rows = list(
            (
                await session.execute(
                    select(CanonicalBrainRegion).where(CanonicalBrainRegion.id.in_(desc_ids))
                )
            ).scalars().all()
        )
        for row in rows:
            bucket = regions_by_level.get(row.granularity_level)
            if bucket is not None:
                bucket.append(row)
        for bucket in regions_by_level.values():
            bucket.sort(key=lambda r: (depth_by_id.get(r.id, 99), r.region_code))

    cell_type_rows = (
        await session.execute(
            select(CellTypeRegistry, RegionCellAlignment)
            .join(RegionCellAlignment, RegionCellAlignment.cell_type_id == CellTypeRegistry.id)
            .where(RegionCellAlignment.region_id == region_id)
            .order_by(RegionCellAlignment.confidence.desc().nulls_last(), CellTypeRegistry.cell_type_code)
        )
    ).all()
    cell_types = [
        {
            "cell_type_id": ct.id,
            "cell_type_code": ct.cell_type_code,
            "canonical_name_en": ct.canonical_name_en,
            "canonical_name_cn": ct.canonical_name_cn,
            "taxonomy_source": ct.taxonomy_source,
            "mapping_type": alignment.mapping_type,
            "confidence": float(alignment.confidence) if alignment.confidence is not None else None,
        }
        for ct, alignment in cell_type_rows
    ]

    molecule_rows = (
        await session.execute(
            select(MolecularEntityRegistry, RegionMolecularAlignment)
            .join(
                RegionMolecularAlignment,
                RegionMolecularAlignment.molecular_entity_id == MolecularEntityRegistry.id,
            )
            .where(RegionMolecularAlignment.region_id == region_id)
            .order_by(
                RegionMolecularAlignment.confidence.desc().nulls_last(),
                MolecularEntityRegistry.entity_code,
            )
        )
    ).all()
    molecules = [
        {
            "molecular_entity_id": entity.id,
            "entity_code": entity.entity_code,
            "canonical_name_en": entity.canonical_name_en,
            "entity_type": entity.entity_type,
            "evidence_type": alignment.evidence_type,
            "confidence": float(alignment.confidence) if alignment.confidence is not None else None,
            "source": alignment.source,
        }
        for entity, alignment in molecule_rows
    ]

    return {
        "region": region,
        "parents": parents,
        "children": children,
        "meso_regions": regions_by_level["meso"],
        "subregions": regions_by_level["subregion"],
        "fine_regions": regions_by_level["fine"],
        "cell_types": cell_types,
        "molecules": molecules,
    }
