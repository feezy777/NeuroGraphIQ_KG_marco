"""Brainnetome BNA246 importer (idempotent) — external data → atlas layer → canonical.

Governance chain (never writes external rows directly into canonical):
    BNA246_regions_circos.tsv (source file)
        → atlas_region_resources (246 rows, atlas-native identity)
            → atlas_region_mappings (exact, same_species)
                → canonical_brain_regions (granularity_level='meso', laterality='left'|'right')
                    → canonical_region_hierarchy (BNA subregion --part_of--> gyrus parent)

Run from backend/:
    .venv/Scripts/python.exe scripts/brainnetome_importer.py

Data notes (honest):
- The official BNA246 table is hosted on brainnetome.org (unreachable from this
  dev environment); the importer uses the official atlas's circos band file
  (246 rows = 210 cortical + 36 subcortical, odd id = left hemisphere, matching
  the BNA246 README numbering).
- Gyrus abbreviations in the circos file differ from the Fan-2016 paper names
  (Cun=MVOcC, Ent=PhG, OcG/sOcG=LOcC, Str=BG, Th=Tha); GYRUS_PARENT maps them
  explicitly.
- Hemisphere info is stored in the laterality field — NO left_*/right_* names
  or entities (code suffix _l/_r exists only because region_code is unique).
- Gyrus-level parents are the existing clinical (Macro96) regions where the
  circos gyrus maps 1:1; where one circos gyrus spans several clinical regions
  (MFG/IFG/CG/Cun/Str), the subregion attaches to cerebrum directly — recorded
  in the edge provenance, not silently guessed.
"""

from __future__ import annotations

import asyncio
import re
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

TSV_PATH = BACKEND_DIR / "data" / "atlases" / "brainnetome" / "BNA246_regions_circos.tsv"
ATLAS_NAME = "Brainnetome Atlas"
ATLAS_VERSION = "BNA246 (2016)"
RESOURCE_CODE = "brainnetome_bna246"

_BAND_RE = re.compile(r"^(?P<gyrus>[A-Za-z0-9]+)_(?P<hemi>[LR])_(?P<n>\d+)_(?P<idx>\d+)$")

# circos lobe id -> lobe name (from the 14 `chr - lobeN ...` header rows)
_LOBE_NAMES = {
    "lobe1": "frontal", "lobe2": "insular", "lobe3": "limbic", "lobe4": "temporal",
    "lobe5": "parietal", "lobe6": "occipital", "lobe7": "subcortical",
    "lobe8": "subcortical", "lobe9": "occipital", "lobe10": "parietal",
    "lobe11": "temporal", "lobe12": "limbic", "lobe13": "insular", "lobe14": "frontal",
}

# circos gyrus abbr -> (parent canonical code, gyrus name EN, gyrus name CN)
# Parent = existing clinical region when the gyrus maps 1:1; ng:br:cerebrum when
# the gyrus spans several clinical regions (see module docstring).
GYRUS_PARENT: dict[str, tuple[str, str, str]] = {
    "SFG": ("ng:br:superior_frontal", "Superior frontal gyrus", "额上回"),
    "MFG": ("ng:br:cerebrum", "Middle frontal gyrus", "额中回"),
    "IFG": ("ng:br:cerebrum", "Inferior frontal gyrus", "额下回"),
    "OrG": ("ng:br:lateral_orbitofrontal", "Orbital gyrus", "眶回"),
    "PrG": ("ng:br:precentral", "Precentral gyrus", "中央前回"),
    "PCL": ("ng:br:paracentral", "Paracentral lobule", "中央旁小叶"),
    "STG": ("ng:br:superior_temporal", "Superior temporal gyrus", "颞上回"),
    "MTG": ("ng:br:middle_temporal", "Middle temporal gyrus", "颞中回"),
    "ITG": ("ng:br:inferior_temporal", "Inferior temporal gyrus", "颞下回"),
    "FuG": ("ng:br:fusiform", "Fusiform gyrus", "梭状回"),
    "pSTS": ("ng:br:superior_temporal", "Posterior superior temporal sulcus", "颞上沟后部"),
    "SPL": ("ng:br:superior_parietal", "Superior parietal lobule", "顶上小叶"),
    "IPL": ("ng:br:inferior_parietal", "Inferior parietal lobule", "顶下小叶"),
    "PCun": ("ng:br:precuneus", "Precuneus", "楔前叶"),
    "PoG": ("ng:br:postcentral", "Postcentral gyrus", "中央后回"),
    "Ins": ("ng:br:insula", "Insular gyrus", "岛回"),
    "CG": ("ng:br:cerebrum", "Cingulate gyrus", "扣带回"),
    "Cun": ("ng:br:cerebrum", "Medioventral occipital cortex", "腹内侧枕叶皮层"),
    "Ent": ("ng:br:parahippocampal", "Parahippocampal gyrus", "海马旁回"),
    "OcG": ("ng:br:lateral_occipital", "Lateral occipital cortex", "外侧枕叶皮层"),
    "sOcG": ("ng:br:lateral_occipital", "Superior lateral occipital cortex", "上外侧枕叶皮层"),
    "Amg": ("ng:br:amygdala", "Amygdala", "杏仁核"),
    "Hipp": ("ng:br:hippocampus", "Hippocampus", "海马"),
    "Str": ("ng:br:cerebrum", "Striatum (basal ganglia)", "纹状体"),
    "Th": ("ng:br:thalamus_proper", "Thalamus", "丘脑"),
}

_LATERALITY_CN = {"L": "左", "R": "右"}


def parse_tsv(path: Path) -> list[dict]:
    """Parse circos band rows -> [{id, lobe, gyrus, hemi, n, idx}].

    Skips the 14 `chr - lobeN ...` header lines; keeps only `band` rows.
    """
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if not fields or fields[0] != "band":
            continue
        lobe_key, band_id, name = fields[1], int(fields[2]), fields[3]
        match = _BAND_RE.match(name)
        if match is None:
            print(f"  !! unparsable band name: {name!r} (id={band_id}) — skipped")
            continue
        rows.append(
            {
                "id": band_id,
                "lobe": _LOBE_NAMES.get(lobe_key, "unknown"),
                "gyrus": match.group("gyrus"),
                "hemi": match.group("hemi"),
                "n": int(match.group("n")),
                "idx": int(match.group("idx")),
                "native_name": name,
            }
        )
    return rows


async def _region_by_code(session, code: str) -> CanonicalBrainRegion | None:
    return (
        await session.execute(
            select(CanonicalBrainRegion).where(CanonicalBrainRegion.region_code == code)
        )
    ).scalar_one_or_none()


async def _atlas_row(session, atlas_region_id: str) -> AtlasRegionResource | None:
    return (
        await session.execute(
            select(AtlasRegionResource).where(
                AtlasRegionResource.atlas_name == ATLAS_NAME,
                AtlasRegionResource.atlas_version == ATLAS_VERSION,
                AtlasRegionResource.atlas_region_id == atlas_region_id,
            )
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


async def import_bna246(session) -> dict[str, int]:
    resource = (
        await session.execute(
            select(AtlasResource).where(AtlasResource.resource_code == RESOURCE_CODE)
        )
    ).scalar_one_or_none()
    if resource is None:
        raise RuntimeError(f"atlas resource not registered: {RESOURCE_CODE}")

    stats = {"atlas_rows": 0, "canonical_created": 0, "mappings": 0, "edges": 0, "skipped": 0}
    for row in parse_tsv(TSV_PATH):
        parent_code, gyrus_en, gyrus_cn = GYRUS_PARENT[row["gyrus"]]
        parent = await _region_by_code(session, parent_code)
        if parent is None:
            print(f"  !! parent missing: {parent_code} (gyrus {row['gyrus']}) — skipped")
            stats["skipped"] += 1
            continue

        hemi_lower = row["hemi"].lower()
        laterality = "left" if row["hemi"] == "L" else "right"
        code = f"ng:br:bna_{row['gyrus'].lower()}_{row['n']}_{row['idx']}_{hemi_lower}"

        # 1) atlas row (atlas-native identity)
        atlas_row = await _atlas_row(session, str(row["id"]))
        if atlas_row is None:
            atlas_row = AtlasRegionResource(
                atlas_resource_id=resource.id,
                atlas_name=ATLAS_NAME,
                atlas_version=ATLAS_VERSION,
                atlas_region_id=str(row["id"]),
                region_name=row["native_name"],
                region_acronym=row["gyrus"],
                parent_region_id=None,
                species="human",
                hemisphere=row["hemi"],
                source_file=str(TSV_PATH.relative_to(BACKEND_DIR)),
                provenance={
                    "importer": "brainnetome_importer",
                    "lobe": row["lobe"],
                    "gyrus": row["gyrus"],
                    "hemisphere": row["hemi"],
                },
            )
            session.add(atlas_row)
            await session.flush()
            stats["atlas_rows"] += 1

        # 2) canonical region (granularity_level='meso', laterality carries the side)
        region = await _region_by_code(session, code)
        if region is None:
            payload = CanonicalRegionCreate(
                region_code=code,
                canonical_name_en=f"{gyrus_en} BNA {row['n']}_{row['idx']} ({laterality})",
                canonical_name_cn=f"{gyrus_cn} BNA {row['n']}-{row['idx']}（{_LATERALITY_CN[row['hemi']]}）",
                species="human",
                granularity_domain="brain_region_anatomical",
                granularity_level="meso",
                hemisphere_policy="lateralized",
                laterality=laterality,
                status="active",
                created_by="import:brainnetome",
                description=(
                    f"Brainnetome BNA246 subregion {row['native_name']} "
                    f"(lobe: {row['lobe']}, gyrus: {gyrus_en})."
                ),
                confidence=1.0,
                source_summary={
                    "source": "Brainnetome Atlas BNA246 (2016)",
                    "source_file": "data/atlases/brainnetome/BNA246_regions_circos.tsv",
                    "atlas_region_id": row["id"],
                    "native_name": row["native_name"],
                    "gyrus": row["gyrus"],
                    "lobe": row["lobe"],
                    "note": "circos band file of the official atlas (brainnetome.org unreachable in dev env)",
                },
                external_mappings={
                    "brainnetome_bna": row["native_name"],
                    "brainnetome_id": str(row["id"]),
                },
            )
            region = await crs.create_canonical_region(session, payload)
            stats["canonical_created"] += 1

        # 3) mapping (atlas_region -> canonical, exact / same_species)
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
                    match_details={"atlas_native_id": str(row["id"]), "native_name": row["native_name"]},
                    provenance={"importer": "brainnetome_importer"},
                    created_by="import:brainnetome",
                )
            )
            stats["mappings"] += 1

        # 4) hierarchy edge: BNA subregion --part_of--> gyrus parent
        if not await _edge_exists(session, region.id, parent.id):
            await crs.add_part_of_edge(
                session,
                CanonicalRegionHierarchyCreate(
                    child_region_id=region.id,
                    parent_region_id=parent.id,
                    source="import:brainnetome",
                    confidence=1.0,
                    provenance_json={
                        "importer": "brainnetome_importer",
                        "gyrus": row["gyrus"],
                        "lobe": row["lobe"],
                        "note": (
                            "parent is cerebrum because the circos gyrus spans several "
                            "clinical regions" if parent_code == "ng:br:cerebrum" else "gyrus-level parent"
                        ),
                    },
                    created_by="import:brainnetome",
                ),
            )
            stats["edges"] += 1

    return stats


async def main() -> None:
    if not TSV_PATH.exists():
        print(f"ERROR: BNA246 data file missing: {TSV_PATH}")
        raise SystemExit(1)
    async with AsyncSessionLocal() as session:
        stats = await import_bna246(session)
        await session.commit()
    print("BNA246 IMPORT RESULT")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print("OK")


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))
