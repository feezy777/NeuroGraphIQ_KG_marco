"""Paper evidence backend tests: source verification, rules, schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.services.confidence_rules import PARTIAL_CAP, SUPPORT_CAP, compute_adjustment
from app.services.ontology_residual_schemas import PaperMultiPassageExtraction
from app.services.paper_evidence_service import (
    exact_passage_match,
    locate_passage,
    normalize_for_match,
    normalized_passage_match,
    passage_hash,
    verify_passage_against_source,
)

SOURCE = (
    "The hippocampus is critical for memory consolidation.\n\n"
    "We found hippocampal engagement during spatial navigation tasks.\n\n"
    "These results support the role of the hippocampus in memory."
)


def test_normalize_whitespace_and_unicode():
    assert normalize_for_match("Memory\u00a0Consolidation\n\nTask") == "memory consolidation task"
    assert normalize_for_match("Hippocampus \u2014 memory") == "hippocampus - memory"


def test_exact_and_normalized_match():
    assert exact_passage_match("The hippocampus is critical for memory consolidation.", SOURCE)
    assert not exact_passage_match("Hippocampus is critical", SOURCE)
    assert normalized_passage_match("The  hippocampus\nis critical for memory consolidation.", SOURCE)


def test_verify_rejects_fabricated_passage():
    ok, method = verify_passage_against_source(
        "The hippocampus encodes all episodic memories in the prefrontal cortex.", SOURCE
    )
    assert ok is False
    assert method is None


def test_locate_paragraph():
    idx, locator = locate_passage("We found hippocampal engagement during spatial navigation tasks.", SOURCE)
    assert idx == 1
    assert locator == "paragraph:1"


def test_passage_hash_stable_and_sensitive_to_text():
    assert passage_hash("Memory consolidation") == passage_hash("  Memory   consolidation ")
    assert passage_hash("Memory consolidation") != passage_hash("Memory consolidation process")


def test_support_cap_085():
    r = compute_adjustment(direction="supports", current_confidence=0.2, reviewer_confidence=0.99)
    assert r.apply is True
    assert r.final_confidence == SUPPORT_CAP
    assert r.adjustment_status == "applied"


def test_partial_cap_075():
    r = compute_adjustment(direction="partial", current_confidence=0.1, reviewer_confidence=0.9)
    assert r.final_confidence == PARTIAL_CAP


def test_contradict_no_auto_change():
    r = compute_adjustment(direction="contradicts", current_confidence=0.4, reviewer_confidence=0.8)
    assert r.apply is False
    assert r.adjustment_status == "pending"


def test_not_found_rejected():
    with pytest.raises(ValueError):
        compute_adjustment(direction="not_found", current_confidence=0.4, reviewer_confidence=0.8)


def test_multi_passage_schema_valid():
    payload = {
        "overall_direction": "supports",
        "paper_relevance": "Study directly supports the claim.",
        "passages": [
            {"passage": "The hippocampus is critical for memory consolidation.", "direction": "supports", "reason": "Direct statement", "confidence": 0.9}
        ],
    }
    model = PaperMultiPassageExtraction.model_validate(payload)
    assert len(model.passages) == 1


def test_multi_passage_schema_rejects_bad_direction():
    payload = {
        "overall_direction": "supports",
        "paper_relevance": "x",
        "passages": [{"passage": "a", "direction": "maybe", "reason": "r", "confidence": 0.5}],
    }
    with pytest.raises(ValidationError):
        PaperMultiPassageExtraction.model_validate(payload)
