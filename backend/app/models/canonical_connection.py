"""Canonical Connection ontology models (CN1.2-1).

Canonical Connection is the unified concept identity for the Connection
domain of the NeuroGraphIQ Semantic Core. Endpoints reference
``canonical_brain_regions`` (concept-neutral; laterality stays on the region
anchors); direction semantics are expressed by ``directionality_policy``
instead of duplicated reverse rows (no reverse_connection table, no
double-write). Source-side connection rows (``mirror_region_connections``)
are never modified — alignment to canonical concepts happens outside this
table in later CN phases.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CanonicalConnection(Base):
    """Canonical Connection concept (species-explicit, type-keyed).

    ``connection_code`` is the stable logical IRI (``ng:cn:*``) and is the
    identity; identity for dedup is ``(source_region_id, target_region_id,
    connection_type)`` (UNIQUE). Lifecycle follows the ontology pattern:
    proposed -> active -> deprecated, with a ``replaced_by_connection_id``
    merge chain. Self-loops are CHECK-rejected.
    """

    __tablename__ = "canonical_connections"
    __table_args__ = (
        UniqueConstraint(
            "source_region_id", "target_region_id", "connection_type",
            name="uq_canonical_connection",
        ),
        CheckConstraint(
            "source_region_id <> target_region_id",
            name="chk_canonical_connection_not_self",
        ),
        CheckConstraint(
            "connection_type IN ('structural','functional','projection','association','coactivation','uncertain')",
            name="chk_canonical_connection_type",
        ),
        CheckConstraint(
            "directionality_policy IN ('directed','bidirectional','undirected','unspecified')",
            name="chk_canonical_connection_directionality",
        ),
        CheckConstraint(
            "status IN ('proposed','active','deprecated')",
            name="chk_canonical_connection_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    source_region_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_brain_regions.id", ondelete="CASCADE"), nullable=False
    )
    target_region_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_brain_regions.id", ondelete="CASCADE"), nullable=False
    )
    connection_type: Mapped[str] = mapped_column(String(32), nullable=False)
    directionality_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="unspecified")
    species: Mapped[str] = mapped_column(String(16), nullable=False, default="human")
    granularity_level: Mapped[str] = mapped_column(String(64), nullable=False, default="clinical")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    source_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    evidence_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # Inference governance (20260902): assertion_type 事实/推理分层 + provenance metadata
    assertion_type: Mapped[str] = mapped_column(String(32), nullable=False, default="reported_fact")
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    generation_method: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    evidence_reference: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    replaced_by_connection_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_connections.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MirrorConnectionCanonicalGrounding(Base):
    """Mirror Connection → Canonical Connection grounding record (CN1).

    One row per mirror connection (UNIQUE): the endpoint canonical resolution
    outcome (source/target region + method), the standardized connection
    type / directionality policy (frozen rules), and the grounding status.
    Unresolved rows keep their failure reason so re-runs are idempotent and
    the unresolved report is traceable. The mirror row itself is never
    modified; the canonical side is only referenced, never created here.
    """

    __tablename__ = "mirror_connection_canonical_grounding"
    __table_args__ = (
        UniqueConstraint("mirror_connection_id", name="uq_grounding_mirror_connection"),
        CheckConstraint(
            "status IN ('grounded', 'unresolved')",
            name="chk_grounding_status",
        ),
        CheckConstraint(
            "source_resolution_method IN ('candidate_grounded','name_canonical_exact',"
            "'name_alias_exact','name_normalized_exact','unresolved')"
            " AND target_resolution_method IN ('candidate_grounded','name_canonical_exact',"
            "'name_alias_exact','name_normalized_exact','unresolved')",
            name="chk_grounding_method",
        ),
        CheckConstraint(
            "source_region_id IS NULL OR target_region_id IS NULL"
            " OR source_region_id <> target_region_id",
            name="chk_grounding_not_self",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mirror_connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mirror_region_connections.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    canonical_connection_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_connections.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_region_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_brain_regions.id", ondelete="SET NULL"), nullable=True
    )
    target_region_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_brain_regions.id", ondelete="SET NULL"), nullable=True
    )
    source_resolution_method: Mapped[str] = mapped_column(String(32), nullable=False, default="unresolved")
    target_resolution_method: Mapped[str] = mapped_column(String(32), nullable=False, default="unresolved")
    connection_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    directionality_policy: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="unresolved")
    unresolved_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
