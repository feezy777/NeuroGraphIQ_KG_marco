"""Ontology layer ORM models (Phase 1: quality-control-first)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class OntologyVocabulary(Base):
    """Registry of predicates / relation types / categories / domains / roles / effect types."""

    __tablename__ = "ontology_vocabularies"
    __table_args__ = (
        UniqueConstraint("code", "vocab_type", name="uq_ontology_vocab_code_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    vocab_type: Mapped[str] = mapped_column(String(32), nullable=False)
    label_cn: Mapped[str | None] = mapped_column(String(256), nullable=True)
    label_en: Mapped[str | None] = mapped_column(String(256), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    seq: Mapped[int] = mapped_column(default=0, nullable=False)
    # BR3 multiscale additions (granularity_level vocab only; NULL for other vocab types)
    level_order: Mapped[int | None] = mapped_column(nullable=True)
    source_strategy: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GranularityLevelCompatMap(Base):
    """Legacy granularity_level -> canonical multiscale level compatibility map (BR3)."""

    __tablename__ = "granularity_level_compat_map"

    legacy_level: Mapped[str] = mapped_column(String(64), primary_key=True)
    canonical_level: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OntologyTerm(Base):
    """Canonical function/region term registry entry."""

    __tablename__ = "ontology_terms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    term_code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    canonical_term_en: Mapped[str] = mapped_column(String(512), nullable=False)
    canonical_term_cn: Mapped[str | None] = mapped_column(String(512), nullable=True)
    term_type: Mapped[str] = mapped_column(String(32), nullable=False, default="function")
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(128), nullable=True)
    role: Mapped[str | None] = mapped_column(String(128), nullable=True)
    effect_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    replaced_by_term_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ontology_terms.id"), nullable=True
    )
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    merged_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OntologyTermSynonym(Base):
    """Synonym spellings mapped to a canonical ontology term."""

    __tablename__ = "ontology_term_synonyms"
    __table_args__ = (
        UniqueConstraint("term_id", "synonym_text", "lang", name="uq_ontology_synonym"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    term_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ontology_terms.id", ondelete="CASCADE"), nullable=False
    )
    synonym_text: Mapped[str] = mapped_column(String(512), nullable=False)
    lang: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    match_type: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OntologyTermExternalMapping(Base):
    """Alignment to external standards (UBERON / NIFSTD / NeuroLex / BTO)."""

    __tablename__ = "ontology_term_external_mappings"
    __table_args__ = (
        UniqueConstraint("term_id", "external_system", "external_iri", name="uq_ontology_external"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    term_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ontology_terms.id", ondelete="CASCADE"), nullable=False
    )
    external_system: Mapped[str] = mapped_column(String(64), nullable=False)
    external_iri: Mapped[str] = mapped_column(String(512), nullable=False)
    match_type: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    verified_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OntologyTermGrounding(Base):
    """Maps a business record to a canonical ontology term."""

    __tablename__ = "ontology_term_groundings"
    __table_args__ = (
        UniqueConstraint("target_type", "target_id", name="uq_ontology_grounding_target"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    term_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ontology_terms.id", ondelete="SET NULL"), nullable=True
    )
    grounded_by: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    grounded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OntologyAlignmentCandidate(Base):
    """External-standard alignment candidate awaiting human review."""

    __tablename__ = "ontology_alignment_candidates"
    __table_args__ = (
        UniqueConstraint(
            "target_type", "target_id", "external_system", "external_iri",
            name="uq_ontology_alignment_candidate",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    external_system: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    external_iri: Mapped[str] = mapped_column(String(512), nullable=False)
    external_label: Mapped[str | None] = mapped_column(String(512), nullable=True)
    match_type: Mapped[str] = mapped_column(String(16), nullable=False)
    match_score: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    match_details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OntologyHierarchyCandidate(Base):
    """O1.3-A: deterministic hierarchy parent candidate (NOT a formal edge).

    Separate from ontology_term_relations on purpose — candidates await
    judgment before becoming proposed hierarchy edges.
    """

    __tablename__ = "ontology_hierarchy_candidates"
    __table_args__ = (
        UniqueConstraint(
            "child_term_id", "parent_term_id", "generation_version",
            name="uq_hierarchy_candidate",
        ),
        CheckConstraint(
            "child_term_id <> parent_term_id",
            name="chk_hierarchy_candidate_not_self",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    child_term_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ontology_terms.id", ondelete="CASCADE"), nullable=False
    )
    parent_term_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ontology_terms.id", ondelete="CASCADE"), nullable=False
    )
    candidate_score: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    generation_method: Mapped[str | None] = mapped_column(String(128), nullable=True)
    generation_reasons_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    lexical_score: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    metadata_score: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    usage_score: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    synonym_score: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    parent_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    calibration_label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    generation_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OntologyChangeLog(Base):
    """Audit trail for ontology governance operations."""

    __tablename__ = "ontology_change_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    before_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    after_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    operator_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OntologyTermRelation(Base):
    """Function Concept hierarchy edge (O1.2).

    Canonical direction: child (subject_term_id) --subclass_of--> parent
    (object_term_id). Only ``subclass_of`` is stored; broader/narrower are
    query-direction derivations. DAG: a child may have several parents.
    """

    __tablename__ = "ontology_term_relations"
    __table_args__ = (
        UniqueConstraint(
            "subject_term_id", "predicate", "object_term_id",
            name="uq_ontology_relation_edge",
        ),
        CheckConstraint(
            "subject_term_id <> object_term_id",
            name="chk_ontology_relation_not_self",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_term_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ontology_terms.id", ondelete="CASCADE"), nullable=False
    )
    predicate: Mapped[str] = mapped_column(String(64), nullable=False)
    object_term_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ontology_terms.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OntologyAuditRun(Base):
    """Ontology audit run record (dashboard last-audit + progress)."""

    __tablename__ = "ontology_audit_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    granularity_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
