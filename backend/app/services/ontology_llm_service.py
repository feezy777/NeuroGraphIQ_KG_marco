"""Phase Q4 — Ontology Query LLM 解释层服务。

管线（对齐规格）：用户问题 → Ontology Query Core（已有，唯一事实来源）→
Structured Query Result → 本服务（LLM Explanation）→ Natural Language Answer。

安全边界：
- 空结果 / unresolved / 配置禁用 → **确定性回退文案，不调用 LLM**。
- LLM 只接收 compact 结构化结果（ontology_query_prompt），没有数据库访问能力。
- response_validator 用 canonical 脑区名称集扫描回答中的名称：出现不在
  evidence 中的已知脑区 → hallucination_warning（标记但不阻断展示）。
- evidence_entities 由结构化结果确定性导出，不采信 LLM 自报。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical_region import CanonicalBrainRegion
from app.models.canonical_region_alias import CanonicalRegionAlias
from app.prompts.ontology_query_prompt import SYSTEM_PROMPT, build_user_prompt
from app.schemas.ontology_query import (
    OntologyLLMResponse,
    OntologyQueryResponse,
)
from app.services.llm_providers.base import LlmProviderResponse
from app.services.llm_providers.factory import get_llm_provider
from app.services.settings_service import get_ontology_query_runtime_config

logger = logging.getLogger(__name__)

_NO_INFO_ANSWER = "当前知识图谱暂无相关信息。"
_NO_CONNECTION_ANSWER = "当前知识图谱未发现相关连接。"
_LLM_UNAVAILABLE = "LLM 解释暂不可用，以下为知识图谱原始结果摘要。"


def _detail_region_names(detail: dict[str, Any]) -> list[str]:
    """从 detail 中提取合法的证据脑区名（如连接对端 endpoint_region）。

    回答中引用「连接海马的脑区」等对端区域名完全合法，若不进 evidence 会被
    hallucination validator 误报。目前覆盖 connection.endpoint_region 与
    通用 region 字段；其他嵌套结构暂不展开（宁缺毋滥，不把枚举值当证据名）。
    """
    names: list[str] = []
    for key in ("endpoint_region", "region"):
        region = detail.get(key)
        if not isinstance(region, dict):
            continue
        for field in ("canonical_name_cn", "canonical_name_en", "region_code", "name"):
            val = region.get(field)
            if isinstance(val, str) and val.strip():
                names.append(val.strip())
    return names


def _evidence_names(query: OntologyQueryResponse) -> list[str]:
    """从结构化结果确定性导出 evidence 名称集合（去重保序）。"""
    names: list[str] = []
    if query.entity:
        for name in (query.entity.name, query.entity.code):
            if name:
                names.append(name)
    for item in query.results:
        for name in (item.name, item.code):
            if name and name not in names:
                names.append(name)
        detail = item.detail or {}
        for name in _detail_region_names(detail):
            if name not in names:
                names.append(name)
    return names


def _key_points_from_results(query: OntologyQueryResponse, limit: int = 10) -> list[str]:
    points: list[str] = []
    for item in query.results:
        if len(points) >= limit:
            break
        label = f"{item.name}（{item.category}）" if item.category != "function" else item.name
        if label not in points:
            points.append(label)
    return points


def build_fallback_explanation(query: OntologyQueryResponse, question: str) -> OntologyLLMResponse:
    """确定性回退（不调用 LLM）。

    - unresolved / 未解析到实体 → 「当前知识图谱暂无相关信息。」
    - 连接意图空结果 → 「当前知识图谱未发现相关连接。」
    - 其他空结果 → 「当前知识图谱暂无相关信息。」
    - 有结果但 LLM 不可用 → 原始结果摘要。
    """
    if query.entity is None or query.intent == "unresolved":
        answer = f"未解析到与「{question}」相关的图谱实体。{_NO_INFO_ANSWER}"
        return OntologyLLMResponse(
            answer=answer,
            summary=_NO_INFO_ANSWER,
            key_points=[],
            evidence_entities=[],
            confidence=0.0,
        )
    if not query.results:
        if query.intent == "region_connections":
            answer = _NO_CONNECTION_ANSWER
        else:
            answer = _NO_INFO_ANSWER
        return OntologyLLMResponse(
            answer=answer,
            summary=answer,
            key_points=[],
            evidence_entities=_evidence_names(query),
            confidence=query.confidence,
        )
    # 有结果但 LLM 不可用：给原始摘要，明确不是语言总结
    points = _key_points_from_results(query)
    answer = (
        f"{_LLM_UNAVAILABLE}{query.entity.name} 当前关联 {len(query.results)} 条结果，"
        f"主要条目：{'、'.join(points)}。"
    )
    return OntologyLLMResponse(
        answer=answer,
        summary=f"{query.entity.name} 关联 {len(query.results)} 条结果",
        key_points=points,
        evidence_entities=_evidence_names(query),
        confidence=query.confidence,
    )


def _is_substring_of_evidence(name: str, evidence_names: list[str]) -> bool:
    """排除「name 是某个 evidence 名称的子串」的候选（如 海马 ⊂ Q15测试海马）。

    中文无空格分词，精确边界检测不可靠；用「名字出现在回答文本中 + 不是
    evidence 名称子串 + 本身是图谱已知脑区名」作为幻觉启发式，宁可漏报不误报。
    """
    for evidence in evidence_names:
        if evidence and name in evidence:
            return True
    return False


async def validate_hallucinated_entities(
    session: AsyncSession,
    texts: list[str],
    evidence_names: list[str],
) -> list[str]:
    """response_validator：扫描回答文本中出现的 canonical 脑区名称。

    仅在 LLM 回答中出现、且不在 evidence 中的**已知脑区名称**会被标记为幻觉
    （hallucination_warning）。未知词不会误报——validator 只认知识图谱自己的
    脑区名词表（canonical 中英文名 + 别名）；名称是某 evidence 名称子串时
    跳过（如「海马」⊂「Q15测试海马」）。**证据脑区自身的别名视为证据**
    （如 内嗅皮层 是 内嗅 的别名，回答中引用对端别名不误报）。标记只提示、不阻断展示。
    """
    known: set[str] = set()
    rows = await session.execute(
        select(
            CanonicalBrainRegion.canonical_name_cn,
            CanonicalBrainRegion.canonical_name_en,
        ).where(CanonicalBrainRegion.status == "active")
    )
    for cn, en in rows:
        if cn:
            known.add(cn)
        if en:
            known.add(en)
    alias_rows = await session.execute(
        select(CanonicalRegionAlias.alias).join(
            CanonicalBrainRegion,
            CanonicalBrainRegion.id == CanonicalRegionAlias.region_id,
        ).where(CanonicalBrainRegion.status == "active")
    )
    for (alias,) in alias_rows:
        known.add(alias)

    evidence_set = set(evidence_names)
    # 证据名（region cn/en/code）命中的脑区，其别名也属于证据（对端脑区别名引用合法）
    evidence_alias_rows = await session.execute(
        select(CanonicalRegionAlias.alias).join(
            CanonicalBrainRegion,
            CanonicalBrainRegion.id == CanonicalRegionAlias.region_id,
        ).where(
            CanonicalBrainRegion.status == "active",
            or_(
                CanonicalBrainRegion.canonical_name_cn.in_(evidence_names),
                CanonicalBrainRegion.canonical_name_en.in_(evidence_names),
                CanonicalBrainRegion.region_code.in_(evidence_names),
            ),
        )
    )
    for (alias,) in evidence_alias_rows:
        evidence_set.add(alias)

    joined_text = "\n".join(texts)
    flagged: list[str] = []
    for name in sorted(known, key=len, reverse=True):
        if not name or len(name) < 2:
            continue
        if name in evidence_set:
            continue
        if _is_substring_of_evidence(name, evidence_names):
            continue
        if name in joined_text:
            flagged.append(name)
    return flagged


async def generate_explanation(
    session: AsyncSession,
    query: OntologyQueryResponse,
    question: str,
) -> OntologyLLMResponse:
    """Structured Query Result → Natural Language Answer。

    返回的 evidence_entities / key_points 缺失时由 LLM JSON 提供，但
    evidence_entities 一律以结构化结果为准（见模块 docstring）。
    """
    # 空结果 / 未解析 → 确定性回退文案，绝不调用 LLM（规格 3 / 问题 4）
    if query.entity is None or query.intent == "unresolved" or not query.results:
        return build_fallback_explanation(query, question)

    config = get_ontology_query_runtime_config()
    if not config.enabled:
        return build_fallback_explanation(query, question)

    evidence = _evidence_names(query)
    try:
        response: LlmProviderResponse = await get_llm_provider(config.provider).complete_json(
            model=config.model,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_user_prompt(question, query.model_dump()),
            temperature=config.temperature,
            max_tokens=4000,
            timeout_seconds=90,
        )
        parsed = response.parsed_json or {}
    except Exception as exc:  # provider 网络/解析失败 → 确定性回退，不阻断
        logger.warning("ontology_llm provider call failed, using fallback: %s", exc)
        return build_fallback_explanation(query, question)

    answer = str(parsed.get("answer") or "").strip()
    if not answer:
        logger.warning("ontology_llm returned empty answer, using fallback")
        return build_fallback_explanation(query, question)

    raw_points = parsed.get("key_points")
    key_points = [str(p) for p in raw_points if isinstance(raw_points, list) and str(p).strip()]
    if not key_points:
        key_points = _key_points_from_results(query)

    summary = str(parsed.get("summary") or "").strip() or key_points[0] if key_points else ""
    confidence = parsed.get("confidence")
    if not isinstance(confidence, (int, float)) or not (0.0 <= float(confidence) <= 1.0):
        confidence = query.confidence

    hallucinated = await validate_hallucinated_entities(
        session, [answer, summary, *key_points], evidence
    )
    return OntologyLLMResponse(
        answer=answer,
        summary=summary,
        key_points=key_points,
        evidence_entities=evidence,
        confidence=round(float(confidence), 4),
        hallucination_warning=hallucinated,
    )
