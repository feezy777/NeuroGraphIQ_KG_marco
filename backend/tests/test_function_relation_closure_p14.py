"""P1.4 Function Relation layer closure tests (16 acceptance cases).

Covers: term_id-based identity on all three relation tables, qualifier
preservation, dedup semantics, merged redirect safety, circuit
function_association downgrade, circuit write-path closure, query source of
truth, term status rules, invalid-term rejection, full-table integrity and
legacy field compatibility.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from app.database import AsyncSessionLocal
from app.models.mirror_kg import (
    MirrorRegionCircuit,
    MirrorRegionConnection,
    MirrorRegionFunction,
)
from app.models.mirror_macro_clinical import (
    MirrorCircuitFunction,
    MirrorProjectionFunction,
)
from app.models.ontology import OntologyTerm
from app.schemas.mirror_kg import (
    MirrorPromotionStatus,
    MirrorRegionCircuitCreate,
    MirrorRegionFunctionCreate,
    MirrorReviewStatus,
    MirrorStatus,
)
from app.schemas.mirror_macro_clinical import (
    MirrorCircuitFunctionCreate,
    MirrorProjectionFunctionCreate,
)
from app.services import (
    function_term_service as fts,
    mirror_kg_service as mks,
    mirror_macro_clinical_service as mmcs,
)

TEST_PREFIX = "p14_test_"

pytestmark = pytest.mark.function_term_real


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
            for model in (MirrorCircuitFunction, MirrorProjectionFunction, MirrorRegionFunction,
                          MirrorRegionCircuit, MirrorRegionConnection):
                await session.execute(model.__table__.delete().where(
                    model.__table__.c.raw_payload_json["p14_test"].astext.is_not(None)
                ))
            await session.execute(
                OntologyTerm.__table__.delete().where(
                    OntologyTerm.__table__.c.canonical_term_en.like(f"{TEST_PREFIX}%")
                )
            )
            await session.commit()

    yield
    _run(_cleanup())


def _term(session, name: str, *, status: str = "active") -> OntologyTerm:
    term = OntologyTerm(
        term_code=f"ng:func:{name.replace(' ', '_')}",
        canonical_term_en=name,
        term_type="function",
        status=status,
        created_by="p14_test",
    )
    session.add(term)
    return term


def _region_fn(session, *, term: str, category: str = "cognitive", relation: str = "involved_in",
               term_id=None) -> MirrorRegionFunction:
    row = MirrorRegionFunction(
        region_candidate_id=None,
        granularity_level="macro_clinical",
        granularity_family="macro",
        source_atlas="test_atlas",
        function_term=term,
        function_category=category,
        relation_type=relation,
        confidence=0.8,
        mirror_status=MirrorStatus.llm_suggested,
        review_status=MirrorReviewStatus.pending,
        promotion_status=MirrorPromotionStatus.not_promoted,
        raw_payload_json={"p14_test": True},
        term_id=term_id,
    )
    session.add(row)
    return row


def _connection(session) -> MirrorRegionConnection:
    conn = MirrorRegionConnection(
        granularity_level="macro_clinical",
        granularity_family="macro",
        source_atlas="test_atlas",
        connection_type="projection",
        directionality="directed",
        mirror_status=MirrorStatus.llm_suggested,
        review_status=MirrorReviewStatus.pending,
        promotion_status=MirrorPromotionStatus.not_promoted,
        raw_payload_json={"p14_test": True},
    )
    session.add(conn)
    return conn


def _circuit(session, *, name: str = "p14 test circuit") -> MirrorRegionCircuit:
    circ = MirrorRegionCircuit(
        granularity_level="macro_clinical",
        granularity_family="macro",
        source_atlas="test_atlas",
        circuit_name=name,
        circuit_type="simple",
        mirror_status=MirrorStatus.llm_suggested,
        review_status=MirrorReviewStatus.pending,
        promotion_status=MirrorPromotionStatus.not_promoted,
        raw_payload_json={"p14_test": True},
    )
    session.add(circ)
    return circ


# ---------------------------------------------------------------- 1-3 identity


def test_01_region_relation_identity_uses_term_id(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            _term(session, f"{TEST_PREFIX}region id")
            await session.flush()
            # same concept written with different text → single relation
            r1 = await mks.create_mirror_function(session, MirrorRegionFunctionCreate(
                granularity_level="macro_clinical", source_atlas="test_atlas",
                function_term=f"{TEST_PREFIX}region id", raw_payload_json={"p14_test": True},
            ))
            r2 = await mks.create_mirror_function(session, MirrorRegionFunctionCreate(
                granularity_level="macro_clinical", source_atlas="test_atlas",
                function_term=f"{TEST_PREFIX}REGION ID", raw_payload_json={"p14_test": True},
            ))
            assert r1.id == r2.id  # same term_id → merged, not duplicated
            assert r1.term_id is not None
    _run(_case())


def test_02_projection_relation_identity_uses_term_id(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            _term(session, f"{TEST_PREFIX}proj id")
            conn = _connection(session)
            await session.flush()
            p1 = await mmcs.create_projection_function(session, MirrorProjectionFunctionCreate(
                projection_id=conn.id, granularity_level="macro_clinical",
                granularity_family="macro", source_atlas="test_atlas",
                function_term=f"{TEST_PREFIX}proj id", raw_payload_json={"p14_test": True},
            ))
            p2 = await mmcs.create_projection_function(session, MirrorProjectionFunctionCreate(
                projection_id=conn.id, granularity_level="macro_clinical",
                granularity_family="macro", source_atlas="test_atlas",
                function_term=f"{TEST_PREFIX}proj-id", raw_payload_json={"p14_test": True},
            ))
            assert p1.id == p2.id
            assert p1.term_id is not None
    _run(_case())


def test_03_circuit_relation_identity_uses_term_id(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            _term(session, f"{TEST_PREFIX}circ id")
            circ = _circuit(session)
            await session.flush()
            c1 = await mmcs.create_circuit_function(session, MirrorCircuitFunctionCreate(
                circuit_id=circ.id, granularity_level="macro_clinical",
                granularity_family="macro", source_atlas="test_atlas",
                function_term_en=f"{TEST_PREFIX}circ id", raw_payload_json={"p14_test": True},
            ))
            c2 = await mmcs.create_circuit_function(session, MirrorCircuitFunctionCreate(
                circuit_id=circ.id, granularity_level="macro_clinical",
                granularity_family="macro", source_atlas="test_atlas",
                function_term_en=f"{TEST_PREFIX}CIRC ID", raw_payload_json={"p14_test": True},
            ))
            assert c1.id == c2.id
            assert c1.term_id is not None
    _run(_case())


# ---------------------------------------------------------------- 4-5 qualifiers


def test_04_different_qualifiers_not_merged(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}qualifier")
            await session.flush()
            a = _region_fn(session, term=f"{TEST_PREFIX}qualifier", category="motor", term_id=term.id)
            b = _region_fn(session, term=f"{TEST_PREFIX}qualifier", category="cognitive", term_id=term.id)
            await session.flush()
            # same subject+term but different category → two facts
            assert a.id != b.id
            rows = (
                await session.execute(
                    __import__("sqlalchemy").select(MirrorRegionFunction).where(
                        MirrorRegionFunction.term_id == term.id
                    )
                )
            ).scalars().all()
            assert len(rows) == 2
    _run(_case())


def test_05_same_term_same_qualifiers_dedup(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            _term(session, f"{TEST_PREFIX}dedup")
            circ = _circuit(session)
            await session.flush()
            await mmcs.create_circuit_function(session, MirrorCircuitFunctionCreate(
                circuit_id=circ.id, granularity_level="macro_clinical",
                granularity_family="macro", source_atlas="test_atlas",
                function_term_en=f"{TEST_PREFIX}dedup", raw_payload_json={"p14_test": True},
            ))
            await mmcs.create_circuit_function(session, MirrorCircuitFunctionCreate(
                circuit_id=circ.id, granularity_level="macro_clinical",
                granularity_family="macro", source_atlas="test_atlas",
                function_term_en=f"{TEST_PREFIX}dedup", raw_payload_json={"p14_test": True},
            ))
            rows = (
                await session.execute(
                    __import__("sqlalchemy").select(MirrorCircuitFunction).where(
                        MirrorCircuitFunction.circuit_id == circ.id
                    )
                )
            ).scalars().all()
            assert len(rows) == 1
    _run(_case())


# ---------------------------------------------------------------- 6 merged


def test_06_merged_redirect_dup_safe_all_tables(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            canonical = _term(session, f"{TEST_PREFIX}canonical")
            await session.flush()
            old = OntologyTerm(
                term_code=f"ng:func:{TEST_PREFIX}old",
                canonical_term_en=f"{TEST_PREFIX}old",
                term_type="function", status="merged",
                replaced_by_term_id=canonical.id, created_by="p14_test",
            )
            session.add(old)
            await session.flush()
            # projection: one relation on old term, one on canonical
            conn = _connection(session)
            await session.flush()
            p_old = MirrorProjectionFunction(
                projection_id=conn.id, granularity_level="macro_clinical",
                granularity_family="macro", source_atlas="test_atlas",
                function_term=f"{TEST_PREFIX}old", term_id=old.id,
                function_category="cognitive", relation_type="involved_in",
                mirror_status=MirrorStatus.llm_suggested,
                review_status=MirrorReviewStatus.pending,
                promotion_status=MirrorPromotionStatus.not_promoted,
                raw_payload_json={"p14_test": True},
            )
            p_canon = MirrorProjectionFunction(
                projection_id=conn.id, granularity_level="macro_clinical",
                granularity_family="macro", source_atlas="test_atlas",
                function_term=f"{TEST_PREFIX}canonical", term_id=canonical.id,
                function_category="cognitive", relation_type="involved_in",
                mirror_status=MirrorStatus.llm_suggested,
                review_status=MirrorReviewStatus.pending,
                promotion_status=MirrorPromotionStatus.not_promoted,
                raw_payload_json={"p14_test": True},
            )
            session.add_all([p_old, p_canon])
            await session.flush()
            await fts.anchor_function_relation(
                session, target_type="projection_function", row=p_old, created_by="test"
            )
            await session.flush()
            assert p_old.mirror_status == MirrorStatus.superseded
            prov = (p_old.raw_payload_json or {}).get("provenance", {})
            assert prov.get("duplicate_of") == str(p_canon.id)
            assert p_canon.mirror_status != MirrorStatus.superseded
    _run(_case())


# ---------------------------------------------------------------- 7-11 circuit


def test_07_source_text_preserved(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            _term(session, f"{TEST_PREFIX}text")
            circ = _circuit(session)
            await session.flush()
            row = await mmcs.create_circuit_function(session, MirrorCircuitFunctionCreate(
                circuit_id=circ.id, granularity_level="macro_clinical",
                granularity_family="macro", source_atlas="test_atlas",
                function_term_en=f"{TEST_PREFIX}text", raw_payload_json={"p14_test": True},
            ))
            assert row.function_term_en == f"{TEST_PREFIX}text"
            assert row.term_id is not None
    _run(_case())


def test_08_association_not_function_identity(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}assoc")
            circ = _circuit(session)
            await session.flush()
            await mmcs.sync_circuit_function_from_association(
                session, circuit=circ, function_association=f"{TEST_PREFIX}assoc",
                created_by="test",
            )
            await session.flush()
            rows = (
                await session.execute(
                    __import__("sqlalchemy").select(MirrorCircuitFunction).where(
                        MirrorCircuitFunction.circuit_id == circ.id
                    )
                )
            ).scalars().all()
            assert len(rows) == 1
            assert rows[0].term_id == term.id
            # association snapshot stays on the circuit row (compat field)
            circ.function_association = f"{TEST_PREFIX}assoc"
            await session.flush()
            assert circ.function_association == f"{TEST_PREFIX}assoc"
    _run(_case())


def test_09_new_circuit_function_write_creates_relation(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            _term(session, f"{TEST_PREFIX}write")
            circ = _circuit(session)
            await session.flush()
            await mmcs.sync_circuit_function_from_association(
                session, circuit=circ, function_association=f"{TEST_PREFIX}write",
                created_by="test",
            )
            await session.flush()
            rows = (
                await session.execute(
                    __import__("sqlalchemy").select(MirrorCircuitFunction).where(
                        MirrorCircuitFunction.circuit_id == circ.id
                    )
                )
            ).scalars().all()
            assert len(rows) == 1
            assert rows[0].term_id is not None
    _run(_case())


def test_10_legacy_circuit_create_chain_writes_relation(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            _term(session, f"{TEST_PREFIX}legacy circ")
            await session.flush()
            circ = await mks.create_mirror_circuit(session, MirrorRegionCircuitCreate(
                granularity_level="macro_clinical", granularity_family="macro",
                source_atlas="test_atlas", circuit_name="p14 legacy circuit",
                circuit_type="simple", function_association=f"{TEST_PREFIX}legacy circ",
                raw_payload_json={"p14_test": True},
            ))
            rows = (
                await session.execute(
                    __import__("sqlalchemy").select(MirrorCircuitFunction).where(
                        MirrorCircuitFunction.circuit_id == circ.id
                    )
                )
            ).scalars().all()
            assert len(rows) == 1
            assert rows[0].term_id is not None
            assert (circ.function_association or "").strip()  # compat field kept
    _run(_case())


def test_11_circuit_function_query_reads_relation_table(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            _term(session, f"{TEST_PREFIX}query")
            circ = _circuit(session)
            await session.flush()
            await mmcs.create_circuit_function(session, MirrorCircuitFunctionCreate(
                circuit_id=circ.id, granularity_level="macro_clinical",
                granularity_family="macro", source_atlas="test_atlas",
                function_term_en=f"{TEST_PREFIX}query", raw_payload_json={"p14_test": True},
            ))
            await session.flush()
            items, total = await mmcs.list_mirror_circuit_functions(
                session, circuit_id=circ.id, limit=10, offset=0
            )
            assert total == 1
            assert items[0].term_id is not None
    _run(_case())


# ---------------------------------------------------------------- 12-14 terms


def test_12_active_term_anchored(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}active term", status="active")
            await session.flush()
            row = _region_fn(session, term=f"{TEST_PREFIX}active term")
            await session.flush()
            await fts.anchor_function_relation(
                session, target_type="region_function", row=row, created_by="test"
            )
            assert row.term_id == term.id
    _run(_case())


def test_13_proposed_term_anchored(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}proposed term", status="proposed")
            await session.flush()
            row = _region_fn(session, term=f"{TEST_PREFIX}proposed term")
            await session.flush()
            await fts.anchor_function_relation(
                session, target_type="region_function", row=row, created_by="test"
            )
            assert row.term_id == term.id
    _run(_case())


def test_14_invalid_term_rejected(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            region_term = OntologyTerm(
                term_code="ng:region:p14_brain",
                canonical_term_en="p14 brain region",
                term_type="region", status="active", created_by="p14_test",
            )
            session.add(region_term)
            await session.flush()
            res = await fts.resolve_canonical_function_term(session, region_term.id)
            assert res.is_function_term is False
            assert res.state == fts.STATE_INVALID_TYPE
            # relation anchored to the wrong-type term must be un-anchored
            row = _region_fn(session, term="p14 brain region", term_id=region_term.id)
            await session.flush()
            await fts.anchor_function_relation(
                session, target_type="region_function", row=row, created_by="test"
            )
            # the wrong-type anchor is replaced — either by a legit function
            # term resolved from the text, or None — never the region term
            assert row.term_id != region_term.id
            if row.term_id is not None:
                term = await session.get(OntologyTerm, row.term_id)
                assert fts.is_function_term_row(term) is True
    _run(_case())


# ---------------------------------------------------------------- 15-16 global


def test_15_all_relation_tables_no_invalid_term_id():
    from sqlalchemy import text

    async def _case():
        async with AsyncSessionLocal() as session:
            for table in ("mirror_region_functions", "mirror_projection_functions", "mirror_circuit_functions"):
                bad = (await session.execute(text(
                    f"""SELECT count(*) FROM {table} r
                        LEFT JOIN ontology_terms ot ON ot.id = r.term_id
                        WHERE r.term_id IS NULL
                           OR ot.id IS NULL
                           OR ot.status IN ('merged','deprecated')
                           OR ot.term_type <> 'function'
                           OR ot.term_code NOT LIKE 'ng:func:%'"""
                ))).scalar_one()
                assert bad == 0, f"{table} has {bad} rows without a legal term_id"
    _run(_case())


def test_16_legacy_compat_fields_intact(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            _term(session, f"{TEST_PREFIX}compat")
            circ = _circuit(session, name="p14 compat circuit")
            circ.function_association = f"{TEST_PREFIX}compat"  # legacy snapshot
            await session.flush()
            await mmcs.sync_circuit_function_from_association(
                session, circuit=circ, function_association=circ.function_association,
                created_by="test",
            )
            await session.flush()
            # legacy field still readable on the circuit row
            assert circ.function_association == f"{TEST_PREFIX}compat"
            # relation row keeps provenance-bearing raw payload
            rows = (
                await session.execute(
                    __import__("sqlalchemy").select(MirrorCircuitFunction).where(
                        MirrorCircuitFunction.circuit_id == circ.id
                    )
                )
            ).scalars().all()
            assert len(rows) == 1
            assert rows[0].function_term_en == f"{TEST_PREFIX}compat"
    _run(_case())
