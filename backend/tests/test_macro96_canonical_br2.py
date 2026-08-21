"""BR2: Macro96 -> Canonical L2 (Clinical regions) tests.

Acceptance: all 96 Macro96 candidates traceable to a canonical concept;
left/right rows share one hemisphere-neutral concept; L2 part_of L1/L0
hierarchy holds; connection_region_alignment works without touching the
70,029 connection rows; integrity checker reports 96/96.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select, text

from app.database import AsyncSessionLocal
from app.models.candidate import CandidateBrainRegion
from app.models.canonical_region import CanonicalBrainRegion, ConnectionRegionAlignment
from app.schemas.canonical_region import CanonicalRegionCreate
from app.services import canonical_region_service as crs

TEST_PREFIX = "br2_test_"

pytestmark = pytest.mark.function_term_real


def _run(coro):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    return asyncio.run(coro)


@pytest.fixture()
def db():
    """Snapshot Macro96 anchor state before the test; restore it afterwards.

    Test groundings must be restored to their ORIGINAL canonical_region_id
    (not NULL) so seed mappings stay intact (96/96 acceptance).
    """

    async def _snapshot() -> list[tuple]:
        async with AsyncSessionLocal() as s:
            rows = (
                await s.execute(
                    text("SELECT id, canonical_region_id FROM candidate_brain_regions WHERE source_atlas='Macro96'")
                )
            ).all()
            return [(str(r[0]), str(r[1]) if r[1] else None) for r in rows]

    async def _restore(snapshot: list[tuple]) -> None:
        async with AsyncSessionLocal() as s:
            # test alignment rows (created by this suite)
            await s.execute(
                text(
                    "DELETE FROM connection_region_alignment WHERE "
                    "source_canonical_region_id IN "
                    "(SELECT id FROM canonical_brain_regions WHERE region_code LIKE 'ng:br:br2_test_%') "
                    "OR target_canonical_region_id IN "
                    "(SELECT id FROM canonical_brain_regions WHERE region_code LIKE 'ng:br:br2_test_%')"
                )
            )
            # restore original groundings unconditionally (moved-away anchors come back)
            for cid, original in snapshot:
                if original:
                    await s.execute(
                        text(
                            "UPDATE candidate_brain_regions SET canonical_region_id=:o, "
                            "alignment_status='aligned' WHERE id=:c"
                        ),
                        {"o": original, "c": cid},
                    )
            await s.execute(
                text(
                    "UPDATE candidate_brain_regions SET canonical_region_id=NULL, "
                    "alignment_status='not_aligned' WHERE canonical_region_id IN "
                    "(SELECT id FROM canonical_brain_regions WHERE region_code LIKE 'ng:br:br2_test_%')"
                )
            )
            # test edges + regions
            await s.execute(
                text(
                    "DELETE FROM canonical_region_hierarchy WHERE "
                    "child_region_id IN (SELECT id FROM canonical_brain_regions WHERE region_code LIKE 'ng:br:br2_test_%') "
                    "OR parent_region_id IN (SELECT id FROM canonical_brain_regions WHERE region_code LIKE 'ng:br:br2_test_%')"
                )
            )
            await s.execute(
                text("DELETE FROM canonical_brain_regions WHERE region_code LIKE 'ng:br:br2_test_%'")
            )
            await s.commit()

    snapshot = _run(_snapshot())
    yield
    _run(_restore(snapshot))


async def _mk(session, code: str, *, level: str = "clinical", policy: str = "lateralized",
              species: str = "human") -> CanonicalBrainRegion:
    return await crs.create_canonical_region(
        session,
        CanonicalRegionCreate(
            region_code=code,
            canonical_name_en=code.replace("ng:br:", ""),
            species=species,
            granularity_level=level,
            hemisphere_policy=policy,
            status="active",
            confidence=0.9,
            created_by="br2_test",
        ),
    )


async def _candidate(session, en_name: str) -> CandidateBrainRegion:
    return (
        await session.execute(
            select(CandidateBrainRegion).where(
                CandidateBrainRegion.source_atlas == "Macro96",
                CandidateBrainRegion.en_name == en_name,
            )
        )
    ).scalar_one()


# --------------------------------------------------------------------------- #
# 96/96 traceability + hemisphere neutrality
# --------------------------------------------------------------------------- #


def test_macro96_all_96_traceable(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            total, mapped = (
                await s.execute(
                    text(
                        "SELECT count(*), count(canonical_region_id) FROM candidate_brain_regions "
                        "WHERE source_atlas='Macro96'"
                    )
                )
            ).one()
            assert total == 96
            assert mapped == 96
    _run(_t())


def test_left_right_share_single_concept(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            left = await _candidate(s, "left hippocampus")
            right = await _candidate(s, "right hippocampus")
            assert left.canonical_region_id is not None
            assert left.canonical_region_id == right.canonical_region_id
            canonical = await s.get(CanonicalBrainRegion, left.canonical_region_id)
            assert canonical.canonical_name_en == "Hippocampus"
            assert canonical.granularity_level == "clinical"
            assert canonical.hemisphere_policy == "lateralized"
            # laterality survives on both anchors
            assert left.laterality == "left"
            assert right.laterality == "right"
    _run(_t())


def test_no_duplicate_concepts_for_paired_structures(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            # exactly 48 L2 clinical concepts (44 pairs + 5 midline + 3 vermal - reused L1 keys)
            count = int(
                (
                    await s.execute(
                        text(
                            "SELECT count(*) FROM canonical_brain_regions "
                            "WHERE granularity_level='clinical'"
                        )
                    )
                ).scalar_one()
            )
            assert count == 48
            # no two clinical concepts share the same canonical_name_en
            dup = int(
                (
                    await s.execute(
                        text(
                            "SELECT count(*) FROM (SELECT canonical_name_en FROM canonical_brain_regions "
                            "WHERE granularity_level='clinical' GROUP BY canonical_name_en HAVING count(*)>1) d"
                        )
                    )
                ).scalar_one()
            )
            assert dup == 0
    _run(_t())


def test_vermal_lobules_concepts(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            for name in ("cerebellar vermal lobules I-V", "cerebellar vermal lobules VI-VII"):
                cand = await _candidate(s, name)
                canonical = await s.get(CanonicalBrainRegion, cand.canonical_region_id)
                assert canonical.hemisphere_policy == "midline_unpaired"
                parents = await crs.get_parents(s, canonical.id)
                assert [p.region_code for p in parents] == ["ng:br:cerebellum"]
    _run(_t())


# --------------------------------------------------------------------------- #
# L2 -> L1/L0 hierarchy
# --------------------------------------------------------------------------- #


def test_l2_part_of_l1_hierarchy(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            checks = {
                "ng:br:superior_frontal": "ng:br:cerebrum",
                "ng:br:insula": "ng:br:cerebrum",
                "ng:br:hippocampus": "ng:br:cerebrum",
                "ng:br:thalamus_proper": "ng:br:diencephalon",
                "ng:br:3rd_ventricle": "ng:br:brain",
                "ng:br:white_matter": "ng:br:brain",
            }
            for code, parent_code in checks.items():
                region = await crs.get_canonical_region_by_code(s, code)
                assert region is not None, code
                parents = await crs.get_parents(s, region.id)
                assert [p.region_code for p in parents] == [parent_code], code
    _run(_t())


def test_ancestors_from_l2_to_l0(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            hippocampus = await crs.get_canonical_region_by_code(s, "ng:br:hippocampus")
            anc = await crs.get_ancestors(s, hippocampus.id)
            assert [x["region_code"] for x in anc] == ["ng:br:cerebrum", "ng:br:brain"]
            assert [x["depth"] for x in anc] == [1, 2]
    _run(_t())


def test_clinical_part_of_macro_allowed(db):
    from app.schemas.canonical_region import CanonicalRegionHierarchyCreate

    async def _t():
        async with AsyncSessionLocal() as s:
            child = await _mk(s, f"ng:br:{TEST_PREFIX}child", level="clinical")
            parent = await _mk(s, f"ng:br:{TEST_PREFIX}parent", level="macro")
            await s.flush()
            edge = await crs.add_part_of_edge(
                s,
                CanonicalRegionHierarchyCreate(
                    child_region_id=child.id,
                    parent_region_id=parent.id,
                    predicate="part_of",
                    status="active",
                    source="br2_test",
                    confidence=0.9,
                    created_by="br2_test",
                ),
            )
            assert edge.predicate == "part_of"
    _run(_t())


# --------------------------------------------------------------------------- #
# connection_region_alignment (BR2-6) — connection rows untouched
# --------------------------------------------------------------------------- #


def test_connection_alignment_record(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            connection_id = (
                await s.execute(
                    text(
                        "SELECT id FROM mirror_region_connections "
                        "WHERE source_atlas='Macro96' AND source_region_candidate_id IS NOT NULL "
                        "AND target_region_candidate_id IS NOT NULL LIMIT 1"
                    )
                )
            ).scalar_one()
            result = await crs.resolve_and_record_connection_alignment(s, connection_id)
            await s.commit()
            row = (
                await s.execute(
                    text(
                        "SELECT source_canonical_region_id, target_canonical_region_id, "
                        "mapping_type FROM connection_region_alignment WHERE connection_id=:c"
                    ),
                    {"c": str(connection_id)},
                )
            ).first()
            assert row is not None
            assert row[0] is not None and row[1] is not None  # both endpoints canonicalized
            assert row[2] == "exact"
            # the connection row itself is untouched (no identity columns changed)
            conn_count = int(
                (
                    await s.execute(text("SELECT count(*) FROM mirror_region_connections"))
                ).scalar_one()
            )
            assert conn_count == 70029
    _run(_t())


# --------------------------------------------------------------------------- #
# integrity + hemisphere conflict detection
# --------------------------------------------------------------------------- #


def test_integrity_clean_br2(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            result = await crs.check_canonical_brain_region_integrity(s)
            assert result["ok"] is True, result["issues"]
            counts = result["counts"]
            assert counts["macro96_total"] == 96
            assert counts["macro96_mapped"] == 96
            assert counts["l2_clinical_count"] == 48
            assert counts["isolated_node_count"] == 0
    _run(_t())


def test_hemisphere_conflict_detected(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            # a midline_unpaired concept anchored by a left-lateralized candidate
            concept = await _mk(s, f"ng:br:{TEST_PREFIX}midline", policy="midline_unpaired")
            await s.flush()
            cand = await _candidate(s, "left amygdala")
            await crs.ground_candidate(
                s, candidate_id=cand.id, canonical_region_id=concept.id, match_type="exact"
            )
            await s.commit()
            result = await crs.check_canonical_brain_region_integrity(s)
            codes = [i["code"] for i in result["issues"]]
            assert "HEMISPHERE_CONFLICT" in codes
            assert result["ok"] is False
    _run(_t())


def test_research_level_assignable(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            r = await _mk(s, f"ng:br:{TEST_PREFIX}research", level="research")
            assert r.granularity_level == "research"
    _run(_t())
