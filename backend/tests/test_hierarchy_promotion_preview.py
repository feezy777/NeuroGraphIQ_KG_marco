"""FN1 promote preview tests.

Covers the read-only promotion preview pipeline:
  * subclass_of semantic gate (pure function)
  * tier gate, endpoint checks, duplicate checks, cycle checks
  * merged → canonical resolution
  * no writes to ontology_term_relations
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
from app.services import hierarchy_promotion_service as hps

TEST_PREFIX = "preview_test_"
TEST_VERSION = "function_hierarchy_candidate_preview_test"

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
            if terms:
                ids = [str(t.id) for t in terms]
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
            created_by="preview_test",
        )
        session.add(t)
        out[n] = t
    await session.flush()
    return out


def _candidate(session, child, parent, *, method="lexical_containment",
               tier="high_confidence", score=1.5, version=TEST_VERSION):
    row = OntologyHierarchyCandidate(
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
        created_by="preview_test",
    )
    session.add(row)
    return row


# ---------------------------------------------------------------- subclass_of gate


def test_subclass_of_keeps_concept_containment():
    ok, reasons = hps.assess_subclass_of_semantics(
        "working memory", "memory", "lexical_containment",
    )
    assert ok and not reasons


def test_subclass_of_keeps_multiword_specialization():
    ok, reasons = hps.assess_subclass_of_semantics(
        "visual object recognition", "visual recognition", "lexical_containment",
    )
    assert ok and not reasons


def test_subclass_of_rejects_related_to_methods():
    for method in ("metadata", "category_group", "compound_component"):
        ok, reasons = hps.assess_subclass_of_semantics(
            "working memory", "memory", method,
        )
        assert not ok and "related_to_method" in reasons, method


def test_subclass_of_rejects_prepositional_phrase():
    ok, reasons = hps.assess_subclass_of_semantics(
        "regulation of memory", "memory", "lexical_containment",
    )
    assert not ok and "descriptive_phrase_prepositional" in reasons


def test_subclass_of_rejects_relationship_words():
    ok, reasons = hps.assess_subclass_of_semantics(
        "input to memory", "memory", "lexical_containment",
    )
    assert not ok and "descriptive_phrase_relationship_words" in reasons


def test_subclass_of_rejects_modifier_only_extra():
    ok, reasons = hps.assess_subclass_of_semantics(
        "strong memory", "memory", "lexical_containment",
    )
    assert not ok and "modifier_only_extra" in reasons


def test_subclass_of_rejects_no_containment():
    ok, reasons = hps.assess_subclass_of_semantics(
        "memory", "working memory", "lexical_containment",
    )
    assert not ok and "no_token_containment" in reasons


# ---------------------------------------------------------------- preview pipeline


def test_preview_basic_flow(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory", "episodic memory")
            for child, parent in (
                (ts["working memory"], ts["memory"]),
                (ts["episodic memory"], ts["memory"]),
            ):
                _candidate(session, child, parent)
            await session.flush()
            res = await hps.preview_promotion(session, candidate_version=TEST_VERSION)
            assert res["writes"].startswith("none")
            assert res["recommended_promotion_count"] == 2
            assert res["stages"]["tier_gate"]["included"] == 2
            assert res["stages"]["subclass_of_filter"]["rejected_total"] == 0
            assert res["stages"]["endpoint_checks"]["rejected_total"] == 0
            assert res["stages"]["cycle_checks"]["safe"] == 2
            edges = (await session.execute(select(OntologyTermRelation))).scalars().all()
            assert len(edges) == 0  # preview never writes
    _run(_case())


def test_preview_tier_gate_excludes_low(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory", "episodic memory")
            _candidate(session, ts["working memory"], ts["memory"], tier="high_confidence")
            _candidate(session, ts["episodic memory"], ts["memory"],
                       tier="low_confidence", score=0.2)
            await session.flush()
            res = await hps.preview_promotion(session, candidate_version=TEST_VERSION)
            assert res["recommended_promotion_count"] == 1
            assert res["stages"]["tier_gate"]["excluded"] == 1
    _run(_case())


def test_preview_rejects_non_function_parent(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory")
            region = OntologyTerm(
                term_code=f"ng:region:{TEST_PREFIX}brain",
                canonical_term_en=f"{TEST_PREFIX}brain",
                term_type="region", status="active", created_by="preview_test",
            )
            session.add(region)
            await session.flush()
            # FK requires the parent to exist; validity is the preview's job
            _candidate(session, ts["working memory"], region)
            await session.flush()
            res = await hps.preview_promotion(session, candidate_version=TEST_VERSION)
            assert res["recommended_promotion_count"] == 0
            ep = res["stages"]["endpoint_checks"]["rejected"]
            assert ep.get("parent_non_function") == 1
    _run(_case())


def test_preview_duplicate_excluded(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory")
            session.add(OntologyTermRelation(
                subject_term_id=ts["working memory"].id,
                predicate="subclass_of",
                object_term_id=ts["memory"].id,
                status="proposed",
                source="preview_test",
                provenance_json={},
            ))
            _candidate(session, ts["working memory"], ts["memory"])
            await session.flush()
            res = await hps.preview_promotion(session, candidate_version=TEST_VERSION)
            assert res["recommended_promotion_count"] == 0
            assert res["stages"]["duplicate_checks"]["already_in_relations"] == 1
    _run(_case())


def test_preview_cycle_blocked(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "visual memory", "working memory")
            # Existing (manually-created) 2-cycle: memory ⇄ visual memory
            session.add(OntologyTermRelation(
                subject_term_id=ts["memory"].id, predicate="subclass_of",
                object_term_id=ts["visual memory"].id,
                status="active", source="preview_test", provenance_json={},
            ))
            session.add(OntologyTermRelation(
                subject_term_id=ts["visual memory"].id, predicate="subclass_of",
                object_term_id=ts["memory"].id,
                status="active", source="preview_test", provenance_json={},
            ))
            # Candidate attaches to a cyclic node (memory) → blocked
            _candidate(session, ts["working memory"], ts["memory"])
            await session.flush()
            res = await hps.preview_promotion(session, candidate_version=TEST_VERSION)
            assert res["recommended_promotion_count"] == 0
            assert res["stages"]["cycle_checks"]["cycle_blocked"] == 1
    _run(_case())


def test_preview_merged_resolves_to_canonical(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            # canonical name must stay lexically compatible with the child;
            # flush canonical first so replaced_by_term_id is a real id
            memory_canon = OntologyTerm(
                term_code=f"ng:func:{TEST_PREFIX}memory_canon",
                canonical_term_en=f"{TEST_PREFIX}memory",
                term_type="function", status="active", created_by="preview_test",
            )
            session.add(memory_canon)
            await session.flush()
            memory_merged = OntologyTerm(
                term_code=f"ng:func:{TEST_PREFIX}memory_merged",
                canonical_term_en=f"{TEST_PREFIX}memory",
                term_type="function", status="merged", created_by="preview_test",
                replaced_by_term_id=memory_canon.id,
            )
            working = OntologyTerm(
                term_code=f"ng:func:{TEST_PREFIX}working_memory",
                canonical_term_en=f"{TEST_PREFIX}working memory",
                term_type="function", status="active", created_by="preview_test",
            )
            session.add_all([memory_merged, working])
            await session.flush()
            _candidate(session, working, memory_merged)
            await session.flush()
            res = await hps.preview_promotion(session, candidate_version=TEST_VERSION)
            assert res["recommended_promotion_count"] == 1
            assert res["stages"]["endpoint_checks"]["merged_resolved_to_canonical"] == 1
    _run(_case())


def test_preview_related_to_method_excluded(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory")
            _candidate(session, ts["working memory"], ts["memory"], method="metadata")
            await session.flush()
            res = await hps.preview_promotion(session, candidate_version=TEST_VERSION)
            assert res["recommended_promotion_count"] == 0
            sub = res["stages"]["subclass_of_filter"]
            assert sub["rejected"].get("related_to_method") == 1
    _run(_case())


def test_preview_summary_text():
    res = {
        "candidate_version": "v2",
        "tier": "high_confidence",
        "total_candidates": 10,
        "recommended_promotion_count": 3,
        "distinct_children": 2,
        "stages": {
            "tier_gate": {"included": 10, "excluded": 0},
            "subclass_of_filter": {"rejected_total": 5, "rejected": {"descriptive_phrase_prepositional": 5}},
            "endpoint_checks": {"rejected_total": 1, "merged_resolved_to_canonical": 0},
            "duplicate_checks": {"already_in_relations": 1},
            "cycle_checks": {"safe": 3, "cycle_blocked": 0},
        },
    }
    text = hps.preview_summary_text(res)
    assert "RECOMMENDED PROMOTION: 3 edges (2 distinct children)" in text
    assert "descriptive_phrase_prepositional: 5" in text
