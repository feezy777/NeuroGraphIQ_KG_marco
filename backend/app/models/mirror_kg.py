"""Mirror KG ORM models — formal-KG precursor layer (NOT final_*).

LLM and manual candidates for connections, functions, circuits, triples, and evidence.
Must preserve lineage to llm_extraction_runs/items and candidate/resource/batch context.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MirrorRegionConnection(Base):
    __tablename__ = "mirror_region_connections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_region_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidate_brain_regions.id", ondelete="SET NULL"),
        nullable=True,
    )
    target_region_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidate_brain_regions.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_region_final_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    target_region_final_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    source_region_name_cn: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source_region_name_en: Mapped[str | None] = mapped_column(String(256), nullable=True)
    target_region_name_cn: Mapped[str | None] = mapped_column(String(256), nullable=True)
    target_region_name_en: Mapped[str | None] = mapped_column(String(256), nullable=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("atlas_resources.id", ondelete="SET NULL"), nullable=True
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_batches.id", ondelete="SET NULL"), nullable=True
    )
    llm_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("llm_extraction_runs.id", ondelete="SET NULL"), nullable=True
    )
    llm_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("llm_extraction_items.id", ondelete="SET NULL"), nullable=True
    )
    granularity_level: Mapped[str] = mapped_column(String(32), nullable=False)
    granularity_family: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_atlas: Mapped[str] = mapped_column(String(128), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    connection_type: Mapped[str] = mapped_column(String(64), nullable=False)
    directionality: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    strength: Mapped[str | None] = mapped_column(String(64), nullable=True)
    modality: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    uncertainty_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    mirror_status: Mapped[str] = mapped_column(String(64), nullable=False, default="llm_suggested")
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    promotion_status: Mapped[str] = mapped_column(String(64), nullable=False, default="not_promoted")
    raw_payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    normalized_payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MirrorRegionFunction(Base):
    __tablename__ = "mirror_region_functions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidate_brain_regions.id", ondelete="SET NULL"),
        nullable=True,
    )
    region_final_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("atlas_resources.id", ondelete="SET NULL"), nullable=True
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_batches.id", ondelete="SET NULL"), nullable=True
    )
    llm_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("llm_extraction_runs.id", ondelete="SET NULL"), nullable=True
    )
    llm_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("llm_extraction_items.id", ondelete="SET NULL"), nullable=True
    )
    granularity_level: Mapped[str] = mapped_column(String(32), nullable=False)
    granularity_family: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_atlas: Mapped[str] = mapped_column(String(128), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    function_term: Mapped[str] = mapped_column(String(512), nullable=False)
    term_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ontology_terms.id"), nullable=True
    )
    region_name_cn: Mapped[str | None] = mapped_column(String(256), nullable=True)
    region_name_en: Mapped[str | None] = mapped_column(String(256), nullable=True)
    function_category: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False, default="associated_with")
    confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    uncertainty_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    mirror_status: Mapped[str] = mapped_column(String(64), nullable=False, default="llm_suggested")
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    promotion_status: Mapped[str] = mapped_column(String(64), nullable=False, default="not_promoted")
    raw_payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    normalized_payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MirrorRegionCircuit(Base):
    __tablename__ = "mirror_region_circuits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("atlas_resources.id", ondelete="SET NULL"), nullable=True
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_batches.id", ondelete="SET NULL"), nullable=True
    )
    llm_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("llm_extraction_runs.id", ondelete="SET NULL"), nullable=True
    )
    llm_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("llm_extraction_items.id", ondelete="SET NULL"), nullable=True
    )
    granularity_level: Mapped[str] = mapped_column(String(32), nullable=False)
    granularity_family: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_atlas: Mapped[str] = mapped_column(String(128), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    circuit_name: Mapped[str] = mapped_column(String(512), nullable=False)
    name_cn: Mapped[str | None] = mapped_column(String(512), nullable=True)
    circuit_type: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    function_association: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    circuit_strength: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    uncertainty_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_start_region_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    canonical_end_region_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    mirror_status: Mapped[str] = mapped_column(String(64), nullable=False, default="llm_suggested")
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    promotion_status: Mapped[str] = mapped_column(String(64), nullable=False, default="not_promoted")
    raw_payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    normalized_payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MirrorCircuitRegion(Base):
    __tablename__ = "mirror_circuit_regions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    circuit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mirror_region_circuits.id", ondelete="CASCADE"),
        nullable=False,
    )
    region_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidate_brain_regions.id", ondelete="SET NULL"),
        nullable=True,
    )
    region_final_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="participant")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MirrorKgTriple(Base):
    __tablename__ = "mirror_kg_triples"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    subject_label: Mapped[str] = mapped_column(String(512), nullable=False)
    predicate: Mapped[str] = mapped_column(String(256), nullable=False)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    object_label: Mapped[str] = mapped_column(String(512), nullable=False)
    triple_scope: Mapped[str] = mapped_column(String(64), nullable=False, default="same_granularity")
    resource_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("atlas_resources.id", ondelete="SET NULL"), nullable=True
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_batches.id", ondelete="SET NULL"), nullable=True
    )
    llm_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("llm_extraction_runs.id", ondelete="SET NULL"), nullable=True
    )
    llm_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("llm_extraction_items.id", ondelete="SET NULL"), nullable=True
    )
    source_mirror_connection_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mirror_region_connections.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_mirror_function_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mirror_region_functions.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_mirror_circuit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mirror_region_circuits.id", ondelete="SET NULL"),
        nullable=True,
    )
    granularity_level: Mapped[str] = mapped_column(String(32), nullable=False)
    granularity_family: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_atlas: Mapped[str] = mapped_column(String(128), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    uncertainty_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    projection_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mirror_status: Mapped[str] = mapped_column(String(64), nullable=False, default="llm_suggested")
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    promotion_status: Mapped[str] = mapped_column(String(64), nullable=False, default="not_promoted")
    raw_payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    normalized_payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MirrorEvidenceRecord(Base):
    __tablename__ = "mirror_evidence_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evidence_target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("atlas_resources.id", ondelete="SET NULL"), nullable=True
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_batches.id", ondelete="SET NULL"), nullable=True
    )
    llm_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("llm_extraction_runs.id", ondelete="SET NULL"), nullable=True
    )
    llm_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("llm_extraction_items.id", ondelete="SET NULL"), nullable=True
    )
    granularity_level: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False, default="llm_explanation")
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    source_reference_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    citation_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    uncertainty_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_direction: Mapped[str | None] = mapped_column(String(16), nullable=True)
    evidence_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    model_direction: Mapped[str | None] = mapped_column(String(16), nullable=True)
    model_assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    claim_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    claim_text_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    claim_components_snapshot: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    coverage_summary_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    coverage_formula_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    paper_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("paper_sources.id", ondelete="SET NULL"),
        nullable=True,
    )
    paper_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    paper_pmid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    paper_doi: Mapped[str | None] = mapped_column(String(256), nullable=True)
    paper_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    paper_journal: Mapped[str | None] = mapped_column(String(256), nullable=True)
    paper_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suggested_confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    reviewer_confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    confidence_adjustment_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="none"
    )
    verification_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verification_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invalidated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invalidation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MirrorEvidencePassage(Base):
    __tablename__ = "mirror_evidence_passages"
    __table_args__ = (
        UniqueConstraint("evidence_id", "passage_hash", name="uq_evidence_passage_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mirror_evidence_records.id", ondelete="CASCADE"), nullable=False
    )
    paper_passage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("paper_passages.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_scope: Mapped[str] = mapped_column(String(16), nullable=False)
    section_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    paragraph_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passage_text: Mapped[str] = mapped_column(Text, nullable=False)
    passage_text_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    translation_zh: Mapped[str | None] = mapped_column(Text, nullable=True)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    semantic_confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    is_selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_locator: Mapped[str | None] = mapped_column(String(256), nullable=True)
    passage_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_verification_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    supported_components: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ConfidenceAdjustmentLog(Base):
    __tablename__ = "confidence_adjustment_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mirror_evidence_records.id", ondelete="SET NULL"),
        nullable=True,
    )
    before_confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    suggested_confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    reviewer_confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    calculated_confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    after_confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    direction: Mapped[str | None] = mapped_column(String(16), nullable=True)
    formula_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="applied")
    applied_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rolled_back_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rollback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PaperSource(Base):
    __tablename__ = "paper_sources"
    __table_args__ = (
        Index("uq_paper_sources_pmid", "pmid", unique=True, postgresql_where=text("pmid IS NOT NULL AND pmid <> ''")),
        Index(
            "uq_paper_sources_norm_doi",
            "normalized_doi",
            unique=True,
            postgresql_where=text("normalized_doi IS NOT NULL AND normalized_doi <> ''"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="europepmc")
    pmid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pmcid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    doi: Mapped[str | None] = mapped_column(String(256), nullable=True)
    normalized_doi: Mapped[str | None] = mapped_column(String(256), nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    journal: Mapped[str | None] = mapped_column(String(256), nullable=True)
    publication_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_oa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    abstract_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fulltext_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    abstract_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fulltext_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PaperPassage(Base):
    __tablename__ = "paper_passages"
    __table_args__ = (
        UniqueConstraint("paper_id", "paragraph_id", name="uq_paper_passage_paragraph"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paper_sources.id", ondelete="CASCADE"), nullable=False
    )
    source_scope: Mapped[str] = mapped_column(String(16), nullable=False)
    section_title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    paragraph_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    paragraph_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passage_text: Mapped[str] = mapped_column(Text, nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    locator: Mapped[str | None] = mapped_column(String(256), nullable=True)
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
