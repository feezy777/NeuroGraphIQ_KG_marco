"""Pydantic schemas for Canonical BrainRegion (BR1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

REGION_CODE_PATTERN = r"^ng:br:[a-z0-9_]+$"

# BR3 multiscale: canonical macro/meso/subregion/cyto/molecular + legacy compat
# levels (whole_brain/clinical/research/fine/ultra_fine stay assignable so
# existing data and tests keep working; see granularity_level_compat_map).
_GRANULARITY_LEVELS = {
    "whole_brain", "macro", "clinical", "meso", "research",
    "subregion", "fine", "cyto", "ultra_fine", "molecular",
}
_HEMISPHERE_POLICIES = {"bilateral", "lateralized", "midline_unpaired"}
_SPECIES = {"human", "mouse", "unknown"}
# BR4: hemisphere info lives in laterality — no left_*/right_* entity names.
_LATERALITIES = {"bilateral", "left", "right", "midline_unpaired", "unknown"}


class CanonicalRegionCreate(BaseModel):
    region_code: str = Field(..., pattern=REGION_CODE_PATTERN)
    canonical_name_en: str = Field(..., min_length=1, max_length=512)
    canonical_name_cn: str | None = None
    species: str = "human"
    granularity_domain: str = "brain_region_anatomical"
    granularity_level: str
    hemisphere_policy: str
    laterality: str = "bilateral"
    status: str = "proposed"
    description: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    source_summary: dict[str, Any] = Field(default_factory=dict)
    external_mappings: dict[str, Any] = Field(default_factory=dict)
    created_by: str = "manual"

    @field_validator("granularity_level")
    @classmethod
    def _valid_level(cls, v: str) -> str:
        if v not in _GRANULARITY_LEVELS:
            raise ValueError(f"invalid granularity_level: {v}")
        return v

    @field_validator("hemisphere_policy")
    @classmethod
    def _valid_hemisphere(cls, v: str) -> str:
        if v not in _HEMISPHERE_POLICIES:
            raise ValueError(f"invalid hemisphere_policy: {v}")
        return v

    @field_validator("species")
    @classmethod
    def _valid_species(cls, v: str) -> str:
        if v not in _SPECIES:
            raise ValueError(f"invalid species: {v}")
        return v

    @field_validator("laterality")
    @classmethod
    def _valid_laterality(cls, v: str) -> str:
        if v not in _LATERALITIES:
            raise ValueError(f"invalid laterality: {v}")
        return v


class CanonicalRegionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    region_code: str
    canonical_name_en: str
    canonical_name_cn: str | None
    species: str
    granularity_domain: str
    granularity_level: str
    hemisphere_policy: str
    # default keeps BR1-era constructors (tests/clients) valid; DB rows are
    # always populated via from_attributes (column default 'bilateral')
    laterality: str = "bilateral"
    status: str
    description: str | None
    confidence: float | None
    source_summary: dict[str, Any]
    external_mappings: dict[str, Any]
    created_by: str
    created_at: datetime
    updated_at: datetime


class CanonicalRegionHierarchyCreate(BaseModel):
    child_region_id: uuid.UUID
    parent_region_id: uuid.UUID
    predicate: str = "part_of"
    status: str = "active"
    source: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    provenance_json: dict[str, Any] = Field(default_factory=dict)
    created_by: str | None = None

    @field_validator("predicate")
    @classmethod
    def _only_part_of(cls, v: str) -> str:
        if v != "part_of":
            raise ValueError("only predicate='part_of' is allowed (BR1)")
        return v


class CanonicalRegionHierarchyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    child_region_id: uuid.UUID
    parent_region_id: uuid.UUID
    predicate: str
    status: str
    source: str | None
    confidence: float | None
    provenance_json: dict[str, Any]
    created_at: datetime


class CanonicalRegionTreeItem(BaseModel):
    """One node in ancestor/descendant traversal results."""

    id: uuid.UUID
    region_code: str
    canonical_name_en: str
    granularity_level: str
    species: str
    depth: int


class CandidateGroundingRequest(BaseModel):
    candidate_id: uuid.UUID
    canonical_region_id: uuid.UUID
    match_type: str = Field(..., pattern=r"^(exact|close|broader|narrower|uncertain|rejected)$")
    confidence: float | None = Field(default=None, ge=0, le=1)
    match_details: dict[str, Any] = Field(default_factory=dict)


class CanonicalRegionMergeRequest(BaseModel):
    """Body for POST /canonical-regions/merge (BR3 identity-preserving merge)."""

    source_region_id: uuid.UUID
    target_region_id: uuid.UUID


class CanonicalRegionMergeResponse(BaseModel):
    source_region_code: str
    target_region_code: str
    repointed_edges: int
    kept_edges: int
    repointed_mappings: int
    superseded_mappings: int
    repointed_alignments: int
    kept_alignments: int


# ──── Browser (tree explorer) read-only payloads ─────────────────────────────


class RegionEndpointRef(BaseModel):
    """The region on the other side of a connection row."""

    id: uuid.UUID
    region_code: str
    canonical_name_en: str
    canonical_name_cn: str | None
    granularity_level: str


class RegionConnectionRead(BaseModel):
    connection_id: uuid.UUID
    connection_code: str
    connection_type: str
    directionality_policy: str
    status: str
    confidence: float | None
    direction: Literal["outgoing", "incoming"]
    endpoint_region: RegionEndpointRef


class RegionCircuitRead(BaseModel):
    circuit_id: uuid.UUID
    circuit_code: str
    canonical_name_en: str
    circuit_type: str
    status: str
    role: str
    order_index: int
    confidence: float | None


class RegionFunctionRead(BaseModel):
    """Function term reachable from the region through its circuits."""

    function_term_id: uuid.UUID
    term_code: str
    canonical_term_en: str
    canonical_term_cn: str | None
    relation_type: str
    circuit_code: str
    circuit_name: str
    confidence: float | None


class RegionCandidateRead(BaseModel):
    """Candidate anchor for provenance (candidate_brain_regions.canonical_region_id)."""

    candidate_id: uuid.UUID
    source_atlas: str
    source_version: str
    raw_name: str
    std_name: str | None
    en_name: str | None
    cn_name: str | None
    laterality: str
    granularity_level: str
    granularity_family: str
    alignment_status: str
    candidate_status: str
    uberon_iri: str | None
    nifstd_iri: str | None
    created_at: datetime


# ──── BR4: unified multiscale view (cross-layer cell/molecule alignment) ─────


class MultiscaleRegionCellTypeRead(BaseModel):
    """Cell type aligned to the region (cell_type_registry — never a BrainRegion)."""

    cell_type_id: uuid.UUID
    cell_type_code: str
    canonical_name_en: str
    canonical_name_cn: str | None
    taxonomy_source: str | None
    mapping_type: str
    confidence: float | None


class MultiscaleRegionMoleculeRead(BaseModel):
    """Molecular entity aligned to the region (molecular_entity_registry)."""

    molecular_entity_id: uuid.UUID
    entity_code: str
    canonical_name_en: str
    entity_type: str
    evidence_type: str
    confidence: float | None
    source: str | None


class CanonicalRegionMultiscaleView(BaseModel):
    """GET /canonical-regions/{id}/multiscale — one region across all scales."""

    region: CanonicalRegionRead
    parents: list[CanonicalRegionTreeItem]
    children: list[CanonicalRegionRead]
    meso_regions: list[CanonicalRegionRead]
    subregions: list[CanonicalRegionRead]
    fine_regions: list[CanonicalRegionRead]
    cell_types: list[MultiscaleRegionCellTypeRead]
    molecules: list[MultiscaleRegionMoleculeRead]
