"""Canonical Region Browser (tree explorer) tests.

Two layers:

1. Router layer (no DB) — TestClient + service monkeypatch. Guards the route
   order: ``/integrity`` (and the new ``/roots``) must not be swallowed by the
   dynamic ``/{region_id}`` group registered before them (was a 422 regression).
2. DB layer — real e2e test DB, same fixture/hygiene as
   ``test_canonical_brain_region_br1.py`` (``br1_test_`` prefix, Macro96
   snapshot restore, ``function_term_real`` marker).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.database import AsyncSessionLocal
from app.main import app
from app.models.candidate import CandidateBrainRegion
from app.models.canonical_circuit import CanonicalCircuit, CanonicalCircuitFunction, CanonicalCircuitRegion
from app.models.canonical_connection import CanonicalConnection
from app.models.ontology import OntologyTerm
from app.schemas.canonical_region import (
    CanonicalRegionCreate,
    CanonicalRegionHierarchyCreate,
    CanonicalRegionRead,
)
from app.services import canonical_region_service as crs

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
    """Snapshot Macro96 anchor state; restore it afterwards (same as BR1)."""

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
            await session.execute(
                text(
                    "DELETE FROM ontology_alignment_candidates "
                    "WHERE external_system='ng:br' AND external_iri LIKE 'ng:br:br1_test_%'"
                )
            )
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
            await session.execute(
                text(
                    "DELETE FROM canonical_region_hierarchy WHERE "
                    "child_region_id IN (SELECT id FROM canonical_brain_regions WHERE region_code LIKE 'ng:br:br1_test_%') "
                    "OR parent_region_id IN (SELECT id FROM canonical_brain_regions WHERE region_code LIKE 'ng:br:br1_test_%')"
                )
            )
            # test circuits are not reached by the region cascade — remove explicitly
            await session.execute(text("DELETE FROM canonical_circuits WHERE circuit_code LIKE 'ng:ci:br1_test_%'"))
            await session.execute(text("DELETE FROM canonical_brain_regions WHERE region_code LIKE 'ng:br:br1_test_%'"))
            await session.commit()

    snapshot = _run(_snapshot())
    yield
    _run(_cleanup(snapshot))


async def _mk(session, code: str, *, level: str = "macro"):
    return await crs.create_canonical_region(
        session,
        CanonicalRegionCreate(
            region_code=code,
            canonical_name_en=code.replace("ng:br:", ""),
            canonical_name_cn=None,
            species="human",
            granularity_level=level,
            hemisphere_policy="bilateral",
            status="active",
            confidence=0.9,
            created_by="br1_test",
        ),
    )


async def _edge(session, child, parent):
    return await crs.add_part_of_edge(
        session,
        CanonicalRegionHierarchyCreate(
            child_region_id=child.id,
            parent_region_id=parent.id,
            predicate="part_of",
            status="active",
            source="test",
            confidence=0.9,
            created_by="br1_test",
        ),
    )


# --------------------------------------------------------------------------- #
# Router layer — route order + payload shape (no DB)
# --------------------------------------------------------------------------- #


def _region_read(code: str) -> CanonicalRegionRead:
    return CanonicalRegionRead(
        id=uuid.uuid4(),
        region_code=code,
        canonical_name_en=code.replace("ng:br:", ""),
        canonical_name_cn=None,
        species="human",
        granularity_domain="brain_region_anatomical",
        granularity_level="macro",
        hemisphere_policy="bilateral",
        status="active",
        description=None,
        confidence=None,
        source_summary={},
        external_mappings={},
        created_by="test",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def test_roots_route_200():
    client = TestClient(app)
    fake = [_region_read("ng:br:brain"), _region_read("ng:br:cerebrum")]

    async def _fake(session):
        return fake

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(crs, "get_roots", _fake)
        r = client.get("/api/canonical-regions/roots")
    assert r.status_code == 200
    body = r.json()
    assert [row["region_code"] for row in body] == ["ng:br:brain", "ng:br:cerebrum"]
    assert "granularity_level" in body[0]


def test_integrity_route_reachable():
    """Regression guard: /integrity must not be swallowed by /{region_id}.

    Before the route reorder this returned 422 (UUID parse failure on
    'integrity'); the fix moved the dynamic group to the end of the file.
    """
    client = TestClient(app)

    async def _fake(session):
        return {"ok": True, "counts": {}, "issues": []}

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(crs, "check_canonical_brain_region_integrity", _fake)
        r = client.get("/api/canonical-regions/integrity")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_connections_route_returns_payload():
    client = TestClient(app)
    endpoint_id = uuid.uuid4()
    fake = [
        {
            "connection_id": uuid.uuid4(),
            "connection_code": "ng:cn:test_out",
            "connection_type": "structural",
            "directionality_policy": "directed",
            "status": "active",
            "confidence": 0.8,
            "direction": "outgoing",
            "endpoint_region": {
                "id": endpoint_id,
                "region_code": "ng:br:cerebellum",
                "canonical_name_en": "Cerebellum",
                "canonical_name_cn": "小脑",
                "granularity_level": "macro",
            },
        }
    ]

    async def _fake(session, region_id):
        return fake

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(crs, "get_region_connections", _fake)
        r = client.get(f"/api/canonical-regions/{uuid.uuid4()}/connections")
    assert r.status_code == 200
    body = r.json()
    assert body[0]["direction"] == "outgoing"
    assert body[0]["endpoint_region"]["region_code"] == "ng:br:cerebellum"


def test_circuits_route_returns_payload():
    client = TestClient(app)
    fake = [
        {
            "circuit_id": uuid.uuid4(),
            "circuit_code": "ng:ci:test_circuit",
            "canonical_name_en": "test circuit",
            "circuit_type": "pathway",
            "status": "active",
            "role": "core_region",
            "order_index": 0,
            "confidence": 0.7,
        }
    ]

    async def _fake(session, region_id):
        return fake

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(crs, "get_region_circuits", _fake)
        r = client.get(f"/api/canonical-regions/{uuid.uuid4()}/circuits")
    assert r.status_code == 200
    assert r.json()[0]["role"] == "core_region"


def test_functions_route_returns_payload():
    client = TestClient(app)
    fake = [
        {
            "function_term_id": uuid.uuid4(),
            "term_code": "ng:fn:test_fn",
            "canonical_term_en": "motor control",
            "canonical_term_cn": "运动控制",
            "relation_type": "involved_in",
            "circuit_code": "ng:ci:test_circuit",
            "circuit_name": "test circuit",
            "confidence": None,
        }
    ]

    async def _fake(session, region_id):
        return fake

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(crs, "get_region_functions", _fake)
        r = client.get(f"/api/canonical-regions/{uuid.uuid4()}/functions")
    assert r.status_code == 200
    assert r.json()[0]["term_code"] == "ng:fn:test_fn"


def test_candidates_route_returns_payload():
    client = TestClient(app)
    fake = [
        {
            "candidate_id": uuid.uuid4(),
            "source_atlas": "Macro96",
            "source_version": "v3",
            "raw_name": "left hippocampus",
            "std_name": "Hippocampus",
            "en_name": "left hippocampus",
            "cn_name": "海马",
            "laterality": "left",
            "granularity_level": "clinical",
            "granularity_family": "macro_clinical",
            "alignment_status": "aligned",
            "candidate_status": "candidate_created",
            "uberon_iri": None,
            "nifstd_iri": None,
            "created_at": datetime.now(timezone.utc),
        }
    ]

    async def _fake(session, region_id):
        return fake

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(crs, "get_region_candidates", _fake)
        r = client.get(f"/api/canonical-regions/{uuid.uuid4()}/candidates")
    assert r.status_code == 200
    assert r.json()[0]["source_atlas"] == "Macro96"


# --------------------------------------------------------------------------- #
# DB layer — real queries against the e2e test database
# --------------------------------------------------------------------------- #


def test_roots_lists_brain_and_no_root_has_parent(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            roots = await crs.get_roots(s)
            codes = [r.region_code for r in roots]
            # production seed: exactly one top-level region
            assert "ng:br:brain" in codes
            assert "ng:br:cerebrum" not in codes
            # no root may have an active parent edge
            from app.models.canonical_region import CanonicalRegionHierarchy

            for root in roots:
                n = (
                    await s.execute(
                        text(
                            "SELECT COUNT(*) FROM canonical_region_hierarchy "
                            "WHERE child_region_id=:cid AND status='active'"
                        ),
                        {"cid": str(root.id)},
                    )
                ).scalar_one()
                assert n == 0, f"{root.region_code} has an active parent"
    _run(_t())


def test_children_sorted_by_level_order(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            root = await _mk(s, f"ng:br:{TEST_PREFIX}b_root", level="whole_brain")
            macro = await _mk(s, f"ng:br:{TEST_PREFIX}b_macro", level="macro")
            clinical = await _mk(s, f"ng:br:{TEST_PREFIX}b_clinical", level="clinical")
            research = await _mk(s, f"ng:br:{TEST_PREFIX}b_research", level="research")
            await s.flush()
            # insert in reverse order to prove sorting, not insertion order
            await _edge(s, research, root)
            await _edge(s, clinical, root)
            await _edge(s, macro, root)
            children = await crs.get_children(s, root.id)
            assert [c.region_code for c in children] == [macro.region_code, clinical.region_code, research.region_code]
    _run(_t())


def test_region_connections_direction_split(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            a = await _mk(s, f"ng:br:{TEST_PREFIX}conn_a")
            b = await _mk(s, f"ng:br:{TEST_PREFIX}conn_b")
            await s.flush()
            s.add(
                CanonicalConnection(
                    connection_code="ng:cn:br1_test_ab",
                    source_region_id=a.id,
                    target_region_id=b.id,
                    connection_type="structural",
                    directionality_policy="directed",
                    species="human",
                    granularity_level="clinical",
                    status="active",
                    confidence=0.8,
                )
            )
            await s.commit()
            out = await crs.get_region_connections(s, a.id)
            assert len(out) == 1
            assert out[0]["direction"] == "outgoing"
            assert out[0]["endpoint_region"]["id"] == b.id
            inn = await crs.get_region_connections(s, b.id)
            assert len(inn) == 1
            assert inn[0]["direction"] == "incoming"
            assert inn[0]["endpoint_region"]["id"] == a.id
            # neither touches an unrelated region
            c = await _mk(s, f"ng:br:{TEST_PREFIX}conn_c")
            await s.flush()
            assert await crs.get_region_connections(s, c.id) == []
    _run(_t())


def test_region_circuits_roles_ordered(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            # UNIQUE(circuit_id, region_id): one region = one role per circuit,
            # so two regions share the circuit with different order_index values
            r1 = await _mk(s, f"ng:br:{TEST_PREFIX}circ_r1")
            r2 = await _mk(s, f"ng:br:{TEST_PREFIX}circ_r2")
            await s.flush()
            circuit = CanonicalCircuit(
                circuit_code="ng:ci:br1_test_circuit",
                canonical_name_en="test circuit",
                species="human",
                granularity_level="clinical",
                circuit_type="pathway",
                status="active",
                confidence=0.7,
            )
            s.add(circuit)
            await s.flush()
            # insert out of order to prove order_index sorting
            s.add(CanonicalCircuitRegion(circuit_id=circuit.id, region_id=r2.id, role="output", order_index=2))
            s.add(CanonicalCircuitRegion(circuit_id=circuit.id, region_id=r1.id, role="input", order_index=1))
            await s.commit()
            rows = await crs.get_region_circuits(s, r1.id)
            assert [row["role"] for row in rows] == ["input"]
            assert rows[0]["circuit_code"] == "ng:ci:br1_test_circuit"
            assert rows[0]["order_index"] == 1
            # the other member sees its own role
            rows2 = await crs.get_region_circuits(s, r2.id)
            assert [row["role"] for row in rows2] == ["output"]
    _run(_t())


def test_region_functions_derived_via_circuits(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            r = await _mk(s, f"ng:br:{TEST_PREFIX}fn_r")
            await s.flush()
            term = (
                await s.execute(select(OntologyTerm).order_by(OntologyTerm.term_code).limit(1))
            ).scalar_one()
            circuit = CanonicalCircuit(
                circuit_code="ng:ci:br1_test_fn_circuit",
                canonical_name_en="fn test circuit",
                species="human",
                granularity_level="clinical",
                circuit_type="functional_loop",
                status="active",
            )
            s.add(circuit)
            await s.flush()
            s.add(CanonicalCircuitRegion(circuit_id=circuit.id, region_id=r.id, role="core_region"))
            s.add(
                CanonicalCircuitFunction(
                    circuit_id=circuit.id,
                    function_term_id=term.id,
                    relation_type="involved_in",
                    confidence=0.6,
                )
            )
            await s.commit()
            rows = await crs.get_region_functions(s, r.id)
            assert len(rows) == 1
            assert rows[0]["function_term_id"] == term.id
            assert rows[0]["term_code"] == term.term_code
            assert rows[0]["circuit_code"] == "ng:ci:br1_test_fn_circuit"
            # unrelated region sees nothing
            other = await _mk(s, f"ng:br:{TEST_PREFIX}fn_r2")
            await s.flush()
            assert await crs.get_region_functions(s, other.id) == []
    _run(_t())


def test_region_candidates_anchored(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            canonical = await _mk(s, f"ng:br:{TEST_PREFIX}cand_anchor")
            await s.flush()
            candidate = (
                await s.execute(
                    select(CandidateBrainRegion).where(
                        CandidateBrainRegion.source_atlas == "Macro96",
                        CandidateBrainRegion.en_name == "left accumbens area",
                    )
                )
            ).scalar_one()
            await crs.ground_candidate(
                s, candidate_id=candidate.id, canonical_region_id=canonical.id, match_type="exact", confidence=0.95
            )
            await s.commit()
            rows = await crs.get_region_candidates(s, canonical.id)
            assert len(rows) == 1
            assert rows[0]["candidate_id"] == candidate.id
            assert rows[0]["source_atlas"] == "Macro96"
            assert rows[0]["laterality"] == "left"
            # untouched canonical has none
            untouched = await _mk(s, f"ng:br:{TEST_PREFIX}cand_none")
            await s.flush()
            assert await crs.get_region_candidates(s, untouched.id) == []
    _run(_t())
