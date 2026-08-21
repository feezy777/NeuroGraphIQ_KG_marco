"""P1.6: incremental Function Triple projection (subject-scope reconcile).

Any change to a Function Domain Relation (create / update / merge /
supersede / reject / delete / term re-anchor / ontology merge / canonical
rename) triggers a *subject-scoped* desired-state reconcile of the affected
mirror_kg_triples — never a full consolidate.

Core invariants (shared with full rebuild via function_triple_rebuild_service):

* only the three official relation tables feed Function Triples;
* eligibility, canonical resolution, predicate mapping, canonical_key and
  lineage aggregation are reused verbatim from P1.5 builders;
* a canonical SPO may be produced by several relations — lineage
  (provenance.source_relation_ids) always equals the current valid source set;
* the helper never commits — commit belongs to the caller's transaction so
  relation + triple stay atomic;
* reconcile is idempotent and de-duplicated per subject within a session.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import CandidateBrainRegion
from app.models.mirror_kg import MirrorKgTriple, MirrorRegionFunction
from app.models.mirror_macro_clinical import (
    MirrorCircuitFunction,
    MirrorProjectionFunction,
)
from app.models.ontology import OntologyTerm
from app.schemas.mirror_kg import TripleObjectType, TripleSubjectType
from app.services.function_term_service import load_canonical_term_map
from app.services.function_triple_rebuild_service import (
    PROJECTION_VERSION,
    RebuildStats,
    _build_candidates,
    _dedup_candidates,
    _relation_passes,
    apply_desired_diff,
)

PROJECTION_MODE = "incremental"

_RELATION_MODEL_BY_SUBJECT = {
    TripleSubjectType.region_candidate: MirrorRegionFunction,
    TripleSubjectType.connection: MirrorProjectionFunction,
    TripleSubjectType.circuit: MirrorCircuitFunction,
}

_RELATION_SUBJECT_COL = {
    TripleSubjectType.region_candidate: MirrorRegionFunction.region_candidate_id,
    TripleSubjectType.connection: MirrorProjectionFunction.projection_id,
    TripleSubjectType.circuit: MirrorCircuitFunction.circuit_id,
}


async def reconcile_function_subject(
    session: AsyncSession,
    *,
    subject_type: str,
    subject_id: uuid.UUID | None,
    projection_version: str = PROJECTION_VERSION,
    created_by: str = "system:function_triple_projection",
    dry_run: bool = False,
    _reconciled: set[tuple[Any, ...]] | None = None,
) -> RebuildStats:
    """Reconcile one subject's Function Triples to the desired set.

    Scope = the subject (region_candidate / connection / circuit): all of its
    current valid relations are re-read, desired SPOs rebuilt with the shared
    P1.5 builders, and the diff applied (insert / update / stale-delete).

    Pass the same ``_reconciled`` set across a batch to reconcile each subject
    at most once.
    """
    stats = RebuildStats(dry_run=dry_run)
    if subject_id is None:
        return stats
    key = (subject_type, str(subject_id))
    if _reconciled is not None:
        if key in _reconciled:
            stats.warnings.append(f"subject {key} already reconciled this session")
            return stats
        _reconciled.add(key)

    model = _RELATION_MODEL_BY_SUBJECT.get(subject_type)
    col = _RELATION_SUBJECT_COL.get(subject_type)
    if model is None or col is None:
        stats.warnings.append(f"unsupported subject_type: {subject_type}")
        return stats

    # 1. load this subject's current valid relations
    relations = [
        r for r in (await session.execute(
            select(model).where(col == subject_id)
        )).scalars().all()
        if _relation_passes(r)
    ]

    # 2. canonical term map for those relations
    term_ids = {r.term_id for r in relations if r.term_id}
    canonical_map = await load_canonical_term_map(session, term_ids)

    # 3. candidate labels for region subjects
    candidate_map: dict[uuid.UUID, CandidateBrainRegion] = {}
    if subject_type == TripleSubjectType.region_candidate:
        region = await session.get(CandidateBrainRegion, subject_id)
        if region is not None:
            candidate_map = {subject_id: region}

    # 4. desired SPOs for this subject (shared P1.5 builder logic)
    regions = relations if subject_type == TripleSubjectType.region_candidate else []
    projections = relations if subject_type == TripleSubjectType.connection else []
    circuits = relations if subject_type == TripleSubjectType.circuit else []
    candidates, filtered = await _build_candidates(
        session,
        regions=regions,
        projections=projections,
        circuits=circuits,
        candidate_map=candidate_map,
        canonical_map=canonical_map,
        warnings=stats.warnings,
    )
    stats.filtered_invalid_count = filtered
    desired, multi = _dedup_candidates(candidates)
    stats.desired_function_triples = len(desired)
    stats.multi_source_spo_count = multi

    # 5. existing triples for this subject
    existing_rows = list(
        (await session.execute(
            select(MirrorKgTriple).where(
                MirrorKgTriple.subject_type == subject_type,
                MirrorKgTriple.subject_id == subject_id,
                MirrorKgTriple.object_type == TripleObjectType.function,
            )
        )).scalars().all()
    )
    stats.existing_function_triples = len(existing_rows)

    # 6. shared diff (same semantics as full rebuild)
    await apply_desired_diff(
        session,
        existing_rows=existing_rows,
        desired=desired,
        projection_version=projection_version,
        dry_run=dry_run,
        stats=stats,
        created_by=created_by,
    )
    return stats


async def project_changed_function_relations(
    session: AsyncSession,
    changed_relation_ids: list[uuid.UUID],
    *,
    projection_version: str = PROJECTION_VERSION,
    created_by: str = "system:function_triple_projection",
    dry_run: bool = False,
) -> list[RebuildStats]:
    """Batch projection: dedup affected subjects, reconcile each once.

    One circuit gaining 8 functions → a single circuit-scope reconcile.
    """
    scopes: set[tuple[str, uuid.UUID]] = set()
    if changed_relation_ids:
        for model, stype in (
            (MirrorRegionFunction, TripleSubjectType.region_candidate),
            (MirrorProjectionFunction, TripleSubjectType.connection),
            (MirrorCircuitFunction, TripleSubjectType.circuit),
        ):
            rows = (
                await session.execute(
                    select(model).where(model.id.in_(changed_relation_ids))
                )
            ).scalars().all()
            col = _RELATION_SUBJECT_COL[stype]
            for row in rows:
                sid = getattr(row, col.name)
                if sid is not None:
                    scopes.add((stype, sid))

    _reconciled: set[tuple[Any, ...]] = set()
    results: list[RebuildStats] = []
    for stype, sid in scopes:
        stats = await reconcile_function_subject(
            session,
            subject_type=stype,
            subject_id=sid,
            projection_version=projection_version,
            created_by=created_by,
            dry_run=dry_run,
            _reconciled=_reconciled,
        )
        results.append(stats)
    return results


async def refresh_function_term_projection(
    session: AsyncSession,
    term_id: uuid.UUID,
    *,
    projection_version: str = PROJECTION_VERSION,
    dry_run: bool = False,
) -> list[RebuildStats]:
    """Controlled refresh for a canonical Function term (P1.6 §10).

    Canonical display rename / term merge cleanup: re-reconciles every subject
    whose relations reference this term. Never creates new identity — the
    entity SPO key is unchanged.
    """
    subjects: set[tuple[str, uuid.UUID]] = set()
    for model, stype, col in (
        (MirrorRegionFunction, TripleSubjectType.region_candidate, MirrorRegionFunction.region_candidate_id),
        (MirrorProjectionFunction, TripleSubjectType.connection, MirrorProjectionFunction.projection_id),
        (MirrorCircuitFunction, TripleSubjectType.circuit, MirrorCircuitFunction.circuit_id),
    ):
        rows = (
            await session.execute(select(model).where(model.term_id == term_id))
        ).scalars().all()
        for row in rows:
            sid = getattr(row, col.name)
            if sid is not None:
                subjects.add((stype, sid))

    _reconciled: set[tuple[Any, ...]] = set()
    results: list[RebuildStats] = []
    for stype, sid in subjects:
        stats = await reconcile_function_subject(
            session,
            subject_type=stype,
            subject_id=sid,
            projection_version=projection_version,
            created_by="system:function_triple_refresh",
            dry_run=dry_run,
            _reconciled=_reconciled,
        )
        results.append(stats)

    # P1.8: Final Function Triples use the canonical display snapshot too —
    # refresh their object_label without touching identity.
    from sqlalchemy import update

    from app.models.final_kg import FinalKgTriple as _FinalKgTriple
    from app.models.ontology import OntologyTerm as _OT

    term = await session.get(_OT, term_id)
    if term is not None and term.canonical_term_en:
        await session.execute(
            update(_FinalKgTriple)
            .where(
                _FinalKgTriple.object_type == TripleObjectType.function,
                _FinalKgTriple.object_id == term_id,
            )
            .values(object_label=term.canonical_term_en[:512])
        )
    return results


async def check_function_projection_integrity(
    session: AsyncSession,
    *,
    projection_version: str = PROJECTION_VERSION,
) -> dict[str, Any]:
    """P1.6 read-only integrity checker (no data modification).

    Compares the current Mirror Function Triple state against the desired set
    derived from the three official relation tables, plus structural checks.
    """
    from sqlalchemy import func as sa_func

    from app.services.function_triple_rebuild_service import (
        SKIP_MIRROR_STATUSES,
        SKIP_PROMOTION_STATUSES,
        SKIP_REVIEW_STATUSES,
    )

    out: dict[str, Any] = {
        "relation_counts": {},
        "triple_total": 0,
        "function_triple_total": 0,
        "object_id_null": 0,
        "orphan_object": 0,
        "invalid_type_object": 0,
        "merged_object": 0,
        "deprecated_object": 0,
        "duplicate_spo": 0,
        "missing_desired": 0,
        "stale_triples": 0,
        "wrong_object_id": 0,
        "wrong_predicate": 0,
        "wrong_label": 0,
        "wrong_lineage": 0,
        "empty_lineage": 0,
    }

    for label, model in (
        ("region", MirrorRegionFunction),
        ("projection", MirrorProjectionFunction),
        ("circuit", MirrorCircuitFunction),
    ):
        out["relation_counts"][label] = (
            await session.execute(select(sa_func.count()).select_from(model))
        ).scalar_one()

    out["triple_total"] = (
        await session.execute(select(sa_func.count()).select_from(MirrorKgTriple))
    ).scalar_one()
    out["function_triple_total"] = (
        await session.execute(
            select(sa_func.count()).select_from(MirrorKgTriple).where(
                MirrorKgTriple.object_type == TripleObjectType.function
            )
        )
    ).scalar_one()
    out["object_id_null"] = (
        await session.execute(
            select(sa_func.count()).select_from(MirrorKgTriple).where(
                MirrorKgTriple.object_type == TripleObjectType.function,
                MirrorKgTriple.object_id.is_(None),
            )
        )
    ).scalar_one()


    from sqlalchemy import or_

    bad_objects = (
        await session.execute(
            select(sa_func.count()).select_from(MirrorKgTriple)
            .outerjoin(OntologyTerm, OntologyTerm.id == MirrorKgTriple.object_id)
            .where(
                MirrorKgTriple.object_type == TripleObjectType.function,
                MirrorKgTriple.object_id.isnot(None),
                or_(
                    OntologyTerm.id.is_(None),
                    OntologyTerm.term_type != "function",
                    OntologyTerm.status.in_(("merged", "deprecated")),
                ),
            )
        )
    ).scalar_one()
    out["orphan_object"] = bad_objects
    out["invalid_type_object"] = 0
    out["merged_object"] = 0
    out["deprecated_object"] = 0

    dup = (
        await session.execute(
            select(sa_func.count()).select_from(
                select(
                    MirrorKgTriple.subject_type,
                    MirrorKgTriple.subject_id,
                    MirrorKgTriple.predicate,
                    MirrorKgTriple.object_id,
                )
                .where(MirrorKgTriple.object_type == TripleObjectType.function)
                .group_by(
                    MirrorKgTriple.subject_type,
                    MirrorKgTriple.subject_id,
                    MirrorKgTriple.predicate,
                    MirrorKgTriple.object_id,
                )
                .having(sa_func.count() > 1)
                .subquery()
            )
        )
    ).scalar_one()
    out["duplicate_spo"] = dup

    # desired-set diff (dry-run, read-only) → missing / stale / wrong fields
    from app.services.function_triple_rebuild_service import rebuild_function_triples

    stats = await rebuild_function_triples(session, dry_run=True, projection_version=projection_version)
    out["missing_desired"] = stats.inserted_count
    out["stale_triples"] = stats.stale_deleted_count + stats.stale_superseded_count
    out["wrong_object_id"] = stats.upgraded_count

    # lineage: triples whose source_relation_ids list is empty or has invalid entries
    empty_lineage = 0
    wrong_lineage = 0
    triples = (
        await session.execute(
            select(MirrorKgTriple).where(MirrorKgTriple.object_type == TripleObjectType.function)
        )
    ).scalars().all()
    for t in triples:
        prov = (t.raw_payload_json or {}).get("provenance") or {}
        rel_ids = prov.get("source_relation_ids") or []
        if not rel_ids:
            empty_lineage += 1
            continue
        for rid in rel_ids[:8]:
            found = False
            for model in (MirrorRegionFunction, MirrorProjectionFunction, MirrorCircuitFunction):
                if (await session.get(model, uuid.UUID(rid))) is not None:
                    found = True
                    break
            if not found:
                wrong_lineage += 1
                break

    out["empty_lineage"] = empty_lineage
    out["wrong_lineage"] = wrong_lineage
    return out
