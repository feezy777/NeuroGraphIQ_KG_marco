"""CI1.2-A: frozen mirror circuit → canonical circuit mapping rule tests.

Acceptance: circuit_type mapping (functional classification → network /
uncertain; unmapped raises); region role mapping (participant→core_region,
source→input, target→output, hub/relay/modulator→intermediate; unknown
raises); connection role mapping (unknown→supporting); function resolution
reuses function_term_service WITHOUT creating terms; connection resolution
via provenance original_connection_ids; provenance completeness;
dry-run plan never writes and is deterministic.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.schemas.canonical_connection import CanonicalConnectionCreate
from app.schemas.canonical_region import CanonicalRegionCreate
from app.services import canonical_connection_service as ccs
from app.services import canonical_region_service as crs
from app.services import circuit_mapping_service as cms
from app.services.function_term_service import (
    STATE_GROUNDED_ACTIVE,
    STATE_UNRESOLVED,
    VALID_ANCHOR_STATES,
)

TEST_PREFIX = "ci12_test_"

pytestmark = pytest.mark.function_term_real

# macro circuit count frozen from the CI1.2-A audit (e2e DB 2026-08-20)
_MACRO_CIRCUIT_COUNT = 450


def _run(coro):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    return asyncio.run(coro)


@pytest.fixture()
def db():
    """Delete CI1.2 test connections/regions before and after each test."""

    async def _cleanup() -> None:
        async with AsyncSessionLocal() as s:
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


async def _mk_region(session, code: str, species: str = "human", status: str = "active"):
    return await crs.create_canonical_region(
        session,
        CanonicalRegionCreate(
            region_code=f"ng:br:cn1_test_{code}",
            canonical_name_en=f"ci12 test {code}",
            species=species,
            granularity_level="clinical",
            hemisphere_policy="lateralized",
            status=status,
            confidence=0.9,
            created_by="ci12_test",
        ),
    )


async def _mk_connection(session, src, tgt, ctype: str = "structural", status: str = "proposed"):
    return await ccs.create_canonical_connection(
        session,
        CanonicalConnectionCreate(
            source_region_id=src.id,
            target_region_id=tgt.id,
            connection_type=ctype,
            directionality_policy="directed",
            species="human",
            status=status,
            confidence=0.8,
        ),
    )


async def _get_active_function_term(session):
    return (
        await session.execute(
            text(
                "SELECT id, canonical_term_en FROM ontology_terms "
                "WHERE term_type='function' AND status='active' "
                "AND canonical_term_en IS NOT NULL AND canonical_term_en <> '' "
                "AND canonical_term_en ~ '[a-zA-Z]' "
                "ORDER BY id LIMIT 1"
            )
        )
    ).first()


# --------------------------------------------------------------------------- #
# circuit_type mapping
# --------------------------------------------------------------------------- #


def test_map_circuit_type_functional_classifications_to_network():
    # every mirror functional classification is a distributed functional network
    for raw in (
        "cognitive_control_circuit",
        "sensory_circuit",
        "motor_circuit",
        "limbic_circuit",
        "language_related",
        "memory_related",
        "default_mode_related",
        "attention_related",
        "reward_related",
        "salience_related",
    ):
        assert cms.map_circuit_type(raw) == "network", raw


def test_map_circuit_type_uncertain_and_passthrough():
    assert cms.map_circuit_type("uncertain_circuit") == "uncertain"
    assert cms.map_circuit_type("unknown") == "uncertain"
    assert cms.map_circuit_type(None) == "uncertain"
    assert cms.map_circuit_type("") == "uncertain"
    for raw in ("network", "pathway", "reflex", "functional_loop"):
        assert cms.map_circuit_type(raw) == raw


def test_map_circuit_type_unmapped_raises():
    with pytest.raises(cms.CircuitMappingError, match="unmapped mirror circuit_type"):
        cms.map_circuit_type("emotion_circuit_v2")


# --------------------------------------------------------------------------- #
# region / connection role mapping
# --------------------------------------------------------------------------- #


def test_map_circuit_region_role_rules():
    assert cms.map_circuit_region_role("participant") == "core_region"
    assert cms.map_circuit_region_role("source") == "input"
    assert cms.map_circuit_region_role("target") == "output"
    assert cms.map_circuit_region_role("intermediate") == "intermediate"
    # non-terminal topology roles -> intermediate
    assert cms.map_circuit_region_role("hub") == "intermediate"
    assert cms.map_circuit_region_role("relay") == "intermediate"
    assert cms.map_circuit_region_role("modulator") == "intermediate"


def test_map_circuit_region_role_unmapped_raises():
    with pytest.raises(cms.CircuitMappingError):
        cms.map_circuit_region_role("unknown")
    with pytest.raises(cms.CircuitMappingError):
        cms.map_circuit_region_role(None)
    with pytest.raises(cms.CircuitMappingError):
        cms.map_circuit_region_role("gateway")


def test_map_circuit_connection_role_rules():
    assert cms.map_circuit_connection_role("feedforward") == "feedforward"
    assert cms.map_circuit_connection_role("feedback") == "feedback"
    assert cms.map_circuit_connection_role("supporting") == "supporting"
    assert cms.map_circuit_connection_role("unknown") == "supporting"
    assert cms.map_circuit_connection_role(None) == "supporting"
    with pytest.raises(cms.CircuitMappingError):
        cms.map_circuit_connection_role("lateral")


# --------------------------------------------------------------------------- #
# provenance
# --------------------------------------------------------------------------- #


def test_build_circuit_provenance_complete():
    mid = uuid.uuid4()
    rid = uuid.uuid4()
    cid = uuid.uuid4()
    fid = uuid.uuid4()
    prov = cms.build_circuit_provenance(
        mid, [rid], [cid], [fid], mapping_confidence=0.75
    )
    assert set(prov.keys()) == {
        "source_mirror_circuit_id",
        "source_region_ids",
        "source_connection_ids",
        "source_function_ids",
        "mapping_version",
        "mapping_confidence",
    }
    assert prov["source_mirror_circuit_id"] == str(mid)
    assert prov["source_region_ids"] == [str(rid)]
    assert prov["source_connection_ids"] == [str(cid)]
    assert prov["source_function_ids"] == [str(fid)]
    assert prov["mapping_version"] == cms.DEFAULT_MAPPING_VERSION
    assert prov["mapping_confidence"] == 0.75


def test_build_circuit_provenance_defaults_and_validation():
    prov = cms.build_circuit_provenance(uuid.uuid4(), [], [], [])
    assert prov["mapping_confidence"] is None
    with pytest.raises(cms.CircuitMappingError):
        cms.build_circuit_provenance("", [], [], [])
    with pytest.raises(cms.CircuitMappingError):
        cms.build_circuit_provenance(uuid.uuid4(), [], [], [], mapping_version="")
    with pytest.raises(cms.CircuitMappingError):
        cms.build_circuit_provenance(uuid.uuid4(), [], [], [], mapping_confidence=1.5)


# --------------------------------------------------------------------------- #
# function resolution (reuses function_term_service; never creates terms)
# --------------------------------------------------------------------------- #


def test_resolve_circuit_function_by_term_id_anchor(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            row = await _get_active_function_term(s)
            res = await cms.resolve_circuit_function(s, term_id=row[0])
            assert res.term_id == row[0]
            assert res.state in VALID_ANCHOR_STATES

    _run(_t())


def test_resolve_circuit_function_by_exact_text(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            row = await _get_active_function_term(s)
            res = await cms.resolve_circuit_function(s, term_en=row[1])
            assert res.term_id == row[0]
            assert res.state == STATE_GROUNDED_ACTIVE
            assert res.is_function_term

    _run(_t())


def test_resolve_circuit_function_unresolved_never_creates_term(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            before = (
                await s.execute(
                    text("SELECT count(*) FROM ontology_terms WHERE term_type='function'")
                )
            ).scalar_one()
            res = await cms.resolve_circuit_function(
                s, term_en="zz_no_such_function_ci12_test"
            )
            assert res.state == STATE_UNRESOLVED
            assert res.term_id is None
            after = (
                await s.execute(
                    text("SELECT count(*) FROM ontology_terms WHERE term_type='function'")
                )
            ).scalar_one()
            assert after == before
            assert (
                await s.execute(
                    text("SELECT count(*) FROM ontology_terms WHERE term_code LIKE 'ng:func:zz_no_such%'")
                )
            ).scalar_one() == 0

    _run(_t())


def test_resolve_circuit_function_empty_text_unresolved(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            res = await cms.resolve_circuit_function(s, term_en="", term_cn="")
            assert res.state == STATE_UNRESOLVED

    _run(_t())


# --------------------------------------------------------------------------- #
# connection resolution via provenance
# --------------------------------------------------------------------------- #


def test_resolve_canonical_connection_by_provenance(db):
    fake_mirror_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

    async def _t():
        async with AsyncSessionLocal() as s:
            r1 = await _mk_region(s, "a")
            r2 = await _mk_region(s, "b")
            await s.flush()
            conn = await _mk_connection(s, r1, r2)
            await s.flush()
            await s.execute(
                text(
                    "UPDATE canonical_connections SET provenance_json = "
                    "jsonb_build_object('original_connection_ids', jsonb_build_array(CAST(:mid AS text))) "
                    "WHERE id = :cid"
                ),
                {"mid": str(fake_mirror_id), "cid": conn.id},
            )
            await s.commit()

            resolved = await cms.resolve_canonical_connection(s, fake_mirror_id)
            assert resolved is not None
            assert resolved.id == conn.id
            assert await cms.resolve_canonical_connection(s, uuid.uuid4()) is None

    _run(_t())


# --------------------------------------------------------------------------- #
# dry-run plan (never writes; deterministic)
# --------------------------------------------------------------------------- #


def test_plan_macro_circuit_canonicalization_dry_run(db):
    async def _counts(session):
        rows = {}
        for table in (
            "canonical_circuits",
            "canonical_circuit_regions",
            "canonical_circuit_connections",
            "canonical_circuit_functions",
        ):
            rows[table] = (
                await session.execute(text(f"SELECT count(*) FROM {table}"))
            ).scalar_one()
        return rows

    async def _t():
        async with AsyncSessionLocal() as s:
            before = await _counts(s)
            plan1 = await cms.plan_macro_circuit_canonicalization(s)
            after = await _counts(s)
            plan2 = await cms.plan_macro_circuit_canonicalization(s)
            final = await _counts(s)
            return before, after, final, plan1, plan2

    before, after, final, plan1, plan2 = _run(_t())

    # dry-run never writes
    assert after == before
    assert final == before
    assert plan1["dry_run"] is True

    # deterministic
    assert plan2 == plan1

    # stats: candidates partition into aligned/unresolved/rejected
    stats = plan1["stats"]
    assert stats["candidate_count"] == _MACRO_CIRCUIT_COUNT
    assert (
        stats["aligned_count"] + stats["unresolved_count"] + stats["rejected_count"]
        == stats["candidate_count"]
    )
    assert len(plan1["plans"]) == stats["aligned_count"]
    assert len(plan1["unresolved_circuits"]) == stats["unresolved_count"]
    assert len(plan1["rejected_circuits"]) == stats["rejected_count"]

    # every aligned plan is complete: type/roles in canonical space, full
    # provenance, at least one region member, all members resolved
    for plan in plan1["plans"]:
        assert plan["circuit_type"] in cms._CANONICAL_CIRCUIT_TYPES
        assert plan["species"] == "human"
        assert plan["granularity_level"] == "clinical"
        assert plan["status"] == "proposed"
        assert plan["region_members"], "aligned circuit must have region members"
        assert plan["provenance_json"]["mapping_confidence"] == 1.0
        assert set(plan["provenance_json"].keys()) == {
            "source_mirror_circuit_id",
            "source_region_ids",
            "source_connection_ids",
            "source_function_ids",
            "mapping_version",
            "mapping_confidence",
        }
        assert plan["provenance_json"]["source_mirror_circuit_id"] == plan["mirror_circuit_id"]
        for m in plan["region_members"]:
            assert m["role"] in cms._CANONICAL_REGION_ROLES
            assert m["canonical_region_id"]
            assert m["provenance_json"]["original_role"]
        for m in plan["connection_members"]:
            assert m["role"] in cms._CANONICAL_CONNECTION_ROLES
            assert m["canonical_connection_id"]
        for m in plan["function_members"]:
            assert m["function_term_id"]

    # unresolved/rejected rows carry reasons and mirror ids
    for row in plan1["unresolved_circuits"]:
        assert row["mirror_circuit_id"]
        assert row["failures"]
    for row in plan1["rejected_circuits"]:
        assert row["mirror_circuit_id"]
        assert row["reason"]
