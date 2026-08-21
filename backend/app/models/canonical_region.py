"""Canonical BrainRegion ontology models (BR1).

Canonical BrainRegion is the unified concept identity for the BrainRegion
domain of the NeuroGraphIQ Semantic Core — separate from ``ontology_terms``
(Function domain, P1). Atlas-specific regions anchor to it via
``candidate_brain_regions.canonical_region_id``; anatomical containment is
stored only as ``child --part_of--> parent`` edges in
``canonical_region_hierarchy`` (never subclass_of, never a generic parent_id).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CanonicalBrainRegion(Base):
    """Canonical BrainRegion concept (hemisphere-neutral, species-explicit).

    ``region_code`` is the stable logical IRI (``ng:br:*``) and is the identity;
    display names (``canonical_name_en/cn``) never participate in identity.
    Lifecycle follows the ontology_terms pattern: proposed -> active -> deprecated,
    with a ``replaced_by_region_id`` merge chain.
    """

    __tablename__ = "canonical_brain_regions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region_code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    canonical_name_en: Mapped[str] = mapped_column(String(512), nullable=False)
    canonical_name_cn: Mapped[str | None] = mapped_column(String(512), nullable=True)
    species: Mapped[str] = mapped_column(String(16), nullable=False, default="human")
    granularity_domain: Mapped[str] = mapped_column(
        String(64), nullable=False, default="brain_region_anatomical"
    )
    granularity_level: Mapped[str] = mapped_column(String(64), nullable=False)
    hemisphere_policy: Mapped[str] = mapped_column(String(32), nullable=False)
    laterality: Mapped[str] = mapped_column(String(32), nullable=False, default="bilateral")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    source_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    external_mappings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    replaced_by_region_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_brain_regions.id"), nullable=True
    )
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    merged_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ConnectionRegionAlignment(Base):
    """Pre-computed canonical alignment of a mirror connection's endpoints (BR2-6).

    Read-only projection for CN1 readiness: maps a connection's source/target
    candidate regions to canonical concepts WITHOUT modifying the connection
    row itself. One row per connection (UNIQUE).
    """

    __tablename__ = "connection_region_alignment"
    __table_args__ = (
        UniqueConstraint("connection_id", name="uq_connection_alignment"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mirror_region_connections.id", ondelete="CASCADE"), nullable=False
    )
    source_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("candidate_brain_regions.id", ondelete="SET NULL"), nullable=True
    )
    source_canonical_region_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_brain_regions.id", ondelete="SET NULL"), nullable=True
    )
    target_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("candidate_brain_regions.id", ondelete="SET NULL"), nullable=True
    )
    target_canonical_region_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_brain_regions.id", ondelete="SET NULL"), nullable=True
    )
    mapping_type: Mapped[str] = mapped_column(String(32), nullable=False, default="exact")
    confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    source_atlas: Mapped[str | None] = mapped_column(String(128), nullable=True)
    granularity_level: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CanonicalRegionHierarchy(Base):
    """BrainRegion partonomy edge: child --part_of--> parent.

    Only ``predicate='part_of'`` is stored (CHECK-constrained). Child must be
    finer than parent (validated in service via granularity level order);
    self-loops, duplicates and cycles are rejected at the service layer.
    """

    __tablename__ = "canonical_region_hierarchy"
    __table_args__ = (
        UniqueConstraint(
            "child_region_id", "predicate", "parent_region_id",
            name="uq_region_hierarchy_edge",
        ),
        CheckConstraint(
            "child_region_id <> parent_region_id",
            name="chk_region_hierarchy_not_self",
        ),
        CheckConstraint(
            "predicate = 'part_of'",
            name="chk_region_hierarchy_predicate",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    child_region_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_brain_regions.id", ondelete="CASCADE"), nullable=False
    )
    parent_region_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_brain_regions.id", ondelete="CASCADE"), nullable=False
    )
    predicate: Mapped[str] = mapped_column(String(32), nullable=False, default="part_of")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
