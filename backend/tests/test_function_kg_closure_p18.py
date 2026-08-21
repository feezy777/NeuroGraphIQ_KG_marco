"""P1.8 Function KG closure — controlled E2E + propagation tests.

Six real samples (2 region / 2 projection / 2 circuit) go through the REAL
service chain (relation → mirror triple → review → promotion → final relation
→ final triple), then verify canonical identity equality, Final subject
identity, lineage, idempotency, rollback, the proposed governance gate, and
ontology merge / canonical rename propagation across every layer.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select, text

from app.database import AsyncSessionLocal
from app.models.candidate import CandidateBrainRegion
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
from app.models.mirror_review import MirrorHumanReviewRecord
from app.models.ontology import OntologyTerm
from app.models.final_kg import FinalKgTriple, FinalRegionFunction
from app.models.final_macro_clinical import (
    FinalCircuitFunction,
    FinalProjection,
    FinalProjectionFunction,
)
from app.models.final_kg import FinalRegionCircuit
from app.schemas.mirror_kg import MirrorPromotionStatus, MirrorReviewStatus, MirrorStatus
from app.services import (
    final_function_promotion_service as ffps,
    final_macro_clinical_promotion_service as fmcps,
    function_kg_integrity_service as fkis,
    mirror_kg_service as mks,
    mirror_macro_clinical_service as mmcs,
)
from app.services import ontology_service

TEST_PREFIX = "p18_test_"
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
                    model.__table__.c.raw_payload_json["p18_test"].astext.is_not(None)
                ))
            for model in (FinalCircuitFunction, FinalProjectionFunction, FinalProjection):
                await session.execute(model.__table__.delete().where(
                    model.__table__.c.provenance_json["p18_test"].astext.is_not(None)
                ))
            for model in (MirrorCircuitFunction, MirrorProjectionFunction, MirrorRegionFunction,
                          MirrorRegionCircuit, MirrorRegionConnection):
                await session.execute(model.__table__.delete().where(
                    model.__table__.c.raw_payload_json["p18_test"].astext.is_not(None)
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
        created_by="p18_test",
    )
    session.add(term)
    if replaced_by:
        term.replaced_by_term_id = replaced_by
    return term


async def _approve(session, *, target_type: str, target_id: uuid.UUID) -> None:
    session.add(MirrorHumanReviewRecord(
        target_type=target_type, target_id=target_id, action="approve",
        from_mirror_status=MirrorStatus.llm_suggested, to_mirror_status=MirrorStatus.human_approved,
        from_review_status=MirrorReviewStatus.pending, to_review_status=MirrorReviewStatus.approved,
        reviewer="p18_test", reviewer_note=f"{TEST_PREFIX}approve",
        resource_id=None, batch_id=None, source_atlas="test_atlas",
    ))
    await session.flush()


def _ctx(session, *, promote_dependencies=True):
    return fmcps.PromotionContext(
        session=session, run=None, dry_run=False,
        request=fmcps.FinalMacroClinicalPromotionRequest(
            target_types=["region_function"], dry_run=False,
            promote_dependencies=promote_dependencies, scope=None,
        ),
        warnings=[],
    )


async def _make_region(session, *, term, cand, rid, tag):
    from app.schemas.mirror_kg import MirrorRegionFunctionCreate

    row = await mks.create_mirror_function(session, MirrorRegionFunctionCreate(
        region_candidate_id=cand, resource_id=rid,
        granularity_level="macro_clinical", granularity_family="macro",
        source_atlas="test_atlas", function_term=term.canonical_term_en,
        function_category="cognitive", relation_type="involved_in", confidence=0.8,
        raw_payload_json={"p18_test": True, "tag": tag},
    ))
    await session.flush()
    row.mirror_status = MirrorStatus.human_approved
    row.review_status = MirrorReviewStatus.approved
    await _approve(session, target_type="region_function", target_id=row.id)
    await session.flush()
    return row


async def _make_projection(session, *, term, rid, tag):
    conn = MirrorRegionConnection(
        resource_id=rid, granularity_level="macro_clinical", granularity_family="macro",
        source_atlas="test_atlas", connection_type="projection", directionality="directed",
        mirror_status=MirrorStatus.llm_suggested, review_status=MirrorReviewStatus.pending,
        promotion_status=MirrorPromotionStatus.not_promoted, raw_payload_json={"p18_test": True},
    )
    session.add(conn)
    await session.flush()
    from app.schemas.mirror_macro_clinical import MirrorProjectionFunctionCreate

    row = await mmcs.create_projection_function(session, MirrorProjectionFunctionCreate(
        projection_id=conn.id, resource_id=rid,
        granularity_level="macro_clinical", granularity_family="macro",
        source_atlas="test_atlas", function_term=term.canonical_term_en,
        function_category="cognitive", relation_type="modulates", confidence=0.8,
        raw_payload_json={"p18_test": True, "tag": tag},
    ))
    await session.flush()
    row.mirror_status = MirrorStatus.human_approved
    row.review_status = MirrorReviewStatus.approved
    await _approve(session, target_type="projection_function", target_id=row.id)
    await session.flush()
    return row, conn


async def _make_circuit(session, *, term, rid, tag):
    circ = MirrorRegionCircuit(
        resource_id=rid, granularity_level="macro_clinical", granularity_family="macro",
        source_atlas="test_atlas", circuit_name=f"p18 circuit {tag}", circuit_type="simple",
        mirror_status=MirrorStatus.llm_suggested, review_status=MirrorReviewStatus.pending,
        promotion_status=MirrorPromotionStatus.not_promoted, raw_payload_json={"p18_test": True},
    )
    session.add(circ)
    await session.flush()
    from app.schemas.mirror_macro_clinical import MirrorCircuitFunctionCreate

    row = await mmcs.create_circuit_function(session, MirrorCircuitFunctionCreate(
        circuit_id=circ.id, resource_id=rid,
        granularity_level="macro_clinical", granularity_family="macro",
        source_atlas="test_atlas", function_term_en=term.canonical_term_en,
        confidence=0.8, raw_payload_json={"p18_test": True, "tag": tag},
        function_domain="cognitive", function_role="integration", effect_type="unknown",
    ))
    await session.flush()
    row.mirror_status = MirrorStatus.human_approved
    row.review_status = MirrorReviewStatus.approved
    await _approve(session, target_type="circuit_function", target_id=row.id)
    await session.flush()
    return row, circ


async def _final_circuit(session, *, circ, rid) -> FinalRegionCircuit:
    final = FinalRegionCircuit(
        source_mirror_circuit_id=circ.id, resource_id=rid,
        granularity_level="macro_clinical", granularity_family="macro",
        source_atlas="test_atlas", circuit_name=circ.circuit_name, circuit_type="simple",
        final_status="active", raw_payload_json={"p18_test": True},
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
        final_status="active", provenance_json={"p18_test": True},
    )
    session.add(final)
    await session.flush()
    return final


# ---------------------------------------------------------------- E2E chain


def test_01_e2e_six_samples_full_chain(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            terms = {}
            for i in range(1, 7):
                terms[i] = _term(session, f"{TEST_PREFIX}s{i}")
            await session.flush()

            # 2 region
            r1 = await _make_region(session, term=terms[1], cand=cand_id, rid=rid, tag="r1")
            r2 = await _make_region(session, term=terms[2], cand=cand_id, rid=rid, tag="r2")
            # 2 projection (+ parents)
            p1, c1 = await _make_projection(session, term=terms[3], rid=rid, tag="p1")
            p2, c2 = await _make_projection(session, term=terms[4], rid=rid, tag="p2")
            await _final_projection(session, conn=c1, rid=rid)
            await _final_projection(session, conn=c2, rid=rid)
            # 2 circuit (+ parents)
            cf1, cc1 = await _make_circuit(session, term=terms[5], rid=rid, tag="c1")
            cf2, cc2 = await _make_circuit(session, term=terms[6], rid=rid, tag="c2")
            await _final_circuit(session, circ=cc1, rid=rid)
            await _final_circuit(session, circ=cc2, rid=rid)
            await session.flush()

            # mirror triples auto-produced by incremental projection
            mt = (await session.execute(
                select(MirrorKgTriple).where(MirrorKgTriple.resource_id == rid)
            )).scalars().all()
            assert len(mt) == 6  # 2+2+2

            # promotion through the REAL service
            for row in (r1, r2):
                ctx = _ctx(session)
                f = await fmcps.promote_region_function(ctx, row, review_record_id=None)
                print("DBG promote region", row.function_term, "->", type(f).__name__ if f else None, ctx.warnings)
            for row, _conn in ((p1, c1), (p2, c2)):
                ctx = _ctx(session)
                f = await fmcps.promote_projection_function(ctx, row, review_record_id=None)
                print("DBG promote proj", row.function_term, "->", type(f).__name__ if f else None, ctx.warnings)
            for row, _cc in ((cf1, cc1), (cf2, cc2)):
                ctx = _ctx(session)
                f = await fmcps.promote_circuit_function(ctx, row, review_record_id=None)
                print("DBG promote circ", row.function_term_en, "->", type(f).__name__ if f else None, ctx.warnings)
            await session.flush()

            finals = (await session.execute(
                select(FinalRegionFunction).where(FinalRegionFunction.raw_payload_json["p18_test"].astext.is_not(None))
            )).scalars().all()
            assert len(finals) == 2
            fprojs = (await session.execute(
                select(FinalProjectionFunction).where(
                    FinalProjectionFunction.source_mirror_id.in_([p1.id, p2.id])
                )
            )).scalars().all()
            assert len(fprojs) == 2
            fcircs = (await session.execute(
                select(FinalCircuitFunction).where(
                    FinalCircuitFunction.source_mirror_id.in_([cf1.id, cf2.id])
                )
            )).scalars().all()
            assert len(fcircs) == 2

            ftriples = (await session.execute(
                select(FinalKgTriple).where(FinalKgTriple.resource_id == rid)
            )).scalars().all()
            assert len(ftriples) == 6
            assert all(t.object_id is not None for t in ftriples)
    _run(_case())


def test_02_canonical_identity_consistent(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}id2")
            await session.flush()
            row = await _make_region(session, term=term, cand=cand_id, rid=rid, tag="id2")
            await fmcps.promote_region_function(_ctx(session), row, review_record_id=None)
            await session.flush()
            mt = (await session.execute(
                select(MirrorKgTriple).where(MirrorKgTriple.resource_id == rid)
            )).scalar_one()
            final = (await session.execute(
                select(FinalRegionFunction).where(FinalRegionFunction.raw_payload_json["p18_test"].astext.is_not(None))
            )).scalar_one()
            ft = (await session.execute(
                select(FinalKgTriple).where(FinalKgTriple.resource_id == rid)
            )).scalar_one()
            assert row.term_id == term.id
            assert mt.object_id == term.id
            assert final.term_id == term.id
            assert ft.object_id == term.id
            # the P1 acceptance identity chain
            assert row.term_id == mt.object_id == final.term_id == ft.object_id == term.id
    _run(_case())


def test_03_final_subject_is_final_id(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}sub3")
            await session.flush()
            row, conn = await _make_projection(session, term=term, rid=rid, tag="sub3")
            final_proj = await _final_projection(session, conn=conn, rid=rid)
            await session.flush()
            await fmcps.promote_projection_function(_ctx(session), row, review_record_id=None)
            await session.flush()
            ft = (await session.execute(
                select(FinalKgTriple).where(FinalKgTriple.resource_id == rid)
            )).scalar_one()
            assert ft.subject_type == "final_projection"
            assert ft.subject_id == final_proj.id
            assert ft.subject_id != row.projection_id  # not the mirror id
    _run(_case())


def test_04_e2e_idempotent(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}id4")
            await session.flush()
            row = await _make_region(session, term=term, cand=cand_id, rid=rid, tag="id4")
            for _ in range(2):
                await fmcps.promote_region_function(_ctx(session), row, review_record_id=None)
                await session.flush()
            finals = (await session.execute(
                select(FinalRegionFunction).where(FinalRegionFunction.raw_payload_json["p18_test"].astext.is_not(None))
            )).scalars().all()
            ftriples = (await session.execute(
                select(FinalKgTriple).where(FinalKgTriple.resource_id == rid)
            )).scalars().all()
            assert len(finals) == 1
            assert len(ftriples) == 1
    _run(_case())


def test_05_e2e_rollback(db, rid, cand_id, monkeypatch):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}rb5")
            await session.flush()
            row = await _make_region(session, term=term, cand=cand_id, rid=rid, tag="rb5")

            async def _boom(*a, **k):
                raise RuntimeError("final triple failure (injected)")

            monkeypatch.setattr(ffps, "project_final_function_triple", _boom)
            with pytest.raises(RuntimeError):
                await fmcps.promote_region_function(_ctx(session), row, review_record_id=None)
            await session.rollback()
            finals = (await session.execute(
                select(FinalRegionFunction).where(FinalRegionFunction.raw_payload_json["p18_test"].astext.is_not(None))
            )).scalars().all()
            ftriples = (await session.execute(
                select(FinalKgTriple).where(FinalKgTriple.resource_id == rid)
            )).scalars().all()
            assert not finals and not ftriples  # atomic rollback
            # retry succeeds: the failed transaction rolled back the term and
            # relation too, so rebuild the sample then promote again
            monkeypatch.undo()
            term2 = _term(session, f"{TEST_PREFIX}rb5b")
            await session.flush()
            row2 = await _make_region(session, term=term2, cand=cand_id, rid=rid, tag="rb5b")
            final = await fmcps.promote_region_function(_ctx(session), row2, review_record_id=None)
            await session.flush()
            assert final is not None
    _run(_case())


def test_06_proposed_gate(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}pr6", status="proposed")
            await session.flush()
            row = await _make_region(session, term=term, cand=cand_id, rid=rid, tag="pr6")
            ok, reason, _ = await ffps.check_function_term_eligibility(session, row)
            assert not ok and reason == "function_term_not_active"
            final = await fmcps.promote_region_function(_ctx(session), row, review_record_id=None)
            assert final is None  # no Final relation
            ftriples = (await session.execute(
                select(FinalKgTriple).where(FinalKgTriple.resource_id == rid)
            )).scalars().all()
            assert not ftriples  # no Final triple
            assert row.promotion_status == MirrorPromotionStatus.not_promoted
            term2 = await session.get(OntologyTerm, term.id)
            assert term2.status == "proposed"  # not auto-activated
    _run(_case())


def test_07_ontology_merge_propagates_all_layers(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            t2 = _term(session, f"{TEST_PREFIX}can7")
            await session.flush()
            t1 = _term(session, f"{TEST_PREFIX}old7")
            await session.flush()
            row = await _make_region(session, term=t1, cand=cand_id, rid=rid, tag="mg7")
            await fmcps.promote_region_function(_ctx(session), row, review_record_id=None)
            await session.flush()
            # real merge service
            await ontology_service.merge_term(session, t1.id, t2.id, operator_id="p18_test", reason="test merge")
            await session.flush()
            # mirror relation + mirror triple redirected
            row2 = await session.get(MirrorRegionFunction, row.id)
            assert row2.term_id == t2.id
            mt = (await session.execute(
                select(MirrorKgTriple).where(MirrorKgTriple.resource_id == rid)
            )).scalar_one()
            assert mt.object_id == t2.id
            # final relation + final triple redirected (P1.8 propagation)
            final = (await session.execute(
                select(FinalRegionFunction).where(FinalRegionFunction.raw_payload_json["p18_test"].astext.is_not(None))
            )).scalar_one()
            assert final.term_id == t2.id
            ft = (await session.execute(
                select(FinalKgTriple).where(FinalKgTriple.resource_id == rid)
            )).scalar_one()
            assert ft.object_id == t2.id
            # no merged-term reference anywhere
            assert final.term_id != t1.id and mt.object_id != t1.id and ft.object_id != t1.id
    _run(_case())


def test_08_rename_refreshes_labels_keeps_identity(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}rn8")
            await session.flush()
            row = await _make_region(session, term=term, cand=cand_id, rid=rid, tag="rn8")
            await fmcps.promote_region_function(_ctx(session), row, review_record_id=None)
            await session.flush()
            term.canonical_term_en = f"{TEST_PREFIX}renamed8"
            await session.flush()
            from app.services.function_triple_projection_service import refresh_function_term_projection

            await refresh_function_term_projection(session, term.id)
            await session.flush()
            mt = (await session.execute(
                select(MirrorKgTriple).where(MirrorKgTriple.resource_id == rid)
            )).scalar_one()
            ft = (await session.execute(
                select(FinalKgTriple).where(FinalKgTriple.resource_id == rid)
            )).scalar_one()
            assert mt.object_id == term.id and ft.object_id == term.id  # identity unchanged
            assert mt.object_label == f"{TEST_PREFIX}renamed8"
            assert ft.object_label == f"{TEST_PREFIX}renamed8"  # label refreshed
            assert len((await session.execute(
                select(MirrorKgTriple).where(MirrorKgTriple.resource_id == rid)
            )).scalars().all()) == 1  # no new triple
    _run(_case())


def test_09_final_integrity_clean_with_data(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            terms = [_term(session, f"{TEST_PREFIX}f{i}") for i in range(1, 7)]
            await session.flush()
            r1 = await _make_region(session, term=terms[0], cand=cand_id, rid=rid, tag="f1")
            r2 = await _make_region(session, term=terms[1], cand=cand_id, rid=rid, tag="f2")
            p1, c1 = await _make_projection(session, term=terms[2], rid=rid, tag="f3")
            p2, c2 = await _make_projection(session, term=terms[3], rid=rid, tag="f4")
            cf1, cc1 = await _make_circuit(session, term=terms[4], rid=rid, tag="f5")
            cf2, cc2 = await _make_circuit(session, term=terms[5], rid=rid, tag="f6")
            await _final_projection(session, conn=c1, rid=rid)
            await _final_projection(session, conn=c2, rid=rid)
            await _final_circuit(session, circ=cc1, rid=rid)
            await _final_circuit(session, circ=cc2, rid=rid)
            await session.flush()
            for row in (r1, r2):
                await fmcps.promote_region_function(_ctx(session), row, review_record_id=None)
            for row, _c in ((p1, c1), (p2, c2)):
                await fmcps.promote_projection_function(_ctx(session), row, review_record_id=None)
            for row, _c in ((cf1, cc1), (cf2, cc2)):
                await fmcps.promote_circuit_function(_ctx(session), row, review_record_id=None)
            await session.flush()
            r = await ffps.check_final_function_integrity(session)
            assert r["final_function_triples"] == 6  # data present
            for key in (
                "relation_term_id_null", "relation_orphan_term", "relation_invalid_term",
                "relation_proposed_term", "relation_merged_term", "relation_deprecated_term",
                "triple_object_id_null", "triple_orphan_object", "triple_invalid_object",
                "triple_proposed_object", "triple_merged_object", "triple_deprecated_object",
                "triple_duplicate_spo", "triple_missing_final_relation_lineage",
                "triple_mirror_subject", "triple_wrong_label",
            ):
                assert r[key] == 0, f"{key} = {r[key]}"
    _run(_case())


def test_10_invariants_pass_with_data(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}inv10")
            await session.flush()
            row = await _make_region(session, term=term, cand=cand_id, rid=rid, tag="inv10")
            await fmcps.promote_region_function(_ctx(session), row, review_record_id=None)
            await session.flush()
            inv = await fkis.check_function_kg_invariants(session)
            for k, (ok, ev) in inv.items():
                assert ok, f"{k}: {ev}"
    _run(_case())
