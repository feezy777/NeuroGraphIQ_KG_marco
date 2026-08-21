"""Winterburn 2013 hippocampal subfield importer (idempotent).

Governance chain:
    curated atlas labels (Winterburn et al. 2013 — see data note)
        → atlas_region_resources (6 labels × L/R)
            → atlas_region_mappings (exact, same_species; SRLM deliberately unmapped)
                → canonical_brain_regions (subregion; only the missing CA2 is created)
                    → part_of ng:br:hippocampal_formation

Run from backend/:
    .venv/Scripts/python.exe scripts/hippocampal_subregion_importer.py

Data note (honest): the Winterburn 2013 atlas (NeuroImage 74:254-265) has no
machine-readable public label file; the 6 per-hemisphere labels (CA1, CA2, CA3,
CA4/DG, subiculum, SRLM) are curated from the published atlas description.
Existing canonical anchors (ca1/ca3/dentate_gyrus/subiculum from BR3) are reused
— only ng:br:ca2 is created. SRLM is a stratum (not a neuronal subfield): its
atlas rows are imported but deliberately NOT mapped to any canonical region.
"""

from __future__ import annotations

import asyncio
import selectors
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.canonical_region import CanonicalBrainRegion, CanonicalRegionHierarchy
from app.models.multiscale import AtlasRegionMapping, AtlasRegionResource
from app.models.resource import AtlasResource
from app.schemas.canonical_region import CanonicalRegionCreate, CanonicalRegionHierarchyCreate
from app.services import canonical_region_service as crs

ATLAS_NAME = "Hippocampal Subfield Atlas"
ATLAS_VERSION = "Winterburn 2013"
RESOURCE_CODE = "hippocampal_subfield_winterburn"
PARENT_CODE = "ng:br:hippocampal_formation"

CITATION = "Winterburn et al., NeuroImage 74:254-265, 2013"

# label -> canonical region code (None = atlas row only, no canonical mapping)
SUBFIELD_LABELS: dict[str, str | None] = {
    "CA1": "ng:br:ca1",
    "CA2": "ng:br:ca2",
    "CA3": "ng:br:ca3",
    "CA4/DG": "ng:br:dentate_gyrus",
    "Subiculum": "ng:br:subiculum",
    "SRLM": None,  # stratum radiatum/lacunosum/moleculare — not a neuronal subfield
}

# code -> (name_en, name_cn, uberon_id) for anchors missing from BR3
NEW_ANCHORS: dict[str, tuple[str, str, str]] = {
    "ng:br:ca2": ("Field CA2", "CA2 区", "UBERON_0003883"),
}


async def _region_by_code(session, code: str) -> CanonicalBrainRegion | None:
    return (
        await session.execute(
            select(CanonicalBrainRegion).where(CanonicalBrainRegion.region_code == code)
        )
    ).scalar_one_or_none()


async def ensure_ca2(session) -> int:
    parent = await _region_by_code(session, PARENT_CODE)
    if parent is None:
        raise RuntimeError(f"parent canonical region missing: {PARENT_CODE}")
    created = 0
    for code, (name_en, name_cn, uberon) in NEW_ANCHORS.items():
        if await _region_by_code(session, code) is not None:
            continue
        region = await crs.create_canonical_region(
            session,
            CanonicalRegionCreate(
                region_code=code,
                canonical_name_en=name_en,
                canonical_name_cn=name_cn,
                species="human",
                granularity_domain="brain_region_anatomical",
                granularity_level="subregion",
                hemisphere_policy="bilateral",
                laterality="bilateral",
                status="active",
                created_by="import:winterburn",
                description=(
                    "Hippocampal subfield curated from the Winterburn 2013 atlas "
                    "(high-resolution 3T in vivo subfield labeling)."
                ),
                confidence=1.0,
                source_summary={"source": "Winterburn 2013 atlas", "citation": CITATION, "uberon": uberon},
                external_mappings={"uberon": f"http://purl.obolibrary.org/obo/{uberon}"},
            ),
        )
        await crs.add_part_of_edge(
            session,
            CanonicalRegionHierarchyCreate(
                child_region_id=region.id,
                parent_region_id=parent.id,
                source="import:winterburn",
                confidence=1.0,
                provenance_json={"importer": "hippocampal_subregion_importer", "citation": CITATION},
                created_by="import:winterburn",
            ),
        )
        created += 1
    return created


async def import_winterburn(session) -> dict[str, int]:
    resource = (
        await session.execute(
            select(AtlasResource).where(AtlasResource.resource_code == RESOURCE_CODE)
        )
    ).scalar_one_or_none()
    if resource is None:
        raise RuntimeError(f"atlas resource not registered: {RESOURCE_CODE}")

    stats = {"atlas_rows": 0, "mappings": 0, "unmapped": 0, "skipped": 0}
    for label, canonical_code in SUBFIELD_LABELS.items():
        for hemi in ("L", "R"):
            atlas_id = f"{label}_{hemi}"
            atlas_row = (
                await session.execute(
                    select(AtlasRegionResource).where(
                        AtlasRegionResource.atlas_name == ATLAS_NAME,
                        AtlasRegionResource.atlas_version == ATLAS_VERSION,
                        AtlasRegionResource.atlas_region_id == atlas_id,
                    )
                )
            ).scalar_one_or_none()
            if atlas_row is None:
                atlas_row = AtlasRegionResource(
                    atlas_resource_id=resource.id,
                    atlas_name=ATLAS_NAME,
                    atlas_version=ATLAS_VERSION,
                    atlas_region_id=atlas_id,
                    region_name=label,
                    region_acronym=label,
                    parent_region_id=None,
                    species="human",
                    hemisphere=hemi,
                    source_file=None,
                    provenance={
                        "importer": "hippocampal_subregion_importer",
                        "citation": CITATION,
                        "note": "curated label — no machine-readable public file for this atlas",
                    },
                )
                session.add(atlas_row)
                await session.flush()
                stats["atlas_rows"] += 1

            if canonical_code is None:
                stats["unmapped"] += 1
                continue
            canonical = await _region_by_code(session, canonical_code)
            if canonical is None:
                print(f"  !! canonical missing: {canonical_code} — skipped")
                stats["skipped"] += 1
                continue

            existing_mapping = (
                await session.execute(
                    select(AtlasRegionMapping).where(
                        AtlasRegionMapping.atlas_region_id == atlas_row.id,
                        AtlasRegionMapping.canonical_region_id == canonical.id,
                        AtlasRegionMapping.status == "active",
                    )
                )
            ).scalar_one_or_none()
            if existing_mapping is None:
                session.add(
                    AtlasRegionMapping(
                        atlas_region_id=atlas_row.id,
                        canonical_region_id=canonical.id,
                        mapping_type="exact",
                        confidence=1.0,
                        species_relation="same_species",
                        match_details={"atlas_native_label": atlas_id},
                        provenance={"importer": "hippocampal_subregion_importer", "citation": CITATION},
                        created_by="import:winterburn",
                    )
                )
                stats["mappings"] += 1
    return stats


async def main() -> None:
    async with AsyncSessionLocal() as session:
        ca2_created = await ensure_ca2(session)
        stats = await import_winterburn(session)
        await session.commit()
    print("WINTERBURN IMPORT RESULT")
    print(f"  canonical_created (CA2): {ca2_created}")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print("OK")


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))
