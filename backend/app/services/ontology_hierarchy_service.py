"""O1.2: Function Concept hierarchy — ontology_term_relations service.

Canonical model (see docs/FUNCTION_ONTOLOGY_HIERARCHY.md):

* Function Concept identity = ontology_terms.id (P1).
* Hierarchy edge = ontology_term_relations row: child --subclass_of--> parent.
* Only `subclass_of` is materialized; broader/narrower/has_subclass are query
  direction derivations; no inverse edge is written.
* DAG (multi-parent), not a tree; depth is computed, never stored.
* Proposed/active/rejected/deprecated lifecycle mirrors ontology term status.
* Cycle guard covers active + proposed edges (rejected/deprecated excluded).
* Merged terms are redirected to their canonical replacement, duplicate-safe,
  with a cycle re-check.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ontology import OntologyTerm, OntologyTermRelation
from app.services.function_term_service import (
    TERM_CODE_PREFIX,
    TERM_TYPE_FUNCTION,
    resolve_canonical_function_term,
)

PREDICATE_SUBCLASS_OF = "subclass_of"

# status lifecycle (reuses ontology term lifecycle vocabulary)
STATUS_PROPOSED = "proposed"
STATUS_ACTIVE = "active"
STATUS_REJECTED = "rejected"
STATUS_DEPRECATED = "deprecated"

ACTIVE_GRAPH_STATUSES = frozenset({STATUS_PROPOSED, STATUS_ACTIVE})
CYCLE_GUARD_STATUSES = frozenset({STATUS_PROPOSED, STATUS_ACTIVE})


class HierarchyValidationError(Exception):
    pass


class HierarchyNotFoundError(Exception):
    pass


@dataclass
class HierarchyNode:
    term_id: uuid.UUID
    term_code: str | None
    canonical_term_en: str | None
    canonical_term_cn: str | None
    term_status: str | None


@dataclass
class HierarchyEdgeView:
    id: uuid.UUID
    child: HierarchyNode
    predicate: str
    parent: HierarchyNode
    status: str
    source: str | None
    confidence: float | None
    provenance: dict[str, Any]


@dataclass
class HierarchyPath:
    node: HierarchyNode
    depth: int
    path: list[str] = field(default_factory=list)


async def _load_term(session: AsyncSession, term_id: uuid.UUID) -> OntologyTerm | None:
    return await session.get(OntologyTerm, term_id)


async def validate_function_hierarchy_endpoint(
    session: AsyncSession,
    term_id: uuid.UUID,
    *,
    require_active: bool = False,
) -> tuple[OntologyTerm | None, str | None]:
    """Validate a hierarchy endpoint term.

    1. term exists; 2. term_type == function; 3. term_code rule;
    4. merged → resolve to canonical; 5. deprecated not usable.
    Returns (canonical_term, error_reason).
    """
    res = await resolve_canonical_function_term(session, term_id)
    if res.term_id is None or not res.is_function_term:
        return None, "not_a_function_term"
    if res.status == "deprecated":
        return None, "deprecated_term"
    if require_active and res.status != "active":
        return None, "term_not_active"
    term = await _load_term(session, res.term_id)
    return term, None


def _node(term: OntologyTerm) -> HierarchyNode:
    return HierarchyNode(
        term_id=term.id,
        term_code=term.term_code,
        canonical_term_en=term.canonical_term_en,
        canonical_term_cn=term.canonical_term_cn,
        term_status=term.status,
    )


async def _edge_view(session: AsyncSession, rel: OntologyTermRelation) -> HierarchyEdgeView | None:
    child = await _load_term(session, rel.subject_term_id)
    parent = await _load_term(session, rel.object_term_id)
    if child is None or parent is None:
        return None
    return HierarchyEdgeView(
        id=rel.id,
        child=_node(child),
        predicate=rel.predicate,
        parent=_node(parent),
        status=rel.status,
        source=rel.source,
        confidence=float(rel.confidence) if rel.confidence is not None else None,
        provenance=dict(rel.provenance_json or {}),
    )


async def check_cycle(
    session: AsyncSession,
    child_term_id: uuid.UUID,
    parent_term_id: uuid.UUID,
) -> bool:
    """True if adding child --subclass_of--> parent would create a cycle.

    Guards the effective DAG (proposed + active edges). New edge (child,parent)
    forms a cycle ⟺ parent already reaches child by walking parent links
    (parent → … → child). The candidate edge is not yet inserted (or, at
    activation, walking parent links never passes through it), so no
    self-exclusion is needed. ORM traversal — the graph is small (8k terms).
    """
    rows = (
        await session.execute(
            select(OntologyTermRelation).where(
                OntologyTermRelation.predicate == PREDICATE_SUBCLASS_OF,
                OntologyTermRelation.status.in_(list(CYCLE_GUARD_STATUSES)),
            )
        )
    ).scalars().all()
    # node → its parents (objects of edges where node is the subject/child)
    parents_of: dict[uuid.UUID, list[uuid.UUID]] = {}
    for r in rows:
        parents_of.setdefault(r.subject_term_id, []).append(r.object_term_id)

    stack = list(parents_of.get(parent_term_id, []))
    seen: set[uuid.UUID] = set()
    while stack:
        node = stack.pop()
        if node == child_term_id:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(parents_of.get(node, []))
    return False

async def create_relation(
    session: AsyncSession,
    *,
    child_term_id: uuid.UUID,
    parent_term_id: uuid.UUID,
    status: str = STATUS_PROPOSED,
    source: str | None = None,
    confidence: float | None = None,
    provenance: dict[str, Any] | None = None,
    created_by: str | None = None,
) -> OntologyTermRelation:
    """Create child --subclass_of--> parent (default proposed)."""
    if status not in (STATUS_PROPOSED, STATUS_ACTIVE, STATUS_REJECTED, STATUS_DEPRECATED):
        raise HierarchyValidationError(f"invalid status: {status}")

    child, err = await validate_function_hierarchy_endpoint(session, child_term_id)
    if err:
        raise HierarchyValidationError(f"child {child_term_id}: {err}")
    parent, err = await validate_function_hierarchy_endpoint(session, parent_term_id)
    if err:
        raise HierarchyValidationError(f"parent {parent_term_id}: {err}")

    if child.id == parent.id:
        raise HierarchyValidationError("self-loop: child and parent are the same term")

    existing = (
        await session.execute(
            select(OntologyTermRelation).where(
                OntologyTermRelation.subject_term_id == child.id,
                OntologyTermRelation.predicate == PREDICATE_SUBCLASS_OF,
                OntologyTermRelation.object_term_id == parent.id,
            ).limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing  # idempotent

    if await check_cycle(session, child.id, parent.id):
        raise HierarchyValidationError(
            f"cycle rejected: {child.term_code} --subclass_of--> {parent.term_code} would form a cycle"
        )

    rel = OntologyTermRelation(
        subject_term_id=child.id,
        predicate=PREDICATE_SUBCLASS_OF,
        object_term_id=parent.id,
        status=status,
        source=source,
        confidence=confidence,
        provenance_json=provenance or {},
        created_by=created_by,
    )
    session.add(rel)
    await session.flush()
    return rel


async def activate_relation(
    session: AsyncSession,
    relation_id: uuid.UUID,
    *,
    operator_id: str | None = None,
) -> OntologyTermRelation:
    """proposed → active, re-validating endpoints & cycle."""
    rel = await session.get(OntologyTermRelation, relation_id)
    if rel is None:
        raise HierarchyNotFoundError(str(relation_id))
    if rel.status == STATUS_ACTIVE:
        return rel

    child, err = await validate_function_hierarchy_endpoint(
        session, rel.subject_term_id, require_active=True
    )
    if err:
        raise HierarchyValidationError(f"child {rel.subject_term_id}: {err}")
    parent, err = await validate_function_hierarchy_endpoint(
        session, rel.object_term_id, require_active=True
    )
    if err:
        raise HierarchyValidationError(f"parent {rel.object_term_id}: {err}")

    if await check_cycle(session, rel.subject_term_id, rel.object_term_id):
        raise HierarchyValidationError("cycle rejected at activation")

    rel.status = STATUS_ACTIVE
    if operator_id:
        rel.created_by = operator_id
    await session.flush()
    return rel


async def reject_relation(
    session: AsyncSession,
    relation_id: uuid.UUID,
    *,
    operator_id: str | None = None,
) -> OntologyTermRelation:
    rel = await session.get(OntologyTermRelation, relation_id)
    if rel is None:
        raise HierarchyNotFoundError(str(relation_id))
    rel.status = STATUS_REJECTED
    if operator_id:
        rel.created_by = operator_id
    await session.flush()
    return rel


async def deprecate_relation(
    session: AsyncSession,
    relation_id: uuid.UUID,
    *,
    operator_id: str | None = None,
) -> OntologyTermRelation:
    rel = await session.get(OntologyTermRelation, relation_id)
    if rel is None:
        raise HierarchyNotFoundError(str(relation_id))
    rel.status = STATUS_DEPRECATED
    if operator_id:
        rel.created_by = operator_id
    await session.flush()
    return rel


async def delete_relation(
    session: AsyncSession,
    relation_id: uuid.UUID,
) -> None:
    rel = await session.get(OntologyTermRelation, relation_id)
    if rel is None:
        raise HierarchyNotFoundError(str(relation_id))
    await session.delete(rel)
    await session.flush()


async def get_parents(
    session: AsyncSession,
    term_id: uuid.UUID,
    *,
    statuses: frozenset[str] | None = None,
) -> list[HierarchyEdgeView]:
    statuses = statuses or ACTIVE_GRAPH_STATUSES
    rows = (
        await session.execute(
            select(OntologyTermRelation)
            .where(
                OntologyTermRelation.subject_term_id == term_id,
                OntologyTermRelation.predicate == PREDICATE_SUBCLASS_OF,
                OntologyTermRelation.status.in_(list(statuses)),
            )
            .order_by(OntologyTermRelation.created_at)
        )
    ).scalars().all()
    out: list[HierarchyEdgeView] = []
    for rel in rows:
        view = await _edge_view(session, rel)
        if view is not None:
            out.append(view)
    return out


async def get_children(
    session: AsyncSession,
    term_id: uuid.UUID,
    *,
    statuses: frozenset[str] | None = None,
) -> list[HierarchyEdgeView]:
    statuses = statuses or ACTIVE_GRAPH_STATUSES
    rows = (
        await session.execute(
            select(OntologyTermRelation)
            .where(
                OntologyTermRelation.object_term_id == term_id,
                OntologyTermRelation.predicate == PREDICATE_SUBCLASS_OF,
                OntologyTermRelation.status.in_(list(statuses)),
            )
            .order_by(OntologyTermRelation.created_at)
        )
    ).scalars().all()
    out: list[HierarchyEdgeView] = []
    for rel in rows:
        view = await _edge_view(session, rel)
        if view is not None:
            out.append(view)
    return out


async def get_ancestors(
    session: AsyncSession,
    term_id: uuid.UUID,
    *,
    statuses: frozenset[str] | None = None,
) -> list[HierarchyPath]:
    """All ancestors with minimum depth (DAG may reach an ancestor via
    multiple paths — deduped, keeping the minimum depth)."""
    statuses = statuses or ACTIVE_GRAPH_STATUSES
    rows = (
        await session.execute(
            text(
                """
                WITH RECURSIVE up(term_id, depth) AS (
                    SELECT r.object_term_id, 1
                    FROM ontology_term_relations r
                    WHERE r.subject_term_id = :start
                      AND r.predicate = :pred
                      AND r.status = ANY(:statuses)
                    UNION
                    SELECT r.object_term_id, up.depth + 1
                    FROM ontology_term_relations r
                    JOIN up ON up.term_id = r.subject_term_id
                    WHERE r.predicate = :pred
                      AND r.status = ANY(:statuses)
                ),
                min_depth AS (
                    SELECT term_id, min(depth) AS depth
                    FROM up GROUP BY term_id
                )
                SELECT md.term_id, md.depth
                FROM min_depth md
                ORDER BY md.depth
                """
            ),
            {
                "start": str(term_id),
                "pred": PREDICATE_SUBCLASS_OF,
                "statuses": list(statuses),
            },
        )
    ).all()
    out: list[HierarchyPath] = []
    for term_id_str, depth in rows:
        tid = term_id_str if isinstance(term_id_str, uuid.UUID) else uuid.UUID(term_id_str)
        term = await _load_term(session, tid)
        if term is not None:
            out.append(HierarchyPath(node=_node(term), depth=depth))
    return out


async def get_descendants(
    session: AsyncSession,
    term_id: uuid.UUID,
    *,
    statuses: frozenset[str] | None = None,
) -> list[HierarchyPath]:
    statuses = statuses or ACTIVE_GRAPH_STATUSES
    rows = (
        await session.execute(
            text(
                """
                WITH RECURSIVE down(term_id, depth) AS (
                    SELECT r.subject_term_id, 1
                    FROM ontology_term_relations r
                    WHERE r.object_term_id = :start
                      AND r.predicate = :pred
                      AND r.status = ANY(:statuses)
                    UNION
                    SELECT r.subject_term_id, down.depth + 1
                    FROM ontology_term_relations r
                    JOIN down ON down.term_id = r.object_term_id
                    WHERE r.predicate = :pred
                      AND r.status = ANY(:statuses)
                ),
                min_depth AS (
                    SELECT term_id, min(depth) AS depth
                    FROM down GROUP BY term_id
                )
                SELECT md.term_id, md.depth
                FROM min_depth md
                ORDER BY md.depth
                """
            ),
            {
                "start": str(term_id),
                "pred": PREDICATE_SUBCLASS_OF,
                "statuses": list(statuses),
            },
        )
    ).all()
    out: list[HierarchyPath] = []
    for term_id_str, depth in rows:
        tid = term_id_str if isinstance(term_id_str, uuid.UUID) else uuid.UUID(term_id_str)
        term = await _load_term(session, tid)
        if term is not None:
            out.append(HierarchyPath(node=_node(term), depth=depth))
    return out


async def redirect_relations_for_term_merge(
    session: AsyncSession,
    *,
    source_term_id: uuid.UUID,
    target_term_id: uuid.UUID,
    operator_id: str | None = None,
) -> dict[str, int]:
    """T1 merge → T2: redirect hierarchy edges, duplicate-safe, cycle re-check.

    child --subclass_of--> T1   →   child --subclass_of--> T2
    T1 --subclass_of--> parent  →   T2 --subclass_of--> parent
    """
    counts = {"redirected": 0, "dropped_duplicate": 0, "blocked_cycle": 0}

    # 1. edges where T1 is the child (subject) → target becomes child
    as_child = (
        await session.execute(
            select(OntologyTermRelation).where(
                OntologyTermRelation.subject_term_id == source_term_id,
                OntologyTermRelation.predicate == PREDICATE_SUBCLASS_OF,
            )
        )
    ).scalars().all()
    for rel in as_child:
        if rel.object_term_id == target_term_id:
            # duplicate of an existing edge → supersede this one
            await session.delete(rel)
            counts["dropped_duplicate"] += 1
            continue
        if await check_cycle(session, target_term_id, rel.object_term_id):
            counts["blocked_cycle"] += 1
            continue
        rel.subject_term_id = target_term_id
        counts["redirected"] += 1

    # 2. edges where T1 is the parent (object) → target becomes parent
    as_parent = (
        await session.execute(
            select(OntologyTermRelation).where(
                OntologyTermRelation.object_term_id == source_term_id,
                OntologyTermRelation.predicate == PREDICATE_SUBCLASS_OF,
            )
        )
    ).scalars().all()
    for rel in as_parent:
        if rel.subject_term_id == target_term_id:
            await session.delete(rel)
            counts["dropped_duplicate"] += 1
            continue
        # duplicate-safe: target edge (subject, subclass_of, target) already exists
        dup = (
            await session.execute(
                select(OntologyTermRelation.id).where(
                    OntologyTermRelation.subject_term_id == rel.subject_term_id,
                    OntologyTermRelation.predicate == PREDICATE_SUBCLASS_OF,
                    OntologyTermRelation.object_term_id == target_term_id,
                ).limit(1)
            )
        ).scalar_one_or_none()
        if dup is not None:
            await session.delete(rel)
            counts["dropped_duplicate"] += 1
            continue
        if await check_cycle(session, rel.subject_term_id, target_term_id):
            counts["blocked_cycle"] += 1
            continue
        rel.object_term_id = target_term_id
        counts["redirected"] += 1

    await session.flush()
    return counts


async def check_function_hierarchy_integrity(
    session: AsyncSession,
) -> dict[str, Any]:
    """Read-only hierarchy audit (empty table → clean)."""
    from sqlalchemy import func as sa_func

    out: dict[str, Any] = {
        "total": 0, "active": 0, "proposed": 0, "rejected": 0, "deprecated": 0,
        "self_loop": 0, "duplicate_edge": 0, "orphan_subject": 0, "orphan_object": 0,
        "invalid_subject_type": 0, "invalid_object_type": 0,
        "merged_subject": 0, "merged_object": 0, "deprecated_endpoint": 0,
        "cycle_count": 0,
        "active_graph_nodes": 0, "root_count": 0, "leaf_count": 0,
        "multi_parent_nodes": 0, "participating_nodes": 0, "isolated_active_terms": 0,
    }

    rels = (await session.execute(select(OntologyTermRelation))).scalars().all()
    out["total"] = len(rels)
    terms: dict[uuid.UUID, OntologyTerm] = {}
    for r in rels:
        out[r.status] = out.get(r.status, 0) + 1
        if r.subject_term_id == r.object_term_id:
            out["self_loop"] += 1
        subj = terms.get(r.subject_term_id)
        if subj is None:
            subj = await _load_term(session, r.subject_term_id)
            if subj is not None:
                terms[r.subject_term_id] = subj
        obj = terms.get(r.object_term_id)
        if obj is None:
            obj = await _load_term(session, r.object_term_id)
            if obj is not None:
                terms[r.object_term_id] = obj
        if subj is None:
            out["orphan_subject"] += 1
        elif subj.term_type != TERM_TYPE_FUNCTION or not (subj.term_code or "").startswith(TERM_CODE_PREFIX):
            out["invalid_subject_type"] += 1
        elif subj.status == "merged":
            out["merged_subject"] += 1
        if obj is None:
            out["orphan_object"] += 1
        elif obj.term_type != TERM_TYPE_FUNCTION or not (obj.term_code or "").startswith(TERM_CODE_PREFIX):
            out["invalid_object_type"] += 1
        elif obj.status == "merged":
            out["merged_object"] += 1
        if subj is not None and subj.status == "deprecated":
            out["deprecated_endpoint"] += 1
        if obj is not None and obj.status == "deprecated":
            out["deprecated_endpoint"] += 1

    # duplicate edges (same triple) — unique constraint prevents, but audit anyway
    seen: set[tuple] = set()
    for r in rels:
        key = (str(r.subject_term_id), r.predicate, str(r.object_term_id))
        if key in seen:
            out["duplicate_edge"] += 1
        seen.add(key)

    # cycle scan on the guard graph: walk parents per node, detect revisit
    active_rels = [r for r in rels if r.status in CYCLE_GUARD_STATUSES]
    adj: dict[uuid.UUID, list[uuid.UUID]] = {}
    for r in active_rels:
        adj.setdefault(r.subject_term_id, []).append(r.object_term_id)
    visiting: set[uuid.UUID] = set()
    visited: set[uuid.UUID] = set()
    cycles = 0

    def _dfs(node: uuid.UUID, stack: set[uuid.UUID]) -> None:
        nonlocal cycles
        if node in stack:
            cycles += 1
            return
        if node in visited:
            return
        stack.add(node)
        for nxt in adj.get(node, []):
            _dfs(nxt, stack)
        stack.discard(node)
        visited.add(node)

    for node in list(adj):
        if node not in visited:
            _dfs(node, set())
    out["cycle_count"] = cycles

    # active graph stats
    active_terms = (
        await session.execute(
            select(OntologyTerm).where(
                OntologyTerm.term_type == TERM_TYPE_FUNCTION,
                OntologyTerm.status == "active",
            )
        )
    ).scalars().all()
    active_term_ids = {t.id for t in active_terms}

    participating: set[uuid.UUID] = set()
    parent_counts: dict[uuid.UUID, int] = {}
    for r in active_rels:
        if r.status != STATUS_ACTIVE:
            continue
        if r.subject_term_id in active_term_ids:
            participating.add(r.subject_term_id)
        if r.object_term_id in active_term_ids:
            participating.add(r.object_term_id)
        parent_counts[r.subject_term_id] = parent_counts.get(r.subject_term_id, 0) + 1

    # multi-parent counts nodes with >1 parent across the guard graph
    # (proposed + active), since a proposed second parent is still a parent.
    guard_parent_counts: dict[uuid.UUID, int] = {}
    for r in active_rels:
        guard_parent_counts[r.subject_term_id] = guard_parent_counts.get(r.subject_term_id, 0) + 1

    out["participating_nodes"] = len(participating)
    out["isolated_active_terms"] = len(active_term_ids - participating)
    out["active_graph_nodes"] = len(participating)
    out["root_count"] = sum(
        1 for t in participating
        if not any(r.object_term_id == t and r.status == STATUS_ACTIVE for r in active_rels)
    )
    out["leaf_count"] = sum(
        1 for t in participating
        if not any(r.subject_term_id == t and r.status == STATUS_ACTIVE for r in active_rels)
    )
    out["multi_parent_nodes"] = sum(1 for c in guard_parent_counts.values() if c > 1)
    return out
