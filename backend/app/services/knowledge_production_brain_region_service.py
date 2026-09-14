"""Phase 1 Knowledge Production - read-only BrainRegion seed access.

Reads ONLY the Gate7B formal knowledge tables of ``neurographiq_human_brain_v1``:

    brain_regions, kg_entities, region_mappings, external_regions, atlases

This module is strictly read-only: it issues SELECT statements only. It must not
import or reference candidate_* / mirror_* / final_* models, and it must not be
extended into a write path (knowledge production writes belong to later phases
and to a different layer).
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.knowledge_production import (
    BrainRegionSeedDetail,
    BrainRegionSeedItem,
    BrainRegionSeedListResponse,
    BrainRegionSummary,
    GATE7B_GRANULARITY_LEVELS,
)

# Gate7B identity: entity_id (e.g. NGIQ-BR-00000001) is the stable public id.
_IDENTIFIER_COLUMN = "e.entity_id"

# Atlas names are reachable only through the mapping chain:
#   region_mappings -> external_regions -> atlases -> kg_entities(name_en)
_ATLAS_LATERAL = """
    LEFT JOIN LATERAL (
        SELECT array_agg(DISTINCT ae.name_en ORDER BY ae.name_en) AS atlas_names
        FROM region_mappings rm
        JOIN external_regions x ON x.entity_pk = rm.external_region_pk
        JOIN atlases a ON a.entity_pk = x.atlas_pk
        JOIN kg_entities ae ON ae.entity_pk = a.entity_pk
        WHERE rm.brain_region_pk = b.entity_pk
          AND ae.name_en IS NOT NULL
    ) atlas ON TRUE
"""

_ATLAS_EXISTS_FILTER = """
    EXISTS (
        SELECT 1
        FROM region_mappings rm
        JOIN external_regions x ON x.entity_pk = rm.external_region_pk
        JOIN atlases a ON a.entity_pk = x.atlas_pk
        JOIN kg_entities ae ON ae.entity_pk = a.entity_pk
        WHERE rm.brain_region_pk = b.entity_pk
          AND ae.name_en ILIKE :atlas_like
    )
"""

_SELECT_COLUMNS = """
    b.entity_pk,
    e.entity_id,
    e.name_en,
    e.name_zh,
    e.abbreviation,
    b.granularity_level,
    b.region_category,
    b.hemisphere,
    b.species_taxon_id,
    e.record_status,
    e.review_status,
    COALESCE(atlas.atlas_names, ARRAY[]::text[]) AS atlas_names
"""

_MAX_LIMIT = 200
_DEFAULT_LIMIT = 50


def normalize_limit(limit: int | None) -> int:
    """Clamp the page size. Never allow an unbounded list request."""
    if limit is None or limit <= 0:
        return _DEFAULT_LIMIT
    return min(int(limit), _MAX_LIMIT)


def normalize_offset(offset: int | None) -> int:
    if offset is None or offset < 0:
        return 0
    return int(offset)


def build_filters(
    *,
    granularity_level: str | None = None,
    source_atlas: str | None = None,
    search: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Build the WHERE clause + bound parameters. Pure function (unit-testable)."""
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if granularity_level:
        clauses.append("b.granularity_level = :granularity_level")
        params["granularity_level"] = granularity_level
    if source_atlas and source_atlas.strip():
        clauses.append(_ATLAS_EXISTS_FILTER)
        params["atlas_like"] = f"%{source_atlas.strip()}%"
    if search and search.strip():
        clauses.append(
            "(e.name_en ILIKE :search_like OR e.name_zh ILIKE :search_like"
            " OR e.entity_id ILIKE :search_like)"
        )
        params["search_like"] = f"%{search.strip()}%"
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def row_to_item(row: Mapping[str, Any]) -> BrainRegionSeedItem:
    """Map one DB row to the list DTO. Pure function (unit-testable)."""
    return BrainRegionSeedItem(
        entity_pk=row["entity_pk"],
        entity_id=row["entity_id"],
        name_en=row["name_en"],
        name_zh=row["name_zh"],
        abbreviation=row["abbreviation"],
        granularity_level=row["granularity_level"],
        region_category=row["region_category"],
        hemisphere=row["hemisphere"],
        species_taxon_id=row["species_taxon_id"],
        record_status=row["record_status"],
        review_status=row["review_status"],
        atlas_names=list(row["atlas_names"] or []),
    )


async def list_seed_regions(
    session: AsyncSession,
    *,
    granularity_level: str | None = None,
    source_atlas: str | None = None,
    search: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> BrainRegionSeedListResponse:
    """Server-side paginated BrainRegion seed list. SELECT only."""
    where, params = build_filters(
        granularity_level=granularity_level, source_atlas=source_atlas, search=search
    )
    total = int(
        (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM brain_regions b"
                    " JOIN kg_entities e ON e.entity_pk = b.entity_pk" + where
                ),
                params,
            )
        ).scalar_one()
    )
    rows = (
        await session.execute(
            text(
                "SELECT " + _SELECT_COLUMNS
                + " FROM brain_regions b"
                " JOIN kg_entities e ON e.entity_pk = b.entity_pk"
                + _ATLAS_LATERAL + where
                + " ORDER BY e.entity_id LIMIT :limit OFFSET :offset"
            ),
            {**params, "limit": normalize_limit(limit), "offset": normalize_offset(offset)},
        )
    ).mappings().all()
    return BrainRegionSeedListResponse(
        items=[row_to_item(r) for r in rows], total=total
    )


async def summarize_seed_regions(session: AsyncSession) -> BrainRegionSummary:
    """Counts per Gate7B granularity level in ONE aggregate query. SELECT only."""
    rows = (
        await session.execute(
            text(
                "SELECT b.granularity_level, COUNT(*) AS n"
                " FROM brain_regions b"
                " JOIN kg_entities e ON e.entity_pk = b.entity_pk"
                " GROUP BY b.granularity_level"
            )
        )
    ).mappings().all()
    counts = {r["granularity_level"]: int(r["n"]) for r in rows}
    return BrainRegionSummary(
        total=sum(counts.values()),
        by_granularity={g: counts.get(g, 0) for g in GATE7B_GRANULARITY_LEVELS},
    )


def _mapping_summary_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    external: list[str] = []
    mapping_types: list[str] = []
    review_statuses: list[str] = []
    for r in rows:
        if r["external_region_id"] and r["external_region_id"] not in external:
            external.append(r["external_region_id"])
        if r["mapping_type"] and r["mapping_type"] not in mapping_types:
            mapping_types.append(r["mapping_type"])
        if r["review_status"] and r["review_status"] not in review_statuses:
            review_statuses.append(r["review_status"])
    return {
        "external_region_ids": external,
        "mapping_types": mapping_types,
        "mapping_review_statuses": review_statuses,
    }


async def get_seed_region(
    session: AsyncSession, identifier: str
) -> BrainRegionSeedDetail | None:
    """Fetch one BrainRegion by entity_id. Returns None when absent. SELECT only."""
    row = (
        await session.execute(
            text(
                "SELECT " + _SELECT_COLUMNS + ", e.definition_en,"
                " b.parent_region_pk, b.hierarchy_depth"
                " FROM brain_regions b"
                " JOIN kg_entities e ON e.entity_pk = b.entity_pk"
                + _ATLAS_LATERAL
                + f" WHERE {_IDENTIFIER_COLUMN} = :identifier"
            ),
            {"identifier": identifier},
        )
    ).mappings().first()
    if row is None:
        return None

    mappings = (
        await session.execute(
            text(
                "SELECT xe.entity_id AS external_region_id, rm.mapping_type,"
                " rm.review_status"
                " FROM region_mappings rm"
                " JOIN brain_regions b ON b.entity_pk = rm.brain_region_pk"
                " JOIN kg_entities e ON e.entity_pk = b.entity_pk"
                " JOIN external_regions x ON x.entity_pk = rm.external_region_pk"
                " JOIN kg_entities xe ON xe.entity_pk = x.entity_pk"
                f" WHERE {_IDENTIFIER_COLUMN} = :identifier"
                " ORDER BY xe.entity_id"
            ),
            {"identifier": identifier},
        )
    ).mappings().all()

    item = row_to_item(row)
    return BrainRegionSeedDetail(
        **item.model_dump(),
        definition_en=row["definition_en"],
        parent_region_pk=row["parent_region_pk"],
        hierarchy_depth=row["hierarchy_depth"],
        **_mapping_summary_rows(mappings),
    )
