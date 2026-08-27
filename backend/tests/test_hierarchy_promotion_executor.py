"""FN1 promote executor tests: batched writes into ontology_term_relations.

Covers:
  * batched writes (batch_size validation, batch splitting)
  * per-batch gates: endpoint existence/type/status, duplicate, subclass_of,
    cycle
  * provenance: candidate_id, generation_version, confidence, source
  * idempotent re-run
  * post-promotion statistics (depth, roots, orphans, cycle audit)
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.ontology import (
    OntologyHierarchyCandidate,
    OntologyTerm,
    OntologyTermRelation,
)
from app.services import hierarchy_promotion_executor as hpe
from app.services.hierarchy_promotion_executor import PROMOTION_SOURCE

TEST_PREFIX = "promote_test_"
TEST_VERSION = "function_hierarchy_candidate_promote_test"

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
            terms = (await session.execute(
                select(OntologyTerm).where(
                    OntologyTerm.term_code.like(f"ng:func:{TEST_PREFIX}%")
                    | OntologyTerm.term_code.like(f"ng:region:{TEST_PREFIX}%")
                )
            )).scalars().all()
            ids = [str(t.id) for t in terms]
            if ids:
                # FK order: relations/candidates first, then the terms
                rel_t = OntologyTermRelation.__table__
                cand_t = OntologyHierarchyCandidate.__table__
                term_t = OntologyTerm.__table__
                for col in (rel_t.c.subject_term_id, rel_t.c.object_term_id):
                    await session.execute(rel_t.delete().where(col.in_(ids)))
                for col in (cand_t.c.child_term_id, cand_t.c.parent_term_id):
                    await session.execute(cand_t.delete().where(col.in_(ids)))
                await session.execute(term_t.delete().where(term_t.c.id.in_(ids)))
            await session.commit()

    yield
    _run(_cleanup())


async def _terms(session, *names, **kw):
    out = {}
    status = kw.get("status", "active")
    for n in names:
        t = OntologyTerm(
            term_code=f"ng:func:{TEST_PREFIX}{n.replace(' ', '_')}",
            canonical_term_en=f"{TEST_PREFIX}{n}",
            term_type="function",
            status=status,
            created_by="promote_test",
        )
        session.add(t)
        out[n] = t
    await session.flush()
    return out


def _candidate(session, child, parent, *, method="lexical_containment",
               tier="high_confidence", score=1.5, version=TEST_VERSION):
    session.add(OntologyHierarchyCandidate(
        child_term_id=child.id,
        parent_term_id=parent.id,
        candidate_score=score,
        generation_method=method,
        generation_reasons_json={
            "quality_tier": tier,
            "quality_score": score,
            "quality_reasons": [],
        },
        generation_version=version,
        status="pending",
        created_by="promote_test",
    ))
    return score


def _region(session, name):
    t = OntologyTerm(
        term_code=f"ng:region:{TEST_PREFIX}{name.replace(' ', '_')}",
        canonical_term_en=f"{TEST_PREFIX}{name}",
        term_type="region",
        status="active",
        created_by="promote_test",
    )
    session.add(t)
    return t


async def _count_edges(session) -> int:
    return len((await session.execute(select(OntologyTermRelation))).scalars().all())


# ---------------------------------------------------------------- batching


def test_batch_size_validation(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory")
            _candidate(session, ts["working memory"], ts["memory"])
            await session.flush()
            for bad in (100, 2000):
                with pytest.raises(ValueError):
                    await hpe.promote_candidates(
                        session, candidate_version=TEST_VERSION, batch_size=bad,
                    )
    _run(_case())


def test_promote_basic_flow(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory", "episodic memory")
            _candidate(session, ts["working memory"], ts["memory"], score=1.5)
            _candidate(session, ts["episodic memory"], ts["memory"], score=1.2)
            await session.flush()
            res = await hpe.promote_candidates(
                session, candidate_version=TEST_VERSION, created_by="promote_test",
            )
            assert res["promoted_edges"] == 2
            assert res["batches_completed"] == 1
            assert res["status"] == "proposed"
            assert await _count_edges(session) == 2
            edges = (await session.execute(select(OntologyTermRelation))).scalars().all()
            for e in edges:
                assert e.predicate == "subclass_of"
                assert e.source == PROMOTION_SOURCE
                assert e.created_by == "promote_test"
    _run(_case())


def test_promote_splits_into_batches(db, monkeypatch):
    monkeypatch.setattr(hpe, "MIN_BATCH_SIZE", 1)
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory", "episodic memory")
            for child, parent in (
                (ts["working memory"], ts["memory"]),
                (ts["episodic memory"], ts["memory"]),
            ):
                _candidate(session, child, parent)
            await session.flush()
            res = await hpe.promote_candidates(
                session, candidate_version=TEST_VERSION, batch_size=1,
                created_by="promote_test",
            )
            assert res["batches_completed"] == 2
            assert res["promoted_edges"] == 2
            assert await _count_edges(session) == 2
    _run(_case())


# ---------------------------------------------------------------- per-batch gates


def test_promote_rejects_non_function_parent(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory")
            parent = _region(session, "brain")
            await session.flush()
            _candidate(session, ts["working memory"], parent)
            await session.flush()
            res = await hpe.promote_candidates(
                session, candidate_version=TEST_VERSION, created_by="promote_test",
            )
            assert res["promoted_edges"] == 0
            assert res["rejected"]["parent_non_function"] == 1
            assert await _count_edges(session) == 0
    _run(_case())


def test_promote_duplicate_skipped(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory")
            session.add(OntologyTermRelation(
                subject_term_id=ts["working memory"].id,
                predicate="subclass_of",
                object_term_id=ts["memory"].id,
                status="proposed",
                source="promote_test",
                provenance_json={},
            ))
            _candidate(session, ts["working memory"], ts["memory"])
            await session.flush()
            res = await hpe.promote_candidates(
                session, candidate_version=TEST_VERSION, created_by="promote_test",
            )
            assert res["promoted_edges"] == 0
            assert res["rejected"]["duplicate"] == 1
            assert await _count_edges(session) == 1  # pre-existing edge untouched
    _run(_case())


def test_promote_cycle_skipped(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "visual memory", "working memory")
            # existing 2-cycle memory ⇄ visual memory
            for s, o in ((ts["memory"], ts["visual memory"]),
                         (ts["visual memory"], ts["memory"])):
                session.add(OntologyTermRelation(
                    subject_term_id=s.id, predicate="subclass_of",
                    object_term_id=o.id, status="active",
                    source="promote_test", provenance_json={},
                ))
            _candidate(session, ts["working memory"], ts["memory"])
            await session.flush()
            res = await hpe.promote_candidates(
                session, candidate_version=TEST_VERSION, created_by="promote_test",
            )
            assert res["promoted_edges"] == 0
            assert res["rejected"]["cycle"] == 1
            assert await _count_edges(session) == 2
    _run(_case())


def test_promote_subclass_of_rejected(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory")
            _candidate(session, ts["working memory"], ts["memory"], method="metadata")
            await session.flush()
            res = await hpe.promote_candidates(
                session, candidate_version=TEST_VERSION, created_by="promote_test",
            )
            assert res["promoted_edges"] == 0
            assert res["rejected"]["subclass_of"] == 1
    _run(_case())


# ---------------------------------------------------------------- provenance


def test_promote_preserves_provenance(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory")
            _candidate(session, ts["working memory"], ts["memory"], score=0.87)
            await session.flush()
            res = await hpe.promote_candidates(
                session, candidate_version=TEST_VERSION, created_by="promote_test",
            )
            assert res["promoted_edges"] == 1
            edge = (await session.execute(select(OntologyTermRelation))).scalars().first()
            assert edge is not None
            assert float(edge.confidence) == 0.87
            prov = edge.provenance_json
            assert prov["candidate_id"]
            assert prov["generation_version"] == TEST_VERSION
            assert prov["generation_method"] == "lexical_containment"
            assert prov["quality_tier"] == "high_confidence"
            assert edge.source == PROMOTION_SOURCE
    _run(_case())


def test_promote_idempotent(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory")
            _candidate(session, ts["working memory"], ts["memory"])
            await session.flush()
            first = await hpe.promote_candidates(
                session, candidate_version=TEST_VERSION, created_by="promote_test",
            )
            assert first["promoted_edges"] == 1
            second = await hpe.promote_candidates(
                session, candidate_version=TEST_VERSION, created_by="promote_test",
            )
            assert second["promoted_edges"] == 0
            assert second["rejected"]["duplicate"] == 1
            assert await _count_edges(session) == 1
    _run(_case())


# ---------------------------------------------------------------- stats


def test_stats_chain_depth_and_roots(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory", "working memory consolidation")
            session.add(OntologyTermRelation(
                subject_term_id=ts["working memory"].id, predicate="subclass_of",
                object_term_id=ts["memory"].id, status="active",
                source="promote_test", provenance_json={},
            ))
            session.add(OntologyTermRelation(
                subject_term_id=ts["working memory consolidation"].id, predicate="subclass_of",
                object_term_id=ts["working memory"].id, status="active",
                source="promote_test", provenance_json={},
            ))
            await session.flush()
            stats = await hpe.build_hierarchy_stats(session)
            assert stats["total_edges"] == 2
            assert stats["max_depth"] == 2  # consolidation → working → memory
            assert stats["root_functions"] == 1  # memory (no parent)
            assert stats["cycle_audit"]["pass"] is True
    _run(_case())


def test_stats_orphan_functions(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory")
            session.add(OntologyTermRelation(
                subject_term_id=ts["working memory"].id, predicate="subclass_of",
                object_term_id=ts["memory"].id, status="active",
                source="promote_test", provenance_json={},
            ))
            await session.flush()
            # baseline over the real DB (many pre-existing function terms)
            before = await hpe.build_hierarchy_stats(session)
            # add one unattached function term → orphan count rises by exactly 1
            await _terms(session, "unattached function")
            await session.flush()
            after = await hpe.build_hierarchy_stats(session)
            assert after["orphan_functions"] == before["orphan_functions"] + 1
            assert after["root_functions"] == before["root_functions"]  # unchanged
    _run(_case())


def test_stats_cycle_audit_detects_cycle(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "visual memory")
            for s, o in ((ts["memory"], ts["visual memory"]),
                         (ts["visual memory"], ts["memory"])):
                session.add(OntologyTermRelation(
                    subject_term_id=s.id, predicate="subclass_of",
                    object_term_id=o.id, status="active",
                    source="promote_test", provenance_json={},
                ))
            await session.flush()
            stats = await hpe.build_hierarchy_stats(session)
            assert stats["cycle_audit"]["pass"] is False
            assert stats["cycle_audit"]["cyclic_nodes"] == 2
    _run(_case())


def test_summary_text():
    res = {
        "candidate_version": "v2", "tier": "high_confidence",
        "batch_size": 500, "status": "proposed",
        "total_candidates": 10, "tier_included": 10,
        "batches_completed": 1, "promoted_edges": 8, "rejected_total": 2,
        "rejected": {"duplicate": 1, "subclass_of": 1, "cycle": 0,
                     "child_term_missing": 0, "parent_term_missing": 0,
                     "child_non_function": 0, "parent_non_function": 0,
                     "child_status": 0, "parent_status": 0},
        "stats": {
            "total_edges": 8, "max_depth": 4, "root_functions": 3,
            "orphan_functions": 12,
            "cycle_audit": {"pass": True, "cyclic_nodes": 0},
        },
        "source": "v2",
    }
    text = hpe.promotion_summary_text(res)
    assert "PROMOTED EDGES    : 8" in text
    assert "max_depth 4" in text
    assert "cycle audit: PASS (0 cyclic nodes)" in text
