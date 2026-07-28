"""Mirror circuit correction overlay ORM model.

All corrections write to this separate overlay table. DeepSeek may ONLY
propose corrections here. Direct source data is NEVER modified.
Human approval required before applying.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Float, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MirrorCircuitCorrection(Base):
    """Overlay table for proposed circuit corrections.

    Each row represents a single atomic field-level correction proposed
    by DeepSeek diagnosis and pending human approval.
    """

    __tablename__ = "mirror_circuit_corrections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    circuit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True,
    )
    validation_result_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    rule_code: Mapped[str] = mapped_column(Text, nullable=False)
    field_path: Mapped[str] = mapped_column(Text, nullable=False)
    original_value: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True,
    )
    suggested_value: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True,
    )
    approved_value: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True,
    )
    correction_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="metadata",
    )
    repairability: Mapped[str] = mapped_column(
        String(32), nullable=False, default="manual_required",
    )
    suggestion_source: Mapped[str] = mapped_column(
        String(32), default="deepseek",
    )
    suggestion_confidence: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True,
    )
    authoritative_source: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )
    deterministic_validation_status: Mapped[str] = mapped_column(
        String(32), default="pending",
    )
    deterministic_validation_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )
    approval_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="proposed",
    )
    approved_by: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    approval_reason: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )
    revalidation_status: Mapped[str] = mapped_column(
        String(32), default="not_started",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
