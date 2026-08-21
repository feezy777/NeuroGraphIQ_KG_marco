"""Schemas for parallel paper-evidence extraction runs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.ontology import PaperRef


class PaperEvidenceExtractionRunRequest(BaseModel):
    target_type: str
    target_id: uuid.UUID
    papers: list[PaperRef] = Field(min_length=1, max_length=20)
    only_oa: bool = False
    stop_after_strong_support: bool = False
    mode: Literal["function", "existence"] = "function"
    concurrency: int = Field(default=4, ge=1, le=6)


class PaperEvidenceExtractionStartResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: uuid.UUID
    status: str
    total_items: int
    requested_concurrency: int
    created_at: datetime


class PaperEvidenceExtractionItemDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    item_index: int
    pmid: str | None = None
    pmcid: str | None = None
    doi: str | None = None
    title: str | None = None
    paper_json: dict[str, Any] = Field(default_factory=dict)
    status: str
    progress_percent: int
    attempt_count: int
    result_json: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    stage_timings_json: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime


class PaperEvidenceExtractionRunDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    mode: Literal["function", "existence"]
    status: str
    total_items: int
    completed_items: int
    evidence_hit_items: int
    no_evidence_items: int
    failed_items: int
    requested_concurrency: int
    active_concurrency: int
    cancel_requested: bool
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    items: list[PaperEvidenceExtractionItemDetail] = Field(default_factory=list)
    progress_percent: float = Field(default=0.0, ge=0.0, le=100.0)
