"""CI1.2-B: Macro circuit canonicalizer tests.

Acceptance: plan classification matches the frozen numbers (450 macro
→ 293 aligned / 145 unresolved / 12 rejected, post CI1.3-2 connection
evidence merge); aligned circuits write to canonical_circuits as proposed
with full region/function/connection member binding and complete provenance;
unresolved/rejected never written; connection members that cannot bind are
recorded in unresolved_connections without failing the circuit; second run
inserts 0 (idempotent); mirror tables never change (53,562 mirror circuits).
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services import macro_circuit_canonicalizer as mcc

TEST_PREFIX = "ci12b_test_"

pytestmark = pytest.mark.function_term_real

# frozen from the CI1.2-A dry-run, recomputed after the CI1.3-2 connection
# evidence merge and the CI1.3-3 production write of all 293 aligned circuits
# (e2e DB 2026-08-20)
_MACRO_CIRCUIT_COUNT = 450
_ALIGNED_COUNT = 293
_UNRESOLVED_COUNT = 145
_REJECTED_COUNT = 12
_REGION_MEMBERS_ALIGNED = 1402
_FUNCTION_MEMBERS_ALIGNED = 1420
_PROJECTION_MEMBERS_ALIGNED = 600

_PROVENANCE_KEYS = {
    "source_mirror_circuit_id",
    "source_region_ids",
    "source_connection_ids",
    "source_function_ids",
    "mapping_version",
    "mapping_confidence",
}


def _run(coro):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    return asyncio.run(coro)


@pytest.fixture()
def db():
    """Delete CI1.2-B test canonical circuits (+ members) before and after."""

    async def _cleanup() -> None:
        async with AsyncSessionLocal() as s:
            for table in ("canonical_circuit_regions", "canonical_circuit_connections", "canonical_circuit_functions"):
                await s.execute(
                    text(
                        f"DELETE FROM {table} WHERE circuit_id IN "
                        "(SELECT id FROM canonical_circuits WHERE "
                        "provenance_json->>'source_mirror_circuit_id' LIKE 'ci12b_test_%')"
                    )
                )
            await s.execute(
                text(
                    "DELETE FROM canonical_circuits WHERE "
                    "provenance_json->>'source_mirror_circuit_id' LIKE 'ci12b_test_%'"
                )
            )
            await s.commit()

    _run(_cleanup())
    yield
    _run(_cleanup())


async def _get_real_ids(session):
    regions = (
        await session.execute(
            text(
                "SELECT id FROM canonical_brain_regions "
                "WHERE species IN ('human', 'unknown') ORDER BY id LIMIT 2"
            )
        )
    ).scalars().all()
    connection = (
        await session.execute(
            text(
                "SELECT id FROM canonical_connections "
                "WHERE species IN ('human', 'unknown') ORDER BY id LIMIT 1"
            )
        )
    ).scalars().all()
    term = (
        await session.execute(
            text(
                "SELECT id FROM ontology_terms "
                "WHERE term_type='function' AND status='active' ORDER BY id LIMIT 1"
            )
        )
    ).scalars().all()
    return regions, connection, term


def _region_member(region_id, *, role="core_region", order_index=0, mid_suffix="r1"):
    return {
        "canonical_region_id": str(region_id),
        "role": role,
        "order_index": order_index,
        "confidence": 0.8,
        "provenance_json": {
            "original_mirror_region_id": f"{TEST_PREFIX}region_{mid_suffix}",
            "original_role": "participant",
        },
    }


def _connection_member(connection_id, *, role="supporting", mid_suffix="c1"):
    return {
        "canonical_connection_id": str(connection_id),
        "role": role,
        "confidence": 0.7,
        "provenance_json": {
            "original_mirror_membership_id": f"{TEST_PREFIX}membership_{mid_suffix}",
            "original_projection_id": f"{TEST_PREFIX}projection_{mid_suffix}",
            "original_role_in_circuit": "unknown",
        },
    }


def _function_member(term_id, *, mid_suffix="f1"):
    return {
        "function_term_id": str(term_id),
        "relation_type": "associated_with",
        "confidence": 0.9,
        "provenance_json": {
            "original_mirror_function_id": f"{TEST_PREFIX}function_{mid_suffix}",
            "original_function_role": "enables",
            "original_effect_type": None,
            "resolution_path": ["direct"],
        },
    }


def _plan_item(
    *,
    mid,
    name="CI12B Test Circuit",
    cn=None,
    ctype="network",
    region_members,
    connection_members,
    function_members,
):
    region_ids = [m["provenance_json"]["original_mirror_region_id"] for m in region_members]
    connection_ids = [
        m["provenance_json"]["original_mirror_membership_id"] for m in connection_members
    ]
    function_ids = [m["provenance_json"]["original_mirror_function_id"] for m in function_members]
    return {
        "mirror_circuit_id": mid,
        "source_atlas": "Macro96",
        "canonical_name_en": name,
        "canonical_name_cn": cn,
        "circuit_type": ctype,
        "original_circuit_type": "sensory_circuit",
        "species": "human",
        "granularity_level": "clinical",
        "status": "proposed",
        "description": None,
        "confidence": 0.8,
        "source_summary": {
            "source_atlas": "Macro96",
            "mirror_circuit_type": "sensory_circuit",
            "region_members": len(region_members),
            "function_members": len(function_members),
            "connection_members": len(connection_members),
        },
        "provenance_json": {
            "source_mirror_circuit_id": mid,
            "source_region_ids": region_ids,
            "source_connection_ids": connection_ids,
            "source_function_ids": function_ids,
            "mapping_version": "macro96_canonical_circuit_v1",
            "mapping_confidence": 1.0,
        },
        "region_members": region_members,
        "connection_members": connection_members,
        "function_members": function_members,
    }


# --------------------------------------------------------------------------- #
# plan classification
# --------------------------------------------------------------------------- #


def test_build_plan_matches_frozen_classification(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            plan = await mcc.build_plan(s)
            stats = plan["stats"]
            assert stats["candidate_count"] == _MACRO_CIRCUIT_COUNT
            assert stats["aligned_count"] == _ALIGNED_COUNT
            assert stats["unresolved_count"] == _UNRESOLVED_COUNT
            assert stats["rejected_count"] == _REJECTED_COUNT
            # member-level stats span all non-rejected circuits (incl. unresolved)
            assert stats["region_members_aligned"] == _REGION_MEMBERS_ALIGNED
            assert stats["function_members_aligned"] == _FUNCTION_MEMBERS_ALIGNED
            assert stats["projection_members_aligned"] == _PROJECTION_MEMBERS_ALIGNED
            assert len(plan["plans"]) == _ALIGNED_COUNT
            assert len(plan["unresolved_circuits"]) == _UNRESOLVED_COUNT
            assert len(plan["rejected_circuits"]) == _REJECTED_COUNT
            for p in plan["plans"]:
                assert p["status"] == "proposed"
                assert set(p["provenance_json"].keys()) == _PROVENANCE_KEYS
                assert p["provenance_json"]["source_mirror_circuit_id"] == p["mirror_circuit_id"]
                assert p["region_members"]
                # provenance id lists exactly mirror the member provenance ids
                assert p["provenance_json"]["source_region_ids"] == [
                    m["provenance_json"]["original_mirror_region_id"]
                    for m in p["region_members"]
                ]
                assert p["provenance_json"]["source_connection_ids"] == [
                    m["provenance_json"]["original_mirror_membership_id"]
                    for m in p["connection_members"]
                ]
                assert p["provenance_json"]["source_function_ids"] == [
                    m["provenance_json"]["original_mirror_function_id"]
                    for m in p["function_members"]
                ]
            return plan

    plan = _run(_t())
    plan_ids = {p["mirror_circuit_id"] for p in plan["plans"]}
    unresolved_ids = {u["mirror_circuit_id"] for u in plan["unresolved_circuits"]}
    rejected_ids = {r["mirror_circuit_id"] for r in plan["rejected_circuits"]}
    # unresolved / rejected circuits never enter the write plan
    assert plan_ids.isdisjoint(unresolved_ids)
    assert plan_ids.isdisjoint(rejected_ids)
    # skipped circuits always carry reasons
    for u in plan["unresolved_circuits"]:
        assert u["failures"]
    for r in plan["rejected_circuits"]:
        assert r["reason"]


def test_dry_run_marks_itself(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            result = await mcc.dry_run(s)
            assert result["dry_run"] is True
            assert len(result["plans"]) == _ALIGNED_COUNT

    _run(_t())


# --------------------------------------------------------------------------- #
# write: members, provenance, partial connections, idempotency
# --------------------------------------------------------------------------- #


def test_write_creates_circuit_with_full_members_and_provenance(db):
    mid = f"{TEST_PREFIX}circuit_full"

    async def _t():
        async with AsyncSessionLocal() as s:
            regions, connections, terms = await _get_real_ids(s)
            plan = _plan_item(
                mid=mid,
                cn="测试回路",
                region_members=[
                    _region_member(regions[0], role="core_region", order_index=0),
                    _region_member(regions[1], role="input", order_index=1),
                ],
                connection_members=[_connection_member(connections[0])],
                function_members=[_function_member(terms[0])],
            )
            result = await mcc.write(s, [plan])
            await s.commit()
            return result, regions, connections, terms

    result, regions, connections, terms = _run(_t())
    assert result == {
        "created": 1,
        "skipped_existing": 0,
        "region_members_written": 2,
        "connection_members_written": 1,
        "function_members_written": 1,
        "folded_region_members": 0,
        "folded_connection_members": 0,
        "folded_function_members": 0,
        "unresolved_connections": [],
    }

    async def _verify():
        async with AsyncSessionLocal() as s:
            circuit = (
                await s.execute(
                    text(
                        "SELECT id, circuit_code, canonical_name_en, canonical_name_cn, "
                        "status, circuit_type, provenance_json, source_summary, created_by "
                        "FROM canonical_circuits WHERE provenance_json->>'source_mirror_circuit_id' = :mid"
                    ),
                    {"mid": mid},
                )
            ).first()
            assert circuit is not None
            assert circuit.canonical_name_en == "CI12B Test Circuit"
            assert circuit.canonical_name_cn == "测试回路"
            assert circuit.status == "proposed"
            assert circuit.circuit_type == "network"
            assert circuit.created_by == "macro96_canonical_circuit_v1"
            assert set(circuit.provenance_json.keys()) == _PROVENANCE_KEYS
            assert circuit.source_summary["source_atlas"] == "Macro96"
            cid = circuit.id

            rows = (
                await s.execute(
                    text(
                        "SELECT region_id, role, order_index, provenance_json "
                        "FROM canonical_circuit_regions WHERE circuit_id = :cid ORDER BY order_index"
                    ),
                    {"cid": cid},
                )
            ).all()
            assert [r.role for r in rows] == ["core_region", "input"]
            assert rows[0].provenance_json["original_role"] == "participant"
            assert rows[0].provenance_json["original_mirror_region_id"] == f"{TEST_PREFIX}region_r1"

            conn_rows = (
                await s.execute(
                    text(
                        "SELECT connection_id, role, provenance_json "
                        "FROM canonical_circuit_connections WHERE circuit_id = :cid"
                    ),
                    {"cid": cid},
                )
            ).all()
            assert len(conn_rows) == 1
            assert conn_rows[0].connection_id == connections[0]
            assert conn_rows[0].role == "supporting"
            assert (
                conn_rows[0].provenance_json["original_role_in_circuit"] == "unknown"
            )

            func_rows = (
                await s.execute(
                    text(
                        "SELECT function_term_id, relation_type, provenance_json "
                        "FROM canonical_circuit_functions WHERE circuit_id = :cid"
                    ),
                    {"cid": cid},
                )
            ).all()
            assert len(func_rows) == 1
            assert func_rows[0].function_term_id == terms[0]
            assert func_rows[0].relation_type == "associated_with"

    _run(_verify())


def test_write_connection_partial_binding_does_not_fail_circuit(db):
    mid = f"{TEST_PREFIX}circuit_partial"

    async def _t():
        async with AsyncSessionLocal() as s:
            regions, connections, terms = await _get_real_ids(s)
            missing = uuid.uuid4()
            plan = _plan_item(
                mid=mid,
                region_members=[_region_member(regions[0])],
                connection_members=[
                    _connection_member(connections[0]),
                    _connection_member(missing, mid_suffix="c2"),
                ],
                function_members=[_function_member(terms[0])],
            )
            result = await mcc.write(s, [plan])
            await s.commit()
            return result, missing

    result, missing = _run(_t())
    assert result["created"] == 1
    assert result["connection_members_written"] == 1
    assert len(result["unresolved_connections"]) == 1
    assert result["unresolved_connections"][0]["canonical_connection_id"] == str(missing)
    assert result["unresolved_connections"][0]["mirror_circuit_id"] == mid

    async def _verify():
        async with AsyncSessionLocal() as s:
            cid = (
                await s.execute(
                    text(
                        "SELECT id FROM canonical_circuits WHERE "
                        "provenance_json->>'source_mirror_circuit_id' = :mid"
                    ),
                    {"mid": mid},
                )
            ).scalar_one()
            count = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM canonical_circuit_connections WHERE circuit_id = :cid"
                    ),
                    {"cid": cid},
                )
            ).scalar_one()
            assert count == 1

    _run(_verify())


def test_write_second_run_is_idempotent(db):
    mid = f"{TEST_PREFIX}circuit_idem"

    async def _mk_plan():
        async with AsyncSessionLocal() as s:
            regions, connections, terms = await _get_real_ids(s)
            return _plan_item(
                mid=mid,
                region_members=[_region_member(regions[0])],
                connection_members=[],
                function_members=[],
            )

    plan = _run(_mk_plan())

    async def _write_once():
        async with AsyncSessionLocal() as s:
            result = await mcc.write(s, [plan])
            await s.commit()
            return result

    first = _run(_write_once())
    second = _run(_write_once())
    assert first["created"] == 1
    assert second["created"] == 0
    assert second["skipped_existing"] == 1

    async def _verify():
        async with AsyncSessionLocal() as s:
            count = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM canonical_circuits WHERE "
                        "provenance_json->>'source_mirror_circuit_id' = :mid"
                    ),
                    {"mid": mid},
                )
            ).scalar_one()
            assert count == 1

    _run(_verify())


def test_write_mirror_tables_untouched(db):
    mid = f"{TEST_PREFIX}circuit_mirror"

    async def _t():
        async with AsyncSessionLocal() as s:
            tables = (
                "mirror_region_circuits",
                "mirror_circuit_regions",
                "mirror_circuit_functions",
                "mirror_circuit_projection_memberships",
            )
            before = {}
            for t in tables:
                before[t] = (
                    await s.execute(text(f"SELECT count(*) FROM {t}"))
                ).scalar_one()
            spot_before = (
                await s.execute(
                    text("SELECT updated_at FROM mirror_region_circuits ORDER BY id LIMIT 1")
                )
            ).scalar_one()

            regions, connections, terms = await _get_real_ids(s)
            plan = _plan_item(
                mid=mid,
                region_members=[_region_member(regions[0])],
                connection_members=[_connection_member(connections[0])],
                function_members=[_function_member(terms[0])],
            )
            await mcc.write(s, [plan])
            await s.commit()

            after = {}
            for t in tables:
                after[t] = (
                    await s.execute(text(f"SELECT count(*) FROM {t}"))
                ).scalar_one()
            spot_after = (
                await s.execute(
                    text("SELECT updated_at FROM mirror_region_circuits ORDER BY id LIMIT 1")
                )
            ).scalar_one()
            return before, after, spot_before, spot_after

    before, after, spot_before, spot_after = _run(_t())
    assert before == after
    assert before["mirror_region_circuits"] == 53562
    assert spot_before == spot_after


# --------------------------------------------------------------------------- #
# full real plan against the production canonical layer (post CI1.3-3 write):
# the batch must be a complete no-op — plan and DB are in sync (all 293
# aligned circuits written) — and the integrity checker must accept the
# production data
# --------------------------------------------------------------------------- #


def test_full_plan_write_is_noop_and_integrity_ok_then_rollback(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            before = (
                await s.execute(text("SELECT count(*) FROM canonical_circuits"))
            ).scalar_one()
            plan = await mcc.build_plan(s)
            result = await mcc.write(s, plan["plans"])
            # production runs (CI1.2-B + CI1.3-3) already wrote all aligned circuits
            assert result["created"] == 0
            assert result["skipped_existing"] == _ALIGNED_COUNT
            assert result["region_members_written"] == 0
            assert result["connection_members_written"] == 0
            assert result["function_members_written"] == 0
            assert result["folded_region_members"] == 0
            assert result["folded_connection_members"] == 0
            assert result["folded_function_members"] == 0
            assert result["unresolved_connections"] == []
            # production canonical layer passes the CI1.1 integrity checker
            integrity = await mcc.integrity_check(s)
            assert integrity["ok"] is True, integrity["issues"]
            assert integrity["counts"]["total_circuits"] == _ALIGNED_COUNT
            assert integrity["counts"]["mirror_circuits_untouched"] == 53562
            # everything above ran inside the session transaction — roll back
            await s.rollback()
            after = (
                await s.execute(text("SELECT count(*) FROM canonical_circuits"))
            ).scalar_one()
            assert after == before

    _run(_t())
