"""Phase Q4 — Ontology Query LLM 解释层的固定 Prompt 模板。

设计原则（对齐规格）：
- LLM 只能读取 Structured Query Result，绝不自行查询数据库。
- 固定 system prompt 承载医学解释规则；user prompt 由「用户问题 + 结构化知识结果」拼装。
- 输出要求 JSON（answer/summary/key_points/confidence），由 provider 的 json_mode 兜底解析。
"""

from __future__ import annotations

import json
from typing import Any

SYSTEM_PROMPT = (
    "你是 NeuroGraphIQ 医学知识解释助手。你的任务：根据提供的结构化知识结果生成医学解释。\n"
    "规则：\n"
    "1. 不能添加结果中不存在的实体。\n"
    "2. 不能创造新的连接。\n"
    "3. 不能改变脑区关系。\n"
    "4. 所有结论必须来自 evidence。\n"
    "5. 如果信息不足，明确说明。\n"
    "回答使用中文，面向医学/科研用户，语气客观、克制，不做任何结果之外的推测。"
)

JSON_INSTRUCTION = (
    "请只输出一个 JSON 对象（不要输出任何额外文字），结构如下：\n"
    '{"answer": "完整医学解释（2-4 句，所有结论必须来自下方结构化结果）", '
    '"summary": "一句话摘要", '
    '"key_points": ["要点1", "要点2", "..."], '
    '"confidence": 0.0-1.0 之间的数字，表示你对照 evidence 回答的把握}'
)


def _compact_result(query: dict[str, Any], max_items: int = 50) -> dict[str, Any]:
    """把 OntologyQueryResponse 压缩为喂给 LLM 的紧凑结构（截断长结果控制 token）。"""
    results = []
    for item in query.get("results", [])[:max_items]:
        results.append(
            {
                "name": item.get("name"),
                "category": item.get("category"),
                "detail": item.get("detail") or {},
                "confidence": item.get("confidence"),
                "provenance": item.get("provenance"),
            }
        )
    entity = query.get("entity")
    compact: dict[str, Any] = {
        "intent": query.get("intent"),
        "entity": (
            {
                "name": entity.get("name"),
                "code": entity.get("code"),
            }
            if entity
            else None
        ),
        "result_count": len(query.get("results", [])),
        "results": results,
    }
    if query.get("results") and len(query["results"]) > max_items:
        compact["truncated"] = len(query["results"]) - max_items
    return compact


def build_user_prompt(question: str, structured_result: dict[str, Any]) -> str:
    """用户问题 + 结构化知识结果 → user prompt。

    structured_result 是 OntologyQueryResponse 的 dict 形态（可直接传
    ``handle_ontology_query`` 的返回值）。LLM 唯一可见的知识来源就是这里。
    """
    return (
        f"用户问题：{question}\n\n"
        "结构化知识结果（来自 NeuroGraphIQ 知识图谱查询，是唯一事实来源）：\n"
        f"{json.dumps(_compact_result(structured_result), ensure_ascii=False, indent=2, default=str)}\n\n"
        f"{JSON_INSTRUCTION}"
    )
