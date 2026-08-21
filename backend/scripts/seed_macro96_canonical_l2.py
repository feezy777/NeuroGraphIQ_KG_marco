"""BR2 seed: Macro96 96-pool -> Canonical BrainRegion L2 (Clinical regions).

Builds the canonical hierarchy:
    L0 Brain
     └── L1 Macro system (Cerebrum / Diencephalon / Brain stem / Cerebellum)
           └── L2 Clinical regions (Macro96 structures, hemisphere-neutral)

Rules:
- Hemisphere-neutral canonical concepts: left/right candidate rows anchor to
  ONE concept (laterality stays on candidates, never dropped).
- 4 L1 concepts are directly reused by 96-pool structures that ARE the L1
  concept itself (Brain stem / Cerebellum exterior+WM / Ventral diencephalon).
- All 96 candidate rows end up with canonical_region_id (96/96 acceptance).
- Non-neural structures present in the 96 pool (ventricles/CSF/white matter)
  become L2 concepts part_of Brain — the pool is treated as given, no
  structures are dropped.

Idempotent. Usage:
    python scripts/seed_macro96_canonical_l2.py
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy import select, text

from app.database import AsyncSessionLocal
from app.models.candidate import CandidateBrainRegion
from app.schemas.canonical_region import CanonicalRegionCreate, CanonicalRegionHierarchyCreate
from app.services import canonical_region_service as crs

DATA_JSON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "macro96_regions.json"
)

# Explicit parent mapping (key -> L1 canonical code). Keys are 96-pool names
# with the left/right prefix stripped. Derived from the actual pool contents.
_PARENT_MAP: dict[str, str] = {
    # --- cortex (31) -> Cerebrum ---
    **{k: "ng:br:cerebrum" for k in [
        "caudal anterior cingulate", "caudal middle frontal", "cuneus", "entorhinal",
        "fusiform", "inferior parietal", "inferior temporal", "isthmus cingulate",
        "lateral occipital", "lateral orbitofrontal", "lingual gyrus",
        "medial orbitofrontal", "middle temporal", "parahippocampal", "paracentral",
        "pars opercularis", "pars orbitalis", "pars triangularis", "pericalcarine",
        "postcentral", "posterior cingulate", "precentral", "precuneus",
        "rostral anterior cingulate", "rostral middle frontal", "superior frontal",
        "superior parietal", "superior temporal", "supramarginal",
        "transverse temporal", "insula",
    ]},
    # --- subcortex (7) -> Cerebrum ---
    "accumbens area": "ng:br:cerebrum",
    "amygdala": "ng:br:cerebrum",
    "basal forebrain": "ng:br:cerebrum",
    "caudate": "ng:br:cerebrum",
    "hippocampus": "ng:br:cerebrum",
    "pallidum": "ng:br:cerebrum",
    "putamen": "ng:br:cerebrum",
    # --- diencephalon ---
    "thalamus proper": "ng:br:diencephalon",
    # --- cerebellum ---
    "cerebellar vermal lobules i-v": "ng:br:cerebellum",
    "cerebellar vermal lobules vi-vii": "ng:br:cerebellum",
    "cerebellar vermal lobules viii-x": "ng:br:cerebellum",
    # --- ventricles / CSF / white matter -> Brain (L0) ---
    "lateral ventricle": "ng:br:brain",
    "inferior lateral ventricle": "ng:br:brain",
    "3rd ventricle": "ng:br:brain",
    "4th ventricle": "ng:br:brain",
    "csf": "ng:br:brain",
    "white matter": "ng:br:brain",
}

# 96-pool structures that ARE the L1 concept itself — no new concept created,
# candidates ground directly to the existing L1 canonical region.
_L1_REUSE: dict[str, str] = {
    "brain stem": "ng:br:brain_stem",
    "cerebellum exterior": "ng:br:cerebellum",
    "cerebellum white matter": "ng:br:cerebellum",
    "ventral diencephalon": "ng:br:diencephalon",
}

_LATERAL_PREFIX = re.compile(r"^(left|right)\s+", re.IGNORECASE)
_LATERAL_CN_PREFIX = re.compile(r"^(左|右)")


_CANONICAL_NAME_OVERRIDE = {"csf": "CSF", "3rd ventricle": "3rd ventricle", "4th ventricle": "4th ventricle"}


def _canonical_name_en(key: str) -> str:
    # FreeSurfer-style names stay as-is except a leading title-case letter.
    if key in _CANONICAL_NAME_OVERRIDE:
        return _CANONICAL_NAME_OVERRIDE[key]
    return key[0].upper() + key[1:]


def _slug(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")


def _load_pool() -> list[dict]:
    with open(DATA_JSON, encoding="utf-8") as f:
        return json.load(f)


def _group_pool(pool: list[dict]) -> dict[str, dict]:
    """Group 96-pool rows by hemisphere-stripped key.

    Returns {key: {lats: [...], en: [...], cn: [...]}}
    """
    groups: dict[str, dict] = {}
    for row in pool:
        en = row["name_en"]
        cn = row.get("name_cn") or ""
        key = _LATERAL_PREFIX.sub("", en).strip().lower()
        g = groups.setdefault(key, {"lats": [], "en": [], "cn": []})
        g["lats"].append(row["laterality"])
        g["en"].append(en)
        g["cn"].append(cn)
    return groups


async def main() -> None:
    pool = _load_pool()
    groups = _group_pool(pool)
    assert len(pool) == 96, f"expected 96 pool rows, got {len(pool)}"
    assert len(groups) == 52, f"expected 52 hemisphere-neutral keys, got {len(groups)}"

    async with AsyncSessionLocal() as session:
        created_codes: list[str] = []
        for key, g in sorted(groups.items()):
            lats = set(g["lats"])
            if key in _L1_REUSE:
                continue  # grounds directly to the existing L1 concept
            code = f"ng:br:{_slug(key)}"
            existing = await crs.get_canonical_region_by_code(session, code)
            if existing is not None:
                continue
            if lats <= {"left", "right"}:
                policy = "lateralized"
            else:
                policy = "midline_unpaired"
            cn = next((c for c in g["cn"] if c), "")
            cn_core = _LATERAL_CN_PREFIX.sub("", cn).strip() or None
            await crs.create_canonical_region(
                session,
                CanonicalRegionCreate(
                    region_code=code,
                    canonical_name_en=_canonical_name_en(key),
                    canonical_name_cn=cn_core,
                    species="human",
                    granularity_domain="brain_region_anatomical",
                    granularity_level="clinical",
                    hemisphere_policy=policy,
                    status="active",
                    confidence=0.95,
                    description=f"L2 clinical region from the Macro96 96-pool: {key}.",
                    source_summary={
                        "macro96": {"pool": "Macro96", "key": key,
                                    "laterality_values": sorted(lats)},
                    },
                    created_by="br2_seed",
                ),
            )
            created_codes.append(code)
        print("created_l2_concepts:", len(created_codes))

        # ---- hierarchy: L2 -> L1 (and ventricles/CSF/WM -> L0 Brain) ----
        # Keys in _L1_REUSE have no new concept (they ARE the L1 concept).
        edges_created = 0
        for key, g in sorted(groups.items()):
            if key in _L1_REUSE:
                continue
            parent_code = _PARENT_MAP[key]
            code = f"ng:br:{_slug(key)}"
            child = await crs.get_canonical_region_by_code(session, code)
            parent = await crs.get_canonical_region_by_code(session, parent_code)
            if child is None or parent is None:
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
                    source="macro96_pool_mapping",
                    confidence=0.95,
                    provenance_json={
                        "pool": "Macro96",
                        "structure_key": key,
                        "source_atlas": "Macro96",
                        "note": "L2 clinical region part_of L1/L0 canonical system",
                    },
                    created_by="br2_seed",
                ),
            )
            edges_created += 1
        print("hierarchy_edges_created:", edges_created)

        # ---- grounding: all 96 rows -> canonical (96/96) ----
        grounded = 0
        for key, g in sorted(groups.items()):
            target_code = _L1_REUSE.get(key) or f"ng:br:{_slug(key)}"
            canonical = await crs.get_canonical_region_by_code(session, target_code)
            if canonical is None:
                print(f"[warn] missing canonical for {key} -> {target_code}")
                continue
            for en in g["en"]:
                row = (
                    await session.execute(
                        select(CandidateBrainRegion).where(
                            CandidateBrainRegion.source_atlas == "Macro96",
                            CandidateBrainRegion.en_name == en,
                        )
                    )
                ).scalar_one_or_none()
                if row is None:
                    print(f"[warn] missing candidate row: {en}")
                    continue
                if row.canonical_region_id == canonical.id:
                    grounded += 1
                    continue
                await crs.ground_candidate(
                    session,
                    candidate_id=row.id,
                    canonical_region_id=canonical.id,
                    match_type="exact",
                    confidence=0.95,
                    match_details={"rule": "macro96_pool_exact", "seed": "br2",
                                   "hemisphere_stripped_key": key},
                )
                grounded += 1
        print("grounded_rows:", grounded)

        await session.commit()
        integrity = await crs.check_canonical_brain_region_integrity(session)
        print("integrity_counts:", json.dumps(integrity["counts"], ensure_ascii=False))
        print("integrity_issues:", json.dumps(integrity["issues"], ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
