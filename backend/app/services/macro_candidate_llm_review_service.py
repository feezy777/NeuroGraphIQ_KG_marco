"""Macro Candidate Connection LLM Scientific Review V1 —— LLM 科学审核。

输入 paper_connection_candidate_rankings(第一阶段 Top 200,score 降序),
LLM 依据论文原文证据判断 supported / uncertain / not_supported,
结果写入 macro_candidate_connection_llm_reviews(candidate 层)。

流程:
  paper_candidate_ranking → LLM evidence judge → review results

约束(用户要求):
* 允许 LLM 调用 + 创建 candidate review 结果
* 禁止:创建 canonical connection / validation / promotion /
  Final KG 写入 / 修改已有连接 / 修改 ranking
* LLM 必须经 llm_providers/factory.py 抽象(项目硬约束)
* 保存 prompt + response + model_name + token 信息(接口提供时)
* 失败重试(指数退避) + 幂等(UNIQUE(ranking_id) + ON CONFLICT DO NOTHING)

判断原则(用户定义,全部进入 system prompt):
1. 必须基于论文原文
2. 仅共同出现不能认为连接
3. 背景介绍/疾病相关/功能描述但无连接关系 → not_supported
4. 出现 projection/connect/tract/fiber/pathway/connectivity → 优先考虑支持
5. 保留不确定
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from app.services.llm_providers.factory import get_llm_provider
from app.services.settings_service import (
    get_deepseek_runtime_config,
    get_kimi_runtime_config,
)

# ---- 常量 ----

GENERATION_METHOD = "macro_candidate_llm_review_v1"
ASSERTION_TYPE = "candidate"
SOURCE_TYPE = "llm_review"
PROMPT_VERSION = "macro_candidate_llm_review_v1"

DECISION_VALUES = ("supported", "uncertain", "not_supported")
CONNECTION_TYPE_VALUES = ("structural_connection", "functional_connectivity",
                          "projection", "association", "unknown")
DIRECTION_VALUES = ("A_to_B", "B_to_A", "bidirectional", "unknown")
STRENGTH_VALUES = ("high", "medium", "low")

DEFAULT_DECISION = "uncertain"
DEFAULT_CONNECTION_TYPE = "unknown"
DEFAULT_DIRECTION = "unknown"
DEFAULT_STRENGTH = "low"
DEFAULT_CONFIDENCE = 0.0

MAX_EVIDENCES_PER_PROMPT = 3
MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 2.0
DEFAULT_TEMPERATURE = 0.1
DEFAULT_MAX_TOKENS = 1200

SYSTEM_PROMPT = """你是一名神经科学知识图谱审核专家。根据提供的论文证据，判断两个脑区之间是否存在明确连接。

判断原则：
1. 必须基于论文原文，不要猜测。
2. 仅共同出现不能认为连接。
3. 背景介绍、疾病相关、功能描述但无连接关系：not_supported。
4. 出现 projection、connect、tract、fiber、pathway、connectivity 等连接相关表述：优先考虑支持。
5. 无法确定时保留 uncertain。

请输出 JSON（不要输出其他文本）：
{
  "decision": "supported" | "uncertain" | "not_supported",
  "connection_type": "structural_connection" | "functional_connectivity" | "projection" | "association" | "unknown",
  "direction": "A_to_B" | "B_to_A" | "bidirectional" | "unknown",
  "confidence": 0-1,
  "evidence_strength": "high" | "medium" | "low",
  "reasoning": "解释为什么"
}"""


# ---- Prompt 构造 ----

def build_user_prompt(region_a: str, region_b: str,
                      evidences: list[dict]) -> str:
    """Region A/B + 论文证据 → user prompt(每条证据: title/PMID/section/句子)。"""
    lines = [
        f"Region A: {region_a}",
        f"Region B: {region_b}",
        "",
        "Evidence:",
    ]
    for i, ev in enumerate(evidences[:MAX_EVIDENCES_PER_PROMPT], 1):
        title = (ev.get("paper_title") or "unknown").strip()
        pmid = ev.get("pmid")
        section = (ev.get("section_name") or "unknown").strip()
        sentence = (ev.get("sentence") or "").strip()
        lines.append(f"[{i}]")
        lines.append(f"论文: {title}")
        lines.append(f"PMID: {pmid if pmid is not None else 'unknown'}")
        lines.append(f"section: {section}")
        lines.append(f"original sentence: {sentence}")
        lines.append("")
    return "\n".join(lines).strip()


# ---- LLM 响应解析(带 fallback) ----

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_llm_json(raw_text: str | None) -> tuple[dict[str, Any] | None, str | None]:
    """LLM 原始文本 → dict。

    容忍 ```json 围栏、前后杂散文本、尾逗号。
    返回 (parsed, parse_error);解析失败 (None, error)。
    """
    if not raw_text or not raw_text.strip():
        return None, "empty_response"
    text = raw_text.strip()
    # 去掉 markdown 围栏
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text)
    block = _JSON_BLOCK_RE.search(text)
    candidate = block.group(0) if block else text
    try:
        parsed = json.loads(candidate)
        if not isinstance(parsed, dict):
            return None, "not_a_json_object"
        return parsed, None
    except json.JSONDecodeError:
        # 尾逗号修复重试
        fixed = re.sub(r",\s*([}\]])", r"\1", candidate)
        try:
            parsed = json.loads(fixed)
            if isinstance(parsed, dict):
                return parsed, "trailing_comma_fixed"
            return None, "not_a_json_object"
        except json.JSONDecodeError as exc:
            return None, f"json_decode_error:{exc.msg}"


def _clamp_confidence(value: Any) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return DEFAULT_CONFIDENCE
    return min(max(v, 0.0), 1.0)


def normalize_review(data: dict[str, Any] | None,
                     parse_error: str | None = None) -> dict[str, Any]:
    """字段校验 + 枚举归一 + 非法值 fallback(确定行为,可测试)。

    非法 decision → uncertain(保留不确定原则);非法 connection_type →
    unknown;非法 direction → unknown;非法 strength → low。
    """
    data = data or {}
    decision = data.get("decision")
    if decision not in DECISION_VALUES:
        decision = DEFAULT_DECISION
    connection_type = data.get("connection_type")
    if connection_type not in CONNECTION_TYPE_VALUES:
        connection_type = DEFAULT_CONNECTION_TYPE
    direction = data.get("direction")
    if direction not in DIRECTION_VALUES:
        direction = DEFAULT_DIRECTION
    strength = data.get("evidence_strength")
    if strength not in STRENGTH_VALUES:
        strength = DEFAULT_STRENGTH
    reasoning = data.get("reasoning")
    reasoning = str(reasoning).strip() if reasoning is not None else ""
    return {
        "decision": decision,
        "connection_type": connection_type,
        "direction": direction,
        "confidence": round(_clamp_confidence(data.get("confidence")), 3),
        "evidence_strength": strength,
        "reasoning": reasoning,
        "parse_error": parse_error,
    }


# ---- 单条审核(带重试) ----

async def review_one_candidate(
    ranking: dict,
    evidences: list[dict],
    *,
    provider_key: str = "deepseek",
    model: str | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_retries: int = MAX_RETRIES,
) -> dict:
    """对一条 ranking 执行 LLM 审核(重试 + fallback)。

    ranking: {id, source_region_id, target_region_id, source_name,
              target_name, paper_count}
    evidences: [{paper_title, pmid, section_name, sentence}] 按质量排序
    返回审核行 dict(含 raw_response_json/provenance_json/token_usage),
    LLM 不可用或解析失败 → decision=uncertain + error 记录(不抛异常)。
    """
    provider = get_llm_provider(provider_key)
    cfg = (get_deepseek_runtime_config() if provider_key == "deepseek"
           else get_kimi_runtime_config())
    resolved_model = model or getattr(cfg, "default_model", None) or \
        "deepseek-chat"

    system_prompt = SYSTEM_PROMPT
    user_prompt = build_user_prompt(
        ranking.get("source_name") or ranking["source_region_id"],
        ranking.get("target_name") or ranking["target_region_id"],
        evidences)

    last_error: str | None = None
    raw_text: str | None = None
    parsed: dict[str, Any] | None = None
    parse_err: str | None = None
    usage_dict: dict = {}
    finish_reason: str | None = None
    latency_ms = 0
    response_format: str | None = None

    for attempt in range(max_retries + 1):
        try:
            result = await provider.complete_text(
                model=resolved_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=True,
            )
        except Exception as exc:  # provider 级异常(超时/网络)
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < max_retries:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * (2 ** attempt))
            continue

        raw_text = result.raw_text
        usage_dict = result.usage.as_dict()
        finish_reason = result.finish_reason
        latency_ms = result.latency_ms
        response_format = result.response_format
        if not result.transport_ok or not raw_text:
            last_error = result.error or "transport_failed"
            if attempt < max_retries:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * (2 ** attempt))
            continue
        parsed, parse_err = parse_llm_json(raw_text)
        if parsed is None:
            last_error = parse_err
            if attempt < max_retries:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * (2 ** attempt))
            continue
        break

    normalized = normalize_review(parsed, parse_err if parsed is None else None)
    if parsed is not None and parse_err == "trailing_comma_fixed":
        normalized["parse_error"] = parse_err

    raw_response = {
        "raw_text": (raw_text or "")[:4000],
        "parsed": parsed,
        "parse_error": parse_err if parsed is None else normalized.get("parse_error"),
        "transport_ok": parsed is not None,
        "finish_reason": finish_reason,
        "latency_ms": latency_ms,
        "response_format": response_format,
        "error": last_error,
        "retries": max_retries,
    }
    provenance = {
        "ranking_id": str(ranking["id"]),
        "candidate_pair_ids": ranking.get("candidate_pair_ids", []),
        "prompt_version": PROMPT_VERSION,
        "prompt": {"system": system_prompt, "user": user_prompt},
        "evidence_refs": [
            {"paper_title": e.get("paper_title"),
             "pmid": e.get("pmid"),
             "section_name": e.get("section_name"),
             "sentence_snippet": (e.get("sentence") or "")[:200]}
            for e in evidences[:MAX_EVIDENCES_PER_PROMPT]],
        "llm": {"provider": provider_key, "model": resolved_model,
                "latency_ms": latency_ms},
        "trace_chain": ["ranking", "candidate_pair", "llm_review"],
    }
    return {
        "ranking_id": str(ranking["id"]),
        "source_region_id": str(ranking["source_region_id"]),
        "target_region_id": str(ranking["target_region_id"]),
        "decision": normalized["decision"],
        "connection_type": normalized["connection_type"],
        "direction": normalized["direction"],
        "confidence": normalized["confidence"],
        "evidence_strength": normalized["evidence_strength"],
        "reasoning": normalized["reasoning"],
        "model_name": resolved_model,
        "prompt_version": PROMPT_VERSION,
        "raw_response_json": raw_response,
        "provenance_json": provenance,
        "token_usage": usage_dict,
        "assertion_type": ASSERTION_TYPE,
        "source_type": SOURCE_TYPE,
        "generation_method": GENERATION_METHOD,
    }


async def review_candidates_batch(
    candidates: list[dict],
    *,
    provider_key: str = "deepseek",
    model: str | None = None,
    concurrency: int = 5,
) -> list[dict]:
    """批量审核(并发限流,逐条独立失败隔离)。"""
    semaphore = asyncio.Semaphore(concurrency)

    async def _guarded(ranking: dict) -> dict:
        async with semaphore:
            return await review_one_candidate(
                ranking, ranking.get("evidences", []),
                provider_key=provider_key, model=model)

    return await asyncio.gather(*(_guarded(c) for c in candidates))


# ---- 幂等 INSERT ----

INSERT_REVIEW_SQL = """\
INSERT INTO macro_candidate_connection_llm_reviews
    (ranking_id, source_region_id, target_region_id, decision,
     connection_type, direction, confidence, evidence_strength, reasoning,
     model_name, prompt_version, raw_response_json, provenance_json,
     token_usage, assertion_type, source_type, generation_method)
VALUES (:ranking_id, :source_region_id, :target_region_id, :decision,
        :connection_type, :direction, :confidence, :evidence_strength,
        :reasoning, :model_name, :prompt_version, :raw_response_json,
        :provenance_json, :token_usage, :assertion_type, :source_type,
        :generation_method)
ON CONFLICT (ranking_id) DO NOTHING
"""
