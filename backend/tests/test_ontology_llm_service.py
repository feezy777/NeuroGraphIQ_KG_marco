"""Phase Q4 — Ontology Query LLM 解释层测试。

规格覆盖（test_ontology_llm_service.py）：
1. structured result → answer（mock provider，验证 prompt 拼接 / temperature=0.1）
2. 禁止添加不存在实体 → hallucination_warning（回答中出现 evidence 外的已知脑区）
3. 空结果 → 「当前知识图谱暂无相关信息。」（不调用 LLM）
4. API /api/ontology-query/explain 正常调用（unresolved → 确定性回退；有结果 → LLM 解释）

额外覆盖：
- 连接意图空结果 → 「当前知识图谱未发现相关连接。」
- ontology_query 配置 enabled=False → 不调用 LLM
- provider 抛异常 → 回退不阻断
- 无幻觉误报（回答只含 evidence 名称；「海马」⊂「Q15测试海马」子串排除）
- evidence_entities 由结构化结果确定性导出（不采信 LLM 自报）
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.main import app
from app.schemas.canonical_region import CanonicalRegionCreate
from app.schemas.ontology_query import (
    OntologyQueryEntity,
    OntologyQueryResponse,
    OntologyQueryResultItem,
)
from app.schemas.settings import OntologyQueryRuntimeSettings
from app.services import canonical_region_service as crs
from app.services.llm_providers.base import LlmProviderResponse, LlmProviderUsage
from app.services.ontology_llm_service import generate_explanation

TEST_PREFIX = "q15_llm_"


def _run(coro):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    return asyncio.run(coro)


def _mk_response(parsed: dict) -> LlmProviderResponse:
    return LlmProviderResponse(
        provider="deepseek",
        model="deepseek-v4-flash",
        raw_text=__import__("json").dumps(parsed, ensure_ascii=False),
        parsed_json=parsed,
        usage=LlmProviderUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        finish_reason="stop",
        request_payload_redacted={},
        response_payload={},
        latency_ms=5,
    )


def _query_response(
    *,
    intent: str = "region_functions",
    entity_name: str = "Q15测试海马",
    results: list[OntologyQueryResultItem] | None = None,
) -> OntologyQueryResponse:
    return OntologyQueryResponse(
        intent=intent,
        entity=OntologyQueryEntity(
            type="region",
            id="00000000-0000-0000-0000-000000000001",
            code="ng:br:q15_llm_hippo",
            name=entity_name,
            matched_by="canonical_name_cn",
        ),
        results=results or [],
        confidence=0.95,
        warnings=[],
    )


def _function_result(name: str = "记忆形成") -> OntologyQueryResultItem:
    return OntologyQueryResultItem(
        id="00000000-0000-0000-0000-000000000002",
        code="ng:func:q15_memory",
        name=name,
        category="function",
        detail={},
        confidence=0.9,
        provenance="canonical_function",
    )


async def _cleanup_q15(session) -> None:
    await session.execute(
        text("DELETE FROM canonical_brain_regions WHERE region_code LIKE :p"),
        {"p": f"ng:br:{TEST_PREFIX}%"},
    )
    await session.commit()


async def _seed_phantom(session) -> None:
    """seed 一个「回答中出现但不在 evidence 中」的已知脑区 Q15幻影海马。"""
    await crs.create_canonical_region(
        session,
        CanonicalRegionCreate(
            region_code="ng:br:q15_llm_phantom",
            canonical_name_en="Q15 Phantom Hippocampus",
            canonical_name_cn="Q15幻影海马",
            species="human",
            granularity_level="clinical",
            hemisphere_policy="bilateral",
            status="active",
            confidence=0.9,
            created_by=TEST_PREFIX,
        ),
    )
    await session.commit()


@pytest.fixture()
def q15_llm_db():
    async def _seed():
        async with AsyncSessionLocal() as session:
            await _cleanup_q15(session)
            await _seed_phantom(session)

    _run(_seed())
    yield
    async def _cleanup():
        async with AsyncSessionLocal() as session:
            await _cleanup_q15(session)

    _run(_cleanup())


# --------------------------------------------------------------------------- #
# 1. structured result → answer
# --------------------------------------------------------------------------- #

def test_1_structured_result_to_answer(monkeypatch):
    """规格 1：结构化结果 → LLM answer；prompt 含问题与结果、temperature=0.1。"""
    query = _query_response(results=[_function_result()])
    parsed = {
        "answer": "根据知识图谱，Q15测试海马目前关联的功能包括：1.记忆形成。证据来源：Q15测试海马 canonical_function。",
        "summary": "Q15测试海马 关联功能：记忆形成",
        "key_points": ["记忆形成"],
        "confidence": 0.9,
    }
    mock_provider = AsyncMock()
    mock_provider.complete_json = AsyncMock(return_value=_mk_response(parsed))
    monkeypatch.setattr(
        "app.services.ontology_llm_service.get_llm_provider", lambda name: mock_provider
    )
    monkeypatch.setattr(
        "app.services.ontology_llm_service.get_ontology_query_runtime_config",
        lambda: OntologyQueryRuntimeSettings(
            enabled=True, provider="deepseek", model="deepseek-v4-flash", temperature=0.1
        ),
    )

    async def _call():
        async with AsyncSessionLocal() as session:
            return await generate_explanation(session, query, "Q15测试海马有哪些功能")

    resp = _run(_call())

    assert resp.answer.startswith("根据知识图谱")
    assert resp.summary == "Q15测试海马 关联功能：记忆形成"
    assert resp.key_points == ["记忆形成"]
    assert resp.confidence == 0.9
    # evidence_entities 由结构化结果导出：实体名 + code + 结果名
    assert resp.evidence_entities == [
        "Q15测试海马",
        "ng:br:q15_llm_hippo",
        "记忆形成",
        "ng:func:q15_memory",
    ]
    assert resp.hallucination_warning == []
    # 调用参数校验：temperature=0.1（规格要求低温度稳定），prompt 含问题与结果
    call_kwargs = mock_provider.complete_json.call_args.kwargs
    assert call_kwargs["model"] == "deepseek-v4-flash"
    assert call_kwargs["temperature"] == 0.1
    assert "Q15测试海马有哪些功能" in call_kwargs["user_prompt"]
    assert "记忆形成" in call_kwargs["user_prompt"]


# --------------------------------------------------------------------------- #
# 2. 禁止添加不存在实体 → hallucination_warning
# --------------------------------------------------------------------------- #

def test_2_hallucinated_known_region_flagged(q15_llm_db, monkeypatch):
    """规格 2：回答中出现 evidence 外的已知脑区 → hallucination_warning（不阻断）。"""
    query = _query_response(results=[_function_result()])
    parsed = {
        "answer": "根据知识图谱，Q15测试海马与 Q15幻影海马 存在重要关联。",
        "summary": "Q15测试海马 关联 Q15幻影海马",
        "key_points": [],
        "confidence": 0.9,
    }
    mock_provider = AsyncMock()
    mock_provider.complete_json = AsyncMock(return_value=_mk_response(parsed))
    monkeypatch.setattr(
        "app.services.ontology_llm_service.get_llm_provider", lambda name: mock_provider
    )
    monkeypatch.setattr(
        "app.services.ontology_llm_service.get_ontology_query_runtime_config",
        lambda: OntologyQueryRuntimeSettings(),
    )

    async def _call():
        async with AsyncSessionLocal() as session:
            return await generate_explanation(session, query, "Q15测试海马有哪些功能")

    resp = _run(_call())

    # 幻影脑区不在 evidence 中 → 标记；「海马」⊂「Q15测试海马」子串排除不误报
    assert "Q15幻影海马" in resp.hallucination_warning
    assert "海马" not in resp.hallucination_warning


def test_2b_no_false_positive_when_only_evidence_names(q15_llm_db, monkeypatch):
    """扩展：回答只含 evidence 名称时无幻觉标记（含子串排除）。"""
    query = _query_response(results=[_function_result()])
    parsed = {
        "answer": "根据知识图谱，Q15测试海马目前关联功能：记忆形成。",
        "summary": "Q15测试海马",
        "key_points": ["记忆形成"],
        "confidence": 0.9,
    }
    mock_provider = AsyncMock()
    mock_provider.complete_json = AsyncMock(return_value=_mk_response(parsed))
    monkeypatch.setattr(
        "app.services.ontology_llm_service.get_llm_provider", lambda name: mock_provider
    )
    monkeypatch.setattr(
        "app.services.ontology_llm_service.get_ontology_query_runtime_config",
        lambda: OntologyQueryRuntimeSettings(),
    )

    async def _call():
        async with AsyncSessionLocal() as session:
            return await generate_explanation(session, query, "Q15测试海马有哪些功能")

    resp = _run(_call())
    assert resp.hallucination_warning == []


# --------------------------------------------------------------------------- #
# 3. 空结果 / 未解析 → 确定性回退，不调用 LLM
# --------------------------------------------------------------------------- #

def test_3_empty_results_fallback_no_llm(monkeypatch):
    """规格 3：空结果 → 「当前知识图谱暂无相关信息。」，不调用 LLM。"""
    query = _query_response(results=[])  # 有实体但无结果
    monkeypatch.setattr(
        "app.services.ontology_llm_service.get_llm_provider",
        AsyncMock(),
    )

    async def _call():
        async with AsyncSessionLocal() as session:
            return await generate_explanation(session, query, "Q15测试海马有哪些功能")

    resp = _run(_call())
    assert resp.answer == "当前知识图谱暂无相关信息。"
    assert resp.confidence == 0.95  # 回退沿用结构化置信度
    assert resp.evidence_entities == ["Q15测试海马", "ng:br:q15_llm_hippo"]


def test_3b_unresolved_fallback_no_llm(monkeypatch):
    """扩展：unresolved（无实体）→ 回退说明，不调用 LLM。"""
    query = OntologyQueryResponse(
        intent="unresolved", entity=None, results=[], confidence=0.0, warnings=["未识别"]
    )
    mock_get = AsyncMock()
    monkeypatch.setattr("app.services.ontology_llm_service.get_llm_provider", mock_get)

    async def _call():
        async with AsyncSessionLocal() as session:
            return await generate_explanation(session, query, "今天的天气")

    resp = _run(_call())
    assert "暂无相关信息" in resp.answer
    assert resp.confidence == 0.0
    mock_get.assert_not_called()


def test_3c_connection_empty_results_uses_connection_message(monkeypatch):
    """扩展：连接意图空结果 → 「当前知识图谱未发现相关连接。」。"""
    query = _query_response(intent="region_connections", results=[])

    async def _call():
        async with AsyncSessionLocal() as session:
            return await generate_explanation(session, query, "Q15测试海马和Q15幻影海马有什么关系")

    resp = _run(_call())
    assert resp.answer == "当前知识图谱未发现相关连接。"


def test_3d_disabled_config_no_llm(monkeypatch):
    """扩展：ontology_query enabled=False → 回退，不调用 LLM。"""
    query = _query_response(results=[_function_result()])
    mock_get = AsyncMock()
    monkeypatch.setattr("app.services.ontology_llm_service.get_llm_provider", mock_get)
    monkeypatch.setattr(
        "app.services.ontology_llm_service.get_ontology_query_runtime_config",
        lambda: OntologyQueryRuntimeSettings(enabled=False),
    )

    async def _call():
        async with AsyncSessionLocal() as session:
            return await generate_explanation(session, query, "Q15测试海马有哪些功能")

    resp = _run(_call())
    assert "LLM 解释暂不可用" in resp.answer  # 有结果 → 原始摘要回退
    assert resp.key_points == ["记忆形成"]
    mock_get.assert_not_called()


def test_3e_provider_failure_falls_back(monkeypatch):
    """扩展：provider 抛异常 → 确定性回退，不阻断。"""
    query = _query_response(results=[_function_result()])
    mock_provider = AsyncMock()
    mock_provider.complete_json = AsyncMock(side_effect=RuntimeError("network down"))
    monkeypatch.setattr(
        "app.services.ontology_llm_service.get_llm_provider", lambda name: mock_provider
    )
    monkeypatch.setattr(
        "app.services.ontology_llm_service.get_ontology_query_runtime_config",
        lambda: OntologyQueryRuntimeSettings(),
    )

    async def _call():
        async with AsyncSessionLocal() as session:
            return await generate_explanation(session, query, "Q15测试海马有哪些功能")

    resp = _run(_call())
    assert "LLM 解释暂不可用" in resp.answer
    assert resp.key_points == ["记忆形成"]


# --------------------------------------------------------------------------- #
# 4. API /api/ontology-query/explain 正常调用
# --------------------------------------------------------------------------- #

def _api_explain(question: str) -> dict:
    with TestClient(app) as client:
        resp = client.post("/api/ontology-query/explain", json={"question": question})
        assert resp.status_code == 200, resp.text
        return resp.json()


def test_4_api_explain_unresolved_returns_both_tracks():
    """规格 4：API 正常调用 — unresolved 问题返回 {question, query_result, explanation}。"""
    data = _api_explain("QQQQQLLMXYZ有哪些亚区")

    assert data["question"] == "QQQQQLLMXYZ有哪些亚区"
    assert data["query_result"]["intent"] == "unresolved"
    assert data["query_result"]["entity"] is None
    assert data["explanation"]["answer"].startswith("未解析到")
    assert "暂无相关信息" in data["explanation"]["answer"]
    assert data["explanation"]["confidence"] == 0.0


def test_4b_api_explain_with_mock_provider(monkeypatch):
    """规格 4 扩展：真实查询 + mock provider → LLM 解释写入 explanation。"""
    async def _region_exists() -> bool:
        async with AsyncSessionLocal() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT 1 FROM canonical_brain_regions "
                        "WHERE canonical_name_cn = '海马' AND status = 'active'"
                    )
                )
            ).first()
            return row is not None

    if not _run(_region_exists()):
        pytest.skip("开发库无 canonical_name_cn=海马 的 active 脑区")

    parsed = {
        "answer": "海马是重要的记忆相关脑区。根据知识图谱，目前关联功能包括：记忆形成、空间导航。",
        "summary": "海马 关联 记忆形成等 73 条功能",
        "key_points": ["记忆形成", "空间导航"],
        "confidence": 0.85,
    }
    mock_provider = AsyncMock()
    mock_provider.complete_json = AsyncMock(return_value=_mk_response(parsed))
    monkeypatch.setattr(
        "app.services.ontology_llm_service.get_llm_provider", lambda name: mock_provider
    )
    monkeypatch.setattr(
        "app.services.ontology_llm_service.get_ontology_query_runtime_config",
        lambda: OntologyQueryRuntimeSettings(),
    )

    data = _api_explain("海马有哪些功能")

    assert data["query_result"]["intent"] == "region_functions"
    assert data["query_result"]["entity"]["code"] == "ng:br:hippocampus"
    assert data["query_result"]["results"]
    expl = data["explanation"]
    assert expl["answer"] == parsed["answer"]
    assert expl["summary"] == parsed["summary"]
    assert expl["key_points"] == ["记忆形成", "空间导航"]
    assert expl["confidence"] == 0.85
    # evidence_entities 以结构化结果为准（LLM 自报不被采信）
    assert "海马" in expl["evidence_entities"]
