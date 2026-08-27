"""O1.3-A quality filter: score and triage ontology_hierarchy_candidates.

Applies deterministic quality rules to existing candidates and stores
the result in generation_reasons_json (quality_tier + quality_score +
quality_reasons). No writes to ontology_term_relations.

Tiers:
  high_confidence  — safe to promote after spot-check
  review           — human review needed
  low_confidence   — likely noise, exclude from promotion
  rejected         — filtered out by hard rules
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func as sa_func
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ontology import OntologyHierarchyCandidate, OntologyTerm

# ── Quality thresholds ──
HIGH_THRESHOLD = 0.70
REVIEW_THRESHOLD = 0.40
# Below REVIEW_THRESHOLD → low_confidence

# Hard rejection patterns (case-insensitive on canonical_term_en)
_ANATOMICAL_LOCATION_PREFIXES = (
    "lateral ", "medial ", "ventral ", "dorsal ",
    "anterior ", "posterior ", "superior ", "inferior ",
    "ipsilateral ", "contralateral ", "bilateral ",
)

_MODALITY_SUBSTITUTION_PAIRS = [
    ("somatosensory", "auditory"),
    ("somatosensory", "visual"),
    ("somatosensory", "motor"),
    ("auditory", "visual"),
    ("motor", "sensory"),
    ("visual", "somatosensory"),
    ("auditory", "somatosensory"),
]

# Tokens that indicate a description/relationship rather than IS-A hierarchy
_RELATIONSHIP_INDICATORS = frozenset({
    "to", "from", "between", "via", "through", "onto", "input", "output",
    "projection", "connection", "pathway", "relay", "signaling",
    "transmission", "influence", "effect", "regulation",
})

_MODIFIER_TOKENS = frozenset({
    "strong", "weak", "primary", "secondary", "direct", "indirect",
    "broad", "narrow", "selective", "general", "specific", "abstract",
    "complex", "simple", "basic", "advanced", "dominant", "subordinate",
    "cross", "cross-modal", "multimodal", "unimodal",
    "cortical", "subcortical", "central", "peripheral",
    "cerebro", "cerebellar", "limbic", "thalamic", "hypothalamic",
    "corticocortical", "corticopontine", "corticostriatal",
    "somatosensory", "somatomotor", "visuomotor",
})


@dataclass
class QualityAssessment:
    candidate_id: uuid.UUID
    child_name: str
    parent_name: str
    base_score: float
    quality_score: float
    quality_tier: str
    quality_reasons: list[str] = field(default_factory=list)
    kept: bool = True


def _tokens(name: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", (name or "").lower())]


def _token_set(name: str) -> set[str]:
    return set(_tokens(name))


# Standalone anatomical location tokens (exact match, not prefix)
_LOCATION_TOKENS = frozenset({
    "lateral", "medial", "ventral", "dorsal",
    "anterior", "posterior", "superior", "inferior",
    "ipsilateral", "contralateral", "bilateral",
    "left", "right", "rostral", "caudal",
    "deep", "superficial", "layer", "zone",
})


def _is_good_hierarchy(child_name: str, parent_name: str) -> bool:
    """Quick check: does this look like a true IS-A relationship?"""
    ct = _token_set(child_name)
    pt = _token_set(parent_name)
    if not ct or not pt:
        return False
    # Parent tokens must be a subset of child tokens
    if not pt.issubset(ct):
        return False
    # Child must be strictly longer (more tokens)
    extra = ct - pt
    if not extra:
        return False
    # The extra tokens should not ALL be anatomical locations or modifiers
    non_modifier_extra = extra - _MODIFIER_TOKENS - _LOCATION_TOKENS
    return len(non_modifier_extra) > 0


def _has_modality_substitution(child_name: str, parent_name: str) -> bool:
    """Check if child and parent differ mainly by modality substitution.

    A substitution means the child has modality A where the parent has modality B
    (or vice versa), and both A and B appear as unique tokens in their respective
    names. This catches "somatosensory to visual" → "auditory to visual" (child
    has somatosensory-only, parent has auditory-only).
    """
    ct = _token_set(child_name)
    pt = _token_set(parent_name)
    child_only = ct - pt
    parent_only = pt - ct
    for a, b in _MODALITY_SUBSTITUTION_PAIRS:
        # child has a, parent has b (substitution)
        if a in child_only and b in parent_only:
            return True
        # child has b, parent has a (reverse substitution)
        if b in child_only and a in parent_only:
            return True
    return False


def _is_anatomical_detail(child_name: str, parent_name: str) -> bool:
    """Child adds only anatomical location prefix/insertion to parent."""
    cl = child_name.lower()
    for prefix in _ANATOMICAL_LOCATION_PREFIXES:
        if cl.startswith(prefix) and cl[len(prefix):] == parent_name.lower():
            return True
    # Child = parent with a single location token inserted or added
    ct = _token_set(child_name)
    pt = _token_set(parent_name)
    if ct and pt and pt.issubset(ct):
        extra = ct - pt
        if extra and extra.issubset(_LOCATION_TOKENS | _MODIFIER_TOKENS):
            return True
    return False


def _is_relationship_not_isa(child_name: str, parent_name: str) -> bool:
    """Check if this looks like a relationship description, not IS-A."""
    ct = _token_set(child_name)
    pt = _token_set(parent_name)
    extra = ct - pt
    # All extra tokens are relationship indicators
    if extra and extra.issubset(_RELATIONSHIP_INDICATORS):
        return True
    return False


def assess_candidate(
    child_name: str,
    parent_name: str,
    base_score: float,
    method: str,
    candidate_id: uuid.UUID | None = None,
) -> QualityAssessment:
    """Score a single candidate for hierarchy quality."""
    cid = candidate_id or uuid.UUID(int=0)
    reasons: list[str] = []
    quality = base_score  # start from base

    # ── Pre-checks ──
    if not (child_name or "").strip() or not (parent_name or "").strip():
        return QualityAssessment(
            candidate_id=cid, child_name=child_name, parent_name=parent_name,
            base_score=base_score, quality_score=0.0, quality_tier="rejected",
            quality_reasons=["empty_name"], kept=False,
        )

    # ── Hard rejections ──
    # 1. Compound component method with low score
    if method == "compound_component":
        reasons.append("compound_component_method")
        quality *= 0.2

    # 2. Same token count, likely siblings
    ct = _token_set(child_name)
    pt = _token_set(parent_name)
    if ct and pt and len(ct) == len(pt) and len(ct) > 1:
        if _has_modality_substitution(child_name, parent_name):
            reasons.append("modality_substitution")
            quality *= 0.1
        elif not pt.issubset(ct):
            reasons.append("same_count_no_subset")
            quality *= 0.1
        else:
            reasons.append("same_token_count_sibling")
            quality *= 0.3

    # 3. Anatomical detail (location prefix only)
    if _is_anatomical_detail(child_name, parent_name):
        reasons.append("anatomical_detail_only")
        quality *= 0.2

    # 4. Relationship indicators (input/output/projection)
    if _is_relationship_not_isa(child_name, parent_name):
        reasons.append("relationship_not_isa")
        quality *= 0.15

    # 5. Very long descriptive phrases (> 6 tokens each) are suspicious
    if len(ct) > 6 and len(pt) > 5:
        reasons.append("very_long_descriptive")
        quality *= 0.5

    # ── Quality bonuses ──
    # 1. Clean IS-A: parent is a meaningful subset
    if _is_good_hierarchy(child_name, parent_name) and not reasons:
        reasons.append("good_isa_hierarchy")
        quality = min(quality * 1.2, 2.0)

    # 2. Parent is much shorter (clear generalization)
    if pt and ct and len(pt) <= len(ct) - 2:
        extra = ct - pt
        if extra and not extra.issubset(_MODIFIER_TOKENS | {
            t for t in extra if any(
                t.startswith(loc.split()[0]) for loc in _ANATOMICAL_LOCATION_PREFIXES
            )
        }):
            reasons.append("clear_generalization")
            quality = min(quality * 1.1, 2.0)

    # 3. Bonus for active parent
    # (handled externally with parent_status)

    # ── Tier assignment ──
    if quality >= HIGH_THRESHOLD:
        tier = "high_confidence"
    elif quality >= REVIEW_THRESHOLD:
        tier = "review"
    else:
        tier = "low_confidence"

    return QualityAssessment(
        candidate_id=cid,
        child_name=child_name,
        parent_name=parent_name,
        base_score=base_score,
        quality_score=round(quality, 4),
        quality_tier=tier,
        quality_reasons=reasons,
        kept=tier in ("high_confidence", "review"),
    )


async def run_quality_filter(
    session: AsyncSession,
    *,
    generation_version: str = "function_hierarchy_candidate_v2",
) -> dict[str, Any]:
    """Run quality filter on all candidates of the given version.

    Updates each candidate's generation_reasons_json with quality_tier,
    quality_score, and quality_reasons fields. Returns statistics.
    """
    rows = (
        await session.execute(
            select(OntologyHierarchyCandidate).where(
                OntologyHierarchyCandidate.generation_version == generation_version,
            )
        )
    ).scalars().all()

    if not rows:
        return {"total": 0, "error": "no_candidates_found"}

    # Pre-load term names
    term_ids: set[uuid.UUID] = set()
    for r in rows:
        term_ids.add(r.child_term_id)
        term_ids.add(r.parent_term_id)
    terms = (
        await session.execute(
            select(OntologyTerm).where(OntologyTerm.id.in_(term_ids))
        )
    ).scalars().all()
    term_names: dict[uuid.UUID, str] = {t.id: t.canonical_term_en for t in terms}
    term_status: dict[uuid.UUID, str] = {t.id: t.status for t in terms}

    # Assess each candidate
    stats: dict[str, Any] = {
        "total": len(rows),
        "by_tier": {"high_confidence": 0, "review": 0, "low_confidence": 0, "rejected": 0},
        "by_reason": {},
        "active_parent_high": 0,
        "proposed_parent_high": 0,
    }
    reassigned = 0

    for r in rows:
        child_name = term_names.get(r.child_term_id, "")
        parent_name = term_names.get(r.parent_term_id, "")
        assessment = assess_candidate(
            child_name=child_name,
            parent_name=parent_name,
            base_score=float(r.candidate_score or 0),
            method=r.generation_method or "",
            candidate_id=r.id,
        )

        # Active parent bonus
        if assessment.quality_tier == "high_confidence":
            pstatus = term_status.get(r.parent_term_id, "")
            if pstatus == "active":
                stats["active_parent_high"] += 1
            else:
                stats["proposed_parent_high"] += 1

        # Write quality fields into generation_reasons_json
        reasons_json = dict(r.generation_reasons_json or {})
        reasons_json["quality_tier"] = assessment.quality_tier
        reasons_json["quality_score"] = assessment.quality_score
        reasons_json["quality_reasons"] = assessment.quality_reasons
        r.generation_reasons_json = reasons_json

        stats["by_tier"][assessment.quality_tier] += 1
        for reason in assessment.quality_reasons:
            stats["by_reason"][reason] = stats["by_reason"].get(reason, 0) + 1

        reassigned += 1

    await session.flush()

    # Sort reason dict
    stats["by_reason"] = dict(sorted(stats["by_reason"].items(), key=lambda x: -x[1]))
    stats["reassigned"] = reassigned
    return stats


async def list_filtered_candidates(
    session: AsyncSession,
    *,
    tier: str | None = None,
    generation_version: str = "function_hierarchy_candidate_v2",
    min_quality_score: float | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """List candidates with quality filter applied."""
    rows = (
        await session.execute(
            select(OntologyHierarchyCandidate).where(
                OntologyHierarchyCandidate.generation_version == generation_version,
            )
        )
    ).scalars().all()

    term_ids: set[uuid.UUID] = set()
    for r in rows:
        term_ids.add(r.child_term_id)
        term_ids.add(r.parent_term_id)
    terms = (
        await session.execute(
            select(OntologyTerm).where(OntologyTerm.id.in_(term_ids))
        )
    ).scalars().all()
    term_names: dict[uuid.UUID, str] = {t.id: t.canonical_term_en for t in terms}
    term_status_map: dict[uuid.UUID, str] = {t.id: t.status for t in terms}

    filtered: list[dict[str, Any]] = []
    for r in rows:
        reasons = r.generation_reasons_json or {}
        q_tier = reasons.get("quality_tier", "unrated")
        q_score = reasons.get("quality_score", float(r.candidate_score or 0))

        if tier and q_tier != tier:
            continue
        if min_quality_score is not None and q_score < min_quality_score:
            continue

        filtered.append({
            "id": str(r.id),
            "child_term_id": str(r.child_term_id),
            "parent_term_id": str(r.parent_term_id),
            "child_name": term_names.get(r.child_term_id, ""),
            "parent_name": term_names.get(r.parent_term_id, ""),
            "child_status": term_status_map.get(r.child_term_id, ""),
            "parent_status": term_status_map.get(r.parent_term_id, ""),
            "base_score": float(r.candidate_score or 0),
            "quality_score": q_score,
            "quality_tier": q_tier,
            "quality_reasons": reasons.get("quality_reasons", []),
            "generation_method": r.generation_method,
        })

    filtered.sort(key=lambda x: -x["quality_score"])
    total = len(filtered)
    return filtered[offset:offset + limit], total


async def filter_stats(
    session: AsyncSession,
    *,
    generation_version: str = "function_hierarchy_candidate_v2",
) -> dict[str, Any]:
    """Summary statistics of quality-filtered candidates."""
    rows = (
        await session.execute(
            select(OntologyHierarchyCandidate).where(
                OntologyHierarchyCandidate.generation_version == generation_version,
            )
        )
    ).scalars().all()

    if not rows:
        return {"total": 0}

    by_tier: dict[str, int] = {}
    tier_scores: dict[str, list[float]] = {}
    children_by_tier: dict[str, set[uuid.UUID]] = {}

    for r in rows:
        reasons = r.generation_reasons_json or {}
        tier = reasons.get("quality_tier", "unrated")
        qs = reasons.get("quality_score", float(r.candidate_score or 0))

        by_tier[tier] = by_tier.get(tier, 0) + 1
        tier_scores.setdefault(tier, []).append(qs)
        children_by_tier.setdefault(tier, set()).add(r.child_term_id)

    result: dict[str, Any] = {
        "total": len(rows),
        "by_tier": by_tier,
        "children_covered_by_tier": {t: len(s) for t, s in children_by_tier.items()},
        "avg_quality_score_by_tier": {
            t: round(sum(scores) / len(scores), 4) if scores else 0
            for t, scores in tier_scores.items()
        },
    }
    return result
