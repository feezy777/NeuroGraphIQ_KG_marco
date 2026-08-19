# -*- coding: utf-8 -*-
"""build_search_query negative 变体:否定连接词注入。"""

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

from app.services import evidence_target_adapter as eta


def _run(coro):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_negative_query_contains_negation_terms():
    dto = {
        "source_region": "BLA", "target_region": "IL",
        "canonical_terms": [], "function_terms": [], "function_synonyms": [],
        "display_name": "BLA → IL",
    }
    with patch.object(eta, "build_target_dto", AsyncMock(return_value=dto)):
        q = _run(eta.build_search_query(None, "connection", uuid.uuid4(), mode="existence", negative=True))
    assert "no projection" in q or "does not connect" in q or "absence of connection" in q
    assert "ABSTRACT:\"BLA\"" in q
    assert "ABSTRACT:\"IL\"" in q


def test_positive_query_has_no_negation_terms():
    dto = {
        "source_region": "BLA", "target_region": "IL",
        "canonical_terms": [], "function_terms": [], "function_synonyms": [],
        "display_name": "BLA → IL",
    }
    with patch.object(eta, "build_target_dto", AsyncMock(return_value=dto)):
        q = _run(eta.build_search_query(None, "connection", uuid.uuid4(), mode="existence"))
    assert "no projection" not in q


def test_connection_claim_components_include_function_optional():
    """连接主张:功能为可选组件(required=False),不影响存在性 coverage。"""
    dto = {
        "source_region": "Hippocampus",
        "target_region": "Prefrontal cortex",
        "relation": "projects to",
        "directionality": "unidirectional",
        "canonical_terms": ["memory consolidation"],
    }
    comps = eta._build_claim_components("connection", dto)
    types = [c["component_type"] for c in comps]
    assert types == ["source_region", "target_region", "relation", "direction", "function"]
    fn = next(c for c in comps if c["component_type"] == "function")
    assert fn["required"] is False
    assert "memory consolidation" in fn["statement"]


def test_connection_claim_components_no_function_when_no_canonical_term():
    """无功能词时 connection 不产生 function 组件。"""
    dto = {
        "source_region": "BLA",
        "target_region": "IL",
        "relation": "projects to",
        "directionality": "",
        "canonical_terms": [],
    }
    comps = eta._build_claim_components("connection", dto)
    assert [c["component_type"] for c in comps] == ["source_region", "target_region", "relation"]
