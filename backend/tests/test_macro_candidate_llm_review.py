"""Macro Candidate Connection LLM Scientific Review V1 测试(纯函数 + mock provider)。

覆盖用户要求 5 项:
1. LLM JSON 解析测试
2. invalid response fallback
3. decision 分类测试
4. provenance 完整测试
5. 幂等测试

扩展:prompt 构造含全部证据字段、重试(transport 失败后成功)、
全失败 → uncertain fallback、token_usage 记录。
LLM 调用全部 mock(项目硬约束:测试必须 mock provider)。
"""

import asyncio

import pytest

from app.services.llm_providers.base import (
    LlmProviderTextResult,
    LlmProviderUsage,
)
from app.services.macro_candidate_llm_review_service import (
    ASSERTION_TYPE,
    GENERATION_METHOD,
    INSERT_REVIEW_SQL,
    PROMPT_VERSION,
    SOURCE_TYPE,
    SYSTEM_PROMPT,
    build_user_prompt,
    normalize_review,
    parse_llm_json,
    review_one_candidate,
)

RANKING_ID = "r1111111-1111-1111-1111-111111111111"
RANKING = {
    "id": RANKING_ID,
    "source_region_id": "11111111-1111-1111-1111-111111111111",
    "target_region_id": "22222222-2222-2222-2222-222222222222",
    "source_name": "Amygdala",
    "target_name": "Hippocampus",
    "paper_count": 3,
    "candidate_pair_ids": ["c1111111-1111-1111-1111-111111111111"],
}
EVIDENCES = [{
    "paper_title": "Amygdala–hippocampus projections",
    "pmid": 12345,
    "section_name": "Results",
    "sentence": "The amygdala sends a dense projection to the hippocampus.",
}]


class FakeProvider:
    """可控 mock provider:预设响应序列。"""

    name = "fake"

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    async def complete_text(self, **kwargs):
        self.calls += 1
        if not self._responses:
            return LlmProviderTextResult(
                raw_text=None, usage=LlmProviderUsage(), finish_reason=None,
                provider="fake", model="fake-model", transport_ok=False,
                error="no_more_responses")
        return self._responses.pop(0)


def _result(raw_text=None, *, transport_ok=True, error=None,
            usage=None, latency_ms=0):
    return LlmProviderTextResult(
        raw_text=raw_text,
        usage=usage or LlmProviderUsage(prompt_tokens=100,
                                        completion_tokens=50,
                                        total_tokens=150),
        finish_reason="stop",
        provider="fake",
        model="fake-model",
        transport_ok=transport_ok,
        error=error,
        latency_ms=latency_ms,
        response_format="text")


async def _review_async(responses, **kwargs):
    fake = FakeProvider(responses)
    import app.services.macro_candidate_llm_review_service as mod
    original = mod.get_llm_provider
    mod.get_llm_provider = lambda _k: fake
    try:
        return await review_one_candidate(RANKING, EVIDENCES,
                                          provider_key="deepseek",
                                          model="fake-model",
                                          max_retries=kwargs.pop(
                                              "retries", 2), **kwargs)
    finally:
        mod.get_llm_provider = original


def _review(responses, **kwargs):
    return asyncio.run(_review_async(responses, **kwargs))


# ---- 1. LLM JSON 解析测试 ----

def test_parse_plain_json():
    parsed, err = parse_llm_json('{"decision": "supported", "confidence": 0.9}')
    assert parsed == {"decision": "supported", "confidence": 0.9}
    assert err is None


def test_parse_markdown_fenced_json():
    raw = ('```json\n{"decision": "uncertain", "confidence": 0.4}\n```')
    parsed, err = parse_llm_json(raw)
    assert parsed["decision"] == "uncertain"
    assert err is None


def test_parse_json_with_surrounding_text():
    raw = ('Here is my analysis:\n{"decision": "not_supported", '
           '"reasoning": "co-occurrence only"}\nHope this helps.')
    parsed, err = parse_llm_json(raw)
    assert parsed["decision"] == "not_supported"
    assert err is None


def test_parse_trailing_comma():
    parsed, err = parse_llm_json(
        '{"decision": "supported", "confidence": 0.8,}')
    assert parsed["decision"] == "supported"
    assert err == "trailing_comma_fixed"


def test_parse_empty_and_non_json():
    assert parse_llm_json(None) == (None, "empty_response")
    assert parse_llm_json("") == (None, "empty_response")
    parsed, err = parse_llm_json("I cannot determine anything at all.")
    assert parsed is None
    assert err is not None


# ---- 2. invalid response fallback ----

def test_invalid_response_falls_back_to_uncertain():
    """非 JSON 响应 → decision=uncertain + strength=low + parse_error 记录。"""
    review = _review([_result("The amygdala projects to hippocampus.")])
    assert review["decision"] == "uncertain"
    assert review["evidence_strength"] == "low"
    assert review["connection_type"] == "unknown"
    assert review["raw_response_json"]["parse_error"] is not None


def test_transport_failure_falls_back_to_uncertain():
    """transport 全失败 → uncertain + error 记录,不抛异常。"""
    review = _review([_result(None, transport_ok=False, error="timeout"),
                            _result(None, transport_ok=False, error="timeout"),
                            _result(None, transport_ok=False, error="timeout")],
                           retries=2)
    assert review["decision"] == "uncertain"
    assert review["raw_response_json"]["transport_ok"] is False
    assert review["raw_response_json"]["error"] == "timeout"


def test_retry_then_success():
    """前两次失败,第三次成功 → 成功结果生效(重试生效)。"""
    review = _review([
        _result(None, transport_ok=False, error="timeout"),
        _result("{not valid json"),
        _result('{"decision": "supported", "connection_type": "projection", '
                '"direction": "A_to_B", "confidence": 0.85, '
                '"evidence_strength": "high", "reasoning": "dense projection"}'),
    ], retries=2)
    assert review["decision"] == "supported"
    assert review["connection_type"] == "projection"
    assert review["direction"] == "A_to_B"
    assert review["confidence"] == 0.85
    assert review["evidence_strength"] == "high"


# ---- 3. decision 分类测试 ----

def test_normalize_keeps_valid_values():
    data = {"decision": "supported", "connection_type": "functional_connectivity",
            "direction": "bidirectional", "confidence": 0.75,
            "evidence_strength": "medium", "reasoning": "fc found"}
    out = normalize_review(data)
    assert out["decision"] == "supported"
    assert out["connection_type"] == "functional_connectivity"
    assert out["direction"] == "bidirectional"
    assert out["confidence"] == 0.75
    assert out["evidence_strength"] == "medium"


def test_normalize_invalid_values_default():
    """非法枚举 → 默认值(decision→uncertain, type→unknown, ...)。"""
    out = normalize_review({"decision": "YES", "connection_type": "tract",
                            "direction": "up", "confidence": "abc",
                            "evidence_strength": "very_high",
                            "reasoning": None})
    assert out["decision"] == "uncertain"
    assert out["connection_type"] == "unknown"
    assert out["direction"] == "unknown"
    assert out["confidence"] == 0.0
    assert out["evidence_strength"] == "low"
    assert out["reasoning"] == ""


def test_normalize_confidence_clamped():
    assert normalize_review({"confidence": 1.7})["confidence"] == 1.0
    assert normalize_review({"confidence": -0.3})["confidence"] == 0.0
    assert normalize_review({"confidence": 0.4567})["confidence"] == 0.457


# ---- 4. provenance 完整测试 ----

def test_provenance_complete():
    review = _review([_result(
        '{"decision": "supported", "connection_type": "projection", '
        '"direction": "A_to_B", "confidence": 0.9, '
        '"evidence_strength": "high", "reasoning": "explicit projection"}')])
    prov = review["provenance_json"]
    assert prov["ranking_id"] == RANKING_ID
    assert prov["prompt_version"] == PROMPT_VERSION
    assert prov["candidate_pair_ids"] == RANKING["candidate_pair_ids"]
    assert prov["trace_chain"] == ["ranking", "candidate_pair", "llm_review"]
    assert prov["llm"]["provider"] == "deepseek"
    assert prov["llm"]["model"] == "fake-model"
    assert "system" in prov["prompt"] and "user" in prov["prompt"]
    # prompt 含判断原则 + 证据原文
    assert "神经科学知识图谱审核专家" in prov["prompt"]["system"]
    assert "Amygdala" in prov["prompt"]["user"]
    assert "dense projection to the hippocampus" in prov["prompt"]["user"]
    assert prov["evidence_refs"][0]["pmid"] == 12345
    assert prov["evidence_refs"][0]["sentence_snippet"].startswith("The amygdala")
    # model_name + token_usage
    assert review["model_name"] == "fake-model"
    assert review["token_usage"] == {"prompt_tokens": 100,
                                     "completion_tokens": 50,
                                     "total_tokens": 150}
    # 约束字段
    assert review["assertion_type"] == ASSERTION_TYPE == "candidate"
    assert review["source_type"] == SOURCE_TYPE == "llm_review"
    assert review["generation_method"] == GENERATION_METHOD


def test_build_prompt_contains_all_evidence_fields():
    prompt = build_user_prompt("Amygdala", "Hippocampus", [{
        "paper_title": "A&H study", "pmid": 999,
        "section_name": "Methods",
        "sentence": "Amygdala connects to hippocampus via a tract.",
    }])
    assert "Region A: Amygdala" in prompt
    assert "Region B: Hippocampus" in prompt
    assert "论文: A&H study" in prompt
    assert "PMID: 999" in prompt
    assert "section: Methods" in prompt
    assert "Amygdala connects to hippocampus via a tract." in prompt


# ---- 5. 幂等测试 ----

def test_insert_idempotent_sql():
    assert "ON CONFLICT (ranking_id) DO NOTHING" in INSERT_REVIEW_SQL
    assert "DELETE" not in INSERT_REVIEW_SQL
    assert "UPDATE" not in INSERT_REVIEW_SQL
    assert "generation_method" in INSERT_REVIEW_SQL
