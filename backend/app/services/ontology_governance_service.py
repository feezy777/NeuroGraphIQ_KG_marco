"""Ontology governance workbench service (dashboard, issues, review, batch ops)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import CandidateBrainRegion
from app.models.mirror_kg import (
    MirrorCircuitRegion,
    MirrorKgTriple,
    MirrorRegionCircuit,
    MirrorRegionConnection,
    MirrorRegionFunction,
)
from app.models.mirror_macro_clinical import (
    MirrorCircuitProjectionMembership,
    MirrorCircuitStep,
    MirrorProjectionFunction,
)
from app.models.ontology import (
    OntologyAlignmentCandidate,
    OntologyAuditRun,
    OntologyChangeLog,
    OntologyTerm,
    OntologyTermExternalMapping,
    OntologyTermGrounding,
    OntologyTermSynonym,
    OntologyVocabulary,
)
from app.services.ontology_service import (
    TERM_TABLE_BY_TYPE,
    normalize_term_key,
    _upsert_grounding,
    activate_term,
    _term_code,
)

FUNCTION_TARGETS = ("circuit_function", "projection_function", "region_function")

ENUM_FIELD_MAP: dict[str, tuple[type, str]] = {
    "category": (MirrorRegionFunction, "function_category"),
    "relation_type": (MirrorRegionFunction, "relation_type"),
    "projection_category": (MirrorProjectionFunction, "function_category"),
    "projection_relation": (MirrorProjectionFunction, "relation_type"),
    "connection_type": (MirrorRegionConnection, "connection_type"),
    "directionality": (MirrorRegionConnection, "directionality"),
    "circuit_type": (MirrorRegionCircuit, "circuit_type"),
    "circuit_region_role": (MirrorCircuitRegion, "role"),
    "step_type": (MirrorCircuitStep, "step_type"),
    "step_role": (MirrorCircuitStep, "role"),
    "projection_role": (MirrorCircuitProjectionMembership, "role_in_circuit"),
    "triple_subject_type": (MirrorKgTriple, "subject_type"),
    "triple_object_type": (MirrorKgTriple, "object_type"),
    "triple_scope": (MirrorKgTriple, "triple_scope"),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _active_vocab(session: AsyncSession) -> dict[str, set[str]]:
    rows = (
        await session.execute(
            select(OntologyVocabulary.code, OntologyVocabulary.vocab_type).where(
                OntologyVocabulary.status == "active"
            )
        )
    ).all()
    out: dict[str, set[str]] = {}
    for code, vocab_type in rows:
        out.setdefault(vocab_type, set()).add(code)
    return out


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


async def _recommend_terms(
    session: AsyncSession, term_text: str, top: int = 3
) -> list[dict]:
    active = (
        await session.execute(
            select(OntologyTerm).where(OntologyTerm.status == "active")
        )
    ).scalars().all()
    q = _tokens(term_text)
    scored = []
    for term in active:
        d = _tokens(term.canonical_term_en)
        if not q or not d:
            continue
        score = len(q & d) / max(len(q), len(d))
        if score >= 0.4:
            scored.append((score, term))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "term_id": str(term.id),
            "canonical_term_en": term.canonical_term_en,
            "term_code": term.term_code,
            "confidence": round(score, 2),
        }
        for score, term in scored[:top]
    ]


async def dashboard(session: AsyncSession, granularity_level: str | None = None) -> dict:
    vocab = await _active_vocab(session)
    total = grounded = 0
    for key, model in TERM_TABLE_BY_TYPE.items():
        total_q = select(func.count()).select_from(model)
        grounded_q = select(func.count()).select_from(model).where(model.term_id.is_not(None))
        if granularity_level:
            total_q = total_q.where(model.granularity_level == granularity_level)
            grounded_q = grounded_q.where(model.granularity_level == granularity_level)
        total += (await session.execute(total_q)).scalar_one()
        grounded += (await session.execute(grounded_q)).scalar_one()
    proposed = (
        await session.execute(
            select(func.count())
            .select_from(OntologyTerm)
            .where(OntologyTerm.status == "proposed")
        )
    ).scalar_one()
    region_q = select(CandidateBrainRegion)
    if granularity_level:
        region_q = region_q.where(CandidateBrainRegion.granularity_level == granularity_level)
    regions = (await session.execute(region_q)).scalars().all()
    region_unaligned = sum(
        1 for r in regions if not (r.uberon_iri or "").strip() and not (r.nifstd_iri or "").strip()
    )
    anomaly_counts = await enum_anomalies_summary(session, granularity_level)
    anomaly_total = sum(v for v in anomaly_counts.values())
    last_audit = (
        await session.execute(
            select(OntologyAuditRun).where(OntologyAuditRun.status == "completed")
            .order_by(OntologyAuditRun.finished_at.desc()).limit(1)
        )
    ).scalar_one_or_none()
    return {
        "function_anchor_rate": round(grounded / total, 4) if total else 0.0,
        "function_total": total,
        "function_grounded": grounded,
        "proposed_terms": proposed,
        "ungrounded_records": total - grounded,
        "region_unaligned": region_unaligned,
        "enum_anomalies": anomaly_total,
        "last_audit_at": last_audit.finished_at.isoformat() if last_audit else None,
    }


async def enum_anomalies_summary(
    session: AsyncSession, granularity_level: str | None = None
) -> dict[str, int]:
    vocab = await _active_vocab(session)
    out: dict[str, int] = {}
    for field, (model, column) in ENUM_FIELD_MAP.items():
        vocab_type = field.split("_")[0] if field.startswith("projection_") or field.startswith("circuit_") or field == "directionality" or field == "connection_type" else field
        # map field -> vocab_type
        vt = _FIELD_VOCAB_TYPE.get(field)
        allowed = vocab.get(vt, set())
        if not allowed:
            continue
        q = (
            select(func.count())
            .select_from(model)
            .where(getattr(model, column).notin_(list(allowed)))
        )
        if granularity_level and hasattr(model, "granularity_level"):
            q = q.where(model.granularity_level == granularity_level)
        out[field] = (await session.execute(q)).scalar_one()
    return out


_FIELD_VOCAB_TYPE = {
    "category": "category",
    "relation_type": "relation_type",
    "projection_category": "category",
    "projection_relation": "relation_type",
    "connection_type": "connection_type",
    "directionality": "directionality",
    "circuit_type": "circuit_type",
    "circuit_region_role": "circuit_region_role",
    "step_type": "step_type",
    "step_role": "step_role",
    "projection_role": "projection_role",
    "triple_subject_type": "triple_subject_type",
    "triple_object_type": "triple_object_type",
    "triple_scope": "triple_scope",
}


async def issues_summary(
    session: AsyncSession, granularity_level: str | None = None
) -> dict:
    d = await dashboard(session, granularity_level)
    return {
        "term_ungrounded": d["ungrounded_records"],
        "term_not_active": 0,
        "term_deprecated": 0,
        "region_unaligned": d["region_unaligned"],
        "enum_invalid": d["enum_anomalies"],
        "predicate_unknown": 0,
        "total": d["ungrounded_records"] + d["region_unaligned"] + d["enum_anomalies"],
    }


async def entity_summary(session: AsyncSession, entity: str) -> dict:
    """Ontology-relevant summary for connection / circuit entities."""
    vocab = await _active_vocab(session)
    if entity == "connection":
        total = (
            await session.execute(select(func.count()).select_from(MirrorRegionConnection))
        ).scalar_one()
        by_type_rows = (
            await session.execute(
                select(MirrorRegionConnection.connection_type, func.count())
                .group_by(MirrorRegionConnection.connection_type)
                .order_by(func.count().desc())
            )
        ).all()
        by_dir_rows = (
            await session.execute(
                select(MirrorRegionConnection.directionality, func.count())
                .group_by(MirrorRegionConnection.directionality)
                .order_by(func.count().desc())
            )
        ).all()
        allowed_type = vocab.get("connection_type", set())
        allowed_dir = vocab.get("directionality", set())
        anomalies = 0
        if allowed_type:
            anomalies += (
                await session.execute(
                    select(func.count())
                    .select_from(MirrorRegionConnection)
                    .where(MirrorRegionConnection.connection_type.notin_(list(allowed_type)))
                )
            ).scalar_one()
        if allowed_dir:
            anomalies += (
                await session.execute(
                    select(func.count())
                    .select_from(MirrorRegionConnection)
                    .where(MirrorRegionConnection.directionality.notin_(list(allowed_dir)))
                )
            ).scalar_one()
        return {
            "entity": "connection",
            "total": total,
            "anomalies": anomalies,
            "by_type": [{"value": r[0], "count": r[1]} for r in by_type_rows],
            "by_direction": [{"value": r[0], "count": r[1]} for r in by_dir_rows],
        }
    if entity == "circuit":
        total = (
            await session.execute(select(func.count()).select_from(MirrorRegionCircuit))
        ).scalar_one()
        by_type_rows = (
            await session.execute(
                select(MirrorRegionCircuit.circuit_type, func.count())
                .group_by(MirrorRegionCircuit.circuit_type)
                .order_by(func.count().desc())
            )
        ).all()
        step_type_rows = (
            await session.execute(
                select(MirrorCircuitStep.step_type, func.count())
                .group_by(MirrorCircuitStep.step_type)
                .order_by(func.count().desc())
            )
        ).all()
        step_role_rows = (
            await session.execute(
                select(MirrorCircuitStep.role, func.count())
                .group_by(MirrorCircuitStep.role)
                .order_by(func.count().desc())
            )
        ).all()
        anomalies = 0
        for field in ("circuit_type", "step_type", "step_role", "circuit_region_role", "projection_role"):
            pair = ENUM_FIELD_MAP.get(field)
            allowed = vocab.get(_FIELD_VOCAB_TYPE.get(field, ""), set())
            if pair is None or not allowed:
                continue
            model, column = pair
            anomalies += (
                await session.execute(
                    select(func.count())
                    .select_from(model)
                    .where(getattr(model, column).notin_(list(allowed)))
                )
            ).scalar_one()
        return {
            "entity": "circuit",
            "total": total,
            "anomalies": anomalies,
            "by_type": [{"value": r[0], "count": r[1]} for r in by_type_rows],
            "by_step_type": [{"value": r[0], "count": r[1]} for r in step_type_rows],
            "by_step_role": [{"value": r[0], "count": r[1]} for r in step_role_rows],
        }
    raise ValueError(f"unsupported entity: {entity}")


async def ungrounded_records(
    session: AsyncSession,
    *,
    granularity_level: str | None = None,
    target_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    types = [target_type] if target_type else list(FUNCTION_TARGETS)
    items = []
    total = 0
    remaining_limit = limit
    for key in types:
        model = TERM_TABLE_BY_TYPE.get(key)
        if model is None:
            continue
        base = (
            select(model)
            .join(
                OntologyTermGrounding,
                and_(
                    OntologyTermGrounding.target_type == key,
                    OntologyTermGrounding.target_id == model.id,
                ),
            )
            .where(
                OntologyTermGrounding.grounded_by == "ungrounded",
                OntologyTermGrounding.created_by.not_like("skipped:%"),
            )
        )
        if granularity_level:
            base = base.where(model.granularity_level == granularity_level)
        total += (
            await session.execute(
                select(func.count()).select_from(base.subquery())
            )
        ).scalar_one()
        if remaining_limit > 0:
            rows = (
                await session.execute(base.offset(offset).limit(remaining_limit))
            ).scalars().all()
            offset = max(0, offset - (offset if False else 0))
            for row in rows:
                term_text = _term_text(row, key)
                items.append(
                    {
                        "target_type": key,
                        "target_id": str(row.id),
                        "function_term": term_text,
                        "granularity_level": row.granularity_level,
                        "reason": "no matching active ontology term",
                        "recommendations": await _recommend_terms(session, term_text),
                    }
                )
            remaining_limit -= len(rows)
    return {"items": items, "total": total}


async def mark_skip(
    session: AsyncSession,
    *,
    target_type: str,
    target_id: uuid.UUID,
    reason: str,
    operator_id: str | None = None,
) -> dict:
    model = TERM_TABLE_BY_TYPE.get(target_type)
    if model is None:
        raise ValueError(f"unsupported target_type: {target_type}")
    row = await session.get(model, target_id)
    if row is None:
        raise ValueError("target not found")
    await _upsert_grounding(
        session,
        target_type=target_type,
        target_id=target_id,
        term_id=None,
        grounded_by="ungrounded",
        confidence=None,
        created_by=f"skipped:{reason}"[:64],
    )
    session.add(
        OntologyChangeLog(
            action_type="grounding.skip",
            entity_type=f"ontology_term_grounding:{target_type}",
            entity_id=target_id,
            before_data={},
            after_data={"reason": reason},
            operator_id=operator_id,
            reason=reason,
        )
    )
    await session.flush()
    return {"target_type": target_type, "target_id": str(target_id), "skipped": True}


def _term_text(row, target_type: str) -> str:
    if target_type == "circuit_function":
        return str(row.function_term_en or row.function_term_cn or "")
    return str(row.function_term or row.function_term_cn or "")


async def term_detail(session: AsyncSession, term_id: uuid.UUID) -> dict:
    term = await session.get(OntologyTerm, term_id)
    if term is None:
        raise ValueError("term not found")
    synonyms = (
        await session.execute(
            select(OntologyTermSynonym).where(OntologyTermSynonym.term_id == term_id)
        )
    ).scalars().all()
    mappings = (
        await session.execute(
            select(OntologyTermExternalMapping).where(
                OntologyTermExternalMapping.term_id == term_id
            )
        )
    ).scalars().all()
    refs = await term_references(session, term_id, limit=20, offset=0)
    logs = (
        await session.execute(
            select(OntologyChangeLog)
            .where(OntologyChangeLog.entity_id == term_id)
            .order_by(OntologyChangeLog.created_at.desc())
            .limit(20)
        )
    ).scalars().all()
    return {
        "term": {
            "id": str(term.id),
            "term_code": term.term_code,
            "canonical_term_en": term.canonical_term_en,
            "canonical_term_cn": term.canonical_term_cn,
            "term_type": term.term_type,
            "status": term.status,
            "created_by": term.created_by,
            "created_at": term.created_at.isoformat(),
            "updated_at": term.updated_at.isoformat(),
            "replaced_by_term_id": str(term.replaced_by_term_id) if term.replaced_by_term_id else None,
        },
        "synonyms": [
            {
                "id": str(s.id),
                "synonym_text": s.synonym_text,
                "lang": s.lang,
                "match_type": s.match_type,
                "status": s.status,
            }
            for s in synonyms
        ],
        "external_mappings": [
            {
                "id": str(m.id),
                "external_system": m.external_system,
                "external_iri": m.external_iri,
                "external_label": m.external_label,
                "match_type": m.match_type,
            }
            for m in mappings
        ],
        "references": refs,
        "change_logs": [
            {
                "id": str(log.id),
                "action_type": log.action_type,
                "operator_id": log.operator_id,
                "reason": log.reason,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ],
    }


async def term_references(
    session: AsyncSession,
    term_id: uuid.UUID,
    *,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    items = []
    total = 0
    for key, model in TERM_TABLE_BY_TYPE.items():
        total += (
            await session.execute(
                select(func.count()).select_from(model).where(model.term_id == term_id)
            )
        ).scalar_one()
    for key, model in TERM_TABLE_BY_TYPE.items():
        rows = (
            await session.execute(
                select(model)
                .where(model.term_id == term_id)
                .offset(offset)
                .limit(limit)
            )
        ).scalars().all()
        for row in rows:
            items.append(
                {
                    "target_type": key,
                    "target_id": str(row.id),
                    "function_term": _term_text(row, key),
                    "granularity_level": row.granularity_level,
                }
            )
        limit -= len(rows)
        if limit <= 0:
            break
    return {"items": items, "total": total}


async def merge_preview(
    session: AsyncSession, source_id: uuid.UUID, target_id: uuid.UUID
) -> dict:
    if source_id == target_id:
        raise ValueError("cannot merge a term into itself")
    source = await session.get(OntologyTerm, source_id)
    target = await session.get(OntologyTerm, target_id)
    if source is None or target is None:
        raise ValueError("term not found")
    src_syns = (
        await session.execute(
            select(OntologyTermSynonym).where(OntologyTermSynonym.term_id == source_id)
        )
    ).scalars().all()
    tgt_syns = (
        await session.execute(
            select(OntologyTermSynonym).where(OntologyTermSynonym.term_id == target_id)
        )
    ).scalars().all()
    tgt_syn_keys = {(s.synonym_text, s.lang) for s in tgt_syns}
    src_maps = (
        await session.execute(
            select(OntologyTermExternalMapping).where(
                OntologyTermExternalMapping.term_id == source_id
            )
        )
    ).scalars().all()
    tgt_maps = (
        await session.execute(
            select(OntologyTermExternalMapping).where(
                OntologyTermExternalMapping.term_id == target_id
            )
        )
    ).scalars().all()
    tgt_map_keys = {(m.external_system, m.external_iri) for m in tgt_maps}
    grounding_count = (
        await session.execute(
            select(func.count())
            .select_from(OntologyTermGrounding)
            .where(OntologyTermGrounding.term_id == source_id)
        )
    ).scalar_one()
    business = {}
    for key, model in TERM_TABLE_BY_TYPE.items():
        business[key] = (
            await session.execute(
                select(func.count()).select_from(model).where(model.term_id == source_id)
            )
        ).scalar_one()
    return {
        "source": {
            "id": str(source.id),
            "term_code": source.term_code,
            "canonical_term_en": source.canonical_term_en,
            "status": source.status,
        },
        "target": {
            "id": str(target.id),
            "term_code": target.term_code,
            "canonical_term_en": target.canonical_term_en,
            "status": target.status,
        },
        "synonyms_to_move": len(src_syns),
        "synonym_conflicts": sum(1 for s in src_syns if (s.synonym_text, s.lang) in tgt_syn_keys),
        "external_mappings_to_move": len(src_maps),
        "external_mapping_conflicts": sum(
            1 for m in src_maps if (m.external_system, m.external_iri) in tgt_map_keys
        ),
        "groundings_to_update": grounding_count,
        "business_rows_to_update": business,
        "source_status_after": "merged",
    }


async def batch_activate(
    session: AsyncSession,
    term_ids: list[uuid.UUID],
    *,
    operator_id: str | None = None,
    reason: str | None = None,
) -> dict:
    activated = skipped = failed = 0
    errors = []
    for term_id in term_ids:
        try:
            term = await session.get(OntologyTerm, term_id)
            if term is None:
                skipped += 1
                continue
            if term.status == "active":
                skipped += 1
                continue
            await activate_term(session, term_id, operator_id=operator_id, reason=reason)
            activated += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            errors.append({"term_id": str(term_id), "error": str(exc)})
    await session.flush()
    return {
        "activated": activated,
        "skipped": skipped,
        "failed": failed,
        "errors": errors[:20],
    }


async def manual_grounding(
    session: AsyncSession,
    *,
    target_type: str,
    target_id: uuid.UUID,
    term_id: uuid.UUID,
    operator_id: str | None = None,
    reason: str | None = None,
) -> dict:
    model = TERM_TABLE_BY_TYPE.get(target_type)
    if model is None:
        raise ValueError(f"unsupported target_type: {target_type}")
    term = await resolve_any_term(session, term_id)
    row = await session.get(model, target_id)
    if row is None:
        raise ValueError("target not found")
    grounding = await _upsert_grounding(
        session,
        target_type=target_type,
        target_id=target_id,
        term_id=term.id,
        grounded_by="manual",
        confidence=1.0,
        created_by=operator_id or "manual",
    )
    row.term_id = term.id
    session.add(
        OntologyChangeLog(
            action_type="grounding.manual",
            entity_type=f"ontology_term_grounding:{target_type}",
            entity_id=target_id,
            before_data={},
            after_data={
                "term_id": str(term.id),
                "term_code": term.term_code,
                "target_type": target_type,
                "target_id": str(target_id),
            },
            operator_id=operator_id,
            reason=reason,
        )
    )
    await session.flush()
    return {
        "target_type": target_type,
        "target_id": str(target_id),
        "term_id": str(term.id),
        "term_code": term.term_code,
    }


async def resolve_any_term(session: AsyncSession, term_id: uuid.UUID) -> OntologyTerm:
    term = await session.get(OntologyTerm, term_id)
    if term is None:
        raise ValueError("term not found")
    return term


async def batch_grounding_by_text(
    session: AsyncSession,
    *,
    target_type: str,
    term_text: str,
    term_id: uuid.UUID,
    operator_id: str | None = None,
    limit: int = 500,
) -> dict:
    model = TERM_TABLE_BY_TYPE.get(target_type)
    if model is None:
        raise ValueError(f"unsupported target_type: {target_type}")
    term = await resolve_any_term(session, term_id)
    column = model.function_term if hasattr(model, "function_term") else model.function_term_en
    rows = (
        await session.execute(
            select(model)
            .where(func.lower(func.trim(column)) == term_text.lower().strip())
            .limit(limit)
        )
    ).scalars().all()
    updated = 0
    for row in rows:
        if row.term_id == term.id:
            continue
        await _upsert_grounding(
            session,
            target_type=target_type,
            target_id=row.id,
            term_id=term.id,
            grounded_by="manual",
            confidence=1.0,
            created_by=operator_id or "manual",
        )
        row.term_id = term.id
        updated += 1
    await session.flush()
    return {"target_type": target_type, "term_text": term_text, "updated": updated}


async def vocabulary_usage(
    session: AsyncSession, vocab_type: str | None = None
) -> dict:
    vocab = await _active_vocab(session)
    fields = {v: k for k, v in _FIELD_VOCAB_TYPE.items() if k}
    rows = (
        await session.execute(
            select(OntologyVocabulary).order_by(
                OntologyVocabulary.vocab_type, OntologyVocabulary.seq
            )
        )
    ).scalars().all()
    items = []
    for entry in rows:
        if vocab_type and entry.vocab_type != vocab_type:
            continue
        usage = 0
        for field, model_col in ENUM_FIELD_MAP.items():
            if _FIELD_VOCAB_TYPE.get(field) != entry.vocab_type:
                continue
            model, column = model_col
            usage += (
                await session.execute(
                    select(func.count())
                    .select_from(model)
                    .where(getattr(model, column) == entry.code)
                )
            ).scalar_one()
        items.append(
            {
                "id": str(entry.id),
                "code": entry.code,
                "vocab_type": entry.vocab_type,
                "label_cn": entry.label_cn,
                "label_en": entry.label_en,
                "description": entry.description,
                "status": entry.status,
                "seq": entry.seq,
                "usage_count": usage,
                "updated_at": entry.updated_at.isoformat(),
            }
        )
    return {"items": items, "total": len(items)}


async def list_enum_anomalies(
    session: AsyncSession,
    *,
    field: str,
    granularity_level: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    pair = ENUM_FIELD_MAP.get(field)
    if pair is None:
        raise ValueError(f"unsupported field: {field}")
    model, column = pair
    vocab = await _active_vocab(session)
    allowed = vocab.get(_FIELD_VOCAB_TYPE.get(field, ""), set())
    if not allowed:
        return {"items": [], "total": 0}
    conds = [getattr(model, column).notin_(list(allowed))]
    if granularity_level and hasattr(model, "granularity_level"):
        conds.append(model.granularity_level == granularity_level)
    total = (
        await session.execute(
            select(func.count()).select_from(model).where(*conds)
        )
    ).scalar_one()
    rows = (
        await session.execute(select(model).where(*conds).offset(offset).limit(limit))
    ).scalars().all()
    items = []
    for row in rows:
        items.append(
            {
                "target_type": model.__tablename__,
                "target_id": str(row.id),
                "field": field,
                "value": str(getattr(row, column)),
                "granularity_level": getattr(row, "granularity_level", None),
            }
        )
    return {"items": items, "total": total}


async def replace_enum_values(
    session: AsyncSession,
    *,
    field: str,
    old_value: str,
    new_code: str,
    operator_id: str | None = None,
    reason: str | None = None,
) -> dict:
    pair = ENUM_FIELD_MAP.get(field)
    if pair is None:
        raise ValueError(f"unsupported field: {field}")
    model, column = pair
    vocab = await _active_vocab(session)
    allowed = vocab.get(_FIELD_VOCAB_TYPE.get(field, ""), set())
    if new_code not in allowed:
        raise ValueError(f"new_code not in active vocabulary: {new_code}")
    result = await session.execute(
        update(model)
        .where(getattr(model, column) == old_value)
        .values({column: new_code})
    )
    count = result.rowcount or 0
    session.add(
        OntologyChangeLog(
            action_type="enum.replace",
            entity_type=model.__tablename__,
            entity_id=uuid.uuid4(),
            before_data={"field": field, "old_value": old_value},
            after_data={"field": field, "new_code": new_code, "affected_rows": count},
            operator_id=operator_id,
            reason=reason,
        )
    )
    await session.flush()
    return {"field": field, "old_value": old_value, "new_code": new_code, "updated": count}


async def duplicate_terms(
    session: AsyncSession, *, limit: int = 50, offset: int = 0
) -> dict:
    terms = (
        await session.execute(
            select(OntologyTerm).where(OntologyTerm.status.in_(("active", "proposed")))
        )
    ).scalars().all()
    synonyms = (
        await session.execute(select(OntologyTermSynonym))
    ).scalars().all()
    syn_by_key: dict[str, list[uuid.UUID]] = {}
    for s in synonyms:
        key = normalize_term_key(s.synonym_text)
        if key:
            syn_by_key.setdefault(key, []).append(s.term_id)
    canon_by_key: dict[str, list[OntologyTerm]] = {}
    for t in terms:
        canon_by_key.setdefault(normalize_term_key(t.canonical_term_en), []).append(t)
    groups = []
    for key, members in canon_by_key.items():
        if len(members) > 1:
            groups.append({"basis": f"canonical:{key}", "term_ids": [str(t.id) for t in members]})
    for key, ids in syn_by_key.items():
        if len(set(ids)) > 1:
            groups.append({"basis": f"synonym:{key}", "term_ids": [str(i) for i in set(ids)]})
    return {
        "items": groups[offset : offset + limit],
        "total": len(groups),
    }


async def list_alignment_candidates(
    session: AsyncSession,
    *,
    status: str | None = None,
    granularity_level: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    q = (
        select(OntologyAlignmentCandidate, CandidateBrainRegion)
        .join(
            CandidateBrainRegion,
            and_(
                OntologyAlignmentCandidate.target_type == "region",
                OntologyAlignmentCandidate.target_id == CandidateBrainRegion.id,
            ),
        )
        .order_by(OntologyAlignmentCandidate.created_at.desc())
    )
    if status:
        q = q.where(OntologyAlignmentCandidate.status == status)
    if granularity_level:
        q = q.where(CandidateBrainRegion.granularity_level == granularity_level)
    total = (
        await session.execute(select(func.count()).select_from(q.subquery()))
    ).scalar_one()
    rows = (await session.execute(q.offset(offset).limit(limit))).all()
    items = []
    for candidate, region in rows:
        items.append(
            {
                "candidate_id": str(candidate.id),
                "region_id": str(region.id),
                "en_name": region.en_name,
                "cn_name": region.cn_name,
                "source_atlas": region.source_atlas,
                "external_system": candidate.external_system,
                "external_iri": candidate.external_iri,
                "external_label": candidate.external_label,
                "match_type": candidate.match_type,
                "match_score": float(candidate.match_score) if candidate.match_score is not None else None,
                "match_details": candidate.match_details,
                "status": candidate.status,
                "reviewed_by": candidate.reviewed_by,
                "reviewed_at": candidate.reviewed_at.isoformat() if candidate.reviewed_at else None,
            }
        )
    return {"items": items, "total": total}


async def alignment_candidates_stats(
    session: AsyncSession, granularity_level: str | None = None
) -> dict:
    q = (
        select(OntologyAlignmentCandidate, CandidateBrainRegion)
        .join(
            CandidateBrainRegion,
            and_(
                OntologyAlignmentCandidate.target_type == "region",
                OntologyAlignmentCandidate.target_id == CandidateBrainRegion.id,
            ),
        )
    )
    if granularity_level:
        q = q.where(CandidateBrainRegion.granularity_level == granularity_level)
    rows = (await session.execute(q)).all()
    status_counts: dict[str, int] = {}
    match_counts: dict[str, int] = {}
    for candidate, _region in rows:
        status_counts[candidate.status] = status_counts.get(candidate.status, 0) + 1
        match_counts[candidate.match_type] = match_counts.get(candidate.match_type, 0) + 1
    return {
        "total": len(rows),
        "by_status": status_counts,
        "by_match_type": match_counts,
    }


async def review_alignment_candidate(
    session: AsyncSession,
    candidate_id: uuid.UUID,
    *,
    action: str,
    operator_id: str | None = None,
    reason: str | None = None,
    external_iri: str | None = None,
    external_label: str | None = None,
) -> dict:
    candidate = await session.get(OntologyAlignmentCandidate, candidate_id)
    if candidate is None:
        raise ValueError("candidate not found")
    if candidate.status in ("accepted", "rejected"):
        raise ValueError(f"candidate already reviewed: {candidate.status}")
    if action not in ("accept", "reject", "modify"):
        raise ValueError("action must be accept|reject|modify")
    before = {
        "status": candidate.status,
        "external_iri": candidate.external_iri,
        "external_label": candidate.external_label,
    }
    if external_iri:
        candidate.external_iri = external_iri
    if external_label:
        candidate.external_label = external_label
    if action == "accept":
        candidate.status = "accepted"
        if candidate.target_type == "region":
            region = await session.get(CandidateBrainRegion, candidate.target_id)
            if region is None:
                raise ValueError("target region not found")
            if candidate.external_system.lower() == "uberon":
                region.uberon_iri = candidate.external_iri
            elif candidate.external_system.lower() == "nifstd":
                region.nifstd_iri = candidate.external_iri
            region.alignment_status = "aligned"
    elif action == "reject":
        candidate.status = "rejected"
    else:
        candidate.status = "pending"
    candidate.reviewed_by = operator_id
    candidate.reviewed_at = _now()
    session.add(
        OntologyChangeLog(
            action_type=f"alignment.{action}",
            entity_type="ontology_alignment_candidate",
            entity_id=candidate.id,
            before_data=before,
            after_data={
                "status": candidate.status,
                "external_iri": candidate.external_iri,
                "external_label": candidate.external_label,
            },
            operator_id=operator_id,
            reason=reason,
        )
    )
    await session.flush()
    return {"candidate_id": str(candidate.id), "status": candidate.status}


async def batch_accept_exact_candidates(
    session: AsyncSession, *, operator_id: str | None = None
) -> dict:
    candidates = (
        await session.execute(
            select(OntologyAlignmentCandidate).where(
                OntologyAlignmentCandidate.match_type == "exact",
                OntologyAlignmentCandidate.status == "pending",
            )
        )
    ).scalars().all()
    accepted = 0
    for candidate in candidates:
        await review_alignment_candidate(
            session,
            candidate.id,
            action="accept",
            operator_id=operator_id,
            reason="batch accept exact candidates",
        )
        accepted += 1
    await session.flush()
    return {"accepted": accepted}


async def list_change_logs(
    session: AsyncSession,
    *,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    action_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    q = select(OntologyChangeLog).order_by(OntologyChangeLog.created_at.desc())
    if entity_type:
        q = q.where(OntologyChangeLog.entity_type == entity_type)
    if entity_id:
        q = q.where(OntologyChangeLog.entity_id == entity_id)
    if action_type:
        q = q.where(OntologyChangeLog.action_type == action_type)
    total = (
        await session.execute(select(func.count()).select_from(q.subquery()))
    ).scalar_one()
    rows = (await session.execute(q.offset(offset).limit(limit))).scalars().all()
    return {
        "items": [
            {
                "id": str(log.id),
                "action_type": log.action_type,
                "entity_type": log.entity_type,
                "entity_id": str(log.entity_id),
                "before_data": log.before_data,
                "after_data": log.after_data,
                "operator_id": log.operator_id,
                "reason": log.reason,
                "created_at": log.created_at.isoformat(),
            }
            for log in rows
        ],
        "total": total,
    }


async def run_audit(
    session: AsyncSession,
    *,
    granularity_level: str | None = None,
    created_by: str | None = None,
) -> dict:
    run = OntologyAuditRun(
        status="running",
        granularity_level=granularity_level,
        created_by=created_by,
    )
    session.add(run)
    await session.flush()
    try:
        summary = await issues_summary(session, granularity_level)
        run.summary = summary
        run.status = "completed"
        run.finished_at = _now()
    except Exception as exc:  # noqa: BLE001
        run.status = "failed"
        run.error_message = str(exc)
        run.finished_at = _now()
    await session.flush()
    return {
        "run_id": str(run.id),
        "status": run.status,
        "summary": run.summary,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


async def list_audit_runs(
    session: AsyncSession, *, limit: int = 20, offset: int = 0
) -> dict:
    q = select(OntologyAuditRun).order_by(OntologyAuditRun.started_at.desc())
    total = (
        await session.execute(select(func.count()).select_from(q.subquery()))
    ).scalar_one()
    rows = (await session.execute(q.offset(offset).limit(limit))).scalars().all()
    return {
        "items": [
            {
                "id": str(run.id),
                "status": run.status,
                "granularity_level": run.granularity_level,
                "summary": run.summary,
                "started_at": run.started_at.isoformat(),
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "error_message": run.error_message,
            }
            for run in rows
        ],
        "total": total,
    }
