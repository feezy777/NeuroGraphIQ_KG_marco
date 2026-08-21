"""Cell type importer (idempotent) — Allen Cell Types / Hodge 2019 taxonomy.

Cell types are NEVER BrainRegions: they go to cell_type_registry
(ng:ct:* codes) and align to canonical regions via region_cell_alignment
(mapping_type contains/enriched/marker). No rows enter canonical_brain_regions
or canonical_region_hierarchy.

Run from backend/:
    .venv/Scripts/python.exe scripts/cell_type_importer.py

Data note (honest): the celltypes.brain-map.org API endpoints are unreachable
from this dev environment; the imported set is curated from the published
human MTG SMART-seq taxonomy (Hodge et al., Nature 573:61-68, 2019), hosted by
the Allen Cell Types Database. Pvalb subclass is covered by the existing
ng:ct:parvalbumin_interneuron demo row — not duplicated.
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
from app.models.canonical_region import CanonicalBrainRegion
from app.models.multiscale import CellTypeRegistry, RegionCellAlignment

CITATION = "Hodge et al., Nature 573:61-68, 2019 (human MTG SMART-seq taxonomy)"
TAXONOMY_SOURCE = "Allen Cell Types Database"
TAXONOMY_VERSION = "Hodge 2019 (human MTG)"

# code, name_en, name_cn, description
CELL_TYPES: list[tuple[str, str, str, str]] = [
    ("ng:ct:l23_it", "L2/3 IT neuron", "第 2/3 层端脑内投射神经元", "Glutamatergic intratelencephalic projecting neuron"),
    ("ng:ct:l4_it", "L4 IT neuron", "第 4 层端脑内投射神经元", "Glutamatergic intratelencephalic projecting neuron"),
    ("ng:ct:l5_it", "L5 IT neuron", "第 5 层端脑内投射神经元", "Glutamatergic intratelencephalic projecting neuron"),
    ("ng:ct:l5_et", "L5 ET neuron", "第 5 层端脑外投射神经元", "Glutamatergic extratelencephalic projecting neuron"),
    ("ng:ct:l56_np", "L5/6 NP neuron", "第 5/6 层近投射神经元", "Glutamatergic near-projecting neuron"),
    ("ng:ct:l6_it", "L6 IT neuron", "第 6 层端脑内投射神经元", "Glutamatergic intratelencephalic projecting neuron"),
    ("ng:ct:l6_ct", "L6 CT neuron", "第 6 层皮质丘脑投射神经元", "Glutamatergic corticothalamic projecting neuron"),
    ("ng:ct:l6b", "L6b neuron", "第 6b 层神经元", "Glutamatergic subplate-derived neuron"),
    ("ng:ct:lamp5", "Lamp5 interneuron", "Lamp5 阳性中间神经元", "GABAergic Lamp5-expressing interneuron"),
    ("ng:ct:sncg", "Sncg interneuron", "Sncg 阳性中间神经元", "GABAergic Sncg-expressing interneuron"),
    ("ng:ct:vip", "VIP interneuron", "VIP 阳性中间神经元", "GABAergic vasoactive intestinal peptide-expressing interneuron"),
    ("ng:ct:sst_chodl", "Sst Chodl interneuron", "Sst-Chodl 阳性中间神经元", "GABAergic long-range projecting Sst/Chodl interneuron"),
    ("ng:ct:sst", "Sst interneuron", "生长抑素阳性中间神经元", "GABAergic somatostatin-expressing interneuron"),
    ("ng:ct:astrocyte", "Astrocyte", "星形胶质细胞", "Non-neuronal astrocyte"),
    ("ng:ct:oligodendrocyte", "Oligodendrocyte", "少突胶质细胞", "Non-neuronal myelinating oligodendrocyte"),
    ("ng:ct:opc", "OPC", "少突胶质前体细胞", "Non-neuronal oligodendrocyte precursor cell"),
    ("ng:ct:microglia", "Microglia", "小胶质细胞", "Non-neuronal microglia"),
    ("ng:ct:endothelial", "Endothelial cell", "内皮细胞", "Non-neuronal vascular endothelial cell"),
]

# region_code, cell_type_code, mapping_type, confidence
# Hodge sampled MTG → all subclasses align to middle temporal (contains);
# two classical well-established facts complete the set.
ALIGNMENTS: list[tuple[str, str, str, float]] = [
    ("ng:br:middle_temporal", "ng:ct:l23_it", "contains", 0.9),
    ("ng:br:middle_temporal", "ng:ct:l4_it", "contains", 0.9),
    ("ng:br:middle_temporal", "ng:ct:l5_it", "contains", 0.9),
    ("ng:br:middle_temporal", "ng:ct:l5_et", "contains", 0.9),
    ("ng:br:middle_temporal", "ng:ct:l56_np", "contains", 0.9),
    ("ng:br:middle_temporal", "ng:ct:l6_it", "contains", 0.9),
    ("ng:br:middle_temporal", "ng:ct:l6_ct", "contains", 0.9),
    ("ng:br:middle_temporal", "ng:ct:l6b", "contains", 0.9),
    ("ng:br:middle_temporal", "ng:ct:lamp5", "contains", 0.9),
    ("ng:br:middle_temporal", "ng:ct:sncg", "contains", 0.9),
    ("ng:br:middle_temporal", "ng:ct:vip", "contains", 0.9),
    ("ng:br:middle_temporal", "ng:ct:sst_chodl", "contains", 0.9),
    ("ng:br:middle_temporal", "ng:ct:sst", "contains", 0.9),
    ("ng:br:middle_temporal", "ng:ct:astrocyte", "contains", 0.9),
    ("ng:br:middle_temporal", "ng:ct:oligodendrocyte", "contains", 0.9),
    ("ng:br:middle_temporal", "ng:ct:opc", "contains", 0.9),
    ("ng:br:middle_temporal", "ng:ct:microglia", "contains", 0.9),
    ("ng:br:middle_temporal", "ng:ct:endothelial", "contains", 0.9),
    ("ng:br:ca1", "ng:ct:sst", "contains", 0.8),
    ("ng:br:cerebrum", "ng:ct:microglia", "contains", 0.9),
]


async def _region_by_code(session, code: str) -> CanonicalBrainRegion | None:
    return (
        await session.execute(
            select(CanonicalBrainRegion).where(CanonicalBrainRegion.region_code == code)
        )
    ).scalar_one_or_none()


async def import_cell_types(session) -> dict[str, int]:
    stats = {"cell_types_created": 0, "alignments_created": 0, "skipped": 0}

    created_by_code: dict[str, int] = {}
    for code, name_en, name_cn, desc in CELL_TYPES:
        existing = (
            await session.execute(
                select(CellTypeRegistry).where(CellTypeRegistry.cell_type_code == code)
            )
        ).scalar_one_or_none()
        if existing is not None:
            created_by_code[code] = existing.id
            continue
        row = CellTypeRegistry(
            cell_type_code=code,
            canonical_name_en=name_en,
            canonical_name_cn=name_cn,
            species="human",
            taxonomy_source=TAXONOMY_SOURCE,
            taxonomy_version=TAXONOMY_VERSION,
            external_iri="https://celltypes.brain-map.org/",
            description=desc,
            provenance={
                "importer": "cell_type_importer",
                "citation": CITATION,
                "note": "curated from the published taxonomy — API unreachable from dev environment",
            },
        )
        session.add(row)
        await session.flush()
        created_by_code[code] = row.id
        stats["cell_types_created"] += 1

    for region_code, ct_code, mtype, conf in ALIGNMENTS:
        region = await _region_by_code(session, region_code)
        ct_id = created_by_code.get(ct_code)
        if region is None or ct_id is None:
            print(f"  !! alignment target missing: region={region_code} cell={ct_code}")
            stats["skipped"] += 1
            continue
        dup = (
            await session.execute(
                select(RegionCellAlignment).where(
                    RegionCellAlignment.region_id == region.id,
                    RegionCellAlignment.cell_type_id == ct_id,
                    RegionCellAlignment.mapping_type == mtype,
                )
            )
        ).scalar_one_or_none()
        if dup is not None:
            continue
        session.add(
            RegionCellAlignment(
                region_id=region.id,
                cell_type_id=ct_id,
                mapping_type=mtype,
                confidence=conf,
                provenance={"importer": "cell_type_importer", "citation": CITATION},
            )
        )
        stats["alignments_created"] += 1
    return stats


async def main() -> None:
    async with AsyncSessionLocal() as session:
        stats = await import_cell_types(session)
        await session.commit()
    print("CELL TYPE IMPORT RESULT")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print("OK")


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))
