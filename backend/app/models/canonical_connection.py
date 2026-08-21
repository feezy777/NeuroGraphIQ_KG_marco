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
    replaced_by_connection_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_connections.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
