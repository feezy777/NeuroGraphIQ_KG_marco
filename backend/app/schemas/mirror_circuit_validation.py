"""Mirror circuit validation request/response schemas."""
from __future__ import annotations
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


# ── Circuit Correction Schemas ────────────────────────────────────────────


class CorrectionRead(BaseModel):
    """A single proposed field-level correction from DeepSeek diagnosis."""
    id: str
    circuit_id: str
    rule_code: str
    field_path: str
    original_value: Optional[Any] = None
    suggested_value: Optional[Any] = None
    approved_value: Optional[Any] = None
    correction_type: str = "metadata"
    repairability: str = "manual_required"
    approval_status: str = "proposed"
    deterministic_validation_status: str = "pending"
    suggestion_source: str = "deepseek"
    suggestion_confidence: Optional[float] = None
    authoritative_source: Optional[str] = None
    revalidation_status: str = "not_started"
    created_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class BlockerAnalysisRequest(BaseModel):
    """Request to analyze blocked circuits with DeepSeek."""
    circuit_ids: list[str] = Field(default_factory=list)
    force_refresh: bool = False


class BlockerAnalysisResponse(BaseModel):
    """Per-circuit diagnosis response from DeepSeek."""
    circuit_id: str
    circuit_name: str
    status: str
    overall_repairability: str = "manual_required"
    rule_diagnostics: list[dict] = Field(default_factory=list)
    suggested_changes: list[dict] = Field(default_factory=list)
    revalidation_recommended: bool = True
    reextraction_recommended: bool = False
    rejection_recommended: bool = False


class CircuitValidationCreateRequest(BaseModel):
    granularity_level: str
    source_atlas: Optional[str] = None
    target_types: list[str] = Field(default_factory=list)
    circuit_ids: list[str] = Field(default_factory=list)
    step_ids: list[str] = Field(default_factory=list)
    batch_ids: list[str] = Field(default_factory=list)
    reviewer_a_provider: str = "deepseek"
    reviewer_a_model: str = "deepseek-chat"
    reviewer_b_provider: str = "kimi"
    reviewer_b_model: str = "kimi"
    dry_run: bool = False
    max_objects: Optional[int] = None


class CircuitValidationRunRead(BaseModel):
    id: str
    granularity_level: str
    status: str
    rule_validation_status: str
    dual_review_status: str
    adjudication_status: str
    rule_total_count: int = 0
    rule_passed_count: int = 0
    rule_failed_count: int = 0
    rule_blocked_count: int = 0
    dual_review_agreement_count: int = 0
    dual_review_conflict_count: int = 0
    dual_review_rejection_count: int = 0
    reviewer_a_provider: str
    reviewer_b_provider: str
    dry_run: bool = False
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class CircuitValidationResultRead(BaseModel):
    id: str
    run_id: str
    target_type: str
    target_id: str
    object_label: Optional[str] = None
    rule_overall_status: Optional[str] = None
    rule_blocked: bool = False
    rule_validation_result_json: list[dict] = Field(default_factory=list)
    reviewer_a_decision: Optional[str] = None
    reviewer_a_confidence: Optional[float] = None
    reviewer_a_payload_json: Optional[dict] = None
    reviewer_b_decision: Optional[str] = None
    reviewer_b_confidence: Optional[float] = None
    reviewer_b_payload_json: Optional[dict] = None
    adjudication_status: Optional[str] = None
    adjudication_confidence_diff: Optional[float] = None
    adjudication_summary: Optional[str] = None
    recommended_review_priority: Optional[str] = None
    created_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class CircuitValidationRunDetail(CircuitValidationRunRead):
    results: list[CircuitValidationResultRead] = Field(default_factory=list)


class CandidateProgressItem(BaseModel):
    circuit_id: str
    circuit_name: str = ""
    path_summary: str = ""
    completed_rule_count: int = 0
    enabled_rule_count: int = 0
    pass_count: int = 0
    warning_count: int = 0
    hard_fail_count: int = 0
    status: str = "pending"
    current_rule_code: str = ""
    eligible_for_dual_review: bool = False
    error_message: Optional[str] = None
    blocked_reasons: list[dict] = Field(default_factory=list)
    deepseek_diagnosis: list[dict] = Field(default_factory=list)


class CircuitValidationProgressResponse(BaseModel):
    run_id: str
    status: str
    phase: str
    # Legacy fields (kept for backward compat)
    progress_percent: float = 0.0
    rule_total: int = 0
    rule_done: int = 0
    dual_total: int = 0
    dual_done: int = 0
    adjudication_done: bool = False
    # Enriched progress fields
    selected_candidate_count: int = 0
    completed_candidate_count: int = 0
    enabled_rule_count: int = 0
    expected_rule_execution_count: int = 0
    completed_rule_execution_count: int = 0
    pass_count: int = 0
    warning_count: int = 0
    hard_fail_count: int = 0
    eligible_for_dual_review_count: int = 0
    blocked_candidate_count: int = 0
    failed_candidate_count: int = 0
    started_at: Optional[str] = None
    elapsed_seconds: float = 0.0
    candidate_progress: list[CandidateProgressItem] = Field(default_factory=list)
