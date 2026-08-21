"""BR1 seed: Canonical BrainRegion L0/L1 Macro Backbone (idempotent).

Writes ONLY:
- L0 canonical region: Brain (whole_brain)
- L1 canonical regions: Cerebrum / Diencephalon / Brain stem / Cerebellum (macro)
- L1 --part_of--> L0 edges
- exact/close candidate grounding (Macro96) via canonical_region_id FK

Does NOT write: L2/L3 nodes, Allen candidates, AAL3, Brainnetome/HCP parcels,
inferred facts, connections, circuits. Deferred mappings are printed as a
report only.

Usage:
    python scripts/seed_brain_region_backbone.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy import select, text

from app.database import AsyncSessionLocal
from app.models.candidate import CandidateBrainRegion
from app.schemas.canonical_region import CanonicalRegionCreate, CanonicalRegionHierarchyCreate
from app.services import canonical_region_service as crs

ALLEN_STRUCTURES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "allen", "structures.json"
)

# --------------------------------------------------------------------------- #
# L0 / L1 canonical backbone — every node sourced from Allen HBA + Macro96
# --------------------------------------------------------------------------- #

# allen_id: (name, depth) verified against backend/data/allen/structures.json (2026-08-20)
REGIONS: list[dict] = [
    {
        "region_code": "ng:br:brain",
        "canonical_name_en": "Brain",
        "canonical_name_cn": "脑",
        "species": "human",
        "granularity_domain": "brain_region_anatomical",
        "granularity_level": "whole_brain",
        "hemisphere_policy": "bilateral",
        "status": "active",
        "confidence": 0.99,
        "description": "Whole-brain root of the NeuroGraphIQ BrainRegion partonomy (L0).",
        "source_summary": {
            "allen": {"structure_id": 997, "name": "root", "path": "/997/"},
            "macro96": {"support": "implicit root of the 96-pool"},
        },
        "created_by": "br1_seed",
    },
    {
        "region_code": "ng:br:cerebrum",
        "canonical_name_en": "Cerebrum",
        "canonical_name_cn": "大脑",
        "species": "human",
        "granularity_domain": "brain_region_anatomical",
        "granularity_level": "macro",
        "hemisphere_policy": "bilateral",
        "status": "active",
        "confidence": 0.98,
        "description": "Telencephalic cerebrum: cerebral cortex + cerebral nuclei.",
        "source_summary": {
            "allen": {"structure_id": 567, "name": "Cerebrum", "path": "/997/8/567/"},
            "macro96": {"support": "cortex regions (Desikan-style) + subcortical structures"},
        },
        "created_by": "br1_seed",
    },
    {
        "region_code": "ng:br:diencephalon",
        "canonical_name_en": "Diencephalon",
        "canonical_name_cn": "间脑",
        "species": "human",
        "granularity_domain": "brain_region_anatomical",
        "granularity_level": "macro",
        "hemisphere_policy": "bilateral",
        "status": "active",
        "confidence": 0.95,
        "description": "Interbrain: thalamus, hypothalamus, epithalamus, subthalamus.",
        "source_summary": {
            "allen": {"structure_id": 1129, "name": "Interbrain", "path": "/997/8/343/1129/",
                      "note": "Allen places Interbrain under Brain stem; we follow the classic "
                              "division (diencephalon = forebrain major division) with parent Brain."},
            "macro96": {"support": "ventral diencephalon (FreeSurfer, ventral part only)"},
        },
        "created_by": "br1_seed",
    },
    {
        "region_code": "ng:br:brain_stem",
        "canonical_name_en": "Brain stem",
        "canonical_name_cn": "脑干",
        "species": "human",
        "granularity_domain": "brain_region_anatomical",
        "granularity_level": "macro",
        "hemisphere_policy": "midline_unpaired",
        "status": "active",
        "confidence": 0.98,
        "description": "Midbrain, pons and medulla (excluding Interbrain per classic division).",
        "source_summary": {
            "allen": {"structure_id": 343, "name": "Brain stem", "path": "/997/8/343/"},
            "macro96": {"support": "exact 'Brain stem' label (midline)"},
        },
        "created_by": "br1_seed",
    },
    {
        "region_code": "ng:br:cerebellum",
        "canonical_name_en": "Cerebellum",
        "canonical_name_cn": "小脑",
        "species": "human",
        "granularity_domain": "brain_region_anatomical",
        "granularity_level": "macro",
        "hemisphere_policy": "bilateral",
        "status": "active",
        "confidence": 0.98,
        "description": "Cerebellar cortex, nuclei and white matter.",
        "source_summary": {
            "allen": {"structure_id": 512, "name": "Cerebellum", "path": "/997/8/512/"},
            "macro96": {"support": "cerebellum exterior + cerebellum white matter (L/R)"},
        },
        "created_by": "br1_seed",
    },
]

# (child_code, parent_code, source, confidence, provenance)
EDGES: list[tuple[str, str, str, float, dict]] = [
    ("ng:br:cerebrum", "ng:br:brain", "allen_hba_hierarchy", 0.98,
     {"allen_path": "/997/8/567/", "basis": "major brain division"}),
    ("ng:br:diencephalon", "ng:br:brain", "classic_division + macro96", 0.95,
     {"allen_path": "/997/8/343/1129/",
      "note": "Allen path nests Interbrain under Brain stem; classic division "
              "treats diencephalon as a forebrain major division — documented deviation."}),
    ("ng:br:brain_stem", "ng:br:brain", "allen_hba_hierarchy + macro96", 0.98,
     {"allen_path": "/997/8/343/"}),
    ("ng:br:cerebellum", "ng:br:brain", "allen_hba_hierarchy + macro96", 0.98,
     {"allen_path": "/997/8/512/"}),
]

# Grounding rules: (match predicate, canonical region_code, match_type, confidence, detail)
# Macro96 en_name exact patterns only — no fuzzy name matching.
GROUNDINGS: list[tuple[str, str, str, float, str]] = [
    ("en_name = 'Brain stem' AND laterality = 'midline'", "ng:br:brain_stem", "exact", 0.98,
     "Macro96 exact label"),
    ("en_name ILIKE '%cerebellum %'", "ng:br:cerebellum", "close", 0.9,
     "FreeSurfer cerebellum exterior + white matter compartments jointly cover the canonical cerebellum"),
    ("en_name ILIKE '%ventral diencephalon%'", "ng:br:diencephalon", "close", 0.85,
     "FreeSurfer ventral diencephalon is the ventral part of the diencephalon (unambiguous)"),
]


def _load_allen_reference() -> dict[int, dict]:
    with open(ALLEN_STRUCTURES, encoding="utf-8") as f:
        data = json.load(f)
    return {int(s["id"]): s for s in data}


async def main() -> None:
    allen = _load_allen_reference()
    async with AsyncSessionLocal() as session:
        created: list[str] = []
        for spec in REGIONS:
            existing = await crs.get_canonical_region_by_code(session, spec["region_code"])
            if existing is not None:
                continue
            await crs.create_canonical_region(session, CanonicalRegionCreate(**spec))
            created.append(spec["region_code"])
        # sanity: allen references actually exist in the local structure tree
        for spec in REGIONS:
            aid = spec["source_summary"]["allen"]["structure_id"]
            if aid not in allen:
                print(f"[warn] allen structure {aid} not found in structures.json")

        edges_created = 0
        for child_code, parent_code, source, confidence, provenance in EDGES:
            child = await crs.get_canonical_region_by_code(session, child_code)
            parent = await crs.get_canonical_region_by_code(session, parent_code)
            if child is None or parent is None:
                print(f"[warn] edge skipped (missing node): {child_code} -> {parent_code}")
                continue
            dup = (
                await session.execute(
                    text(
                        "SELECT 1 FROM canonical_region_hierarchy "
                        "WHERE child_region_id=:c AND parent_region_id=:p"
                    ),
                    {"c": child.id, "p": parent.id},
                )
            ).scalar_one_or_none()
            if dup is not None:
                continue
            await crs.add_part_of_edge(
                session,
                CanonicalRegionHierarchyCreate(
                    child_region_id=child.id,
                    parent_region_id=parent.id,
                    predicate="part_of",
                    status="active",
                    source=source,
                    confidence=confidence,
                    provenance_json=provenance,
                    created_by="br1_seed",
                ),
            )
            edges_created += 1

        grounded: list[str] = []
        for where, code, match_type, confidence, detail in GROUNDINGS:
            canonical = await crs.get_canonical_region_by_code(session, code)
            if canonical is None:
                print(f"[warn] grounding skipped (missing canonical): {code}")
                continue
            rows = (
                await session.execute(
                    select(CandidateBrainRegion).where(
                        CandidateBrainRegion.source_atlas == "Macro96"
                    ).where(text(where))
                )
            ).scalars().all()
            for c in rows:
                await crs.ground_candidate(
                    session,
                    candidate_id=c.id,
                    canonical_region_id=canonical.id,
                    match_type=match_type,
                    confidence=confidence,
                    match_details={"rule": detail, "seed": "br1", "source_atlas": c.source_atlas},
                )
                grounded.append(f"{c.en_name} -> {code}")

        await session.commit()

        integrity = await crs.check_canonical_brain_region_integrity(session)
        print("created:", created or "(all present)")
        print("edges_created:", edges_created)
        print("grounded:", len(grounded))
        for g in grounded:
            print("   ", g)
        print("integrity:", json.dumps(integrity["counts"], ensure_ascii=False))
        print("issues:", json.dumps(integrity["issues"], ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
