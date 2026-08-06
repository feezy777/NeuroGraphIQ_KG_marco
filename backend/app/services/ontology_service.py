"""Ontology service: vocabulary/term registry, grounding, coverage."""

from __future__ import annotations

import re
import uuid

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mirror_kg import MirrorRegionFunction
from app.models.mirror_macro_clinical import MirrorCircuitFunction, MirrorProjectionFunction
from app.models.candidate import CandidateBrainRegion
from app.models.ontology import (
    OntologyTerm,
    OntologyTermExternalMapping,
    OntologyTermGrounding,
    OntologyTermSynonym,
    OntologyVocabulary,
)

TERM_TABLE_BY_TYPE: dict[str, type] = {
    "circuit_function": MirrorCircuitFunction,
    "projection_function": MirrorProjectionFunction,
    "region_function": MirrorRegionFunction,
}

_TERM_CODE_PREFIX = {
    "function": "ng:func",
    "projection": "ng:proj",
    "region": "ng:region",
    "other": "ng:term",
}


def normalize_term_key(text: str) -> str:
    """Lowercase and collapse to alphanumeric tokens for deterministic matching."""
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    return " ".join(tokens)


def _term_code(canonical_term_en: str, term_type: str) -> str:
    prefix = _TERM_CODE_PREFIX.get(term_type or "other", "ng:term")
    slug = normalize_term_key(canonical_term_en).replace(" ", "_") or "unnamed"
    return f"{prefix}:{slug}"


def _index_lookup(index: dict[str, uuid.UUID], term_text: str) -> uuid.UUID | None:
    return index.get(normalize_term_key(term_text))


def _term_text_for(row, target_type: str) -> str:
    if target_type == "circuit_function":
        return str(row.function_term_en or row.function_term_cn or "")
    if target_type == "projection_function":
        return str(row.function_term or row.function_term_cn or "")
    if target_type == "region_function":
        return str(row.function_term or "")
    return ""


async def _load_term_index(session: AsyncSession) -> dict[str, uuid.UUID]:
    index: dict[str, uuid.UUID] = {}
    terms = (
        await session.execute(
            select(OntologyTerm).where(OntologyTerm.status == "active")
        )
    ).scalars().all()
    for term in terms:
        key = normalize_term_key(term.canonical_term_en)
        if key:
            index.setdefault(key, term.id)
    synonyms = (
        await session.execute(
            select(OntologyTermSynonym).where(OntologyTermSynonym.status == "active")
        )
    ).scalars().all()
    for synonym in synonyms:
        key = normalize_term_key(synonym.synonym_text)
        if key:
            index.setdefault(key, synonym.term_id)
    return index


async def _upsert_grounding(
    session: AsyncSession,
    *,
    target_type: str,
    target_id: uuid.UUID,
    term_id: uuid.UUID | None,
    grounded_by: str,
    confidence: float | None,
    created_by: str | None,
) -> OntologyTermGrounding:
    await session.execute(
        delete(OntologyTermGrounding).where(
            OntologyTermGrounding.target_type == target_type,
            OntologyTermGrounding.target_id == target_id,
        )
    )
    grounding = OntologyTermGrounding(
        target_type=target_type,
        target_id=target_id,
        term_id=term_id,
        grounded_by=grounded_by,
        confidence=confidence,
        created_by=created_by,
    )
    session.add(grounding)
    await session.flush()
    return grounding


# ---- Vocabulary ----


async def list_vocabularies(
    session: AsyncSession,
    *,
    vocab_type: str | None = None,
    status: str | None = None,
) -> list[OntologyVocabulary]:
    query = select(OntologyVocabulary).order_by(
        OntologyVocabulary.vocab_type, OntologyVocabulary.seq
    )
    if vocab_type:
        query = query.where(OntologyVocabulary.vocab_type == vocab_type)
    if status:
        query = query.where(OntologyVocabulary.status == status)
    return list((await session.execute(query)).scalars().all())


async def create_vocabulary(
    session: AsyncSession,
    *,
    code: str,
    vocab_type: str,
    label_cn: str | None = None,
    label_en: str | None = None,
    description: str | None = None,
    seq: int = 0,
) -> OntologyVocabulary:
    existing = (
        await session.execute(
            select(OntologyVocabulary).where(
                OntologyVocabulary.code == code,
                OntologyVocabulary.vocab_type == vocab_type,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ValueError(f"vocabulary {vocab_type}:{code} already exists")
    row = OntologyVocabulary(
        code=code,
        vocab_type=vocab_type,
        label_cn=label_cn,
        label_en=label_en,
        description=description,
        seq=seq,
    )
    session.add(row)
    await session.flush()
    return row


async def get_active_codes(session: AsyncSession, vocab_type: str) -> list[str]:
    query = (
        select(OntologyVocabulary.code)
        .where(
            OntologyVocabulary.vocab_type == vocab_type,
            OntologyVocabulary.status == "active",
        )
        .order_by(OntologyVocabulary.seq)
    )
    return list((await session.execute(query)).scalars().all())


async def load_active_vocab_context(session: AsyncSession) -> dict[str, set[str]]:
    """Load all active vocabulary codes grouped by vocab_type (one query)."""
    rows = (
        await session.execute(
            select(OntologyVocabulary.code, OntologyVocabulary.vocab_type).where(
                OntologyVocabulary.status == "active"
            )
        )
    ).all()
    context: dict[str, set[str]] = {}
    for code, vocab_type in rows:
        context.setdefault(vocab_type, set()).add(code)
    return context


# ---- Terms ----


async def list_terms(
    session: AsyncSession,
    *,
    status: str | None = None,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[OntologyTerm], int]:
    conditions = []
    if status:
        conditions.append(OntologyTerm.status == status)
    if q:
        pattern = f"%{q.strip()}%"
        conditions.append(
            or_(
                OntologyTerm.canonical_term_en.ilike(pattern),
                OntologyTerm.canonical_term_cn.ilike(pattern),
            )
        )
    total_query = select(func.count()).select_from(OntologyTerm)
    query = select(OntologyTerm).order_by(OntologyTerm.created_at.desc())
    for condition in conditions:
        total_query = total_query.where(condition)
        query = query.where(condition)
    total = (await session.execute(total_query)).scalar_one()
    rows = (await session.execute(query.limit(limit).offset(offset))).scalars().all()
    return list(rows), total


async def propose_term(
    session: AsyncSession,
    *,
    canonical_term_en: str,
    canonical_term_cn: str | None = None,
    term_type: str = "function",
    category: str | None = None,
    domain: str | None = None,
    role: str | None = None,
    effect_type: str | None = None,
    description: str | None = None,
    created_by: str = "llm",
) -> OntologyTerm:
    key = normalize_term_key(canonical_term_en)
    if not key:
        raise ValueError("canonical_term_en must be non-empty")
    existing_terms = (
        await session.execute(
            select(OntologyTerm).where(OntologyTerm.status != "deprecated")
        )
    ).scalars().all()
    for term in existing_terms:
        if normalize_term_key(term.canonical_term_en) == key:
            return term
    row = OntologyTerm(
        term_code=_term_code(canonical_term_en, term_type),
        canonical_term_en=canonical_term_en.strip(),
        canonical_term_cn=canonical_term_cn,
        term_type=term_type,
        category=category,
        domain=domain,
        role=role,
        effect_type=effect_type,
        description=description,
        status="proposed",
        created_by=created_by,
    )
    session.add(row)
    await session.flush()
    return row


async def activate_term(session: AsyncSession, term_id: uuid.UUID) -> OntologyTerm:
    term = await session.get(OntologyTerm, term_id)
    if term is None:
        raise ValueError("term not found")
    if term.status == "deprecated":
        raise ValueError("cannot activate deprecated term")
    term.status = "active"
    await session.flush()
    return term


async def deprecate_term(session: AsyncSession, term_id: uuid.UUID) -> OntologyTerm:
    term = await session.get(OntologyTerm, term_id)
    if term is None:
        raise ValueError("term not found")
    term.status = "deprecated"
    await session.flush()
    return term


async def merge_term(
    session: AsyncSession,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
) -> OntologyTerm:
    if source_id == target_id:
        raise ValueError("cannot merge a term into itself")
    source = await session.get(OntologyTerm, source_id)
    target = await session.get(OntologyTerm, target_id)
    if source is None or target is None:
        raise ValueError("term not found")
    source_synonyms = (
        await session.execute(
            select(OntologyTermSynonym).where(OntologyTermSynonym.term_id == source_id)
        )
    ).scalars().all()
    target_synonyms = (
        await session.execute(
            select(OntologyTermSynonym).where(OntologyTermSynonym.term_id == target_id)
        )
    ).scalars().all()
    target_keys = {(s.synonym_text, s.lang) for s in target_synonyms}
    for synonym in source_synonyms:
        if (synonym.synonym_text, synonym.lang) in target_keys:
            await session.delete(synonym)
    await session.execute(
        update(OntologyTermSynonym)
        .where(OntologyTermSynonym.term_id == source_id)
        .values(term_id=target_id)
    )
    await session.execute(
        update(OntologyTermExternalMapping)
        .where(OntologyTermExternalMapping.term_id == source_id)
        .values(term_id=target_id)
    )
    await session.execute(
        update(OntologyTermGrounding)
        .where(OntologyTermGrounding.term_id == source_id)
        .values(term_id=target_id)
    )
    for model in TERM_TABLE_BY_TYPE.values():
        await session.execute(
            update(model).where(model.term_id == source_id).values(term_id=target_id)
        )
    await session.delete(source)
    await session.flush()
    return target


async def add_synonym(
    session: AsyncSession,
    *,
    term_id: uuid.UUID,
    synonym_text: str,
    lang: str = "en",
    match_type: str = "synonym",
    confidence: float | None = None,
) -> OntologyTermSynonym:
    term = await session.get(OntologyTerm, term_id)
    if term is None:
        raise ValueError("term not found")
    row = OntologyTermSynonym(
        term_id=term_id,
        synonym_text=synonym_text.strip(),
        lang=lang,
        match_type=match_type,
        confidence=confidence,
    )
    session.add(row)
    await session.flush()
    return row


# ---- Grounding ----


async def ground_deterministic(
    session: AsyncSession,
    *,
    target_type: str,
    target_id: uuid.UUID,
    term_text: str,
    created_by: str = "system",
) -> OntologyTermGrounding:
    model = TERM_TABLE_BY_TYPE.get(target_type)
    if model is None:
        raise ValueError(f"unsupported target_type: {target_type}")
    row = await session.get(model, target_id)
    if row is None:
        raise ValueError("target not found")
    index = await _load_term_index(session)
    term_id = _index_lookup(index, term_text)
    if term_id is None:
        grounding = await _upsert_grounding(
            session,
            target_type=target_type,
            target_id=target_id,
            term_id=None,
            grounded_by="ungrounded",
            confidence=None,
            created_by=created_by,
        )
    else:
        grounding = await _upsert_grounding(
            session,
            target_type=target_type,
            target_id=target_id,
            term_id=term_id,
            grounded_by="deterministic",
            confidence=1.0,
            created_by=created_by,
        )
    row.term_id = grounding.term_id
    await session.flush()
    return grounding


async def run_deterministic_grounding_batch(
    session: AsyncSession,
    target_type: str,
    limit: int = 500,
) -> dict:
    model = TERM_TABLE_BY_TYPE.get(target_type)
    if model is None:
        raise ValueError(f"unsupported target_type: {target_type}")
    index = await _load_term_index(session)
    ungrounded_exists = (
        select(OntologyTermGrounding.target_id)
        .where(
            OntologyTermGrounding.target_type == target_type,
            OntologyTermGrounding.target_id == model.id,
        )
        .exists()
    )
    rows = (
        await session.execute(select(model).where(~ungrounded_exists).limit(limit))
    ).scalars().all()
    if not rows:
        return {"target_type": target_type, "processed": 0, "grounded": 0, "ungrounded": 0}
    target_ids = [row.id for row in rows]
    await session.execute(
        delete(OntologyTermGrounding).where(
            OntologyTermGrounding.target_type == target_type,
            OntologyTermGrounding.target_id.in_(target_ids),
        )
    )
    grounded = 0
    for row in rows:
        term_id = _index_lookup(index, _term_text_for(row, target_type))
        session.add(
            OntologyTermGrounding(
                target_type=target_type,
                target_id=row.id,
                term_id=term_id,
                grounded_by="deterministic" if term_id else "ungrounded",
                confidence=1.0 if term_id else None,
                created_by="system",
            )
        )
        row.term_id = term_id
        if term_id:
            grounded += 1
    await session.flush()
    return {
        "target_type": target_type,
        "processed": len(rows),
        "grounded": grounded,
        "ungrounded": len(rows) - grounded,
    }


async def list_groundings(
    session: AsyncSession,
    *,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[OntologyTermGrounding], int]:
    conditions = []
    if target_type:
        conditions.append(OntologyTermGrounding.target_type == target_type)
    if target_id:
        conditions.append(OntologyTermGrounding.target_id == target_id)
    total_query = select(func.count()).select_from(OntologyTermGrounding)
    query = select(OntologyTermGrounding).order_by(OntologyTermGrounding.grounded_at.desc())
    for condition in conditions:
        total_query = total_query.where(condition)
        query = query.where(condition)
    total = (await session.execute(total_query)).scalar_one()
    rows = (await session.execute(query.limit(limit).offset(offset))).scalars().all()
    return list(rows), total


# ---- Coverage & Panorama ----


async def coverage(session: AsyncSession, granularity_level: str | None = None) -> dict:
    items = []
    for key, model in TERM_TABLE_BY_TYPE.items():
        total_query = select(func.count()).select_from(model)
        grounded_query = (
            select(func.count()).select_from(model).where(model.term_id.is_not(None))
        )
        method_query = (
            select(OntologyTermGrounding.grounded_by, func.count())
            .join(model, OntologyTermGrounding.target_id == model.id)
            .where(OntologyTermGrounding.target_type == key)
        )
        if granularity_level:
            total_query = total_query.where(model.granularity_level == granularity_level)
            grounded_query = grounded_query.where(
                model.granularity_level == granularity_level
            )
            method_query = method_query.where(
                model.granularity_level == granularity_level
            )
        total = (await session.execute(total_query)).scalar_one()
        grounded = (await session.execute(grounded_query)).scalar_one()
        method_rows = (
            await session.execute(
                method_query.group_by(OntologyTermGrounding.grounded_by)
            )
        ).all()
        items.append(
            {
                "key": key,
                "label": key,
                "total": total,
                "grounded": grounded,
                "ungrounded": total - grounded,
                "by_method": {row[0]: row[1] for row in method_rows},
            }
        )
    total_terms = (
        await session.execute(select(func.count()).select_from(OntologyTerm))
    ).scalar_one()
    active_terms = (
        await session.execute(
            select(func.count()).select_from(OntologyTerm).where(OntologyTerm.status == "active")
        )
    ).scalar_one()
    proposed_terms = (
        await session.execute(
            select(func.count()).select_from(OntologyTerm).where(OntologyTerm.status == "proposed")
        )
    ).scalar_one()
    return {
        "items": items,
        "total_terms": total_terms,
        "active_terms": active_terms,
        "proposed_terms": proposed_terms,
    }


async def term_panorama(
    session: AsyncSession,
    target_type: str,
    granularity_level: str | None = None,
    limit: int = 5000,
) -> dict:
    model = TERM_TABLE_BY_TYPE.get(target_type)
    if model is None:
        raise ValueError(f"unsupported target_type: {target_type}")
    column = model.function_term if hasattr(model, "function_term") else model.function_term_en
    query = (
        select(func.lower(func.trim(column)).label("term_key"), column.label("term_label"), func.count().label("cnt"))
        .group_by(column)
        .order_by(func.count().desc())
        .limit(limit)
    )
    if granularity_level:
        query = query.where(model.granularity_level == granularity_level)
    rows = (await session.execute(query)).all()
    items = [
        {"term_key": row[0], "term_label": row[1], "count": row[2], "sample_ids": []}
        for row in rows
    ]
    return {"target_type": target_type, "total_distinct": len(items), "items": items}


# ---- Region alignment ----


async def region_alignment_summary(
    session: AsyncSession,
    granularity_level: str | None = None,
    limit: int = 5000,
) -> dict:
    query = select(CandidateBrainRegion).order_by(CandidateBrainRegion.en_name)
    if granularity_level:
        query = query.where(CandidateBrainRegion.granularity_level == granularity_level)
    rows = (await session.execute(query.limit(limit))).scalars().all()
    total = len(rows)
    aligned = sum(1 for row in rows if (row.uberon_iri or "").strip() or (row.nifstd_iri or "").strip())
    items = [
        {
            "id": str(row.id),
            "en_name": row.en_name,
            "cn_name": row.cn_name,
            "source_atlas": row.source_atlas,
            "uberon_iri": row.uberon_iri,
            "nifstd_iri": row.nifstd_iri,
            "alignment_status": row.alignment_status,
        }
        for row in rows
    ]
    return {"total": total, "aligned": aligned, "unaligned": total - aligned, "items": items}
