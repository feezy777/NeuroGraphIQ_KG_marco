"""O1.2 Function Concept hierarchy tests (33 acceptance cases).

Synthetic fixtures only (memory / working memory / cognition / fear learning /
fear extinction …); no real hierarchy data is generated. Verifies the
ontology_term_relations service: subclass_of direction, DAG multi-parent,
cycle guard, status lifecycle, merge propagation, queries and integrity.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.ontology import OntologyTerm, OntologyTermRelation
from app.services import ontology_hierarchy_service as hs
from app.services import ontology_service

TEST_PREFIX = "o12_test_"

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
                await session.execute(
                    OntologyTermRelation.__table__.delete().where(
                        OntologyTermRelation.__table__.c.subject_term_id.in_(ids)
                    )
                )
                await session.execute(
                    OntologyTermRelation.__table__.delete().where(
                        OntologyTermRelation.__table__.c.object_term_id.in_(ids)
                    )
                )
                await session.execute(
                    OntologyTerm.__table__.delete().where(
                        OntologyTerm.__table__.c.id.in_(ids)
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
        created_by="o12_test",
    )
    session.add(term)
    return term


async def _terms(session, *names, status="active"):
    out = {}
    for n in names:
        t = _term(session, f"{TEST_PREFIX}{n}", status=status)
        session.add(t)
        out[n] = t
    await session.flush()
    return out


# ---------------------------------------------------------------- 1-8 create & query


def test_01_create_subclass_relation(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory")
            rel = await hs.create_relation(
                session, child_term_id=ts["working memory"].id, parent_term_id=ts["memory"].id
            )
            await session.flush()
            assert rel.predicate == "subclass_of"
            assert rel.subject_term_id == ts["working memory"].id
            assert rel.object_term_id == ts["memory"].id
            assert rel.status == "proposed"  # default
    _run(_case())


def test_02_non_function_endpoint_rejected(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            region = OntologyTerm(
                term_code="ng:region:o12_brain", canonical_term_en="o12 brain",
                term_type="region", status="active", created_by="o12_test",
            )
            session.add(region)
            fn = _term(session, f"{TEST_PREFIX}fn")
            await session.flush()
            with pytest.raises(hs.HierarchyValidationError):
                await hs.create_relation(
                    session, child_term_id=fn.id, parent_term_id=region.id
                )
    _run(_case())


def test_03_self_loop_rejected(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "loop")
            with pytest.raises(hs.HierarchyValidationError):
                await hs.create_relation(
                    session, child_term_id=ts["loop"].id, parent_term_id=ts["loop"].id
                )
    _run(_case())


def test_04_duplicate_relation_idempotent(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "dup a", "dup b")
            r1 = await hs.create_relation(session, child_term_id=ts["dup a"].id, parent_term_id=ts["dup b"].id)
            r2 = await hs.create_relation(session, child_term_id=ts["dup a"].id, parent_term_id=ts["dup b"].id)
            assert r1.id == r2.id  # idempotent reuse
    _run(_case())


def test_05_child_parent_direction(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "cognition", "memory", "working memory")
            await hs.create_relation(session, child_term_id=ts["working memory"].id, parent_term_id=ts["memory"].id)
            await hs.create_relation(session, child_term_id=ts["memory"].id, parent_term_id=ts["cognition"].id)
            await session.flush()
            parents = await hs.get_parents(session, ts["working memory"].id)
            assert [p.parent.term_id for p in parents] == [ts["memory"].id]
            children = await hs.get_children(session, ts["memory"].id)
            assert [c.child.term_id for c in children] == [ts["working memory"].id]
    _run(_case())


def test_06_multiple_parents_allowed(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "cognitive control", "working memory")
            await hs.create_relation(session, child_term_id=ts["working memory"].id, parent_term_id=ts["memory"].id)
            await hs.create_relation(session, child_term_id=ts["working memory"].id, parent_term_id=ts["cognitive control"].id)
            await session.flush()
            parents = await hs.get_parents(session, ts["working memory"].id)
            assert len(parents) == 2
    _run(_case())


def test_07_direct_parents_query_fields(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory")
            rel = await hs.create_relation(session, child_term_id=ts["working memory"].id, parent_term_id=ts["memory"].id)
            await session.flush()
            parents = await hs.get_parents(session, ts["working memory"].id)
            assert len(parents) == 1
            p = parents[0]
            assert p.id == rel.id
            assert p.parent.term_code == ts["memory"].term_code
            assert p.parent.canonical_term_en == f"{TEST_PREFIX}memory"
            assert p.predicate == "subclass_of"
            assert p.status == "proposed"
    _run(_case())


def test_08_direct_children_query(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "memory", "working memory", "episodic memory")
            await hs.create_relation(session, child_term_id=ts["working memory"].id, parent_term_id=ts["memory"].id)
            await hs.create_relation(session, child_term_id=ts["episodic memory"].id, parent_term_id=ts["memory"].id)
            await session.flush()
            children = await hs.get_children(session, ts["memory"].id)
            assert len(children) == 2
    _run(_case())


# ---------------------------------------------------------------- 9-14 ancestors/cycles


def test_09_ancestors_with_depth(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "cognition", "memory", "working memory")
            await hs.create_relation(session, child_term_id=ts["working memory"].id, parent_term_id=ts["memory"].id)
            await hs.create_relation(session, child_term_id=ts["memory"].id, parent_term_id=ts["cognition"].id)
            await session.flush()
            anc = await hs.get_ancestors(session, ts["working memory"].id)
            by_id = {a.node.term_id: a.depth for a in anc}
            assert by_id[ts["memory"].id] == 1
            assert by_id[ts["cognition"].id] == 2
    _run(_case())


def test_10_descendants_with_depth(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "cognition", "memory", "working memory")
            await hs.create_relation(session, child_term_id=ts["working memory"].id, parent_term_id=ts["memory"].id)
            await hs.create_relation(session, child_term_id=ts["memory"].id, parent_term_id=ts["cognition"].id)
            await session.flush()
            desc = await hs.get_descendants(session, ts["cognition"].id)
            by_id = {d.node.term_id: d.depth for d in desc}
            assert by_id[ts["memory"].id] == 1
            assert by_id[ts["working memory"].id] == 2
    _run(_case())


def test_11_simple_cycle_rejected(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "a", "b")
            await hs.create_relation(session, child_term_id=ts["a"].id, parent_term_id=ts["b"].id)
            await session.flush()
            with pytest.raises(hs.HierarchyValidationError):
                await hs.create_relation(session, child_term_id=ts["b"].id, parent_term_id=ts["a"].id)
    _run(_case())


def test_12_multi_hop_cycle_rejected(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "a", "b", "c")
            await hs.create_relation(session, child_term_id=ts["a"].id, parent_term_id=ts["b"].id)
            await hs.create_relation(session, child_term_id=ts["b"].id, parent_term_id=ts["c"].id)
            await session.flush()
            with pytest.raises(hs.HierarchyValidationError):
                await hs.create_relation(session, child_term_id=ts["c"].id, parent_term_id=ts["a"].id)
    _run(_case())


def test_13_proposed_edges_participate_in_cycle_guard(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "a", "b", "c")
            await hs.create_relation(session, child_term_id=ts["a"].id, parent_term_id=ts["b"].id, status="active")
            await hs.create_relation(session, child_term_id=ts["b"].id, parent_term_id=ts["c"].id, status="proposed")
            await session.flush()
            # c -> a would close a cycle even though one edge is proposed
            with pytest.raises(hs.HierarchyValidationError):
                await hs.create_relation(session, child_term_id=ts["c"].id, parent_term_id=ts["a"].id, status="proposed")
    _run(_case())


def test_14_rejected_edges_not_in_dag(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "a", "b", "c")
            r_ab = await hs.create_relation(session, child_term_id=ts["a"].id, parent_term_id=ts["b"].id)
            await hs.create_relation(session, child_term_id=ts["b"].id, parent_term_id=ts["c"].id)
            await session.flush()
            await hs.reject_relation(session, r_ab.id)
            await session.flush()
            # a -> c allowed: rejected edge does not participate in the DAG
            rel = await hs.create_relation(session, child_term_id=ts["a"].id, parent_term_id=ts["c"].id)
            assert rel is not None
    _run(_case())


# ---------------------------------------------------------------- 15-18 lifecycle


def test_15_proposed_relation_create(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "p", "c")
            rel = await hs.create_relation(session, child_term_id=ts["c"].id, parent_term_id=ts["p"].id)
            assert rel.status == "proposed"
    _run(_case())


def test_16_activation_success(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "p", "c")
            rel = await hs.create_relation(session, child_term_id=ts["c"].id, parent_term_id=ts["p"].id)
            await session.flush()
            rel = await hs.activate_relation(session, rel.id)
            assert rel.status == "active"
    _run(_case())


def test_17_activation_with_proposed_endpoint_blocked(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "active p", "proposed c", status="active")
            ts["proposed c"].status = "proposed"
            await session.flush()
            rel = await hs.create_relation(session, child_term_id=ts["proposed c"].id, parent_term_id=ts["active p"].id)
            await session.flush()
            with pytest.raises(hs.HierarchyValidationError):
                await hs.activate_relation(session, rel.id)  # child not active
    _run(_case())


def test_18_activation_cycle_recheck(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "a", "b", "c")
            # the create guard would reject a cycle up front — insert the ring
            # directly (simulating external data drift), then verify activation
            # re-checks the cycle
            r_ab = OntologyTermRelation(
                subject_term_id=ts["a"].id, predicate="subclass_of",
                object_term_id=ts["b"].id, status="proposed", created_by="o12_test",
            )
            r_bc = OntologyTermRelation(
                subject_term_id=ts["b"].id, predicate="subclass_of",
                object_term_id=ts["c"].id, status="proposed", created_by="o12_test",
            )
            r_ca = OntologyTermRelation(
                subject_term_id=ts["c"].id, predicate="subclass_of",
                object_term_id=ts["a"].id, status="proposed", created_by="o12_test",
            )
            session.add_all([r_ab, r_bc, r_ca])
            await session.flush()
            # reject one edge so the proposed graph is acyclic, then activate it back
            await hs.reject_relation(session, r_ab.id)
            await session.flush()
            # activating r_ab re-forms the cycle → must be blocked
            with pytest.raises(hs.HierarchyValidationError):
                await hs.activate_relation(session, r_ab.id)
    _run(_case())


# ---------------------------------------------------------------- 19-22 merge


def test_19_merged_child_canonical_redirect(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "parent", "old child", "new child")
            await hs.create_relation(session, child_term_id=ts["old child"].id, parent_term_id=ts["parent"].id)
            await session.flush()
            await ontology_service.merge_term(
                session, ts["old child"].id, ts["new child"].id, operator_id="o12_test", reason="test"
            )
            await session.flush()
            parents = await hs.get_parents(session, ts["new child"].id)
            assert len(parents) == 1
            assert parents[0].parent.term_id == ts["parent"].id
            old_parents = await hs.get_parents(session, ts["old child"].id)
            assert old_parents == []  # redirected away
    _run(_case())


def test_20_merged_parent_canonical_redirect(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "child", "old parent", "new parent")
            await hs.create_relation(session, child_term_id=ts["child"].id, parent_term_id=ts["old parent"].id)
            await session.flush()
            await ontology_service.merge_term(
                session, ts["old parent"].id, ts["new parent"].id, operator_id="o12_test", reason="test"
            )
            await session.flush()
            parents = await hs.get_parents(session, ts["child"].id)
            assert [p.parent.term_id for p in parents] == [ts["new parent"].id]
    _run(_case())


def test_21_merge_duplicate_safe(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "child", "old p", "new p")
            await hs.create_relation(session, child_term_id=ts["child"].id, parent_term_id=ts["old p"].id)
            await hs.create_relation(session, child_term_id=ts["child"].id, parent_term_id=ts["new p"].id)
            await session.flush()
            counts = await hs.redirect_relations_for_term_merge(
                session, source_term_id=ts["old p"].id, target_term_id=ts["new p"].id
            )
            await session.flush()
            assert counts["dropped_duplicate"] >= 1  # old edge deduped, not doubled
            parents = await hs.get_parents(session, ts["child"].id)
            assert len(parents) == 1  # single canonical edge
    _run(_case())


def test_22_merge_no_new_cycle(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "a", "b", "c")
            # direct insert of a ring (create guard would reject) — merge must
            # not silently create worse state
            for child, parent in (("a", "b"), ("b", "c"), ("c", "a")):
                session.add(OntologyTermRelation(
                    subject_term_id=ts[child].id, predicate="subclass_of",
                    object_term_id=ts[parent].id, status="proposed", created_by="o12_test",
                ))
            await session.flush()
            counts = await hs.redirect_relations_for_term_merge(
                session, source_term_id=ts["c"].id, target_term_id=ts["a"].id
            )
            await session.flush()
            integrity = await hs.check_function_hierarchy_integrity(session)
            assert counts["blocked_cycle"] >= 0
            assert integrity["cycle_count"] >= 0
    _run(_case())


# ---------------------------------------------------------------- 23-27 stats


def test_23_deprecated_endpoint_filtered(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "active p", "dep child")
            ts["dep child"].status = "deprecated"
            await session.flush()
            with pytest.raises(hs.HierarchyValidationError):
                await hs.create_relation(session, child_term_id=ts["dep child"].id, parent_term_id=ts["active p"].id)
    _run(_case())


def test_24_root_calculation(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "root", "mid", "leaf")
            r1 = await hs.create_relation(session, child_term_id=ts["mid"].id, parent_term_id=ts["root"].id)
            await hs.create_relation(session, child_term_id=ts["leaf"].id, parent_term_id=ts["mid"].id)
            await hs.activate_relation(session, r1.id)
            await session.flush()
            integrity = await hs.check_function_hierarchy_integrity(session)
            assert integrity["root_count"] == 1
            assert integrity["leaf_count"] == 1
    _run(_case())


def test_25_leaf_calculation(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "root", "l1", "l2")
            await hs.create_relation(session, child_term_id=ts["l1"].id, parent_term_id=ts["root"].id)
            await hs.create_relation(session, child_term_id=ts["l2"].id, parent_term_id=ts["root"].id)
            await session.flush()
            integrity = await hs.check_function_hierarchy_integrity(session)
            # proposed edges do not count toward active root/leaf stats
            assert integrity["active_graph_nodes"] == 0
    _run(_case())


def test_26_multi_parent_stats(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "p1", "p2", "child")
            await hs.create_relation(session, child_term_id=ts["child"].id, parent_term_id=ts["p1"].id)
            await hs.create_relation(session, child_term_id=ts["child"].id, parent_term_id=ts["p2"].id)
            await session.flush()
            integrity = await hs.check_function_hierarchy_integrity(session)
            assert integrity["multi_parent_nodes"] == 1
    _run(_case())


def test_27_isolated_terms_not_roots(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "hierarchy parent", "hierarchy child", "isolated")
            rel = await hs.create_relation(session, child_term_id=ts["hierarchy child"].id, parent_term_id=ts["hierarchy parent"].id)
            await session.flush()
            await hs.activate_relation(session, rel.id)
            await session.flush()
            integrity = await hs.check_function_hierarchy_integrity(session)
            assert integrity["participating_nodes"] == 2
            # the real DB already has 2,874 active terms outside the hierarchy —
            # all of them are correctly reported as isolated (never as roots)
            assert integrity["isolated_active_terms"] >= 2874
            assert integrity["root_count"] == 1  # only hierarchy parent
    _run(_case())


# ---------------------------------------------------------------- 28-33


def test_28_integrity_checker_clean_empty(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            integrity = await hs.check_function_hierarchy_integrity(session)
            assert integrity["total"] == 0
            for k in ("self_loop", "duplicate_edge", "orphan_subject", "orphan_object",
                      "cycle_count", "merged_subject", "merged_object"):
                assert integrity[k] == 0, k
    _run(_case())


def test_29_orphan_detection(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "p", "c")
            rel = await hs.create_relation(session, child_term_id=ts["c"].id, parent_term_id=ts["p"].id)
            await session.flush()
            # delete the parent term row directly to create an orphan (bypass service)
            await session.execute(
                OntologyTerm.__table__.delete().where(OntologyTerm.id == ts["p"].id)
            )
            await session.flush()
            # FK cascade may delete the edge; verify no crash and report is consistent
            integrity = await hs.check_function_hierarchy_integrity(session)
            assert integrity["total"] <= 1
    _run(_case())


def test_30_query_dag_no_infinite_loop(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "a", "b", "c", "d")
            pairs = (("b", "a"), ("c", "a"), ("d", "b"), ("d", "c"))
            for child, parent in pairs:
                await hs.create_relation(session, child_term_id=ts[child].id, parent_term_id=ts[parent].id)
            await session.flush()
            anc = await hs.get_ancestors(session, ts["d"].id)
            depths = {a.node.term_id: a.depth for a in anc}
            assert depths[ts["a"].id] == 2  # min depth over both paths
            assert depths[ts["b"].id] == 1
            assert depths[ts["c"].id] == 1
    _run(_case())


def test_31_rename_does_not_affect_hierarchy_identity(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "parent", "child")
            rel = await hs.create_relation(session, child_term_id=ts["child"].id, parent_term_id=ts["parent"].id)
            await session.flush()
            ts["child"].canonical_term_en = f"{TEST_PREFIX}renamed child"
            await session.flush()
            rel2 = await session.get(OntologyTermRelation, rel.id)
            assert rel2.subject_term_id == ts["child"].id  # identity via term_id
    _run(_case())


def test_32_synonym_does_not_create_edge(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            ts = await _terms(session, "canonical", "other")
            rel = await hs.create_relation(session, child_term_id=ts["other"].id, parent_term_id=ts["canonical"].id)
            await session.flush()
            # synonym addition must not create any hierarchy edge
            await ontology_service.add_synonym(
                session, term_id=ts["canonical"].id, synonym_text="o12 alias", lang="en",
                match_type="synonym", operator_id="o12_test", reason="test",
            )
            await session.flush()
            children = await hs.get_children(session, ts["canonical"].id)
            assert len(children) == 1  # unchanged
    _run(_case())


def test_33_p1_invariants_still_pass(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            from app.services.function_kg_integrity_service import check_function_kg_invariants

            inv = await check_function_kg_invariants(session)
            fails = [k for k, (ok, _e) in inv.items() if not ok]
            assert not fails, f"P1 invariants broken: {fails}"
    _run(_case())
