"""Ontology Query Phase 1 — POST /api/ontology-query 测试。

规格要求（5 个必须测试）：
1. 「海马有哪些亚区」→ region_children → CA1/CA2/CA3/DG/Subiculum
2. 「连接海马的脑区有哪些」→ region_connections
3. 「海马参与哪些回路」→ region_circuits
4. 「海马有哪些细胞和分子」→ region_multiscale
5. 未知问题 → unresolved，不报错

确定性策略：自建 `oq_test_` 前缀数据（实体名用独特名，避免与真实
canonical 名称双匹配），断言路径/意图/结果结构与规格行为等价；
另加真实数据条件测试（开发库有「海马」时直接验证规格问题原文，
无数据则 skip）。解析层级覆盖：cn / en / alias / synonym。
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.database import AsyncSessionLocal
from app.main import app
from app.models.candidate import CandidateBrainRegion
from app.models.canonical_circuit import (
    CanonicalCircuit,
    CanonicalCircuitFunction,
    CanonicalCircuitRegion,
)
from app.models.canonical_connection import CanonicalConnection
from app.models.canonical_region import CanonicalBrainRegion
from app.models.multiscale import (
    CellTypeRegistry,
    MolecularEntityRegistry,
    RegionCellAlignment,
    RegionMolecularAlignment,
)
from app.models.ontology import OntologyTerm, OntologyTermSynonym
from app.schemas.canonical_region import CanonicalRegionCreate, CanonicalRegionHierarchyCreate
from app.services import canonical_region_service as crs

TEST_PREFIX = "oq_test_"


def _run(coro):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    return asyncio.run(coro)


async def _mk(session, code: str, *, en: str, cn: str, level: str = "clinical"):
    return await crs.create_canonical_region(
        session,
        CanonicalRegionCreate(
            region_code=code,
            canonical_name_en=en,
            canonical_name_cn=cn,
            species="human",
            granularity_level=level,
            hemisphere_policy="bilateral",
            status="active",
            confidence=0.9,
            created_by=TEST_PREFIX,
        ),
    )


async def _edge(session, child, parent):
    await crs.add_part_of_edge(
        session,
        CanonicalRegionHierarchyCreate(
            child_region_id=child.id,
            parent_region_id=parent.id,
            predicate="part_of",
            status="active",
            source="test",
            confidence=0.9,
            created_by=TEST_PREFIX,
        ),
    )


async def _cleanup_oq_test(session) -> None:
    """按 TEST_PREFIX 清理全部测试数据（FK 顺序：子表先删）。"""
    await session.execute(
        text(
            "DELETE FROM canonical_region_hierarchy WHERE child_region_id IN "
            "(SELECT id FROM canonical_brain_regions WHERE region_code LIKE :p) "
            "OR parent_region_id IN (SELECT id FROM canonical_brain_regions WHERE region_code LIKE :p)"
        ),
        {"p": f"ng:br:{TEST_PREFIX}%"},
    )
    for table in (
        "canonical_circuit_functions",
        "canonical_circuit_regions",
        "canonical_circuit_connections",
    ):
        await session.execute(
            text(
                f"DELETE FROM {table} WHERE circuit_id IN "
                f"(SELECT id FROM canonical_circuits WHERE circuit_code LIKE :p)"
            ),
            {"p": f"{TEST_PREFIX}%"},
        )
    await session.execute(
        text("DELETE FROM canonical_circuits WHERE circuit_code LIKE :p"), {"p": f"{TEST_PREFIX}%"}
    )
    await session.execute(
        text(
            "DELETE FROM canonical_connections WHERE connection_code LIKE :p OR "
            "source_region_id IN (SELECT id FROM canonical_brain_regions WHERE region_code LIKE :p2) "
            "OR target_region_id IN (SELECT id FROM canonical_brain_regions WHERE region_code LIKE :p2)"
        ),
        {"p": f"{TEST_PREFIX}%", "p2": f"ng:br:{TEST_PREFIX}%"},
    )
    await session.execute(
        text(
            "DELETE FROM region_molecular_alignment WHERE molecular_entity_id IN "
            "(SELECT id FROM molecular_entity_registry WHERE entity_code LIKE :p)"
        ),
        {"p": f"{TEST_PREFIX}%"},
    )
    await session.execute(
        text("DELETE FROM molecular_entity_registry WHERE entity_code LIKE :p"), {"p": f"{TEST_PREFIX}%"}
    )
    await session.execute(
        text(
            "DELETE FROM region_cell_alignment WHERE cell_type_id IN "
            "(SELECT id FROM cell_type_registry WHERE cell_type_code LIKE :p)"
        ),
        {"p": f"{TEST_PREFIX}%"},
    )
    await session.execute(
        text("DELETE FROM cell_type_registry WHERE cell_type_code LIKE :p"), {"p": f"{TEST_PREFIX}%"}
    )
    await session.execute(
        text(
            "DELETE FROM ontology_term_synonyms WHERE term_id IN "
            "(SELECT id FROM ontology_terms WHERE term_code LIKE :p)"
        ),
        {"p": f"{TEST_PREFIX}%"},
    )
    await session.execute(
        text("DELETE FROM ontology_terms WHERE term_code LIKE :p"), {"p": f"{TEST_PREFIX}%"}
    )
    await session.execute(
        text("DELETE FROM canonical_brain_regions WHERE region_code LIKE :p"),
        {"p": f"ng:br:{TEST_PREFIX}%"},
    )
    await session.commit()


@pytest.fixture()
def oq_db():
    """自建测试图谱：OQ测试海马 + 5 亚区 + 2 连接 + 1 回路(2 功能) + 细胞/分子 + region 术语同义词。"""

    async def _seed():
        async with AsyncSessionLocal() as session:
            hippo = await _mk(session, "ng:br:oq_test_hippocampus", en="OQ Test Hippocampus", cn="OQ测试海马")
            cortex_a = await _mk(session, "ng:br:oq_test_cortex_a", en="OQ Test Cortex A", cn="OQ测试皮层A")
            cortex_b = await _mk(session, "ng:br:oq_test_cortex_b", en="OQ Test Cortex B", cn="OQ测试皮层B")
            subs = [
                await _mk(
                    session,
                    f"ng:br:oq_test_sub_{name.lower()}",
                    en=f"OQ Test Sub {name}",
                    cn=f"OQ测试{name}",
                    level="subregion",
                )
                for name in ("CA1", "CA2", "CA3", "DG", "Subiculum")
            ]
            for sub in subs:
                await _edge(session, sub, hippo)
            await session.flush()

            # 2 条连接：皮层A → 海马（incoming），海马 → 皮层B（outgoing）
            session.add_all(
                [
                    CanonicalConnection(
                        connection_code=f"{TEST_PREFIX}conn_1",
                        source_region_id=cortex_a.id,
                        target_region_id=hippo.id,
                        connection_type="projection",
                        directionality_policy="directed",
                        status="active",
                        confidence=0.9,
                    ),
                    CanonicalConnection(
                        connection_code=f"{TEST_PREFIX}conn_2",
                        source_region_id=hippo.id,
                        target_region_id=cortex_b.id,
                        connection_type="projection",
                        directionality_policy="directed",
                        status="active",
                        confidence=0.8,
                    ),
                ]
            )

            # 1 回路（海马为成员）+ 2 个功能术语
            circuit = CanonicalCircuit(
                circuit_code=f"{TEST_PREFIX}circuit_1",
                canonical_name_en="OQ Test Trisynaptic Circuit",
                canonical_name_cn="OQ测试三突触回路",
                circuit_type="functional_loop",
                status="active",
                confidence=0.9,
            )
            session.add(circuit)
            await session.flush()
            session.add(
                CanonicalCircuitRegion(
                    circuit_id=circuit.id, region_id=hippo.id, role="core_region", order_index=0
                )
            )
            fn1 = OntologyTerm(
                term_code=f"{TEST_PREFIX}fn_1",
                canonical_term_en="Memory Encoding",
                canonical_term_cn="记忆编码",
                term_type="function",
                status="active",
            )
            fn2 = OntologyTerm(
                term_code=f"{TEST_PREFIX}fn_2",
                canonical_term_en="Spatial Navigation",
                canonical_term_cn="空间导航",
                term_type="function",
                status="active",
            )
            session.add_all([fn1, fn2])
            await session.flush()
            session.add_all(
                [
                    CanonicalCircuitFunction(
                        circuit_id=circuit.id, function_term_id=fn1.id, relation_type="associated_with"
                    ),
                    CanonicalCircuitFunction(
                        circuit_id=circuit.id, function_term_id=fn2.id, relation_type="associated_with"
                    ),
                ]
            )

            # 细胞 / 分子（multiscale 注册表）
            ct = CellTypeRegistry(
                cell_type_code=f"{TEST_PREFIX}pyramidal",
                canonical_name_en="OQ Test Pyramidal Neuron",
                canonical_name_cn="OQ测试锥体神经元",
            )
            session.add(ct)
            await session.flush()
            session.add(
                RegionCellAlignment(
                    region_id=hippo.id, cell_type_id=ct.id, mapping_type="enriched", confidence=0.9
                )
            )
            mol = MolecularEntityRegistry(
                entity_code=f"{TEST_PREFIX}gene_a",
                entity_type="gene",
                canonical_name_en="OQ Test Gene A",
                canonical_name_cn="OQ测试基因A",
            )
            session.add(mol)
            await session.flush()
            session.add(
                RegionMolecularAlignment(
                    region_id=hippo.id,
                    molecular_entity_id=mol.id,
                    entity_type="gene",
                    evidence_type="expression",
                    confidence=0.8,
                    source="test",
                )
            )

            # region 类型术语 + 同义词（synonyms 解析层）
            region_term = OntologyTerm(
                term_code=f"{TEST_PREFIX}region_term_1",
                canonical_term_en="OQ Test Hippocampus",
                canonical_term_cn="OQ测试海马",
                term_type="region",
                status="active",
            )
            session.add(region_term)
            await session.flush()
            session.add(
                OntologyTermSynonym(
                    term_id=region_term.id, synonym_text="OQ海马体", lang="cn", match_type="exact"
                )
            )
            await session.commit()
            return hippo.id

    hippo_id = _run(_seed())

    yield hippo_id

    async def _cleanup():
        async with AsyncSessionLocal() as session:
            await _cleanup_oq_test(session)

    _run(_cleanup())


def _query(question: str) -> dict:
    with TestClient(app) as client:
        resp = client.post("/api/ontology-query", json={"question": question})
        assert resp.status_code == 200, resp.text
        return resp.json()


# --------------------------------------------------------------------------- #
# 规格 5 测试（自建数据，行为等价）
# --------------------------------------------------------------------------- #


def test_children_intent_returns_subregions(oq_db):
    resp = _query("OQ测试海马有哪些亚区")

    assert resp["intent"] == "region_children"
    assert resp["confidence"] > 0
    assert resp["entity"]["type"] == "region"
    assert resp["entity"]["id"] == str(oq_db)
    assert resp["entity"]["code"] == "ng:br:oq_test_hippocampus"
    assert resp["entity"]["matched_by"] == "canonical_name_cn"
    names = {r["name"] for r in resp["results"]}
    assert {"OQ测试CA1", "OQ测试CA2", "OQ测试CA3", "OQ测试DG", "OQ测试Subiculum"} <= names
    assert all(r["category"] == "children" for r in resp["results"])
    assert all(r["provenance"] for r in resp["results"])  # 所有结果可追溯


def test_connections_intent_returns_directed_connections(oq_db):
    resp = _query("连接OQ测试海马的脑区有哪些")

    assert resp["intent"] == "region_connections"
    assert resp["entity"]["id"] == str(oq_db)
    directions = {r["detail"]["direction"] for r in resp["results"]}
    assert directions == {"incoming", "outgoing"}  # 传入 + 传出
    by_code = {r["code"]: r for r in resp["results"]}
    assert f"{TEST_PREFIX}conn_1" in by_code and f"{TEST_PREFIX}conn_2" in by_code
    assert by_code[f"{TEST_PREFIX}conn_1"]["detail"]["direction"] == "incoming"
    assert by_code[f"{TEST_PREFIX}conn_2"]["detail"]["direction"] == "outgoing"


def test_circuits_intent_returns_memberships(oq_db):
    resp = _query("OQ测试海马参与哪些回路")

    assert resp["intent"] == "region_circuits"
    assert resp["entity"]["id"] == str(oq_db)
    assert len(resp["results"]) == 1
    item = resp["results"][0]
    assert item["category"] == "circuit"
    assert item["code"] == f"{TEST_PREFIX}circuit_1"
    assert item["detail"]["role"] == "core_region"
    assert item["detail"]["circuit_type"] == "functional_loop"


def test_multiscale_intent_returns_cells_and_molecules(oq_db):
    resp = _query("OQ测试海马有哪些细胞和分子")

    assert resp["intent"] == "region_multiscale"
    assert resp["entity"]["id"] == str(oq_db)
    categories = {r["category"] for r in resp["results"]}
    assert categories == {"cell_type", "molecule"}
    assert any(r["name"] == "OQ测试锥体神经元" for r in resp["results"])
    assert any(r["name"] == "OQ Test Gene A" for r in resp["results"])


def test_unknown_question_returns_unresolved_without_error(oq_db):
    resp = _query("今天的天气怎么样")

    assert resp["intent"] == "unresolved"
    assert resp["entity"] is None
    assert resp["results"] == []
    assert resp["confidence"] == 0
    assert resp["warnings"]  # 可解释的未命中原因


# --------------------------------------------------------------------------- #
# 解析层级 + 边界补充
# --------------------------------------------------------------------------- #


def test_english_name_matches_canonical_name_en(oq_db):
    resp = _query("OQ Test Hippocampus有哪些亚区")

    assert resp["intent"] == "region_children"
    assert resp["entity"]["matched_by"] == "canonical_name_en"
    assert len(resp["results"]) == 5


def test_synonym_matches_via_region_ontology_term(oq_db):
    resp = _query("OQ海马体有哪些亚区")

    assert resp["intent"] == "region_children"
    assert resp["entity"]["matched_by"] == "synonym"
    assert resp["entity"]["id"] == str(oq_db)
    assert len(resp["results"]) == 5


def test_function_intent_returns_terms_via_circuits(oq_db):
    resp = _query("OQ测试海马的功能是什么")

    assert resp["intent"] == "region_functions"
    names = {r["name"] for r in resp["results"]}
    assert {"记忆编码", "空间导航"} <= names
    assert all(r["provenance"] for r in resp["results"])


def test_empty_results_returns_warning_not_error(oq_db):
    resp = _query("OQ测试皮层A的细胞和分子有哪些")

    assert resp["intent"] == "region_multiscale"
    assert resp["results"] == []
    assert resp["warnings"]  # 「暂无…记录」提示


def test_ambiguous_multi_entity_returns_unresolved(oq_db):
    resp = _query("OQ测试海马和OQ测试皮层A连接哪些")

    assert resp["intent"] == "unresolved"
    assert resp["warnings"]


def test_alias_matches_aligned_candidate_name(oq_db):
    """aliases 层：真实 candidate 名称（可追溯 canonical 关联）命中。无数据则跳过。"""

    async def _find_alias_name() -> tuple[str, str] | None:
        async with AsyncSessionLocal() as session:
            row = (
                await session.execute(
                    select(CandidateBrainRegion)
                    .where(CandidateBrainRegion.canonical_region_id.is_not(None))
                    .limit(1)
                )
            ).scalars().first()
            if row is None:
                return None
            return str(row.canonical_region_id), (row.raw_name or row.en_name or row.cn_name)

    found = _run(_find_alias_name())
    if found is None:
        pytest.skip("e2e 库无已对齐 candidate 行，跳过 aliases 层测试")
    canonical_id, alias_name = found

    resp = _query(f"{alias_name}有哪些亚区")
    assert resp["intent"] == "region_children"
    assert resp["entity"]["id"] == canonical_id
    assert resp["entity"]["matched_by"] == "alias"


# --------------------------------------------------------------------------- #
# 规格原文真实数据条件测试（开发库含「海马」时直接验证规格问题）
# --------------------------------------------------------------------------- #


def _real_hippocampus_id() -> str | None:
    async def _find() -> str | None:
        async with AsyncSessionLocal() as session:
            region = await crs.get_canonical_region_by_code(session, "ng:br:hippocampus")
            return str(region.id) if region else None

    return _run(_find())


def _real_region_id_by_name(cn_name: str) -> uuid.UUID | None:
    async def _find() -> uuid.UUID | None:
        async with AsyncSessionLocal() as session:
            rows = await crs.list_canonical_regions(session)
            for r in rows:
                if r.canonical_name_cn == cn_name:
                    return r.id
            return None

    return _run(_find())


def test_real_hippocampus_children_spec_question():
    """规格原文：「海马有哪些亚区」→ region_children。真实数据存在时直接验证。"""
    hippo_id = _real_hippocampus_id()
    if hippo_id is None:
        pytest.skip("e2e 库无真实海马（ng:br:hippocampus），跳过规格原文测试")

    resp = _query("海马有哪些亚区")
    assert resp["intent"] == "region_children"
    assert resp["entity"]["id"] == hippo_id
    assert resp["entity"]["matched_by"] == "canonical_name_cn"
    assert len(resp["results"]) >= 5  # 真实数据：BNA meso 分区（海马 BNA 2-1/2-2 左右 + 海马结构）

    # 规格原文的 CA1/CA2/CA3/DG/Subiculum 在真实层级挂在「海马结构」下：
    formation = _real_region_id_by_name("海马结构")
    if formation:
        resp2 = _query("海马结构有哪些亚区")
        assert resp2["intent"] == "region_children"
        assert resp2["entity"]["id"] == str(formation)
        names2 = {r["name"] for r in resp2["results"]}
        assert len(names2) >= 5
        assert any(n.startswith("CA1") for n in names2)
        assert any(n.startswith("CA2") for n in names2)
        assert any(n.startswith("CA3") for n in names2)
        assert any("齿状回" in n for n in names2)  # DG
        assert any("下托" in n or "Subiculum" in n for n in names2)


def test_real_hippocampus_connections_spec_question():
    hippo_id = _real_hippocampus_id()
    if hippo_id is None:
        pytest.skip("e2e 库无真实海马，跳过规格原文测试")

    resp = _query("连接海马的脑区有哪些")
    assert resp["intent"] == "region_connections"
    assert resp["entity"]["id"] == hippo_id
    assert all(r["category"] == "connection" for r in resp["results"])
