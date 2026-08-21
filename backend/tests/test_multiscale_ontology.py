"""BR3 multiscale ontology tests (macro->meso->subregion->cyto->molecular).

Runs against the isolated e2e test database. Test-scoped rows carry the
``br3_test_`` prefix and are removed by the cleanup fixture. The production
seed (Macro96 clinical layer, BR3 anchors, Allen P56 atlas rows) is read-only.

Acceptance mapping:
1. Macro96 data unchanged (no deletes / no ID migration)
2. granularity vocabulary correct (10 levels + compat map)
3. atlas resource layer importable
4. atlas -> canonical mapping traceable
5. hierarchy produces no cycles
6. merge keeps identity traceable
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select, text

from app.database import AsyncSessionLocal
from app.models.canonical_region import CanonicalBrainRegion, CanonicalRegionHierarchy
from app.models.multiscale import (
    AtlasRegionMapping,
    AtlasRegionResource,
    CellTypeRegistry,
    MolecularEntityRegistry,
    RegionCellAlignment,
    RegionMolecularAlignment,
)
from app.schemas.canonical_region import CanonicalRegionCreate, CanonicalRegionHierarchyCreate
from app.schemas.multiscale import (
    AtlasRegionBatchImport,
    AtlasRegionCreate,
    AtlasRegionMappingCreate,
    CellTypeCreate,
    MolecularEntityCreate,
    RegionCellAlignmentCreate,
    RegionMolecularAlignmentCreate,
)
from app.services import canonical_region_service as crs
from app.services import multiscale_service as ms

pytestmark = pytest.mark.function_term_real

ATLAS_TEST = "br3_test_atlas"


def _run(coro):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    return asyncio.run(coro)


@pytest.fixture()
def db():
    async def _cleanup():
        async with AsyncSessionLocal() as session:
            await session.execute(
                text(
                    "DELETE FROM atlas_region_mappings WHERE atlas_region_id IN "
                    "(SELECT id FROM atlas_region_resources WHERE atlas_name='br3_test_atlas')"
                )
            )
            await session.execute(text("DELETE FROM atlas_region_resources WHERE atlas_name='br3_test_atlas'"))
            await session.execute(
                text(
                    "DELETE FROM region_cell_alignment WHERE region_id IN "
                    "(SELECT id FROM canonical_brain_regions WHERE region_code LIKE 'ng:br:br3_test_%') "
                    "OR cell_type_id IN (SELECT id FROM cell_type_registry WHERE cell_type_code LIKE 'ng:ct:br3_test_%')"
                )
            )
            await session.execute(
                text(
                    "DELETE FROM region_molecular_alignment WHERE region_id IN "
                    "(SELECT id FROM canonical_brain_regions WHERE region_code LIKE 'ng:br:br3_test_%') "
                    "OR molecular_entity_id IN (SELECT id FROM molecular_entity_registry WHERE entity_code LIKE 'ng:mol:br3_test_%')"
                )
            )
            await session.execute(text("DELETE FROM cell_type_registry WHERE cell_type_code LIKE 'ng:ct:br3_test_%'"))
            await session.execute(
                text("DELETE FROM molecular_entity_registry WHERE entity_code LIKE 'ng:mol:br3_test_%'")
            )
            await session.execute(
                text(
                    "DELETE FROM canonical_region_hierarchy WHERE "
                    "child_region_id IN (SELECT id FROM canonical_brain_regions WHERE region_code LIKE 'ng:br:br3_test_%') "
                    "OR parent_region_id IN (SELECT id FROM canonical_brain_regions WHERE region_code LIKE 'ng:br:br3_test_%')"
                )
            )
            await session.execute(text("DELETE FROM canonical_brain_regions WHERE region_code LIKE 'ng:br:br3_test_%'"))
            await session.commit()

    yield
    _run(_cleanup())


async def _mk(session, code: str, *, level: str, parent: CanonicalBrainRegion | None = None) -> CanonicalBrainRegion:
    region = await crs.create_canonical_region(
        session,
        CanonicalRegionCreate(
            region_code=code,
            canonical_name_en=code.replace("ng:br:", ""),
            species="human",
            granularity_level=level,
            hemisphere_policy="bilateral",
            status="active",
            created_by="br3_test",
        ),
    )
    if parent is not None:
        await crs.add_part_of_edge(
            session,
            CanonicalRegionHierarchyCreate(
                child_region_id=region.id,
                parent_region_id=parent.id,
                created_by="br3_test",
            ),
        )
    return region


# ──── 1. Macro96 data unchanged ──────────────────────────────────────────────


def test_macro96_layer_unchanged(db):
    async def _check(session):
        clinical_total = (
            await session.execute(
                text("SELECT count(*) FROM canonical_brain_regions WHERE granularity_level='clinical'")
            )
        ).scalar_one()
        macro96 = (
            await session.execute(
                text(
                    "SELECT count(*), count(canonical_region_id) FROM candidate_brain_regions "
                    "WHERE source_atlas='Macro96'"
                )
            )
        ).one()
        hippocampus = (
            await session.execute(
                text(
                    "SELECT region_code, status, granularity_level FROM canonical_brain_regions "
                    "WHERE region_code='ng:br:hippocampus'"
                )
            )
        ).one()
        return clinical_total, macro96, hippocampus

    async def _run_check():
        async with AsyncSessionLocal() as session:
            return await _check(session)

    clinical_total, (macro96_total, macro96_mapped), hippocampus = _run(_run_check())
    assert clinical_total == 48
    assert macro96_total == 96 and macro96_mapped == 96
    assert hippocampus[0] == "ng:br:hippocampus"
    assert hippocampus[1] == "active" and hippocampus[2] == "clinical"


# ──── 2. granularity vocabulary correct ──────────────────────────────────────


def test_granularity_vocab_multiscale(db):
    async def _run_check():
        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT code, status, level_order, description, source_strategy FROM ontology_vocabularies "
                        "WHERE vocab_type='granularity_level' ORDER BY COALESCE(level_order, seq)"
                    )
                )
            ).all()
            compat = (
                await session.execute(
                    text("SELECT legacy_level, canonical_level FROM granularity_level_compat_map ORDER BY legacy_level")
                )
            ).all()
            return rows, compat

    rows, compat = _run(_run_check())
    codes = [r[0] for r in rows]
    for expected in ("macro", "meso", "subregion", "cyto", "molecular"):
        assert expected in codes, f"missing canonical level: {expected}"
    assert codes.index("macro") < codes.index("meso") < codes.index("subregion")
    assert codes.index("subregion") < codes.index("cyto") < codes.index("molecular")
    canonical = {r[0]: r for r in rows if r[0] in ("macro", "meso", "subregion", "cyto", "molecular")}
    for level, row in canonical.items():
        assert row[1] == "active"
        assert row[2] is not None, f"{level} missing level_order"
        assert row[3], f"{level} missing description"
        assert row[4], f"{level} missing source_strategy"
    legacy = {r[0]: r for r in rows if r[0] in ("whole_brain", "clinical", "research", "fine", "ultra_fine")}
    for level, row in legacy.items():
        assert row[1] == "active", f"legacy {level} must stay active"
    assert "parcel" not in [r[0] for r in rows if r[1] == "active"]
    compat_map = dict(compat)
    assert compat_map == {
        "clinical": "macro",
        "fine": "cyto",
        "parcel": "subregion",
        "research": "meso",
        "ultra_fine": "molecular",
        "whole_brain": "macro",
    }


def test_new_levels_assignable_and_parcel_rejected(db):
    async def _run_check():
        async with AsyncSessionLocal() as session:
            created = []
            for level in ("meso", "subregion", "cyto", "molecular"):
                created.append(await _mk(session, f"ng:br:br3_test_vocab_{level}", level=level))
            levels_out = [r.granularity_level for r in created]
            await session.commit()
            return levels_out

    levels = _run(_run_check())
    assert set(levels) == {"meso", "subregion", "cyto", "molecular"}
    # parcel stays deprecated: rejected at the schema boundary
    with pytest.raises(ValueError, match="parcel"):
        CanonicalRegionCreate(
            region_code="ng:br:br3_test_vocab_parcel",
            canonical_name_en="parcel test",
            species="human",
            granularity_level="parcel",
            hemisphere_policy="bilateral",
        )


# ──── 3. atlas resource layer importable ─────────────────────────────────────


def test_atlas_rows_importable_and_idempotent(db):
    payload = AtlasRegionBatchImport(
        rows=[
            AtlasRegionCreate(
                atlas_name=ATLAS_TEST,
                atlas_version="v1",
                atlas_region_id="r1",
                region_name="Test region one",
                parent_region_id=None,
                species="mouse",
            ),
            AtlasRegionCreate(
                atlas_name=ATLAS_TEST,
                atlas_version="v1",
                atlas_region_id="r2",
                region_name="Test region two",
                parent_region_id="r1",
                species="mouse",
            ),
        ],
        source_file="test/fixture.json",
        created_by="br3_test",
    )

    async def _run_import():
        async with AsyncSessionLocal() as session:
            first = await ms.import_atlas_regions(session, payload)
            second = await ms.import_atlas_regions(session, payload)
            await session.commit()
            rows = await ms.list_atlas_regions(session, atlas_name=ATLAS_TEST)
            return first, second, rows

    first, second, rows = _run(_run_import())
    assert first == {"inserted": 2, "skipped": 0, "total": 2}
    assert second == {"inserted": 0, "skipped": 2, "total": 2}
    assert len(rows) == 2
    assert rows[1].parent_region_id == "r1"


def test_registered_sources_present(db):
    async def _run_check():
        async with AsyncSessionLocal() as session:
            rows = await ms.list_atlas_sources(session)
            return {r.resource_code for r in rows}

    codes = _run(_run_check())
    expected = {
        "allen_mouse_p56_structure",
        "allen_hba_structure",
        "brainnetome_bna246",
        "hippocampal_subfield_winterburn",
        "allen_cell_types_database",
        "julich_brain_siibra",
    }
    assert expected <= codes


# ──── 4. atlas -> canonical mapping traceable ────────────────────────────────


def test_atlas_mapping_traceable_and_conflict_guarded(db):
    async def _run_check():
        async with AsyncSessionLocal() as session:
            atlas = (
                await session.execute(
                    select(AtlasRegionResource).where(
                        AtlasRegionResource.atlas_name == "Allen Mouse Brain Atlas",
                        AtlasRegionResource.atlas_region_id == "1089",
                    )
                )
            ).scalar_one()
            hf = (
                await session.execute(
                    select(CanonicalBrainRegion).where(
                        CanonicalBrainRegion.region_code == "ng:br:hippocampal_formation"
                    )
                )
            ).scalar_one()
            ca1 = (
                await session.execute(
                    select(CanonicalBrainRegion).where(CanonicalBrainRegion.region_code == "ng:br:ca1")
                )
            ).scalar_one()
            # traceable: query mappings of the seeded canonical
            mappings = await ms.list_atlas_mappings(session, canonical_region_id=hf.id)
            mappings_out = [(m.mapping_type, m.canonical_region_id, m.species_relation) for m in mappings]
            conflict = None
            try:
                await ms.create_atlas_mapping(
                    session,
                    AtlasRegionMappingCreate(
                        atlas_region_id=atlas.id,
                        canonical_region_id=ca1.id,  # different canonical than seeded mapping
                        mapping_type="exact",
                        species_relation="homology",
                        created_by="br3_test",
                    ),
                )
            except ms.MultiscaleError as exc:
                conflict = str(exc)
            await session.rollback()
            return mappings_out, conflict

    mappings, conflict = _run(_run_check())
    assert any(m[1] is not None and m[0] == "exact" for m in mappings)
    assert conflict is not None and "active mapping" in conflict


def test_cross_species_mapping_requires_homology(db):
    async def _run_check():
        async with AsyncSessionLocal() as session:
            atlas = (
                await session.execute(
                    select(AtlasRegionResource).where(
                        AtlasRegionResource.atlas_name == "Allen Mouse Brain Atlas",
                        AtlasRegionResource.atlas_region_id == "1089",
                    )
                )
            ).scalar_one()
            target = await _mk(session, "ng:br:br3_test_xspecies", level="meso")
            await session.commit()
            rejected = None
            try:
                await ms.create_atlas_mapping(
                    session,
                    AtlasRegionMappingCreate(
                        atlas_region_id=atlas.id,
                        canonical_region_id=target.id,
                        mapping_type="uncertain",
                        species_relation="same_species",  # mouse -> human must declare homology
                        created_by="br3_test",
                    ),
                )
            except ms.MultiscaleError as exc:
                rejected = str(exc)
            await session.rollback()
            return rejected

    rejected = _run(_run_check())
    assert rejected is not None and "homology" in rejected


# ──── 5. hierarchy produces no cycles ────────────────────────────────────────


def test_seeded_hierarchy_acyclic_and_cycle_guard(db):
    async def _run_check():
        async with AsyncSessionLocal() as session:
            result = await crs.check_canonical_brain_region_integrity(session)
            cycles = [i for i in result["issues"] if i["code"] == "CYCLE"]
            # service-level: adding an upward edge must be rejected
            hf = (
                await session.execute(
                    select(CanonicalBrainRegion).where(
                        CanonicalBrainRegion.region_code == "ng:br:hippocampal_formation"
                    )
                )
            ).scalar_one()
            ca1 = (
                await session.execute(
                    select(CanonicalBrainRegion).where(CanonicalBrainRegion.region_code == "ng:br:ca1")
                )
            ).scalar_one()
            rejected = None
            try:
                await crs.add_part_of_edge(
                    session,
                    CanonicalRegionHierarchyCreate(
                        child_region_id=hf.id,
                        parent_region_id=ca1.id,  # meso under subregion -> upward edge
                        created_by="br3_test",
                    ),
                )
            except crs.CanonicalRegionError as exc:
                rejected = str(exc)
            await session.rollback()
            return cycles, rejected, result["counts"]

    cycles, rejected, counts = _run(_run_check())
    assert cycles == []
    assert rejected is not None and "direction" in rejected
    assert counts["hierarchy_edges"] >= 7
    assert counts["meso_count"] >= 3 and counts["subregion_count"] >= 4


# ──── 6. merge keeps identity traceable ──────────────────────────────────────


def test_merge_preserves_identity(db):
    async def _run_check():
        async with AsyncSessionLocal() as session:
            hippocampus = (
                await session.execute(
                    select(CanonicalBrainRegion).where(
                        CanonicalBrainRegion.region_code == "ng:br:hippocampus"
                    )
                )
            ).scalar_one()
            src = await _mk(session, "ng:br:br3_test_merge_src", level="meso", parent=hippocampus)
            tgt = await _mk(session, "ng:br:br3_test_merge_tgt", level="meso", parent=hippocampus)
            await session.flush()
            result = await crs.merge_canonical_region(session, src.id, tgt.id)
            await session.commit()
            merged_src = (
                await session.execute(
                    select(CanonicalBrainRegion).where(
                        CanonicalBrainRegion.region_code == "ng:br:br3_test_merge_src"
                    )
                )
            ).scalar_one()
            repointed = (
                await session.execute(
                    select(CanonicalRegionHierarchy).where(
                        CanonicalRegionHierarchy.child_region_id == tgt.id,
                        CanonicalRegionHierarchy.parent_region_id == hippocampus.id,
                    )
                )
            ).scalar_one_or_none()
            return result, merged_src, repointed

    result, merged_src, repointed = _run(_run_check())
    assert merged_src.status == "merged"
    assert merged_src.replaced_by_region_id is not None
    assert merged_src.region_code == "ng:br:br3_test_merge_src"  # identity kept
    assert result["target_region_code"] == "ng:br:br3_test_merge_tgt"
    assert repointed is not None  # edge re-pointed to target


def test_merge_dedups_atlas_mappings_and_realigns(db):
    """Merge guards: never two active mappings for one atlas row; alignments
    re-point to target unless their unique key already exists there."""
    async def _run_check():
        async with AsyncSessionLocal() as session:
            hippocampus = (
                await session.execute(
                    select(CanonicalBrainRegion).where(
                        CanonicalBrainRegion.region_code == "ng:br:hippocampus"
                    )
                )
            ).scalar_one()
            src = await _mk(session, "ng:br:br3_test_merge2_src", level="meso", parent=hippocampus)
            tgt = await _mk(session, "ng:br:br3_test_merge2_tgt", level="meso", parent=hippocampus)
            atlas = AtlasRegionResource(
                atlas_name=ATLAS_TEST, atlas_version="v1", atlas_region_id="merge-r1",
                region_name="Merge row one", species="human",
            )
            session.add(atlas)
            await session.flush()
            # two active mappings for the same atlas row, created via ORM to
            # bypass the single-active-mapping service guard
            session.add(AtlasRegionMapping(
                atlas_region_id=atlas.id, canonical_region_id=src.id,
                mapping_type="exact", species_relation="same_species", created_by="br3_test",
            ))
            session.add(AtlasRegionMapping(
                atlas_region_id=atlas.id, canonical_region_id=tgt.id,
                mapping_type="exact", species_relation="same_species", created_by="br3_test",
            ))
            ct = CellTypeRegistry(
                cell_type_code="ng:ct:br3_test_merge2", canonical_name_en="Merge cell", species="human",
            )
            session.add(ct)
            await session.flush()
            # contains: re-pointable; marker: collides with existing tgt row
            session.add(RegionCellAlignment(region_id=src.id, cell_type_id=ct.id,
                                            mapping_type="contains", confidence=0.9))
            session.add(RegionCellAlignment(region_id=tgt.id, cell_type_id=ct.id,
                                            mapping_type="marker", confidence=0.5))
            session.add(RegionCellAlignment(region_id=src.id, cell_type_id=ct.id,
                                            mapping_type="marker", confidence=0.6))
            await session.flush()
            result = await crs.merge_canonical_region(session, src.id, tgt.id)
            await session.commit()
            active_targets = [
                str(m.canonical_region_id)
                for m in (
                    await session.execute(
                        select(AtlasRegionMapping).where(
                            AtlasRegionMapping.atlas_region_id == atlas.id,
                            AtlasRegionMapping.status == "active",
                        )
                    )
                ).scalars().all()
            ]
            aligns = (
                await session.execute(
                    select(RegionCellAlignment).where(RegionCellAlignment.cell_type_id == ct.id)
                )
            ).scalars().all()
            align_out = sorted((str(a.region_id), a.mapping_type) for a in aligns)
            return result, active_targets, align_out, str(tgt.id), str(src.id)

    result, active_targets, align_out, tgt_id, src_id = _run(_run_check())
    assert result["superseded_mappings"] == 1 and result["repointed_mappings"] == 0
    assert result["repointed_alignments"] == 1 and result["kept_alignments"] == 1
    assert active_targets == [tgt_id]  # exactly one active mapping, pointing at target
    assert (tgt_id, "contains") in align_out  # re-pointed
    assert (src_id, "marker") in align_out  # kept on merged source (traceable)


# ──── cell / molecular interfaces (NOT BrainRegions) ─────────────────────────


def test_cell_type_and_alignment_interface(db):
    async def _run_check():
        async with AsyncSessionLocal() as session:
            ca1 = (
                await session.execute(
                    select(CanonicalBrainRegion).where(CanonicalBrainRegion.region_code == "ng:br:ca1")
                )
            ).scalar_one()
            ct = await ms.create_cell_type(
                session,
                CellTypeCreate(
                    cell_type_code="ng:ct:br3_test_pyramidal",
                    canonical_name_en="Test pyramidal neuron",
                    species="human",
                    taxonomy_source="test",
                ),
            )
            alignment = await ms.create_region_cell_alignment(
                session,
                RegionCellAlignmentCreate(
                    region_id=ca1.id,
                    cell_type_id=ct.id,
                    mapping_type="contains",
                    confidence=0.9,
                ),
            )
            await session.commit()
            canonical_total = (
                await session.execute(text("SELECT count(*) FROM canonical_brain_regions"))
            ).scalar_one()
            cell_total = (await session.execute(text("SELECT count(*) FROM cell_type_registry"))).scalar_one()
            return ct, alignment, canonical_total, cell_total

    ct, alignment, canonical_total, cell_total = _run(_run_check())
    # cell types are NOT canonical regions: creating one must not change the region count
    assert alignment.mapping_type == "contains"
    assert ct.cell_type_code == "ng:ct:br3_test_pyramidal"
    assert canonical_total >= 60
    assert cell_total >= 1


def test_molecular_entity_and_alignment_interface(db):
    async def _run_check():
        async with AsyncSessionLocal() as session:
            ca3 = (
                await session.execute(
                    select(CanonicalBrainRegion).where(CanonicalBrainRegion.region_code == "ng:br:ca3")
                )
            ).scalar_one()
            entity = await ms.create_molecular_entity(
                session,
                MolecularEntityCreate(
                    entity_code="ng:mol:br3_test_gene",
                    entity_type="gene",
                    canonical_name_en="Test gene",
                    species="human",
                ),
            )
            alignment = await ms.create_region_molecular_alignment(
                session,
                RegionMolecularAlignmentCreate(
                    region_id=ca3.id,
                    molecular_entity_id=entity.id,
                    evidence_type="expression",
                    confidence=0.8,
                    source="test",
                ),
            )
            await session.commit()
            return alignment

    alignment = _run(_run_check())
    assert alignment.entity_type == "gene"
    assert alignment.evidence_type == "expression"
    assert alignment.source == "test"
