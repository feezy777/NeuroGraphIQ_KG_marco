"""P1.7 Mirror → Final Function promotion tests (30 acceptance cases).

Promotes small scoped samples through the real promotion functions and
verifies: canonical term identity, active-only gate, parent-subject rule,
idempotency, Final Function Triple projection (object_id = ontology_terms.id,
subject = Final entity id), transaction atomicity and the Final integrity
checker.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select, text

from app.database import AsyncSessionLocal
from app.models.candidate import CandidateBrainRegion
from app.models.mirror_review import MirrorHumanReviewRecord
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
from app.models.final_kg import FinalKgTriple, FinalRegionFunction
from app.models.final_macro_clinical import (
    FinalCircuitFunction,
    FinalProjectionFunction,
    FinalProjection,
)
from app.models.final_kg import FinalRegionCircuit
from app.schemas.mirror_kg import (
    MirrorPromotionStatus,
    MirrorReviewStatus,
    MirrorStatus,
)
from app.services import (
    final_function_promotion_service as ffps,
    final_macro_clinical_promotion_service as fmcps,
    function_term_service as fts,
    mirror_kg_service as mks,
    mirror_macro_clinical_service as mmcs,
)


TEST_PREFIX = "p17_test_"
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
            for model in (FinalKgTriple, FinalRegionFunction, FinalRegionCircuit):
                await session.execute(model.__table__.delete().where(
                    model.__table__.c.raw_payload_json["p17_test"].astext.is_not(None)
                ))
            for model in (FinalCircuitFunction, FinalProjectionFunction, FinalProjection):
                await session.execute(model.__table__.delete().where(
                    model.__table__.c.provenance_json["p17_test"].astext.is_not(None)
                ))
            for model in (MirrorCircuitFunction, MirrorProjectionFunction, MirrorRegionFunction,
                          MirrorRegionCircuit, MirrorRegionConnection):
                await session.execute(model.__table__.delete().where(
                    model.__table__.c.raw_payload_json["p17_test"].astext.is_not(None)
                ))
            await session.execute(
                MirrorHumanReviewRecord.__table__.delete().where(
                    MirrorHumanReviewRecord.__table__.c.reviewer_note.like(f"{TEST_PREFIX}%")
                )
            )
            if _TEST_RIDS:
                await session.execute(MirrorKgTriple.__table__.delete().where(
                    MirrorKgTriple.__table__.c.resource_id.in_([str(r) for r in _TEST_RIDS])
                ))
                await session.execute(FinalKgTriple.__table__.delete().where(
                    FinalKgTriple.__table__.c.resource_id.in_([str(r) for r in _TEST_RIDS])
                ))
            test_term_ids = (
                await session.execute(
                    select(OntologyTerm.id).where(
                        OntologyTerm.__table__.c.canonical_term_en.like(f"{TEST_PREFIX}%")
                    )
                )
            ).scalars().all()
            if test_term_ids:
                for table in (MirrorKgTriple.__table__, FinalKgTriple.__table__):
                    await session.execute(table.delete().where(
                        table.c.object_id.in_([str(t) for t in test_term_ids])
                    ))
            await session.execute(
                OntologyTerm.__table__.delete().where(
                    OntologyTerm.__table__.c.canonical_term_en.like(f"{TEST_PREFIX}%")
                )
            )
            await session.commit()

    yield
    _run(_cleanup())


@pytest.fixture()
def rid():
    async def _load():
        async with AsyncSessionLocal() as session:
            row = (await session.execute(text("SELECT id FROM atlas_resources LIMIT 1"))).scalar_one_or_none()
            if row is None:
                pytest.skip("no atlas_resources rows available")
            _TEST_RIDS.add(row)
            return row

    return _run(_load())


@pytest.fixture()
def cand_id():
    async def _load():
        async with AsyncSessionLocal() as session:
            row = (await session.execute(select(CandidateBrainRegion.id).limit(1))).scalar_one_or_none()
            if row is None:
                pytest.skip("no candidate_brain_regions rows available")
            return row

    return _run(_load())


def _term(session, name: str, *, status: str = "active", replaced_by=None) -> OntologyTerm:
    term = OntologyTerm(
        term_code=f"ng:func:{name.replace(' ', '_')}",
        canonical_term_en=name,
        term_type="function",
        status=status,
        created_by="p17_test",
    )
    session.add(term)
    if replaced_by:
        term.replaced_by_term_id = replaced_by
    return term


async def _approve(session, *, target_type: str, target_id: uuid.UUID) -> None:
    session.add(MirrorHumanReviewRecord(
        target_type=target_type,
        target_id=target_id,
        action="approve",
        from_mirror_status=MirrorStatus.llm_suggested,
        to_mirror_status=MirrorStatus.human_approved,
        from_review_status=MirrorReviewStatus.pending,
        to_review_status=MirrorReviewStatus.approved,
        reviewer="p17_test",
        reviewer_note=f"{TEST_PREFIX}approve",
        resource_id=None,
        batch_id=None,
        source_atlas="test_atlas",
    ))
    await session.flush()


async def _region_row(session, *, term, cand, rid, relation="involved_in",
                      category="cognitive", approved=True) -> MirrorRegionFunction:
    row = MirrorRegionFunction(
        region_candidate_id=cand, resource_id=rid,
        granularity_level="macro_clinical", granularity_family="macro",
        source_atlas="test_atlas", function_term=term.canonical_term_en,
        function_category=category, relation_type=relation, confidence=0.8,
        mirror_status=MirrorStatus.llm_suggested, review_status=MirrorReviewStatus.pending,
        promotion_status=MirrorPromotionStatus.not_promoted,
        raw_payload_json={"p17_test": True}, term_id=term.id,
    )
    session.add(row)
    await session.flush()
    if approved:
        row.mirror_status = MirrorStatus.human_approved
        row.review_status = MirrorReviewStatus.approved
        await _approve(session, target_type="region_function", target_id=row.id)
        await session.flush()
    return row


async def _projection_row(session, *, term, rid, approved=True) -> tuple[MirrorProjectionFunction, MirrorRegionConnection]:
    conn = MirrorRegionConnection(
        resource_id=rid, granularity_level="macro_clinical", granularity_family="macro",
        source_atlas="test_atlas", connection_type="projection", directionality="directed",
        mirror_status=MirrorStatus.llm_suggested, review_status=MirrorReviewStatus.pending,
        promotion_status=MirrorPromotionStatus.not_promoted, raw_payload_json={"p17_test": True},
    )
    session.add(conn)
    await session.flush()
    row = MirrorProjectionFunction(
        projection_id=conn.id, resource_id=rid,
        granularity_level="macro_clinical", granularity_family="macro",
        source_atlas="test_atlas", function_term=term.canonical_term_en,
        function_category="cognitive", relation_type="modulates", confidence=0.8,
        mirror_status=MirrorStatus.llm_suggested, review_status=MirrorReviewStatus.pending,
        promotion_status=MirrorPromotionStatus.not_promoted,
        raw_payload_json={"p17_test": True}, term_id=term.id,
        function_domain="cognitive", function_role="modulation", effect_type="excitatory",
    )
    session.add(row)
    await session.flush()
    if approved:
        row.mirror_status = MirrorStatus.human_approved
        row.review_status = MirrorReviewStatus.approved
        await _approve(session, target_type="projection_function", target_id=row.id)
        await session.flush()
    return row, conn


async def _circuit_row(session, *, term, rid, approved=True) -> tuple[MirrorCircuitFunction, MirrorRegionCircuit]:
    circ = MirrorRegionCircuit(
        resource_id=rid, granularity_level="macro_clinical", granularity_family="macro",
        source_atlas="test_atlas", circuit_name="p17 circuit", circuit_type="simple",
        mirror_status=MirrorStatus.llm_suggested, review_status=MirrorReviewStatus.pending,
        promotion_status=MirrorPromotionStatus.not_promoted, raw_payload_json={"p17_test": True},
    )
    session.add(circ)
    await session.flush()
    row = MirrorCircuitFunction(
        circuit_id=circ.id, resource_id=rid,
        granularity_level="macro_clinical", granularity_family="macro",
        source_atlas="test_atlas", function_term_en=term.canonical_term_en,
        confidence=0.8, mirror_status=MirrorStatus.llm_suggested,
        review_status=MirrorReviewStatus.pending, promotion_status=MirrorPromotionStatus.not_promoted,
        raw_payload_json={"p17_test": True}, term_id=term.id,
        function_domain="cognitive", function_role="integration", effect_type="unknown",
    )
    session.add(row)
    await session.flush()
    if approved:
        row.mirror_status = MirrorStatus.human_approved
        row.review_status = MirrorReviewStatus.approved
        await _approve(session, target_type="circuit_function", target_id=row.id)
        await session.flush()
    return row, circ


def _ctx(session, *, promote_dependencies=True):
    return fmcps.PromotionContext(
        session=session,
        run=None,
        dry_run=False,
        request=fmcps.FinalMacroClinicalPromotionRequest(
            target_types=["region_function"],
            dry_run=False,
            promote_dependencies=promote_dependencies,
            scope=None,
        ),
        warnings=[],
    )


async def _final_circuit(session, *, circ, rid) -> FinalRegionCircuit:
    final = FinalRegionCircuit(
        source_mirror_circuit_id=circ.id, resource_id=rid,
        granularity_level="macro_clinical", granularity_family="macro",
        source_atlas="test_atlas", circuit_name=circ.circuit_name, circuit_type="simple",
        final_status="active", raw_payload_json={"p17_test": True},
    )
    session.add(final)
    await session.flush()
    return final


async def _final_projection(session, *, conn, rid) -> FinalProjection:
    final = FinalProjection(
        final_uid=f"final_macro_clinical:projection:{conn.id}",
        source_mirror_type="projection", source_mirror_id=conn.id,
        resource_id=rid, source_atlas="test_atlas", granularity_level="macro_clinical",
        granularity_family="macro", projection_type="projection", directionality="directed",
        final_status="active", provenance_json={"p17_test": True},
    )
    session.add(final)
    await session.flush()
    return final


# ---------------------------------------------------------------- 1-4 basics


def test_01_active_region_function_promotes(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}r1")
            await session.flush()
            row = await _region_row(session, term=term, cand=cand_id, rid=rid)
            final = await fmcps.promote_region_function(_ctx(session), row, review_record_id=None)
            await session.flush()
            assert final is not None
            assert final.term_id == term.id
            assert final.function_term == term.canonical_term_en
            finals = (await session.execute(
                select(FinalRegionFunction).where(FinalRegionFunction.raw_payload_json["p17_test"].astext.is_not(None))
            )).scalars().all()
            assert len(finals) == 1
    _run(_case())


def test_02_active_projection_function_promotes(db, rid):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}p2")
            await session.flush()
            row, conn = await _projection_row(session, term=term, rid=rid)
            final_proj = await _final_projection(session, conn=conn, rid=rid)
            await session.flush()
            final = await fmcps.promote_projection_function(_ctx(session), row, review_record_id=None)
            await session.flush()
            assert final is not None
            assert final.term_id == term.id
            assert final.final_projection_id == final_proj.id
    _run(_case())


def test_03_active_circuit_function_promotes(db, rid):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}c3")
            await session.flush()
            row, circ = await _circuit_row(session, term=term, rid=rid)
            await _final_circuit(session, circ=circ, rid=rid)
            await session.flush()
            final = await fmcps.promote_circuit_function(_ctx(session), row, review_record_id=None)
            await session.flush()
            assert final is not None
            assert final.term_id == term.id
            assert final.function_term == term.canonical_term_en
    _run(_case())


def test_04_circuit_function_no_longer_preview_only(db, rid):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}c4")
            await session.flush()
            row, circ = await _circuit_row(session, term=term, rid=rid)
            await _final_circuit(session, circ=circ, rid=rid)
            await session.flush()
            final = await fmcps.promote_circuit_function(_ctx(session), row, review_record_id=None)
            await session.flush()
            assert isinstance(final, FinalCircuitFunction)
            finals = (await session.execute(
                select(FinalCircuitFunction).where(FinalCircuitFunction.final_uid.isnot(None))
            )).scalars().all()
            assert len(finals) == 1
    _run(_case())


# ---------------------------------------------------------------- 5-6 identity


def test_05_final_term_id_equals_canonical(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}id5")
            await session.flush()
            row = await _region_row(session, term=term, cand=cand_id, rid=rid)
            final = await fmcps.promote_region_function(_ctx(session), row, review_record_id=None)
            await session.flush()
            assert final.term_id == term.id
            assert final.term_id == row.term_id  # same ontology_terms.id
    _run(_case())


def test_06_mirror_final_share_canonical_identity(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}id6")
            await session.flush()
            row = await _region_row(session, term=term, cand=cand_id, rid=rid)
            await fmcps.promote_region_function(_ctx(session), row, review_record_id=None)
            await session.flush()
            final = (await session.execute(
                select(FinalRegionFunction).where(FinalRegionFunction.raw_payload_json["p17_test"].astext.is_not(None))
            )).scalar_one()
            ftriple = (await session.execute(
                select(FinalKgTriple).where(FinalKgTriple.object_type == "function")
            )).scalars().all()
            assert ftriple and all(t.object_id == term.id for t in ftriple)
            assert ftriple[0].object_id == final.term_id
    _run(_case())


# ---------------------------------------------------------------- 7-10 term gates


def test_07_proposed_term_blocked(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}pr7", status="proposed")
            await session.flush()
            row = await _region_row(session, term=term, cand=cand_id, rid=rid)
            ok, reason, _ = await ffps.check_function_term_eligibility(session, row)
            assert not ok and reason == "function_term_not_active"
            final = await fmcps.promote_region_function(_ctx(session), row, review_record_id=None)
            assert final is None  # not written
    _run(_case())


def test_08_deprecated_term_blocked(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}dp8", status="deprecated")
            await session.flush()
            row = await _region_row(session, term=term, cand=cand_id, rid=rid)
            ok, reason, _ = await ffps.check_function_term_eligibility(session, row)
            assert not ok and reason == "function_term_deprecated"
    _run(_case())


def test_09_merged_to_active_canonical_promotes(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            canon = _term(session, f"{TEST_PREFIX}can9")
            await session.flush()
            old = _term(session, f"{TEST_PREFIX}old9", status="merged", replaced_by=canon.id)
            await session.flush()
            row = await _region_row(session, term=old, cand=cand_id, rid=rid)
            ok, reason, res = await ffps.check_function_term_eligibility(session, row)
            assert ok and reason is None
            assert res.term_id == canon.id  # resolved to canonical active
            final = await fmcps.promote_region_function(_ctx(session), row, review_record_id=None)
            await session.flush()
            assert final is not None and final.term_id == canon.id
    _run(_case())


def test_10_invalid_term_blocked(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            region_term = OntologyTerm(
                term_code="ng:region:p17_brain", canonical_term_en="p17 brain",
                term_type="region", status="active", created_by="p17_test",
            )
            session.add(region_term)
            await session.flush()
            row = MirrorRegionFunction(
                region_candidate_id=cand_id, resource_id=rid,
                granularity_level="macro_clinical", granularity_family="macro",
                source_atlas="test_atlas", function_term="p17 brain",
                function_category="cognitive", relation_type="involved_in",
                mirror_status=MirrorStatus.human_approved, review_status=MirrorReviewStatus.approved,
                promotion_status=MirrorPromotionStatus.not_promoted,
                raw_payload_json={"p17_test": True}, term_id=region_term.id,
            )
            session.add(row)
            await session.flush()
            ok, reason, _ = await ffps.check_function_term_eligibility(session, row)
            assert not ok and reason == "function_term_invalid"
    _run(_case())


# ---------------------------------------------------------------- 11-13 gates


def test_11_parent_not_promoted_blocked(db, rid):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}p11")
            await session.flush()
            row, _conn = await _projection_row(session, term=term, rid=rid)
            # no Final projection exists and promote_dependencies=False
            ctx = _ctx(session, promote_dependencies=False)
            final = await fmcps.promote_projection_function(ctx, row, review_record_id=None)
            assert final is None
            assert any("parent" in w for w in ctx.warnings)
    _run(_case())


def test_12_review_not_approved_blocked(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}r12")
            await session.flush()
            row = await _region_row(session, term=term, cand=cand_id, rid=rid, approved=False)
            status, reason, *_ = await fmcps.check_promotion_eligibility(
                session, target_type="region_function", obj=row, allow_conflict_with_human_reason=False
            )
            assert status != "eligible"
    _run(_case())


def test_13_validation_blocker_blocked(db, rid, cand_id, monkeypatch):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}r13")
            await session.flush()
            row = await _region_row(session, term=term, cand=cand_id, rid=rid)
            import app.services.mirror_promotion_service as mps

            async def _blocker(*a, **k):
                return {"has_blocker": True, "has_error": False}

            monkeypatch.setattr(mps, "get_latest_validation_summary", _blocker)
            ok, reason, *_ = await mps.validate_promotion_eligibility(session, "region_function", row)
            assert not ok and reason == "HAS_VALIDATION_BLOCKER"
    _run(_case())


# ---------------------------------------------------------------- 14-18 relation quality


def test_14_qualifiers_preserved(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}q14")
            await session.flush()
            row = await _region_row(session, term=term, cand=cand_id, rid=rid, category="motor")
            final = await fmcps.promote_region_function(_ctx(session), row, review_record_id=None)
            await session.flush()
            assert final.function_category == "motor"
            assert final.relation_type == "involved_in"
    _run(_case())


def test_15_function_text_is_snapshot(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}snap15")
            await session.flush()
            row = await _region_row(session, term=term, cand=cand_id, rid=rid)
            row.function_term = f"{TEST_PREFIX}snap15!"  # odd source text
            await session.flush()
            final = await fmcps.promote_region_function(_ctx(session), row, review_record_id=None)
            await session.flush()
            assert final.function_term == f"{TEST_PREFIX}snap15!"
            assert final.term_id == term.id  # identity from term, not text
    _run(_case())


def test_16_repeated_promotion_idempotent(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}id16")
            await session.flush()
            row = await _region_row(session, term=term, cand=cand_id, rid=rid)
            await fmcps.promote_region_function(_ctx(session), row, review_record_id=None)
            await session.flush()
            # promote again with a fresh circuit parent setup (dup check by source)
            await fmcps.promote_region_function(_ctx(session), row, review_record_id=None)
            await session.flush()
            finals = (await session.execute(
                select(FinalRegionFunction).where(FinalRegionFunction.raw_payload_json["p17_test"].astext.is_not(None))
            )).scalars().all()
            assert len(finals) == 1
            ftriples = (await session.execute(
                select(FinalKgTriple).where(FinalKgTriple.object_type == "function")
            )).scalars().all()
            assert len(ftriples) == 1  # triple also idempotent
    _run(_case())


def test_17_same_function_different_qualifier_not_merged(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}q17")
            await session.flush()
            r1 = await _region_row(session, term=term, cand=cand_id, rid=rid, category="motor")
            r2 = await _region_row(session, term=term, cand=cand_id, rid=rid, category="cognitive")
            await fmcps.promote_region_function(_ctx(session), r1, review_record_id=None)
            await fmcps.promote_region_function(_ctx(session), r2, review_record_id=None)
            await session.flush()
            finals = (await session.execute(
                select(FinalRegionFunction).where(FinalRegionFunction.raw_payload_json["p17_test"].astext.is_not(None))
            )).scalars().all()
            assert len(finals) == 2  # distinct facts, not merged
    _run(_case())


def test_18_source_mirror_mapping_reversible(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}map18")
            await session.flush()
            row = await _region_row(session, term=term, cand=cand_id, rid=rid)
            final = await fmcps.promote_region_function(_ctx(session), row, review_record_id=None)
            await session.flush()
            assert final.source_mirror_function_id == row.id  # mirror → final
            back = (await session.execute(
                select(FinalRegionFunction).where(FinalRegionFunction.source_mirror_function_id == row.id)
            )).scalar_one_or_none()
            assert back is not None and back.id == final.id  # final → mirror
    _run(_case())


# ---------------------------------------------------------------- 19-23 final triple


def test_19_final_triple_auto_produced(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}t19")
            await session.flush()
            row = await _region_row(session, term=term, cand=cand_id, rid=rid)
            await fmcps.promote_region_function(_ctx(session), row, review_record_id=None)
            await session.flush()
            ftriples = (await session.execute(
                select(FinalKgTriple).where(FinalKgTriple.object_type == "function")
            )).scalars().all()
            assert len(ftriples) == 1
            assert ftriples[0].predicate == "involved_in_function"
    _run(_case())


def test_20_final_triple_object_id_not_null(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}t20")
            await session.flush()
            row = await _region_row(session, term=term, cand=cand_id, rid=rid)
            await fmcps.promote_region_function(_ctx(session), row, review_record_id=None)
            await session.flush()
            ftriples = (await session.execute(
                select(FinalKgTriple).where(FinalKgTriple.object_type == "function")
            )).scalars().all()
            assert all(t.object_id is not None for t in ftriples)
    _run(_case())


def test_21_final_triple_object_equals_relation_term(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}t21")
            await session.flush()
            row = await _region_row(session, term=term, cand=cand_id, rid=rid)
            final = await fmcps.promote_region_function(_ctx(session), row, review_record_id=None)
            await session.flush()
            ftriple = (await session.execute(
                select(FinalKgTriple).where(FinalKgTriple.object_type == "function")
            )).scalar_one()
            assert ftriple.object_id == final.term_id == term.id
    _run(_case())


def test_22_final_triple_subject_is_final_id(db, rid):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}t22")
            await session.flush()
            row, conn = await _projection_row(session, term=term, rid=rid)
            final_proj = await _final_projection(session, conn=conn, rid=rid)
            await session.flush()
            await fmcps.promote_projection_function(_ctx(session), row, review_record_id=None)
            await session.flush()
            ftriple = (await session.execute(
                select(FinalKgTriple).where(FinalKgTriple.object_type == "function")
            )).scalar_one()
            assert ftriple.subject_type == "final_projection"
            assert ftriple.subject_id == final_proj.id  # Final entity id, not mirror
    _run(_case())


def test_23_rename_does_not_change_triple_identity(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}t23")
            await session.flush()
            row = await _region_row(session, term=term, cand=cand_id, rid=rid)
            await fmcps.promote_region_function(_ctx(session), row, review_record_id=None)
            await session.flush()
            term.canonical_term_en = f"{TEST_PREFIX}renamed23"
            await session.flush()
            # re-promotion must not create a second triple (object_id unchanged)
            await fmcps.promote_region_function(_ctx(session), row, review_record_id=None)
            await session.flush()
            ftriples = (await session.execute(
                select(FinalKgTriple).where(FinalKgTriple.object_type == "function")
            )).scalars().all()
            assert len(ftriples) == 1
    _run(_case())


# ---------------------------------------------------------------- 24-25 transaction


def test_24_triple_failure_rolls_back(db, rid, cand_id, monkeypatch):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}t24")
            await session.flush()
            row = await _region_row(session, term=term, cand=cand_id, rid=rid)

            async def _boom(*a, **k):
                raise RuntimeError("final triple projection failure (injected)")

            monkeypatch.setattr(ffps, "project_final_function_triple", _boom)
            with pytest.raises(RuntimeError):
                await fmcps.promote_region_function(_ctx(session), row, review_record_id=None)
            await session.rollback()
            finals = (await session.execute(
                select(FinalRegionFunction).where(FinalRegionFunction.raw_payload_json["p17_test"].astext.is_not(None))
            )).scalars().all()
            assert not finals  # relation rolled back with the failed triple
    _run(_case())


def test_25_promotion_status_only_after_success(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}t25")
            await session.flush()
            # blocked: proposed term → status must NOT become promoted
            proposed = _term(session, f"{TEST_PREFIX}pr25", status="proposed")
            await session.flush()
            prow = await _region_row(session, term=proposed, cand=cand_id, rid=rid)
            await fmcps.promote_region_function(_ctx(session), prow, review_record_id=None)
            await session.flush()
            assert prow.promotion_status == MirrorPromotionStatus.not_promoted
            # success: active term → status updates via Step 9 path
            arow = await _region_row(session, term=term, cand=cand_id, rid=rid)
            final = await fmcps.promote_region_function(_ctx(session), arow, review_record_id=None)
            await session.flush()
            assert final is not None
    _run(_case())


# ---------------------------------------------------------------- 26-28


def test_26_batch_promotion_no_duplicates(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            t1 = _term(session, f"{TEST_PREFIX}b26a")
            t2 = _term(session, f"{TEST_PREFIX}b26b")
            await session.flush()
            r1 = await _region_row(session, term=t1, cand=cand_id, rid=rid)
            r2 = await _region_row(session, term=t2, cand=cand_id, rid=rid)
            for row in (r1, r2):
                await fmcps.promote_region_function(_ctx(session), row, review_record_id=None)
                await session.flush()
            finals = (await session.execute(
                select(FinalRegionFunction).where(FinalRegionFunction.raw_payload_json["p17_test"].astext.is_not(None))
            )).scalars().all()
            assert len(finals) == 2
    _run(_case())


def test_27_evidence_provenance_preserved(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}e27")
            await session.flush()
            row = await _region_row(session, term=term, cand=cand_id, rid=rid)
            row.evidence_text = "p17 evidence marker"
            await session.flush()
            final = await fmcps.promote_region_function(_ctx(session), row, review_record_id=None)
            await session.flush()
            assert final.evidence_text == "p17 evidence marker"
            assert final.raw_payload_json.get("p17_test") is True
    _run(_case())


def test_28_circuit_promotion_uses_relation_not_association(db, rid):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}c28")
            await session.flush()
            row, circ = await _circuit_row(session, term=term, rid=rid)
            circ.function_association = "p17 legacy association text"  # must be ignored
            await session.flush()
            await _final_circuit(session, circ=circ, rid=rid)
            await session.flush()
            final = await fmcps.promote_circuit_function(_ctx(session), row, review_record_id=None)
            await session.flush()
            assert final is not None
            assert final.term_id == term.id  # from relation term, not association text
            ftriple = (await session.execute(
                select(FinalKgTriple).where(FinalKgTriple.object_type == "function")
            )).scalar_one()
            assert ftriple.object_label == term.canonical_term_en
    _run(_case())


# ---------------------------------------------------------------- 29-30 global


def test_29_non_function_promotion_unaffected(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}n29")
            await session.flush()
            row = await _region_row(session, term=term, cand=cand_id, rid=rid)
            await fmcps.promote_region_function(_ctx(session), row, review_record_id=None)
            await session.flush()
            ftriples = (await session.execute(
                select(FinalKgTriple).where(FinalKgTriple.object_type == "function")
            )).scalars().all()
            non_fn = (await session.execute(
                select(FinalKgTriple).where(FinalKgTriple.object_type != "function")
            )).scalars().all()
            assert len(ftriples) == 1
            assert len(non_fn) == 0  # nothing else created by function promotion
    _run(_case())


def test_30_final_function_integrity_clean(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}i30")
            await session.flush()
            row = await _region_row(session, term=term, cand=cand_id, rid=rid)
            await fmcps.promote_region_function(_ctx(session), row, review_record_id=None)
            await session.flush()
            r = await ffps.check_final_function_integrity(session)
            for key in (
                "relation_term_id_null", "relation_orphan_term", "relation_invalid_term",
                "relation_proposed_term", "relation_merged_term", "relation_deprecated_term",
                "triple_object_id_null", "triple_orphan_object", "triple_invalid_object",
                "triple_merged_object", "triple_deprecated_object", "triple_duplicate_spo",
                "triple_missing_final_relation_lineage", "triple_mirror_subject",
                "triple_wrong_label",
            ):
                assert r[key] == 0, f"{key} = {r[key]}"
            assert r["final_region_functions"] == 1
            assert r["final_function_triples"] == 1
    _run(_case())
