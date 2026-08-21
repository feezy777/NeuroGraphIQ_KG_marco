"""BR3 multiscale seed (idempotent): canonical anchors + atlas rows + demo mappings.

Run from backend/:
    .venv/Scripts/python.exe scripts/seed_multiscale_ontology.py

What it does (all idempotent):
1. Creates 7 curated canonical anchors (3 meso + 4 subregion) with part_of edges
   into the existing Macro96 clinical layer — Macro96 data is untouched.
2. Imports backend/data/allen/structures.json (Allen MOUSE P56 structure
   ontology, correctly labeled species='mouse') into atlas_region_resources.
3. Creates demo atlas->canonical mappings covering all four mapping_types
   (exact/broader/narrower/uncertain) with species_relation='homology'.
4. Registers demo cell types / molecular entities + alignments (interface
   rows only — NO bulk import; cell types and molecular entities are NOT
   BrainRegions).

Does NOT touch mirror_region_connections / canonical_connections /
canonical_circuits, and does NOT create any inference results.
"""

from __future__ import annotations

import asyncio
import json
import selectors
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.canonical_region import CanonicalBrainRegion
from app.models.multiscale import (
    AtlasRegionMapping,
    AtlasRegionResource,
    CellTypeRegistry,
    MolecularEntityRegistry,
    RegionCellAlignment,
    RegionMolecularAlignment,
)
from app.schemas.canonical_region import CanonicalRegionCreate, CanonicalRegionHierarchyCreate
from app.services import canonical_region_service as crs

ATLAS_NAME = "Allen Mouse Brain Atlas"
ATLAS_VERSION = "P56 structure ontology"
STRUCTURES_JSON = BACKEND_DIR / "data" / "allen" / "structures.json"

# code -> (name_en, name_cn, level, parent_code, uberon_id)
CANONICAL_ANCHORS: list[tuple[str, str, str, str, str | None, str]] = [
    ("ng:br:hippocampal_formation", "Hippocampal formation", "海马结构", "meso",
     "ng:br:hippocampus", "UBERON_0002421"),
    ("ng:br:dlpfc", "Dorsolateral prefrontal cortex", "背外侧前额叶皮层", "meso",
     "ng:br:rostral_middle_frontal", "UBERON_0009834"),
    ("ng:br:vmpfc", "Ventromedial prefrontal cortex", "腹内侧前额叶皮层", "meso",
     "ng:br:medial_orbitofrontal", "UBERON_0009835"),
    ("ng:br:ca1", "Field CA1", "CA1 区", "subregion",
     "ng:br:hippocampal_formation", "UBERON_0003881"),
    ("ng:br:ca3", "Field CA3", "CA3 区", "subregion",
     "ng:br:hippocampal_formation", "UBERON_0003882"),
    ("ng:br:dentate_gyrus", "Dentate gyrus", "齿状回", "subregion",
     "ng:br:hippocampal_formation", "UBERON_0001885"),
    ("ng:br:subiculum", "Subiculum", "下托", "subregion",
     "ng:br:hippocampal_formation", "UBERON_0002191"),
]

# (atlas_native_id, canonical_code, mapping_type, confidence)
DEMO_MAPPINGS: list[tuple[str, str, str, float]] = [
    ("1089", "ng:br:hippocampal_formation", "exact", 0.9),
    ("382", "ng:br:ca1", "exact", 0.9),
    ("463", "ng:br:ca3", "exact", 0.9),
    ("726", "ng:br:dentate_gyrus", "exact", 0.9),
    ("502", "ng:br:subiculum", "exact", 0.9),
    ("1080", "ng:br:hippocampal_formation", "narrower", 0.85),
    ("375", "ng:br:hippocampal_formation", "narrower", 0.8),
    ("184", "ng:br:vmpfc", "broader", 0.6),
    ("44", "ng:br:vmpfc", "uncertain", 0.55),
    ("972", "ng:br:dlpfc", "uncertain", 0.5),
]

# (code, name_en, name_cn, species, taxonomy_source, external_iri, description)
CELL_TYPES: list[tuple[str, str, str, str, str, str, str]] = [
    ("ng:ct:pyramidal_neuron", "Pyramidal neuron", "锥体神经元", "human",
     "Allen Cell Types Database", "https://celltypes.brain-map.org/", "Excitatory principal neuron"),
    ("ng:ct:granule_cell", "Granule cell", "颗粒细胞", "human",
     "Allen Cell Types Database", "https://celltypes.brain-map.org/", "Dentate gyrus principal neuron"),
    ("ng:ct:parvalbumin_interneuron", "Parvalbumin interneuron", "小清蛋白中间神经元", "human",
     "Allen Cell Types Database", "https://celltypes.brain-map.org/", "Fast-spiking GABAergic interneuron"),
]

# (region_code, cell_type_code, mapping_type, confidence)
REGION_CELL_ALIGNMENTS: list[tuple[str, str, str, float]] = [
    ("ng:br:ca1", "ng:ct:pyramidal_neuron", "contains", 0.9),
    ("ng:br:dentate_gyrus", "ng:ct:granule_cell", "contains", 0.95),
    ("ng:br:ca1", "ng:ct:parvalbumin_interneuron", "marker", 0.7),
    # 海马体本身也包含锥体神经元（CA 区的标志性细胞类型）—— 旗舰示例
    ("ng:br:hippocampus", "ng:ct:pyramidal_neuron", "contains", 0.85),
]

# (code, entity_type, name_en, name_cn, external_iri, description)
MOLECULAR_ENTITIES: list[tuple[str, str, str, str, str, str]] = [
    ("ng:mol:bdnf", "gene", "BDNF", "脑源性神经营养因子",
     "http://identifiers.org/hgnc/HGNC:1033", "Brain-derived neurotrophic factor"),
    ("ng:mol:nr3c1", "gene", "NR3C1", "糖皮质激素受体基因",
     "http://identifiers.org/hgnc/HGNC:7978", "Glucocorticoid receptor"),
    ("ng:mol:gad1", "gene", "GAD1", "谷氨酸脱羧酶 1",
     "http://identifiers.org/hgnc/HGNC:4092", "Glutamate decarboxylase 1"),
    ("ng:mol:dopamine", "neurotransmitter", "Dopamine", "多巴胺",
     "http://identifiers.org/chebi/CHEBI:18243", "Monoamine neurotransmitter"),
]

# (region_code, entity_code, evidence_type, confidence)
REGION_MOLECULAR_ALIGNMENTS: list[tuple[str, str, str, float]] = [
    ("ng:br:ca1", "ng:mol:bdnf", "expression", 0.85),
    ("ng:br:dentate_gyrus", "ng:mol:nr3c1", "expression", 0.8),
    ("ng:br:ca3", "ng:mol:gad1", "expression", 0.75),
    ("ng:br:ca1", "ng:mol:dopamine", "expression", 0.6),
    # 海马体是 BDNF 高表达脑区（文献共识）—— 旗舰示例
    ("ng:br:hippocampus", "ng:mol:bdnf", "expression", 0.8),
]


async def _region_by_code(session, code: str) -> CanonicalBrainRegion | None:
    return (
        await session.execute(
            select(CanonicalBrainRegion).where(CanonicalBrainRegion.region_code == code)
        )
    ).scalar_one_or_none()


async def seed_canonical_anchors(session) -> dict[str, int]:
    created = 0
    for code, name_en, name_cn, level, parent_code, uberon in CANONICAL_ANCHORS:
        if await _region_by_code(session, code) is not None:
            continue
        parent = await _region_by_code(session, parent_code)
        if parent is None:
            print(f"  !! parent missing: {parent_code} (skipping {code})")
            continue
        payload = CanonicalRegionCreate(
            region_code=code,
            canonical_name_en=name_en,
            canonical_name_cn=name_cn,
            species="human",
            granularity_domain="brain_region_anatomical",
            granularity_level=level,
            hemisphere_policy="bilateral",
            status="active",
            created_by="seed:multiscale",
            description=f"BR3 curated {level} anchor (curated, UBERON-anchored).",
            confidence=1.0,
            source_summary={"source": "BR3 curated seed", "uberon": uberon},
            external_mappings={"uberon": f"http://purl.obolibrary.org/obo/{uberon}"},
        )
        region = await crs.create_canonical_region(session, payload)
        edge_payload = CanonicalRegionHierarchyCreate(
            child_region_id=region.id,
            parent_region_id=parent.id,
            source="seed:multiscale",
            confidence=1.0,
            provenance_json={"seed": "BR3 multiscale", "uberon": uberon},
            created_by="seed:multiscale",
        )
        await crs.add_part_of_edge(session, edge_payload)
        created += 1
    return {"canonical_anchors_created": created}


async def seed_atlas_rows(session) -> dict[str, int]:
    data = json.loads(STRUCTURES_JSON.read_text(encoding="utf-8"))
    inserted = 0
    skipped = 0
    for row in data:
        existing = (
            await session.execute(
                select(AtlasRegionResource).where(
                    AtlasRegionResource.atlas_name == ATLAS_NAME,
                    AtlasRegionResource.atlas_version == ATLAS_VERSION,
                    AtlasRegionResource.atlas_region_id == str(row.get("id")),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            skipped += 1
            continue
        session.add(
            AtlasRegionResource(
                atlas_name=ATLAS_NAME,
                atlas_version=ATLAS_VERSION,
                atlas_region_id=str(row.get("id")),
                region_name=str(row.get("name") or ""),
                region_acronym=row.get("acronym"),
                parent_region_id=str(row["parent_structure_id"]) if row.get("parent_structure_id") else None,
                species="mouse",
                hemisphere="bilateral",
                source_file=str(STRUCTURES_JSON.relative_to(BACKEND_DIR)),
                provenance={"ontology_id": row.get("ontology_id"), "created_by": "seed:multiscale"},
            )
        )
        inserted += 1
    await session.flush()
    return {"atlas_rows_inserted": inserted, "atlas_rows_skipped": skipped}


async def _atlas_row(session, native_id: str) -> AtlasRegionResource | None:
    return (
        await session.execute(
            select(AtlasRegionResource).where(
                AtlasRegionResource.atlas_name == ATLAS_NAME,
                AtlasRegionResource.atlas_version == ATLAS_VERSION,
                AtlasRegionResource.atlas_region_id == native_id,
            )
        )
    ).scalar_one_or_none()


async def seed_demo_mappings(session) -> dict[str, int]:
    created = 0
    for native_id, code, mtype, conf in DEMO_MAPPINGS:
        atlas_row = await _atlas_row(session, native_id)
        canonical = await _region_by_code(session, code)
        if atlas_row is None or canonical is None:
            print(f"  !! mapping target missing: atlas={native_id} canonical={code}")
            continue
        existing = (
            await session.execute(
                select(AtlasRegionMapping).where(
                    AtlasRegionMapping.atlas_region_id == atlas_row.id,
                    AtlasRegionMapping.canonical_region_id == canonical.id,
                    AtlasRegionMapping.status == "active",
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        session.add(
            AtlasRegionMapping(
                atlas_region_id=atlas_row.id,
                canonical_region_id=canonical.id,
                mapping_type=mtype,
                confidence=conf,
                species_relation="homology",  # mouse atlas -> human canonical
                match_details={"atlas_native_id": native_id},
                provenance={"seed": "BR3 demo", "note": "cross-species homology mapping"},
                created_by="seed:multiscale",
            )
        )
        created += 1
    await session.flush()
    return {"demo_mappings_created": created}


async def seed_cell_and_molecular(session) -> dict[str, int]:
    cell_created = 0
    for code, name_en, name_cn, species, source, iri, desc in CELL_TYPES:
        if (
            await session.execute(
                select(CellTypeRegistry).where(CellTypeRegistry.cell_type_code == code)
            )
        ).scalar_one_or_none() is not None:
            continue
        session.add(
            CellTypeRegistry(
                cell_type_code=code,
                canonical_name_en=name_en,
                canonical_name_cn=name_cn,
                species=species,
                taxonomy_source=source,
                external_iri=iri,
                description=desc,
                provenance={"seed": "BR3 demo"},
            )
        )
        cell_created += 1

    mol_created = 0
    for code, etype, name_en, name_cn, iri, desc in MOLECULAR_ENTITIES:
        if (
            await session.execute(
                select(MolecularEntityRegistry).where(MolecularEntityRegistry.entity_code == code)
            )
        ).scalar_one_or_none() is not None:
            continue
        session.add(
            MolecularEntityRegistry(
                entity_code=code,
                entity_type=etype,
                canonical_name_en=name_en,
                canonical_name_cn=name_cn,
                external_iri=iri,
                species="human",
                description=desc,
                provenance={"seed": "BR3 demo"},
            )
        )
        mol_created += 1
    await session.flush()

    cell_align_created = 0
    for region_code, ct_code, mtype, conf in REGION_CELL_ALIGNMENTS:
        region = await _region_by_code(session, region_code)
        ct = (
            await session.execute(
                select(CellTypeRegistry).where(CellTypeRegistry.cell_type_code == ct_code)
            )
        ).scalar_one_or_none()
        if region is None or ct is None:
            continue
        dup = (
            await session.execute(
                select(RegionCellAlignment).where(
                    RegionCellAlignment.region_id == region.id,
                    RegionCellAlignment.cell_type_id == ct.id,
                    RegionCellAlignment.mapping_type == mtype,
                )
            )
        ).scalar_one_or_none()
        if dup is not None:
            continue
        session.add(
            RegionCellAlignment(
                region_id=region.id,
                cell_type_id=ct.id,
                mapping_type=mtype,
                confidence=conf,
                provenance={"seed": "BR3 demo"},
            )
        )
        cell_align_created += 1

    mol_align_created = 0
    for region_code, entity_code, etype, conf in REGION_MOLECULAR_ALIGNMENTS:
        region = await _region_by_code(session, region_code)
        entity = (
            await session.execute(
                select(MolecularEntityRegistry).where(
                    MolecularEntityRegistry.entity_code == entity_code
                )
            )
        ).scalar_one_or_none()
        if region is None or entity is None:
            continue
        dup = (
            await session.execute(
                select(RegionMolecularAlignment).where(
                    RegionMolecularAlignment.region_id == region.id,
                    RegionMolecularAlignment.molecular_entity_id == entity.id,
                    RegionMolecularAlignment.evidence_type == etype,
                )
            )
        ).scalar_one_or_none()
        if dup is not None:
            continue
        session.add(
            RegionMolecularAlignment(
                region_id=region.id,
                molecular_entity_id=entity.id,
                entity_type=entity.entity_type,
                evidence_type=etype,
                confidence=conf,
                source="Allen HBA expression (existing molecular_attr family)",
                provenance={"seed": "BR3 demo"},
            )
        )
        mol_align_created += 1
    await session.flush()
    return {
        "cell_types_created": cell_created,
        "molecular_entities_created": mol_created,
        "region_cell_alignments_created": cell_align_created,
        "region_molecular_alignments_created": mol_align_created,
    }


async def main() -> None:
    if not STRUCTURES_JSON.exists():
        print(f"ERROR: atlas data file missing: {STRUCTURES_JSON}")
        print("Expected backend/data/allen/structures.json (Allen P56 structure ontology).")
        raise SystemExit(1)
    stats: dict[str, int] = {}
    async with AsyncSessionLocal() as session:
        stats.update(await seed_canonical_anchors(session))
        stats.update(await seed_atlas_rows(session))
        stats.update(await seed_demo_mappings(session))
        stats.update(await seed_cell_and_molecular(session))
        await session.commit()
    print("SEED RESULT")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print("OK")


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))
