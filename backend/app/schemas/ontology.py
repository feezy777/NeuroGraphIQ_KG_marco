"""Ontology layer Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

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


class TermSynonymCreateRequest(BaseModel):
    synonym_text: str
    lang: str = "en"
    match_type: str = "synonym"


class BatchActivateRequest(BaseModel):
    term_ids: list[uuid.UUID]
    reason: str | None = None


class ManualGroundingRequest(BaseModel):
    target_type: str
    target_id: uuid.UUID
    term_id: uuid.UUID
    reason: str | None = None


class BatchGroundingByTextRequest(BaseModel):
    target_type: str
    term_text: str
    term_id: uuid.UUID


class GroundingSkipRequest(BaseModel):
    target_type: str
    target_id: uuid.UUID
    reason: str


class EnumReplaceRequest(BaseModel):
    field: str
    old_value: str
    new_code: str
    reason: str | None = None


class AlignmentReviewRequest(BaseModel):
    action: str
    reason: str | None = None
    external_iri: str | None = None
    external_label: str | None = None


class PaperSearchRequest(BaseModel):
    target_type: str
    target_id: uuid.UUID
    limit: int = Field(default=5, ge=1, le=20)
    mode: str = "function"
    query_override: str | None = None


class EvidenceAttachRequest(BaseModel):
    target_type: str
    target_id: uuid.UUID
    pmid: str
    excerpt: str
    direction: str = "supports"
    mode: str = "function"
    suggested_confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class EvidenceExtractRequest(BaseModel):
    target_type: str
    target_id: uuid.UUID
    pmid: str
    title: str
    abstract: str


class EvidencePassageItem(BaseModel):
    source_scope: Literal["abstract", "fulltext"] = "abstract"
    section_title: str | None = None
    paragraph_index: int | None = None
    paragraph_id: str | None = None
    passage: str
    translation_zh: str | None = None
    direction: Literal["supports", "partial", "contradicts", "not_found"]
    evidence_level: Literal["direct", "indirect", "interpretive", "background"] = "indirect"
    reason: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    semantic_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_locator: str | None = None
    source_verified: bool = False
    source_verification_method: str | None = None
    supported_components: list[str] = Field(default_factory=list, max_length=12)


class EvidenceExtractResponse(BaseModel):
    paper_id: uuid.UUID | None = None
    paper: dict | None = None
    claim: dict | None = None
    claim_components: list[dict] | None = None
    coverage_summary: dict | None = None
    retrieval_summary: dict | None = None
    overall_direction: Literal["supports", "partial", "contradicts", "mixed", "not_found"]
    paper_relevance: float
    assessment: str | None = None
    source_type: Literal["abstract", "fulltext", "none"]
    passages: list[EvidencePassageItem]


class EvidenceAttachRequest(BaseModel):
    target_type: str
    target_id: uuid.UUID
    pmid: str
    direction: Literal["supports", "partial", "contradicts", "mixed", "not_found"]
    evidence_level: Literal["direct", "indirect", "interpretive", "background"] = "indirect"
    model_direction: Literal["supports", "partial", "contradicts", "mixed", "not_found"] | None = None
    model_assessment: str | None = None
    reviewer_note: str | None = None
    reviewer_confidence: float = Field(ge=0.0, le=1.0)
    passages: list[EvidencePassageItem]


class AttachPreviewRequest(BaseModel):
    target_type: str
    target_id: uuid.UUID
    pmid: str
    direction: Literal["supports", "partial", "contradicts", "mixed", "not_found"]
    reviewer_confidence: float = Field(ge=0.0, le=1.0)
    passages: list[EvidencePassageItem]


class AttachPreviewResponse(BaseModel):
    target_type: str
    target_id: uuid.UUID
    current_confidence: float | None
    direction: str
    reviewer_confidence: float
    final_confidence: float | None
    cap: float | None
    selected_passage_count: int
    duplicate_passage_count: int
    evidence_text_preview: str
    allow: bool
    block_reasons: list[str]


class EvidenceRollbackRequest(BaseModel):
    reason: str


class BatchTaskCreateRequest(BaseModel):
    target_type: str
    scope: str = "all"
    mode: str = "function"
    max_papers_per_object: int = Field(default=3, ge=1, le=10)
    limit: int = Field(default=500, ge=1, le=5000)
    start_paused: bool = False
    name: str | None = None
    granularity_level: str | None = None
    only_oa: bool = False
    confidence_lt: float | None = Field(default=None, ge=0.0, le=1.0)
    stop_after_strong_support: bool = False
    target_ids: list[str] | None = None
    filter_snapshot: dict | None = None


class PassageSelectionRequest(BaseModel):
    paper_passage_id: uuid.UUID
    selected_text: str = Field(min_length=1, max_length=4000)


class TaskItemDraftRequest(BaseModel):
    draft: dict
    revision: int = 0


class EvidenceAuditRequest(BaseModel):
    action_type: str = Field(min_length=1, max_length=64)
    entity_type: str = Field(default="evidence", max_length=64)
    entity_id: uuid.UUID
    before_data: dict | None = None
    after_data: dict | None = None
    reason: str | None = None


class ReviewResolveRequest(BaseModel):
    note: str = Field(default="", max_length=2000)


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


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
