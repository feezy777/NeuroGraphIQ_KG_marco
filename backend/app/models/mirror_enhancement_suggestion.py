"""Mirror enhancement suggestion ORM model — Tier 2 LLM content proposals."""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any, Optional
from sqlalchemy import DateTime, Float, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class MirrorEnhancementSuggestion(Base):
    __tablename__ = "mirror_enhancement_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    circuit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True,
    )
    validation_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    field_path: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_value: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True,
    )
    original_value: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True,
    )
    suggestion_type: Mapped[str] = mapped_column(
        String(64), nullable=False,
    )
    suggestion_source: Mapped[str] = mapped_column(
        String(32), default="deepseek",
    )
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    approval_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="proposed",
    )
    approved_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
