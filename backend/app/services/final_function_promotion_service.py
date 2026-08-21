"""P1.7: Mirror → Final Function promotion support.

Shared helpers used by both promotion chains (Step 9 mirror_promotion_service
and final_macro_clinical_promotion_service):

* canonical Function term eligibility — Final accepts ONLY canonical active
  Functions (proposed/deprecated/invalid/missing are blockers; merged resolves
  to its canonical target and is accepted only when that target is active);
* Final Function Triple projection — a promoted Final Function Relation
  immediately produces its Final Function Triple (object_id = ontology_terms.id,
  subject = Final entity id). No blind Mirror-triple copying.

Mirror and Final share the SAME canonical Function identity (ontology_terms.id):
no new Final Function entity is ever created.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.final_kg import FinalKgTriple
from app.models.final_macro_clinical import (
    FinalCircuitFunction,
    FinalProjectionFunction,
)
from app.models.final_kg import FinalRegionFunction
from app.schemas.mirror_kg import TripleObjectType, TripleScope
from app.services.function_term_service import (
    FunctionTermResolution,
    resolve_canonical_function_term,
)
from app.services.llm_function_extraction_service import RELATION_TO_PREDICATE

FINAL_FUNCTION_TARGETS = frozenset({"function", "region_function", "projection_function", "circuit_function"})


async def check_function_term_eligibility(
    session: AsyncSession,
    obj: Any,
) -> tuple[bool, str | None, FunctionTermResolution | None]:
    """P1.7: Final only accepts canonical active Function terms.

    Returns (ok, blocker_reason, resolution). Reasons:
    function_term_missing / function_term_not_active / function_term_deprecated /
    function_term_invalid.
    """
    if obj.term_id is None:
        return False, "function_term_missing", None
    res = await resolve_canonical_function_term(session, obj.term_id)
    if not res.is_function_term or res.term_id is None:
        return False, "function_term_invalid", res
    if res.status == "active":
        return True, None, res
    if res.status == "deprecated":
        return False, "function_term_deprecated", res
    if res.status == "proposed":
        return False, "function_term_not_active", res
    # merged residue (canonical chain ended on a non-active target)
    return False, "function_term_not_active", res


def final_function_predicate(obj: Any) -> str:
    """Predicate for the Final Function Triple (shared Mirror mapping)."""
    relation_type = getattr(obj, "relation_type", None) or "associated_with"
    return RELATION_TO_PREDICATE.get(relation_type, "associated_with_function")


async def project_final_function_triple(
    session: AsyncSession,
    *,
    mirror_relation: Any,
    final_relation: Any,
    canonical: FunctionTermResolution,
    subject_type: str,
    subject_id: uuid.UUID,
    subject_label: str,
    review_record_id: uuid.UUID | None = None,
    promotion_record_id: uuid.UUID | None = None,
    created_by: str = "system:final_function_promotion",
) -> FinalKgTriple | None:
    """Final Function Relation → Final Function Triple (idempotent).

    object_id = canonical ontology_terms.id (Mirror/Final shared identity).
    subject = Final entity id. Lineage kept in provenance_json:
    source_final_relation_id + source_mirror_relation_id.
    """
    predicate = final_function_predicate(mirror_relation)
    canonical_id = canonical.term_id
    if canonical_id is None:
        return None

    # idempotent: same (subject, predicate, object) already projected
    existing = (
        await session.execute(
            select(FinalKgTriple).where(
                FinalKgTriple.subject_type == subject_type,
                FinalKgTriple.subject_id == subject_id,
                FinalKgTriple.predicate == predicate,
                FinalKgTriple.object_type == TripleObjectType.function,
                FinalKgTriple.object_id == canonical_id,
            ).limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    source_final_function_id: uuid.UUID | None = None
    source_final_circuit_id: uuid.UUID | None = None
    final_projection_id: uuid.UUID | None = None
    if isinstance(final_relation, FinalRegionFunction):
        source_final_function_id = final_relation.id
    elif isinstance(final_relation, FinalProjectionFunction):
        final_projection_id = final_relation.final_projection_id
    elif isinstance(final_relation, FinalCircuitFunction):
        source_final_circuit_id = final_relation.final_circuit_id

    source_mirror_function_id: uuid.UUID | None = None
    source_mirror_connection_id: uuid.UUID | None = None
    source_mirror_circuit_id: uuid.UUID | None = None
    if getattr(mirror_relation, "region_candidate_id", None) is not None:
        source_mirror_function_id = mirror_relation.id
    elif getattr(mirror_relation, "projection_id", None) is not None:
        source_mirror_connection_id = mirror_relation.projection_id
    elif getattr(mirror_relation, "circuit_id", None) is not None:
        source_mirror_circuit_id = mirror_relation.circuit_id

    triple = FinalKgTriple(
        subject_type=subject_type,
        subject_id=subject_id,
        subject_label=subject_label[:512],
        predicate=predicate,
        object_type=TripleObjectType.function,
        object_id=canonical_id,
        object_label=(canonical.canonical_name or "")[:512],
        triple_scope=TripleScope.same_granularity,
        resource_id=getattr(mirror_relation, "resource_id", None),
        batch_id=getattr(mirror_relation, "batch_id", None),
        llm_run_id=getattr(mirror_relation, "llm_run_id", None),
        llm_item_id=getattr(mirror_relation, "llm_item_id", None),
        review_record_id=review_record_id,
        promotion_record_id=promotion_record_id,
        source_final_function_id=source_final_function_id,
        source_final_circuit_id=source_final_circuit_id,
        source_mirror_function_id=source_mirror_function_id,
        source_mirror_connection_id=source_mirror_connection_id,
        source_mirror_circuit_id=source_mirror_circuit_id,
        granularity_level=getattr(mirror_relation, "granularity_level", "") or "",
        granularity_family=getattr(mirror_relation, "granularity_family", None),
        source_atlas=getattr(mirror_relation, "source_atlas", "") or "",
        source_version=getattr(mirror_relation, "source_version", None),
        confidence=getattr(mirror_relation, "confidence", None),
        evidence_text=getattr(mirror_relation, "evidence_text", None),
        uncertainty_reason=getattr(mirror_relation, "uncertainty_reason", None),
        final_status="active",
        raw_payload_json={
            "source": "final_function_projection",
            "projection_mode": "promotion",
            "source_final_relation_id": str(final_relation.id),
            "source_final_projection_id": str(final_projection_id) if final_projection_id else None,
            "source_mirror_relation_id": str(mirror_relation.id),
            "term_id": str(canonical_id),
            "term_code": canonical.term_code,
        },
        normalized_payload_json={
            "predicate": predicate,
            "canonical_term_id": str(canonical_id),
            "generation_source": "final_function_relation",
        },
    )
    session.add(triple)
    await session.flush()
    return triple


async def check_final_function_integrity(
    session: AsyncSession,
) -> dict[str, int]:
    """P1.7 read-only checker for Final Function relations & triples (P1.8 reuses)."""
    from sqlalchemy import func as sa_func
    from sqlalchemy import or_

    from app.models.ontology import OntologyTerm

    out: dict[str, int] = {
        "final_region_functions": 0,
        "final_projection_functions": 0,
        "final_circuit_functions": 0,
        "final_kg_triples_total": 0,
        "final_function_triples": 0,
        "relation_term_id_null": 0,
        "relation_orphan_term": 0,
        "relation_invalid_term": 0,
        "relation_proposed_term": 0,
        "relation_merged_term": 0,
        "relation_deprecated_term": 0,
        "relation_duplicate_semantic": 0,
        "relation_missing_source_mapping": 0,
        "triple_object_id_null": 0,
        "triple_orphan_object": 0,
        "triple_invalid_object": 0,
        "triple_proposed_object": 0,
        "triple_merged_object": 0,
        "triple_deprecated_object": 0,
        "triple_duplicate_spo": 0,
        "triple_missing_final_relation_lineage": 0,
        "triple_mirror_subject": 0,
        "triple_wrong_object_id": 0,
        "triple_wrong_label": 0,
    }

    rel_models = {
        "final_region_functions": FinalRegionFunction,
        "final_projection_functions": FinalProjectionFunction,
        "final_circuit_functions": FinalCircuitFunction,
    }
    for label, model in rel_models.items():
        out[label] = (
            await session.execute(select(sa_func.count()).select_from(model))
        ).scalar_one()
        out["relation_term_id_null"] += (
            await session.execute(
                select(sa_func.count()).select_from(model).where(model.term_id.is_(None))
            )
        ).scalar_one()

    # join term status for all three relation tables
    for model in rel_models.values():
        rows = (
            await session.execute(
                select(model.term_id, OntologyTerm.status, OntologyTerm.term_type)
                .outerjoin(OntologyTerm, OntologyTerm.id == model.term_id)
            )
        ).all()
        for term_id, status, term_type in rows:
            if term_id is None:
                continue
            if status is None:
                out["relation_orphan_term"] += 1
            elif term_type != "function":
                out["relation_invalid_term"] += 1
            elif status == "proposed":
                out["relation_proposed_term"] += 1
            elif status == "merged":
                out["relation_merged_term"] += 1
            elif status == "deprecated":
                out["relation_deprecated_term"] += 1

    out["final_kg_triples_total"] = (
        await session.execute(select(sa_func.count()).select_from(FinalKgTriple))
    ).scalar_one()
    out["final_function_triples"] = (
        await session.execute(
            select(sa_func.count()).select_from(FinalKgTriple).where(
                FinalKgTriple.object_type == TripleObjectType.function
            )
        )
    ).scalar_one()
    out["triple_object_id_null"] = (
        await session.execute(
            select(sa_func.count()).select_from(FinalKgTriple).where(
                FinalKgTriple.object_type == TripleObjectType.function,
                FinalKgTriple.object_id.is_(None),
            )
        )
    ).scalar_one()

    triples = (
        await session.execute(
            select(FinalKgTriple, OntologyTerm).outerjoin(
                OntologyTerm, OntologyTerm.id == FinalKgTriple.object_id
            ).where(FinalKgTriple.object_type == TripleObjectType.function)
        )
    ).all()
    seen_spo: set[tuple] = set()
    for triple, term in triples:
        if triple.object_id is None:
            continue
        spo = (triple.subject_type, str(triple.subject_id), triple.predicate, str(triple.object_id))
        if spo in seen_spo:
            out["triple_duplicate_spo"] += 1
        seen_spo.add(spo)
        if term is None:
            out["triple_orphan_object"] += 1
        elif term.term_type != "function":
            out["triple_invalid_object"] += 1
        elif term.status == "proposed":
            out["triple_proposed_object"] += 1
        elif term.status == "merged":
            out["triple_merged_object"] += 1
        elif term.status == "deprecated":
            out["triple_deprecated_object"] += 1
        if term is not None and triple.object_label != term.canonical_term_en:
            out["triple_wrong_label"] += 1
        # lineage: must reference a Final function relation
        has_lineage = (
            triple.source_final_function_id is not None
            or triple.source_final_circuit_id is not None
            or (triple.raw_payload_json or {}).get("source_final_projection_id") is not None
        )
        if not has_lineage:
            out["triple_missing_final_relation_lineage"] += 1
        # subject must be a Final entity id (region_candidate is the stable
        # Final identity for region functions — there is no separate final
        # region table; connection/circuit/mirror_* subjects are mirror-only)
        if triple.subject_type in ("connection", "circuit", "mirror_connection", "mirror_circuit"):
            out["triple_mirror_subject"] += 1

    return out


async def propagate_ontology_merge_to_final(
    session: AsyncSession,
    *,
    source_term_id: uuid.UUID,
    target_term_id: uuid.UUID,
) -> dict[str, int]:
    """P1.8: after an ontology merge, Final relations & triples must never keep
    pointing at the merged term (canonical identity governance).

    Duplicate-safe: rows that already carry the target term are left alone;
    the merged-term rows are re-pointed (source rows may have been merged into
    the same target by duplicate-safe relation redirect).
    """
    from sqlalchemy import update

    counts = {"relations": 0, "triples": 0}

    for model in (FinalRegionFunction, FinalProjectionFunction, FinalCircuitFunction):
        result = await session.execute(
            update(model)
            .where(model.term_id == source_term_id, model.term_id != target_term_id)
            .values(term_id=target_term_id)
        )
        counts["relations"] += result.rowcount or 0

    triple_result = await session.execute(
        update(FinalKgTriple)
        .where(
            FinalKgTriple.object_type == TripleObjectType.function,
            FinalKgTriple.object_id == source_term_id,
            FinalKgTriple.object_id != target_term_id,
        )
        .values(object_id=target_term_id)
    )
    counts["triples"] = triple_result.rowcount or 0
    await session.flush()
    return counts
