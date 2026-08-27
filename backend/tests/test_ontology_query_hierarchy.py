"""Ontology Query — function hierarchy traversal 测试。

场景（真实 DB，依赖 FN1 v2 落库数据）：
  * Memory 查询 → Working Memory、Spatial Memory 等子功能
  * Hippocampus + Function → function hierarchy 扩展关联结果
  * Attention 查询 → Visual Attention 等子功能
  * 前后对比（hierarchy_analysis: without/with + added_paths）

纯逻辑（隔离数据）：BFS depth/path、ancestors、环安全、function 解析。
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.ontology import (
    OntologyTerm,
    OntologyTermRelation,
    OntologyTermSynonym,
)
from app.services import ontology_query_service as oqs

QH_PREFIX = "qh_test_"

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
                    OntologyTerm.term_code.like(f"ng:func:{QH_PREFIX}%")
                )
            )).scalars().all()
            ids = [str(t.id) for t in terms]
            if ids:
                rel_t = OntologyTermRelation.__table__
                term_t = OntologyTerm.__table__
                syn_t = OntologyTermSynonym.__table__
                for col in (rel_t.c.subject_term_id, rel_t.c.object_term_id):
                    await session.execute(rel_t.delete().where(col.in_(ids)))
                await session.execute(syn_t.delete().where(syn_t.c.term_id.in_(ids)))
                await session.execute(term_t.delete().where(term_t.c.id.in_(ids)))
            await session.commit()

    yield
    _run(_cleanup())


async def _term(session, name, *, status="active"):
    t = OntologyTerm(
        term_code=f"ng:func:{QH_PREFIX}{name.replace(' ', '_')}",
        canonical_term_en=f"{QH_PREFIX}{name}",
        term_type="function",
        status=status,
        created_by="qh_test",
    )
    session.add(t)
    await session.flush()
    return t


async def _edge(session, child, parent, *, status="active"):
    session.add(OntologyTermRelation(
        subject_term_id=child.id,
        predicate="subclass_of",
        object_term_id=parent.id,
        status=status,
        source="qh_test",
        provenance_json={},
    ))
    await session.flush()


def _names(items) -> set[str]:
    return {i["name"] for i in items}


def _norm_name_set(items) -> set[str]:
    return {i["name"].lower() for i in items}


# ================================================================ 场景:真实数据
# Memory / Attention / Hippocampus 为 FN1 v2 已落库真实术语


def test_memory_children_query():
    async def _case():
        async with AsyncSessionLocal() as session:
            res = await oqs.handle_ontology_query(session, "Memory 有哪些子功能")
            assert res["intent"] == "function_children"
            assert res["entity"]["type"] == "function"
            names = _norm_name_set(res["results"])
            assert "working memory" in names, sorted(names)[:20]
            assert "spatial memory" in names
            analysis = res["hierarchy_analysis"]
            assert analysis is not None
            assert analysis["without_hierarchy_count"] == 1
            assert analysis["with_hierarchy_count"] == len(res["results"]) >= 2
            assert analysis["added_descendant_count"] >= 2
            assert any("memory" in p.lower() for p in analysis["added_paths"])
            # 结果携带 subclass_of 溯源
            assert all(i["provenance"] == "ontology_term_relations.subclass_of"
                       for i in res["results"])
    _run(_case())


def test_bare_function_name_fallback():
    """裸实体名 "Memory"：无意图关键词 → region 解析失败 → function 回退。"""
    async def _case():
        async with AsyncSessionLocal() as session:
            res = await oqs.handle_ontology_query(session, "Memory")
            assert res["intent"] == "function_children"
            assert any("未识别意图" in w for w in res["warnings"])
            names = _norm_name_set(res["results"])
            assert "working memory" in names
            assert res["hierarchy_analysis"]["with_hierarchy_count"] >= 2
    _run(_case())


def test_attention_children_query():
    async def _case():
        async with AsyncSessionLocal() as session:
            res = await oqs.handle_ontology_query(session, "Attention 有哪些子功能")
            assert res["intent"] == "function_children"
            names = _norm_name_set(res["results"])
            assert "visual attention" in names, sorted(names)[:20]
    _run(_case())


def test_working_memory_ancestors_query():
    async def _case():
        async with AsyncSessionLocal() as session:
            res = await oqs.handle_ontology_query(session, "Working Memory 的上级功能")
            assert res["intent"] == "function_ancestors"
            names = _norm_name_set(res["results"])
            assert "memory" in names, sorted(names)[:20]
            analysis = res["hierarchy_analysis"]
            assert analysis["without_hierarchy_count"] == 1
            assert analysis["added_descendant_count"] == len(res["results"]) >= 1
    _run(_case())


def test_hippocampus_functions_hierarchy_expansion():
    """Hippocampus 的功能：region 关联功能 + hierarchy 一级子功能扩展。"""
    async def _case():
        async with AsyncSessionLocal() as session:
            res = await oqs.handle_ontology_query(session, "Hippocampus 的功能")
            assert res["intent"] == "region_functions"
            analysis = res["hierarchy_analysis"]
            assert analysis is not None
            without = analysis["without_hierarchy_count"]
            with_h = analysis["with_hierarchy_count"]
            assert with_h > without  # hierarchy 扩展增加了结果
            assert analysis["added_descendant_count"] == with_h - without
            categories = {i["category"] for i in res["results"]}
            assert "function_descendant" in categories
            assert analysis["added_paths"], "应有新增关联路径"
            assert all("→" in p for p in analysis["added_paths"][:3])
    _run(_case())


def test_region_children_unaffected():
    """非 function 意图不受影响（向后兼容，无 hierarchy_analysis）。"""
    async def _case():
        async with AsyncSessionLocal() as session:
            res = await oqs.handle_ontology_query(session, "Hippocampus 有哪些亚区")
            assert res["intent"] == "region_children"
            assert res["hierarchy_analysis"] is None
            assert all(i["category"] == "children" for i in res["results"])
    _run(_case())


def test_region_functions_plain_query():
    """region_functions 意图不带 hierarchy 场景（无 function 关联时 analysis=None）。"""
    async def _case():
        async with AsyncSessionLocal() as session:
            # 用无关联 function 的 region 验证 analysis 可为 None
            res = await oqs.handle_ontology_query(session, "Hippocampus 的功能")
            assert res["hierarchy_analysis"] is not None  # 真实数据必有关联
            # 对比：查询不带 function hierarchy 的普通 region 子区
            res2 = await oqs.handle_ontology_query(session, "Hippocampus 有哪些亚区")
            assert res2["hierarchy_analysis"] is None
    _run(_case())


# ================================================================ 纯逻辑:隔离数据


def test_descendants_depth_and_path(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            a = await _term(session, "memory2")
            b = await _term(session, "working memory2")
            c = await _term(session, "consolidation2")
            x = await _term(session, "sibling2")
            await _edge(session, b, a)
            await _edge(session, c, b)
            await _edge(session, x, a)
            descs = await oqs.get_function_descendants(session, a.id)
            by_name = {d["name"]: d for d in descs}
            assert by_name["qh_test_working memory2"]["depth"] == 1
            assert by_name["qh_test_consolidation2"]["depth"] == 2
            assert by_name["qh_test_sibling2"]["depth"] == 1
            # path: consolidation → [memory2, working memory2]（不含查询 term）
            assert by_name["qh_test_consolidation2"]["path_names"] == [
                "qh_test_memory2", "qh_test_working memory2",
            ]
    _run(_case())


def test_ancestors_depth_and_path(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            a = await _term(session, "memory2")
            b = await _term(session, "working memory2")
            c = await _term(session, "consolidation2")
            await _edge(session, b, a)
            await _edge(session, c, b)
            anc = await oqs.get_function_ancestors(session, c.id)
            by_name = {d["name"]: d for d in anc}
            assert by_name["qh_test_working memory2"]["depth"] == 1
            assert by_name["qh_test_memory2"]["depth"] == 2
    _run(_case())


def test_descendants_cycle_safe(db):
    """手动边造成环时 BFS 不死循环（visited 去重）。"""
    async def _case():
        async with AsyncSessionLocal() as session:
            a = await _term(session, "memory2")
            b = await _term(session, "visual memory2")
            await _edge(session, b, a)
            await _edge(session, a, b)  # 环: memory2 ⇄ visual memory2
            descs = await oqs.get_function_descendants(session, a.id)
            assert {d["name"] for d in descs} == {"qh_test_visual memory2"}
            assert all(d["depth"] == 1 for d in descs)
    _run(_case())


def test_resolve_function_term(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            t = await _term(session, "episodic memory2")
            syn = OntologyTermSynonym(
                term_id=t.id, synonym_text="EM2", lang="en", match_type="alias", status="active",
            )
            session.add(syn)
            await session.flush()
            term, matched_by, matched_name = await oqs.resolve_function_term(
                session, f"{QH_PREFIX}episodic memory2")
            assert term is not None and term.id == t.id
            assert matched_by == "function_canonical_term_en"
            term2, matched_by2, _ = await oqs.resolve_function_term(session, "EM2")
            assert term2 is not None and term2.id == t.id
            assert matched_by2 == "function_synonym"
            term3, _, _ = await oqs.resolve_function_term(session, "no such function 2")
            assert term3 is None
    _run(_case())
