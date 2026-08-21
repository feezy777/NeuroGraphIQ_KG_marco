"""O1.3-A: deterministic Function hierarchy PARENT CANDIDATE generation.

Retrieves candidate parents for a Function child term from the real
ontology_terms + usage data. Deliberately NOT a hierarchy edge writer:

* candidates live in ontology_hierarchy_candidates;
* formal edges live in ontology_term_relations (untouched here);
* no LLM, no auto-activation, no auto-root.

Candidate sources (deterministic, interpretable):
  A. lexical containment      — parent tokens ⊂ child tokens (subset, longer parent wins)
  B. token subset             — same as A (canonical family handled separately)
  C. metadata consistency     — domain/category agreement (currently 0 coverage in data)
  D. synonym / canonical      — used to *exclude* synonym pairs & canonical dupes
  E. usage-context similarity — Jaccard over subject sets (weak signal only)
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mirror_kg import MirrorRegionFunction
from app.models.mirror_macro_clinical import (
    MirrorCircuitFunction,
    MirrorProjectionFunction,
)
from app.models.ontology import (
    OntologyHierarchyCandidate,
    OntologyTerm,
    OntologyTermSynonym,
)
from app.services.function_term_service import TERM_CODE_PREFIX, TERM_TYPE_FUNCTION

GENERATION_VERSION = "function_hierarchy_candidate_v1"
DEFAULT_TOP_K = 10

# single-token parents that carry no useful information content
GENERIC_PARENT_TOKENS = frozenset({
    "function", "functions", "signal", "signals", "activity", "activities",
    "response", "responses", "relay", "unknown", "none", "unspecified", "n/a",
    "modulation", "regulation", "coordination", "integration", "encoding",
    "retrieval", "consolidation", "transmission", "circulation",
})

# stopwords removed from term tokens before matching
STOPWORDS = frozenset({
    "via", "through", "using", "with", "during", "after", "before", "from",
    "into", "upon", "within", "across", "along", "under", "over", "in", "of",
})

# compound connectors that split a Function into components
_COMPOUND_SPLIT_RE = re.compile(r"\band\b|\band_\b|_and_|\+", re.IGNORECASE)


class CandidateGenerationError(Exception):
    pass


@dataclass
class Candidate:
    child_term_id: uuid.UUID
    parent_term_id: uuid.UUID
    candidate_score: float
    lexical_score: float
    metadata_score: float
    usage_score: float
    synonym_score: float
    parent_status: str
    reasons: dict[str, Any]
    method: str


@dataclass
class TermIndex:
    """Prebuilt in-memory index over Function terms (built once per batch)."""

    terms: dict[uuid.UUID, OntologyTerm] = field(default_factory=dict)
    token_set: dict[uuid.UUID, set[str]] = field(default_factory=dict)
    token_terms: dict[str, set[uuid.UUID]] = field(default_factory=dict)
    canonical_key: dict[uuid.UUID, str] = field(default_factory=dict)
    canonical_to_term: dict[str, uuid.UUID] = field(default_factory=dict)
    synonym_keys: dict[uuid.UUID, set[str]] = field(default_factory=dict)
    usage_subjects: dict[uuid.UUID, set[uuid.UUID]] = field(default_factory=dict)
    usage_count: dict[uuid.UUID, int] = field(default_factory=dict)
    term_status: dict[uuid.UUID, str] = field(default_factory=dict)


def _tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS}


def _norm_key(text: str | None) -> str:
    return " ".join(sorted(_tokens(text)))


async def load_term_index(
    session: AsyncSession,
    *,
    include_proposed: bool = True,
) -> TermIndex:
    """One-pass index over Function terms + synonyms + usage subjects."""
    idx = TermIndex()
    statuses = ("active",) if not include_proposed else ("active", "proposed")
    terms = (
        await session.execute(
            select(OntologyTerm).where(
                OntologyTerm.term_type == TERM_TYPE_FUNCTION,
                OntologyTerm.status.in_(statuses),
            )
        )
    ).scalars().all()
    for t in terms:
        if not (t.term_code or "").startswith(TERM_CODE_PREFIX):
            continue
        idx.terms[t.id] = t
        idx.token_set[t.id] = _tokens(t.canonical_term_en)
        key = _norm_key(t.canonical_term_en)
        idx.canonical_key[t.id] = key
        idx.canonical_to_term.setdefault(key, t.id)
        idx.term_status[t.id] = t.status
        for tok in idx.token_set[t.id]:
            idx.token_terms.setdefault(tok, set()).add(t.id)

    syns = (await session.execute(select(OntologyTermSynonym))).scalars().all()
    for syn in syns:
        if syn.term_id in idx.terms:
            idx.synonym_keys.setdefault(syn.term_id, set()).add(_norm_key(syn.synonym_text))

    # usage subjects: term → set of subjects using it (region/projection/circuit)
    for model, subj_col, term_col in (
        (MirrorRegionFunction, MirrorRegionFunction.region_candidate_id, MirrorRegionFunction.term_id),
        (MirrorProjectionFunction, MirrorProjectionFunction.projection_id, MirrorProjectionFunction.term_id),
        (MirrorCircuitFunction, MirrorCircuitFunction.circuit_id, MirrorCircuitFunction.term_id),
    ):
        rows = (
            await session.execute(
                select(term_col, subj_col).where(term_col.isnot(None), subj_col.isnot(None))
            )
        ).all()
        for term_id, subj_id in rows:
            idx.usage_subjects.setdefault(term_id, set()).add(subj_id)
            idx.usage_count[term_id] = idx.usage_count.get(term_id, 0) + 1

    return idx


def _generic_parent(parent_tokens: set[str]) -> bool:
    return len(parent_tokens) == 1 and next(iter(parent_tokens)) in GENERIC_PARENT_TOKENS


def _is_compound(name: str | None) -> bool:
    return bool(name and _COMPOUND_SPLIT_RE.search(name))


def generate_candidates_for_term(
    child: OntologyTerm,
    idx: TermIndex,
    *,
    top_k: int = DEFAULT_TOP_K,
) -> tuple[list[Candidate], str | None]:
    """Deterministic candidate parents for one Function term.

    Returns (candidates sorted by score desc, no_candidate_reason|None).
    """
    child_id = child.id
    child_key = _norm_key(child.canonical_term_en)
    child_tokens = idx.token_set.get(child_id, set())
    if not child_tokens:
        return [], "empty_name"
    if _is_compound(child.canonical_term_en):
        pass  # compound handling below (components scored lower)

    raw: list[tuple[float, uuid.UUID, str, dict[str, Any]]] = []

    # A/B. lexical containment: parent token set ⊆ child token set
    #      (ordered longer-first gives more specific parents priority)
    for token in child_tokens:
        for cand_id in idx.token_terms.get(token, ()):
            if cand_id == child_id:
                continue
            cand_tokens = idx.token_set.get(cand_id, set())
            if not cand_tokens or not cand_tokens.issubset(child_tokens):
                continue
            if len(cand_tokens) >= len(child_tokens):
                continue  # parent must be strictly less specific
            if _generic_parent(cand_tokens):
                continue
            # single-token parent must be the child's last token (core noun):
            # 'working memory' → 'memory' OK; 'auditory reflex' → 'auditory' not.
            if len(cand_tokens) == 1 and len(child_tokens) > 1:
                last_token = sorted(child_tokens, key=lambda t: (child.canonical_term_en or "").lower().find(t))[-1]
                if next(iter(cand_tokens)) != last_token:
                    continue
            # canonical-identical / synonym pair exclusion:
            # child is a synonym of the parent (or canonical-identical) → not an edge
            cand_key = idx.canonical_key.get(cand_id, "")
            if cand_key == child_key or child_key in idx.synonym_keys.get(cand_id, set()):
                continue
            parent = idx.terms.get(cand_id)
            if parent is None or parent.status == "deprecated":
                continue
            lex = len(cand_tokens) / max(1, len(child_tokens))  # more shared tokens → stronger
            if lex < 0.4:
                continue
            # child must not be a component of a compound split of the parent
            if _is_compound(parent.canonical_term_en) and child_tokens.issubset(_tokens(parent.canonical_term_en)):
                continue
            usage = _jaccard(idx, child_id, cand_id)
            meta = _metadata_score(child, parent)
            reasons = {
                "lexical_containment": True,
                "parent_tokens": sorted(cand_tokens),
                "child_tokens": sorted(child_tokens),
                "usage_overlap": round(usage, 3),
                "shared_domain": _shared_meta(child, parent),
            }
            raw.append((_score(lex, meta, usage), cand_id, "lexical_containment", reasons))

    # C. metadata-only candidates (same domain/category) — weak, no lexical basis
    for cand_id, cand in idx.terms.items():
        if cand_id == child_id:
            continue
        if idx.token_set.get(cand_id, set()) & child_tokens:
            continue  # already covered by lexical path
        if _metadata_score(child, cand) >= 1.0:
            usage = _jaccard(idx, child_id, cand_id)
            reasons = {"metadata_only": True, "shared_domain": _shared_meta(child, cand),
                       "usage_overlap": round(usage, 3)}
            raw.append((_score(0.0, 1.0, usage), cand_id, "metadata", reasons))

    # E. usage-context similarity (weak signal only, never above structural)
    if raw:
        # lexical winners already ranked; add usage-only candidates sparingly
        pass

    # compound components: split child on 'and' and propose components as weak candidates
    if _is_compound(child.canonical_term_en):
        for part in _COMPOUND_SPLIT_RE.split(child.canonical_term_en):
            part_key = _norm_key(part)
            if not part_key:
                continue
            part_term_id = idx.canonical_to_term.get(part_key)
            if part_term_id is None or part_term_id == child_id:
                continue
            part_term = idx.terms.get(part_term_id)
            if part_term is None or part_term.status == "deprecated":
                continue
            reasons = {"compound_term_component_candidate": True, "component": part.strip()}
            raw.append((0.3, part_term_id, "compound_component", reasons))

    if not raw:
        return [], _no_candidate_reason(child, idx)

    # dedupe by parent
    seen: dict[uuid.UUID, tuple[float, str, dict[str, Any]]] = {}
    for score, cand_id, method, reasons in raw:
        if cand_id not in seen or score > seen[cand_id][0]:
            seen[cand_id] = (score, method, reasons)

    ranked = sorted(seen.items(), key=lambda kv: (-kv[1][0], kv[0]))
    candidates: list[Candidate] = []
    for cand_id, (score, method, reasons) in ranked[:top_k]:
        parent = idx.terms[cand_id]
        candidates.append(Candidate(
            child_term_id=child_id,
            parent_term_id=cand_id,
            candidate_score=round(score, 4),
            lexical_score=_lex_share(idx, child_id, cand_id),
            metadata_score=round(_metadata_score(child, parent), 4),
            usage_score=round(_jaccard(idx, child_id, cand_id), 4),
            synonym_score=1.0 if child_key in idx.synonym_keys.get(cand_id, set()) else 0.0,
            parent_status=parent.status,
            reasons=reasons,
            method=method,
        ))
    return candidates, None


def _lex_share(idx: TermIndex, child_id: uuid.UUID, parent_id: uuid.UUID) -> float:
    c = idx.token_set.get(child_id, set())
    p = idx.token_set.get(parent_id, set())
    if not c or not p:
        return 0.0
    return len(p) / len(c)


def _jaccard(idx: TermIndex, a: uuid.UUID, b: uuid.UUID) -> float:
    sa = idx.usage_subjects.get(a, set())
    sb = idx.usage_subjects.get(b, set())
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    return inter / (len(sa) + len(sb) - inter)


def _metadata_score(child: OntologyTerm, parent: OntologyTerm) -> float:
    score = 0.0
    for attr in ("domain", "category"):
        cv = getattr(child, attr, None)
        pv = getattr(parent, attr, None)
        if cv and pv and cv == pv:
            score += 0.5
    return score


def _shared_meta(child: OntologyTerm, parent: OntologyTerm) -> str | None:
    for attr in ("domain", "category"):
        cv = getattr(child, attr, None)
        pv = getattr(parent, attr, None)
        if cv and pv and cv == pv:
            return str(cv)
    return None


def _score(lex: float, meta: float, usage: float) -> float:
    return 2.0 * lex + 1.0 * meta + 0.5 * usage


def _no_candidate_reason(child: OntologyTerm, idx: TermIndex) -> str:
    if _is_compound(child.canonical_term_en):
        return "compound_unresolved"
    if not idx.usage_subjects.get(child.id):
        return "isolated_concept"
    return "no_lexical_parent"


async def generate_candidates_for_term_id(
    session: AsyncSession,
    term_id: uuid.UUID,
    *,
    top_k: int = DEFAULT_TOP_K,
    generation_version: str = GENERATION_VERSION,
    index: TermIndex | None = None,
    created_by: str | None = None,
) -> tuple[list[OntologyHierarchyCandidate], str | None]:
    """Generate + persist candidates for one term (idempotent per version)."""
    idx = index or await load_term_index(session)
    child = idx.terms.get(term_id) or await session.get(OntologyTerm, term_id)
    if child is None or child.term_type != TERM_TYPE_FUNCTION:
        raise CandidateGenerationError(f"not a function term: {term_id}")

    candidates, reason = generate_candidates_for_term(child, idx, top_k=top_k)
    if not candidates:
        return [], reason

    persisted: list[OntologyHierarchyCandidate] = []
    for cand in candidates:
        existing = (
            await session.execute(
                select(OntologyHierarchyCandidate).where(
                    OntologyHierarchyCandidate.child_term_id == cand.child_term_id,
                    OntologyHierarchyCandidate.parent_term_id == cand.parent_term_id,
                    OntologyHierarchyCandidate.generation_version == generation_version,
                ).limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            persisted.append(existing)
            continue
        row = OntologyHierarchyCandidate(
            child_term_id=cand.child_term_id,
            parent_term_id=cand.parent_term_id,
            candidate_score=cand.candidate_score,
            generation_method=cand.method,
            generation_reasons_json=cand.reasons,
            lexical_score=cand.lexical_score,
            metadata_score=cand.metadata_score,
            usage_score=cand.usage_score,
            synonym_score=cand.synonym_score,
            parent_status=cand.parent_status,
            status="pending",
            generation_version=generation_version,
            created_by=created_by,
        )
        session.add(row)
        persisted.append(row)
    await session.flush()
    return persisted, None


async def generate_candidates_batch(
    session: AsyncSession,
    term_ids: list[uuid.UUID],
    *,
    top_k: int = DEFAULT_TOP_K,
    generation_version: str = GENERATION_VERSION,
    created_by: str | None = None,
) -> dict[str, Any]:
    """Batch generation with one shared index (no N×M relation queries)."""
    idx = await load_term_index(session)
    total = 0
    no_candidate: dict[str, int] = {}
    per_term: list[dict[str, Any]] = []
    for term_id in term_ids:
        child = idx.terms.get(term_id)
        if child is None:
            continue
        cands, reason = await generate_candidates_for_term_id(
            session, term_id, top_k=top_k,
            generation_version=generation_version, index=idx, created_by=created_by,
        )
        total += len(cands)
        if reason:
            no_candidate[reason] = no_candidate.get(reason, 0) + 1
        per_term.append({"term_id": str(term_id), "candidate_count": len(cands),
                         "no_candidate_reason": reason})
    await session.flush()
    return {"total_candidates": total, "no_candidate_by_reason": no_candidate, "per_term": per_term}


async def list_candidates(
    session: AsyncSession,
    *,
    child_term_id: uuid.UUID | None = None,
    status: str | None = None,
    generation_version: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[OntologyHierarchyCandidate], int]:
    q = select(OntologyHierarchyCandidate).order_by(
        OntologyHierarchyCandidate.candidate_score.desc()
    )
    conds = []
    if child_term_id:
        conds.append(OntologyHierarchyCandidate.child_term_id == child_term_id)
    if status:
        conds.append(OntologyHierarchyCandidate.status == status)
    if generation_version:
        conds.append(OntologyHierarchyCandidate.generation_version == generation_version)
    if conds:
        q = q.where(*conds)
    total = (
        await session.execute(select(sa_func.count()).select_from(q.subquery()))
    ).scalar_one()
    rows = (await session.execute(q.limit(limit).offset(offset))).scalars().all()
    return list(rows), total


async def set_calibration_label(
    session: AsyncSession,
    candidate_id: uuid.UUID,
    label: str,
) -> OntologyHierarchyCandidate:
    allowed = {"good_parent", "plausible_parent", "related_not_parent", "wrong", "no_parent_found"}
    if label not in allowed:
        raise CandidateGenerationError(f"invalid calibration label: {label}")
    row = await session.get(OntologyHierarchyCandidate, candidate_id)
    if row is None:
        raise CandidateGenerationError(f"candidate not found: {candidate_id}")
    row.calibration_label = label
    await session.flush()
    return row


async def candidate_stats(
    session: AsyncSession,
    *,
    generation_version: str | None = None,
) -> dict[str, Any]:
    q = select(OntologyHierarchyCandidate)
    conds = []
    if generation_version:
        conds.append(OntologyHierarchyCandidate.generation_version == generation_version)
    if conds:
        q = q.where(*conds)
    rows = (await session.execute(q)).scalars().all()
    by_label: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for r in rows:
        by_status[r.status] = by_status.get(r.status, 0) + 1
        if r.calibration_label:
            by_label[r.calibration_label] = by_label.get(r.calibration_label, 0) + 1
    return {
        "total": len(rows),
        "by_status": by_status,
        "by_calibration_label": by_label,
        "distinct_children": len({r.child_term_id for r in rows}),
    }


async def check_hierarchy_candidate_integrity(
    session: AsyncSession,
    *,
    generation_version: str | None = None,
) -> dict[str, int]:
    """Read-only candidate integrity audit."""
    q = select(OntologyHierarchyCandidate)
    conds = []
    if generation_version:
        conds.append(OntologyHierarchyCandidate.generation_version == generation_version)
    if conds:
        q = q.where(*conds)
    rows = (await session.execute(q)).scalars().all()

    out: dict[str, int] = {
        "total": len(rows), "duplicate": 0, "self": 0, "orphan_child": 0,
        "orphan_parent": 0, "invalid_child": 0, "invalid_parent": 0,
        "merged_child": 0, "merged_parent": 0, "deprecated_child": 0,
        "deprecated_parent": 0, "canonical_identical": 0, "missing_version": 0,
        "score_out_of_range": 0, "missing_reasons": 0,
    }
    seen: set[tuple] = set()
    terms: dict[uuid.UUID, OntologyTerm] = {}
    for r in rows:
        if not r.generation_version:
            out["missing_version"] += 1
        key = (str(r.child_term_id), str(r.parent_term_id), r.generation_version or "")
        if key in seen:
            out["duplicate"] += 1
        seen.add(key)
        if r.child_term_id == r.parent_term_id:
            out["self"] += 1
        if not (0.0 <= (r.candidate_score or 0.0) <= 10.0):
            out["score_out_of_range"] += 1
        if not r.generation_reasons_json:
            out["missing_reasons"] += 1
        for tid, label, key in (
            (r.child_term_id, "child", "orphan_child"),
            (r.parent_term_id, "parent", "orphan_parent"),
        ):
            term = terms.get(tid)
            if term is None:
                term = await session.get(OntologyTerm, tid)
                if term is not None:
                    terms[tid] = term
            if term is None:
                out[key] += 1
                continue
            if term.term_type != TERM_TYPE_FUNCTION:
                out["invalid_child" if label == "child" else "invalid_parent"] += 1
            if term.status == "merged":
                out["merged_child" if label == "child" else "merged_parent"] += 1
            if term.status == "deprecated":
                out["deprecated_child" if label == "child" else "deprecated_parent"] += 1
    # canonical-identical pairs
    for r in rows:
        c = terms.get(r.child_term_id)
        p = terms.get(r.parent_term_id)
        if c and p and _norm_key(c.canonical_term_en) == _norm_key(p.canonical_term_en):
            out["canonical_identical"] += 1
    return out
