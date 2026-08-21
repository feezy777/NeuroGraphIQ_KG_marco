"""HCP MMP1.0 (Glasser 2016) importer (idempotent) — 360 parcels → atlas layer → canonical.

Governance chain (same as brainnetome_importer):
    glasser360NodeNames.txt (official MMP1.0 label file)
        → atlas_region_resources (360 rows, label = atlas-native id)
            → atlas_region_mappings (exact, same_species)
                → canonical_brain_regions (meso, laterality='left'|'right')
                    → part_of ng:br:cerebrum

Run from backend/:
    .venv/Scripts/python.exe scripts/hcp_mmp_importer.py

Data notes (honest):
- The official MMP1.0 name file contains ONLY area names (no gyrus/parent info),
  so every parcel attaches to cerebrum — the limitation is recorded in edge
  provenance, not silently inferred.
- Names contain hyphens (9-46d, OP2-3, i6-8) — normalized to underscores in
  region_code (ng:br:mmp_9_46d_l); hemisphere lives in laterality (no
  left_*/right_* entity names).
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

NAMES_PATH = BACKEND_DIR / "data" / "atlases" / "hcp_mmp" / "glasser360NodeNames.txt"
ATLAS_NAME = "HCP MMP1.0 (Glasser 2016)"
ATLAS_VERSION = "MMP1.0 360-parcel"
RESOURCE_CODE = "hcp_mmp_glasser"
PARENT_CODE = "ng:br:cerebrum"

_HEMI_PREFIX = {"Right": ("R", "right"), "Left": ("L", "left")}


def parse_names(path: Path) -> list[dict]:
    """One label per line: `Right_V1` -> {label, hemi, side, name, code_suffix}."""
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        prefix, _, name = line.partition("_")
        hemi = _HEMI_PREFIX.get(prefix)
        if hemi is None or not name:
            print(f"  !! unparsable label: {line!r} — skipped")
            continue
        normalized = name.lower().replace("-", "_")
        rows.append(
            {
                "label": line,
                "name": name,
                "hemi": hemi[0],
                "laterality": hemi[1],
                "code_suffix": f"{normalized}_{hemi[1][0]}",
            }
        )
    return rows


async def _region_by_code(session, code: str) -> CanonicalBrainRegion | None:
    return (
        await session.execute(
            select(CanonicalBrainRegion).where(CanonicalBrainRegion.region_code == code)
        )
    ).scalar_one_or_none()


async def _atlas_row(session, label: str) -> AtlasRegionResource | None:
    return (
        await session.execute(
            select(AtlasRegionResource).where(
                AtlasRegionResource.atlas_name == ATLAS_NAME,
                AtlasRegionResource.atlas_version == ATLAS_VERSION,
                AtlasRegionResource.atlas_region_id == label,
            )
        )
    ).scalar_one_or_none()


async def import_mmp(session) -> dict[str, int]:
    resource = (
        await session.execute(
            select(AtlasResource).where(AtlasResource.resource_code == RESOURCE_CODE)
        )
    ).scalar_one_or_none()
    if resource is None:
        raise RuntimeError(f"atlas resource not registered: {RESOURCE_CODE}")

    parent = await _region_by_code(session, PARENT_CODE)
    if parent is None:
        raise RuntimeError(f"parent canonical region missing: {PARENT_CODE}")

    stats = {"atlas_rows": 0, "canonical_created": 0, "mappings": 0, "edges": 0, "skipped": 0}
    for row in parse_names(NAMES_PATH):
        code = f"ng:br:mmp_{row['code_suffix']}"

        atlas_row = await _atlas_row(session, row["label"])
        if atlas_row is None:
            atlas_row = AtlasRegionResource(
                atlas_resource_id=resource.id,
                atlas_name=ATLAS_NAME,
                atlas_version=ATLAS_VERSION,
                atlas_region_id=row["label"],
                region_name=row["name"],
                region_acronym=row["name"],
                parent_region_id=None,
                species="human",
                hemisphere=row["hemi"],
                source_file=str(NAMES_PATH.relative_to(BACKEND_DIR)),
                provenance={"importer": "hcp_mmp_importer"},
            )
            session.add(atlas_row)
            await session.flush()
            stats["atlas_rows"] += 1

        region = await _region_by_code(session, code)
        if region is None:
            payload = CanonicalRegionCreate(
                region_code=code,
                canonical_name_en=f"{row['name']} (HCP-MMP1.0, {row['laterality']})",
                canonical_name_cn=None,
                species="human",
                granularity_domain="brain_region_anatomical",
                granularity_level="meso",
                hemisphere_policy="lateralized",
                laterality=row["laterality"],
                status="active",
                created_by="import:hcp_mmp",
                description=(
                    f"HCP MMP1.0 cortical parcel {row['name']} "
                    f"({row['laterality']} hemisphere)."
                ),
                confidence=1.0,
                source_summary={
                    "source": "HCP MMP1.0 (Glasser et al. 2016)",
                    "source_file": "data/atlases/hcp_mmp/glasser360NodeNames.txt",
                    "atlas_native_label": row["label"],
                    "note": "official name file carries no gyrus/parent info — parent is cerebrum",
                },
                external_mappings={
                    "hcp_mmp1": row["label"],
                    "glasser_2016": row["name"],
                },
            )
            region = await crs.create_canonical_region(session, payload)
            stats["canonical_created"] += 1

        existing_mapping = (
            await session.execute(
                select(AtlasRegionMapping).where(
                    AtlasRegionMapping.atlas_region_id == atlas_row.id,
                    AtlasRegionMapping.canonical_region_id == region.id,
                    AtlasRegionMapping.status == "active",
                )
            )
        ).scalar_one_or_none()
        if existing_mapping is None:
            session.add(
                AtlasRegionMapping(
                    atlas_region_id=atlas_row.id,
                    canonical_region_id=region.id,
                    mapping_type="exact",
                    confidence=1.0,
                    species_relation="same_species",
                    match_details={"atlas_native_label": row["label"]},
                    provenance={"importer": "hcp_mmp_importer"},
                    created_by="import:hcp_mmp",
                )
            )
            stats["mappings"] += 1

        edge = (
            await session.execute(
                select(CanonicalRegionHierarchy).where(
                    CanonicalRegionHierarchy.child_region_id == region.id,
                    CanonicalRegionHierarchy.parent_region_id == parent.id,
                    CanonicalRegionHierarchy.predicate == "part_of",
                )
            )
        ).scalar_one_or_none()
        if edge is None:
            await crs.add_part_of_edge(
                session,
                CanonicalRegionHierarchyCreate(
                    child_region_id=region.id,
                    parent_region_id=parent.id,
                    source="import:hcp_mmp",
                    confidence=1.0,
                    provenance_json={
                        "importer": "hcp_mmp_importer",
                        "note": "parent is cerebrum: official name file has no gyrus/parent info",
                    },
                    created_by="import:hcp_mmp",
                ),
            )
            stats["edges"] += 1

    return stats


async def main() -> None:
    if not NAMES_PATH.exists():
        print(f"ERROR: MMP name file missing: {NAMES_PATH}")
        raise SystemExit(1)
    async with AsyncSessionLocal() as session:
        stats = await import_mmp(session)
        await session.commit()
    print("HCP-MMP1.0 IMPORT RESULT")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print("OK")


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))
