# -*- coding: utf-8 -*-
"""locate/judge/two-stage semantic-block tests.

Semantic recall path: full-text semantic blocks → LLM locate (high recall) →
strict judge (component match required). Co-occurrence alone is not evidence.
"""

import asyncio
from unittest.mock import AsyncMock, patch

from app.services import paper_evidence_service as pes


def _run(coro):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _claim():
    return {
        "claim_text": "X projects to Y",
        "structured_claim": {},
        "function_term": "connect",
        "claim_components": [],
        "claim_version": "v1",
    }


def _blocks():
    return [
        {
            "block_id": "b1",
            "paragraphs": [
                {"paragraph_id": "p1", "passage_text": "text one", "section_title": "Results"}
            ],
        },
        {
            "block_id": "b2",
            "paragraphs": [
                {"paragraph_id": "p2", "passage_text": "text two", "section_title": "Discussion"}
            ],
        },
    ]


def test_locate_uses_blocks_and_returns_hits():
    """locate 直接对语义块高召回:返回块 id + 块全文,不依赖关键词窗口。"""
    with patch.object(pes, "get_llm_provider", return_value=AsyncMock()) as mock_provider:
        mock_provider.return_value.complete_json = AsyncMock(return_value=type(
            "R",
            (),
            {
                "raw_text": "",
                "parsed_json": {
                    "candidates": [
                        {"paragraph_id": "b2", "relevance": 0.9,
                         "relation_cue": "direct_connection", "reason": "相关"}
                    ]
                },
                "model": "m",
            },
        )())
        hits = _run(pes.locate_candidates(_claim(), _blocks()))
    assert len(hits) == 1
    assert hits[0]["paragraph_id"] == "b2"
    assert hits[0]["relevance"] == 0.9
    assert hits[0]["passage_text"] == "text two"
    assert hits[0]["section"] == "Discussion"


def test_locate_still_supports_legacy_context_windows():
    """兼容旧 {context: [...]} 关键词窗口结构。"""
    legacy = [
        {
            "context": [
                {"paragraph_id": "p1", "passage_text": "text one", "section_title": "Results"}
            ]
        },
        {
            "context": [
                {"paragraph_id": "p2", "passage_text": "text two", "section_title": "Discussion"}
            ]
        },
    ]
    with patch.object(pes, "get_llm_provider", return_value=AsyncMock()) as mock_provider:
        mock_provider.return_value.complete_json = AsyncMock(return_value=type(
            "R",
            (),
            {
                "raw_text": "",
                "parsed_json": {
                    "candidates": [{"paragraph_id": "p2", "relevance": 0.8, "reason": "x"}]
                },
                "model": "m",
            },
        )())
        hits = _run(pes.locate_candidates(_claim(), legacy))
    assert len(hits) == 1
    assert hits[0]["paragraph_id"] == "p2"
    assert hits[0]["passage_text"] == "text two"


def test_judge_user_prompt_requires_component_match():
    """严格判定:要素至少两项匹配才给证据;仅共现不算证据。"""
    assert "至少" in pes._JUDGE_USER and "supported_components" in pes._JUDGE_USER
    assert "共现" in pes._JUDGE_USER
    assert "not_found" in pes._JUDGE_USER


def test_judge_accepts_block_hits_full_text():
    """judge 输入为块全文(不截断),id 取 paragraph_id/block_id。"""
    provider = AsyncMock()
    provider.complete_json = AsyncMock(return_value=type(
        "R",
        (),
        {
            "raw_text": "",
            "parsed_json": {
                "overall_direction": "supports",
                "paper_relevance": 0.9,
                "assessment": "支持",
                "evidence_dimension": "existence",
                "passages": [{"paragraph_id": "b2", "passage": "text two", "direction": "supports"}],
            },
            "model": "m",
        },
    )())
    with patch.object(pes, "get_llm_provider", return_value=provider):
        candidates = [
            {"paragraph_id": "b1", "passage_text": "text one", "section_title": "Results"},
            {"paragraph_id": "b2", "passage_text": "text two", "section_title": "Discussion"},
        ]
        result = _run(pes.judge_candidates(_claim(), candidates, "t"))
    assert result["overall_direction"] == "supports"
    assert len(result["passages"]) == 1
    assert provider.complete_json.await_count == 1


def test_build_judge_input_joins_neighbor_blocks():
    """命中块 + 前后各 1 个邻块全文拼接,供 judge 严格判定。"""
    blocks = [
        {"block_id": "b1", "paragraphs": [{"paragraph_id": "p1", "passage_text": "A" * 100}]},
        {"block_id": "b2", "paragraphs": [{"paragraph_id": "p2", "passage_text": "B" * 100}]},
        {"block_id": "b3", "paragraphs": [{"paragraph_id": "p3", "passage_text": "C" * 100}]},
    ]
    hits = [{"paragraph_id": "b2", "relevance": 0.9}]
    inp = pes._build_judge_input(blocks, hits)
    assert len(inp) == 1
    assert inp[0]["paragraph_id"] == "b2"
    assert "A" * 100 in inp[0]["passage_text"]
    assert "B" * 100 in inp[0]["passage_text"]
    assert "C" * 100 in inp[0]["passage_text"]


def test_two_stage_uses_semantic_blocks_and_judges():
    """two_stage 对语义块 locate → 命中块+邻块 judge。"""
    from app.services.paragraph_retrieval import build_semantic_windows

    paras = [
        {"paragraph_id": "p1", "passage_text": "X terminates in Y as shown by tracing.",
         "section_title": "Results", "paragraph_index": 0, "source_scope": "body"},
        {"paragraph_id": "p2", "passage_text": "Unrelated cell culture methods.",
         "section_title": "Methods", "paragraph_index": 1, "source_scope": "body"},
    ]
    blocks = build_semantic_windows(paras, target_chars=800, max_windows=60)
    with patch.object(pes, "locate_candidates", new=AsyncMock(return_value=[
        {"paragraph_id": "p1", "relevance": 0.9,
         "passage_text": "X terminates in Y as shown by tracing.", "section": "Results"},
    ])) as mock_locate:
        with patch.object(pes, "judge_candidates", new=AsyncMock(return_value={
            "overall_direction": "supports", "paper_relevance": 0.9,
            "assessment": "支持", "evidence_dimension": "existence",
            "passages": [{"paragraph_id": "p1", "passage": "X terminates in Y as shown by tracing.",
                          "direction": "supports", "confidence": 0.8}],
        })) as mock_judge:
            result = _run(pes.extract_passage_two_stage(
                claim=_claim(), title="t", windows=blocks
            ))
    assert result["overall_direction"] == "supports"
    assert len(result["passages"]) == 1
    assert result["_two_stage"] is True
    # locate 收到的是语义块
    locate_args = mock_locate.await_args
    assert locate_args.args[1][0]["block_id"] == "p1"


def test_two_stage_falls_back_when_locate_empty():
    """0 命中回退:单阶段提取(块转窗口结构)。"""
    from app.services.paragraph_retrieval import build_semantic_windows

    paras = [
        {"paragraph_id": "p1", "passage_text": "X projects to Y in macaque.",
         "section_title": "Abstract", "paragraph_index": 0, "source_scope": "abstract"},
    ]
    blocks = build_semantic_windows(paras, target_chars=800, max_windows=60)
    with patch.object(pes, "locate_candidates", new=AsyncMock(return_value=[])):
        with patch.object(pes, "extract_passage_from_paper", new=AsyncMock(return_value={
            "overall_direction": "partial", "paper_relevance": 0.4, "assessment": "a",
            "passages": [{"paragraph_id": "p1", "passage": "X projects to Y in macaque.",
                          "direction": "partial", "confidence": 0.3}],
        })) as mock_extract:
            result = _run(pes.extract_passage_two_stage(
                claim=_claim(), title="t", windows=blocks
            ))
    assert result["overall_direction"] == "partial"
    assert "_two_stage" not in result
    # 回退传的是窗口结构(context)而非块,兼容单阶段提取器
    assert mock_extract.await_args.kwargs["windows"][0]["context"]
