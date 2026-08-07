"""Pydantic schemas for DeepSeek residual term alignment (closed-set enums)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ParseStatus = Literal["ok", "parse_error", "schema_error", "provider_error"]
ItemStatus = Literal[
    "mapped_active",
    "mapped_proposed",
    "created_proposed",
    "low_confidence",
    "invalid",
    "failed",
]


class ResidualTermItem(BaseModel):
    """One LLM suggestion; strict validation with closed-set rules."""

    term: str = Field(min_length=1, max_length=512)
    canonical_term: str = Field(min_length=1, max_length=512)
    confidence: float = Field(ge=0.0, le=1.0)


class ResidualBatchOutput(BaseModel):
    """Full model output envelope: {"items": [...]}."""

    items: list[ResidualTermItem]


class ResidualItemResult(BaseModel):
    """Post-processed per-item result with closed-set status."""

    term: str
    canonical_term: str = ""
    confidence: float = 0.0
    status: ItemStatus = "invalid"
    detail: str | None = None


class ResidualBatchRecord(BaseModel):
    """Per-batch metadata retained for audit/debugging."""

    target_type: str
    model: str
    prompt_version: str
    raw_response: str
    parse_status: ParseStatus
    retry_count: int
    items: list[ResidualItemResult]


class PaperPassageExtraction(BaseModel):
    """LLM extraction of the paper passage relevant to a KG object."""

    direction: Literal["supports", "partial", "contradicts", "not_found"]
    passage: str = Field(min_length=1, max_length=2000)
    reason: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0.0, le=1.0)
    paragraph_id: str | None = Field(default=None, max_length=128)
    section: str | None = Field(default=None, max_length=256)
    evidence_level: Literal["direct", "indirect", "interpretive", "background"] = "indirect"
    semantic_confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class PaperMultiPassageExtraction(BaseModel):
    overall_direction: Literal["supports", "partial", "contradicts", "not_found"]
    paper_relevance: float = Field(ge=0.0, le=1.0)
    assessment: str = Field(default="", max_length=1000)
    passages: list[PaperPassageExtraction] = Field(default_factory=list, max_length=10)
