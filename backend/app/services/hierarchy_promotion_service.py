"""FN1 promote preview: read-only assessment of hierarchy candidates.

Deliberately NOT a promotion executor — this module never writes to
ontology_term_relations. It answers: "if we promoted tier X of version Y,
how many edges would be created, and which candidates fail which gate?"

Per-candidate pipeline:

  tier gate       — quality_tier (written by hierarchy_candidate_quality_filter)
                    must be high_confidence (configurable)
  subclass_of     — deterministic semantic gate: concept containment only.
                    Rejects descriptive phrases and related_to semantics.
  endpoint checks — child & parent are valid ontology_terms (exist, function
                    type, not deprecated; merged → canonical resolution)
  duplicate check — (child, subclass_of, parent) already in term_relations
  cycle check     — adding the edge (with all other candidates) would form a
                    cycle in the effective DAG (proposed + active edges)

The cycle check runs Kahn's algorithm over the full graph (existing
relations + all candidate edges) and flags every candidate touching a
cyclic node as cycle_blocked — precise cycle membership, conservative
edge flagging, O(V + E).
"""

from __future__ import annotations

import re
import uuid
from collections import deque
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ontology import (
    OntologyHierarchyCandidate,
    OntologyTerm,
    OntologyTermRelation,
)
from app.services.function_term_service import TERM_TYPE_FUNCTION
from app.services.hierarchy_candidate_quality_filter import (
    _MODIFIER_TOKENS,
    _RELATIONSHIP_INDICATORS,
    _token_set,
)
from app.services.ontology_hierarchy_service import PREDICATE_SUBCLASS_OF

DEFAULT_VERSION = "function_hierarchy_candidate_v2"
DEFAULT_TIER = "high_confidence"

# Methods that express relatedness (co-membership, components) rather than
# concept containment — never subclass_of edges.
RELATED_TO_METHODS = frozenset({"metadata", "category_group", "compound_component"})

# Preposition/connector markers that turn a name into a descriptive phrase
# ("regulation of memory", "role of attention in learning").
_PHRASE_RE = re.compile(
    r"\b(of|for|in|with|via|during|after|before|between|through|using)\b", re.IGNORECASE
)


def assess_subclass_of_semantics(
    child_name: str,
    parent_name: str,
    method: str,
) -> tuple[bool, list[str]]:
    """True if (child, parent) expresses concept containment (IS-A).

    Returns (is_subclass, reasons). Rejects:
      1. related_to methods      — non-lexical methods are co-membership, not IS-A
      2. descriptive phrases     — parent differs from child only by relationship
                                   words, or the child is a "X of Y" phrase
      3. modifier-only extras    — extra tokens are all modifiers/locations
    Keeps clear lexical containment with content-bearing extra tokens.
    """
    reasons: list[str] = []
    ct = _token_set(child_name)
    pt = _token_set(parent_name)
    if not ct or not pt:
        return False, ["empty_name"]

    # 1. related_to semantics
    if method in RELATED_TO_METHODS:
        reasons.append("related_to_method")
        return False, reasons

    # lexical containment is a hard requirement for IS-A
    if not pt.issubset(ct):
        reasons.append("no_token_containment")
        return False, reasons
    extra = ct - pt
    if not extra:
        reasons.append("identical_token_set")
        return False, reasons

    # 2. descriptive phrases
    if extra.issubset(_RELATIONSHIP_INDICATORS):
        reasons.append("descriptive_phrase_relationship_words")
        return False, reasons
    # child is a "X of Y" / "X for Y" phrase: the parent is the noun inside a
    # prepositional construction rather than a superordinate concept
    if _PHRASE_RE.search(child_name or ""):
        reasons.append("descriptive_phrase_prepositional")
        return False, reasons

    # 3. modifier-only extras: "strong memory" ⊃ "memory" is modification,
    #    not specialization
    if extra.issubset(_MODIFIER_TOKENS):
        reasons.append("modifier_only_extra")
        return False, reasons

    return True, reasons


def _tier_of(candidate: OntologyHierarchyCandidate) -> str:
    return (candidate.generation_reasons_json or {}).get("quality_tier", "unrated")


async def load_term_map(
    session: AsyncSession,
    term_ids: set[uuid.UUID],
) -> dict[uuid.UUID, OntologyTerm]:
    """Load terms and resolve merged → canonical replacement.

    Chain-safe (max 8 hops); canonical terms are loaded from the DB when
    not referenced by any candidate. Shared by preview and executor so both
    assess the same effective endpoints.
    """
    terms = (
        await session.execute(select(OntologyTerm).where(OntologyTerm.id.in_(term_ids)))
    ).scalars().all()
    term_map: dict[uuid.UUID, OntologyTerm] = {t.id: t for t in terms}
    for t in list(term_map.values()):
        if t.status != "merged" or not t.replaced_by_term_id:
            continue
        hop = t.replaced_by_term_id
        nxt: OntologyTerm | None = None
        for _ in range(8):
            nxt = term_map.get(hop)
            if nxt is None:
                nxt = await session.get(OntologyTerm, hop)
                if nxt is None:
                    break
                term_map[hop] = nxt
            if nxt.status != "merged" or not nxt.replaced_by_term_id:
                break
            hop = nxt.replaced_by_term_id
        if nxt is not None and nxt.status != "merged":
            term_map[t.id] = nxt
    return term_map


def _term_ok(term: OntologyTerm | None) -> str | None:
    """Endpoint validity — returns None when the term is a valid endpoint."""
    if term is None:
        return "term_missing"
    if term.term_type != TERM_TYPE_FUNCTION:
        return "non_function"
    if term.status in ("deprecated", "merged"):
        return f"status_{term.status}"
    if term.status not in ("active", "proposed"):
        return f"status_{term.status}"
    return None


async def preview_promotion(
    session: AsyncSession,
    *,
    candidate_version: str = DEFAULT_VERSION,
    tier: str = DEFAULT_TIER,
) -> dict[str, Any]:
    """Read-only promotion preview for one candidate version + tier.

    No writes. Returns per-gate counts, the recommended promotion count,
    and blocking reasons.
    """
    candidates = (
        await session.execute(
            select(OntologyHierarchyCandidate).where(
                OntologyHierarchyCandidate.generation_version == candidate_version,
            )
        )
    ).scalars().all()

    total = len(candidates)
    if not total:
        return {
            "candidate_version": candidate_version,
            "tier": tier,
            "recommended_promotion_count": 0,
            "stages": {},
            "writes": "none",
            "error": "no_candidates_for_version",
        }

    # ── tier gate ──
    in_tier = [c for c in candidates if _tier_of(c) == tier]
    excluded_by_tier = total - len(in_tier)

    # ── load terms + existing relations once ──
    term_ids: set[uuid.UUID] = set()
    for c in in_tier:
        term_ids.add(c.child_term_id)
        term_ids.add(c.parent_term_id)
    term_map = await load_term_map(session, term_ids)

    existing_relations = (
        await session.execute(
            select(OntologyTermRelation).where(
                OntologyTermRelation.predicate == PREDICATE_SUBCLASS_OF,
                OntologyTermRelation.status.in_(("proposed", "active")),
            )
        )
    ).scalars().all()
    existing_pairs = {(r.subject_term_id, r.object_term_id) for r in existing_relations}

    # ── gates ──
    subclass_rejected: dict[str, int] = {}
    endpoint_rejected: dict[str, int] = {}
    merged_resolved = 0
    duplicates = 0
    resolved_pairs: list[tuple[uuid.UUID, uuid.UUID, OntologyHierarchyCandidate]] = []

    for c in in_tier:
        # 1. endpoint validity (hard requirement — a broken endpoint cannot
        #    be semantically assessed); term_map already resolves merged →
        #    canonical, so validity applies to the resolved term and the
        #    written endpoint ids are the canonical ids.
        child = term_map.get(c.child_term_id)
        parent = term_map.get(c.parent_term_id)
        child_err = _term_ok(child)
        parent_err = _term_ok(parent)
        if child_err:
            endpoint_rejected[f"child_{child_err}"] = endpoint_rejected.get(f"child_{child_err}", 0) + 1
            continue
        if parent_err:
            endpoint_rejected[f"parent_{parent_err}"] = endpoint_rejected.get(f"parent_{parent_err}", 0) + 1
            continue

        child_id = term_map[c.child_term_id].id  # canonical (may equal original)
        parent_id = term_map[c.parent_term_id].id
        if child_id != c.child_term_id or parent_id != c.parent_term_id:
            merged_resolved += 1

        # 2. duplicate against existing formal edges
        if (child_id, parent_id) in existing_pairs:
            duplicates += 1
            continue

        # 3. subclass_of semantics (concept containment, not phrase/related)
        child_name = child.canonical_term_en if child else ""
        parent_name = parent.canonical_term_en if parent else ""
        ok, reasons = assess_subclass_of_semantics(
            child_name, parent_name, c.generation_method or "",
        )
        if not ok:
            for r in reasons:
                subclass_rejected[r] = subclass_rejected.get(r, 0) + 1
            continue

        resolved_pairs.append((child_id, parent_id, c))

    # ── cycle check on the full graph (existing + kept candidates) ──
    # node → parents (child --subclass_of--> parent means parent is "above")
    parents_of: dict[uuid.UUID, list[uuid.UUID]] = {}
    for r in existing_relations:
        parents_of.setdefault(r.subject_term_id, []).append(r.object_term_id)
    for child_id, parent_id, _c in resolved_pairs:
        parents_of.setdefault(child_id, []).append(parent_id)

    cycle_blocked_terms: set[uuid.UUID] = set()  # term ids on any cycle
    _find_cycle_nodes(parents_of, cycle_blocked_terms)

    safe_pairs: list[tuple[uuid.UUID, uuid.UUID, OntologyHierarchyCandidate]] = []
    cycle_count = 0
    for child_id, parent_id, c in resolved_pairs:
        if child_id in cycle_blocked_terms or parent_id in cycle_blocked_terms:
            cycle_count += 1
            continue
        safe_pairs.append((child_id, parent_id, c))

    # ── output ──
    recommended = len(safe_pairs)
    return {
        "candidate_version": candidate_version,
        "tier": tier,
        "total_candidates": total,
        "recommended_promotion_count": recommended,
        "distinct_children": len({c.child_term_id for _, _, c in safe_pairs}),
        "stages": {
            "tier_gate": {
                "total": total,
                "included": len(in_tier),
                "excluded": excluded_by_tier,
            },
            "subclass_of_filter": {
                "included": len(in_tier) - sum(subclass_rejected.values()),
                "rejected": dict(sorted(subclass_rejected.items(), key=lambda x: -x[1])),
                "rejected_total": sum(subclass_rejected.values()),
            },
            "endpoint_checks": {
                "valid": len(resolved_pairs),
                "rejected": dict(sorted(endpoint_rejected.items(), key=lambda x: -x[1])),
                "rejected_total": sum(endpoint_rejected.values()),
                "merged_resolved_to_canonical": merged_resolved,
            },
            "duplicate_checks": {
                "unique": len(resolved_pairs) - duplicates,
                "already_in_relations": duplicates,
            },
            "cycle_checks": {
                "safe": recommended,
                "cycle_blocked": cycle_count,
            },
        },
        "samples": [
            {
                "child": term_map.get(c.child_term_id).canonical_term_en if term_map.get(c.child_term_id) else "",
                "parent": term_map.get(c.parent_term_id).canonical_term_en if term_map.get(c.parent_term_id) else "",
                "score": float(c.candidate_score or 0),
                "method": c.generation_method,
            }
            for _, _, c in safe_pairs[:10]
        ],
        "writes": "none — preview only",
    }


def _find_cycle_nodes(
    parents_of: dict[uuid.UUID, list[uuid.UUID]],
    out: set[uuid.UUID],
) -> None:
    """Mark nodes that participate in a directed cycle (Kahn peeling).

    parents_of: child → list of parents. Kahn's algorithm removes nodes with
    in-degree 0 iteratively; every node left over participates in a cycle.
    Precise (exactly the cyclic nodes), O(V + E).

    A candidate edge whose child or parent is a cyclic node is conservatively
    flagged cycle_blocked — its promotion would participate in (or attach
    to) a cycle.
    """
    indegree: dict[uuid.UUID, int] = {}
    for parents in parents_of.values():
        for p in parents:
            indegree[p] = indegree.get(p, 0) + 1
    for n in parents_of:
        indegree.setdefault(n, 0)

    queue = deque(n for n, d in indegree.items() if d == 0)
    while queue:
        node = queue.popleft()
        for p in parents_of.get(node, ()):
            indegree[p] -= 1
            if indegree[p] == 0:
                queue.append(p)

    for n, d in indegree.items():
        if d > 0:
            out.add(n)


def preview_summary_text(result: dict[str, Any]) -> str:
    """Compact human-readable summary of a preview result."""
    s = result["stages"]
    lines = [
        f"candidate_version : {result['candidate_version']}",
        f"tier              : {result['tier']}",
        f"total candidates  : {result['total_candidates']}",
        f"tier gate         : included {s['tier_gate']['included']} / excluded {s['tier_gate']['excluded']}",
        f"subclass_of       : rejected {s['subclass_of_filter']['rejected_total']}",
        f"endpoint checks   : rejected {s['endpoint_checks']['rejected_total']} (merged_resolved {s['endpoint_checks']['merged_resolved_to_canonical']})",
        f"duplicate checks  : already_in_relations {s['duplicate_checks']['already_in_relations']}",
        f"cycle checks      : blocked {s['cycle_checks']['cycle_blocked']}",
        "─" * 40,
        f"RECOMMENDED PROMOTION: {result['recommended_promotion_count']} edges "
        f"({result['distinct_children']} distinct children)",
        "writes: none — preview only",
    ]
    if s["subclass_of_filter"]["rejected"]:
        lines.append("subclass_of rejections:")
        for reason, n in s["subclass_of_filter"]["rejected"].items():
            lines.append(f"  {reason}: {n}")
    return "\n".join(lines)
