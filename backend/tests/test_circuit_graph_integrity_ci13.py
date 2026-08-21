"""CI1.3-3: Circuit-Connection-Region closure integrity checker tests.

Acceptance: a connection member whose endpoints are both region members of
the same circuit is topology-closed; a member with an endpoint outside the
circuit is flagged (TOPOLOGY_ENDPOINT_NOT_MEMBER, high); deprecated entity
references are flagged (medium); the checker is read-only (production rows
never change); counts include the topology closure statistics.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.schemas.canonical_circuit import (
    CanonicalCircuitConnectionCreate,
    CanonicalCircuitCreate,
    CanonicalCircuitRegionCreate,
)
from app.schemas.canonical_connection import CanonicalConnectionCreate
from app.schemas.canonical_region import CanonicalRegionCreate
from app.services import canonical_circuit_service as cis
from app.services import canonical_connection_service as ccs
from app.services import canonical_region_service as crs

TEST_PREFIX = "ci13_test_"

pytestmark = pytest.mark.function_term_real


def _run(coro):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    return asyncio.run(coro)


@pytest.fixture()
def db():
    """Delete CI1.3 test circuits/members/connections/regions before and after."""

    async def _cleanup() -> None:
        async with AsyncSessionLocal() as s:
            for table in ("canonical_circuit_regions", "canonical_circuit_connections",
                          "canonical_circuit_functions"):
                await s.execute(
                    text(
                        f"DELETE FROM {table} WHERE circuit_id IN "
                        "(SELECT id FROM canonical_circuits WHERE circuit_code LIKE 'ng:ci:ci13_test_%')"
                    )
                )
            await s.execute(
                text("DELETE FROM canonical_circuits WHERE circuit_code LIKE 'ng:ci:ci13_test_%'")
            )
            await s.execute(
                text(
                    "DELETE FROM canonical_connections WHERE "
                    "source_region_id IN (SELECT id FROM canonical_brain_regions "
                    "WHERE region_code LIKE 'ng:br:cn1_test_%') "
                    "OR target_region_id IN (SELECT id FROM canonical_brain_regions "
                    "WHERE region_code LIKE 'ng:br:cn1_test_%')"
                )
            )
            await s.execute(
                text("DELETE FROM canonical_brain_regions WHERE region_code LIKE 'ng:br:cn1_test_%'")
            )
            await s.commit()

    _run(_cleanup())
    yield
    _run(_cleanup())


async def _mk_region(session, code: str, status: str = "active"):
    return await crs.create_canonical_region(
        session,
        CanonicalRegionCreate(
            region_code=f"ng:br:cn1_test_{code}",
            canonical_name_en=f"ci13 test {code}",
            species="human",
            granularity_level="clinical",
            hemisphere_policy="lateralized",
            status=status,
            confidence=0.9,
            created_by="ci13_test",
        ),
    )


async def _mk_connection(session, src, tgt, ctype: str = "structural"):
    return await ccs.create_canonical_connection(
        session,
        CanonicalConnectionCreate(
            source_region_id=src.id,
            target_region_id=tgt.id,
            connection_type=ctype,
            directionality_policy="directed",
            species="human",
            status="proposed",
            confidence=0.8,
        ),
    )


async def _mk_circuit(session, name: str, code_suffix: str):
    # explicit circuit_code keeps cleanup (ng:ci:ci13_test_%) exact — the
    # auto slug from the display name would escape the fixture's LIKE pattern
    return await cis.create_canonical_circuit(
        session,
        CanonicalCircuitCreate(
            canonical_name_en=name,
            circuit_code=f"ng:ci:{TEST_PREFIX}{code_suffix}",
            circuit_type="network",
            species="human",
            granularity_level="clinical",
            status="proposed",
            confidence=0.8,
            created_by="ci13_test",
        ),
    )


def test_closed_topology_no_issue_for_its_circuit(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            a = await _mk_region(s, "a")
            b = await _mk_region(s, "b")
            conn = await _mk_connection(s, a, b)
            circuit = await _mk_circuit(s, "CI13 Closed Topology", "closed")
            await cis.add_circuit_region(
                s, circuit.id,
                CanonicalCircuitRegionCreate(region_id=a.id, role="core_region",
                                             order_index=0, confidence=0.8),
            )
            await cis.add_circuit_region(
                s, circuit.id,
                CanonicalCircuitRegionCreate(region_id=b.id, role="core_region",
                                             order_index=1, confidence=0.8),
            )
            await cis.add_circuit_connection(
                s, circuit.id,
                CanonicalCircuitConnectionCreate(connection_id=conn.id, role="supporting",
                                                 confidence=0.7),
            )
            await s.commit()
            return circuit, conn

    circuit, conn = _run(_t())

    async def _check():
        async with AsyncSessionLocal() as s:
            result = await cis.check_circuit_graph_integrity(s)
            # the closed circuit's connection must not appear in any issue
            # (checker messages reference circuits by id)
            for i in result["issues"]:
                assert str(circuit.id) not in i["message"], i
            assert result["counts"]["topology_closed_connections"] >= 1
            return result

    result = _run(_check())
    assert "circuits_with_connections" in result["counts"]


def test_open_topology_flagged_and_counted(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            a = await _mk_region(s, "a")
            b = await _mk_region(s, "b")
            conn = await _mk_connection(s, a, b)
            circuit = await _mk_circuit(s, "CI13 Open Topology", "open")
            # only region A is a member; B exists but stays outside the circuit
            await cis.add_circuit_region(
                s, circuit.id,
                CanonicalCircuitRegionCreate(region_id=a.id, role="core_region",
                                             order_index=0, confidence=0.8),
            )
            await cis.add_circuit_connection(
                s, circuit.id,
                CanonicalCircuitConnectionCreate(connection_id=conn.id, role="supporting",
                                                 confidence=0.7),
            )
            await s.commit()
            return circuit

    circuit = _run(_t())

    async def _check():
        async with AsyncSessionLocal() as s:
            result = await cis.check_circuit_graph_integrity(s)
            open_issues = [i for i in result["issues"]
                           if i["code"] == "TOPOLOGY_ENDPOINT_NOT_MEMBER"
                           and str(circuit.id) in i["message"]]
            assert open_issues, result["issues"]
            assert open_issues[0]["severity"] == "high"
            assert result["counts"]["topology_open_connections"] >= 1
            assert result["ok"] is False  # high issues fail the checker
            return result

    _run(_check())


def test_deprecated_region_reference_flagged(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            dep = await _mk_region(s, "dep", status="deprecated")
            circuit = await _mk_circuit(s, "CI13 Deprecated Ref", "dep")
            await cis.add_circuit_region(
                s, circuit.id,
                CanonicalCircuitRegionCreate(region_id=dep.id, role="core_region",
                                             order_index=0, confidence=0.8),
            )
            await s.commit()
            return circuit

    circuit = _run(_t())

    async def _check():
        async with AsyncSessionLocal() as s:
            result = await cis.check_circuit_graph_integrity(s)
            dep_issues = [i for i in result["issues"]
                          if i["code"] == "DEPRECATED_REGION_REFERENCE"
                          and str(circuit.id) in i["message"]]
            assert dep_issues, result["issues"]
            assert dep_issues[0]["severity"] == "medium"
            assert result["counts"]["deprecated_reference_count"] >= 1

    _run(_check())


def test_checker_is_read_only(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            before = {}
            for table in ("canonical_circuits", "canonical_circuit_regions",
                          "canonical_circuit_connections", "canonical_circuit_functions",
                          "canonical_connections", "canonical_brain_regions",
                          "mirror_region_circuits"):
                before[table] = (
                    await s.execute(text(f"SELECT count(*) FROM {table}"))
                ).scalar_one()
            result = await cis.check_circuit_graph_integrity(s)
            await s.rollback()
            after = {}
            for table in before:
                after[table] = (
                    await s.execute(text(f"SELECT count(*) FROM {table}"))
                ).scalar_one()
            return before, after, result

    before, after, result = _run(_t())
    assert before == after
    assert set(result.keys()) == {"ok", "counts", "issues"}
    assert "topology_closed_connections" in result["counts"]
    assert "topology_open_connections" in result["counts"]
    assert "circuits_with_connections" in result["counts"]
    assert "orphan_member_count" not in result["counts"]  # split per member type
