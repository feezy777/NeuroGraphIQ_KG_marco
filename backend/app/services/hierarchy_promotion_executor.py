"""FN1 promote executor: batched writes of hierarchy candidates.

Writes subclass_of edges from quality-filtered candidates into
ontology_term_relations. Batches (500–1000 edges, default 500); every
batch re-runs the full gate set before writing:

  endpoint checks — child & parent exist, are function terms, and are
                    usable (active/proposed; merged → canonical)
  duplicate check — (child, subclass_of, parent) not already in the graph
  subclass_of     — concept containment only (shared with preview)
  cycle check     — Kahn's algorithm over the effective graph (existing +
                    already-written + this batch); edges touching a cyclic
                    node are rejected

Provenance is preserved per edge: candidate_id, generation_version,
generation_method, quality tier/score (provenance_json) plus confidence
(confidence column) and source = generation version. Writes are
idempotent: re-running promotes nothing new.

This module touches only ontology terms/relations — never Connection,
Circuit or Inference modules.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ontology import (
    OntologyHierarchyCandidate,
    OntologyTerm,
    OntologyTermRelation,
)
from app.services.function_term_service import TERM_TYPE_FUNCTION
from app.services.hierarchy_promotion_service import (
    DEFAULT_TIER,
    DEFAULT_VERSION,
    _find_cycle_nodes,
    _tier_of,
    assess_subclass_of_semantics,
    load_term_map,
)
from app.services.ontology_hierarchy_service import (
    PREDICATE_SUBCLASS_OF,
    STATUS_PROPOSED,
)

MIN_BATCH_SIZE = 500
MAX_BATCH_SIZE = 1000
DEFAULT_BATCH_SIZE = 500

# Edges written by this pipeline carry source = the candidate version so
# provenance is auditable in bulk.
PROMOTION_SOURCE = DEFAULT_VERSION

_USABLE_STATUSES = frozenset({"active", "proposed"})
_CYCLE_STATUSES = ("proposed", "active")


def _rejected_counters() -> dict[str, int]:
    return {
        "child_term_missing": 0,
        "parent_term_missing": 0,
        "child_non_function": 0,
        "parent_non_function": 0,
        "child_status": 0,
        "parent_status": 0,
        "duplicate": 0,
        "subclass_of": 0,
        "cycle": 0,
    }


async def promote_candidates(
    session: AsyncSession,
    *,
    candidate_version: str = DEFAULT_VERSION,
    tier: str = DEFAULT_TIER,
    batch_size: int = DEFAULT_BATCH_SIZE,
    status: str = STATUS_PROPOSED,
    created_by: str | None = "hierarchy_promotion",
) -> dict[str, Any]:
    """Promote quality-filtered candidates into ontology_term_relations.

    Batched writes (500–1000 per batch). Each batch re-validates endpoints,
    duplicates, subclass_of semantics and cycles against the graph that
    includes every earlier batch. Returns the promotion report; writes are
    committed per batch.
    """
    if not (MIN_BATCH_SIZE <= batch_size <= MAX_BATCH_SIZE):
        raise ValueError(
            f"batch_size must be in [{MIN_BATCH_SIZE}, {MAX_BATCH_SIZE}], got {batch_size}"
        )

    candidates = (
        await session.execute(
            select(OntologyHierarchyCandidate).where(
                OntologyHierarchyCandidate.generation_version == candidate_version,
            )
        )
    ).scalars().all()
    total = len(candidates)
    in_tier = [c for c in candidates if _tier_of(c) == tier]

    # ── load terms once (merged → canonical resolved) ──
    term_ids: set[uuid.UUID] = set()
    for c in in_tier:
        term_ids.add(c.child_term_id)
        term_ids.add(c.parent_term_id)
    term_map = await load_term_map(session, term_ids)

    # ── existing graph once; in-memory sets grow with each batch ──
    existing_rows = (
        await session.execute(
            select(OntologyTermRelation).where(
                OntologyTermRelation.predicate == PREDICATE_SUBCLASS_OF,
                OntologyTermRelation.status.in_(_CYCLE_STATUSES),
            )
        )
    ).scalars().all()
    existing_pairs = {(r.subject_term_id, r.object_term_id) for r in existing_rows}
    parents_of: dict[uuid.UUID, list[uuid.UUID]] = {}
    for r in existing_rows:
        parents_of.setdefault(r.subject_term_id, []).append(r.object_term_id)

    rejected = _rejected_counters()
    promoted_ids: list[uuid.UUID] = []
    batches_completed = 0

    pending = list(in_tier)
    while pending:
        batch = pending[:batch_size]
        pending = pending[batch_size:]

        # ── pre-write checks for this batch ──
        keep: list[tuple[uuid.UUID, uuid.UUID, OntologyHierarchyCandidate]] = []
        for c in batch:
            child = term_map.get(c.child_term_id)
            parent = term_map.get(c.parent_term_id)
            if child is None:
                rejected["child_term_missing"] += 1
                continue
            if parent is None:
                rejected["parent_term_missing"] += 1
                continue
            if child.term_type != TERM_TYPE_FUNCTION:
                rejected["child_non_function"] += 1
                continue
            if parent.term_type != TERM_TYPE_FUNCTION:
                rejected["parent_non_function"] += 1
                continue
            if child.status not in _USABLE_STATUSES:
                rejected["child_status"] += 1
                continue
            if parent.status not in _USABLE_STATUSES:
                rejected["parent_status"] += 1
                continue
            # resolved (canonical) endpoint ids are what gets written
            child_id = term_map[c.child_term_id].id
            parent_id = term_map[c.parent_term_id].id
            if (child_id, parent_id) in existing_pairs:
                rejected["duplicate"] += 1
                continue
            ok, _reasons = assess_subclass_of_semantics(
                child.canonical_term_en or "",
                parent.canonical_term_en or "",
                c.generation_method or "",
            )
            if not ok:
                rejected["subclass_of"] += 1
                continue
            keep.append((child_id, parent_id, c))

        # ── batch cycle check: existing graph + earlier batches + this batch ──
        batch_parents = {k: list(v) for k, v in parents_of.items()}
        for child_id, parent_id, _c in keep:
            batch_parents.setdefault(child_id, []).append(parent_id)
        cyclic_terms: set[uuid.UUID] = set()
        _find_cycle_nodes(batch_parents, cyclic_terms)

        # ── write the safe edges of this batch ──
        for child_id, parent_id, c in keep:
            if child_id in cyclic_terms or parent_id in cyclic_terms:
                rejected["cycle"] += 1
                continue
            reasons = c.generation_reasons_json or {}
            session.add(OntologyTermRelation(
                subject_term_id=child_id,
                predicate=PREDICATE_SUBCLASS_OF,
                object_term_id=parent_id,
                status=status,
                source=PROMOTION_SOURCE,
                confidence=float(c.candidate_score or 0),
                provenance_json={
                    "candidate_id": str(c.id),
                    "generation_version": c.generation_version,
                    "generation_method": c.generation_method,
                    "quality_tier": reasons.get("quality_tier"),
                    "quality_score": reasons.get("quality_score"),
                },
                created_by=created_by,
            ))
            existing_pairs.add((child_id, parent_id))
            parents_of.setdefault(child_id, []).append(parent_id)
            promoted_ids.append(c.id)
        await session.flush()
        await session.commit()
        batches_completed += 1

    stats = await build_hierarchy_stats(
        session, statuses=frozenset({status, "active"})
    )
    return {
        "candidate_version": candidate_version,
        "tier": tier,
        "batch_size": batch_size,
        "status": status,
        "total_candidates": total,
        "tier_included": len(in_tier),
        "batches_completed": batches_completed,
        "promoted_edges": len(promoted_ids),
        "rejected": rejected,
        "rejected_total": sum(rejected.values()),
        "stats": stats,
        "source": PROMOTION_SOURCE,
    }


async def build_hierarchy_stats(
    session: AsyncSession,
    *,
    statuses: frozenset[str] = frozenset({"proposed", "active"}),
) -> dict[str, Any]:
    """Post-promotion statistics over the subclass_of DAG.

    max_depth: longest child→root path (memoized DFS over the acyclic part).
    root_functions: terms with children but no parent (hierarchy tops).
    orphan_functions: function terms with neither parent nor child.
    cycle_audit: Kahn peel — remaining nodes are exactly the cyclic ones.
    """
    edges = (
        await session.execute(
            select(OntologyTermRelation).where(
                OntologyTermRelation.predicate == PREDICATE_SUBCLASS_OF,
                OntologyTermRelation.status.in_(list(statuses)),
            )
        )
    ).scalars().all()

    parents_of: dict[uuid.UUID, list[uuid.UUID]] = {}
    children_of: dict[uuid.UUID, list[uuid.UUID]] = {}
    all_nodes: set[uuid.UUID] = set()
    for r in edges:
        parents_of.setdefault(r.subject_term_id, []).append(r.object_term_id)
        children_of.setdefault(r.object_term_id, []).append(r.subject_term_id)
        all_nodes.update((r.subject_term_id, r.object_term_id))

    # cycle audit — Kahn peel: nodes left over are exactly the cyclic ones
    cyclic_nodes: set[uuid.UUID] = set()
    _find_cycle_nodes(parents_of, cyclic_nodes)

    # longest path to a root, memoized; cyclic nodes are excluded from the
    # depth walk (their depth is undefined)
    memo: dict[uuid.UUID, int] = {}

    def _depth(node: uuid.UUID) -> int:
        if node in cyclic_nodes:
            return 0
        if node in memo:
            return memo[node]
        best = 0
        for parent in parents_of.get(node, ()):
            best = max(best, 1 + _depth(parent))
        memo[node] = best
        return best

    max_depth = max((_depth(n) for n in all_nodes), default=0)
    roots = [n for n in all_nodes if n not in parents_of]

    terms = (
        await session.execute(
            select(OntologyTerm).where(
                OntologyTerm.term_type == TERM_TYPE_FUNCTION,
                OntologyTerm.status.in_(list(statuses)),
            )
        )
    ).scalars().all()
    orphans = [
        t for t in terms
        if t.id not in parents_of and t.id not in children_of
    ]

    return {
        "total_edges": len(edges),
        "max_depth": max_depth,
        "root_functions": len(roots),
        "orphan_functions": len(orphans),
        "cycle_audit": {
            "pass": len(cyclic_nodes) == 0,
            "cyclic_nodes": len(cyclic_nodes),
            "cyclic_node_sample": sorted(str(x) for x in cyclic_nodes)[:10],
        },
    }


def promotion_summary_text(result: dict[str, Any]) -> str:
    """Compact human-readable promotion report."""
    st = result["stats"]
    rej = result["rejected"]
    lines = [
        f"candidate_version : {result['candidate_version']}",
        f"tier              : {result['tier']}",
        f"batch_size        : {result['batch_size']}",
        f"status written    : {result['status']}",
        "─" * 40,
        f"total candidates  : {result['total_candidates']}",
        f"tier included     : {result['tier_included']}",
        f"batches completed : {result['batches_completed']}",
        f"PROMOTED EDGES    : {result['promoted_edges']}",
        f"rejected total    : {result['rejected_total']}"
        + (
            f" (duplicate {rej['duplicate']}, subclass_of {rej['subclass_of']}, "
            f"cycle {rej['cycle']}, endpoint {rej['child_term_missing'] + rej['parent_term_missing'] + rej['child_non_function'] + rej['parent_non_function'] + rej['child_status'] + rej['parent_status']})"
        ),
        "─" * 40,
        f"stats: total_edges {st['total_edges']} | max_depth {st['max_depth']} | "
        f"roots {st['root_functions']} | orphans {st['orphan_functions']}",
        f"cycle audit: {'PASS' if st['cycle_audit']['pass'] else 'FAIL'} "
        f"({st['cycle_audit']['cyclic_nodes']} cyclic nodes)",
    ]
    return "\n".join(lines)
