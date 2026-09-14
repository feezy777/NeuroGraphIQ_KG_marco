"""Phase 1 Knowledge Production API DTOs (read-only).

These DTOs describe only fields that actually exist in the Gate7B formal
knowledge tables of ``neurographiq_human_brain_v1``:

    kg_entities  (identity / names / lifecycle)
    brain_regions (subtype row: granularity / hemisphere / category)
    region_mappings + external_regions + atlases (atlas provenance)

No candidate_* / mirror_* / final_* entity is represented here.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# The frozen Gate7B granularity vocabulary. This is the ONLY granularity
# vocabulary used by the Knowledge Production module.
GranularityLevel = Literal[
    "G1_MACRO",
    "G2_MESO_ANATOMICAL",
    "G3_MESO_FINE",
    "G4_MICROSTRUCTURAL_FINE",
]

GATE7B_GRANULARITY_LEVELS: tuple[str, ...] = (
    "G1_MACRO",
    "G2_MESO_ANATOMICAL",
    "G3_MESO_FINE",
    "G4_MICROSTRUCTURAL_FINE",
)


class BrainRegionSeedItem(BaseModel):
    """One canonical BrainRegion usable as a discovery seed. Read-only."""

    entity_pk: int
    entity_id: str
    name_en: str | None = None
    name_zh: str | None = None
    abbreviation: str | None = None
    granularity_level: str | None = None
    region_category: str | None = None
    hemisphere: str | None = None
    species_taxon_id: str | None = None
    record_status: str | None = None
    review_status: str | None = None
    atlas_names: list[str] = Field(default_factory=list)


class BrainRegionSeedListResponse(BaseModel):
    items: list[BrainRegionSeedItem]
    total: int


class BrainRegionSummary(BaseModel):
    """Read-only BrainRegion counts for the Production Index summary row.

    One aggregate query instead of one list request per granularity.
    Contains ONLY fields that exist in the Gate7B authority tables.
    """

    total: int
    by_granularity: dict[str, int]


class BrainRegionSeedDetail(BrainRegionSeedItem):
    """Detail view. Adds only fields that exist on brain_regions / kg_entities."""

    definition_en: str | None = None
    parent_region_pk: int | None = None
    hierarchy_depth: int | None = None
    external_region_ids: list[str] = Field(default_factory=list)
    mapping_types: list[str] = Field(default_factory=list)
    mapping_review_statuses: list[str] = Field(default_factory=list)
