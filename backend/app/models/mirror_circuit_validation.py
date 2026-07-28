"""Mirror circuit validation ORM models."""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any, Optional
from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class MirrorCircuitValidationRun(Base):
    __tablename__ = "mirror_circuit_validation_runs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    granularity_level: Mapped[str] = mapped_column(String(32), nullable=False)
    source_atlas: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    target_types: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    scope_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    rule_validation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    rule_total_count: Mapped[int] = mapped_column(Integer, default=0)
    rule_passed_count: Mapped[int] = mapped_column(Integer, default=0)
    rule_failed_count: Mapped[int] = mapped_column(Integer, default=0)
    rule_warning_count: Mapped[int] = mapped_column(Integer, default=0)
    rule_blocked_count: Mapped[int] = mapped_column(Integer, default=0)
    rule_hard_failure_count: Mapped[int] = mapped_column(Integer, default=0)
    dual_review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    dual_review_total_count: Mapped[int] = mapped_column(Integer, default=0)
    dual_review_agreement_count: Mapped[int] = mapped_column(Integer, default=0)
    dual_review_conflict_count: Mapped[int] = mapped_column(Integer, default=0)
    dual_review_rejection_count: Mapped[int] = mapped_column(Integer, default=0)
    dual_review_uncertain_count: Mapped[int] = mapped_column(Integer, default=0)
    dual_review_low_evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    adjudication_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    reviewer_a_provider: Mapped[str] = mapped_column(String(64), nullable=False, default="deepseek")
    reviewer_a_model: Mapped[str] = mapped_column(String(128), nullable=False, default="deepseek-chat")
    reviewer_b_provider: Mapped[str] = mapped_column(String(64), nullable=False, default="kimi")
    reviewer_b_model: Mapped[str] = mapped_column(String(128), nullable=False, default="kimi")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class MirrorCircuitValidationResult(Base):
    __tablename__ = "mirror_circuit_validation_results"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    object_label: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rule_validation_result_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    rule_overall_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    rule_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewer_a_decision: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    reviewer_a_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reviewer_a_payload_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    reviewer_b_decision: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    reviewer_b_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reviewer_b_payload_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    adjudication_status: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    adjudication_confidence_diff: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    adjudication_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recommended_review_priority: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    mirror_review_record_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    deepseek_diagnosis_json: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
