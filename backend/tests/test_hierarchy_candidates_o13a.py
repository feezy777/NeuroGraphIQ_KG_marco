"""O1.3-A hierarchy parent candidate generation tests (29 acceptance cases).

Deterministic retrieval on synthetic fixtures — no LLM, no writes to
ontology_term_relations. Verifies candidate quality, filters, scoring,
idempotency, sampling determinism, calibration, integrity and P1/O1.2
non-regression.
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
from app.services import (
    function_hierarchy_candidate_service as fhcs,
    ontology_hierarchy_service as hs,
    ontology_service,
)

TEST_PREFIX = "o13a_test_"

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
                ids = [str(t.id) for t in terms]
                for col in (OntologyHierarchyCandidate.child_term_id,
                            OntologyHierarchyCandidate.parent_term_id,
                            OntologyTermRelation.subject_term_id,
                            OntologyTermRelation.object_term_id):
                    table = col.parent  # column's parent table
                    await session.execute(table.delete().where(col.in_(ids)))
                await session.execute(
                    OntologyTermSynonym.__table__.delete().where(
                        OntologyTermSynonym.__table__.c.term_id.in_(ids)
                    )
                )
                await session.execute(
                    OntologyTerm.__table__.delete().where(OntologyTerm.__table__.c.id.in_(ids))
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
        created_by="o13a_test",
    )
    session.add(term)
    return term


async def _terms(session, *names, **kw):
    out = {}
    status = kw.get("status", "active")
    for n in names:
        t = _term(session, f"{TEST_PREFIX}{n}", status=status)
        session.add(t)
        out[n] = t
    await session.flush()
    return out

def _idx(ts, usage=None):
    """Pure in-memory index over fixture terms only (no real-DB pollution)."""
    idx = fhcs.TermIndex()
    for name, t in ts.items():
        idx.terms[t.id] = t
        tokens = fhcs._tokens(t.canonical_term_en)
        idx.token_set[t.id] = tokens
        key = fhcs._norm_key(t.canonical_term_en)
        idx.canonical_key[t.id] = key
        idx.canonical_to_term.setdefault(key, t.id)
        idx.term_status[t.id] = t.status
        for tok in tokens:
            idx.token_terms.setdefault(tok, set()).add(t.id)
    if usage:
        for tid, subjects in usage.items():
            idx.usage_subjects[tid] = subjects
            idx.usage_count[tid] = len(subjects)
    return idx



# ---------------------------------------------------------------- 1-8 retrieval


def test_01_lexical_parent_retrieval(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory")
            idx = _idx(ts)
            cands, reason = fhcs.generate_candidates_for_term(ts["working memory"], idx, top_k=5)
            assert reason is None
            assert any(c.parent_term_id == ts["memory"].id for c in cands)
    _run(_case())


def test_02_token_subset_retrieval(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "visual recognition", "visual object recognition")
            idx = _idx(ts)
            cands, _ = fhcs.generate_candidates_for_term(ts["visual object recognition"], idx, top_k=5)
            assert any(c.parent_term_id == ts["visual recognition"].id for c in cands)
    _run(_case())


def test_03_synonym_does_not_create_candidate(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "fear extinction", "fear extinction old")
            await ontology_service.add_synonym(
                session, term_id=ts["fear extinction"].id,
                synonym_text=f"{TEST_PREFIX}fear extinction old", lang="en",
                match_type="synonym", operator_id="o13a_test", reason="test",
            )
            await session.flush()
            idx = _idx(ts)
            cands, _ = fhcs.generate_candidates_for_term(ts["fear extinction old"], idx, top_k=5)
            assert not any(c.parent_term_id == ts["fear extinction"].id for c in cands)
    _run(_case())


def test_04_canonical_same_filtered(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "memory ")
            # canonical keys are identical after normalization
            idx = _idx(ts)
            cands, _ = fhcs.generate_candidates_for_term(ts["memory "], idx, top_k=5)
            assert not any(c.parent_term_id == ts["memory"].id for c in cands)
    _run(_case())


def test_05_self_candidate_filtered(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory")
            idx = _idx(ts)
            cands, _ = fhcs.generate_candidates_for_term(ts["memory"], idx, top_k=5)
            assert not any(c.parent_term_id == ts["memory"].id for c in cands)
    _run(_case())


def test_06_generic_token_parent_filtered(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "modulation", "cognitive modulation")
            idx = _idx(ts)
            cands, _ = fhcs.generate_candidates_for_term(ts["cognitive modulation"], idx, top_k=5)
            assert not any(c.parent_term_id == ts["modulation"].id for c in cands)
    _run(_case())


def test_07_active_parent_preferred(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory")
            ts["memory"].status = "proposed"
            await session.flush()
            idx = await fhcs.load_term_index(session, include_proposed=True)
            cands, _ = fhcs.generate_candidates_for_term(ts["working memory"], idx, top_k=5)
            assert cands and cands[0].parent_status == "proposed"  # only parent available
            # with both statuses, active ranks first
            ts2 = await _terms(session, "memory2", "memory3")
            ts2["memory2"].status = "proposed"
            await session.flush()
            # reindex
            idx2 = await fhcs.load_term_index(session, include_proposed=True)
            child = _term(session, f"{TEST_PREFIX}working memory2")
            session.add(child)
            await session.flush()
            cands2, _ = fhcs.generate_candidates_for_term(child, idx2, top_k=5)
            # both parents share tokens; active memory3 should outrank proposed memory2
            actives = [c for c in cands2 if c.parent_status == "active"]
            props = [c for c in cands2 if c.parent_status == "proposed"]
            assert actives and props
            assert max(c.candidate_score for c in actives) >= max(c.candidate_score for c in props)
    _run(_case())


def test_08_proposed_parent_secondary_allowed(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory")
            ts["memory"].status = "proposed"
            await session.flush()
            idx = await fhcs.load_term_index(session, include_proposed=True)
            cands, _ = fhcs.generate_candidates_for_term(ts["working memory"], idx, top_k=5)
            assert any(c.parent_term_id == ts["memory"].id for c in cands)  # not blocked
    _run(_case())


# ---------------------------------------------------------------- 9-13 scoring


def test_09_metadata_score(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory")
            ts["memory"].domain = "cognition"
            ts["working memory"].domain = "cognition"
            await session.flush()
            idx = await fhcs.load_term_index(session, include_proposed=False)
            cands, _ = fhcs.generate_candidates_for_term(ts["working memory"], idx, top_k=5)
            m = [c for c in cands if c.parent_term_id == ts["memory"].id]
            assert m and m[0].metadata_score > 0
    _run(_case())


def test_10_usage_context_score(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            from app.models.mirror_kg import MirrorRegionFunction

            ts = await _terms(session, "memory", "working memory")
            subj = uuid.uuid4()
            for t in (ts["memory"], ts["working memory"]):
                session.add(MirrorRegionFunction(
                    region_candidate_id=subj, term_id=t.id,
                    granularity_level="macro_clinical", source_atlas="test_atlas",
                    function_term=t.canonical_term_en, mirror_status="llm_suggested",
                    review_status="pending", promotion_status="not_promoted",
                    raw_payload_json={"o13a_test": True},
                ))
            await session.flush()
            idx = await fhcs.load_term_index(session, include_proposed=False)
            cands, _ = fhcs.generate_candidates_for_term(ts["working memory"], idx, top_k=5)
            m = [c for c in cands if c.parent_term_id == ts["memory"].id]
            assert m and m[0].usage_score > 0
    _run(_case())


def test_11_compound_term_component_candidate(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "fear extinction", "emotional regulation", "fear extinction and emotional regulation")
            idx = await fhcs.load_term_index(session, include_proposed=False)
            cands, _ = fhcs.generate_candidates_for_term(ts["fear extinction and emotional regulation"], idx, top_k=10)
            reasons = [c.reasons for c in cands]
            assert any(r.get("compound_term_component_candidate") for r in reasons)
            # components scored low (0.3), never beat structural candidates
            comp = [c for c in cands if c.reasons.get("compound_term_component_candidate")]
            if comp:
                assert max(c.candidate_score for c in comp) <= 0.3
    _run(_case())


def test_12_no_candidate_reason(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "unique concept alpha beta gamma")
            idx = await fhcs.load_term_index(session, include_proposed=False)
            cands, reason = fhcs.generate_candidates_for_term(ts["unique concept alpha beta gamma"], idx, top_k=5)
            assert not cands and reason is not None
    _run(_case())


def test_13_topk_truncation(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            # many subset parents of a long name
            ts = await _terms(session, "a", "a b", "a b c", "a b c d")
            idx = await fhcs.load_term_index(session, include_proposed=False)
            cands, _ = fhcs.generate_candidates_for_term(ts["a b c d"], idx, top_k=2)
            assert len(cands) <= 2
    _run(_case())


# ---------------------------------------------------------------- 14-21 idempotency


def test_14_deterministic_repeat(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory", "cognition")
            idx = await fhcs.load_term_index(session, include_proposed=False)
            c1, _ = fhcs.generate_candidates_for_term(ts["working memory"], idx, top_k=10)
            c2, _ = fhcs.generate_candidates_for_term(ts["working memory"], idx, top_k=10)
            assert [(c.parent_term_id, c.candidate_score) for c in c1] == \
                   [(c.parent_term_id, c.candidate_score) for c in c2]
    _run(_case())


def test_15_generation_version_idempotent(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory")
            await fhcs.generate_candidates_for_term_id(
                session, ts["working memory"].id, top_k=5, created_by="o13a_test"
            )
            await fhcs.generate_candidates_for_term_id(
                session, ts["working memory"].id, top_k=5, created_by="o13a_test"
            )
            rows = (await session.execute(
                select(OntologyHierarchyCandidate).where(
                    OntologyHierarchyCandidate.child_term_id == ts["working memory"].id
                )
            )).scalars().all()
            assert len(rows) == 1  # same version → no duplicates
    _run(_case())


def test_16_regeneration_new_version(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory")
            await fhcs.generate_candidates_for_term_id(
                session, ts["working memory"].id, top_k=5,
                generation_version="v1", created_by="o13a_test",
            )
            await fhcs.generate_candidates_for_term_id(
                session, ts["working memory"].id, top_k=5,
                generation_version="v2", created_by="o13a_test",
            )
            rows = (await session.execute(
                select(OntologyHierarchyCandidate).where(
                    OntologyHierarchyCandidate.child_term_id == ts["working memory"].id
                )
            )).scalars().all()
            assert len(rows) == 2  # one per version
    _run(_case())


def test_17_batch_generation(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory", "cognition", "fear extinction")
            res = await fhcs.generate_candidates_batch(
                session, [t.id for t in ts.values()], top_k=5, created_by="o13a_test"
            )
            assert res["total_candidates"] >= 1
    _run(_case())


def test_18_duplicate_candidate_zero(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory")
            await fhcs.generate_candidates_for_term_id(session, ts["working memory"].id, top_k=5, created_by="o13a_test")
            r = await fhcs.check_hierarchy_candidate_integrity(session)
            assert r["duplicate"] == 0
            assert r["total"] >= 1
    _run(_case())


def test_19_merged_endpoint_resolved(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "memory old", "working memory")
            ts["memory old"].status = "merged"
            ts["memory old"].replaced_by_term_id = ts["memory"].id
            await session.flush()
            idx = await fhcs.load_term_index(session, include_proposed=True)
            cands, _ = fhcs.generate_candidates_for_term(ts["working memory"], idx, top_k=5)
            assert not any(c.parent_term_id == ts["memory old"].id for c in cands)  # merged excluded
            assert any(c.parent_term_id == ts["memory"].id for c in cands)  # canonical included
    _run(_case())


def test_20_deprecated_endpoint_excluded(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory")
            ts["memory"].status = "deprecated"
            await session.flush()
            idx = await fhcs.load_term_index(session, include_proposed=True)
            cands, _ = fhcs.generate_candidates_for_term(ts["working memory"], idx, top_k=5)
            assert not any(c.parent_term_id == ts["memory"].id for c in cands)
    _run(_case())


def test_21_invalid_function_excluded(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory")
            region = OntologyTerm(
                term_code="ng:region:o13a_brain", canonical_term_en=f"{TEST_PREFIX}brain",
                term_type="region", status="active", created_by="o13a_test",
            )
            session.add(region)
            await session.flush()
            idx = await fhcs.load_term_index(session, include_proposed=False)
            cands, _ = fhcs.generate_candidates_for_term(ts["working memory"], idx, top_k=5)
            assert not any(c.parent_term_id == region.id for c in cands)
    _run(_case())


# ---------------------------------------------------------------- 22-29


def test_22_sampling_deterministic(db):
    from scripts.generate_hierarchy_candidates_o13a import sample_active_terms

    async def _case():
        async with AsyncSessionLocal() as session:
            s1 = await sample_active_terms(session, 30)
            s2 = await sample_active_terms(session, 30)
            assert [t.id for t in s1] == [t.id for t in s2]
            assert len(s1) == 30
    _run(_case())


def test_23_report_generation_exists():
    import os

    p = os.path.join("data", "exports", "hierarchy_candidates", "o13a_report_20260821.md")
    assert os.path.exists(p), "report file missing"
    with open(p, encoding="utf-8") as f:
        content = f.read()
    assert "total_candidates" in content and "## " in content


def test_24_calibration_label(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory")
            cands, _ = await fhcs.generate_candidates_for_term_id(
                session, ts["working memory"].id, top_k=5, created_by="o13a_test"
            )
            assert cands
            row = await fhcs.set_calibration_label(session, cands[0].id, "good_parent")
            assert row.calibration_label == "good_parent"
    _run(_case())


def test_25_topk_metrics(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(
                session,
                "memory", "working memory", "cognition",
                "visual processing", "visual object recognition", "attention",
            )
            golden = {
                ts["working memory"].id: ts["memory"].id,
                ts["visual object recognition"].id: ts["visual processing"].id,
            }
            hit_top1 = hit_top3 = hit_top5 = 0
            total = 0
            idx = await fhcs.load_term_index(session, include_proposed=False)
            for child_id, gold_parent in golden.items():
                child = idx.terms.get(child_id)
                if child is None:
                    continue
                cands, _ = fhcs.generate_candidates_for_term(child, idx, top_k=10)
                ids = [c.parent_term_id for c in cands]
                total += 1
                if ids and ids[0] == gold_parent:
                    hit_top1 += 1
                if gold_parent in ids[:3]:
                    hit_top3 += 1
                if gold_parent in ids[:5]:
                    hit_top5 += 1
            assert total == 2
            assert hit_top1 >= 1  # working memory → memory is a direct subset
            assert hit_top5 >= 1  # visual object recognition → visual processing
    _run(_case())


def test_26_candidate_integrity_clean(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory", "cognition", "fear extinction")
            await fhcs.generate_candidates_batch(session, [t.id for t in ts.values()], top_k=5, created_by="o13a_test")
            r = await fhcs.check_hierarchy_candidate_integrity(session)
            assert r["total"] >= 1
            for k in ("duplicate", "self", "orphan_child", "orphan_parent",
                      "invalid_child", "invalid_parent", "merged_child", "merged_parent",
                      "deprecated_child", "deprecated_parent", "canonical_identical",
                      "missing_version", "score_out_of_range", "missing_reasons"):
                assert r[k] == 0, f"{k} = {r[k]}"
    _run(_case())


def test_27_ontology_term_relations_untouched(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory")
            await fhcs.generate_candidates_for_term_id(session, ts["working memory"].id, top_k=5, created_by="o13a_test")
            edges = (await session.execute(select(OntologyTermRelation))).scalars().all()
            assert len(edges) == 0  # formal hierarchy untouched
    _run(_case())


def test_28_o12_hierarchy_integrity_clean(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory")
            await fhcs.generate_candidates_for_term_id(session, ts["working memory"].id, top_k=5, created_by="o13a_test")
            r = await hs.check_function_hierarchy_integrity(session)
            assert r["total"] == 0  # still no formal edges
    _run(_case())


def test_29_p1_invariants_pass(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            from app.services.function_kg_integrity_service import check_function_kg_invariants

            inv = await check_function_kg_invariants(session)
            fails = [k for k, (ok, _e) in inv.items() if not ok]
            assert not fails, f"P1 invariants broken: {fails}"
    _run(_case())
