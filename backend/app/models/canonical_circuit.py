"""Canonical Circuit ontology models (CI1.1).

Canonical Circuit is the unified concept identity for the Circuit domain of
the NeuroGraphIQ Semantic Core. Members reference the canonical layers below
it: regions -> ``canonical_brain_regions``, connections ->
``canonical_connections``, functions -> ``ontology_terms``. Lifecycle follows
the ontology pattern proposed -> active -> deprecated with a
``replaced_by_circuit_id`` merge chain. Source-side circuit rows
(``mirror_region_circuits`` / ``mirror_circuit_*``) are never modified, and
no circuit is auto-generated or inferred — this layer only establishes the
entity + membership infrastructure.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CanonicalCircuit(Base):
    """Canonical Circuit concept (species-explicit, type-keyed).

    ``circuit_code`` is the stable logical IRI (``ng:ci:*``) and is the
    identity. Membership lives in the three member tables; a proposed circuit
    never reaches the Final KG. Merge is expressed by
    ``replaced_by_circuit_id`` (deprecated -> replacement), never by moving
    or deleting the deprecated row.
    """

    __tablename__ = "canonical_circuits"
    __table_args__ = (
        CheckConstraint(
            "circuit_type IN ('network','pathway','reflex','functional_loop','uncertain')",
            name="chk_canonical_circuit_type",
        ),
        CheckConstraint(
            "status IN ('proposed','active','deprecated')",
            name="chk_canonical_circuit_status",
        ),
        CheckConstraint(
            "replaced_by_circuit_id IS NULL OR replaced_by_circuit_id <> id",
            name="chk_canonical_circuit_not_self_merge",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    circuit_code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    canonical_name_en: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_name_cn: Mapped[str | None] = mapped_column(Text, nullable=True)
    species: Mapped[str] = mapped_column(String(16), nullable=False, default="human")
    granularity_level: Mapped[str] = mapped_column(String(64), nullable=False, default="clinical")
    circuit_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    source_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    replaced_by_circuit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_circuits.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CanonicalCircuitRegion(Base):
    """Region membership of a canonical circuit (dedup by circuit+region)."""

    __tablename__ = "canonical_circuit_regions"
    __table_args__ = (
        UniqueConstraint("circuit_id", "region_id", name="uq_canonical_circuit_region"),
        CheckConstraint(
            "role IN ('core_region','input','output','intermediate')",
            name="chk_canonical_circuit_region_role",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    circuit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_circuits.id", ondelete="CASCADE"), nullable=False
    )
    region_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_brain_regions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="core_region")
    order_index: Mapped[int] = mapped_column(nullable=False, default=0)
    confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CanonicalCircuitConnection(Base):
    """Connection membership of a canonical circuit (dedup by circuit+connection)."""

    __tablename__ = "canonical_circuit_connections"
    __table_args__ = (
        UniqueConstraint("circuit_id", "connection_id", name="uq_canonical_circuit_connection"),
        CheckConstraint(
            "role IN ('feedforward','feedback','supporting')",
            name="chk_canonical_circuit_connection_role",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    circuit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_circuits.id", ondelete="CASCADE"), nullable=False
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_connections.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="supporting")
    confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CanonicalCircuitFunction(Base):
    """Function-term membership of a canonical circuit (dedup by circuit+term)."""

    __tablename__ = "canonical_circuit_functions"
    __table_args__ = (
        UniqueConstraint("circuit_id", "function_term_id", name="uq_canonical_circuit_function"),
        CheckConstraint(
            "relation_type IN ("
            "'involved_in','associated_with','necessary_for','modulates',"
            "'participates_in','uncertain_association','unknown')",
            name="chk_canonical_circuit_function_relation",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    circuit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_circuits.id", ondelete="CASCADE"), nullable=False
    )
    function_term_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ontology_terms.id", ondelete="CASCADE"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False, default="associated_with")
    confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
