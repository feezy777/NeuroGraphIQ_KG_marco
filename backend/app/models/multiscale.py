"""BR3 multiscale models: atlas resource layer + cell/molecular alignment layers.

Design principle (BR3):
- External atlas rows live in atlas_region_resources; they are NEVER written
  directly into canonical_brain_regions.
- atlas_region_mappings is the auditable atlas_region -> canonical_region link.
- Cell types and molecular entities are NOT BrainRegions: independent
  registries + alignment tables.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AtlasRegionResource(Base):
    """One raw atlas region row (atlas-native identity)."""

    __tablename__ = "atlas_region_resources"
    __table_args__ = (
        UniqueConstraint("atlas_name", "atlas_version", "atlas_region_id", name="uq_atlas_region_resources_native"),
        CheckConstraint("status IN ('active', 'superseded')", name="chk_atlas_region_resources_status"),
        CheckConstraint(
            "hemisphere IN ('L', 'R', 'bilateral', 'midline', 'unknown')",
            name="chk_atlas_region_resources_hemisphere",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    atlas_resource_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("atlas_resources.id", ondelete="SET NULL"), nullable=True
    )
    atlas_name: Mapped[str] = mapped_column(String(128), nullable=False)
    atlas_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    atlas_region_id: Mapped[str] = mapped_column(String(128), nullable=False)
    region_name: Mapped[str] = mapped_column(String(500), nullable=False)
    region_acronym: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parent_region_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    species: Mapped[str] = mapped_column(String(32), nullable=False, default="human")
    hemisphere: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    source_file: Mapped[str | None] = mapped_column(String(500), nullable=True)
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AtlasRegionMapping(Base):
    """atlas_region -> canonical_region alignment (exact/broader/narrower/uncertain)."""

    __tablename__ = "atlas_region_mappings"
    __table_args__ = (
        CheckConstraint(
            "mapping_type IN ('exact', 'broader', 'narrower', 'uncertain')",
            name="chk_atlas_region_mappings_type",
        ),
        CheckConstraint(
            "species_relation IN ('same_species', 'homology', 'unknown')",
            name="chk_atlas_region_mappings_species_rel",
        ),
        CheckConstraint("status IN ('active', 'superseded')", name="chk_atlas_region_mappings_status"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="chk_atlas_region_mappings_conf",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    atlas_region_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("atlas_region_resources.id", ondelete="CASCADE"), nullable=False
    )
    canonical_region_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_brain_regions.id", ondelete="SET NULL"), nullable=True
    )
    mapping_type: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    species_relation: Mapped[str] = mapped_column(String(32), nullable=False, default="same_species")
    match_details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CellTypeRegistry(Base):
    """Cell types — independent entity registry, NOT BrainRegions (BR3 Cyto layer)."""

    __tablename__ = "cell_type_registry"
    __table_args__ = (
        UniqueConstraint("cell_type_code", name="uq_cell_type_registry_code"),
        CheckConstraint("status IN ('active', 'deprecated')", name="chk_cell_type_registry_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cell_type_code: Mapped[str] = mapped_column(String(128), nullable=False)
    canonical_name_en: Mapped[str] = mapped_column(String(512), nullable=False)
    canonical_name_cn: Mapped[str | None] = mapped_column(String(512), nullable=True)
    species: Mapped[str] = mapped_column(String(32), nullable=False, default="human")
    taxonomy_source: Mapped[str | None] = mapped_column(String(256), nullable=True)
    taxonomy_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_iri: Mapped[str | None] = mapped_column(String(256), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RegionCellAlignment(Base):
    """BrainRegion x CellType alignment (spec: region_id, cell_type_id, mapping_type, confidence, provenance)."""

    __tablename__ = "region_cell_alignment"
    __table_args__ = (
        UniqueConstraint("region_id", "cell_type_id", "mapping_type", name="uq_region_cell_alignment"),
        CheckConstraint(
            "mapping_type IN ('contains', 'enriched', 'marker', 'unknown')",
            name="chk_region_cell_alignment_type",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="chk_region_cell_alignment_conf",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_brain_regions.id", ondelete="CASCADE"), nullable=False
    )
    cell_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cell_type_registry.id", ondelete="CASCADE"), nullable=False
    )
    mapping_type: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MolecularEntityRegistry(Base):
    """Molecular entities (gene/protein/neurotransmitter/receptor) — NOT BrainRegions (BR3 Molecular layer)."""

    __tablename__ = "molecular_entity_registry"
    __table_args__ = (
        UniqueConstraint("entity_code", name="uq_molecular_entity_registry_code"),
        CheckConstraint(
            "entity_type IN ('gene', 'protein', 'neurotransmitter', 'receptor')",
            name="chk_molecular_entity_registry_type",
        ),
        CheckConstraint("status IN ('active', 'deprecated')", name="chk_molecular_entity_registry_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_code: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_name_en: Mapped[str] = mapped_column(String(512), nullable=False)
    canonical_name_cn: Mapped[str | None] = mapped_column(String(512), nullable=True)
    external_iri: Mapped[str | None] = mapped_column(String(256), nullable=True)
    species: Mapped[str] = mapped_column(String(32), nullable=False, default="human")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RegionMolecularAlignment(Base):
    """BrainRegion x MolecularEntity alignment (spec: region_id, molecular_entity, entity_type, confidence, source)."""

    __tablename__ = "region_molecular_alignment"
    __table_args__ = (
        UniqueConstraint("region_id", "molecular_entity_id", "evidence_type", name="uq_region_molecular_alignment"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="chk_region_molecular_alignment_conf",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_brain_regions.id", ondelete="CASCADE"), nullable=False
    )
    molecular_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("molecular_entity_registry.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(32), nullable=False, default="expression")
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    source: Mapped[str | None] = mapped_column(String(500), nullable=True)
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
