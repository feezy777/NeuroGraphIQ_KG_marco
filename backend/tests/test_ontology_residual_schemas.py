"""DeepSeek residual alignment schema tests (no network, no DB)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.services.ontology_residual_schemas import (
    ResidualBatchOutput,
    ResidualItemResult,
    ResidualTermItem,
)


def test_residual_term_item_valid():
    item = ResidualTermItem(term="working memory", canonical_term="memory", confidence=0.95)
    assert item.confidence == 0.95


def test_residual_term_item_rejects_bad_confidence():
    with pytest.raises(ValidationError):
        ResidualTermItem(term="x", canonical_term="y", confidence=2.0)


def test_residual_term_item_rejects_empty_canonical():
    with pytest.raises(ValidationError):
        ResidualTermItem(term="x", canonical_term="", confidence=0.9)


def test_residual_batch_output_valid():
    batch = ResidualBatchOutput(
        items=[
            {"term": "working memory", "canonical_term": "memory", "confidence": 0.95},
            {"term": "attention", "canonical_term": "attention", "confidence": 0.9},
        ]
    )
    assert len(batch.items) == 2


def test_residual_item_result_closed_status():
    with pytest.raises(ValidationError):
        ResidualItemResult(term="x", status="not_a_status")
    assert ResidualItemResult(term="x", status="mapped_active").status == "mapped_active"


def test_parse_with_fallback_array_and_fence():
    from scripts.llm_residual_grounding import _parse_with_fallback

    raw = '```json\n[{"term": "a", "canonical_term": "b", "confidence": 0.9}]\n```'
    out = _parse_with_fallback(raw)
    assert out.items[0].canonical_term == "b"
