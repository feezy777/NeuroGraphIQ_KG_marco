"""P1.6 incremental Function Triple projection tests (24 acceptance cases).

Scoped by unique resource_id. Verifies create/update/delete/supersede/merge/
rename all auto-sync Mirror Function Triples via subject-scope reconcile, and
that incremental state equals full-rebuild state.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select

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
from app.models.ontology import OntologyTerm
from app.schemas.mirror_kg import (
    MirrorKgTripleCreate,
    MirrorPromotionStatus,
    MirrorRegionFunctionCreate,
    MirrorReviewStatus,
    MirrorStatus,
    TripleObjectType,
    TripleSubjectType,
)
from app.schemas.mirror_macro_clinical import (
    MirrorCircuitFunctionCreate,
    MirrorProjectionFunctionCreate,
)
from app.services import (
    function_triple_projection_service as ftps,
    function_triple_rebuild_service as ftrs,
    mirror_kg_service as mks,
    mirror_macro_clinical_service as mmcs,
)

TEST_PREFIX = "p16_test_"
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
                    model.__table__.c.raw_payload_json["p16_test"].astext.is_not(None)
                ))
            if _TEST_RIDS:
                await session.execute(MirrorKgTriple.__table__.delete().where(
                    MirrorKgTriple.__table__.c.resource_id.in_([str(r) for r in _TEST_RIDS])
                ))
            # triples whose object points at a test term (resource_id may be NULL)
            test_term_ids = (
                await session.execute(
                    select(OntologyTerm.id).where(
                        OntologyTerm.__table__.c.canonical_term_en.like(f"{TEST_PREFIX}%")
                    )
                )
            ).scalars().all()
            if test_term_ids:
                await session.execute(MirrorKgTriple.__table__.delete().where(
                    MirrorKgTriple.__table__.c.object_id.in_([str(t) for t in test_term_ids])
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
        created_by="p16_test",
    )
    session.add(term)
    if replaced_by:
        term.replaced_by_term_id = replaced_by
    return term


async def _fn_triples(session, *, rid: uuid.UUID, subject_type: str | None = None):
    q = select(MirrorKgTriple).where(
        MirrorKgTriple.resource_id == rid,
        MirrorKgTriple.object_type == TripleObjectType.function,
    )
    if subject_type:
        q = q.where(MirrorKgTriple.subject_type == subject_type)
    return (await session.execute(q)).scalars().all()


async def _region_fn(session, *, name: str, term_id, cand, rid, relation="involved_in",
                     category="cognitive") -> MirrorRegionFunction:
    return await mks.create_mirror_function(session, MirrorRegionFunctionCreate(
        region_candidate_id=cand,
        resource_id=rid,
        granularity_level="macro_clinical",
        granularity_family="macro",
        source_atlas="test_atlas",
        function_term=name,
        function_category=category,
        relation_type=relation,
        confidence=0.8,
        raw_payload_json={"p16_test": True},
    ))


# ---------------------------------------------------------------- 1-3 create


def test_01_region_create_projects_triple(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}r1")
            await session.flush()
            await _region_fn(session, name=f"{TEST_PREFIX}r1", term_id=term.id, cand=cand_id, rid=rid)
            await session.flush()
            rows = await _fn_triples(session, rid=rid)
            assert len(rows) == 1
            assert rows[0].object_id == term.id
            assert rows[0].subject_id == cand_id
    _run(_case())


def test_02_projection_create_projects_triple(db, rid):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}p2")
            await session.flush()
            conn = MirrorRegionConnection(
                resource_id=rid, granularity_level="macro_clinical", granularity_family="macro",
                source_atlas="test_atlas", connection_type="projection", directionality="directed",
                mirror_status=MirrorStatus.llm_suggested, review_status=MirrorReviewStatus.pending,
                promotion_status=MirrorPromotionStatus.not_promoted, raw_payload_json={"p16_test": True},
            )
            session.add(conn)
            await session.flush()
            await mmcs.create_projection_function(session, MirrorProjectionFunctionCreate(
                projection_id=conn.id, resource_id=rid, granularity_level="macro_clinical",
                granularity_family="macro", source_atlas="test_atlas",
                function_term=f"{TEST_PREFIX}p2", relation_type="modulates",
                raw_payload_json={"p16_test": True},
            ))
            await session.flush()
            rows = await _fn_triples(session, rid=rid)
            assert len(rows) == 1
            assert rows[0].object_id == term.id
            assert rows[0].subject_type == TripleSubjectType.connection
            assert rows[0].predicate == "modulates_function"
    _run(_case())


def test_03_circuit_create_projects_triple(db, rid):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}c3")
            await session.flush()
            circ = MirrorRegionCircuit(
                resource_id=rid, granularity_level="macro_clinical", granularity_family="macro",
                source_atlas="test_atlas", circuit_name="p16 circuit", circuit_type="simple",
                mirror_status=MirrorStatus.llm_suggested, review_status=MirrorReviewStatus.pending,
                promotion_status=MirrorPromotionStatus.not_promoted, raw_payload_json={"p16_test": True},
            )
            session.add(circ)
            await session.flush()
            await mmcs.create_circuit_function(session, MirrorCircuitFunctionCreate(
                circuit_id=circ.id, resource_id=rid, granularity_level="macro_clinical",
                granularity_family="macro", source_atlas="test_atlas",
                function_term_en=f"{TEST_PREFIX}c3", raw_payload_json={"p16_test": True},
            ))
            await session.flush()
            rows = await _fn_triples(session, rid=rid)
            assert len(rows) == 1
            assert rows[0].object_id == term.id
            assert rows[0].subject_type == TripleSubjectType.circuit
    _run(_case())


# ---------------------------------------------------------------- 4-6 update


def test_04_source_text_change_same_term_keeps_identity(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}u4")
            await session.flush()
            row = await _region_fn(session, name=f"{TEST_PREFIX}u4", term_id=term.id, cand=cand_id, rid=rid)
            await session.flush()
            before = await _fn_triples(session, rid=rid)
            triple_id = before[0].id
            await mks.update_mirror_function(session, row.id, {"function_term": f"{TEST_PREFIX}U4!"})
            await session.flush()
            after = await _fn_triples(session, rid=rid)
            assert len(after) == 1
            assert after[0].id == triple_id          # identity unchanged
            assert after[0].object_id == term.id     # object unchanged
    _run(_case())


def test_05_term_change_reconciles_old_and_new(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            t1 = _term(session, f"{TEST_PREFIX}f1")
            t2 = _term(session, f"{TEST_PREFIX}f2")
            await session.flush()
            row = await _region_fn(session, name=f"{TEST_PREFIX}f1", term_id=t1.id, cand=cand_id, rid=rid)
            await session.flush()
            assert len(await _fn_triples(session, rid=rid)) == 1
            await mks.update_mirror_function(session, row.id, {"term_id": t2.id})
            await session.flush()
            rows = await _fn_triples(session, rid=rid)
            assert len(rows) == 1
            assert rows[0].object_id == t2.id  # old SPO gone, new SPO present
    _run(_case())


def test_06_qualifier_change_updates_predicate(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}q6")
            await session.flush()
            row = await _region_fn(session, name=f"{TEST_PREFIX}q6", term_id=term.id, cand=cand_id, rid=rid,
                                   relation="associated_with")
            await session.flush()
            rows = await _fn_triples(session, rid=rid)
            assert rows[0].predicate == "associated_with_function"
            await mks.update_mirror_function(session, row.id, {"relation_type": "modulates"})
            await session.flush()
            rows = await _fn_triples(session, rid=rid)
            assert len(rows) == 1
            assert rows[0].predicate == "modulates_function"  # no stale old-predicate triple
    _run(_case())


# ---------------------------------------------------------------- 7-9 delete/supersede/reject


def test_07_relation_delete_removes_triple(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}d7")
            await session.flush()
            row = await _region_fn(session, name=f"{TEST_PREFIX}d7", term_id=term.id, cand=cand_id, rid=rid)
            await session.flush()
            assert len(await _fn_triples(session, rid=rid)) == 1
            await mks.delete_mirror_function(session, row.id)
            await session.flush()
            assert len(await _fn_triples(session, rid=rid)) == 0
    _run(_case())


def test_08_superseded_removes_lineage(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}s8")
            await session.flush()
            row = await _region_fn(session, name=f"{TEST_PREFIX}s8", term_id=term.id, cand=cand_id, rid=rid)
            await session.flush()
            row.mirror_status = MirrorStatus.superseded
            await session.flush()
            await ftps.reconcile_function_subject(
                session, subject_type=TripleSubjectType.region_candidate, subject_id=cand_id
            )
            await session.flush()
            assert len(await _fn_triples(session, rid=rid)) == 0
    _run(_case())


def test_09_rejected_not_projected(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}rj9")
            await session.flush()
            row = await _region_fn(session, name=f"{TEST_PREFIX}rj9", term_id=term.id, cand=cand_id, rid=rid)
            await session.flush()
            assert len(await _fn_triples(session, rid=rid)) == 1
            row.review_status = MirrorReviewStatus.rejected
            row.mirror_status = MirrorStatus.human_rejected
            await session.flush()
            await ftps.reconcile_function_subject(
                session, subject_type=TripleSubjectType.region_candidate, subject_id=cand_id
            )
            await session.flush()
            assert len(await _fn_triples(session, rid=rid)) == 0
    _run(_case())


# ---------------------------------------------------------------- 10-12 multi-source


def test_10_multi_source_delete_one_keeps_triple(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}m10_a")
            await session.flush()
            r1 = await _region_fn(session, name=f"{TEST_PREFIX}m10_a", term_id=term.id, cand=cand_id, rid=rid)
            r2 = await _region_fn(session, name=f"{TEST_PREFIX}m10 a", term_id=term.id, cand=cand_id, rid=rid,
                                 category="motor")
            await session.flush()
            rows = await _fn_triples(session, rid=rid)
            assert len(rows) == 1
            prov = (rows[0].raw_payload_json or {}).get("provenance", {})
            assert str(r1.id) in prov["source_relation_ids"] and str(r2.id) in prov["source_relation_ids"]
            await mks.delete_mirror_function(session, r1.id)
            await session.flush()
            rows = await _fn_triples(session, rid=rid)
            assert len(rows) == 1  # triple survives
            prov = (rows[0].raw_payload_json or {}).get("provenance", {})
            assert str(r2.id) in prov["source_relation_ids"]
            assert str(r1.id) not in prov["source_relation_ids"]
    _run(_case())


def test_11_delete_last_source_removes_triple(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}m11_a")
            await session.flush()
            r1 = await _region_fn(session, name=f"{TEST_PREFIX}m11_a", term_id=term.id, cand=cand_id, rid=rid)
            r2 = await _region_fn(session, name=f"{TEST_PREFIX}m11 a", term_id=term.id, cand=cand_id, rid=rid,
                                 category="motor")
            await session.flush()
            await mks.delete_mirror_function(session, r1.id)
            await session.flush()
            await mks.delete_mirror_function(session, r2.id)
            await session.flush()
            assert len(await _fn_triples(session, rid=rid)) == 0
    _run(_case())


def test_12_second_source_merges_lineage(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}m12_a")
            await session.flush()
            r1 = await _region_fn(session, name=f"{TEST_PREFIX}m12_a", term_id=term.id, cand=cand_id, rid=rid)
            await session.flush()
            rows = await _fn_triples(session, rid=rid)
            assert len(rows) == 1
            prov = (rows[0].raw_payload_json or {}).get("provenance", {})
            assert str(r1.id) in prov["source_relation_ids"]
            r2 = await _region_fn(session, name=f"{TEST_PREFIX}m12 a", term_id=term.id, cand=cand_id, rid=rid,
                                 category="motor")
            await session.flush()
            rows = await _fn_triples(session, rid=rid)
            assert len(rows) == 1  # still one SPO
            prov = (rows[0].raw_payload_json or {}).get("provenance", {})
            assert str(r1.id) in prov["source_relation_ids"] and str(r2.id) in prov["source_relation_ids"]
    _run(_case())


# ---------------------------------------------------------------- 13-15 terms


def test_13_proposed_term_projects(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}pr13", status="proposed")
            await session.flush()
            await _region_fn(session, name=f"{TEST_PREFIX}pr13", term_id=term.id, cand=cand_id, rid=rid)
            await session.flush()
            rows = await _fn_triples(session, rid=rid)
            assert len(rows) == 1 and rows[0].object_id == term.id
    _run(_case())


def test_14_deprecated_not_projected(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}dp14", status="deprecated")
            await session.flush()
            await _region_fn(session, name=f"{TEST_PREFIX}dp14", term_id=term.id, cand=cand_id, rid=rid)
            await session.flush()
            assert len(await _fn_triples(session, rid=rid)) == 0
    _run(_case())


def test_15_merged_term_redirects_automatically(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            canon = _term(session, f"{TEST_PREFIX}can15")
            await session.flush()
            old = _term(session, f"{TEST_PREFIX}old15", status="merged", replaced_by=canon.id)
            await session.flush()
            await _region_fn(session, name=f"{TEST_PREFIX}old15", term_id=old.id, cand=cand_id, rid=rid)
            await session.flush()
            rows = await _fn_triples(session, rid=rid)
            assert len(rows) == 1
            assert rows[0].object_id == canon.id  # redirected, never the merged term
    _run(_case())


# ---------------------------------------------------------------- 16-18 rename / association


def test_16_canonical_rename_updates_label(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}rn16")
            await session.flush()
            await _region_fn(session, name=f"{TEST_PREFIX}rn16", term_id=term.id, cand=cand_id, rid=rid)
            await session.flush()
            rows = await _fn_triples(session, rid=rid)
            assert rows[0].object_label == f"{TEST_PREFIX}rn16"
            term.canonical_term_en = f"{TEST_PREFIX}renamed"
            await session.flush()
            await ftps.refresh_function_term_projection(session, term.id)
            await session.flush()
            rows = await _fn_triples(session, rid=rid)
            assert len(rows) == 1
            assert rows[0].object_label == f"{TEST_PREFIX}renamed"
            assert rows[0].object_id == term.id  # identity unchanged
    _run(_case())


def test_17_rename_does_not_change_canonical_key(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}rk17")
            await session.flush()
            await _region_fn(session, name=f"{TEST_PREFIX}rk17", term_id=term.id, cand=cand_id, rid=rid)
            await session.flush()
            rows = await _fn_triples(session, rid=rid)
            assert len(rows) == 1  # rename never duplicates the SPO
            term.canonical_term_en = f"{TEST_PREFIX}renamed17"
            await session.flush()
            await ftps.refresh_function_term_projection(session, term.id)
            await session.flush()
            assert len(await _fn_triples(session, rid=rid)) == 1
    _run(_case())


def test_18_association_sync_projects_via_relation(db, rid):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}as18")
            await session.flush()
            circ = MirrorRegionCircuit(
                resource_id=rid, granularity_level="macro_clinical", granularity_family="macro",
                source_atlas="test_atlas", circuit_name="p16 assoc", circuit_type="simple",
                function_association=f"{TEST_PREFIX}as18",
                mirror_status=MirrorStatus.llm_suggested, review_status=MirrorReviewStatus.pending,
                promotion_status=MirrorPromotionStatus.not_promoted, raw_payload_json={"p16_test": True},
            )
            session.add(circ)
            await session.flush()
            await mmcs.sync_circuit_function_from_association(
                session, circuit=circ, function_association=circ.function_association, created_by="test"
            )
            await session.flush()
            rows = await _fn_triples(session, rid=rid)
            assert len(rows) == 1
            assert rows[0].object_id == term.id  # projected from the relation, not the text
    _run(_case())


# ---------------------------------------------------------------- 19-21 batch / idempotency / rollback


def test_19_batch_projection_dedups_subject(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            t1 = _term(session, f"{TEST_PREFIX}b19a")
            t2 = _term(session, f"{TEST_PREFIX}b19b")
            await session.flush()
            r1 = await _region_fn(session, name=f"{TEST_PREFIX}b19a", term_id=t1.id, cand=cand_id, rid=rid)
            r2 = await _region_fn(session, name=f"{TEST_PREFIX}b19b", term_id=t2.id, cand=cand_id, rid=rid)
            await session.flush()
            # simulate an external inconsistency (one triple lost), then
            # batch-project via ids → one subject, one reconcile
            triples = await _fn_triples(session, rid=rid)
            assert len(triples) == 2
            await session.execute(
                MirrorKgTriple.__table__.delete().where(MirrorKgTriple.id == triples[0].id)
            )
            await session.flush()
            results = await ftps.project_changed_function_relations(
                session, [r1.id, r2.id]
            )
            assert len(results) == 1  # single subject scope despite 2 ids
            assert len(await _fn_triples(session, rid=rid)) == 2  # repaired
    _run(_case())


def test_20_incremental_twice_idempotent(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}id20")
            await session.flush()
            await _region_fn(session, name=f"{TEST_PREFIX}id20", term_id=term.id, cand=cand_id, rid=rid)
            await session.flush()
            s1 = await ftps.reconcile_function_subject(
                session, subject_type=TripleSubjectType.region_candidate, subject_id=cand_id
            )
            s2 = await ftps.reconcile_function_subject(
                session, subject_type=TripleSubjectType.region_candidate, subject_id=cand_id
            )
            assert s1.inserted_count == 0 and s1.upgraded_count == 0
            assert s2.inserted_count == 0 and s2.upgraded_count == 0
    _run(_case())


def test_21_projection_failure_rolls_back_transaction(db, rid, cand_id, monkeypatch):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _term(session, f"{TEST_PREFIX}rb21")
            await session.flush()

            async def _boom(*args, **kwargs):
                raise RuntimeError("projection failure (injected)")

            monkeypatch.setattr(ftps, "reconcile_function_subject", _boom)
            with pytest.raises(RuntimeError):
                await _region_fn(session, name=f"{TEST_PREFIX}rb21", term_id=term.id, cand=cand_id, rid=rid)
            await session.rollback()
            # relation must not have been committed either
            rows = (await session.execute(
                select(MirrorRegionFunction).where(
                    MirrorRegionFunction.resource_id == rid,
                    MirrorRegionFunction.function_term == f"{TEST_PREFIX}rb21",
                )
            )).scalars().all()
            assert not rows
    _run(_case())


# ---------------------------------------------------------------- 22-24 consistency


def test_22_rebuild_after_incremental_zero_diff(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            t1 = _term(session, f"{TEST_PREFIX}z22a")
            t2 = _term(session, f"{TEST_PREFIX}z22b")
            await session.flush()
            await _region_fn(session, name=f"{TEST_PREFIX}z22a", term_id=t1.id, cand=cand_id, rid=rid)
            r2 = await _region_fn(session, name=f"{TEST_PREFIX}z22b", term_id=t2.id, cand=cand_id, rid=rid)
            await session.flush()
            # incremental ops: delete one source of a two-source SPO? simpler:
            await mks.update_mirror_function(session, r2.id, {"relation_type": "modulates"})
            await session.flush()
            # full rebuild on the whole DB must find zero diff for this scope
            stats = await ftrs.rebuild_function_triples(session, dry_run=True)
            assert stats.inserted_count == 0
            assert stats.stale_deleted_count == 0
    _run(_case())


def test_23_integrity_checker_clean():
    async def _case():
        async with AsyncSessionLocal() as session:
            r = await ftps.check_function_projection_integrity(session)
            for key in (
                "object_id_null", "orphan_object", "invalid_type_object",
                "merged_object", "deprecated_object", "duplicate_spo",
                "missing_desired", "stale_triples", "wrong_object_id",
                "wrong_predicate", "wrong_label", "wrong_lineage", "empty_lineage",
            ):
                assert r[key] == 0, f"{key} = {r[key]}"
    _run(_case())


def test_24_non_function_triples_untouched(db, rid, cand_id):
    async def _case():
        async with AsyncSessionLocal() as session:
            conn = MirrorRegionConnection(
                source_region_candidate_id=None, target_region_candidate_id=None,
                resource_id=rid, granularity_level="macro_clinical", granularity_family="macro",
                source_atlas="test_atlas", connection_type="structural_connection",
                directionality="directed",
                mirror_status=MirrorStatus.llm_suggested, review_status=MirrorReviewStatus.pending,
                promotion_status=MirrorPromotionStatus.not_promoted, raw_payload_json={"p16_test": True},
            )
            session.add(conn)
            await session.flush()
            await mks.create_mirror_triple(session, MirrorKgTripleCreate(
                subject_type=TripleSubjectType.region_candidate, subject_id=uuid.uuid4(),
                subject_label="s", predicate="structurally_connects_to",
                object_type=TripleObjectType.region_candidate, object_id=uuid.uuid4(),
                object_label="t", granularity_level="macro_clinical", source_atlas="test_atlas",
                resource_id=rid, raw_payload_json={"p16_test": True},
            ))
            await session.flush()
            term = _term(session, f"{TEST_PREFIX}n24")
            await session.flush()
            await _region_fn(session, name=f"{TEST_PREFIX}n24", term_id=term.id, cand=cand_id, rid=rid)
            await session.flush()
            conn_rows = (await session.execute(
                select(MirrorKgTriple).where(
                    MirrorKgTriple.predicate == "structurally_connects_to",
                    MirrorKgTriple.resource_id == rid,
                )
            )).scalars().all()
            assert len(conn_rows) == 1  # untouched by function projection
    _run(_case())
