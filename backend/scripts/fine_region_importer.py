"""Fine (cytoarchitectonic) region importer — Julich-Brain ready + curated anchors.

Two paths (both idempotent):

1. Bulk import (only when a real Julich file is present): reads the first
   matching file under data/atlases/julich/ (JSON list or TSV/CSV with columns
   julich_id, name, hemisphere, parent_name) and runs the full governance chain:
   file → atlas_region_resources → atlas_region_mappings → canonical (fine)
   → part_of parent. NEVER overwrites existing canonical regions (per spec:
   "不要覆盖已有区域").

2. Curated anchors (always): classical Brodmann areas are textbook-certain
   cytoarchitectonic regions of the Julich-Brain lineage. They are created as
   fine-level canonical anchors WITHOUT atlas rows (no Julich-Brain 3.1 data is
   reachable from this environment — honest limitation, no fabricated rows).

Run from backend/:
    .venv/Scripts/python.exe scripts/fine_region_importer.py
"""

from __future__ import annotations

import asyncio
import csv
import json
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

ATLAS_NAME = "Julich-Brain Atlas"
ATLAS_VERSION = "siibra cytoarchitectonic maps"
RESOURCE_CODE = "julich_brain_siibra"
DATA_DIR = BACKEND_DIR / "data" / "atlases" / "julich"

CITATION = "Amunts & Zilles, Science 348:1421-1422, 2015 (Julich-Brain atlas of the human cortex)"

# Curated classical Brodmann areas: (code, name_en, name_cn, parent_code)
# Parent chosen 1:1 where the area lies inside a single clinical region;
# ng:br:cerebrum where it spans several (recorded honestly in edge provenance).
CURATED_BRODMANN: list[tuple[str, str, str, str]] = [
    ("ng:br:ba4", "Area 4 (primary motor cortex)", "4 区（初级运动皮层）", "ng:br:precentral"),
    ("ng:br:ba3a", "Area 3a (proprioceptive somatosensory)", "3a 区（本体感觉皮层）", "ng:br:postcentral"),
    ("ng:br:ba3b", "Area 3b (primary somatosensory cortex)", "3b 区（初级躯体感觉皮层）", "ng:br:postcentral"),
    ("ng:br:ba1", "Area 1 (cutaneous somatosensory)", "1 区（皮肤感觉皮层）", "ng:br:postcentral"),
    ("ng:br:ba2", "Area 2 (joint somatosensory)", "2 区（关节感觉皮层）", "ng:br:postcentral"),
    ("ng:br:ba17", "Area 17 (primary visual cortex)", "17 区（初级视觉皮层）", "ng:br:pericalcarine"),
    ("ng:br:ba22", "Area 22 (auditory association cortex)", "22 区（听觉联络皮层）", "ng:br:superior_temporal"),
    ("ng:br:ba40", "Area 40 (supramarginal gyrus)", "40 区（缘上回）", "ng:br:supramarginal"),
    ("ng:br:ba39", "Area 39 (angular region)", "39 区（角回区）", "ng:br:inferior_parietal"),
    ("ng:br:ba7", "Area 7 (superior parietal association)", "7 区（顶上联合皮层）", "ng:br:precuneus"),
    ("ng:br:ba44", "Area 44 (Broca region, opercular)", "44 区（布罗卡区盖部）", "ng:br:pars_opercularis"),
    ("ng:br:ba45", "Area 45 (Broca region, triangular)", "45 区（布罗卡区三角部）", "ng:br:pars_triangularis"),
    ("ng:br:ba6", "Area 6 (premotor cortex)", "6 区（前运动皮层）", "ng:br:cerebrum"),
    ("ng:br:ba24", "Area 24 (anterior cingulate)", "24 区（前扣带回）", "ng:br:cerebrum"),
    ("ng:br:ba32", "Area 32 (dorsal anterior cingulate)", "32 区（背侧前扣带回）", "ng:br:cerebrum"),
]


async def _region_by_code(session, code: str) -> CanonicalBrainRegion | None:
    return (
        await session.execute(
            select(CanonicalBrainRegion).where(CanonicalBrainRegion.region_code == code)
        )
    ).scalar_one_or_none()


async def _edge_exists(session, child_id, parent_id) -> bool:
    return (
        await session.execute(
            select(CanonicalRegionHierarchy).where(
                CanonicalRegionHierarchy.child_region_id == child_id,
                CanonicalRegionHierarchy.parent_region_id == parent_id,
                CanonicalRegionHierarchy.predicate == "part_of",
            )
        )
    ).scalar_one_or_none() is not None


async def import_curated_brodmann(session) -> dict[str, int]:
    """Curated fine-level anchors (no atlas rows — see module docstring)."""
    stats = {"canonical_created": 0, "edges": 0, "skipped": 0}
    for code, name_en, name_cn, parent_code in CURATED_BRODMANN:
        parent = await _region_by_code(session, parent_code)
        if parent is None:
            print(f"  !! parent missing: {parent_code} (skipping {code})")
            stats["skipped"] += 1
            continue
        region = await _region_by_code(session, code)
        if region is None:
            region = await crs.create_canonical_region(
                session,
                CanonicalRegionCreate(
                    region_code=code,
                    canonical_name_en=name_en,
                    canonical_name_cn=name_cn,
                    species="human",
                    granularity_domain="brain_region_anatomical",
                    granularity_level="fine",
                    hemisphere_policy="bilateral",
                    laterality="bilateral",
                    status="active",
                    created_by="curated:fine",
                    description=(
                        f"Classical Brodmann cytoarchitectonic {code.split(':')[-1]} "
                        f"({CITATION})."
                    ),
                    confidence=1.0,
                    source_summary={
                        "source": "curated classical cytoarchitectonics (Brodmann 1909 lineage)",
                        "citation": CITATION,
                        "note": "Julich-Brain 3.1 bulk data unreachable in this environment — curated anchor, no atlas row",
                    },
                    external_mappings={"brodmann_1909": code.split(":")[-1].upper()},
                ),
            )
            stats["canonical_created"] += 1
        if not await _edge_exists(session, region.id, parent.id):
            await crs.add_part_of_edge(
                session,
                CanonicalRegionHierarchyCreate(
                    child_region_id=region.id,
                    parent_region_id=parent.id,
                    source="curated:fine",
                    confidence=1.0,
                    provenance_json={
                        "importer": "fine_region_importer",
                        "citation": CITATION,
                        "note": (
                            "parent is cerebrum: area spans several clinical regions"
                            if parent_code == "ng:br:cerebrum"
                            else "1:1 clinical parent"
                        ),
                    },
                    created_by="curated:fine",
                ),
            )
            stats["edges"] += 1
    return stats


async def import_julich_file(session) -> dict[str, int] | None:
    """Bulk path: only runs when a Julich data file actually exists."""
    files = sorted(DATA_DIR.glob("*.json")) + sorted(DATA_DIR.glob("*.tsv")) + sorted(DATA_DIR.glob("*.csv"))
    if not files:
        return None
    path = files[0]
    resource = (
        await session.execute(
            select(AtlasResource).where(AtlasResource.resource_code == RESOURCE_CODE)
        )
    ).scalar_one_or_none()
    if resource is None:
        raise RuntimeError(f"atlas resource not registered: {RESOURCE_CODE}")

    if path.suffix == ".json":
        rows = json.loads(path.read_text(encoding="utf-8"))
    else:
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t" if path.suffix == ".tsv" else ","))

    stats = {"atlas_rows": 0, "canonical_created": 0, "mappings": 0, "edges": 0, "skipped": 0}
    for row in rows:
        julich_id = str(row["julich_id"])
        name = str(row["name"])
        hemi_code = str(row.get("hemisphere") or "bilateral")
        hemi = {"left": "L", "right": "R"}.get(hemi_code, "bilateral")
        laterality = {"L": "left", "R": "right"}.get(hemi, "bilateral")
        parent_code = str(row.get("parent_name") or "").strip() or "ng:br:cerebrum"
        parent = await _region_by_code(session, parent_code)
        if parent is None:
            print(f"  !! parent missing: {parent_code} (skipping julich {julich_id})")
            stats["skipped"] += 1
            continue

        atlas_row = (
            await session.execute(
                select(AtlasRegionResource).where(
                    AtlasRegionResource.atlas_name == ATLAS_NAME,
                    AtlasRegionResource.atlas_version == ATLAS_VERSION,
                    AtlasRegionResource.atlas_region_id == julich_id,
                )
            )
        ).scalar_one_or_none()
        if atlas_row is None:
            atlas_row = AtlasRegionResource(
                atlas_resource_id=resource.id,
                atlas_name=ATLAS_NAME,
                atlas_version=ATLAS_VERSION,
                atlas_region_id=julich_id,
                region_name=name,
                parent_region_id=None,
                species="human",
                hemisphere=hemi,
                source_file=str(path.relative_to(BACKEND_DIR)),
                provenance={"importer": "fine_region_importer"},
            )
            session.add(atlas_row)
            await session.flush()
            stats["atlas_rows"] += 1

        code = f"ng:br:julich_{julich_id.lower().replace('-', '_')}"
        region = await _region_by_code(session, code)
        if region is None:  # NEVER overwrite existing regions
            region = await crs.create_canonical_region(
                session,
                CanonicalRegionCreate(
                    region_code=code,
                    canonical_name_en=f"{name} (Julich-Brain)",
                    canonical_name_cn=None,
                    species="human",
                    granularity_domain="brain_region_anatomical",
                    granularity_level="fine",
                    hemisphere_policy="lateralized" if hemi in ("L", "R") else "bilateral",
                    laterality=laterality,
                    status="active",
                    created_by="import:julich",
                    description=f"Julich-Brain cytoarchitectonic region {julich_id}.",
                    confidence=1.0,
                    source_summary={
                        "source": "Julich-Brain Atlas",
                        "source_file": str(path.relative_to(BACKEND_DIR)),
                        "atlas_region_id": julich_id,
                    },
                    external_mappings={"julich_brain": julich_id},
                ),
            )
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
                    match_details={"atlas_native_id": julich_id},
                    provenance={"importer": "fine_region_importer"},
                    created_by="import:julich",
                )
            )
            stats["mappings"] += 1

        if not await _edge_exists(session, region.id, parent.id):
            await crs.add_part_of_edge(
                session,
                CanonicalRegionHierarchyCreate(
                    child_region_id=region.id,
                    parent_region_id=parent.id,
                    source="import:julich",
                    confidence=1.0,
                    provenance_json={"importer": "fine_region_importer", "julich_id": julich_id},
                    created_by="import:julich",
                ),
            )
            stats["edges"] += 1
    return stats


async def main() -> None:
    async with AsyncSessionLocal() as session:
        bulk = await import_julich_file(session)
        curated = await import_curated_brodmann(session)
        await session.commit()
    if bulk is None:
        print("JULICH BULK IMPORT: no data file under data/atlases/julich/ — skipped (honest)")
    else:
        print("JULICH BULK IMPORT RESULT")
        for k, v in bulk.items():
            print(f"  {k}: {v}")
    print("CURATED BRODMANN RESULT")
    for k, v in curated.items():
        print(f"  {k}: {v}")
    print("OK")


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))
