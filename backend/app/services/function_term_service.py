"""Unified Function term resolution, auto-propose and batch anchoring (P1.3).

Canonical Function identity lives in ``ontology_terms``
(``term_type='function'``, ``term_code`` ``ng:func:*``) — see P1.2 design.
This module is the single entry point for every Function grounding concern:

* ``resolve_canonical_function_term`` — merged / deprecated / wrong-type guard
* ``resolve_or_propose_function_term`` — text → term (match ladder + auto-propose)
* ``anchor_function_relation`` — write-time anchoring for mirror function rows
* ``backfill_function_grounding`` — idempotent batch backfill (mirror tables)
* ``reanchor_function_targets`` — post field-completion re-anchoring

Rules enforced here (P1.2 constraints):
* no fuzzy / semantic auto-merge — only exact normalized matches + registered synonyms;
* merged terms are resolved to their canonical replacement (dup-safe redirect);
* non-function ontology terms are never used as Function anchors;
* unresolved text keeps the relation row but never fabricates an anchor.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.mirror_kg import MirrorRegionFunction
from app.models.mirror_macro_clinical import MirrorCircuitFunction, MirrorProjectionFunction
from app.models.ontology import OntologyChangeLog, OntologyTerm, OntologyTermSynonym
from app.schemas.mirror_kg import MirrorStatus
from app.services.ontology_service import (
    TERM_TABLE_BY_TYPE,
    _upsert_grounding,
    normalize_term_key,
)

TERM_TYPE_FUNCTION = "function"
TERM_CODE_PREFIX = "ng:func:"

# Derived grounding states (P1.2 §7).
STATE_GROUNDED_ACTIVE = "grounded_active"
STATE_GROUNDED_PROPOSED = "grounded_proposed"
STATE_UNRESOLVED = "unresolved"
STATE_AMBIGUOUS = "ambiguous"
STATE_MERGED_REDIRECT = "merged_redirect"
STATE_INVALID_TYPE = "invalid_type"

VALID_ANCHOR_STATES = frozenset({STATE_GROUNDED_ACTIVE, STATE_GROUNDED_PROPOSED})

# Only these term states may be projected as an entity-ized Function Triple
# object (P1.5): deprecated / invalid / merged-residue / unresolved → never.
VALID_TRIPLE_TERM_STATES = frozenset({STATE_GROUNDED_ACTIVE, STATE_GROUNDED_PROPOSED})

DEFAULT_BATCH_SIZE = 1000

FUNCTION_MODELS = (MirrorRegionFunction, MirrorProjectionFunction, MirrorCircuitFunction)

# Relation identity qualifiers kept in dedup/dup-safety logic (P1.2 constraint A):
# identity = subject + term_id + qualifiers. Text alone is never identity.
_QUALIFIERS_BY_TYPE: dict[str, tuple[str, ...]] = {
    "region_function": ("region_candidate_id", "function_category", "relation_type"),
    "projection_function": ("projection_id", "function_category", "relation_type"),
    "circuit_function": ("circuit_id", "function_domain", "function_role", "effect_type"),
}


@dataclass
class FunctionTermResolution:
    """Result of a function-term lookup / resolution.

    ``term_id`` is always the canonical (post-resolution) term id, or None.
    ``state`` is one of the STATE_* constants; ``path`` records the resolution
    ladder steps for audit (e.g. ["active_canonical_exact"], ["auto_propose"]).
    """

    term_id: uuid.UUID | None = None
    term_code: str | None = None
    canonical_name: str | None = None
    status: str | None = None
    is_function_term: bool = False
    state: str = STATE_UNRESOLVED
    path: list[str] = field(default_factory=list)


def zh_term_key(text: str) -> str:
    """Normalize keeping CJK characters (for Chinese function source texts)."""
    return " ".join(re.findall(r"[a-z0-9一-鿿]+", (text or "").lower()))


@dataclass
class TermIndex:
    """Prebuilt matching indexes over ontology_terms (+ synonyms), keyed by
    ``normalize_term_key``. Built once per batch / call via ``_load_term_index``."""

    active_canon: dict[str, uuid.UUID] = field(default_factory=dict)
    active_synonym: dict[str, uuid.UUID] = field(default_factory=dict)
    proposed_canon: dict[str, uuid.UUID] = field(default_factory=dict)
    merged_canon: dict[str, uuid.UUID] = field(default_factory=dict)
    zh_canon: dict[str, uuid.UUID] = field(default_factory=dict)
    ambiguous_keys: set[str] = field(default_factory=set)


def is_function_term_row(term: OntologyTerm | None) -> bool:
    """Function vocabulary guard: term_type == 'function' and ng:func: code."""
    return (
        term is not None
        and (term.term_type or "") == TERM_TYPE_FUNCTION
        and (term.term_code or "").startswith(TERM_CODE_PREFIX)
    )


async def _load_term_index(session: AsyncSession) -> TermIndex:
    """Index active/proposed/merged function terms and active synonyms."""
    index = TermIndex()
    terms = (
        await session.execute(
            select(OntologyTerm).where(OntologyTerm.term_type == TERM_TYPE_FUNCTION)
        )
    ).scalars().all()
    for term in terms:
        if not (term.term_code or "").startswith(TERM_CODE_PREFIX):
            continue
        key = normalize_term_key(term.canonical_term_en)
        if not key:
            continue
        if term.status == "active":
            index.active_canon.setdefault(key, term.id)
        elif term.status == "proposed":
            index.proposed_canon.setdefault(key, term.id)
        elif term.status == "merged":
            index.merged_canon.setdefault(key, term.id)
        if term.canonical_term_cn:
            zkey = zh_term_key(term.canonical_term_cn)
            if zkey:
                index.zh_canon.setdefault(zkey, term.id)
    synonyms = (
        await session.execute(
            select(OntologyTermSynonym)
            .where(OntologyTermSynonym.status == "active")
            .join(OntologyTerm, OntologyTerm.id == OntologyTermSynonym.term_id)
            .where(OntologyTerm.term_type == TERM_TYPE_FUNCTION)
        )
    ).scalars().all()
    for synonym in synonyms:
        key = normalize_term_key(synonym.synonym_text)
        if not key:
            continue
        existing = index.active_synonym.get(key)
        if existing is not None and existing != synonym.term_id:
            index.ambiguous_keys.add(key)
        else:
            index.active_synonym.setdefault(key, synonym.term_id)
    return index


def _state_for(term: OntologyTerm | None) -> str:
    if term is None:
        return STATE_UNRESOLVED
    if term.status == "merged":
        return STATE_MERGED_REDIRECT
    if term.status == "active":
        return STATE_GROUNDED_ACTIVE
    if term.status == "proposed":
        return STATE_GROUNDED_PROPOSED
    # deprecated / other → not an anchor
    return STATE_INVALID_TYPE


def _resolution_for(
    term: OntologyTerm | None,
    *,
    path: list[str],
    is_function: bool,
) -> FunctionTermResolution:
    if term is None:
        return FunctionTermResolution(state=STATE_UNRESOLVED, path=path)
    if not is_function:
        # non-Function ontology terms are never valid Function anchors
        return FunctionTermResolution(
            term_id=term.id,
            term_code=term.term_code,
            canonical_name=term.canonical_term_en,
            status=term.status,
            is_function_term=False,
            state=STATE_INVALID_TYPE,
            path=path,
        )
    return FunctionTermResolution(
        term_id=term.id,
        term_code=term.term_code,
        canonical_name=term.canonical_term_en,
        status=term.status,
        is_function_term=True,
        state=_state_for(term),
        path=path,
    )


async def load_canonical_term_map(
    session: AsyncSession,
    term_ids: set[uuid.UUID],
) -> dict[uuid.UUID, FunctionTermResolution]:
    """Batch term_id → canonical resolution (shared by consolidate & rebuild)."""
    out: dict[uuid.UUID, FunctionTermResolution] = {}
    for tid in term_ids:
        if tid is None:
            continue
        out[tid] = await resolve_canonical_function_term(session, tid)
    return out


async def resolve_canonical_function_term(
    session: AsyncSession,
    term_id: uuid.UUID,
) -> FunctionTermResolution:
    """Resolve a term id to its canonical Function term.

    Follows ``replaced_by_term_id`` chains (merged → canonical), refuses
    non-Function terms, and reports deprecated terms as deprecated (never
    silently treated as active).
    """
    term = await session.get(OntologyTerm, term_id)
    if term is None:
        return FunctionTermResolution(state=STATE_UNRESOLVED, path=["not_found"])
    if not is_function_term_row(term):
        return _resolution_for(term, path=["invalid_type"], is_function=False)
    if term.status == "deprecated":
        return _resolution_for(term, path=["deprecated"], is_function=True)

    cursor = term
    hops = 0
    path: list[str] = []
    while cursor.replaced_by_term_id is not None and hops < 10:
        nxt = await session.get(OntologyTerm, cursor.replaced_by_term_id)
        if nxt is None:
            break
        cursor = nxt
        path.append("merged_redirect")
        hops += 1
    if cursor.id != term.id and cursor.status in ("merged", "deprecated"):
        # chain did not land on a usable term
        return _resolution_for(cursor, path=path or ["merged_redirect"], is_function=True)
    return _resolution_for(cursor, path=path or ["direct"], is_function=True)


async def _auto_propose_term(
    session: AsyncSession,
    text: str,
    *,
    created_by: str,
    source: str,
) -> FunctionTermResolution:
    """Create a proposed Function OntologyTerm (no semantic merge).

    Idempotent: reuses any existing term with the same derived term_code;
    a merged/deprecated collision is resolved to its canonical replacement.
    """
    key = normalize_term_key(text) or zh_term_key(text)
    slug = key.replace(" ", "_") or "unnamed"
    term_code = f"{TERM_CODE_PREFIX}{slug}"
    existing = (
        await session.execute(
            select(OntologyTerm).where(OntologyTerm.term_code == term_code)
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.status in ("merged", "deprecated"):
            res = await resolve_canonical_function_term(session, existing.id)
            res.path = ["term_code_reuse", *res.path]
            return res
        return _resolution_for(
            existing, path=["term_code_reuse"], is_function=True
        )

    operator = (created_by or "system")[:64]
    term = OntologyTerm(
        term_code=term_code,
        canonical_term_en=text[:512],
        term_type=TERM_TYPE_FUNCTION,
        status="proposed",
        created_by=operator,
        description=f"auto-proposed by {source}; original text: {text[:200]}",
    )
    session.add(term)
    await session.flush()
    session.add(
        OntologyChangeLog(
            action_type="term.auto_propose",
            entity_type="ontology_term",
            entity_id=term.id,
            before_data={},
            after_data={
                "term_code": term_code,
                "canonical_term_en": text[:512],
                "source": source,
            },
            operator_id=operator,
            reason=f"auto-propose from {source}",
        )
    )
    await session.flush()
    return FunctionTermResolution(
        term_id=term.id,
        term_code=term.term_code,
        canonical_name=term.canonical_term_en,
        status=term.status,
        is_function_term=True,
        state=STATE_GROUNDED_PROPOSED,
        path=["auto_propose"],
    )


async def resolve_or_propose_function_term(
    session: AsyncSession,
    function_text: str | None,
    *,
    created_by: str = "system:auto_grounding",
    source: str = "grounding",
    index: TermIndex | None = None,
) -> FunctionTermResolution:
    """Text → canonical Function term (match ladder + auto-propose).

    Ladder (P1.2 §6):
    1. normalize-exact active canonical
    2. active synonym exact
    3. proposed canonical exact
    4. merged canonical exact → canonical resolution
    5. unresolved → auto-propose a proposed Function term

    No fuzzy matching and no semantic merging, ever.
    """
    text = (function_text or "").strip()
    if not text:
        return FunctionTermResolution(state=STATE_UNRESOLVED, path=["empty_text"])
    key = normalize_term_key(text)
    idx = index or await _load_term_index(session)
    if not key:
        # Chinese (or CJK-only) source text: no latin tokens to normalize —
        # match against canonical_term_cn, auto-propose with a CJK slug.
        zkey = zh_term_key(text)
        if not zkey:
            return FunctionTermResolution(state=STATE_UNRESOLVED, path=["empty_key"])
        term_id = idx.zh_canon.get(zkey)
        if term_id is not None:
            term = await session.get(OntologyTerm, term_id)
            return _resolution_for(term, path=["zh_canonical_exact"], is_function=True)
        return await _auto_propose_term(session, text, created_by=created_by, source=source)

    if key in idx.ambiguous_keys:
        return FunctionTermResolution(state=STATE_AMBIGUOUS, path=["ambiguous_synonym"])

    term_id = idx.active_canon.get(key)
    if term_id is not None:
        term = await session.get(OntologyTerm, term_id)
        return _resolution_for(term, path=["active_canonical_exact"], is_function=True)

    term_id = idx.active_synonym.get(key)
    if term_id is not None:
        term = await session.get(OntologyTerm, term_id)
        return _resolution_for(term, path=["active_synonym_exact"], is_function=True)

    term_id = idx.proposed_canon.get(key)
    if term_id is not None:
        term = await session.get(OntologyTerm, term_id)
        return _resolution_for(term, path=["proposed_canonical_exact"], is_function=True)

    term_id = idx.merged_canon.get(key)
    if term_id is not None:
        res = await resolve_canonical_function_term(session, term_id)
        res.path = ["merged_canonical_exact", *res.path]
        return res

    return await _auto_propose_term(session, text, created_by=created_by, source=source)


def _term_text_for(row, target_type: str) -> str:
    """Mirror of ontology_service._term_text_for (single source of text)."""
    if target_type == "circuit_function":
        return str(row.function_term_en or row.function_term_cn or "")
    if target_type == "projection_function":
        return str(row.function_term or row.function_term_cn or "")
    if target_type == "region_function":
        return str(row.function_term or "")
    return ""


def _qualifier_match(model, row, new_term_id: uuid.UUID) -> Any:
    """WHERE clause for the same-subject + same-term dup check (P1.2 constraint B)."""
    conds = [model.term_id == new_term_id, model.id != row.id]
    for qualifier in _QUALIFIERS_BY_TYPE.get(_target_type_for(row), ()):
        conds.append(getattr(model, qualifier) == getattr(row, qualifier, None))
    return and_(*conds)


def _target_type_for(row) -> str:
    if isinstance(row, MirrorRegionFunction):
        return "region_function"
    if isinstance(row, MirrorProjectionFunction):
        return "projection_function"
    if isinstance(row, MirrorCircuitFunction):
        return "circuit_function"
    raise ValueError(f"unsupported function row: {type(row).__name__}")


async def _redirect_relation_with_dup_safety(
    session: AsyncSession,
    row,
    new_term_id: uuid.UUID,
    old_term_id: uuid.UUID,
) -> bool:
    """Point a relation at its canonical term, merging duplicates if needed.

    Returns True when the row was superseded because an identical
    (subject + term_id + qualifiers) relation already exists; False when the
    redirect was applied directly. Never silently drops data: the losing row
    keeps evidence/provenance and is marked superseded with a duplicate audit.
    """
    model = TERM_TABLE_BY_TYPE[_target_type_for(row)]
    other = (
        await session.execute(
            select(model).where(_qualifier_match(model, row, new_term_id)).limit(1)
        )
    ).scalar_one_or_none()
    if other is None:
        row.term_id = new_term_id
        raw = dict(row.raw_payload_json or {})
        provenance = raw.setdefault("provenance", {})
        provenance["term_redirect"] = {
            "from": str(old_term_id),
            "to": str(new_term_id),
            "at": datetime.now(timezone.utc).isoformat(),
        }
        row.raw_payload_json = raw
        flag_modified(row, "raw_payload_json")
        return False

    # Same-subject + same-term relation exists → merge provenance into it.
    if float(other.confidence or 0.0) < float(row.confidence or 0.0):
        other.confidence = row.confidence
    if row.evidence_text and not other.evidence_text:
        other.evidence_text = row.evidence_text
    raw_other = dict(other.raw_payload_json or {})
    prov_other = raw_other.setdefault("provenance", {})
    prov_other.setdefault("merged_duplicates", []).append(
        {"duplicate_id": str(row.id), "old_term_id": str(old_term_id), "reason": "term_merged_redirect"}
    )
    other.raw_payload_json = raw_other
    flag_modified(other, "raw_payload_json")

    raw = dict(row.raw_payload_json or {})
    provenance = raw.setdefault("provenance", {})
    provenance["duplicate_of"] = str(other.id)
    provenance["duplicate_reason"] = f"term merged redirect: {old_term_id} → {new_term_id}"
    row.raw_payload_json = raw
    flag_modified(row, "raw_payload_json")
    row.mirror_status = MirrorStatus.superseded
    return True


async def anchor_function_relation(
    session: AsyncSession,
    *,
    target_type: str,
    row,
    created_by: str = "extraction",
    index: TermIndex | None = None,
) -> FunctionTermResolution:
    """Unified write-time anchor for a Function relation row.

    * already-anchored (active/proposed) → kept, merged anchors redirected;
    * merged / deprecated / wrong-type anchors → re-resolved from text;
    * unresolved text → ``term_id=None`` + ungrounded record (no fabrication).
    """
    if target_type not in TERM_TABLE_BY_TYPE:
        raise ValueError(f"unsupported target_type: {target_type}")

    if row.term_id is not None:
        res = await resolve_canonical_function_term(session, row.term_id)
        if res.is_function_term and res.state in VALID_ANCHOR_STATES:
            if res.term_id != row.term_id:
                await _redirect_relation_with_dup_safety(
                    session, row, res.term_id, row.term_id
                )
            await _upsert_grounding(
                session,
                target_type=target_type,
                target_id=row.id,
                term_id=res.term_id,
                grounded_by="deterministic",
                confidence=1.0,
                created_by=created_by,
            )
            await session.flush()
            return res

    res = await resolve_or_propose_function_term(
        session,
        _term_text_for(row, target_type),
        created_by=created_by,
        source=f"anchor:{target_type}",
        index=index,
    )
    if res.is_function_term and res.state in VALID_ANCHOR_STATES:
        row.term_id = res.term_id
        grounded_by = "deterministic"
        confidence = 1.0
    else:
        row.term_id = None
        grounded_by = "ungrounded"
        confidence = None
    await _upsert_grounding(
        session,
        target_type=target_type,
        target_id=row.id,
        term_id=row.term_id,
        grounded_by=grounded_by,
        confidence=confidence,
        created_by=created_by,
    )
    await session.flush()
    return res


async def reanchor_function_targets(
    session: AsyncSession,
    targets: dict[uuid.UUID, Any],
    *,
    created_by: str = "field_completion",
) -> dict[str, int]:
    """Re-anchor all function-typed targets of a field-completion run.

    Field completion writes function text directly (apply_field_update), which
    may leave term_id stale — this closes that gap after the run.
    """
    rows = [t for t in targets.values() if isinstance(t, FUNCTION_MODELS)]
    if not rows:
        return {}
    index = await _load_term_index(session)
    counts: dict[str, int] = {}
    affected: set[tuple[str, uuid.UUID]] = set()
    for row in rows:
        res = await anchor_function_relation(
            session,
            target_type=_target_type_for(row),
            row=row,
            created_by=created_by,
            index=index,
        )
        counts[res.state] = counts.get(res.state, 0) + 1
        if isinstance(row, MirrorRegionFunction) and row.region_candidate_id:
            affected.add(("region_candidate", row.region_candidate_id))
        elif isinstance(row, MirrorProjectionFunction) and row.projection_id:
            affected.add(("connection", row.projection_id))
        elif isinstance(row, MirrorCircuitFunction) and row.circuit_id:
            affected.add(("circuit", row.circuit_id))
    # P1.6: field completion may have changed text/term — reconcile affected
    if affected:
        from app.services.function_triple_projection_service import (
            reconcile_function_subject,
        )

        reconciled: set[tuple[Any, ...]] = set()
        for stype, sid in affected:
            await reconcile_function_subject(
                session,
                subject_type=stype,
                subject_id=sid,
                created_by=created_by,
                _reconciled=reconciled,
            )
    await session.flush()
    return counts


def _term_is_invalid(model) -> Any:
    """Correlated predicate: relation.term_id points to a merged/deprecated
    term, a non-Function term, or a term with a non-ng:func: code."""
    return exists(
        select(OntologyTerm.id).where(
            OntologyTerm.id == model.term_id,
            or_(
                OntologyTerm.status.in_(("merged", "deprecated")),
                OntologyTerm.term_type != TERM_TYPE_FUNCTION,
                ~OntologyTerm.term_code.like(f"{TERM_CODE_PREFIX}%"),
            ),
        )
    )


async def backfill_function_grounding(
    session: AsyncSession,
    *,
    target_type: str,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_batches: int | None = None,
    created_by: str = "backfill:p1.3",
) -> dict[str, int]:
    """Idempotent batch backfill of relation.term_id for one mirror table.

    Processes rows whose term_id is NULL or points to a merged/deprecated /
    wrong-type term. Never touches function text. Safe to re-run.
    """
    if target_type not in TERM_TABLE_BY_TYPE:
        raise ValueError(f"unsupported target_type: {target_type}")
    model = TERM_TABLE_BY_TYPE[target_type]
    index = await _load_term_index(session)

    stats: dict[str, int] = {
        "total_scanned": 0,
        "rows_updated": 0,
        "proposed_created": 0,
        "dup_superseded": 0,
        STATE_GROUNDED_ACTIVE: 0,
        STATE_GROUNDED_PROPOSED: 0,
        STATE_UNRESOLVED: 0,
        STATE_AMBIGUOUS: 0,
        STATE_MERGED_REDIRECT: 0,
        STATE_INVALID_TYPE: 0,
    }
    batches = 0
    while True:
        if max_batches is not None and batches >= max_batches:
            break
        rows = (
            await session.execute(
                select(model)
                .where(
                    or_(
                        model.term_id.is_(None),
                        _term_is_invalid(model),
                    )
                )
                .order_by(model.id)
                .limit(batch_size)
            )
        ).scalars().all()
        if not rows:
            break
        batches += 1
        for row in rows:
            had_term = row.term_id is not None
            res = await anchor_function_relation(
                session,
                target_type=target_type,
                row=row,
                created_by=created_by,
                index=index,
            )
            stats["total_scanned"] += 1
            if res.path and res.path[-1] == "auto_propose":
                stats["proposed_created"] += 1
            if had_term and row.term_id is None:
                stats["rows_updated"] += 1
            elif not had_term and row.term_id is not None:
                stats["rows_updated"] += 1
            stats[res.state] = stats.get(res.state, 0) + 1
        await session.flush()
        await session.commit()
    return stats


async def count_function_grounding_states(
    session: AsyncSession,
    *,
    target_type: str,
) -> dict[str, int]:
    """Current state distribution for one mirror function table (reporting)."""
    if target_type not in TERM_TABLE_BY_TYPE:
        raise ValueError(f"unsupported target_type: {target_type}")
    model = TERM_TABLE_BY_TYPE[target_type]
    rows = (
        await session.execute(
            select(model, OntologyTerm)
            .outerjoin(OntologyTerm, OntologyTerm.id == model.term_id)
        )
    ).all()
    stats: dict[str, int] = {
        "total": len(rows),
        STATE_GROUNDED_ACTIVE: 0,
        STATE_GROUNDED_PROPOSED: 0,
        STATE_UNRESOLVED: 0,
        STATE_AMBIGUOUS: 0,
        STATE_MERGED_REDIRECT: 0,
        STATE_INVALID_TYPE: 0,
        "merged_redirect_dup_superseded": 0,
    }
    for row, term in rows:
        if term is None:
            stats[STATE_UNRESOLVED] += 1
            continue
        if not is_function_term_row(term):
            stats[STATE_INVALID_TYPE] += 1
            continue
        stats[_state_for(term)] = stats.get(_state_for(term), 0) + 1
        prov = (row.raw_payload_json or {}).get("provenance") or {}
        if prov.get("duplicate_of"):
            stats["merged_redirect_dup_superseded"] += 1
    return stats
