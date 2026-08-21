"""Ontology Query — 可控、可解释的知识图谱自然语言查询。

POST /api/ontology-query           {question} → {intent, entity, results, confidence, warnings, source_entities}
POST /api/ontology-query/explain   {question} → {question, query_result, explanation}
- Phase 1：纯规则分类 + 精确匹配，无 LLM、无写操作、复用 canonical service。
- Phase Q4：/explain 在结构化结果之上追加 LLM 医学解释；LLM 只能读取
  Structured Query Result，不自行查询数据库。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.ontology_query import (
    OntologyExplainRequest,
    OntologyExplainResponse,
    OntologyQueryRequest,
    OntologyQueryResponse,
)
from app.services.ontology_llm_service import generate_explanation
from app.services.ontology_query_service import handle_ontology_query

router = APIRouter(prefix="/api/ontology-query", tags=["Ontology Query"])


@router.post("", response_model=OntologyQueryResponse)
async def ontology_query(
    body: OntologyQueryRequest,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """自然语言图谱查询（Phase 1：脑区实体 × 5 种意图）。"""
    return await handle_ontology_query(session, body.question)


@router.post("/explain", response_model=OntologyExplainResponse)
async def ontology_query_explain(
    body: OntologyExplainRequest,
    session: AsyncSession = Depends(get_db),
) -> OntologyExplainResponse:
    """Phase Q4 — 结构化结果（Knowledge Graph Evidence）+ LLM 医学解释（AI Explanation）。

    流程：question → Ontology Query Core（唯一事实来源）→ Structured Query Result
    → LLM Explanation Service → Natural Language Answer。空结果/未解析走确定性
    回退文案，不调用 LLM。
    """
    query_result = await handle_ontology_query(session, body.question)
    query = OntologyQueryResponse.model_validate(query_result)
    explanation = await generate_explanation(session, query, body.question)
    return OntologyExplainResponse(
        question=body.question,
        query_result=query,
        explanation=explanation,
    )
