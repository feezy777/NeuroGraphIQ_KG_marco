"""P1.5 Function Triple entity-ization tests (20 acceptance cases).

Scoped rebuilds (unique resource_id) keep tests fast and isolated. Asserts
filter by subject/object ids rather than payload markers.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from app.database import AsyncSessionLocal
from app.models.mirror_kg import (
    MirrorKgTriple,
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
    MirrorKgTripleCreate,
    MirrorPromotionStatus,
    MirrorReviewStatus,
    MirrorStatus,
    TripleObjectType,
    TripleSubjectType,
)
from app.services import (
    function_triple_rebuild_service as ftrs,
    mirror_kg_service as mks,
)

TEST_PREFIX = "p15_test_"

# resource ids created by tests (rebuild-inserted triples carry no p15_test
# payload marker, so teardown deletes triples by resource id)
_TEST_RIDS: set = set()

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
                    model.__table__.c.raw_payload_json["p15_test"].astext.is_not(None)
                ))
            if _TEST_RIDS:
                await session.execute(MirrorKgTriple.__table__.delete().where(
                    MirrorKgTriple.__table__.c.resource_id.in_([str(r) for r in _TEST_RIDS])
                ))
            await session.execute(
                OntologyTerm.__table__.delete().where(
                    OntologyTerm.__table__.c.canonical_term_en.like(f"{TEST_PREFIX}%")
                )
            )
            await session.commit()

    yield
    _run(_cleanup())


def _rid() -> uuid.UUID:
    return uuid.uuid4()


async def _any_candidate_id(session) -> uuid.UUID:
    """A real candidate_brain_regions id (FK target for region functions)."""
    from sqlalchemy import select

    from app.models.candidate import CandidateBrainRegion

    row = (await session.execute(select(CandidateBrainRegion.id).limit(1))).scalar_one_or_none()
    if row is None:
        pytest.skip("no candidate_brain_regions rows available")
    return row


@pytest.fixture()
def rid():
    """Shared real atlas_resources id (FK target for scope isolation)."""

    async def _load():
        from sqlalchemy import text

        async with AsyncSessionLocal() as session:
            row = (await session.execute(text("SELECT id FROM atlas_resources LIMIT 1"))).scalar_one_or_none()
            if row is None:
                pytest.skip("no atlas_resources rows available")
            _TEST_RIDS.add(row)
            return row

    return _run(_load())


@pytest.fixture()
def cand_id():
    """Shared real candidate id for region-function subjects (FK target)."""

    async def _load():
        async with AsyncSessionLocal() as session:
            return await _any_candidate_id(session)

    return _run(_load())


def _term(session, name: str, *, status: str = "active", replaced_by=None) -> OntologyTerm:
    term = OntologyTerm(
        term_code=f"ng:func:{name.replace(' ', '_')}",
        canonical_term_en=name,
        term_type="function",
        status=status,
        created_by="p15_test",
    )
    session.add(term)
    if replaced_by:
        term.replaced_by_term_id = replaced_by
    return term


def _region(session, name: str, *, term_id=None, relation="involved_in",
            resource_id=None, subject_id=cand_id) -> MirrorRegionFunction:
    row = MirrorRegionFunction(
        region_candidate_id=subject_id,
        resource_id=resource_id,
        granularity_level="macro_clinical",
        granularity_family="macro",
        source_atlas="test_atlas",
        function_term=name,
        function_category="cognitive",
        relation_type=relation,
        confidence=0.8,
        mirror_status=MirrorStatus.llm_suggested,
        review_status=MirrorReviewStatus.pending,
        promotion_status=MirrorPromotionStatus.not_promoted,
        raw_payload_json={"p15_test": True},
        term_id=term_id,
    )
    session.add(row)
    return row


async def _projection(session, name: str, *, term_id=None, resource_id=None) -> MirrorProjectionFunction:
    conn = MirrorRegionConnection(
        resource_id=resource_id,
        granularity_level="macro_clinical",
        granularity_family="macro",
        source_atlas="test_atlas",
        connection_type="projection",
        directionality="directed",
        mirror_status=MirrorStatus.llm_suggested,
        review_status=MirrorReviewStatus.pending,
        promotion_status=MirrorPromotionStatus.not_promoted,
        raw_payload_json={"p15_test": True},
    )
    session.add(conn)
    await session.flush()
    row = MirrorProjectionFunction(
        projection_id=conn.id,
        resource_id=resource_id,
        granularity_level="macro_clinical",
        granularity_family="macro",
        source_atlas="test_atlas",
        function_term=name,
        function_category="cognitive",
        relation_type="modulates",
        confidence=0.8,
        mirror_status=MirrorStatus.llm_suggested,
        review_status=MirrorReviewStatus.pending,
        promotion_status=MirrorPromotionStatus.not_promoted,
        raw_payload_json={"p15_test": True},
        term_id=term_id,
    )
    session.add(row)
    return row


async def _circuit(session, name: str, *, term_id=None, resource_id=None) -> MirrorCircuitFunction:
    circ = MirrorRegionCircuit(
        resource_id=resource_id,
        granularity_level="macro_clinical",
        granularity_family="macro",
        source_atlas="test_atlas",
        circuit_name="p15 circuit",
        circuit_type="simple",
        mirror_status=MirrorStatus.llm_suggested,
        review_status=MirrorReviewStatus.pending,
        promotion_status=MirrorPromotionStatus.not_promoted,
        raw_payload_json={"p15_test": True},
    )
    session.add(circ)
    await session.flush()
    row = MirrorCircuitFunction(
        circuit_id=circ.id,
        resource_id=resource_id,
        granularity_level="macro_clinical",
        granularity_family="macro",
        source_atlas="test_atlas",
        function_term_en=name,
        confidence=0.8,
        mirror_status=MirrorStatus.llm_suggested,
        review_status=MirrorReviewStatus.pending,
        promotion_status=MirrorPromotionStatus.not_promoted,
        raw_payload_json={"p15_test": True},
        term_id=term_id,
    )
    session.add(row)
    return row


async def _fn_triples(session, *, scope_rid: uuid.UUID):
    from sqlalchemy import select

    rows = (await session.execute(
        select(MirrorKgTriple).where(
            MirrorKgTriple.object_type == TripleObjectType.function,
            MirrorKgTriple.resource_id == scope_rid,
        )
    )).scalars().all()
    return rows


async def _rebuild(session, scope_rid: uuid.UUID, *, apply=False):
    return await ftrs.rebuild_function_triples(
        session,
        dry_run=not apply,
        scope_resource_id=scope_rid,
    )


# ---------------------------------------------------------------- 1-3 entity ids


def test_01_region_function_triple_object_id(db, cand_id, rid):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}region fn")
            await session.flush()
            row = _region(session, f"{TEST_PREFIX}region fn", term_id=term.id, resource_id=rid,
                          subject_id=cand_id)
            await session.flush()
            stats = await _rebuild(session, rid, apply=True)
            await session.flush()
            rows = await _fn_triples(session, scope_rid=rid)
            assert rows and all(r.object_id == term.id for r in rows)
            assert rows[0].subject_id == row.region_candidate_id
    _run(_case())


def test_02_projection_function_triple_object_id(db, rid):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}proj fn")
            await session.flush()
            row = await _projection(session, f"{TEST_PREFIX}proj fn", term_id=term.id, resource_id=rid)
            await session.flush()
            await _rebuild(session, rid, apply=True)
            await session.flush()
            rows = await _fn_triples(session, scope_rid=rid)
            assert rows and all(r.object_id == term.id for r in rows)
            assert rows[0].subject_type == TripleSubjectType.connection
            assert rows[0].predicate == "modulates_function"
    _run(_case())


def test_03_circuit_function_triple_object_id(db, rid):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}circ fn")
            await session.flush()
            row = await _circuit(session, f"{TEST_PREFIX}circ fn", term_id=term.id, resource_id=rid)
            await session.flush()
            await _rebuild(session, rid, apply=True)
            await session.flush()
            rows = await _fn_triples(session, scope_rid=rid)
            assert rows and all(r.object_id == term.id for r in rows)
            assert rows[0].subject_type == TripleSubjectType.circuit
            assert rows[0].predicate == "associated_with_function"
    _run(_case())


# ---------------------------------------------------------------- 4-8 term rules


def test_04_canonical_resolution_merged(db, cand_id, rid):
    async def _case():
        async with AsyncSessionLocal() as session:
            canon = _term(session, f"{TEST_PREFIX}canonical")
            await session.flush()
            old = _term(session, f"{TEST_PREFIX}old", status="merged", replaced_by=canon.id)
            await session.flush()
            cand_id = await _any_candidate_id(session)
            _region(session, f"{TEST_PREFIX}old", term_id=old.id, resource_id=rid,
                    subject_id=cand_id)
            await session.flush()
            await _rebuild(session, rid, apply=True)
            await session.flush()
            rows = await _fn_triples(session, scope_rid=rid)
            assert rows and all(r.object_id == canon.id for r in rows)
    _run(_case())


def test_05_proposed_term_projected(db, cand_id, rid):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}proposed", status="proposed")
            await session.flush()
            cand_id = await _any_candidate_id(session)
            _region(session, f"{TEST_PREFIX}proposed", term_id=term.id, resource_id=rid,
                    subject_id=cand_id)
            await session.flush()
            await _rebuild(session, rid, apply=True)
            await session.flush()
            rows = await _fn_triples(session, scope_rid=rid)
            assert rows and all(r.object_id == term.id for r in rows)
    _run(_case())


def test_06_merged_redirect_never_keeps_old_object(db, cand_id, rid):
    async def _case():
        async with AsyncSessionLocal() as session:
            canon = _term(session, f"{TEST_PREFIX}canonical6")
            await session.flush()
            old = _term(session, f"{TEST_PREFIX}old6", status="merged", replaced_by=canon.id)
            await session.flush()
            cand_id = await _any_candidate_id(session)
            _region(session, f"{TEST_PREFIX}old6", term_id=old.id, resource_id=rid,
                    subject_id=cand_id)
            await session.flush()
            await _rebuild(session, rid, apply=True)
            await session.flush()
            rows = await _fn_triples(session, scope_rid=rid)
            assert rows and all(r.object_id != old.id for r in rows)
            assert all(r.object_id == canon.id for r in rows)
    _run(_case())


def test_07_deprecated_not_projected(db, cand_id, rid):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}deprecated", status="deprecated")
            await session.flush()
            cand_id = await _any_candidate_id(session)
            _region(session, f"{TEST_PREFIX}deprecated", term_id=term.id, resource_id=rid,
                    subject_id=cand_id)
            await session.flush()
            stats = await _rebuild(session, rid)
            rows = await _fn_triples(session, scope_rid=rid)
            assert not rows
            assert stats.filtered_invalid_count >= 1
    _run(_case())


def test_08_invalid_type_not_projected(db, cand_id, rid):
    async def _case():
        async with AsyncSessionLocal() as session:
            region_term = OntologyTerm(
                term_code="ng:region:p15_brain", canonical_term_en="p15 brain",
                term_type="region", status="active", created_by="p15_test",
            )
            session.add(region_term)
            await session.flush()
            cand_id = await _any_candidate_id(session)
            _region(session, "p15 brain", term_id=region_term.id, resource_id=rid,
                    subject_id=cand_id)
            await session.flush()
            stats = await _rebuild(session, rid)
            rows = await _fn_triples(session, scope_rid=rid)
            assert not rows
            assert stats.filtered_invalid_count >= 1
    _run(_case())


# ---------------------------------------------------------------- 9-13 identity


def test_09_object_label_is_canonical_snapshot(db, cand_id, rid):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}snapshot")
            await session.flush()
            cand_id = await _any_candidate_id(session)
            _region(session, f"{TEST_PREFIX}SNAPSHOT!", term_id=term.id, resource_id=rid,
                    subject_id=cand_id)
            await session.flush()
            await _rebuild(session, rid, apply=True)
            await session.flush()
            rows = await _fn_triples(session, scope_rid=rid)
            assert rows and all(r.object_label == term.canonical_term_en for r in rows)
    _run(_case())


def test_10_source_text_not_identity(db, rid):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}identity")
            await session.flush()
            sid = await _any_candidate_id(session)
            await session.flush()
            _region(session, f"{TEST_PREFIX}identity", term_id=term.id, resource_id=rid, subject_id=sid)
            _region(session, f"{TEST_PREFIX}IDENTITY", term_id=term.id, resource_id=rid, subject_id=sid)
            await session.flush()
            stats = await _rebuild(session, rid)
            assert stats.desired_function_triples == 1
    _run(_case())


def test_11_canonical_key_uses_object_id(db):
    from app.services.triple_consolidation_service import normalize_triple_key

    oid = uuid.uuid4()
    sid = uuid.uuid4()
    k1 = normalize_triple_key(
        subject_type="region_candidate", subject_id=sid, subject_label="x",
        predicate="involved_in_function", object_type="function", object_id=oid,
        object_label="fear extinction", triple_scope="same_granularity",
        source_atlas="a", granularity_level="g", granularity_family=None,
        resource_id=None, batch_id=None,
    )
    k2 = normalize_triple_key(
        subject_type="region_candidate", subject_id=sid, subject_label="x",
        predicate="involved_in_function", object_type="function", object_id=oid,
        object_label="fear_extinction", triple_scope="same_granularity",
        source_atlas="a", granularity_level="g", granularity_family=None,
        resource_id=None, batch_id=None,
    )
    assert k1 == k2  # same entity SPO → same canonical key despite label text


def test_12_same_term_different_text_no_duplicate(db, rid):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}dup")
            await session.flush()
            sid = await _any_candidate_id(session)
            await session.flush()
            _region(session, f"{TEST_PREFIX}dup", term_id=term.id, resource_id=rid, subject_id=sid)
            _region(session, f"{TEST_PREFIX}dup!", term_id=term.id, resource_id=rid, subject_id=sid)
            await session.flush()
            stats = await _rebuild(session, rid)
            assert stats.desired_function_triples == 1
    _run(_case())


def test_13_multi_source_spo_lineage_preserved(db, rid):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}multi")
            await session.flush()
            sid = await _any_candidate_id(session)
            await session.flush()
            r1 = _region(session, f"{TEST_PREFIX}multi a", term_id=term.id, resource_id=rid, subject_id=sid)
            r2 = _region(session, f"{TEST_PREFIX}multi b", term_id=term.id, resource_id=rid, subject_id=sid)
            await session.flush()
            await _rebuild(session, rid, apply=True)
            await session.flush()
            rows = await _fn_triples(session, scope_rid=rid)
            assert len(rows) == 1
            prov = (rows[0].raw_payload_json or {}).get("provenance", {})
            ids = prov.get("source_relation_ids", [])
            assert str(r1.id) in ids and str(r2.id) in ids
    _run(_case())


# ---------------------------------------------------------------- 14-18


def test_14_function_association_never_projects(db, rid):
    async def _case():
        async with AsyncSessionLocal() as session:
            circ = MirrorRegionCircuit(
                resource_id=rid,
                granularity_level="macro_clinical", granularity_family="macro",
                source_atlas="test_atlas", circuit_name="p15 assoc circuit",
                circuit_type="simple", function_association="p15 assoc text",
                mirror_status=MirrorStatus.llm_suggested,
                review_status=MirrorReviewStatus.pending,
                promotion_status=MirrorPromotionStatus.not_promoted,
                raw_payload_json={"p15_test": True},
            )
            session.add(circ)
            await session.flush()
            await _rebuild(session, rid)
            rows = await _fn_triples(session, scope_rid=rid)
            assert not rows
    _run(_case())


def test_15_circuit_relation_projects_triple(db, rid):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}circ rel")
            await session.flush()
            await _circuit(session, f"{TEST_PREFIX}circ rel", term_id=term.id, resource_id=rid)
            await session.flush()
            await _rebuild(session, rid, apply=True)
            await session.flush()
            rows = await _fn_triples(session, scope_rid=rid)
            assert rows and rows[0].object_id == term.id
            assert rows[0].subject_type == TripleSubjectType.circuit
    _run(_case())


def test_16_rebuild_idempotent(db, cand_id, rid):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}idem")
            await session.flush()
            cand_id = await _any_candidate_id(session)
            _region(session, f"{TEST_PREFIX}idem", term_id=term.id, resource_id=rid,
                    subject_id=cand_id)
            await session.flush()
            await _rebuild(session, rid, apply=True)
            await session.commit()
            second = await _rebuild(session, rid, apply=True)
            assert second.inserted_count == 0
            assert second.stale_deleted_count == 0
            assert second.upgraded_count == 0
    _run(_case())


def test_17_stale_triple_safe_handling(db, cand_id, rid):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}stale")
            await session.flush()
            sid = await _any_candidate_id(session)
            await session.flush()
            row = _region(session, f"{TEST_PREFIX}stale", term_id=term.id, resource_id=rid, subject_id=sid)
            await session.flush()
            # legacy NULL-object triple for a subject whose relation was deleted
            mks.create_mirror_triple(session, MirrorKgTripleCreate(
                subject_type=TripleSubjectType.region_candidate,
                subject_id=uuid.uuid4(),
                subject_label="orphan",
                predicate="associated_with_function",
                object_type=TripleObjectType.function,
                object_id=None,
                object_label=f"{TEST_PREFIX}stale orphan",
                granularity_level="macro_clinical",
                source_atlas="test_atlas",
                resource_id=rid,
                raw_payload_json={"p15_test": True},
            ))
            await session.flush()
            await _rebuild(session, rid, apply=True)
            await session.flush()
            rows = await _fn_triples(session, scope_rid=rid)
            assert len(rows) == 1  # orphan legacy triple removed, real one kept
            assert rows[0].object_id == term.id
    _run(_case())


def test_18_non_function_triples_unaffected(db, cand_id, rid):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}mixed")
            await session.flush()
            cand_id = await _any_candidate_id(session)
            _region(session, f"{TEST_PREFIX}mixed", term_id=term.id, resource_id=rid,
                    subject_id=cand_id)
            conn = MirrorRegionConnection(
                source_region_candidate_id=None, target_region_candidate_id=None,
                resource_id=rid,
                granularity_level="macro_clinical", granularity_family="macro",
                source_atlas="test_atlas", connection_type="structural_connection",
                directionality="directed",
                mirror_status=MirrorStatus.llm_suggested,
                review_status=MirrorReviewStatus.pending,
                promotion_status=MirrorPromotionStatus.not_promoted,
                raw_payload_json={"p15_test": True},
            )
            session.add(conn)
            await session.flush()
            # pre-existing non-function triple that must survive the rebuild
            await mks.create_mirror_triple(session, MirrorKgTripleCreate(
                subject_type=TripleSubjectType.region_candidate,
                subject_id=uuid.uuid4(),
                subject_label="s",
                predicate="structurally_connects_to",
                object_type=TripleObjectType.region_candidate,
                object_id=uuid.uuid4(),
                object_label="t",
                granularity_level="macro_clinical",
                source_atlas="test_atlas",
                resource_id=rid,
                raw_payload_json={"p15_test": True},
            ))
            await session.flush()
            await _rebuild(session, rid, apply=True)
            await session.flush()
            conn_rows = (await session.execute(
                __import__("sqlalchemy").select(MirrorKgTriple).where(
                    MirrorKgTriple.predicate == "structurally_connects_to",
                    MirrorKgTriple.resource_id == rid,
                )
            )).scalars().all()
            assert len(conn_rows) == 1  # untouched by function rebuild
    _run(_case())


# ---------------------------------------------------------------- 19-20 global


def test_19_no_orphan_function_object_ids():
    from sqlalchemy import text

    async def _case():
        async with AsyncSessionLocal() as session:
            bad = (await session.execute(text(
                """SELECT count(*) FROM mirror_kg_triples t
                   LEFT JOIN ontology_terms ot ON ot.id = t.object_id
                   WHERE t.object_type='function' AND t.object_id IS NOT NULL
                     AND (ot.id IS NULL OR ot.term_type <> 'function'
                          OR ot.status IN ('merged','deprecated')
                          OR ot.term_code NOT LIKE 'ng:func:%')"""
            ))).scalar_one()
            assert bad == 0
    _run(_case())


def test_20_no_null_object_function_triples():
    from sqlalchemy import text

    async def _case():
        async with AsyncSessionLocal() as session:
            nulls = (await session.execute(text(
                "SELECT count(*) FROM mirror_kg_triples WHERE object_type='function' AND object_id IS NULL"
            ))).scalar_one()
            assert nulls == 0
    _run(_case())
