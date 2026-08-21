"""BR1: Canonical BrainRegion L0/L1 core tests (25 acceptance points).

Runs against the isolated e2e test database. Test-scoped rows carry the
``br1_test_`` prefix and are removed by the cleanup fixture; the production
seed (ng:br:brain/cerebrum/diencephalon/brain_stem/cerebellum) is only read.

Acceptance mapping: 1 create, 2 stable region_code, 3 species explicit,
4 hemisphere policy, 5 candidate canonical FK, 6 laterality preserved,
7 part_of create, 8 self-loop, 9 duplicate edge, 10 cycle, 11 L1->L0 allowed,
12 L0->L1 rejected, 13 ancestor query, 14 descendant query (3-level),
15 exact mapping, 16 ambiguous mapping no FK, 17 cross-species rejected,
18 Allen_HBA not mouse, 19 legacy canonical_id not authoritative,
20 integrity clean, 21 connection readiness, 22 circuit readiness,
23/24 P1 + O1.2 regression (full suite run), 25 full regression (run).
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select, text

from app.database import AsyncSessionLocal
from app.models.candidate import CandidateBrainRegion
from app.models.canonical_region import CanonicalBrainRegion, CanonicalRegionHierarchy
from app.models.ontology import OntologyAlignmentCandidate, OntologyTerm
from app.schemas.canonical_region import (
    CanonicalRegionCreate,
    CanonicalRegionHierarchyCreate,
)
from app.services import canonical_region_service as crs
from app.services.paper_search_multi import _resolve_expected_species

TEST_PREFIX = "br1_test_"

pytestmark = pytest.mark.function_term_real


def _run(coro):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    return asyncio.run(coro)


@pytest.fixture()
def db():
    """Snapshot Macro96 anchor state; restore it afterwards (BR2: original
    groundings must survive test cleanup so 96/96 stays intact)."""

    async def _snapshot() -> list[tuple]:
        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    text("SELECT id, canonical_region_id FROM candidate_brain_regions WHERE source_atlas='Macro96'")
                )
            ).all()
            return [(str(r[0]), str(r[1]) if r[1] else None) for r in rows]

    async def _cleanup(snapshot: list[tuple]):
        async with AsyncSessionLocal() as session:
            # test alignment candidates pointing at ng:br region codes
            await session.execute(
                text(
                    "DELETE FROM ontology_alignment_candidates "
                    "WHERE external_system='ng:br' AND external_iri LIKE 'ng:br:br1_test_%'"
                )
            )
            # restore original groundings unconditionally (moved-away anchors come back)
            for cid, original in snapshot:
                if original:
                    await session.execute(
                        text(
                            "UPDATE candidate_brain_regions SET canonical_region_id=:o, "
                            "alignment_status='aligned' WHERE id=:c"
                        ),
                        {"o": original, "c": cid},
                    )
            await session.execute(
                text(
                    "UPDATE candidate_brain_regions SET canonical_region_id = NULL, "
                    "alignment_status = 'not_aligned' "
                    "WHERE canonical_region_id IN "
                    "(SELECT id FROM canonical_brain_regions WHERE region_code LIKE 'ng:br:br1_test_%')"
                )
            )
            # test hierarchy edges
            await session.execute(
                text(
                    "DELETE FROM canonical_region_hierarchy WHERE "
                    "child_region_id IN (SELECT id FROM canonical_brain_regions WHERE region_code LIKE 'ng:br:br1_test_%') "
                    "OR parent_region_id IN (SELECT id FROM canonical_brain_regions WHERE region_code LIKE 'ng:br:br1_test_%')"
                )
            )
            # test regions themselves
            await session.execute(
                text("DELETE FROM canonical_brain_regions WHERE region_code LIKE 'ng:br:br1_test_%'")
            )
            await session.commit()

    snapshot = _run(_snapshot())
    yield
    _run(_cleanup(snapshot))


async def _mk(session, code: str, *, level: str = "macro", policy: str = "bilateral",
              species: str = "human", status: str = "active") -> CanonicalBrainRegion:
    return await crs.create_canonical_region(
        session,
        CanonicalRegionCreate(
            region_code=code,
            canonical_name_en=code.replace("ng:br:", ""),
            canonical_name_cn=None,
            species=species,
            granularity_level=level,
            hemisphere_policy=policy,
            status=status,
            confidence=0.9,
            created_by="br1_test",
        ),
    )


async def _edge(session, child: CanonicalBrainRegion, parent: CanonicalBrainRegion,
                source: str = "test") -> CanonicalRegionHierarchy:
    return await crs.add_part_of_edge(
        session,
        CanonicalRegionHierarchyCreate(
            child_region_id=child.id,
            parent_region_id=parent.id,
            predicate="part_of",
            status="active",
            source=source,
            confidence=0.9,
            created_by="br1_test",
        ),
    )


# --------------------------------------------------------------------------- #
# 1-4: canonical concept basics
# --------------------------------------------------------------------------- #


def test_create_canonical_region(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            r = await _mk(s, f"ng:br:{TEST_PREFIX}hippocampus", level="macro", policy="lateralized")
            assert r.region_code == f"ng:br:{TEST_PREFIX}hippocampus"
            assert r.species == "human"
            assert r.granularity_level == "macro"
            assert r.hemisphere_policy == "lateralized"
            assert r.status == "active"
    _run(_t())


def test_region_code_stable_identity(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            r1 = await _mk(s, f"ng:br:{TEST_PREFIX}stable")
            await s.flush()
            # same code -> rejected (schema and service both enforce)
            with pytest.raises(crs.CanonicalRegionError, match="already exists"):
                await crs.create_canonical_region(
                    s,
                    CanonicalRegionCreate(
                        region_code=f"ng:br:{TEST_PREFIX}stable",
                        canonical_name_en="renamed display",
                        granularity_level="macro",
                        hemisphere_policy="bilateral",
                    ),
                )
            # code pattern enforced at the schema layer
            with pytest.raises(Exception, match="ng:br"):
                await crs.create_canonical_region(
                    s,
                    CanonicalRegionCreate(
                        region_code="not_a_region_code",
                        canonical_name_en="x",
                        granularity_level="macro",
                        hemisphere_policy="bilateral",
                    ),
                )
    _run(_t())


def test_species_explicit(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            r = await _mk(s, f"ng:br:{TEST_PREFIX}sp", species="mouse")
            assert r.species == "mouse"
            # schema layer rejects invalid species before the service runs
            with pytest.raises(Exception, match="species"):
                await _mk(s, f"ng:br:{TEST_PREFIX}sp2", species="dolphin")
    _run(_t())


def test_hemisphere_policy(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            for policy in ("bilateral", "lateralized", "midline_unpaired"):
                await _mk(s, f"ng:br:{TEST_PREFIX}hp_{policy}", policy=policy)
            with pytest.raises(Exception, match="hemisphere_policy"):
                await _mk(s, f"ng:br:{TEST_PREFIX}hp_bad", policy="sometimes")
    _run(_t())


# --------------------------------------------------------------------------- #
# 5-6: candidate grounding
# --------------------------------------------------------------------------- #


def test_ground_candidate_fk_and_laterality_preserved(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            canonical = await _mk(s, f"ng:br:{TEST_PREFIX}anchor", level="macro")
            await s.flush()
            candidate = (
                await s.execute(
                    select(CandidateBrainRegion).where(
                        CandidateBrainRegion.source_atlas == "Macro96",
                        CandidateBrainRegion.en_name == "left accumbens area",
                    )
                )
            ).scalar_one()
            result = await crs.ground_candidate(
                s,
                candidate_id=candidate.id,
                canonical_region_id=canonical.id,
                match_type="exact",
                confidence=0.95,
            )
            assert result["match_type"] == "exact"
            await s.flush()
            reloaded = await s.get(CandidateBrainRegion, candidate.id)
            assert reloaded.canonical_region_id == canonical.id
            assert reloaded.alignment_status == "aligned"
            # 6: laterality survives canonicalization (never dropped)
            assert reloaded.laterality == "left"
            # resolve round-trip
            resolved = await crs.resolve_candidate_to_canonical(s, candidate.id)
            assert resolved is not None and resolved.id == canonical.id
    _run(_t())


def test_ambiguous_mapping_does_not_write_fk(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            canonical = await _mk(s, f"ng:br:{TEST_PREFIX}ambig")
            await s.flush()
            # Allen candidates are not grounded in BR1/BR2 — good ambiguous subjects
            candidate = (
                await s.execute(
                    select(CandidateBrainRegion).where(
                        CandidateBrainRegion.source_atlas == "Allen_HBA_2012",
                        CandidateBrainRegion.canonical_region_id.is_(None),
                    )
                )
            ).scalars().first()
            # uncertain/broader/narrower never writes the FK
            for match_type in ("uncertain", "narrower"):
                try:
                    await crs.ground_candidate(
                        s, candidate_id=candidate.id,
                        canonical_region_id=canonical.id, match_type=match_type,
                    )
                    raise AssertionError(f"{match_type} must not write FK")
                except crs.CanonicalRegionError as exc:
                    assert "does not write the FK" in str(exc)
            # alignment candidate flow instead
            row = await crs.create_alignment_candidate(
                s, candidate_id=candidate.id,
                canonical_region_id=canonical.id, match_type="uncertain", confidence=0.4,
            )
            assert row.status == "pending"
            assert row.external_iri == canonical.region_code
            assert row.match_type == "uncertain"
            await s.flush()
            reloaded = await s.get(CandidateBrainRegion, candidate.id)
            assert reloaded.canonical_region_id is None
    _run(_t())


def test_cross_species_mapping_rejected(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            canonical = await _mk(s, f"ng:br:{TEST_PREFIX}mouse_region", species="mouse")
            await s.flush()
            candidate = (
                await s.execute(
                    select(CandidateBrainRegion).where(
                        CandidateBrainRegion.source_atlas == "Macro96",
                        CandidateBrainRegion.en_name == "left accumbens area",
                    )
                )
            ).scalar_one()
            # candidate's resource is human -> mouse canonical must be rejected
            try:
                await crs.ground_candidate(
                    s, candidate_id=candidate.id,
                    canonical_region_id=canonical.id, match_type="exact",
                )
                raise AssertionError("cross-species mapping must be rejected")
            except crs.CanonicalRegionError as exc:
                assert "cross-species" in str(exc)
    _run(_t())


# --------------------------------------------------------------------------- #
# 7-12: part_of constraints
# --------------------------------------------------------------------------- #


def test_part_of_l1_to_l0_allowed(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            l0 = await _mk(s, f"ng:br:{TEST_PREFIX}root", level="whole_brain")
            l1 = await _mk(s, f"ng:br:{TEST_PREFIX}child", level="macro")
            await s.flush()
            edge = await _edge(s, l1, l0)
            assert edge.predicate == "part_of"
            parents = await crs.get_parents(s, l1.id)
            assert [p.id for p in parents] == [l0.id]
    _run(_t())


def test_self_loop_rejected(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            r = await _mk(s, f"ng:br:{TEST_PREFIX}self")
            await s.flush()
            try:
                await _edge(s, r, r)
                raise AssertionError("self-loop must be rejected")
            except crs.CanonicalRegionError as exc:
                assert "self-loop" in str(exc)
    _run(_t())


def test_duplicate_edge_rejected(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            l0 = await _mk(s, f"ng:br:{TEST_PREFIX}dup_root", level="whole_brain")
            l1 = await _mk(s, f"ng:br:{TEST_PREFIX}dup_child", level="macro")
            await s.flush()
            await _edge(s, l1, l0)
            try:
                await _edge(s, l1, l0)
                raise AssertionError("duplicate edge must be rejected")
            except crs.CanonicalRegionError as exc:
                assert "duplicate" in str(exc)
    _run(_t())


def test_cycle_rejected(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            # With strict level ordering (child finer than parent), no cycle can
            # ever form through the service — but raw inserts bypass the guard,
            # so the integrity checker must still detect cycles.
            ids = []
            for name in ("cyc_a", "cyc_b", "cyc_c"):
                r = await _mk(s, f"ng:br:{TEST_PREFIX}{name}", level="macro")
                await s.flush()
                ids.append(str(r.id))
            await s.execute(
                text(
                    "INSERT INTO canonical_region_hierarchy (child_region_id, parent_region_id, predicate, status, created_by) VALUES "
                    "(:a, :b, 'part_of', 'active', 'br1_test'), "
                    "(:b, :c, 'part_of', 'active', 'br1_test'), "
                    "(:c, :a, 'part_of', 'active', 'br1_test')"
                ),
                {"a": ids[0], "b": ids[1], "c": ids[2]},
            )
            await s.commit()
            result = await crs.check_canonical_brain_region_integrity(s)
            codes = [i["code"] for i in result["issues"]]
            assert "CYCLE" in codes
            assert result["ok"] is False
    _run(_t())


def test_l0_part_of_l1_rejected(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            l0 = await _mk(s, f"ng:br:{TEST_PREFIX}inv_root", level="whole_brain")
            l1 = await _mk(s, f"ng:br:{TEST_PREFIX}inv_child", level="macro")
            await s.flush()
            try:
                await _edge(s, l0, l1)  # L0 part_of L1 — invalid direction
                raise AssertionError("L0 -> L1 must be rejected")
            except crs.CanonicalRegionError as exc:
                assert "level direction" in str(exc)
    _run(_t())


# --------------------------------------------------------------------------- #
# 13-14: traversal (depth-agnostic CTE)
# --------------------------------------------------------------------------- #


def test_ancestor_and_descendant_queries(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            a = await _mk(s, f"ng:br:{TEST_PREFIX}tr_root", level="whole_brain")
            b = await _mk(s, f"ng:br:{TEST_PREFIX}tr_mid", level="macro")
            c = await _mk(s, f"ng:br:{TEST_PREFIX}tr_leaf", level="research")
            await s.flush()
            await _edge(s, b, a)
            await _edge(s, c, b)
            anc = await crs.get_ancestors(s, c.id)
            assert [x["region_code"] for x in anc] == [b.region_code, a.region_code]
            assert [x["depth"] for x in anc] == [1, 2]
            desc = await crs.get_descendants(s, a.id)
            assert [x["region_code"] for x in desc] == [b.region_code, c.region_code]
            assert [x["depth"] for x in desc] == [1, 2]
            children = await crs.get_children(s, b.id)
            assert [x.id for x in children] == [c.id]
    _run(_t())


# --------------------------------------------------------------------------- #
# 18: Allen_HBA species fix
# --------------------------------------------------------------------------- #


def test_allen_hba_never_inferred_as_mouse():
    # Allen_HBA is a human atlas — "allen" substring must not imply mouse
    assert _resolve_expected_species({"source_atlas": "Allen_HBA_2012", "granularity": "molecular_attr"}) is None
    assert _resolve_expected_species({"source_atlas": "Allen_HBA_2012", "granularity": "macro"}) == "human"
    # explicit metadata wins
    assert _resolve_expected_species({"source_atlas": "Allen_HBA_2012", "species": "human"}) == "human"
    assert _resolve_expected_species({"source_atlas": "Mouse_Allen", "species": "human"}) == "human"
    # explicitly mouse-named sources still resolve
    assert _resolve_expected_species({"source_atlas": "Mouse_Allen"}) == "mouse"
    # granularity alone never implies mouse
    assert _resolve_expected_species({"granularity": "molecular"}) is None
    assert _resolve_expected_species({"granularity": "fine_cyto"}) is None


# --------------------------------------------------------------------------- #
# 19: legacy canonical_id
# --------------------------------------------------------------------------- #


def test_legacy_canonical_id_not_authoritative(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            # legacy canonical_id exists on Macro96 rows (source-local backfill)
            legacy = (
                await s.execute(
                    text(
                        "SELECT canonical_id FROM candidate_brain_regions "
                        "WHERE source_atlas='Macro96' AND canonical_id IS NOT NULL LIMIT 1"
                    )
                )
            ).scalar_one_or_none()
            assert legacy is not None
            assert str(legacy).startswith("Macro96_")
            # resolution uses canonical_region_id, never the legacy canonical_id string
            grounded = (
                await s.execute(
                    select(CandidateBrainRegion).where(
                        CandidateBrainRegion.source_atlas == "Macro96",
                        CandidateBrainRegion.en_name == "left hippocampus",
                    )
                )
            ).scalar_one()
            resolved = await crs.resolve_candidate_to_canonical(s, grounded.id)
            assert resolved is not None
            assert resolved.region_code.startswith("ng:br:")
            assert resolved.region_code != str(legacy).lower().replace("macro96_", "ng:br:")
            # ungrounded Allen candidates resolve to None
            allen = (
                await s.execute(
                    select(CandidateBrainRegion).where(
                        CandidateBrainRegion.source_atlas == "Allen_HBA_2012",
                        CandidateBrainRegion.canonical_region_id.is_(None),
                    )
                )
            ).scalars().first()
            assert allen is not None
            assert await crs.resolve_candidate_to_canonical(s, allen.id) is None
    _run(_t())


# --------------------------------------------------------------------------- #
# 20: integrity checker
# --------------------------------------------------------------------------- #


def test_integrity_clean_on_seeded_backbone(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            result = await crs.check_canonical_brain_region_integrity(s)
            assert result["ok"] is True, result["issues"]
            counts = result["counts"]
            assert counts["l0_count"] >= 1
            assert counts["l1_count"] >= 4
            # BR2: L2 clinical (Macro96) layer exists; BR1 assertions upgraded
            assert counts["l2_clinical_count"] >= 48
            assert counts["macro96_total"] == 96
            assert counts["macro96_mapped"] == 96
            assert counts["mapped_candidates"] >= 96
            assert counts["orphan_canonical_refs"] == 0
            assert counts["cross_species_mappings"] == 0
            assert counts["isolated_node_count"] == 0
    _run(_t())


def test_integrity_detects_level_direction_violation(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            l0 = await _mk(s, f"ng:br:{TEST_PREFIX}inv_root2", level="whole_brain")
            l1 = await _mk(s, f"ng:br:{TEST_PREFIX}inv_child2", level="macro")
            await s.flush()
            # bypass service validation to plant a bad edge (raw insert)
            await s.execute(
                text(
                    "INSERT INTO canonical_region_hierarchy "
                    "(child_region_id, parent_region_id, predicate, status, created_by) "
                    "VALUES (:c, :p, 'part_of', 'active', 'br1_test')"
                ),
                {"c": str(l0.id), "p": str(l1.id)},
            )
            await s.commit()
            result = await crs.check_canonical_brain_region_integrity(s)
            codes = [i["code"] for i in result["issues"]]
            assert "INVALID_LEVEL_DIRECTION" in codes
            assert result["ok"] is False
    _run(_t())


# --------------------------------------------------------------------------- #
# 21-22: readiness helpers (read-only)
# --------------------------------------------------------------------------- #


def test_connection_endpoint_readiness(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            connection = (
                await s.execute(
                    text(
                        "SELECT * FROM mirror_region_connections "
                        "WHERE source_atlas='Macro96' AND source_region_candidate_id IS NOT NULL "
                        "AND target_region_candidate_id IS NOT NULL LIMIT 1"
                    )
                )
            ).first()
            assert connection is not None, "no Macro96 connection fixture found"
            from app.models.mirror_kg import MirrorRegionConnection

            conn_row = await s.get(MirrorRegionConnection, connection[0])
            result = await crs.resolve_connection_endpoints_to_canonical(s, conn_row)
            assert result["source_candidate"] is not None
            assert result["target_candidate"] is not None
            assert "source_canonical" in result and "target_canonical" in result
            assert "resolved" in result
    _run(_t())


def test_circuit_participant_readiness(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            result = await crs.circuit_participant_readiness(s)
            assert result["distinct_participant_candidates"] > 0
            assert result["coverage"] >= 0.0 and result["coverage"] <= 1.0
            assert result["resolved_to_canonical"] + result["unresolved"] == result["distinct_participant_candidates"]
    _run(_t())


# --------------------------------------------------------------------------- #
# 23: P1 invariants continue to hold (ontology_terms untouched by BR1)
# --------------------------------------------------------------------------- #


def test_p1_function_identity_untouched(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            total = int((await s.execute(text("SELECT COUNT(*) FROM ontology_terms"))).scalar_one())
            non_function = int(
                (await s.execute(text("SELECT COUNT(*) FROM ontology_terms WHERE term_type <> 'function'"))).scalar_one()
            )
            assert total == 8189
            assert non_function == 0
            # all mirror function rows still 100% anchored to ontology_terms
            for table in ("mirror_region_functions", "mirror_circuit_functions", "mirror_projection_functions"):
                n = int((await s.execute(text(f"SELECT COUNT(*) FROM {table}"))).scalar_one())
                anchored = int((await s.execute(text(f"SELECT COUNT(*) FROM {table} WHERE term_id IS NOT NULL"))).scalar_one())
                assert n == anchored, f"{table} must stay 100% term-anchored"
    _run(_t())
