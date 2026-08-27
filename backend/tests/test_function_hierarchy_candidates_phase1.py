"""Function Hierarchy Candidate Generation — Phase 1 enhanced tests.

Tests the category-group-parent enhancement, cycle/self-relation safety,
and the generate_all_candidates batch runner.

No LLM, no writes to ontology_term_relations. All test data uses the
TEST_PREFIX namespace and is cleaned up after each test.
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
    OntologyTermSynonym,
)
from app.services import function_hierarchy_candidate_service as fhcs

TEST_PREFIX = "fhc_phase1_test_"

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
                from sqlalchemy import delete as sa_delete
                await session.execute(
                    sa_delete(OntologyHierarchyCandidate).where(
                        OntologyHierarchyCandidate.child_term_id.in_(ids)
                    )
                )
                await session.execute(
                    sa_delete(OntologyHierarchyCandidate).where(
                        OntologyHierarchyCandidate.parent_term_id.in_(ids)
                    )
                )
                await session.execute(
                    sa_delete(OntologyTermRelation).where(
                        OntologyTermRelation.subject_term_id.in_(ids)
                    )
                )
                await session.execute(
                    sa_delete(OntologyTermRelation).where(
                        OntologyTermRelation.object_term_id.in_(ids)
                    )
                )
                await session.execute(
                    sa_delete(OntologyTermSynonym).where(
                        OntologyTermSynonym.term_id.in_(ids)
                    )
                )
                await session.execute(
                    sa_delete(OntologyTerm).where(OntologyTerm.id.in_(ids))
                )
            await session.commit()

    yield
    _run(_cleanup())


def _term(session, name: str, *, status="active", category=None, domain=None) -> OntologyTerm:
    t = OntologyTerm(
        term_code=f"ng:func:{name.replace(' ', '_')}",
        canonical_term_en=f"{TEST_PREFIX}{name}",
        term_type="function",
        status=status,
        category=category,
        domain=domain,
        created_by="fhc_phase1_test",
    )
    session.add(t)
    return t


async def _make_terms(session, names_status_cat: list[tuple]) -> dict[str, OntologyTerm]:
    """names_status_cat: list of (name, status, category, domain) tuples."""
    out = {}
    for item in names_status_cat:
        name, status, cat, dom = item
        t = _term(session, name, status=status, category=cat, domain=dom)
        out[name] = t
    await session.flush()
    return out


def _idx_with_usage(ts: dict[str, OntologyTerm], usage_data: dict[str, int] | None = None) -> fhcs.TermIndex:
    """Build in-memory index with optional usage counts for each term name."""
    idx = fhcs.TermIndex()
    for _name, t in ts.items():
        idx.terms[t.id] = t
        tokens = fhcs._tokens(t.canonical_term_en)
        idx.token_set[t.id] = tokens
        key = fhcs._norm_key(t.canonical_term_en)
        idx.canonical_key[t.id] = key
        idx.canonical_to_term.setdefault(key, t.id)
        idx.term_status[t.id] = t.status
        for tok in tokens:
            idx.token_terms.setdefault(tok, set()).add(t.id)
    if usage_data:
        for name, count in usage_data.items():
            if name in ts:
                tid = ts[name].id
                idx.usage_subjects[tid] = {uuid.uuid4() for _ in range(count)}
                idx.usage_count[tid] = count
    return idx


# ---- Category group parent tests ----


def test_category_group_creates_hub(db):
    """3+ terms sharing (category, domain) → hub term becomes parent."""
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _make_terms(session, [
                ("cat memory recall",      "active", "memory", "cognition"),
                ("cat memory encoding",    "active", "memory", "cognition"),
                ("cat memory consolidation","active", "memory", "cognition"),
                ("cat memory retrieval",   "active", "memory", "cognition"),
            ])
            idx = await fhcs.load_term_index(session, include_proposed=False)
            cat_parents = fhcs._category_group_parents(idx)
            # At least one non-hub member should get a parent
            hub_ids = set(cat_parents.values())
            assert len(hub_ids) >= 1
            # Members (non-hubs in the group) should be in cat_parents
            members = [tid for tid in ts.values() if tid.id in cat_parents]
            assert len(members) >= 2
    _run(_case())


def test_category_group_skips_small_groups(db):
    """Groups with <3 members produce no category-group parents."""
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _make_terms(session, [
                ("tiny cat alpha", "active", "tiny_cat", "tiny_dom"),
                ("tiny cat beta",  "active", "tiny_cat", "tiny_dom"),
            ])
            idx = await fhcs.load_term_index(session, include_proposed=False)
            cat_parents = fhcs._category_group_parents(idx)
            assert not any(tid in cat_parents for tid in ts.values())
    _run(_case())


def test_category_group_skips_no_category(db):
    """Terms with category=None produce no category-group parents."""
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _make_terms(session, [
                ("no cat x", "active", None, None),
                ("no cat y", "active", None, None),
                ("no cat z", "active", None, None),
            ])
            idx = await fhcs.load_term_index(session, include_proposed=False)
            cat_parents = fhcs._category_group_parents(idx)
            assert not any(tid in cat_parents for tid in ts.values())
    _run(_case())


# ---- Cycle and self-relation safety ----


def test_no_self_candidate(db):
    """A term must never be its own parent candidate."""
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _make_terms(session, [
                ("solo concept xyz", "active", None, None),
            ])
            idx = await fhcs.load_term_index(session, include_proposed=False)
            cands, _ = fhcs.generate_candidates_for_term(
                ts["solo concept xyz"], idx, top_k=10,
            )
            for c in cands:
                assert c.child_term_id != c.parent_term_id, "self-candidate detected"
    _run(_case())


def test_no_cycle_in_candidates(db):
    """Candidate generation must not produce A→B and B→A simultaneously.

    We verify that if term X has term Y as a parent, Y does not have X as a parent.
    This is checked on the raw candidate results (not persisted).
    """
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _make_terms(session, [
                ("cyc alpha memory",  "active", None, None),
                ("cyc alpha working memory", "active", None, None),
                ("cyc beta sensory",  "active", None, None),
                ("cyc beta visual sensory processing", "active", None, None),
            ])
            idx = await fhcs.load_term_index(session, include_proposed=False)
            all_cands: dict[str, set[str]] = {}
            for name, t in ts.items():
                cands, _ = fhcs.generate_candidates_for_term(t, idx, top_k=10)
                all_cands[name] = set()
                for c in cands:
                    all_cands[name].add(str(c.parent_term_id))
                    assert c.child_term_id != c.parent_term_id
            # Verify no mutual pairs
            for n1, parents1 in all_cands.items():
                t1_id = str(ts[n1].id)
                for n2, parents2 in all_cands.items():
                    t2_id = str(ts[n2].id)
                    if t1_id in parents2:
                        assert t2_id not in parents1, (
                            f"cycle detected: {n1}→{n2} and {n2}→{n1}"
                        )
    _run(_case())


def test_persisted_candidates_have_no_self_rows(db):
    """After batch persistence, ontology_hierarchy_candidates has no self-referencing rows."""
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _make_terms(session, [
                ("persist mem", "active", None, None),
                ("persist working mem", "active", None, None),
                ("persist visual", "active", None, None),
                ("persist visual attention", "active", None, None),
            ])
            await fhcs.generate_candidates_batch(
                session, [t.id for t in ts.values()], top_k=5, created_by="fhc_test",
            )
            await session.commit()

            rows = (await session.execute(
                select(OntologyHierarchyCandidate).where(
                    OntologyHierarchyCandidate.created_by == "fhc_test"
                )
            )).scalars().all()
            for r in rows:
                assert r.child_term_id != r.parent_term_id, (
                    f"self-row found: {r.child_term_id}"
                )
    _run(_case())


def test_persisted_candidates_integrity_clean(db):
    """Full integrity audit on persisted candidates must report zero issues."""
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _make_terms(session, [
                ("integ mem", "active", None, None),
                ("integ working mem", "active", None, None),
                ("integ visual", "active", None, None),
                ("integ visual attention", "active", None, None),
                ("integ auditory", "active", None, None),
            ])
            await fhcs.generate_candidates_batch(
                session, [t.id for t in ts.values()], top_k=5, created_by="fhc_test_integ",
            )
            await session.commit()
            r = await fhcs.check_hierarchy_candidate_integrity(session)
            for k in ("duplicate", "self", "orphan_child", "orphan_parent",
                      "invalid_child", "invalid_parent", "merged_child", "merged_parent",
                      "deprecated_child", "deprecated_parent", "canonical_identical",
                      "missing_version", "score_out_of_range", "missing_reasons"):
                assert r[k] == 0, f"{k} = {r[k]}"
    _run(_case())


# ---- generate_all_candidates tests ----


def test_generate_all_candidates_returns_stats(db):
    """generate_all_candidates returns comprehensive statistics dict."""
    async def _case():
        async with AsyncSessionLocal() as session:
            # Create enough terms for category grouping
            await _make_terms(session, [
                ("gac mem recall",       "active", "memory", "cognition"),
                ("gac mem encoding",     "active", "memory", "cognition"),
                ("gac mem consolidation","active", "memory", "cognition"),
                ("gac visual search",    "active", "visual", "perception"),
                ("gac visual attention", "active", "visual", "perception"),
            ])
            result = await fhcs.generate_all_candidates(
                session, top_k=5, created_by="fhc_gac_test",
            )
            assert "total_function_terms" in result
            assert "total_candidates_generated" in result
            assert "term_status_distribution" in result
            assert "term_category_distribution" in result
            assert "term_domain_distribution" in result
            assert "method_distribution" in result
            assert "score_histogram" in result
            assert "integrity" in result
            assert "category_group_hubs" in result
            assert result["total_candidates_generated"] >= 2  # at least lexical hits
            await session.commit()
    _run(_case())


def test_generate_all_candidates_category_group_method(db):
    """When enough terms share a category, category_group method appears."""
    async def _case():
        async with AsyncSessionLocal() as session:
            await _make_terms(session, [
                ("grp mem recall",       "active", "test_grp_cat", "test_grp_dom"),
                ("grp mem encoding",     "active", "test_grp_cat", "test_grp_dom"),
                ("grp mem consolidation","active", "test_grp_cat", "test_grp_dom"),
                ("grp mem retrieval",    "active", "test_grp_cat", "test_grp_dom"),
            ])
            result = await fhcs.generate_all_candidates(
                session, top_k=5, created_by="fhc_grp_test",
            )
            methods = result.get("method_distribution", {})
            assert methods.get("category_group", 0) >= 1, (
                f"Expected category_group method, got: {methods}"
            )
    _run(_case())


# ---- Formal hierarchy untouched ----


def test_ontology_term_relations_untouched(db):
    """Candidate generation must never write to ontology_term_relations."""
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _make_terms(session, [
                ("untouched mem", "active", None, None),
                ("untouched working mem", "active", None, None),
            ])
            await fhcs.generate_candidates_batch(
                session, [t.id for t in ts.values()], top_k=5, created_by="fhc_untouched",
            )
            edges = (await session.execute(select(OntologyTermRelation))).scalars().all()
            assert len(edges) == 0, f"Found {len(edges)} edges in ontology_term_relations"
    _run(_case())
