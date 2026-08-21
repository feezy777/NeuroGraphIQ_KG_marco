"""Pydantic schemas for the BR3 multiscale atlas / cell / molecular layers."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

_MAPPING_TYPES = {"exact", "broader", "narrower", "uncertain"}
_SPECIES_RELATIONS = {"same_species", "homology", "unknown"}
_CELL_MAPPING_TYPES = {"contains", "enriched", "marker", "unknown"}
_ENTITY_TYPES = {"gene", "protein", "neurotransmitter", "receptor"}
_HEMISPHERES = {"L", "R", "bilateral", "midline", "unknown"}
_ROW_STATUSES = {"active", "superseded"}
_EVIDENCE_TYPES = {"expression", "receptor_binding", "neurotransmitter_release", "unknown"}


# ──── atlas_region_resources ────────────────────────────────────────────────


class AtlasRegionCreate(BaseModel):
    atlas_name: str = Field(..., min_length=1, max_length=128)
    atlas_version: str = Field(default="", max_length=64)
    atlas_region_id: str = Field(..., min_length=1, max_length=128)
    region_name: str = Field(..., min_length=1, max_length=500)
    region_acronym: str | None = Field(default=None, max_length=64)
    parent_region_id: str | None = Field(default=None, max_length=128)
    species: str = "human"
    hemisphere: str = "unknown"
    source_file: str | None = Field(default=None, max_length=500)
    provenance: dict[str, Any] = Field(default_factory=dict)
    status: str = "active"

    @field_validator("species")
    @classmethod
    def _valid_species(cls, v: str) -> str:
        if v not in {"human", "mouse", "unknown"}:
            raise ValueError(f"invalid species: {v}")
        return v

    @field_validator("hemisphere")
    @classmethod
    def _valid_hemisphere(cls, v: str) -> str:
        if v not in _HEMISPHERES:
            raise ValueError(f"invalid hemisphere: {v}")
        return v

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v: str) -> str:
        if v not in _ROW_STATUSES:
            raise ValueError(f"invalid status: {v}")
        return v


class AtlasRegionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    atlas_resource_id: uuid.UUID | None
    atlas_name: str
    atlas_version: str
    atlas_region_id: str
    region_name: str
    region_acronym: str | None
    parent_region_id: str | None
    species: str
    hemisphere: str
    source_file: str | None
    provenance: dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime


class AtlasRegionBatchImport(BaseModel):
    """Bulk import payload: raw atlas rows (never written into canonical)."""

    rows: list[AtlasRegionCreate]
    source_file: str | None = None
    created_by: str = "import"


class AtlasRegionImportResult(BaseModel):
    inserted: int
    skipped: int
    total: int


# ──── atlas_region_mappings ─────────────────────────────────────────────────


class AtlasRegionMappingCreate(BaseModel):
    atlas_region_id: uuid.UUID
    canonical_region_id: uuid.UUID
    mapping_type: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    species_relation: str = "same_species"
    match_details: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    created_by: str = "manual"

    @field_validator("mapping_type")
    @classmethod
    def _valid_mapping_type(cls, v: str) -> str:
        if v not in _MAPPING_TYPES:
            raise ValueError(f"invalid mapping_type: {v}")
        return v

    @field_validator("species_relation")
    @classmethod
    def _valid_species_relation(cls, v: str) -> str:
        if v not in _SPECIES_RELATIONS:
            raise ValueError(f"invalid species_relation: {v}")
        return v


class AtlasRegionMappingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    atlas_region_id: uuid.UUID
    canonical_region_id: uuid.UUID | None
    mapping_type: str
    confidence: float | None
    species_relation: str
    match_details: dict[str, Any]
    provenance: dict[str, Any]
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime


# ──── cell types (NOT BrainRegions) ─────────────────────────────────────────


class CellTypeCreate(BaseModel):
    cell_type_code: str = Field(..., pattern=r"^ng:ct:[a-z0-9_]+$")
    canonical_name_en: str = Field(..., min_length=1, max_length=512)
    canonical_name_cn: str | None = Field(default=None, max_length=512)
    species: str = "human"
    taxonomy_source: str | None = Field(default=None, max_length=256)
    taxonomy_version: str | None = Field(default=None, max_length=64)
    external_iri: str | None = Field(default=None, max_length=256)
    description: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)

    @field_validator("species")
    @classmethod
    def _valid_species(cls, v: str) -> str:
        if v not in {"human", "mouse", "unknown"}:
            raise ValueError(f"invalid species: {v}")
        return v


class CellTypeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    cell_type_code: str
    canonical_name_en: str
    canonical_name_cn: str | None
    species: str
    taxonomy_source: str | None
    taxonomy_version: str | None
    external_iri: str | None
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class RegionCellAlignmentCreate(BaseModel):
    region_id: uuid.UUID
    cell_type_id: uuid.UUID
    mapping_type: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @field_validator("mapping_type")
    @classmethod
    def _valid_mapping_type(cls, v: str) -> str:
        if v not in _CELL_MAPPING_TYPES:
            raise ValueError(f"invalid mapping_type: {v}")
        return v


class RegionCellAlignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    region_id: uuid.UUID
    cell_type_id: uuid.UUID
    mapping_type: str
    confidence: float | None
    provenance: dict[str, Any]
    created_at: datetime
    updated_at: datetime


# ──── molecular entities (NOT BrainRegions) ─────────────────────────────────


class MolecularEntityCreate(BaseModel):
    entity_code: str = Field(..., pattern=r"^ng:mol:[a-z0-9_]+$")
    entity_type: str
    canonical_name_en: str = Field(..., min_length=1, max_length=512)
    canonical_name_cn: str | None = Field(default=None, max_length=512)
    external_iri: str | None = Field(default=None, max_length=256)
    species: str = "human"
    description: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)

    @field_validator("entity_type")
    @classmethod
    def _valid_entity_type(cls, v: str) -> str:
        if v not in _ENTITY_TYPES:
            raise ValueError(f"invalid entity_type: {v}")
        return v

    @field_validator("species")
    @classmethod
    def _valid_species(cls, v: str) -> str:
        if v not in {"human", "mouse", "unknown"}:
            raise ValueError(f"invalid species: {v}")
        return v


class MolecularEntityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_code: str
    entity_type: str
    canonical_name_en: str
    canonical_name_cn: str | None
    external_iri: str | None
    species: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class RegionMolecularAlignmentCreate(BaseModel):
    region_id: uuid.UUID
    molecular_entity_id: uuid.UUID
    evidence_type: str = "expression"
    confidence: float | None = Field(default=None, ge=0, le=1)
    source: str | None = Field(default=None, max_length=500)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @field_validator("evidence_type")
    @classmethod
    def _valid_evidence_type(cls, v: str) -> str:
        if v not in _EVIDENCE_TYPES:
            raise ValueError(f"invalid evidence_type: {v}")
        return v


class RegionMolecularAlignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    region_id: uuid.UUID
    molecular_entity_id: uuid.UUID
    entity_type: str
    evidence_type: str
    confidence: float | None
    source: str | None
    provenance: dict[str, Any]
    created_at: datetime
    updated_at: datetime


# ──── source registry views ─────────────────────────────────────────────────


class AtlasSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    resource_code: str
    source_atlas: str
    source_version: str
    resource_type: str
    species: str
    granularity_level: str
    granularity_family: str
    template_space: str
    cn_name: str | None
    en_name: str | None
    description: str | None
    remark: str | None
    status: str
    created_at: datetime
    updated_at: datetime
