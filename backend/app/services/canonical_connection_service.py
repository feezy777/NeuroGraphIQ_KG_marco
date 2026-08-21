"""Canonical Connection service (CN1.2-1: schema/model/service foundation).

Responsibilities:
- CRUD for canonical_connections (concept-neutral connection layer)
- identity: ``(source_region_id, target_region_id, connection_type)`` —
  direction is NOT part of identity (no reverse double-write; direction
  semantics live in ``directionality_policy``)
- endpoint validation (regions exist, species consistent)
- integrity checker for the canonical connection layer

Hard boundaries (CN1.2): never writes ``mirror_region_connections``, never
generates triples, never performs inference. This module only establishes
the canonical connection concept infrastructure.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical_connection import CanonicalConnection
from app.models.canonical_region import CanonicalBrainRegion
from app.schemas.canonical_connection import CanonicalConnectionCreate

_VALID_CONNECTION_TYPES = {"structural", "functional", "projection", "association", "coactivation", "uncertain"}
_VALID_DIRECTIONALITY_POLICIES = {"directed", "bidirectional", "undirected", "unspecified"}
_VALID_SPECIES = {"human", "mouse", "unknown"}
_VALID_STATUSES = {"proposed", "active", "deprecated"}
_VALID_GRANULARITY_LEVELS = {"whole_brain", "macro", "clinical", "research", "fine", "ultra_fine"}
_CONNECTION_CODE_PREFIX = "ng:cn:"
_MAX_CODE_RETRIES = 1000


class CanonicalConnectionError(ValueError):
    """Domain error for canonical connection operations."""


def normalize_connection_key(
    source_region_id: uuid.UUID, target_region_id: uuid.UUID, connection_type: str
) -> tuple[uuid.UUID, uuid.UUID, str]:
    """Unique identity of a canonical connection.

    ``(source canonical id, target canonical id, connection_type)``. The key
    is directional (A->B and B->A are distinct keys); reverse semantics are
    expressed via ``directionality_policy='bidirectional'`` on one row, never
    by writing a second mirrored row.
    """
    if connection_type not in _VALID_CONNECTION_TYPES:
        raise CanonicalConnectionError(f"invalid connection_type: {connection_type}")
    return (source_region_id, target_region_id, connection_type)


def _region_slug(region_code: str) -> str:
    return region_code.removeprefix("ng:br:")


async def _generate_connection_code(
    session: AsyncSession,
    source: CanonicalBrainRegion,
    target: CanonicalBrainRegion,
    connection_type: str,
) -> str:
    base = f"{_CONNECTION_CODE_PREFIX}{connection_type}_{_region_slug(source.region_code)}_to_{_region_slug(target.region_code)}"
    candidate = base
    for i in range(2, _MAX_CODE_RETRIES + 2):
        existing = (
            await session.execute(
                select(CanonicalConnection.id).where(CanonicalConnection.connection_code == candidate)
            )
        ).first()
        if existing is None:
            return candidate
        candidate = f"{base}_{i}"
    raise CanonicalConnectionError("could not generate a unique connection_code")


async def validate_endpoint(
    session: AsyncSession,
    source_region_id: uuid.UUID,
    target_region_id: uuid.UUID,
    species: str,
) -> tuple[CanonicalBrainRegion, CanonicalBrainRegion]:
    """Validate that both endpoint regions exist and species are consistent.

    Returns the loaded (source, target) region rows. Raises
    ``CanonicalConnectionError`` when an endpoint is missing, the two
    endpoints have conflicting species, or the connection species conflicts
    with a concrete endpoint species ('unknown' endpoints are compatible
    with anything).
    """
    source = await session.get(CanonicalBrainRegion, source_region_id)
    if source is None:
        raise CanonicalConnectionError(f"source canonical region not found: {source_region_id}")
    target = await session.get(CanonicalBrainRegion, target_region_id)
    if target is None:
        raise CanonicalConnectionError(f"target canonical region not found: {target_region_id}")
    for name, region in (("source", source), ("target", target)):
        if region.species != "unknown" and species != "unknown" and region.species != species:
            raise CanonicalConnectionError(
                f"species mismatch: connection species '{species}' vs {name} region "
                f"'{region.region_code}' species '{region.species}'"
            )
    if source.species != "unknown" and target.species != "unknown" and source.species != target.species:
        raise CanonicalConnectionError(
            f"endpoint species conflict: source '{source.species}' vs target '{target.species}'"
        )
    return source, target


async def check_duplicate(
    session: AsyncSession,
    source_region_id: uuid.UUID,
    target_region_id: uuid.UUID,
    connection_type: str,
) -> CanonicalConnection | None:
    """Return the existing connection with the same identity key, if any."""
    return (
        await session.execute(
            select(CanonicalConnection).where(
                CanonicalConnection.source_region_id == source_region_id,
                CanonicalConnection.target_region_id == target_region_id,
                CanonicalConnection.connection_type == connection_type,
            )
        )
    ).scalar_one_or_none()


async def create_canonical_connection(
    session: AsyncSession, payload: CanonicalConnectionCreate
) -> CanonicalConnection:
    """Create one canonical connection.

    ``connection_code`` is auto-generated (``ng:cn:<type>_<src>_to_<tgt>``)
    when not supplied. Endpoints must exist with consistent species; the
    identity key ``(source, target, connection_type)`` must not already exist;
    self-loops are rejected.
    """
    source, target = await validate_endpoint(
        session, payload.source_region_id, payload.target_region_id, payload.species
    )
    if source.id == target.id:
        raise CanonicalConnectionError(
            f"self-loop rejected: source and target are the same region ({source.region_code})"
        )
    dup = await check_duplicate(
        session, payload.source_region_id, payload.target_region_id, payload.connection_type
    )
    if dup is not None:
        raise CanonicalConnectionError(
            f"duplicate connection: {source.region_code} -> {target.region_code} "
            f"({payload.connection_type}) already exists as {dup.connection_code}"
        )
    if payload.connection_code:
        if not payload.connection_code.startswith(_CONNECTION_CODE_PREFIX):
            raise CanonicalConnectionError(
                f"connection_code must follow the {_CONNECTION_CODE_PREFIX}* pattern"
            )
        existing = (
            await session.execute(
                select(CanonicalConnection.id).where(
                    CanonicalConnection.connection_code == payload.connection_code
                )
            )
        ).first()
        if existing is not None:
            raise CanonicalConnectionError(
                f"connection_code already exists: {payload.connection_code}"
            )
        code = payload.connection_code
    else:
        code = await _generate_connection_code(session, source, target, payload.connection_type)
    connection = CanonicalConnection(**payload.model_dump(exclude={"connection_code"}), connection_code=code)
    session.add(connection)
    await session.flush()
    return connection


async def get_canonical_connection(
    session: AsyncSession, connection_id: uuid.UUID
) -> CanonicalConnection | None:
    return await session.get(CanonicalConnection, connection_id)


async def get_canonical_connection_by_code(
    session: AsyncSession, connection_code: str
) -> CanonicalConnection | None:
    return (
        await session.execute(
            select(CanonicalConnection).where(CanonicalConnection.connection_code == connection_code)
        )
    ).scalar_one_or_none()


async def list_canonical_connections(
    session: AsyncSession,
    *,
    connection_type: str | None = None,
    status: str | None = None,
    species: str | None = None,
) -> list[CanonicalConnection]:
    stmt = select(CanonicalConnection).order_by(
        CanonicalConnection.connection_code
    )
    if connection_type:
        stmt = stmt.where(CanonicalConnection.connection_type == connection_type)
    if status:
        stmt = stmt.where(CanonicalConnection.status == status)
    if species:
        stmt = stmt.where(CanonicalConnection.species == species)
    return list((await session.execute(stmt)).scalars().all())


# --------------------------------------------------------------------------- #
# Integrity checker
# --------------------------------------------------------------------------- #


async def check_canonical_connection_integrity(session: AsyncSession) -> dict[str, Any]:
    """Audit the canonical_connections layer without modifying anything.

    Checks: orphan endpoint region, self loop, duplicate identity key,
    duplicate connection_code, invalid type, invalid directionality policy,
    invalid status/granularity, species mismatch (connection vs endpoints).
    DB-level CHECK/UNIQUE/FK constraints already prevent most of these —
    the checker is a defensive second opinion, plus reports the untouched
    mirror_region_connections row count.
    """
    issues: list[dict[str, str]] = []

    rows = (await session.execute(text(
        "SELECT cc.id, cc.connection_code, cc.source_region_id, cc.target_region_id, "
        "cc.connection_type, cc.directionality_policy, cc.species, cc.granularity_level, "
        "cc.status, cc.replaced_by_connection_id, "
        "src.species AS source_species, tgt.species AS target_species "
        "FROM canonical_connections cc "
        "LEFT JOIN canonical_brain_regions src ON src.id = cc.source_region_id "
        "LEFT JOIN canonical_brain_regions tgt ON tgt.id = cc.target_region_id"
    ))).mappings().all()

    counts: dict[str, int] = {
        "total": len(rows),
        "orphan_endpoint_count": 0,
        "self_loop_count": 0,
        "duplicate_key_count": 0,
        "duplicate_code_count": 0,
        "invalid_type_count": 0,
        "invalid_directionality_count": 0,
        "invalid_status_count": 0,
        "invalid_granularity_count": 0,
        "species_mismatch_count": 0,
    }
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_directionality: dict[str, int] = {}

    for row in rows:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
        by_type[row["connection_type"]] = by_type.get(row["connection_type"], 0) + 1
        by_directionality[row["directionality_policy"]] = (
            by_directionality.get(row["directionality_policy"], 0) + 1
        )
        if row["source_species"] is None or row["target_species"] is None:
            counts["orphan_endpoint_count"] += 1
            issues.append({
                "severity": "critical",
                "code": "ORPHAN_ENDPOINT",
                "message": f"connection {row['connection_code']} references a missing canonical region",
            })
        if row["source_region_id"] == row["target_region_id"]:
            counts["self_loop_count"] += 1
            issues.append({
                "severity": "critical",
                "code": "SELF_LOOP",
                "message": f"connection {row['connection_code']} has source == target",
            })
        if row["connection_type"] not in _VALID_CONNECTION_TYPES:
            counts["invalid_type_count"] += 1
            issues.append({
                "severity": "high",
                "code": "INVALID_TYPE",
                "message": f"connection {row['connection_code']} has invalid connection_type '{row['connection_type']}'",
            })
        if row["directionality_policy"] not in _VALID_DIRECTIONALITY_POLICIES:
            counts["invalid_directionality_count"] += 1
            issues.append({
                "severity": "high",
                "code": "INVALID_DIRECTIONALITY",
                "message": f"connection {row['connection_code']} has invalid directionality_policy '{row['directionality_policy']}'",
            })
        if row["status"] not in _VALID_STATUSES:
            counts["invalid_status_count"] += 1
            issues.append({
                "severity": "medium",
                "code": "INVALID_STATUS",
                "message": f"connection {row['connection_code']} has invalid status '{row['status']}'",
            })
        if row["granularity_level"] not in _VALID_GRANULARITY_LEVELS:
            counts["invalid_granularity_count"] += 1
            issues.append({
                "severity": "medium",
                "code": "INVALID_GRANULARITY",
                "message": f"connection {row['connection_code']} has invalid granularity_level '{row['granularity_level']}'",
            })
        if row["source_species"] is not None and row["target_species"] is not None:
            for name, region_species in (("source", row["source_species"]), ("target", row["target_species"])):
                if region_species != "unknown" and row["species"] != "unknown" and region_species != row["species"]:
                    counts["species_mismatch_count"] += 1
                    issues.append({
                        "severity": "high",
                        "code": "SPECIES_MISMATCH",
                        "message": (
                            f"connection {row['connection_code']} species '{row['species']}' "
                            f"conflicts with {name} region species '{region_species}'"
                        ),
                    })

    dup_keys = (await session.execute(text(
        "SELECT count(*) FROM (SELECT source_region_id, target_region_id, connection_type "
        "FROM canonical_connections GROUP BY 1,2,3 HAVING count(*)>1) d"
    ))).scalar_one()
    if dup_keys:
        counts["duplicate_key_count"] = int(dup_keys)
        issues.append({
            "severity": "critical",
            "code": "DUPLICATE_KEY",
            "message": f"{dup_keys} duplicate (source,target,type) identity groups",
        })
    dup_codes = (await session.execute(text(
        "SELECT count(*) FROM (SELECT connection_code FROM canonical_connections "
        "GROUP BY connection_code HAVING count(*)>1) d"
    ))).scalar_one()
    if dup_codes:
        counts["duplicate_code_count"] = int(dup_codes)
        issues.append({
            "severity": "critical",
            "code": "DUPLICATE_CODE",
            "message": f"{dup_codes} duplicate connection_code values",
        })

    mirror_count = int((await session.execute(
        text("SELECT count(*) FROM mirror_region_connections")
    )).scalar_one())
    counts["mirror_connections_untouched"] = mirror_count

    counts.update({f"status_{k}": v for k, v in by_status.items()})
    counts.update({f"type_{k}": v for k, v in by_type.items()})
    counts.update({f"direction_{k}": v for k, v in by_directionality.items()})

    return {
        "ok": not any(i["severity"] in ("critical", "high") for i in issues),
        "counts": counts,
        "issues": issues,
    }
