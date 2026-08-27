"""Hierarchy Candidate Quality Filter tests.

Tests deterministic quality scoring and triage of hierarchy candidates.
No writes to ontology_term_relations.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import delete as sa_delete
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.ontology import (
    OntologyHierarchyCandidate,
    OntologyTerm,
    OntologyTermRelation,
    OntologyTermSynonym,
)
from app.services import hierarchy_candidate_quality_filter as qf

TEST_PREFIX = "hqf_test_"

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
                    OntologyTerm.canonical_term_en.like(f"{TEST_PREFIX}%")
                )
            )).scalars().all()
            if terms:
                ids = [t.id for t in terms]
                await session.execute(sa_delete(OntologyHierarchyCandidate).where(
                    OntologyHierarchyCandidate.child_term_id.in_(ids)
                ))
                await session.execute(sa_delete(OntologyHierarchyCandidate).where(
                    OntologyHierarchyCandidate.parent_term_id.in_(ids)
                ))
                await session.execute(sa_delete(OntologyTermSynonym).where(
                    OntologyTermSynonym.term_id.in_(ids)
                ))
                await session.execute(sa_delete(OntologyTerm).where(
                    OntologyTerm.id.in_(ids)
                ))
            await session.commit()
    yield
    _run(_cleanup())


# ── Unit tests (pure function, no DB) ──


def test_good_isa_high_score():
    """Clean IS-A: 'working memory' → 'memory' should score high."""
    a = qf.assess_candidate("working memory", "memory", 1.5, "lexical_containment")
    assert a.quality_score >= 0.7
    assert a.quality_tier == "high_confidence"


def test_good_isa_with_category():
    """'episodic memory retrieval' → 'memory retrieval' is good."""
    a = qf.assess_candidate("episodic memory retrieval", "memory retrieval", 1.5, "lexical_containment")
    assert a.quality_tier in ("high_confidence", "review")


def test_modality_substitution_rejected():
    """Cross-modal substitution (somatosensory↔visual) is NOT IS-A."""
    a = qf.assess_candidate(
        "somatosensory to auditory projection",
        "visual to auditory projection",
        2.0, "lexical_containment",
    )
    # Both modality_substitution AND same_count_no_subset should fire
    assert "modality_substitution" in a.quality_reasons or "same_count_no_subset" in a.quality_reasons
    assert a.quality_score < 1.0
    assert a.quality_tier in ("low_confidence", "rejected")


def test_same_token_count_sibling_rejected():
    """Same-length terms with no subset are siblings, not hierarchy."""
    # "sensory motor coordination" vs "sensory motor integration"
    # Same concept class, different specialization — NOT IS-A
    a = qf.assess_candidate(
        "sensory motor coordination",
        "sensory motor integration",
        1.5, "lexical_containment",
    )
    # Same size, no subset → caught by same_count_no_subset
    assert "same_count_no_subset" in a.quality_reasons
    assert a.quality_score < 1.0


def test_anatomical_detail_only_penalized():
    """Adding only an anatomical location prefix is not IS-A."""
    a = qf.assess_candidate(
        "lateral dmn output",
        "dmn output",
        1.83, "lexical_containment",
    )
    assert "anatomical_detail_only" in a.quality_reasons
    assert a.quality_score < 0.5


def test_relationship_not_isa_penalized():
    """All extra tokens being relationship indicators is not IS-A."""
    # "input to hippocampus" vs "to hippocampus" — "input" is purely relational
    a = qf.assess_candidate(
        "input relay to hippocampus",
        "relay to hippocampus",
        1.0, "lexical_containment",
    )
    # "input" is a relationship indicator → penalized
    assert "relationship_not_isa" in a.quality_reasons
    assert a.quality_score < 0.5


def test_compound_component_low():
    """Compound component method gets severe penalty."""
    a = qf.assess_candidate(
        "memory and emotion",
        "emotion",
        0.3, "compound_component",
    )
    assert "compound_component_method" in a.quality_reasons
    assert a.quality_score < 0.1
    assert a.quality_tier == "low_confidence"


def test_very_long_descriptive_penalized():
    """Very long descriptive phrases (>6 tokens each) are suspicious."""
    a = qf.assess_candidate(
        "somatosensory modulation of cortical amygdala lateral zone layer 2",
        "modulation of cortical amygdala lateral zone layer 2",
        1.75, "lexical_containment",
    )
    assert "very_long_descriptive" in a.quality_reasons
    assert a.quality_score < 1.5


def test_clear_generalization_bonus():
    """Short parent with 2+ extra child tokens gets bonus."""
    a = qf.assess_candidate(
        "episodic memory consolidation process",
        "memory",
        1.0, "lexical_containment",
    )
    assert a.quality_score >= 0.7
    assert a.quality_tier in ("high_confidence", "review")


def test_empty_name_handled():
    """Empty term names don't crash."""
    a = qf.assess_candidate("", "memory", 1.0, "lexical_containment")
    assert a.quality_tier in ("low_confidence", "rejected")


# ── DB integration tests ──


def _term(session, name, status="active"):
    t = OntologyTerm(
        term_code=f"ng:func:{TEST_PREFIX}{name.replace(' ', '_')}",
        canonical_term_en=f"{TEST_PREFIX}{name}",
        term_type="function",
        status=status,
        created_by="hqf_test",
    )
    session.add(t)
    return t


def _candidate(session, child, parent, score, method="lexical_containment", version="hqf_test_v1"):
    c = OntologyHierarchyCandidate(
        child_term_id=child.id,
        parent_term_id=parent.id,
        candidate_score=score,
        generation_method=method,
        generation_reasons_json={},
        status="pending",
        generation_version=version,
        created_by="hqf_test",
    )
    session.add(c)
    return c


def test_run_quality_filter_updates_reasons_json(db):
    """run_quality_filter writes quality_tier/score/reasons into generation_reasons_json."""
    async def _case():
        async with AsyncSessionLocal() as session:
            child = _term(session, "working memory")
            parent = _term(session, "memory")
            await session.flush()
            _candidate(session, child, parent, 1.5, version="hqf_test_v1")
            await session.flush()

            stats = await qf.run_quality_filter(session, generation_version="hqf_test_v1")
            await session.commit()

            assert stats["total"] == 1
            assert stats["by_tier"]["high_confidence"] == 1 or stats["by_tier"]["review"] == 1

            row = (await session.execute(
                select(OntologyHierarchyCandidate).where(
                    OntologyHierarchyCandidate.generation_version == "hqf_test_v1"
                )
            )).scalar_one()
            rj = row.generation_reasons_json
            assert "quality_tier" in rj
            assert "quality_score" in rj
            assert "quality_reasons" in rj
    _run(_case())


def test_run_quality_filter_rejects_modality_substitution(db):
    """Modality substitution candidates get low score."""
    async def _case():
        async with AsyncSessionLocal() as session:
            child = _term(session, "somatosensory to auditory projection")
            parent = _term(session, "visual to auditory projection")
            await session.flush()
            _candidate(session, child, parent, 2.0, version="hqf_test_v2")
            await session.flush()

            stats = await qf.run_quality_filter(session, generation_version="hqf_test_v2")
            await session.commit()

            assert stats["by_tier"]["low_confidence"] >= 1
    _run(_case())


def test_filter_stats_returns_summary(db):
    """filter_stats returns tier distribution and averages."""
    async def _case():
        async with AsyncSessionLocal() as session:
            c1 = _term(session, "working memory")
            p1 = _term(session, "memory")
            # compound_component method gets severe penalty → low_confidence
            c2 = _term(session, "memory and emotion")
            p2 = _term(session, "emotion")
            await session.flush()
            _candidate(session, c1, p1, 1.5, version="hqf_test_v3")
            _candidate(session, c2, p2, 0.3, method="compound_component", version="hqf_test_v3")
            await session.flush()

            await qf.run_quality_filter(session, generation_version="hqf_test_v3")
            await session.commit()

            stats = await qf.filter_stats(session, generation_version="hqf_test_v3")
            assert stats["total"] == 2
            assert "high_confidence" in stats["by_tier"] or "review" in stats["by_tier"]
            assert "low_confidence" in stats["by_tier"]
    _run(_case())


def test_list_filtered_candidates_by_tier(db):
    """list_filtered_candidates correctly filters by tier."""
    async def _case():
        async with AsyncSessionLocal() as session:
            c1 = _term(session, "episodic memory")
            p1 = _term(session, "memory")
            # compound_component → low_confidence
            c2 = _term(session, "memory and navigation")
            p2 = _term(session, "navigation")
            await session.flush()
            _candidate(session, c1, p1, 1.5, version="hqf_test_v4")
            _candidate(session, c2, p2, 0.3, method="compound_component", version="hqf_test_v4")
            await session.flush()

            await qf.run_quality_filter(session, generation_version="hqf_test_v4")
            await session.commit()

            high, total = await qf.list_filtered_candidates(
                session, tier="high_confidence", generation_version="hqf_test_v4",
            )
            assert total >= 1
            for item in high:
                assert item["quality_tier"] == "high_confidence"

            low, total_low = await qf.list_filtered_candidates(
                session, tier="low_confidence", generation_version="hqf_test_v4",
            )
            assert total_low >= 1
    _run(_case())


def test_ontology_term_relations_untouched(db):
    """Quality filter must not touch ontology_term_relations."""
    async def _case():
        async with AsyncSessionLocal() as session:
            c = _term(session, "working memory")
            p = _term(session, "memory")
            await session.flush()
            _candidate(session, c, p, 1.5, version="hqf_test_v5")
            await session.flush()

            await qf.run_quality_filter(session, generation_version="hqf_test_v5")
            await session.commit()

            edges = (await session.execute(select(OntologyTermRelation))).scalars().all()
            assert len(edges) == 0
    _run(_case())
