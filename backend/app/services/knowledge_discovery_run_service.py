"""Phase 2A - read-only Discovery Run access.

A Discovery Run is the record of ONE attempt to discover candidate knowledge
around ONE canonical BrainRegion seed. It is workflow / provenance, NOT
knowledge: a run never represents a circuit / connection / function / evidence /
knowledge assertion.

Tables read (SELECT only):

    knowledge_discovery_runs   the run itself (Phase 2A, migration gate7b_011)
    brain_regions              seed resolution (entity_pk)
    kg_entities                public identity resolution (entity_id)

This module is strictly READ-ONLY. It issues SELECT statements only and must
never be extended into a lifecycle writer: create / start / complete / fail /
cancel belong to Phase 2B (``knowledge_discovery_run_lifecycle_service``), which
is a separate, explicitly governed module. Do not add INSERT/UPDATE/DELETE here.

It must not import or reference candidate_* / mirror_* / final_* models, and it
must not call any LLM provider or literature search — Phase 2A executes nothing.
"""
from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.knowledge_production import (
    DiscoveryRunItem,
    DiscoveryRunListResponse,
)

_MAX_LIMIT = 200
_DEFAULT_LIMIT = 50

_SELECT_COLUMNS = """
    r.run_id,
    e.entity_id AS seed_entity_id,
    r.discovery_type,
    r.status,
    r.outcome,
    r.provider,
    r.model_name,
    r.prompt_key,
    r.prompt_version,
    r.query_strategy_version,
    r.created_by,
    r.created_at,
    r.started_at,
    r.finished_at,
    r.error_code,
    r.error_message
"""

# Public identity (entity_id) -> internal shared PK -> the run's FK target.
# The public API is entity_id based; seed_region_pk never leaves the backend.
_FROM = """
    FROM knowledge_discovery_runs r
    JOIN brain_regions b ON b.entity_pk = r.seed_region_pk
    JOIN kg_entities e ON e.entity_pk = b.entity_pk
"""


def normalize_limit(limit: int | None) -> int:
    """Clamp the page size. Never allow an unbounded list request."""
    if limit is None or limit <= 0:
        return _DEFAULT_LIMIT
    return min(int(limit), _MAX_LIMIT)


def normalize_offset(offset: int | None) -> int:
    if offset is None or offset < 0:
        return 0
    return int(offset)


def build_run_filters(
    *,
    discovery_type: str | None = None,
    status: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Build the run WHERE clause + bound parameters. Pure function (unit-testable)."""
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if discovery_type:
        clauses.append("r.discovery_type = :discovery_type")
        params["discovery_type"] = discovery_type
    if status:
        clauses.append("r.status = :status")
        params["status"] = status
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def row_to_item(row: Mapping[str, Any]) -> DiscoveryRunItem:
    """Map one DB row to the run DTO. Pure function (unit-testable).

    ``run_id`` arrives as a ``uuid.UUID``; the DTO exposes it as a string.
    """
    return DiscoveryRunItem(
        run_id=str(row["run_id"]),
        seed_entity_id=row["seed_entity_id"],
        discovery_type=row["discovery_type"],
        status=row["status"],
        outcome=row["outcome"],
        provider=row["provider"],
        model_name=row["model_name"],
        prompt_key=row["prompt_key"],
        prompt_version=row["prompt_version"],
        query_strategy_version=row["query_strategy_version"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        error_code=row["error_code"],
        error_message=row["error_message"],
    )


async def resolve_seed_region_pk(session: AsyncSession, entity_id: str) -> int | None:
    """Resolve a public BrainRegion identity to its internal shared PK. SELECT only.

    Returns None when no such BrainRegion exists. 'No such region' and 'no runs
    for this region' are deliberately different facts and must not be conflated.
    """
    return (
        await session.execute(
            text(
                "SELECT b.entity_pk FROM brain_regions b"
                " JOIN kg_entities e ON e.entity_pk = b.entity_pk"
                " WHERE e.entity_id = :entity_id"
            ),
            {"entity_id": entity_id},
        )
    ).scalar_one_or_none()


async def list_discovery_runs_for_region(
    session: AsyncSession,
    *,
    entity_id: str,
    discovery_type: str | None = None,
    status: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> DiscoveryRunListResponse | None:
    """Discovery Runs recorded for one BrainRegion, newest first. SELECT only.

    Returns None when the BrainRegion itself does not exist (the caller maps
    that to 404); an existing region with no runs returns an empty page.
    """
    if await resolve_seed_region_pk(session, entity_id) is None:
        return None

    where, params = build_run_filters(discovery_type=discovery_type, status=status)
    # Scope to the seed by public identity, so the WHERE never leaks entity_pk.
    scope = " WHERE e.entity_id = :entity_id"
    filters = scope + (
        " AND " + where.removeprefix(" WHERE ") if where else ""
    )

    total = int(
        (
            await session.execute(
                text("SELECT COUNT(*)" + _FROM + filters),
                {**params, "entity_id": entity_id},
            )
        ).scalar_one()
    )
    rows = (
        await session.execute(
            text(
                "SELECT " + _SELECT_COLUMNS + _FROM + filters
                + " ORDER BY r.created_at DESC, r.run_id LIMIT :limit OFFSET :offset"
            ),
            {
                **params,
                "entity_id": entity_id,
                "limit": normalize_limit(limit),
                "offset": normalize_offset(offset),
            },
        )
    ).mappings().all()
    return DiscoveryRunListResponse(items=[row_to_item(r) for r in rows], total=total)


async def get_discovery_run(
    session: AsyncSession, run_id: str
) -> DiscoveryRunItem | None:
    """One Discovery Run by its public run_id. SELECT only. None when absent."""
    row = (
        await session.execute(
            text("SELECT " + _SELECT_COLUMNS + _FROM + " WHERE r.run_id = :run_id"),
            {"run_id": run_id},
        )
    ).mappings().one_or_none()
    return row_to_item(row) if row is not None else None
