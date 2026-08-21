"""Canonical BrainRegion service (BR1: L0/L1 Macro Backbone).

Responsibilities:
- CRUD for canonical_brain_regions / canonical_region_hierarchy (part_of only)
- hierarchy traversal (ancestors/descendants via recursive CTE, depth-agnostic)
- candidate -> canonical grounding (exact/close only writes FK; species guard)
- integrity checker for the canonical layer
- read-only readiness helpers for future Connection (CN1) / Circuit (CR1) work
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical_region import CanonicalBrainRegion, CanonicalRegionHierarchy
from app.models.candidate import CandidateBrainRegion
from app.models.canonical_circuit import CanonicalCircuit, CanonicalCircuitFunction, CanonicalCircuitRegion
from app.models.canonical_connection import CanonicalConnection
from app.models.multiscale import (
    AtlasRegionMapping,
    AtlasRegionResource,
    RegionCellAlignment,
    RegionMolecularAlignment,
)
from app.models.ontology import OntologyAlignmentCandidate, OntologyTerm
from app.models.resource import AtlasResource
from app.schemas.canonical_region import CanonicalRegionCreate, CanonicalRegionHierarchyCreate

# Fallback level order (single source of truth when the vocabulary registry is
# empty, e.g. offline unit tests). Production order is read from
# ontology_vocabularies (vocab_type='granularity_level', status='active',
# ordered by COALESCE(level_order, seq)).
# BR3 multiscale: canonical five-band scale macro -> meso -> subregion ->
# cyto -> molecular, with legacy compat levels interleaved (whole_brain L0,
# clinical L2, research L4, fine L6, ultra_fine L8 — all stay assignable so
# existing data and tests keep working; see granularity_level_compat_map).
_GRANULARITY_LEVEL_ORDER: dict[str, int] = {
    "whole_brain": 0,
    "macro": 1,
    "clinical": 2,
    "meso": 3,
    "research": 4,
    "subregion": 5,
    "fine": 6,
    "cyto": 7,
    "ultra_fine": 8,
    "molecular": 9,
}

_VALID_SPECIES = {"human", "mouse", "unknown"}
_VALID_HEMISPHERE_POLICIES = {"bilateral", "lateralized", "midline_unpaired"}
_FK_WRITABLE_MATCH_TYPES = {"exact", "close"}


class CanonicalRegionError(ValueError):
    """Domain error for canonical region operations."""


async def _load_level_order(session: AsyncSession) -> dict[str, int]:
    rows = (
        await session.execute(
            text(
                "SELECT code, level_order, seq FROM ontology_vocabularies "
                "WHERE vocab_type='granularity_level' AND status='active' "
                "ORDER BY COALESCE(level_order, seq), level_order"
            )
        )
    ).all()
    order = {str(code): int(lo) for code, lo, _ in rows if lo is not None}
    # levels without an explicit level_order keep their row position, starting
    # after the highest explicit order so positions never collide with it
    position = max(order.values(), default=-1) + 1
    for code, lo, _ in rows:
        if code not in order:
            order[str(code)] = position
        position += 1
    return order if order else dict(_GRANULARITY_LEVEL_ORDER)


def level_order(region: CanonicalBrainRegion, order: dict[str, int]) -> int:
    return order.get(region.granularity_level, 999)


# --------------------------------------------------------------------------- #
# Canonical regions
# --------------------------------------------------------------------------- #


async def create_canonical_region(
    session: AsyncSession, payload: CanonicalRegionCreate
) -> CanonicalBrainRegion:
    """Create one canonical region. region_code is the stable identity."""
    if not payload.region_code.startswith("ng:br:"):
        raise CanonicalRegionError("region_code must follow the ng:br:* pattern")
    existing = (
        await session.execute(
            select(CanonicalBrainRegion).where(CanonicalBrainRegion.region_code == payload.region_code)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise CanonicalRegionError(f"region_code already exists: {payload.region_code}")
    await _validate_vocab(payload.species, payload.hemisphere_policy, payload.granularity_level)
    region = CanonicalBrainRegion(**payload.model_dump())
    session.add(region)
    await session.flush()
    return region


async def _validate_vocab(species: str, hemisphere_policy: str, granularity_level: str) -> None:
    if species not in _VALID_SPECIES:
        raise CanonicalRegionError(f"invalid species: {species}")
    if hemisphere_policy not in _VALID_HEMISPHERE_POLICIES:
        raise CanonicalRegionError(f"invalid hemisphere_policy: {hemisphere_policy}")
    if granularity_level not in _GRANULARITY_LEVEL_ORDER:
        raise CanonicalRegionError(f"invalid granularity_level: {granularity_level}")


async def get_canonical_region(
    session: AsyncSession, region_id: uuid.UUID
) -> CanonicalBrainRegion | None:
    return await session.get(CanonicalBrainRegion, region_id)


async def get_canonical_region_by_code(
    session: AsyncSession, region_code: str
) -> CanonicalBrainRegion | None:
    return (
        await session.execute(
            select(CanonicalBrainRegion).where(CanonicalBrainRegion.region_code == region_code)
        )
    ).scalar_one_or_none()


async def list_canonical_regions(
    session: AsyncSession,
    *,
    granularity_level: str | None = None,
    status: str | None = None,
    species: str | None = None,
) -> list[CanonicalBrainRegion]:
    stmt = select(CanonicalBrainRegion).order_by(CanonicalBrainRegion.granularity_level, CanonicalBrainRegion.canonical_name_en)
    if granularity_level:
        stmt = stmt.where(CanonicalBrainRegion.granularity_level == granularity_level)
    if status:
        stmt = stmt.where(CanonicalBrainRegion.status == status)
    if species:
        stmt = stmt.where(CanonicalBrainRegion.species == species)
    return list((await session.execute(stmt)).scalars().all())


# --------------------------------------------------------------------------- #
# Hierarchy (part_of only)
# --------------------------------------------------------------------------- #


async def add_part_of_edge(
    session: AsyncSession, payload: CanonicalRegionHierarchyCreate
) -> CanonicalRegionHierarchy:
    """Add child --part_of--> parent edge with integrity guards."""
    child = await session.get(CanonicalBrainRegion, payload.child_region_id)
    parent = await session.get(CanonicalBrainRegion, payload.parent_region_id)
    if child is None or parent is None:
        raise CanonicalRegionError("child or parent canonical region not found")
    if child.id == parent.id:
        raise CanonicalRegionError("self-loop rejected: child cannot be its own parent")
    order = await _load_level_order(session)
    if level_order(child, order) <= level_order(parent, order):
        raise CanonicalRegionError(
            "invalid level direction: child.level_order must be > parent.level_order "
            f"({child.granularity_level} -> {parent.granularity_level} rejected)"
        )
    # Duplicate edge (also enforced by UNIQUE constraint).
    dup = (
        await session.execute(
            select(CanonicalRegionHierarchy).where(
                CanonicalRegionHierarchy.child_region_id == child.id,
                CanonicalRegionHierarchy.parent_region_id == parent.id,
            )
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise CanonicalRegionError("duplicate edge rejected: edge already exists")
    # Cycle: parent must not already be (a descendant of) child.
    if parent.id in {r["id"] for r in await get_descendants(session, child.id)}:
        raise CanonicalRegionError("cycle rejected: parent is already a descendant of child")
    edge = CanonicalRegionHierarchy(
        child_region_id=child.id,
        parent_region_id=parent.id,
        predicate=payload.predicate,
        status=payload.status,
        source=payload.source,
        confidence=payload.confidence,
        provenance_json=payload.provenance_json,
        created_by=payload.created_by,
    )
    session.add(edge)
    await session.flush()
    return edge


async def get_parents(session: AsyncSession, region_id: uuid.UUID) -> list[CanonicalBrainRegion]:
    rows = (
        await session.execute(
            select(CanonicalRegionHierarchy.parent_region_id).where(
                CanonicalRegionHierarchy.child_region_id == region_id
            )
        )
    ).scalars().all()
    if not rows:
        return []
    return list(
        (await session.execute(select(CanonicalBrainRegion).where(CanonicalBrainRegion.id.in_(rows)))).scalars().all()
    )


async def get_children(session: AsyncSession, region_id: uuid.UUID) -> list[CanonicalBrainRegion]:
    rows = (
        await session.execute(
            select(CanonicalRegionHierarchy.child_region_id).where(
                CanonicalRegionHierarchy.parent_region_id == region_id
            )
        )
    ).scalars().all()
    if not rows:
        return []
    children = list(
        (await session.execute(select(CanonicalBrainRegion).where(CanonicalBrainRegion.id.in_(rows)))).scalars().all()
    )
    order = await _load_level_order(session)
    children.sort(key=lambda r: (level_order(r, order), r.region_code))
    return children


# --------------------------------------------------------------------------- #
# Browser queries (tree explorer — read-only)
# --------------------------------------------------------------------------- #


async def get_roots(session: AsyncSession) -> list[CanonicalBrainRegion]:
    """Top-level regions: no active part_of parent edge. Sorted by level order.

    Renders the true edge structure — a clinical node parented directly to the
    whole_brain root (e.g. ventricles) appears as a root child alongside L1
    macro nodes, not as a depth-2 node.
    """
    has_active_parent = (
        select(CanonicalRegionHierarchy.id)
        .where(
            CanonicalRegionHierarchy.child_region_id == CanonicalBrainRegion.id,
            CanonicalRegionHierarchy.status == "active",
        )
        .exists()
    )
    roots = list(
        (
            await session.execute(
                select(CanonicalBrainRegion).where(~has_active_parent)
            )
        ).scalars().all()
    )
    order = await _load_level_order(session)
    roots.sort(key=lambda r: (level_order(r, order), r.region_code))
    return roots


async def get_region_connections(
    session: AsyncSession, region_id: uuid.UUID
) -> list[dict[str, Any]]:
    """Connections touching the region: outgoing (region is source) first,
    then incoming (region is target), each ordered by connection_code."""
    results: list[dict[str, Any]] = []

    outgoing = (
        await session.execute(
            select(CanonicalConnection, CanonicalBrainRegion)
            .join(CanonicalBrainRegion, CanonicalBrainRegion.id == CanonicalConnection.target_region_id)
            .where(CanonicalConnection.source_region_id == region_id)
            .order_by(CanonicalConnection.connection_code)
        )
    ).all()
    for conn, endpoint in outgoing:
        results.append(_connection_row(conn, endpoint, "outgoing"))

    incoming = (
        await session.execute(
            select(CanonicalConnection, CanonicalBrainRegion)
            .join(CanonicalBrainRegion, CanonicalBrainRegion.id == CanonicalConnection.source_region_id)
            .where(CanonicalConnection.target_region_id == region_id)
            .order_by(CanonicalConnection.connection_code)
        )
    ).all()
    for conn, endpoint in incoming:
        results.append(_connection_row(conn, endpoint, "incoming"))

    return results


def _connection_row(
    conn: CanonicalConnection, endpoint: CanonicalBrainRegion, direction: str
) -> dict[str, Any]:
    return {
        "connection_id": conn.id,
        "connection_code": conn.connection_code,
        "connection_type": conn.connection_type,
        "directionality_policy": conn.directionality_policy,
        "status": conn.status,
        "confidence": float(conn.confidence) if conn.confidence is not None else None,
        "direction": direction,
        "endpoint_region": {
            "id": endpoint.id,
            "region_code": endpoint.region_code,
            "canonical_name_en": endpoint.canonical_name_en,
            "canonical_name_cn": endpoint.canonical_name_cn,
            "granularity_level": endpoint.granularity_level,
        },
    }


async def get_region_circuits(
    session: AsyncSession, region_id: uuid.UUID
) -> list[dict[str, Any]]:
    """Circuits the region participates in, with its membership role."""
    rows = (
        await session.execute(
            select(CanonicalCircuit, CanonicalCircuitRegion)
            .join(CanonicalCircuitRegion, CanonicalCircuitRegion.circuit_id == CanonicalCircuit.id)
            .where(CanonicalCircuitRegion.region_id == region_id)
            .order_by(CanonicalCircuitRegion.order_index, CanonicalCircuit.circuit_code)
        )
    ).all()
    return [
        {
            "circuit_id": circuit.id,
            "circuit_code": circuit.circuit_code,
            "canonical_name_en": circuit.canonical_name_en,
            "circuit_type": circuit.circuit_type,
            "status": circuit.status,
            "role": member.role,
            "order_index": member.order_index,
            "confidence": float(member.confidence) if member.confidence is not None else None,
        }
        for circuit, member in rows
    ]


async def get_region_functions(
    session: AsyncSession, region_id: uuid.UUID
) -> list[dict[str, Any]]:
    """Function terms reachable through the region's circuits.

    The canonical layer has no region -> function direct edge; functions are
    derived via canonical_circuit_regions -> canonical_circuit_functions ->
    ontology_terms. The UI labels this 经回路关联 (via circuits).

    Fallback: 聚合区（如 前额叶）自身无回路时，取其直接亚区（part_of 子区）的
    回路功能；自身有回路的脑区行为不变。
    """
    rows = await _functions_by_circuits(
        session,
        select(CanonicalCircuitRegion.circuit_id)
        .where(CanonicalCircuitRegion.region_id == region_id)
        .scalar_subquery(),
    )
    if not rows:
        child_ids = (
            select(CanonicalRegionHierarchy.child_region_id)
            .where(
                CanonicalRegionHierarchy.parent_region_id == region_id,
                CanonicalRegionHierarchy.status == "active",
            )
            .scalar_subquery()
        )
        rows = await _functions_by_circuits(
            session,
            select(CanonicalCircuitRegion.circuit_id)
            .where(CanonicalCircuitRegion.region_id.in_(child_ids))
            .scalar_subquery(),
        )
    return rows


async def _functions_by_circuits(
    session: AsyncSession, circuit_ids
) -> list[dict[str, Any]]:
    """按回路集合取功能术语（get_region_functions 的共享查询体）。"""
    rows = (
        await session.execute(
            select(CanonicalCircuitFunction, CanonicalCircuit, OntologyTerm)
            .join(CanonicalCircuit, CanonicalCircuit.id == CanonicalCircuitFunction.circuit_id)
            .join(OntologyTerm, OntologyTerm.id == CanonicalCircuitFunction.function_term_id)
            .where(CanonicalCircuitFunction.circuit_id.in_(circuit_ids))
            .order_by(CanonicalCircuit.circuit_code, OntologyTerm.term_code)
        )
    ).all()
    return [
        {
            "function_term_id": term.id,
            "term_code": term.term_code,
            "canonical_term_en": term.canonical_term_en,
            "canonical_term_cn": term.canonical_term_cn,
            "relation_type": ccf.relation_type,
            "circuit_code": circuit.circuit_code,
            "circuit_name": circuit.canonical_name_en,
            "confidence": float(ccf.confidence) if ccf.confidence is not None else None,
        }
        for ccf, circuit, term in rows
    ]


async def get_region_candidates(
    session: AsyncSession, region_id: uuid.UUID
) -> list[dict[str, Any]]:
    """Candidate anchors grounded to this canonical region (provenance)."""
    rows = (
        await session.execute(
            select(CandidateBrainRegion)
            .where(CandidateBrainRegion.canonical_region_id == region_id)
            .order_by(CandidateBrainRegion.source_atlas, CandidateBrainRegion.created_at)
        )
    ).scalars().all()
    return [
        {
            "candidate_id": c.id,
            "source_atlas": c.source_atlas,
            "source_version": c.source_version,
            "raw_name": c.raw_name,
            "std_name": c.std_name,
            "en_name": c.en_name,
            "cn_name": c.cn_name,
            "laterality": c.laterality,
            "granularity_level": c.granularity_level,
            "granularity_family": c.granularity_family,
            "alignment_status": c.alignment_status,
            "candidate_status": c.candidate_status,
            "uberon_iri": c.uberon_iri,
            "nifstd_iri": c.nifstd_iri,
            "created_at": c.created_at,
        }
        for c in rows
    ]


async def get_ancestors(session: AsyncSession, region_id: uuid.UUID) -> list[dict[str, Any]]:
    """All ancestors via recursive CTE (depth 1 = direct parent). Depth-agnostic."""
    rows = (
        await session.execute(
            text(
                """
                WITH RECURSIVE up AS (
                    SELECT h.parent_region_id AS id, 1 AS depth
                    FROM canonical_region_hierarchy h
                    WHERE h.child_region_id = :rid
                    UNION ALL
                    SELECT h.parent_region_id, up.depth + 1
                    FROM canonical_region_hierarchy h
                    JOIN up ON h.child_region_id = up.id
                )
                SELECT r.id, r.region_code, r.canonical_name_en, r.granularity_level,
                       r.species, up.depth
                FROM up
                JOIN canonical_brain_regions r ON r.id = up.id
                ORDER BY up.depth
                """
            ),
            {"rid": str(region_id)},
        )
    ).all()
    return [_row_to_tree_item(row) for row in rows]


async def get_descendants(session: AsyncSession, region_id: uuid.UUID) -> list[dict[str, Any]]:
    """All descendants via recursive CTE (depth 1 = direct child). Depth-agnostic."""
    rows = (
        await session.execute(
            text(
                """
                WITH RECURSIVE down AS (
                    SELECT h.child_region_id AS id, 1 AS depth
                    FROM canonical_region_hierarchy h
                    WHERE h.parent_region_id = :rid
                    UNION ALL
                    SELECT h.child_region_id, down.depth + 1
                    FROM canonical_region_hierarchy h
                    JOIN down ON h.parent_region_id = down.id
                )
                SELECT r.id, r.region_code, r.canonical_name_en, r.granularity_level,
                       r.species, down.depth
                FROM down
                JOIN canonical_brain_regions r ON r.id = down.id
                ORDER BY down.depth
                """
            ),
            {"rid": str(region_id)},
        )
    ).all()
    return [_row_to_tree_item(row) for row in rows]


def _row_to_tree_item(row: Any) -> dict[str, Any]:
    return {
        "id": row[0],
        "region_code": row[1],
        "canonical_name_en": row[2],
        "granularity_level": row[3],
        "species": row[4],
        "depth": int(row[5]),
    }


# --------------------------------------------------------------------------- #
# Candidate grounding
# --------------------------------------------------------------------------- #


async def _candidate_species(session: AsyncSession, candidate: CandidateBrainRegion) -> str | None:
    resource = await session.get(AtlasResource, candidate.resource_id)
    return getattr(resource, "species", None) if resource is not None else None


async def resolve_candidate_to_canonical(
    session: AsyncSession, candidate_id: uuid.UUID
) -> CanonicalBrainRegion | None:
    candidate = await session.get(CandidateBrainRegion, candidate_id)
    if candidate is None or candidate.canonical_region_id is None:
        return None
    return await session.get(CanonicalBrainRegion, candidate.canonical_region_id)


async def ground_candidate(
    session: AsyncSession,
    *,
    candidate_id: uuid.UUID,
    canonical_region_id: uuid.UUID,
    match_type: str,
    confidence: float | None = None,
    match_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ground an Atlas candidate to a canonical region.

    Only exact/close mappings write the FK. broader/narrower/uncertain/rejected
    must go through the alignment-candidate flow instead (no FK write).
    Cross-species grounding is rejected outright.
    """
    candidate = await session.get(CandidateBrainRegion, candidate_id)
    if candidate is None:
        raise CanonicalRegionError("candidate region not found")
    canonical = await session.get(CanonicalBrainRegion, canonical_region_id)
    if canonical is None:
        raise CanonicalRegionError("canonical region not found")
    if match_type not in _FK_WRITABLE_MATCH_TYPES:
        raise CanonicalRegionError(
            f"match_type '{match_type}' does not write the FK; "
            "use create_alignment_candidate() instead"
        )
    candidate_species = await _candidate_species(session, candidate)
    if candidate_species not in (None, "unknown") and canonical.species not in (None, "unknown"):
        if candidate_species != canonical.species:
            raise CanonicalRegionError(
                f"cross-species mapping rejected: candidate species={candidate_species} "
                f"!= canonical species={canonical.species}"
            )
    previous = candidate.canonical_region_id
    candidate.canonical_region_id = canonical.id
    if candidate.alignment_status == "not_aligned":
        candidate.alignment_status = "aligned"
    await session.flush()
    return {
        "candidate_id": str(candidate.id),
        "canonical_region_id": str(canonical.id),
        "canonical_region_code": canonical.region_code,
        "match_type": match_type,
        "confidence": confidence,
        "previous_canonical_region_id": str(previous) if previous else None,
        "laterality": candidate.laterality,
    }


async def create_alignment_candidate(
    session: AsyncSession,
    *,
    candidate_id: uuid.UUID,
    canonical_region_id: uuid.UUID,
    match_type: str,
    confidence: float | None = None,
    match_details: dict[str, Any] | None = None,
) -> OntologyAlignmentCandidate:
    """Record an ambiguous/non-writable mapping as a pending alignment candidate."""
    canonical = await session.get(CanonicalBrainRegion, canonical_region_id)
    if canonical is None:
        raise CanonicalRegionError("canonical region not found")
    row = OntologyAlignmentCandidate(
        target_type="region",
        target_id=candidate_id,
        external_system="ng:br",
        external_id=str(canonical.id),
        external_iri=canonical.region_code,
        external_label=canonical.canonical_name_en,
        match_type=match_type,
        match_score=confidence,
        match_details=match_details or {},
        status="pending",
    )
    session.add(row)
    await session.flush()
    return row


# --------------------------------------------------------------------------- #
# Readiness helpers (CN1 / CR1 — read-only, no writes, no inference)
# --------------------------------------------------------------------------- #


async def resolve_connection_endpoints_to_canonical(
    session: AsyncSession, connection: Any
) -> dict[str, Any]:
    """Read-only: map a mirror connection's candidate endpoints to canonicals."""
    source_candidate = await session.get(CandidateBrainRegion, connection.source_region_candidate_id)
    target_candidate = await session.get(CandidateBrainRegion, connection.target_region_candidate_id)
    source_canonical = await resolve_candidate_to_canonical(session, source_candidate.id) if source_candidate else None
    target_canonical = await resolve_candidate_to_canonical(session, target_candidate.id) if target_candidate else None

    def _cand(c: CandidateBrainRegion | None) -> dict[str, Any] | None:
        if c is None:
            return None
        return {
            "id": str(c.id),
            "en_name": c.en_name,
            "laterality": c.laterality,
            "source_atlas": c.source_atlas,
        }

    def _canon(c: CanonicalBrainRegion | None) -> dict[str, Any] | None:
        if c is None:
            return None
        return {
            "id": str(c.id),
            "region_code": c.region_code,
            "canonical_name_en": c.canonical_name_en,
            "granularity_level": c.granularity_level,
            "hemisphere_policy": c.hemisphere_policy,
            "species": c.species,
        }

    return {
        "source_candidate": _cand(source_candidate),
        "source_canonical": _canon(source_canonical),
        "target_candidate": _cand(target_candidate),
        "target_canonical": _canon(target_canonical),
        "resolved": source_canonical is not None and target_canonical is not None,
    }


async def circuit_participant_readiness(session: AsyncSession) -> dict[str, Any]:
    """Read-only audit: can circuit participants be resolved to canonicals?"""
    from app.models.mirror_kg import MirrorCircuitRegion

    ids = list(
        (
            await session.execute(
                text(
                    "SELECT DISTINCT region_candidate_id FROM mirror_circuit_regions "
                    "WHERE region_candidate_id IS NOT NULL "
                    "UNION "
                    "SELECT DISTINCT region_candidate_id FROM mirror_circuit_steps "
                    "WHERE region_candidate_id IS NOT NULL"
                )
            )
        ).scalars().all()
    )
    mapped = 0
    unmapped: list[dict[str, Any]] = []
    for cid in ids:
        canonical = await resolve_candidate_to_canonical(session, cid)
        if canonical is not None:
            mapped += 1
        else:
            unmapped.append({"candidate_id": str(cid)})
    return {
        "distinct_participant_candidates": len(ids),
        "resolved_to_canonical": mapped,
        "unresolved": len(ids) - mapped,
        "coverage": round(mapped / len(ids), 4) if ids else 0.0,
        "sample_unresolved": unmapped[:10],
    }


async def resolve_and_record_connection_alignment(
    session: AsyncSession, connection_id: uuid.UUID
) -> dict[str, Any]:
    """BR2-6: resolve a mirror connection's endpoints to canonicals and persist
    the alignment row (connection_region_alignment). The connection row itself
    is never modified.

    mapping_type: 'exact' both endpoints canonicalized / 'partial' one side /
    'none' neither.
    """
    from app.models.canonical_region import ConnectionRegionAlignment
    from app.models.mirror_kg import MirrorRegionConnection

    connection = await session.get(MirrorRegionConnection, connection_id)
    if connection is None:
        raise CanonicalRegionError("connection not found")
    result = await resolve_connection_endpoints_to_canonical(session, connection)
    src_can = result["source_canonical"]
    tgt_can = result["target_canonical"]
    if src_can is not None and tgt_can is not None:
        mapping_type = "exact"
    elif src_can is not None or tgt_can is not None:
        mapping_type = "partial"
    else:
        mapping_type = "none"

    existing = (
        await session.execute(
            select(ConnectionRegionAlignment).where(
                ConnectionRegionAlignment.connection_id == connection_id
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = ConnectionRegionAlignment(connection_id=connection_id)
        session.add(existing)
    existing.source_candidate_id = connection.source_region_candidate_id
    existing.source_canonical_region_id = (
        uuid.UUID(str(src_can["id"])) if src_can else None
    )
    existing.target_candidate_id = connection.target_region_candidate_id
    existing.target_canonical_region_id = (
        uuid.UUID(str(tgt_can["id"])) if tgt_can else None
    )
    existing.mapping_type = mapping_type
    existing.confidence = connection.confidence
    existing.source_atlas = connection.source_atlas
    existing.granularity_level = connection.granularity_level
    await session.flush()
    return {
        "connection_id": str(connection_id),
        "source_candidate_id": str(connection.source_region_candidate_id) if connection.source_region_candidate_id else None,
        "source_canonical_region_id": str(src_can["id"]) if src_can else None,
        "target_candidate_id": str(connection.target_region_candidate_id) if connection.target_region_candidate_id else None,
        "target_canonical_region_id": str(tgt_can["id"]) if tgt_can else None,
        "mapping_type": mapping_type,
        "confidence": float(connection.confidence) if connection.confidence is not None else None,
    }


# --------------------------------------------------------------------------- #
# Integrity checker
# --------------------------------------------------------------------------- #


async def check_canonical_brain_region_integrity(session: AsyncSession) -> dict[str, Any]:
    """Full integrity audit of the canonical BrainRegion layer (BR1)."""
    regions = list((await session.execute(select(CanonicalBrainRegion))).scalars().all())
    edges = list((await session.execute(select(CanonicalRegionHierarchy))).scalars().all())
    order = await _load_level_order(session)
    by_id = {r.id: r for r in regions}
    issues: list[dict[str, Any]] = []

    # --- concept-level checks ---
    seen_codes: dict[str, uuid.UUID] = {}
    seen_names: dict[tuple[str, str], uuid.UUID] = {}
    for r in regions:
        if r.region_code in seen_codes:
            issues.append({"severity": "critical", "code": "DUPLICATE_REGION_CODE",
                           "message": f"region_code duplicated: {r.region_code}"})
        else:
            seen_codes[r.region_code] = r.id
        key = (r.canonical_name_en.lower(), r.species)
        if key in seen_names:
            issues.append({"severity": "high", "code": "DUPLICATE_CANONICAL_CONCEPT",
                           "message": f"duplicate canonical concept: {r.canonical_name_en} ({r.species})"})
        else:
            seen_names[key] = r.id
        if r.species not in _VALID_SPECIES:
            issues.append({"severity": "high", "code": "INVALID_SPECIES",
                           "message": f"{r.region_code}: species={r.species}"})
        if r.hemisphere_policy not in _VALID_HEMISPHERE_POLICIES:
            issues.append({"severity": "high", "code": "INVALID_HEMISPHERE_POLICY",
                           "message": f"{r.region_code}: hemisphere_policy={r.hemisphere_policy}"})
        if r.granularity_level not in order:
            issues.append({"severity": "high", "code": "INVALID_GRANULARITY",
                           "message": f"{r.region_code}: granularity_level={r.granularity_level}"})
        if r.status not in ("proposed", "active", "deprecated", "merged"):
            issues.append({"severity": "medium", "code": "INVALID_STATUS",
                           "message": f"{r.region_code}: status={r.status}"})

    # --- hierarchy checks ---
    seen_edges: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for e in edges:
        if e.child_region_id == e.parent_region_id:
            issues.append({"severity": "critical", "code": "SELF_LOOP",
                           "message": f"self-loop edge {e.child_region_id}"})
        pair = (e.child_region_id, e.parent_region_id)
        if pair in seen_edges:
            issues.append({"severity": "high", "code": "DUPLICATE_EDGE",
                           "message": f"duplicate part_of edge {pair}"})
        seen_edges.add(pair)
        if e.child_region_id not in by_id:
            issues.append({"severity": "critical", "code": "ORPHAN_CHILD",
                           "message": f"edge references missing child {e.child_region_id}"})
        if e.parent_region_id not in by_id:
            issues.append({"severity": "critical", "code": "ORPHAN_PARENT",
                           "message": f"edge references missing parent {e.parent_region_id}"})
        child, parent = by_id.get(e.child_region_id), by_id.get(e.parent_region_id)
        if child is not None and parent is not None:
            if level_order(child, order) <= level_order(parent, order):
                issues.append({
                    "severity": "high", "code": "INVALID_LEVEL_DIRECTION",
                    "message": f"{child.region_code}({child.granularity_level}) part_of "
                               f"{parent.region_code}({parent.granularity_level}) — child must be finer",
                })

    # cycle detection (DFS over child->parent graph)
    cycles = _find_cycles(regions, edges)
    for c in cycles:
        issues.append({"severity": "critical", "code": "CYCLE",
                       "message": f"cycle: {' -> '.join(c)}"})

    # --- candidate mapping checks ---
    cand_rows = (
        await session.execute(
            text(
                "SELECT c.id, c.canonical_region_id, r.species AS resource_species "
                "FROM candidate_brain_regions c "
                "LEFT JOIN atlas_resources r ON r.id = c.resource_id"
            )
        )
    ).all()
    mapped_count = 0
    orphan_count = 0
    cross_species_count = 0
    for row in cand_rows:
        if row[1] is None:
            continue
        mapped_count += 1
        canonical = by_id.get(row[1])
        if canonical is None:
            orphan_count += 1
            issues.append({"severity": "critical", "code": "ORPHAN_CANONICAL_REF",
                           "message": f"candidate {row[0]} references missing canonical {row[1]}"})
        elif row[2] not in (None, "unknown") and canonical.species not in (None, "unknown") \
                and row[2] != canonical.species:
            cross_species_count += 1
            issues.append({"severity": "high", "code": "CROSS_SPECIES_MAPPING",
                           "message": f"candidate {row[0]} (species={row[2]}) mapped to "
                                       f"{canonical.region_code} (species={canonical.species})"})

    pending_alignment = int(
        (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM ontology_alignment_candidates "
                    "WHERE target_type='region' AND status='pending'"
                )
            )
        ).scalar_one()
    )

    isolated = [
        r.region_code
        for r in regions
        if all(e.child_region_id != r.id and e.parent_region_id != r.id for e in edges)
    ]

    # --- hemisphere conflict checks (BR2): anchored laterality vs policy ---
    anchor_rows = (
        await session.execute(
            text(
                "SELECT canonical_region_id, laterality, count(*) "
                "FROM candidate_brain_regions "
                "WHERE canonical_region_id IS NOT NULL "
                "GROUP BY canonical_region_id, laterality"
            )
        )
    ).all()
    anchors: dict[uuid.UUID, set[str]] = {}
    for row in anchor_rows:
        anchors.setdefault(row[0], set()).add(str(row[1]))
    for region in regions:
        lats = anchors.get(region.id, set())
        if region.hemisphere_policy == "midline_unpaired" and lats & {"left", "right"}:
            issues.append({
                "severity": "high", "code": "HEMISPHERE_CONFLICT",
                "message": f"{region.region_code} is midline_unpaired but anchored by "
                           f"lateralized candidates: {sorted(lats)}",
            })
        if region.hemisphere_policy == "lateralized":
            if lats and not ({"left"} <= lats and {"right"} <= lats):
                issues.append({
                    "severity": "medium", "code": "HEMISPHERE_PAIR_INCOMPLETE",
                    "message": f"{region.region_code} lateralized but anchor sides "
                               f"incomplete: {sorted(lats)}",
                })

    # --- Macro96 coverage (BR2 acceptance: 96/96) ---
    macro96_total, macro96_mapped = (
        await session.execute(
            text(
                "SELECT count(*), count(canonical_region_id) FROM candidate_brain_regions "
                "WHERE source_atlas='Macro96'"
            )
        )
    ).one()
    if macro96_mapped != macro96_total:
        issues.append({
            "severity": "high", "code": "MACRO96_UNMAPPED",
            "message": f"Macro96 coverage {macro96_mapped}/{macro96_total} — must be 96/96",
        })

    # --- BR3 atlas layer checks (read-only; tables may be empty pre-seed) ---
    atlas_regions = list((await session.execute(select(AtlasRegionResource))).scalars().all())
    atlas_mappings = list((await session.execute(select(AtlasRegionMapping))).scalars().all())

    # orphan atlas parent (atlas-native parent id not resolvable in same atlas)
    native_key = {(a.atlas_name, a.atlas_version, a.atlas_region_id): a for a in atlas_regions}
    orphan_atlas_parents = 0
    for a in atlas_regions:
        if a.parent_region_id and (a.atlas_name, a.atlas_version, a.parent_region_id) not in native_key:
            orphan_atlas_parents += 1
            if orphan_atlas_parents <= 10:
                issues.append({
                    "severity": "medium", "code": "ORPHAN_ATLAS_PARENT",
                    "message": f"atlas region {a.atlas_name}/{a.atlas_region_id} references missing "
                               f"parent {a.parent_region_id}",
                })

    # atlas mapping conflict: one atlas region mapped (active) to >1 distinct canonicals
    atlas_by_id = {a.id: a for a in atlas_regions}
    mapped_targets: dict[uuid.UUID, set[uuid.UUID]] = {}
    atlas_cross_species = 0
    for m in atlas_mappings:
        if m.status != "active" or m.canonical_region_id is None:
            continue
        mapped_targets.setdefault(m.atlas_region_id, set()).add(m.canonical_region_id)
        atlas_row = atlas_by_id.get(m.atlas_region_id)
        canonical = by_id.get(m.canonical_region_id)
        if atlas_row is not None and canonical is not None:
            if atlas_row.species not in (None, "unknown") and canonical.species not in (None, "unknown") \
                    and atlas_row.species != canonical.species:
                atlas_cross_species += 1
                severity = "medium" if m.species_relation == "homology" else "high"
                issues.append({
                    "severity": severity, "code": "ATLAS_CROSS_SPECIES_MAPPING",
                    "message": f"atlas {atlas_row.atlas_name}/{atlas_row.atlas_region_id} "
                               f"(species={atlas_row.species}) mapped to {canonical.region_code} "
                               f"(species={canonical.species}) with species_relation={m.species_relation}",
                })
    for atlas_id, targets in mapped_targets.items():
        if len(targets) > 1:
            a = atlas_by_id.get(atlas_id)
            issues.append({
                "severity": "high", "code": "ATLAS_MAPPING_CONFLICT",
                "message": f"atlas region {a.atlas_name}/{a.atlas_region_id if a else atlas_id} has "
                           f"{len(targets)} active mappings to different canonical regions",
            })

    # cell/molecular alignments still referencing merged regions (rows kept on
    # the merged source during merge; traceable via replaced_by_region_id)
    merged_align_rows = (
        await session.execute(
            text(
                "SELECT count(*) FROM region_cell_alignment a "
                "JOIN canonical_brain_regions r ON r.id = a.region_id AND r.status='merged' "
                "UNION ALL "
                "SELECT count(*) FROM region_molecular_alignment a "
                "JOIN canonical_brain_regions r ON r.id = a.region_id AND r.status='merged'"
            )
        )
    ).all()
    merged_alignments = sum(int(row[0]) for row in merged_align_rows)
    if merged_alignments:
        issues.append({
            "severity": "low", "code": "MERGED_REGION_ALIGNMENT",
            "message": f"{merged_alignments} cell/molecular alignment row(s) still reference merged "
                       "regions (kept for traceability via replaced_by_region_id)",
        })

    counts = {
        "canonical_total": len(regions),
        "active": sum(1 for r in regions if r.status == "active"),
        "proposed": sum(1 for r in regions if r.status == "proposed"),
        "l0_count": sum(1 for r in regions if r.granularity_level == "whole_brain"),
        "l1_count": sum(1 for r in regions if r.granularity_level == "macro"),
        "l2_clinical_count": sum(1 for r in regions if r.granularity_level == "clinical"),
        "above_l1_count": sum(1 for r in regions if level_order(r, order) > 1),
        "hierarchy_edges": len(edges),
        "isolated_node_count": len(isolated),
        "isolated_codes": isolated,
        "mapped_candidates": mapped_count,
        "orphan_canonical_refs": orphan_count,
        "cross_species_mappings": cross_species_count,
        "pending_alignment_candidates": pending_alignment,
        "macro96_total": macro96_total,
        "macro96_mapped": macro96_mapped,
        # BR3 multiscale
        "meso_count": sum(1 for r in regions if r.granularity_level == "meso"),
        "subregion_count": sum(1 for r in regions if r.granularity_level == "subregion"),
        "cyto_count": sum(1 for r in regions if r.granularity_level == "cyto"),
        "molecular_count": sum(1 for r in regions if r.granularity_level == "molecular"),
        "atlas_region_rows": len(atlas_regions),
        "atlas_mapping_rows": len(atlas_mappings),
        "atlas_orphan_parents": orphan_atlas_parents,
        "atlas_cross_species_mappings": atlas_cross_species,
        "merged_region_alignments": merged_alignments,
    }
    return {
        "ok": not any(i["severity"] in ("critical", "high") for i in issues),
        "counts": counts,
        "issues": issues,
    }


def _find_cycles(
    regions: list[CanonicalBrainRegion], edges: list[CanonicalRegionHierarchy]
) -> list[list[str]]:
    graph: dict[uuid.UUID, list[uuid.UUID]] = {r.id: [] for r in regions}
    for e in edges:
        graph.setdefault(e.child_region_id, []).append(e.parent_region_id)
    code_by_id = {r.id: r.region_code for r in regions}
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[uuid.UUID, int] = {r.id: WHITE for r in regions}
    cycles: list[list[str]] = []

    def dfs(node: uuid.UUID, stack: list[uuid.UUID]) -> None:
        color[node] = GRAY
        stack.append(node)
        for nxt in graph.get(node, []):
            if color.get(nxt, BLACK) == GRAY:
                idx = stack.index(nxt) if nxt in stack else 0
                cycles.append([code_by_id.get(x, str(x)) for x in stack[idx:]] + [code_by_id.get(nxt, str(nxt))])
            elif color.get(nxt, BLACK) == WHITE:
                dfs(nxt, stack)
        stack.pop()
        color[node] = BLACK

    for r in regions:
        if color[r.id] == WHITE:
            dfs(r.id, [])
    return cycles[:10]


async def _repoint_child_edges(
    session: AsyncSession,
    source: CanonicalBrainRegion,
    target: CanonicalBrainRegion,
    order: dict[str, int],
) -> tuple[int, int]:
    """Re-point source's active part_of edges (source as child) to target."""
    repointed = 0
    kept = 0
    rows = list(
        (
            await session.execute(
                select(CanonicalRegionHierarchy).where(
                    CanonicalRegionHierarchy.child_region_id == source.id,
                    CanonicalRegionHierarchy.status == "active",
                )
            )
        ).scalars().all()
    )
    for e in rows:
        parent = await session.get(CanonicalBrainRegion, e.parent_region_id)
        dup = (
            await session.execute(
                select(CanonicalRegionHierarchy).where(
                    CanonicalRegionHierarchy.child_region_id == target.id,
                    CanonicalRegionHierarchy.parent_region_id == e.parent_region_id,
                )
            )
        ).scalar_one_or_none()
        if parent is not None and dup is None and level_order(target, order) > level_order(parent, order):
            e.child_region_id = target.id
            repointed += 1
        else:
            kept += 1
    return repointed, kept


async def _repoint_parent_edges(
    session: AsyncSession,
    source: CanonicalBrainRegion,
    target: CanonicalBrainRegion,
    order: dict[str, int],
) -> tuple[int, int]:
    """Re-point source's active part_of edges (source as parent) to target."""
    repointed = 0
    kept = 0
    rows = list(
        (
            await session.execute(
                select(CanonicalRegionHierarchy).where(
                    CanonicalRegionHierarchy.parent_region_id == source.id,
                    CanonicalRegionHierarchy.status == "active",
                )
            )
        ).scalars().all()
    )
    for e in rows:
        child = await session.get(CanonicalBrainRegion, e.child_region_id)
        dup = (
            await session.execute(
                select(CanonicalRegionHierarchy).where(
                    CanonicalRegionHierarchy.child_region_id == e.child_region_id,
                    CanonicalRegionHierarchy.parent_region_id == target.id,
                )
            )
        ).scalar_one_or_none()
        if child is not None and dup is None and level_order(child, order) > level_order(target, order):
            e.parent_region_id = target.id
            repointed += 1
        else:
            kept += 1
    return repointed, kept


async def _repoint_atlas_mappings(
    session: AsyncSession, source: CanonicalBrainRegion, target: CanonicalBrainRegion
) -> tuple[int, int]:
    """Re-point source's active atlas mappings to target.

    When target already has an active mapping for the same atlas row, the
    source's mapping is superseded instead — one active mapping per atlas row.
    """
    repointed = 0
    superseded = 0
    rows = list(
        (
            await session.execute(
                select(AtlasRegionMapping).where(
                    AtlasRegionMapping.canonical_region_id == source.id,
                    AtlasRegionMapping.status == "active",
                )
            )
        ).scalars().all()
    )
    for m in rows:
        dup = (
            await session.execute(
                select(AtlasRegionMapping).where(
                    AtlasRegionMapping.atlas_region_id == m.atlas_region_id,
                    AtlasRegionMapping.canonical_region_id == target.id,
                    AtlasRegionMapping.status == "active",
                )
            )
        ).scalar_one_or_none()
        m.provenance = {**dict(m.provenance), "merged_from": source.region_code}
        if dup is not None:
            m.status = "superseded"
            superseded += 1
        else:
            m.canonical_region_id = target.id
            repointed += 1
    return repointed, superseded


async def _repoint_region_alignments(
    session: AsyncSession, source: CanonicalBrainRegion, target: CanonicalBrainRegion
) -> tuple[int, int]:
    """Re-point source's cell/molecular alignments to target.

    Rows whose unique key already exists on target stay on the merged source
    row — still traceable via ``replaced_by_region_id`` (and surfaced by the
    integrity checker as MERGED_REGION_ALIGNMENT).
    """
    repointed = 0
    kept = 0
    cell_rows = list(
        (
            await session.execute(
                select(RegionCellAlignment).where(RegionCellAlignment.region_id == source.id)
            )
        ).scalars().all()
    )
    for a in cell_rows:
        dup = (
            await session.execute(
                select(RegionCellAlignment).where(
                    RegionCellAlignment.region_id == target.id,
                    RegionCellAlignment.cell_type_id == a.cell_type_id,
                    RegionCellAlignment.mapping_type == a.mapping_type,
                )
            )
        ).scalar_one_or_none()
        if dup is not None:
            kept += 1
        else:
            a.region_id = target.id
            repointed += 1
    mol_rows = list(
        (
            await session.execute(
                select(RegionMolecularAlignment).where(RegionMolecularAlignment.region_id == source.id)
            )
        ).scalars().all()
    )
    for a in mol_rows:
        dup = (
            await session.execute(
                select(RegionMolecularAlignment).where(
                    RegionMolecularAlignment.region_id == target.id,
                    RegionMolecularAlignment.molecular_entity_id == a.molecular_entity_id,
                    RegionMolecularAlignment.evidence_type == a.evidence_type,
                )
            )
        ).scalar_one_or_none()
        if dup is not None:
            kept += 1
        else:
            a.region_id = target.id
            repointed += 1
    return repointed, kept


async def merge_canonical_region(
    session: AsyncSession, source_region_id: uuid.UUID, target_region_id: uuid.UUID
) -> dict[str, Any]:
    """Merge source region into target without breaking identity (BR3).

    - source keeps its region_code and row; status -> 'merged' with
      ``replaced_by_region_id`` pointing at target (identity stays traceable).
    - part_of edges re-point to target only when the level-direction guard
      holds and no duplicate edge exists; otherwise they stay on the merged row.
    - active atlas mappings re-point to target with merge provenance (dedup
      guard: superseded when target already maps the same atlas row);
      cell/molecular alignments re-point likewise.
    """
    source = await session.get(CanonicalBrainRegion, source_region_id)
    target = await session.get(CanonicalBrainRegion, target_region_id)
    if source is None or target is None:
        raise CanonicalRegionError("source or target canonical region not found")
    if source.id == target.id:
        raise CanonicalRegionError("cannot merge a region into itself")
    if target.status == "merged" or source.status == "merged":
        raise CanonicalRegionError("merged regions cannot participate in a merge")
    order = await _load_level_order(session)

    child_repointed, child_kept = await _repoint_child_edges(session, source, target, order)
    parent_repointed, parent_kept = await _repoint_parent_edges(session, source, target, order)
    mappings_repointed, mappings_superseded = await _repoint_atlas_mappings(session, source, target)
    align_repointed, align_kept = await _repoint_region_alignments(session, source, target)

    source.status = "merged"
    source.replaced_by_region_id = target.id
    await session.flush()
    return {
        "source_region_code": source.region_code,
        "target_region_code": target.region_code,
        "repointed_edges": child_repointed + parent_repointed,
        "kept_edges": child_kept + parent_kept,
        "repointed_mappings": mappings_repointed,
        "superseded_mappings": mappings_superseded,
        "repointed_alignments": align_repointed,
        "kept_alignments": align_kept,
    }
