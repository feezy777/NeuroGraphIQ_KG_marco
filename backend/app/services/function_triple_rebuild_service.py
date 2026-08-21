"""P1.5: Function Triple entity-ization — rebuild desired set, diff, apply.

Mirror Function Triple becomes:

    subject --predicate--> Function Entity (object_id = canonical ontology_terms.id)

* object_label is a canonical display snapshot only (never identity);
* canonical identity = S + P + O(term_id) — display text changes cannot create
  a new Triple;
* only the three official relation tables feed Function Triples
  (mirror_region_functions / mirror_projection_functions / mirror_circuit_functions);
* multi-relation → same SPO keeps full lineage in raw_payload_json
  (provenance.source_relation_ids), with the primary relation id kept in the
  legacy source_mirror_*_id column;
* rebuild is idempotent: the second run inserts 0 and changes 0.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import CandidateBrainRegion
from app.models.mirror_kg import (
    MirrorKgTriple,
    MirrorRegionCircuit,
    MirrorRegionConnection,
    MirrorRegionFunction,
)
from app.models.mirror_macro_clinical import (
    MirrorCircuitFunction,
    MirrorProjectionFunction,
)
from app.models.ontology import OntologyTerm
from app.schemas.mirror_kg import (
    MirrorPromotionStatus,
    MirrorReviewStatus,
    MirrorStatus,
    TripleObjectType,
    TripleScope,
    TripleSubjectType,
)
from app.services import mirror_kg_service
from app.services.function_term_service import (
    FunctionTermResolution,
    VALID_TRIPLE_TERM_STATES,
    load_canonical_term_map,
)
from app.services.llm_function_extraction_service import RELATION_TO_PREDICATE

PROJECTION_VERSION = "function_entity_v1"

SKIP_MIRROR_STATUSES = frozenset({
    MirrorStatus.human_rejected,
    MirrorStatus.superseded,
    MirrorStatus.promoted_to_final,
})
SKIP_REVIEW_STATUSES = frozenset({MirrorReviewStatus.rejected})
SKIP_PROMOTION_STATUSES = frozenset({
    MirrorPromotionStatus.failed,
    MirrorPromotionStatus.promoted,
})

@dataclass
class FunctionTripleCandidate:
    """One desired entity-ized Function Triple (pre-dedup)."""

    subject_type: str
    subject_id: uuid.UUID | None
    subject_label: str
    predicate: str
    object_id: uuid.UUID
    object_label: str
    term_code: str | None
    source_type: str                      # region_function | projection_function | circuit_function
    source_relation_ids: list[uuid.UUID] = field(default_factory=list)
    source_texts: list[str] = field(default_factory=list)
    resource_id: uuid.UUID | None = None
    batch_id: uuid.UUID | None = None
    llm_run_id: uuid.UUID | None = None
    llm_item_id: uuid.UUID | None = None
    confidence: float | None = None
    evidence_text: str | None = None
    uncertainty_reason: str | None = None
    mirror_status: str = MirrorStatus.llm_suggested
    review_status: str = MirrorReviewStatus.pending

    def spo_key(self) -> tuple[Any, ...]:
        return (
            self.subject_type,
            str(self.subject_id) if self.subject_id else "",
            self.predicate,
            self.object_type_key(),
            str(self.object_id),
        )

    def object_type_key(self) -> str:
        return TripleObjectType.function


@dataclass
class RebuildStats:
    dry_run: bool
    existing_function_triples: int = 0
    desired_function_triples: int = 0
    multi_source_spo_count: int = 0
    upgraded_count: int = 0
    inserted_count: int = 0
    stale_deleted_count: int = 0
    stale_superseded_count: int = 0
    filtered_invalid_count: int = 0
    semantic_collision_count: int = 0
    warnings: list[str] = field(default_factory=list)


def _relation_passes(rel) -> bool:
    if rel.mirror_status in SKIP_MIRROR_STATUSES:
        return False
    if rel.review_status in SKIP_REVIEW_STATUSES:
        return False
    if rel.promotion_status in SKIP_PROMOTION_STATUSES:
        return False
    return True


def _norm(text: str) -> str:
    import re

    return " ".join(re.findall(r"[a-z0-9]+", (text or "").lower()))


async def _build_candidates(
    session: AsyncSession,
    *,
    regions: list[MirrorRegionFunction],
    projections: list[MirrorProjectionFunction],
    circuits: list[MirrorCircuitFunction],
    candidate_map: dict[uuid.UUID, CandidateBrainRegion],
    canonical_map: dict[uuid.UUID, FunctionTermResolution],
    warnings: list[str],
) -> tuple[list[FunctionTripleCandidate], int]:
    candidates: list[FunctionTripleCandidate] = []
    filtered = 0

    region_label: dict[uuid.UUID, str] = {}
    for rid, cand in candidate_map.items():
        region_label[rid] = cand.en_name or cand.cn_name or cand.std_name or cand.raw_name or str(rid)[:8]

    def _canonical_for(term_id: uuid.UUID | None, rel_id: uuid.UUID, rel_type: str):
        """Returns (canonical id, label, code) or (None, ...) when filtered."""
        nonlocal filtered
        if term_id is None:
            filtered += 1
            warnings.append(f"{rel_type} {rel_id} skipped: unresolved term_id")
            return None
        res = canonical_map.get(term_id)
        if res is None:
            filtered += 1
            warnings.append(f"{rel_type} {rel_id} skipped: term {term_id} not resolvable")
            return None
        if not res.is_function_term or res.state not in VALID_TRIPLE_TERM_STATES:
            filtered += 1
            warnings.append(
                f"{rel_type} {rel_id} skipped: term {term_id} state={res.state} "
                f"status={res.status} (deprecated/invalid/merged-residue not projected)"
            )
            return None
        return res.term_id, res.canonical_name or "", res.term_code

    for fn in regions:
        canon = _canonical_for(fn.term_id, fn.id, "region_function")
        if canon is None:
            continue
        obj_id, obj_label, term_code = canon
        predicate = RELATION_TO_PREDICATE.get(fn.relation_type, "associated_with_function")
        candidates.append(FunctionTripleCandidate(
            subject_type=TripleSubjectType.region_candidate,
            subject_id=fn.region_candidate_id,
            subject_label=region_label.get(fn.region_candidate_id) or "unknown",
            predicate=predicate,
            object_id=obj_id,
            object_label=obj_label,
            term_code=term_code,
            source_type="region_function",
            source_relation_ids=[fn.id],
            source_texts=[fn.function_term or ""],
            resource_id=fn.resource_id,
            batch_id=fn.batch_id,
            llm_run_id=fn.llm_run_id,
            llm_item_id=fn.llm_item_id,
            confidence=float(fn.confidence) if fn.confidence is not None else None,
            evidence_text=fn.evidence_text,
            uncertainty_reason=fn.uncertainty_reason,
            mirror_status=fn.mirror_status,
            review_status=fn.review_status,
        ))

    for fn in projections:
        canon = _canonical_for(fn.term_id, fn.id, "projection_function")
        if canon is None:
            continue
        obj_id, obj_label, term_code = canon
        predicate = RELATION_TO_PREDICATE.get(fn.relation_type, "associated_with_function")
        candidates.append(FunctionTripleCandidate(
            subject_type=TripleSubjectType.connection,
            subject_id=fn.projection_id,
            subject_label=str(fn.projection_id)[:8],
            predicate=predicate,
            object_id=obj_id,
            object_label=obj_label,
            term_code=term_code,
            source_type="projection_function",
            source_relation_ids=[fn.id],
            source_texts=[fn.function_term or ""],
            resource_id=fn.resource_id,
            batch_id=fn.batch_id,
            llm_run_id=fn.llm_run_id,
            llm_item_id=fn.llm_item_id,
            confidence=float(fn.confidence) if fn.confidence is not None else None,
            evidence_text=fn.evidence_text,
            uncertainty_reason=fn.uncertainty_reason,
            mirror_status=fn.mirror_status,
            review_status=fn.review_status,
        ))

    for fn in circuits:
        canon = _canonical_for(fn.term_id, fn.id, "circuit_function")
        if canon is None:
            continue
        obj_id, obj_label, term_code = canon
        candidates.append(FunctionTripleCandidate(
            subject_type=TripleSubjectType.circuit,
            subject_id=fn.circuit_id,
            subject_label=str(fn.circuit_id)[:8],
            predicate="associated_with_function",
            object_id=obj_id,
            object_label=obj_label,
            term_code=term_code,
            source_type="circuit_function",
            source_relation_ids=[fn.id],
            source_texts=[fn.function_term_en or fn.function_term_cn or ""],
            resource_id=fn.resource_id,
            batch_id=fn.batch_id,
            llm_run_id=fn.llm_run_id,
            llm_item_id=fn.llm_item_id,
            confidence=float(fn.confidence) if fn.confidence is not None else None,
            evidence_text=fn.evidence_text,
            uncertainty_reason=fn.uncertainty_reason,
            mirror_status=fn.mirror_status,
            review_status=fn.review_status,
        ))

    return candidates, filtered


def _dedup_candidates(
    candidates: list[FunctionTripleCandidate],
) -> tuple[list[FunctionTripleCandidate], int]:
    """Aggregate per SPO: one candidate per (S, P, O-entity), lineage preserved."""
    by_spo: dict[tuple[Any, ...], FunctionTripleCandidate] = {}
    multi = 0
    for cand in candidates:
        key = cand.spo_key()
        existing = by_spo.get(key)
        if existing is None:
            by_spo[key] = cand
            continue
        multi += 1
        existing.source_relation_ids.extend(
            rid for rid in cand.source_relation_ids if rid not in existing.source_relation_ids
        )
        existing.source_texts.extend(
            t for t in cand.source_texts if t and t not in existing.source_texts
        )
        if cand.confidence is not None and (existing.confidence is None or cand.confidence > existing.confidence):
            existing.confidence = cand.confidence
        if cand.evidence_text and not existing.evidence_text:
            existing.evidence_text = cand.evidence_text
        if not existing.llm_run_id and cand.llm_run_id:
            existing.llm_run_id = cand.llm_run_id
            existing.llm_item_id = cand.llm_item_id
    return list(by_spo.values()), multi


def _payload_for(cand: FunctionTripleCandidate, projection_version: str) -> dict[str, Any]:
    return {
        "source": projection_version,
        "source_type": cand.source_type,
        "term_id": str(cand.object_id),
        "term_code": cand.term_code,
        "provenance": {
            "projection_version": projection_version,
            "source_relation_ids": [str(r) for r in cand.source_relation_ids],
            "source_texts": cand.source_texts,
        },
    }


async def rebuild_function_triples(
    session: AsyncSession,
    *,
    dry_run: bool = True,
    projection_version: str = PROJECTION_VERSION,
    scope_resource_id: uuid.UUID | None = None,
    scope_batch_id: uuid.UUID | None = None,
) -> RebuildStats:
    """Rebuild Mirror Function Triples from the three relation tables.

    Idempotent: run twice → second run inserts 0 / changes 0.
    Never produces object_id=NULL Function Triples.
    """
    stats = RebuildStats(dry_run=dry_run)
    warnings = stats.warnings

    def _scope(cond, model):
        if scope_resource_id:
            cond.append(model.resource_id == scope_resource_id)
        if scope_batch_id:
            cond.append(model.batch_id == scope_batch_id)
        return cond

    region_q = select(MirrorRegionFunction).where(*_scope([], MirrorRegionFunction))
    projection_q = select(MirrorProjectionFunction).where(*_scope([], MirrorProjectionFunction))
    circuit_q = select(MirrorCircuitFunction).where(*_scope([], MirrorCircuitFunction))

    regions = [r for r in (await session.execute(region_q)).scalars().all() if _relation_passes(r)]
    projections = [r for r in (await session.execute(projection_q)).scalars().all() if _relation_passes(r)]
    circuits = [r for r in (await session.execute(circuit_q)).scalars().all() if _relation_passes(r)]

    term_ids = {r.term_id for r in regions + projections + circuits if r.term_id}
    canonical_map = await load_canonical_term_map(session, term_ids)

    region_ids = {r.region_candidate_id for r in regions if r.region_candidate_id}
    candidate_map: dict[uuid.UUID, CandidateBrainRegion] = {}
    if region_ids:
        rows = (
            await session.execute(
                select(CandidateBrainRegion).where(CandidateBrainRegion.id.in_(region_ids))
            )
        ).scalars().all()
        candidate_map = {r.id: r for r in rows}

    candidates, filtered = await _build_candidates(
        session,
        regions=regions,
        projections=projections,
        circuits=circuits,
        candidate_map=candidate_map,
        canonical_map=canonical_map,
        warnings=warnings,
    )
    stats.filtered_invalid_count = filtered

    desired, multi = _dedup_candidates(candidates)
    stats.desired_function_triples = len(desired)
    stats.multi_source_spo_count = multi

    # ---- load existing function triples (scoped when a scope is given) ----
    existing_q = select(MirrorKgTriple).where(
        MirrorKgTriple.object_type == TripleObjectType.function
    )
    if scope_resource_id:
        existing_q = existing_q.where(MirrorKgTriple.resource_id == scope_resource_id)
    if scope_batch_id:
        existing_q = existing_q.where(MirrorKgTriple.batch_id == scope_batch_id)
    existing_rows = list((await session.execute(existing_q)).scalars().all())
    stats.existing_function_triples = len(existing_rows)

    await apply_desired_diff(
        session,
        existing_rows=existing_rows,
        desired=desired,
        projection_version=projection_version,
        dry_run=dry_run,
        stats=stats,
        created_by="system:function_triple_rebuild",
    )
    return stats


def _match_null_object(
    row: MirrorKgTriple,
    desired_by_subject: dict[tuple[Any, ...], list[FunctionTripleCandidate]],
):
    """Match a legacy NULL-object triple to a desired candidate.

    Same (subject, predicate); label-normalize equals the canonical name OR the
    label appears among the candidate's relation source texts.
    """
    cands = desired_by_subject.get((row.subject_type, row.subject_id), [])
    cands = [c for c in cands if c.predicate == row.predicate]
    if not cands:
        return None
    row_norm = _norm(row.object_label)
    for c in cands:
        if _norm(c.object_label) == row_norm:
            return c
        if any(_norm(t) == row_norm for t in c.source_texts):
            return c
    return None


async def _triple_is_referenced(session: AsyncSession, triple_id: uuid.UUID) -> bool:
    """Governance references to a triple row (review / evidence / promotion)."""
    from sqlalchemy import text

    probes = [
        text(
            "SELECT 1 FROM mirror_human_review_records WHERE target_type='mirror_triple' AND target_id=:tid LIMIT 1"
        ),
        text(
            "SELECT 1 FROM mirror_evidence_records WHERE evidence_target_type='mirror_triple' AND evidence_target_id=:tid LIMIT 1"
        ),
        text(
            "SELECT 1 FROM mirror_promotion_records WHERE target_type='triple' AND mirror_target_id=:tid LIMIT 1"
        ),
    ]
    for probe in probes:
        try:
            res = await session.execute(probe, {"tid": triple_id})
            if res.scalar_one_or_none() is not None:
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def cand_source_relation_ids(cand: FunctionTripleCandidate) -> list[str]:
    """Lineage ids of a desired candidate (as strings, for diffing)."""
    return [str(r) for r in cand.source_relation_ids]


async def apply_desired_diff(
    session: AsyncSession,
    *,
    existing_rows: list[MirrorKgTriple],
    desired: list[FunctionTripleCandidate],
    projection_version: str,
    dry_run: bool,
    stats: RebuildStats,
    created_by: str,
) -> None:
    """P1.6 shared reconcile core: diff existing triples vs desired set.

    Used by both full rebuild (P1.5) and incremental projection (P1.6) so the
    two always produce identical results. Only flushes; commit is owned by the
    caller's transaction.
    """
    desired_by_key = {c.spo_key(): c for c in desired}
    # index desired by subject for O(1)-ish NULL-object matching
    desired_by_subject: dict[tuple[Any, ...], list[FunctionTripleCandidate]] = {}
    for c in desired:
        desired_by_subject.setdefault((c.subject_type, c.subject_id), []).append(c)

    # precomputed match keys for existing rows (ID-based + legacy label-based)
    existing_keys: set[tuple[Any, ...]] = set()
    for r in existing_rows:
        sid = str(r.subject_id) if r.subject_id else ""
        if r.object_id is not None:
            existing_keys.add((r.subject_type, sid, r.predicate, str(r.object_id)))
        else:
            existing_keys.add((r.subject_type, sid, r.predicate, _norm(r.object_label)))

    matched_existing_ids: set[uuid.UUID] = set()
    # SPOs already covered by an *earlier matched row* — later rows with the
    # same SPO are duplicate legacy triples and become stale.
    covered_spos: set[tuple[Any, ...]] = set()

    for row in existing_rows:
        if row.object_id is not None:
            key = (
                row.subject_type,
                str(row.subject_id) if row.subject_id else "",
                row.predicate,
                TripleObjectType.function,
                str(row.object_id),
            )
            cand = desired_by_key.get(key)
        else:
            cand = _match_null_object(row, desired_by_subject)
        if cand is None:
            continue
        cand_key = (
            cand.subject_type,
            str(cand.subject_id) if cand.subject_id else "",
            cand.predicate,
            str(cand.object_id),
        )
        if cand_key in covered_spos:
            # duplicate legacy triple for an already-covered SPO → stale
            continue
        matched_existing_ids.add(row.id)
        covered_spos.add(cand_key)
        # ensure the desired SPO is never inserted twice
        existing_keys.add(cand_key)
        if stats.dry_run:
            if row.object_id != cand.object_id or row.object_label != cand.object_label:
                stats.upgraded_count += 1
            continue
        changed = (
            row.object_id != cand.object_id
            or row.object_label != cand.object_label
            or row.projection_version != projection_version
            or (row.raw_payload_json or {}).get("source") != projection_version
            or tuple(sorted((row.raw_payload_json or {}).get("provenance", {}).get("source_relation_ids", [])))
            != tuple(sorted((cand_source_relation_ids(cand))))
        )
        if not changed:
            continue  # already entity-ized & tagged — idempotent no-op
        row.object_id = cand.object_id
        row.object_label = cand.object_label
        row.projection_version = projection_version
        row.raw_payload_json = _payload_for(cand, projection_version)
        row.normalized_payload_json = {
            "predicate": cand.predicate,
            "projection_version": projection_version,
            "canonical_term_id": str(cand.object_id),
            "generation_source": "function_relation",
        }
        # legacy single-source FKs: point at the *subject* entity (the FK
        # columns reference connection/circuit/region rows), except region
        # functions which have their own source_mirror_function_id column.
        first_rel = cand.source_relation_ids[0] if cand.source_relation_ids else None
        if cand.source_type == "region_function":
            row.source_mirror_function_id = first_rel
        elif cand.source_type == "projection_function":
            row.source_mirror_connection_id = cand.subject_id
        elif cand.source_type == "circuit_function":
            row.source_mirror_circuit_id = cand.subject_id
        stats.upgraded_count += 1

    # desired without an existing row → insert
    for cand in desired:
        key = (
            cand.subject_type,
            str(cand.subject_id) if cand.subject_id else "",
            cand.predicate,
            str(cand.object_id),
        )
        if key in existing_keys:
            continue  # already present (upgraded or matched)
        if stats.dry_run:
            stats.inserted_count += 1
            continue
        payload = mirror_kg_service.MirrorKgTripleCreate(
            subject_type=cand.subject_type,
            subject_id=cand.subject_id,
            subject_label=cand.subject_label[:512],
            predicate=cand.predicate,
            object_type=TripleObjectType.function,
            object_id=cand.object_id,
            object_label=cand.object_label[:512],
            triple_scope=TripleScope.same_granularity,
            resource_id=cand.resource_id,
            batch_id=cand.batch_id,
            llm_run_id=cand.llm_run_id,
            llm_item_id=cand.llm_item_id,
            source_mirror_function_id=(
                cand.source_relation_ids[0] if cand.source_type == "region_function" and cand.source_relation_ids else None
            ),
            source_mirror_connection_id=(
                cand.subject_id if cand.source_type == "projection_function" else None
            ),
            source_mirror_circuit_id=(
                cand.subject_id if cand.source_type == "circuit_function" else None
            ),
            granularity_level="",
            granularity_family=None,
            source_atlas="",
            source_version=None,
            confidence=cand.confidence,
            evidence_text=cand.evidence_text,
            uncertainty_reason=cand.uncertainty_reason,
            mirror_status=cand.mirror_status,
            review_status=cand.review_status,
            raw_payload_json=_payload_for(cand, projection_version),
            normalized_payload_json={
                "predicate": cand.predicate,
                "projection_version": projection_version,
                "canonical_term_id": str(cand.object_id),
                "generation_source": "function_relation",
            },
            created_by=created_by,
        )
        # MirrorKgTripleCreate may not carry projection_version; set post-create
        row = await mirror_kg_service.create_mirror_triple(session, payload)
        row.projection_version = projection_version
        stats.inserted_count += 1

    # stale existing rows: matched by nothing
    stale_rows = [r for r in existing_rows if r.id not in matched_existing_ids]
    for row in stale_rows:
        referenced = await _triple_is_referenced(session, row.id)
        if stats.dry_run:
            if referenced:
                stats.stale_superseded_count += 1
            else:
                stats.stale_deleted_count += 1
            continue
        if referenced:
            row.mirror_status = MirrorStatus.superseded
            raw = dict(row.raw_payload_json or {})
            raw.setdefault("provenance", {})["stale_reason"] = "no matching function relation in rebuild"
            row.raw_payload_json = raw
            stats.stale_superseded_count += 1
        else:
            await session.delete(row)
            stats.stale_deleted_count += 1

    await session.flush()
    return stats

