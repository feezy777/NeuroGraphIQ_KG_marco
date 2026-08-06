"""Ontology layer Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class VocabularyRead(BaseModel):
    id: uuid.UUID
    code: str
    vocab_type: str
    label_cn: str | None = None
    label_en: str | None = None
    description: str | None = None
    status: str = "active"
    seq: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class VocabularyCreateRequest(BaseModel):
    code: str
    vocab_type: str
    label_cn: str | None = None
    label_en: str | None = None
    description: str | None = None
    seq: int = 0


class VocabularyListResponse(BaseModel):
    items: list[VocabularyRead]
    total: int


class TermRead(BaseModel):
    id: uuid.UUID
    term_code: str
    canonical_term_en: str
    canonical_term_cn: str | None = None
    term_type: str = "function"
    category: str | None = None
    domain: str | None = None
    role: str | None = None
    effect_type: str | None = None
    description: str | None = None
    status: str = "proposed"
    created_by: str = "manual"
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TermCreateRequest(BaseModel):
    canonical_term_en: str
    canonical_term_cn: str | None = None
    term_type: str = "function"
    category: str | None = None
    domain: str | None = None
    role: str | None = None
    effect_type: str | None = None
    description: str | None = None
    created_by: str = "llm"


class TermListResponse(BaseModel):
    items: list[TermRead]
    total: int


class TermMergeRequest(BaseModel):
    target_id: uuid.UUID


class GroundingRead(BaseModel):
    id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    term_id: uuid.UUID | None = None
    grounded_by: str
    confidence: float | None = None
    created_by: str | None = None
    grounded_at: datetime

    model_config = {"from_attributes": True}


class GroundingRunRequest(BaseModel):
    target_type: str
    limit: int = Field(default=500, ge=1, le=5000)


class GroundingListResponse(BaseModel):
    items: list[GroundingRead]
    total: int


class GroundingRunResponse(BaseModel):
    target_type: str
    processed: int
    grounded: int
    ungrounded: int


class CoverageItem(BaseModel):
    key: str
    label: str
    total: int
    grounded: int
    ungrounded: int
    by_method: dict[str, int] = Field(default_factory=dict)


class CoverageResponse(BaseModel):
    items: list[CoverageItem]
    total_terms: int
    active_terms: int
    proposed_terms: int


class PanoramaItem(BaseModel):
    term_key: str
    term_label: str
    count: int
    sample_ids: list[uuid.UUID] = Field(default_factory=list)


class PanoramaResponse(BaseModel):
    target_type: str
    total_distinct: int
    items: list[PanoramaItem]
