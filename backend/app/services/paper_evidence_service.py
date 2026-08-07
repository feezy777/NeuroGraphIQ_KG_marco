"""Paper evidence retrieval (Europe PMC) + attach to Mirror KG evidence."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import unicodedata
import uuid

import httpx
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.models.mirror_kg import (
    ConfidenceAdjustmentLog,
    MirrorEvidenceRecord,
    MirrorEvidencePassage,
    PaperPassage,
    PaperSource,
    MirrorRegionCircuit,
    MirrorRegionConnection,
    MirrorRegionFunction,
)
from app.models.mirror_macro_clinical import (
    MirrorCircuitFunction,
    MirrorCircuitStep,
    MirrorProjectionFunction,
)
from app.models.ontology import OntologyChangeLog
from app.services.ontology_service import TERM_TABLE_BY_TYPE
from app.config import get_settings
from app.services.llm_providers.factory import get_llm_provider
from app.services.ontology_residual_schemas import PaperMultiPassageExtraction, PaperPassageExtraction
from app.services.confidence_rules import (
    FORMULA_VERSION,
    PARTIAL_CAP,
    SUPPORT_CAP,
    compute_adjustment,
)
from app.services.evidence_target_adapter import (
    TARGET_MODELS as ADAPTER_TARGET_MODELS,
    build_target_dto,
    build_retrieval_context,
)
from app.services.paragraph_retrieval import build_windows, score_paragraphs
from app.services import oa_xml_parser
from app.services import paper_fetch_service as pfs

EUROPE_PMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
SEARCH_TIMEOUT = 25

TARGET_MODELS = ADAPTER_TARGET_MODELS

# Batch execution tuning (independent concurrency for DeepSeek vs Europe PMC)
DEEPSEEK_CONCURRENCY = 2
EUROPE_PMC_CONCURRENCY = 4
BATCH_ITEM_RETRIES = 3
BATCH_BACKOFF_SECONDS = (1.0, 2.0, 4.0)


async def _write_audit(
    session: AsyncSession,
    *,
    action_type: str,
    entity_type: str,
    entity_id: uuid.UUID,
    before_data: dict | None = None,
    after_data: dict | None = None,
    operator_id: str | None = None,
    reason: str | None = None,
) -> None:
    session.add(
        OntologyChangeLog(
            action_type=action_type,
            entity_type=entity_type,
            entity_id=entity_id,
            before_data=before_data or {},
            after_data=after_data or {},
            operator_id=operator_id,
            reason=reason,
        )
    )


async def _write_validation_record(
    session: AsyncSession,
    *,
    evidence_id: uuid.UUID,
    rule_code: str,
    target_type: str,
    target_id: uuid.UUID,
    direction: str | None,
    paper_snapshot: dict | None = None,
    detail: dict | None = None,
    task_id: str | None = None,
    created_by: str | None = None,
) -> None:
    await session.execute(
        text(
            "INSERT INTO evidence_validation_records "
            "(evidence_id, task_id, rule_code, status, target_type, target_id, direction, "
            "paper_snapshot, detail, created_by) "
            "VALUES (:eid, :tid, :rule, 'pending', :tt, :oid, :dir, CAST(:ps AS jsonb), CAST(:det AS jsonb), :cb)"
        ),
        {
            "eid": evidence_id,
            "tid": uuid.UUID(task_id) if task_id else None,
            "rule": rule_code,
            "tt": target_type,
            "oid": target_id,
            "dir": direction,
            "ps": json.dumps(paper_snapshot or {}, ensure_ascii=False),
            "det": json.dumps(detail or {}, ensure_ascii=False),
            "cb": created_by,
        },
    )


# ---- Passage verification (pure functions) ----


def normalize_for_match(text: str) -> str:
    """NFKC + collapse whitespace/newlines + unify common unicode punctuation."""
    t = unicodedata.normalize("NFKC", text or "")
    t = re.sub(r"[\u2010-\u2015\u2212\u00ad\u2018\u2019\u201c\u201d\u3001\u3002\uff0c\uff0e]", "-", t)
    t = re.sub(r"[\s\u200b\u200c\u200d]+", " ", t)
    return t.strip().lower()


def passage_hash(passage: str) -> str:
    return hashlib.sha256(normalize_for_match(passage).encode("utf-8")).hexdigest()


def exact_passage_match(passage: str, source: str) -> bool:
    return bool(passage and passage in source)


def normalized_passage_match(passage: str, source: str) -> bool:
    return bool(passage and normalize_for_match(passage) in normalize_for_match(source))


def _normalize_whitespace_only(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def locate_passage(passage: str, source: str) -> tuple[int | None, str | None]:
    """Find containing paragraph index (paragraph split by blank lines)."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", source or "")]
    for idx, para in enumerate(paragraphs):
        if passage in para or normalized_passage_match(passage, para):
            return idx, f"paragraph:{idx}"
    return None, None


def verify_passage_against_source(passage: str, source: str) -> tuple[bool, str | None]:
    if exact_passage_match(passage, source):
        return True, "exact"
    if _normalize_whitespace_only(passage) and _normalize_whitespace_only(passage) in _normalize_whitespace_only(source):
        return True, "normalized_whitespace"
    if normalized_passage_match(passage, source):
        return True, "normalized_unicode"
    return False, None


def verify_and_locate_passage(
    passage: str, source: str, source_scope: str
) -> tuple[bool, str | None, int | None, str | None]:
    verified, method = verify_passage_against_source(passage, source)
    para_idx, locator = locate_passage(passage, source)
    locator = locator or (f"{source_scope}:verified:{method}" if verified else None)
    return verified, method, para_idx, locator


def normalize_doi(doi: str) -> str:
    """Lowercase, strip URL prefix / whitespace; keep '10.' prefix convention."""
    value = (doi or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "http://dx.doi.org/", "https://dx.doi.org/", "doi:"):
        if value.startswith(prefix):
            value = value[len(prefix):]
    return value.strip()


async def ensure_paper_source(
    session: AsyncSession, paper: dict, *, fetched_at: bool = True
) -> PaperSource:
    """Upsert paper_sources by PMID (preferred) or normalized DOI. Idempotent."""
    pmid = (paper.get("pmid") or "").strip()
    doi = (paper.get("doi") or "").strip()
    norm_doi = normalize_doi(doi) if doi else ""
    abstract = (paper.get("abstract") or "").strip()
    fulltext = (paper.get("fulltext") or "").strip()
    abstract_hash = hashlib.sha256(abstract.encode("utf-8")).hexdigest() if abstract else None
    fulltext_hash = hashlib.sha256(fulltext.encode("utf-8")).hexdigest() if fulltext else None
    year = int(paper["year"]) if str(paper.get("year") or "").isdigit() else None
    metadata_json = json.dumps(
        {
            "authors": paper.get("authors") or "",
            "mode": paper.get("mode") or "function",
            "pmcid": paper.get("pmcid") or "",
        },
        ensure_ascii=False,
    )
    row_id = None
    if pmid:
        row_id = (
            await session.execute(
                text(
                    "INSERT INTO paper_sources "
                    "(source, pmid, pmcid, doi, normalized_doi, title, journal, publication_year, "
                    "is_oa, abstract_available, fulltext_available, metadata_json, abstract_hash, "
                    "fulltext_hash, fetched_at) "
                    "VALUES (:source, :pmid, :pmcid, :doi, :norm_doi, :title, :journal, :year, "
                    ":is_oa, :abs_avail, :ft_avail, CAST(:meta AS jsonb), :abs_hash, :ft_hash, "
                    "CASE WHEN :fetched THEN now() ELSE NULL END) "
                    "ON CONFLICT (pmid) WHERE pmid IS NOT NULL AND pmid <> '' "
                    "DO UPDATE SET doi=EXCLUDED.doi, normalized_doi=EXCLUDED.normalized_doi, "
                    "title=EXCLUDED.title, journal=EXCLUDED.journal, publication_year=EXCLUDED.publication_year, "
                    "is_oa=EXCLUDED.is_oa, abstract_available=EXCLUDED.abstract_available, "
                    "fulltext_available=EXCLUDED.fulltext_available, "
                    "abstract_hash=COALESCE(EXCLUDED.abstract_hash, paper_sources.abstract_hash), "
                    "fulltext_hash=COALESCE(EXCLUDED.fulltext_hash, paper_sources.fulltext_hash), "
                    "fetched_at=CASE WHEN :fetched THEN now() ELSE paper_sources.fetched_at END, "
                    "updated_at=now() "
                    "RETURNING id"
                ),
                {
                    "source": paper.get("source") or "europepmc",
                    "pmid": pmid,
                    "pmcid": (paper.get("pmcid") or "").strip() or None,
                    "doi": doi or None,
                    "norm_doi": norm_doi or None,
                    "title": paper.get("title") or None,
                    "journal": paper.get("journal") or None,
                    "year": year,
                    "is_oa": bool(paper.get("is_open_access", False)),
                    "abs_avail": bool(abstract),
                    "ft_avail": bool(fulltext),
                    "meta": metadata_json,
                    "abs_hash": abstract_hash,
                    "ft_hash": fulltext_hash,
                    "fetched": fetched_at,
                },
            )
        ).scalar_one()
    elif norm_doi:
        row_id = (
            await session.execute(
                text(
                    "INSERT INTO paper_sources "
                    "(source, pmid, pmcid, doi, normalized_doi, title, journal, publication_year, "
                    "is_oa, abstract_available, fulltext_available, metadata_json, abstract_hash, "
                    "fulltext_hash, fetched_at) "
                    "VALUES (:source, NULL, :pmcid, :doi, :norm_doi, :title, :journal, :year, "
                    ":is_oa, :abs_avail, :ft_avail, CAST(:meta AS jsonb), :abs_hash, :ft_hash, "
                    "CASE WHEN :fetched THEN now() ELSE NULL END) "
                    "ON CONFLICT (normalized_doi) WHERE normalized_doi IS NOT NULL AND normalized_doi <> '' "
                    "DO UPDATE SET pmid=COALESCE(EXCLUDED.pmid, paper_sources.pmid), "
                    "doi=EXCLUDED.doi, title=EXCLUDED.title, journal=EXCLUDED.journal, "
                    "publication_year=EXCLUDED.publication_year, is_oa=EXCLUDED.is_oa, "
                    "abstract_available=EXCLUDED.abstract_available, fulltext_available=EXCLUDED.fulltext_available, "
                    "abstract_hash=COALESCE(EXCLUDED.abstract_hash, paper_sources.abstract_hash), "
                    "fulltext_hash=COALESCE(EXCLUDED.fulltext_hash, paper_sources.fulltext_hash), "
                    "fetched_at=CASE WHEN :fetched THEN now() ELSE paper_sources.fetched_at END, "
                    "updated_at=now() "
                    "RETURNING id"
                ),
                {
                    "source": paper.get("source") or "europepmc",
                    "pmcid": (paper.get("pmcid") or "").strip() or None,
                    "doi": doi or None,
                    "norm_doi": norm_doi,
                    "title": paper.get("title") or None,
                    "journal": paper.get("journal") or None,
                    "year": year,
                    "is_oa": bool(paper.get("is_open_access", False)),
                    "abs_avail": bool(abstract),
                    "ft_avail": bool(fulltext),
                    "meta": metadata_json,
                    "abs_hash": abstract_hash,
                    "ft_hash": fulltext_hash,
                    "fetched": fetched_at,
                },
            )
        ).scalar_one()
    if row_id is None:
        raise ValueError("paper has neither PMID nor DOI; cannot persist paper source")
    row = await session.get(PaperSource, row_id)
    if row is None:
        raise ValueError("paper source persistence failed")
    return row


def parse_fulltext_paragraphs(
    fulltext: str, *, source_scope: str = "fulltext"
) -> list[dict]:
    """Split full text into structured paragraphs (section-aware, best effort)."""
    paragraphs: list[dict] = []
    text_value = (fulltext or "").strip()
    if not text_value:
        return paragraphs
    # Simple section detection: lines that look like headings (short, no trailing period).
    lines = text_value.split("\n")
    current_section = ""
    buffer: list[str] = []
    char_offset = 0

    def flush() -> None:
        nonlocal buffer, char_offset
        paragraph_text = " ".join(p.strip() for p in buffer if p.strip()).strip()
        buffer = []
        if not paragraph_text:
            return
        idx = len(paragraphs)
        para_id = f"{current_section.lower().replace(' ', '_')}_p{idx + 1:03d}" if current_section else f"fulltext_p{idx + 1:03d}"
        paragraphs.append(
            {
                "source_scope": source_scope,
                "section_title": current_section or None,
                "paragraph_id": para_id,
                "paragraph_index": idx,
                "passage_text": paragraph_text,
                "text_hash": passage_hash(paragraph_text),
                "locator": f"{current_section.lower().replace(' ', '_')}:paragraph:{idx}" if current_section else f"paragraph:{idx}",
                "char_start": None,
                "char_end": None,
            }
        )

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if len(line) <= 80 and not line.endswith((".", ":", ";", "?", "!")) and len(line.split()) <= 6:
            flush()
            current_section = line
            continue
        buffer.append(line)
    flush()
    return paragraphs


async def ensure_paper_passages(
    session: AsyncSession,
    paper_id: uuid.UUID,
    paragraphs: list[dict],
) -> list[dict]:
    """Persist structured paragraphs (idempotent per paper_id+paragraph_id)."""
    saved: list[dict] = []
    for para in paragraphs:
        para_id = para.get("paragraph_id")
        if not para_id:
            continue
        existing = (
            await session.execute(
                select(PaperPassage).where(
                    PaperPassage.paper_id == paper_id,
                    PaperPassage.paragraph_id == para_id,
                )
            )
        ).scalars().first()
        if existing is not None:
            saved.append(
                {
                    "id": existing.id,
                    "paragraph_id": existing.paragraph_id,
                    "section_title": existing.section_title,
                    "paragraph_index": existing.paragraph_index,
                    "passage_text": existing.passage_text,
                    "source_scope": existing.source_scope,
                    "locator": existing.locator,
                }
            )
            continue
        row = PaperPassage(
            paper_id=paper_id,
            source_scope=para.get("source_scope") or "fulltext",
            section_title=para.get("section_title"),
            paragraph_id=para_id,
            paragraph_index=para.get("paragraph_index"),
            passage_text=para["passage_text"],
            text_hash=para.get("text_hash") or passage_hash(para["passage_text"]),
            locator=para.get("locator"),
            char_start=para.get("char_start"),
            char_end=para.get("char_end"),
        )
        session.add(row)
        await session.flush()
        saved.append(
            {
                "id": row.id,
                "paragraph_id": row.paragraph_id,
                "section_title": row.section_title,
                "paragraph_index": row.paragraph_index,
                "passage_text": row.passage_text,
                "source_scope": row.source_scope,
                "locator": row.locator,
            }
        )
    return saved


async def recall_candidate_passages(
    session: AsyncSession,
    paper_id: uuid.UUID,
    term: str,
    limit: int = 30,
    window: int = 1,
) -> list[dict]:
    """V1 recall: term-hit ranking over structured paragraphs (no LLM/embedding)."""
    rows = (
        await session.execute(
            select(PaperPassage)
            .where(PaperPassage.paper_id == paper_id)
            .order_by(PaperPassage.paragraph_index)
        )
    ).scalars().all()
    tokens = [t for t in re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", term or "") if len(t) > 1]
    scored: list[tuple[int, PaperPassage]] = []
    for idx, row in enumerate(rows):
        text_l = row.passage_text.lower()
        score = sum(1 for t in tokens if t.lower() in text_l)
        scored.append((score, idx, row))
    scored.sort(key=lambda x: (-x[0], x[1]))
    candidates = [r[2] for r in scored]
    if not candidates:
        return []
    # Keep ±window neighbors for context.
    indexed = {r[1]: r[2] for r in scored}
    best_idx = scored[0][1]
    selected_ids: list[uuid.UUID] = []
    # Best-hit paragraph first, then its ±window context, then remaining hits.
    selected_ids.append(indexed[best_idx].id)
    for delta in range(-window, window + 1):
        if delta == 0:
            continue
        row = indexed.get(best_idx + delta)
        if row is not None and row.id not in selected_ids:
            selected_ids.append(row.id)
    for _, idx, row in scored[1:]:
        if len(selected_ids) >= limit:
            break
        if row.id not in selected_ids:
            selected_ids.append(row.id)
    by_id = {r.id: r for r in rows}
    return [
        {
            "id": str(pid),
            "paragraph_id": by_id[pid].paragraph_id,
            "section_title": by_id[pid].section_title,
            "paragraph_index": by_id[pid].paragraph_index,
            "passage_text": by_id[pid].passage_text,
            "source_scope": by_id[pid].source_scope,
            "locator": by_id[pid].locator,
        }
        for pid in selected_ids
        if pid in by_id
    ]


async def load_paper_passages(session: AsyncSession, paper_id: uuid.UUID) -> list[dict]:
    """Load all structured paragraphs of a paper (ordered by index)."""
    rows = (
        await session.execute(
            select(PaperPassage)
            .where(PaperPassage.paper_id == paper_id)
            .order_by(PaperPassage.paragraph_index)
        )
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "paragraph_id": r.paragraph_id,
            "section_title": r.section_title,
            "section_title_raw": None,
            "paragraph_index": r.paragraph_index,
            "passage_text": r.passage_text,
            "source_scope": r.source_scope,
            "locator": r.locator,
            "char_start": r.char_start,
            "char_end": r.char_end,
        }
        for r in rows
    ]


def _name_parts(target_type: str, row) -> list[str]:
    parts: list[str] = []
    if target_type in ("projection_function", "region_function"):
        parts.append(str(getattr(row, "function_term", "") or ""))
    elif target_type == "circuit_function":
        parts.append(str(getattr(row, "function_term_en", "") or getattr(row, "function_term_cn", "") or ""))
    elif target_type in ("projection", "connection"):
        parts.append(str(getattr(row, "source_region_name_en", "") or ""))
        parts.append(str(getattr(row, "target_region_name_en", "") or ""))
        parts.append(str(getattr(row, "connection_type", "") or ""))
    elif target_type == "circuit":
        parts.append(str(getattr(row, "circuit_name", "") or ""))
        parts.append(str(getattr(row, "circuit_type", "") or ""))
    elif target_type == "circuit_step":
        parts.append(str(getattr(row, "step_name", "") or ""))
        parts.append(str(getattr(row, "role", "") or ""))
    return [p for p in parts if p and p != "unknown"]


def _term_text_for(row, target_type: str) -> str:
    if target_type == "circuit_function":
        return str(row.function_term_en or row.function_term_cn or "")
    return str(row.function_term or row.function_term_cn or "")


async def search_papers(query: str, limit: int = 5) -> list[dict]:
    papers = await _search(query, limit)
    if not papers:
        tokens = [t for t in re.split(r"[^a-zA-Z0-9]+", query) if t]
        fallback = " AND ".join(tokens)
        if fallback and fallback != query:
            papers = await _search(fallback, limit)
    return papers


async def _search(query: str, limit: int) -> list[dict]:
    async with httpx.AsyncClient(trust_env=False, timeout=SEARCH_TIMEOUT) as client:
        resp = await client.get(
            EUROPE_PMC_SEARCH,
            params={"query": query, "format": "json", "pageSize": limit},
        )
        resp.raise_for_status()
        payload = resp.json()
    results = payload.get("resultList", {}).get("result", [])
    papers = []
    for item in results:
        papers.append(
            {
                "pmid": item.get("pmid") or "",
                "doi": item.get("doi") or "",
                "title": item.get("title") or "",
                "journal": item.get("journalTitle") or "",
                "year": item.get("pubYear") or "",
                "authors": item.get("authorString") or "",
                "abstract": (item.get("abstractText") or "")[:2000],
                "is_open_access": str(item.get("isOpenAccess") or "").lower() == "y",
                "source": "europepmc",
            }
        )
    return papers


async def fetch_fulltext(pmid: str) -> str:
    """Fetch OA full text XML from Europe PMC; returns plain text (limited)."""
    if not pmid:
        return ""
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/MED/{pmid}/fullTextXML"
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=SEARCH_TIMEOUT) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return ""
            text_xml = resp.text
    except httpx.HTTPError:
        return ""
    plain = re.sub(r"<[^>]+>", " ", text_xml)
    plain = re.sub(r"\s+", " ", plain).strip()
    return plain[:8000]


async def verify_paper(pmid: str) -> dict | None:
    if not pmid:
        return None
    async with httpx.AsyncClient(trust_env=False, timeout=SEARCH_TIMEOUT) as client:
        resp = await client.get(
            EUROPE_PMC_SEARCH,
            params={"query": f"EXT_ID:{pmid}", "format": "json", "pageSize": 1},
        )
        resp.raise_for_status()
        payload = resp.json()
    results = payload.get("resultList", {}).get("result", [])
    if not results:
        return None
    item = results[0]
    return {
        "pmid": item.get("pmid") or pmid,
        "doi": item.get("doi") or "",
        "title": item.get("title") or "",
        "journal": item.get("journalTitle") or "",
        "year": item.get("pubYear") or "",
        "authors": item.get("authorString") or "",
        "abstract": (item.get("abstractText") or "")[:2000],
        "source": "europepmc",
    }


async def pack_target_info(
    session: AsyncSession,
    target_type: str,
    target_id: uuid.UUID,
    mode: str = "function",
) -> dict:
    model = TARGET_MODELS.get(target_type)
    if model is None:
        raise ValueError(f"unsupported target_type: {target_type}")
    row = await session.get(model, target_id)
    if row is None:
        raise ValueError("target not found")
    name_parts = _name_parts(target_type, row)
    term_text = name_parts[0] if name_parts else str(getattr(row, "id", ""))
    context_parts = [term_text] if mode == "function" else name_parts[:2]
    if target_type in ("projection", "projection_function", "connection") and getattr(row, "projection_id", None):
        proj = await session.get(MirrorRegionConnection, row.projection_id)
        if proj is not None:
            for region_name in (proj.source_region_name_en, proj.target_region_name_en):
                name = (region_name or "").strip()
                if name and len(name) <= 40 and not any(
                    token in name.lower() for token in ("layer", "area", "lobule")
                ):
                    context_parts.append(name)
    query = " AND ".join(f'"{p}"' for p in context_parts if p and p != "unknown")
    if not query:
        query = term_text
    return {
        "target_type": target_type,
        "target_id": str(target_id),
        "function_term": term_text,
        "mode": mode,
        "query": query,
        "info": {
            "granularity_level": getattr(row, "granularity_level", None),
            "source_atlas": getattr(row, "source_atlas", None),
            "confidence": float(row.confidence) if getattr(row, "confidence", None) is not None else None,
        },
    }


async def attach_evidence(
    session: AsyncSession,
    *,
    target_type: str,
    target_id: uuid.UUID,
    pmid: str,
    direction: str,
    reviewer_confidence: float,
    passages: list[dict],
    mode: str = "function",
    operator_id: str | None = None,
    verification_status: str = "human_verified",
) -> dict:
    # 1) verify paper metadata
    paper = await verify_paper(pmid)
    if paper is None:
        raise ValueError("paper not found or invalid PMID")
    paper_source = await ensure_paper_source(session, paper)
    paper_id = paper_source.id
    model = TARGET_MODELS.get(target_type)
    if model is None:
        raise ValueError(f"unsupported target_type: {target_type}")
    row = await session.get(model, target_id)
    if row is None:
        raise ValueError("target not found")
    # 2) re-verify passages against source (backend never trusts the client)
    source, source_scope = await _load_source(pmid)
    if not source:
        raise ValueError("no source text available for passage verification")
    verified = _verify_passages(passages, source, source_scope)
    if not verified:
        raise ValueError("no passage could be verified against the original source")
    # Link verified passages to structured paper_passages when available.
    paper_passage_ids: dict[str, uuid.UUID] = {}
    if paper_id is not None:
        hash_rows = (
            await session.execute(
                select(PaperPassage).where(
                    PaperPassage.paper_id == paper_id,
                    PaperPassage.text_hash.in_([p["passage_hash"] for p in verified]),
                )
            )
        ).scalars().all()
        paper_passage_ids = {r.text_hash: r.id for r in hash_rows}
    for p in verified:
        p["paper_passage_id"] = paper_passage_ids.get(p["passage_hash"])
    hashes = [p["passage_hash"] for p in verified]
    duplicate_count = await _count_duplicate_hashes(session, target_type, target_id, hashes)
    if duplicate_count:
        raise ValueError(f"{duplicate_count} duplicate passage(s) already stored for this object")
    # 3) deterministic confidence rule (human_verified only)
    current = float(row.confidence) if getattr(row, "confidence", None) is not None else None
    adjustment = None
    if verification_status == "human_verified":
        adjustment = compute_adjustment(
            direction=direction,
            current_confidence=current,
            reviewer_confidence=reviewer_confidence,
        )
    # 4) write evidence record
    record = MirrorEvidenceRecord(
        evidence_target_type=target_type,
        evidence_target_id=target_id,
        evidence_type="paper_verification",
        evidence_text="",
        evidence_direction=direction,
        evidence_level=next((p.get("evidence_level") for p in verified if p.get("evidence_level")), "indirect"),
        verification_status=verification_status,
        paper_id=paper_id,
        paper_source=paper["source"],
        paper_pmid=paper["pmid"],
        paper_doi=paper["doi"] or None,
        paper_title=paper["title"] or None,
        paper_journal=paper["journal"] or None,
        paper_year=int(paper["year"]) if str(paper["year"]).isdigit() else None,
        suggested_confidence=reviewer_confidence,
        reviewer_confidence=reviewer_confidence,
        confidence_adjustment_status=(
            adjustment.adjustment_status if adjustment else "none"
        ),
        verification_by=operator_id,
        verification_at=func.now() if verification_status == "human_verified" else None,
        citation_json={
            "pmid": paper["pmid"],
            "doi": paper["doi"],
            "title": paper["title"],
            "journal": paper["journal"],
            "year": paper["year"],
            "authors": paper["authors"],
            "mode": mode,
        },
        source_reference_text=(
            f"{paper['authors']} ({paper['year']}). {paper['title']}. {paper['journal']}."
        ),
    )
    session.add(record)
    await session.flush()
    # 5) write passages
    for p in verified:
        session.add(
            MirrorEvidencePassage(
                evidence_id=record.id,
                paper_passage_id=p.get("paper_passage_id"),
                source_scope=p["source_scope"],
                section_title=p.get("section_title"),
                paragraph_index=p.get("paragraph_index"),
                passage_text=p["passage"],
                passage_text_snapshot=p["passage"],
                direction=p["direction"],
                evidence_level=p.get("evidence_level") or "indirect",
                reason=p.get("reason"),
                confidence=p.get("confidence"),
                semantic_confidence=p.get("semantic_confidence") or p.get("confidence"),
                is_selected=True,
                source_locator=p.get("source_locator"),
                passage_hash=p["passage_hash"],
                source_verified=True,
                source_verification_method=p.get("source_verification_method"),
            )
        )
    # 6) confidence adjustment + log
    final_confidence = current
    if adjustment and adjustment.apply:
        before = current
        final_confidence = adjustment.final_confidence
        row.confidence = final_confidence
        session.add(
            ConfidenceAdjustmentLog(
                target_type=target_type,
                target_id=target_id,
                evidence_id=record.id,
                before_confidence=before,
                suggested_confidence=reviewer_confidence,
                reviewer_confidence=reviewer_confidence,
                calculated_confidence=final_confidence,
                after_confidence=final_confidence,
                direction=direction,
                formula_version=adjustment.formula_version,
                status="applied",
                applied_by=operator_id,
                applied_at=func.now(),
            )
        )
    # 7) rebuild evidence_text from valid records
    row.evidence_text = await rebuild_evidence_text(session, target_type, target_id)
    await session.flush()
    # 8) validation-center records + audit (human_verified only)
    if verification_status == "human_verified":
        await _write_audit(
            session,
            action_type="EVIDENCE_ATTACH",
            entity_type="evidence",
            entity_id=record.id,
            before_data={"confidence": current, "evidence_text": getattr(row, "evidence_text", "") or ""},
            after_data={
                "confidence": float(row.confidence) if getattr(row, "confidence", None) is not None else None,
                "direction": direction,
                "reviewer_confidence": reviewer_confidence,
                "passage_count": len(verified),
                "verification_status": record.verification_status,
            },
            operator_id=operator_id,
            reason="paper evidence attached after human review",
        )
        await _write_validation_record(
            session,
            evidence_id=record.id,
            rule_code=(
                "EV_PAPER_EVIDENCE_CONTRADICTORY"
                if direction == "contradicts"
                else "EV_PAPER_EVIDENCE_ATTACHED"
            ),
            target_type=target_type,
            target_id=target_id,
            direction=direction,
            paper_snapshot={
                "pmid": paper["pmid"],
                "doi": paper["doi"],
                "title": paper["title"],
                "journal": paper["journal"],
                "year": paper["year"],
            },
            detail={
                "reviewer_confidence": reviewer_confidence,
                "final_confidence": final_confidence,
                "status": "pending_review" if direction == "contradicts" else "resolved_by_attach",
            },
            created_by=operator_id,
        )
        if adjustment and not adjustment.apply and direction == "contradicts":
            await _write_validation_record(
                session,
                evidence_id=record.id,
                rule_code="EV_CONFIDENCE_ADJUSTMENT_PENDING",
                target_type=target_type,
                target_id=target_id,
                direction=direction,
                paper_snapshot={
                    "pmid": paper["pmid"],
                    "doi": paper["doi"],
                    "title": paper["title"],
                },
                detail={
                    "before_confidence": current,
                    "suggested_confidence": reviewer_confidence,
                    "formula_version": adjustment.formula_version,
                    "status": "pending",
                },
                created_by=operator_id,
            )
    return {
        "evidence_id": str(record.id),
        "target_type": target_type,
        "target_id": str(target_id),
        "confidence": float(row.confidence) if getattr(row, "confidence", None) is not None else None,
        "final_confidence": float(final_confidence) if final_confidence is not None else None,
        "verification_status": record.verification_status,
        "confidence_adjustment_status": record.confidence_adjustment_status,
        "passage_count": len(verified),
        "paper": {
            "pmid": paper["pmid"],
            "doi": paper["doi"],
            "title": paper["title"],
            "links": {
                "pubmed": f"https://pubmed.ncbi.nlm.nih.gov/{paper['pmid']}/" if paper["pmid"] else None,
                "doi": f"https://doi.org/{paper['doi']}" if paper["doi"] else None,
            },
        },
    }


async def _load_source(pmid: str) -> tuple[str, str]:
    paper = await verify_paper(pmid)
    abstract = (paper or {}).get("abstract") or ""
    fulltext = await fetch_fulltext(pmid)
    if fulltext.strip():
        return fulltext.strip(), "fulltext"
    if abstract.strip():
        return abstract.strip(), "abstract"
    return "", "none"


def _verify_passages(passages: list[dict], source: str, source_scope: str) -> list[dict]:
    verified = []
    for p in passages:
        ok, method, para_idx, locator = verify_and_locate_passage(
            p.get("passage") or "", source, source_scope
        )
        if not ok:
            continue
        item = dict(p)
        item["source_verified"] = True
        item["source_verification_method"] = method
        item["source_scope"] = source_scope
        item["paragraph_index"] = para_idx
        item["source_locator"] = locator
        item["passage_hash"] = passage_hash(item["passage"])
        verified.append(item)
    return verified


async def _count_duplicate_hashes(
    session: AsyncSession, target_type: str, target_id: uuid.UUID, hashes: list[str]
) -> int:
    if not hashes:
        return 0
    rows = (
        await session.execute(
            text(
                "SELECT COUNT(*) FROM mirror_evidence_passages p "
                "JOIN mirror_evidence_records e ON e.id = p.evidence_id "
                "WHERE e.evidence_target_type = :tt AND e.evidence_target_id = :tid "
                "AND p.passage_hash = ANY(:hashes)"
            ),
            {"tt": target_type, "tid": target_id, "hashes": hashes},
        )
    ).scalar_one()
    return int(rows)


async def attach_preview(
    session: AsyncSession,
    *,
    target_type: str,
    target_id: uuid.UUID,
    pmid: str,
    direction: str,
    reviewer_confidence: float,
    passages: list[dict],
) -> dict:
    paper = await verify_paper(pmid)
    block_reasons = []
    if paper is None:
        raise ValueError("paper not found or invalid PMID")
    model = TARGET_MODELS.get(target_type)
    row = await session.get(model, target_id) if model else None
    if row is None:
        raise ValueError("target not found")
    source, source_scope = await _load_source(pmid)
    verified = _verify_passages(passages, source, source_scope) if source else []
    duplicate_count = (
        await _count_duplicate_hashes(
            session, target_type, target_id, [p["passage_hash"] for p in verified]
        )
        if verified
        else 0
    )
    current = float(row.confidence) if getattr(row, "confidence", None) is not None else None
    adjustment = compute_adjustment(
        direction=direction, current_confidence=current, reviewer_confidence=reviewer_confidence
    )
    cap = SUPPORT_CAP if direction == "supports" else (PARTIAL_CAP if direction == "partial" else None)
    if not source:
        block_reasons.append("no source text available")
    if not verified:
        block_reasons.append("no passage could be verified against the original source")
    if duplicate_count:
        block_reasons.append(f"{duplicate_count} duplicate passage(s)")
    if direction == "not_found":
        block_reasons.append("not_found cannot be stored as paper evidence")
    selected = [p["passage"] for p in verified]
    line = (
        f"[论文证据:{'?'}] {paper.get('title') or ''} | {paper.get('pmid') or ''} | "
        f"{paper.get('doi') or ''} | {direction} | {(selected[0] if selected else '')[:200]}"
    )
    return {
        "target_type": target_type,
        "target_id": str(target_id),
        "current_confidence": current,
        "direction": direction,
        "reviewer_confidence": reviewer_confidence,
        "final_confidence": adjustment.final_confidence if adjustment.apply else current,
        "cap": cap,
        "selected_passage_count": len(selected),
        "duplicate_passage_count": duplicate_count,
        "evidence_text_preview": line,
        "allow": len(block_reasons) == 0,
        "block_reasons": block_reasons,
    }


async def rebuild_evidence_text(
    session: AsyncSession, target_type: str, target_id: uuid.UUID
) -> str:
    records = (
        await session.execute(
            select(MirrorEvidenceRecord)
            .where(
                MirrorEvidenceRecord.evidence_target_type == target_type,
                MirrorEvidenceRecord.evidence_target_id == target_id,
                MirrorEvidenceRecord.evidence_type == "paper_verification",
                MirrorEvidenceRecord.verification_status.in_(
                    ("human_verified", "ai_extracted")
                ),
            )
            .order_by(MirrorEvidenceRecord.created_at.desc())
        )
    ).scalars().all()
    lines = []
    for record in records:
        passage = (
            await session.execute(
                select(MirrorEvidencePassage)
                .where(
                    MirrorEvidencePassage.evidence_id == record.id,
                    MirrorEvidencePassage.is_selected.is_(True),
                )
                .order_by(MirrorEvidencePassage.created_at)
                .limit(1)
            )
        ).scalars().first()
        snippet = (passage.passage_text if passage else "")[:500]
        lines.append(
            f"[论文证据:{record.id}] {record.paper_title or ''} | {record.paper_pmid or ''} | "
            f"{record.paper_doi or ''} | {record.evidence_direction or ''} | {snippet}"
        )
    return "\n".join(lines)


async def rollback_evidence(
    session: AsyncSession,
    evidence_id: uuid.UUID,
    *,
    reason: str,
    operator_id: str | None = None,
) -> dict:
    record = await session.get(MirrorEvidenceRecord, evidence_id)
    if record is None:
        raise ValueError("evidence not found")
    if record.verification_status == "invalidated":
        return {"evidence_id": str(evidence_id), "status": "already_invalidated", "changed": False}
    record.verification_status = "invalidated"
    record.verification_by = operator_id
    record.invalidated_by = operator_id
    record.invalidated_at = func.now()
    record.invalidation_reason = reason
    log = (
        await session.execute(
            select(ConfidenceAdjustmentLog).where(
                ConfidenceAdjustmentLog.evidence_id == evidence_id,
                ConfidenceAdjustmentLog.status == "applied",
            )
        )
    ).scalars().first()
    target_type = record.evidence_target_type
    target_id = record.evidence_target_id
    if log is not None:
        log.status = "rolled_back"
        log.rolled_back_by = operator_id
        log.rolled_back_at = func.now()
        log.rollback_reason = reason
    # recompute confidence from other valid applied logs
    model = TARGET_MODELS.get(target_type)
    row = await session.get(model, target_id) if model else None
    if row is not None:
        remaining = (
            await session.execute(
                select(ConfidenceAdjustmentLog)
                .where(
                    ConfidenceAdjustmentLog.target_type == target_type,
                    ConfidenceAdjustmentLog.target_id == target_id,
                    ConfidenceAdjustmentLog.status == "applied",
                )
                .order_by(ConfidenceAdjustmentLog.applied_at.desc())
            )
        ).scalars().all()
        candidates = [float(x.after_confidence) for x in remaining if x.after_confidence is not None]
        if log is not None and log.before_confidence is not None:
            candidates.append(float(log.before_confidence))
        row.confidence = max(candidates) if candidates else None
        row.evidence_text = await rebuild_evidence_text(session, target_type, target_id)
    await session.flush()
    await _write_audit(
        session,
        action_type="EVIDENCE_ROLLBACK",
        entity_type="evidence",
        entity_id=evidence_id,
        before_data={
            "status": "human_verified" if log is not None else record.verification_status,
            "confidence": float(row.confidence) if row is not None and getattr(row, "confidence", None) is not None else None,
        },
        after_data={"status": "invalidated", "rollback_reason": reason},
        operator_id=operator_id,
        reason=reason,
    )
    await _write_validation_record(
        session,
        evidence_id=evidence_id,
        rule_code="EV_PAPER_EVIDENCE_INVALIDATED",
        target_type=target_type,
        target_id=target_id,
        direction=record.evidence_direction,
        paper_snapshot={
            "pmid": record.paper_pmid,
            "doi": record.paper_doi,
            "title": record.paper_title,
            "journal": record.paper_journal,
            "year": record.paper_year,
        },
        detail={"reason": reason, "confidence": float(row.confidence) if row is not None and getattr(row, "confidence", None) is not None else None},
        created_by=operator_id,
    )
    return {
        "evidence_id": str(evidence_id),
        "status": "invalidated",
        "changed": True,
        "confidence": float(row.confidence) if row is not None and getattr(row, "confidence", None) is not None else None,
    }


async def list_paper_evidence(
    session: AsyncSession,
    *,
    target_type: str,
    target_id: uuid.UUID,
    limit: int = 20,
) -> dict:
    rows = (
        await session.execute(
            select(MirrorEvidenceRecord)
            .where(
                MirrorEvidenceRecord.evidence_target_type == target_type,
                MirrorEvidenceRecord.evidence_target_id == target_id,
                MirrorEvidenceRecord.evidence_type == "paper_verification",
            )
            .order_by(MirrorEvidenceRecord.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    passages_by_evidence: dict[uuid.UUID, list[MirrorEvidencePassage]] = {}
    if rows:
        evidence_ids = [r.id for r in rows]
        passage_rows = (
            await session.execute(
                select(MirrorEvidencePassage)
                .where(MirrorEvidencePassage.evidence_id.in_(evidence_ids))
                .order_by(MirrorEvidencePassage.created_at)
            )
        ).scalars().all()
        for p in passage_rows:
            passages_by_evidence.setdefault(p.evidence_id, []).append(p)
    return {
        "items": [
            {
                "evidence_id": str(r.id),
                "evidence_text": r.evidence_text,
                "direction": r.evidence_direction,
                "evidence_level": r.evidence_level,
                "verification_status": r.verification_status,
                "paper_id": str(r.paper_id) if r.paper_id else None,
                "pmid": r.paper_pmid,
                "doi": r.paper_doi,
                "title": r.paper_title,
                "journal": r.paper_journal,
                "year": r.paper_year,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "verification_by": r.verification_by,
                "verification_at": r.verification_at.isoformat() if r.verification_at else None,
                "suggested_confidence": (
                    float(r.suggested_confidence) if r.suggested_confidence is not None else None
                ),
                "reviewer_confidence": (
                    float(r.reviewer_confidence) if r.reviewer_confidence is not None else None
                ),
                "confidence_adjustment_status": r.confidence_adjustment_status,
                "invalidated_by": r.invalidated_by,
                "invalidated_at": r.invalidated_at.isoformat() if r.invalidated_at else None,
                "invalidation_reason": r.invalidation_reason,
                "passage_count": len(
                    [p for p in passages_by_evidence.get(r.id, []) if p.is_selected]
                ),
                "links": {
                    "pubmed": f"https://pubmed.ncbi.nlm.nih.gov/{r.paper_pmid}/" if r.paper_pmid else None,
                    "doi": f"https://doi.org/{r.paper_doi}" if r.paper_doi else None,
                },
                "passages": [
                    {
                        "id": str(p.id),
                        "source_scope": p.source_scope,
                        "section_title": p.section_title,
                        "paragraph_index": p.paragraph_index,
                        "passage": p.passage_text,
                        "translation_zh": p.translation_zh,
                        "direction": p.direction,
                        "reason": p.reason,
                        "confidence": float(p.confidence) if p.confidence is not None else None,
                        "source_locator": p.source_locator,
                        "source_verified": p.source_verified,
                        "source_verification_method": p.source_verification_method,
                        "is_selected": p.is_selected,
                    }
                    for p in passages_by_evidence.get(r.id, [])
                ],
            }
            for r in rows
        ]
    }


def _extract_json_object(text_value: str) -> str:
    """Locate the outermost JSON object in a noisy LLM response."""
    start = text_value.find("{")
    end = text_value.rfind("}")
    if start >= 0 and end > start:
        return text_value[start : end + 1]
    return text_value


def _parse_multi(raw_text: str) -> PaperMultiPassageExtraction:
    text_value = (raw_text or "").strip()
    fence = re.search(r"```(?:json|JSON)?\s*(.*?)```", text_value, re.DOTALL)
    if fence:
        text_value = fence.group(1).strip()
    text_value = _extract_json_object(text_value)
    # JSON does not allow trailing commas; LLM responses often include them.
    text_value = re.sub(r",\s*([}\]])", r"\1", text_value)
    parsed = json.loads(text_value)
    return PaperMultiPassageExtraction.model_validate(parsed)


async def extract_passage(*, term: str, title: str, abstract: str, fulltext: str = "") -> dict:
    cfg = get_settings()
    provider = get_llm_provider("deepseek")
    source = (fulltext or abstract or "").strip()
    source_type = "fulltext" if fulltext.strip() else ("abstract" if abstract.strip() else "none")
    system = "You are a strict JSON API. Reply only with the requested JSON object. Never explain."
    user = (
        f'Find all passages in the paper relevant to the neuroscience claim "{term}". '
        "For each relevant passage, output the ORIGINAL passage verbatim (copy exactly from the source; "
        "do NOT summarize, rewrite, or invent sentences). "
        "Return ONLY one raw JSON object. Do NOT use markdown, code fences, bullet lists, or any text "
        "outside the JSON object. Do NOT include trailing commas. "
        'Return JSON exactly like: {"overall_direction": "supports", "paper_relevance": "<one sentence>", '
        '"passages": [{"passage": "<verbatim original>", "direction": "supports", '
        '"reason": "<one sentence>", "confidence": 0.9}]}. '
        f"Paper title: {title}\nSource ({source_type}): {source[:8000]}"
    )
    parsed = None
    parse_status = "provider_error"
    retry_count = 0
    raw_response = ""
    for attempt in range(3):
        retry_count = attempt
        try:
            if attempt == 0:
                resp = await provider.complete_json(
                    model=cfg.ontology_residual_model,
                    system_prompt=system,
                    user_prompt=user,
                    temperature=0.1,
                    max_tokens=cfg.ontology_residual_max_tokens,
                )
                raw_response = resp.raw_text or ""
                if not getattr(resp, "transport_ok", True):
                    raise httpx.TransportError(
                        getattr(resp, "error", None) or "DeepSeek transport error"
                    )
                if resp.parsed_json is not None:
                    parsed = PaperMultiPassageExtraction.model_validate(resp.parsed_json)
                else:
                    parsed = _parse_multi(raw_response)
            else:
                text_result = await provider.complete_text(
                    model=cfg.ontology_residual_model,
                    system_prompt=system,
                    user_prompt=user + "\n\nIMPORTANT: Respond with ONLY the raw JSON object.",
                    temperature=0.2,
                    max_tokens=cfg.ontology_residual_max_tokens,
                    json_mode=False,
                )
                raw_response = text_result.raw_text or ""
                if not getattr(text_result, "transport_ok", True):
                    raise httpx.TransportError(
                        getattr(text_result, "error", None) or "DeepSeek transport error"
                    )
                parsed = _parse_multi(raw_response)
            parse_status = "ok"
            break
        except httpx.HTTPError:
            parse_status = "network_error"
            if attempt < 2:
                await asyncio.sleep(cfg.ontology_residual_backoff_seconds)
        except (ValidationError, ValueError, json.JSONDecodeError):
            parse_status = "parse_error"
            if attempt < 2:
                await asyncio.sleep(cfg.ontology_residual_backoff_seconds)
    if parsed is None:
        hint = ""
        if parse_status == "parse_error" and raw_response:
            hint = f" raw_preview={raw_response[:200]!r}"
        raise ValueError(
            f"passage extraction failed: {parse_status} after {retry_count + 1} attempt(s){hint}"
        )
    passages = []
    for item in parsed.passages:
        verified, method, para_idx, locator = verify_and_locate_passage(
            item.passage, source, source_type
        )
        passages.append(
            {
                "source_scope": source_type,
                "section_title": None,
                "paragraph_index": para_idx,
                "passage": item.passage,
                "direction": item.direction,
                "reason": item.reason,
                "confidence": item.confidence,
                "source_locator": locator,
                "source_verified": verified,
                "passage_hash": passage_hash(item.passage),
            }
        )
    return {
        "overall_direction": parsed.overall_direction,
        "paper_relevance": parsed.paper_relevance,
        "source_type": source_type,
        "passages": passages,
        "parse_status": parse_status,
        "retry_count": retry_count,
        "raw_response": raw_response[:1000],
    }


def _verify_extraction_passages(
    passages: list[dict],
    paragraph_map: dict[str, dict],
) -> list[dict]:
    """Strict backend verification: paragraph_id must exist and passage must match.

    Only exact / normalized whitespace / normalized Unicode punctuation pass.
    If paragraph_id is missing or unknown → source_verified=false (no fallback).
    """
    verified_out: list[dict] = []
    for item in passages:
        para_id = (item.get("paragraph_id") or "").strip()
        candidate = paragraph_map.get(para_id)
        source_text = (candidate or {}).get("passage_text") or ""
        ok, method = (
            verify_passage_against_source(item.get("passage") or "", source_text)
            if source_text
            else (False, None)
        )
        verified_out.append(
            {
                **item,
                "source_scope": (candidate or {}).get("source_scope") or "fulltext",
                "section_title": (candidate or {}).get("section_title") or item.get("section"),
                "paragraph_index": (candidate or {}).get("paragraph_index"),
                "source_locator": (candidate or {}).get("locator") if ok else None,
                "source_verified": ok,
                "source_verification_method": method if ok else None,
                "passage_hash": passage_hash(item.get("passage") or ""),
            }
        )
    return verified_out


def _dedupe_extraction_passages(passages: list[dict]) -> list[dict]:
    """Drop duplicate paragraphs / overlapping same-text passages.

    * same paragraph_id + same normalized text → keep once;
    * same paragraph + different direction (support vs contradict) → keep both;
    * overlapping same-text candidates → keep the longer, more complete one.
    """
    groups: dict[str, dict[str, dict]] = {}
    for p in passages:
        para_key = p.get("paragraph_id") or ""
        dir_key = p.get("direction") or "unknown"
        existing = groups.setdefault(para_key, {}).get(dir_key)
        if existing is None:
            groups[para_key][dir_key] = p
            continue
        # same paragraph + same direction: keep the longer, more complete one
        if len(p.get("passage") or "") > len(existing.get("passage") or ""):
            groups[para_key][dir_key] = p
    return [p for by_dir in groups.values() for p in by_dir.values()]


def _combine_overall_direction(parsed: PaperMultiPassageExtraction) -> str:
    directions = {p.direction for p in parsed.passages}
    if not directions:
        return "not_found"
    if "supports" in directions and "contradicts" in directions:
        return "partial"
    if "contradicts" in directions:
        return "contradicts"
    if "supports" in directions:
        return "supports"
    if "partial" in directions:
        return "partial"
    return parsed.overall_direction


async def extract_passage_from_paper(
    *,
    claim: dict,
    title: str,
    windows: list[dict],
    max_input_chars: int = 24000,
) -> dict:
    """DeepSeek judgment over recalled paragraph windows (paragraph_id-aware)."""
    cfg = get_settings()
    provider = get_llm_provider("deepseek")
    blocks: list[str] = []
    truncated = False
    budget = max_input_chars
    for w in windows:
        focus = w.get("focus_paragraph_id") or ""
        section = w.get("section_title") or ""
        focus_idx = w.get("paragraph_index")
        block = f"[focus:{focus}]" + (f" ({section})" if section else "")
        for p in w.get("context") or []:
            if p.get("paragraph_id") == focus:
                role_label = "current"
            elif focus_idx is not None and (p.get("paragraph_index") or 0) < focus_idx:
                role_label = "previous"
            else:
                role_label = "next"
            block += f"\n<{role_label} id={p.get('paragraph_id')}>\n{p.get('passage_text') or ''}\n</{role_label}>"
        if budget - len(block) <= 0:
            truncated = True
            break
        blocks.append(block)
        budget -= len(block)
    joined = "\n\n".join(blocks)
    system = (
        "You are a strict JSON API for neuroscience evidence judgment. "
        "Reply only with the requested JSON object. Never explain."
    )
    user = (
        f'Knowledge claim to verify: "{claim.get("claim_text") or claim.get("function_term") or ""}"\n'
        "Structured claim (relation direction matters): "
        f"{claim.get('structured_claim') or claim.get('claim_text') or ''}\n"
        "Rules:\n"
        "1. Use ONLY the given paragraphs; never add model knowledge.\n"
        "2. Output passages verbatim (copy exactly); never rewrite or invent sentences.\n"
        "3. Reuse the exact paragraph ids from the <id=...> markers; never invent ids.\n"
        "4. If no paragraph truly supports or contradicts the claim, return not_found with passages=[] (do NOT fabricate weak evidence).\n"
        "5. Search for BOTH supporting and contradicting evidence; you may return 1-8 passages.\n"
        "6. Distinguish experimental Results (direct) from author interpretation (interpretive) and background (background).\n"
        "7. Keyword co-occurrence is NOT evidence: 'A and B both participate in X' does not mean 'A projects to B'.\n"
        "8. Direction matters: 'B -> A' does not support 'A -> B'; functional connectivity is not an anatomical projection.\n"
        "9. evidence_level: direct (experiment proves the claim/core relation), indirect (needs reasonable inference), "
        "interpretive (author explanation in Discussion/Conclusion), background (Introduction/review-like).\n"
        "10. overall_direction must reflect ALL returned passages (support+contradict -> partial).\n"
        "Return ONLY one raw JSON object (no markdown, no code fences, no trailing commas):\n"
        '{"overall_direction": "supports", "paper_relevance": 0.9, '
        '"assessment": "<one or two sentences summarizing the judgment>", '
        '"passages": [{"paragraph_id": "<id>", "section": "<section>", "passage": "<verbatim>", '
        '"direction": "supports", "evidence_level": "direct|indirect|interpretive|background", '
        '"reason": "<one sentence>", "confidence": 0.9, "semantic_confidence": 0.9}]}\n'
        f"Paper title: {title}\nCandidate paragraph windows:\n{joined}"
    )
    parsed = None
    parse_status = "provider_error"
    retry_count = 0
    raw_response = ""
    for attempt in range(3):
        retry_count = attempt
        try:
            if attempt == 0:
                resp = await provider.complete_json(
                    model=cfg.ontology_residual_model,
                    system_prompt=system,
                    user_prompt=user,
                    temperature=0.1,
                    max_tokens=cfg.ontology_residual_max_tokens,
                )
                raw_response = resp.raw_text or ""
                if not getattr(resp, "transport_ok", True):
                    raise httpx.TransportError(getattr(resp, "error", None) or "DeepSeek transport error")
                if resp.parsed_json is not None:
                    parsed = PaperMultiPassageExtraction.model_validate(resp.parsed_json)
                else:
                    parsed = _parse_multi(raw_response)
            else:
                text_result = await provider.complete_text(
                    model=cfg.ontology_residual_model,
                    system_prompt=system,
                    user_prompt=user + "\n\nIMPORTANT: Respond with ONLY the raw JSON object.",
                    temperature=0.2,
                    max_tokens=cfg.ontology_residual_max_tokens,
                    json_mode=False,
                )
                raw_response = text_result.raw_text or ""
                if not getattr(text_result, "transport_ok", True):
                    raise httpx.TransportError(getattr(text_result, "error", None) or "DeepSeek transport error")
                parsed = _parse_multi(raw_response)
            parse_status = "ok"
            break
        except httpx.HTTPError:
            parse_status = "network_error"
            if attempt < 2:
                await asyncio.sleep(cfg.ontology_residual_backoff_seconds)
        except (ValidationError, ValueError, json.JSONDecodeError):
            parse_status = "parse_error"
            if attempt < 2:
                await asyncio.sleep(cfg.ontology_residual_backoff_seconds)
    if parsed is None:
        hint = ""
        if parse_status == "parse_error" and raw_response:
            hint = f" raw_preview={raw_response[:200]!r}"
        raise ValueError(
            f"passage extraction failed: {parse_status} after {retry_count + 1} attempt(s){hint}"
        )
    paragraph_map: dict[str, dict] = {}
    for w in windows:
        for p in w.get("context") or []:
            if p.get("paragraph_id"):
                paragraph_map.setdefault(p["paragraph_id"], p)
    raw_items = [
        {
            "paragraph_id": item.paragraph_id,
            "section": item.section,
            "passage": item.passage,
            "direction": item.direction,
            "evidence_level": item.evidence_level,
            "reason": item.reason,
            "confidence": item.confidence,
            "semantic_confidence": item.semantic_confidence or item.confidence,
        }
        for item in parsed.passages
    ]
    verified_passages = _verify_extraction_passages(raw_items, paragraph_map)
    deduped = _dedupe_extraction_passages(verified_passages)
    overall = _combine_overall_direction(parsed)
    source_type = (
        "fulltext"
        if any((p.get("source_scope") == "fulltext") for p in paragraph_map.values())
        else "abstract"
    )
    return {
        "overall_direction": overall,
        "paper_relevance": parsed.paper_relevance,
        "assessment": parsed.assessment,
        "source_type": source_type,
        "passages": deduped,
        "retrieval_summary": {
            "candidate_windows": len(windows),
            "input_truncated": truncated,
            "verified_count": sum(1 for p in deduped if p.get("source_verified")),
            "unverified_count": sum(1 for p in deduped if not p.get("source_verified")),
        },
        "parse_status": parse_status,
        "retry_count": retry_count,
        "raw_response": raw_response[:1000],
    }


async def translate_text(text: str) -> dict:
    cfg = get_settings()
    provider = get_llm_provider("deepseek")
    system = "You are a professional neuroscience translator. Reply with only the simplified Chinese translation."
    user = f"Translate the following English passage into simplified Chinese:\n\n{text[:3000]}"
    result = await provider.complete_text(
        model=cfg.ontology_residual_model,
        system_prompt=system,
        user_prompt=user,
        temperature=0.1,
        max_tokens=cfg.ontology_residual_max_tokens,
        json_mode=False,
    )
    return {"translated": (result.raw_text or "").strip()}


async def queue_targets(
    session: AsyncSession, target_type: str, scope: str, limit: int
) -> dict:
    ids = await _resolve_scope_ids(session, target_type, scope, limit)
    model = TARGET_MODELS.get(target_type)
    items = []
    for target_id in ids:
        row = await session.get(model, uuid.UUID(target_id))
        label = _name_parts(target_type, row)[0] if row is not None else target_id
        items.append(
            {
                "target_type": target_type,
                "target_id": target_id,
                "label": label,
                "confidence": float(row.confidence) if row is not None and getattr(row, "confidence", None) is not None else None,
            }
        )
    return {"items": items}


# ---- Batch evidence tasks ----


async def _resolve_scope_ids(
    session: AsyncSession, target_type: str, scope: str, limit: int
) -> list[str]:
    table = TARGET_MODELS.get(target_type)
    if table is None:
        raise ValueError(f"unsupported target_type: {target_type}")
    table_name = table.__tablename__
    where = ""
    if scope == "low_confidence":
        where = "WHERE confidence < 0.5"
    elif scope == "all_ungrounded":
        where = "WHERE term_id IS NULL"
    rows = (
        await session.execute(
            text(f"SELECT id::text FROM {table_name} {where} ORDER BY created_at DESC LIMIT :lim"),
            {"lim": limit},
        )
    ).all()
    return [str(r[0]) for r in rows]


async def create_batch_task(
    session: AsyncSession,
    *,
    target_type: str,
    scope: str,
    mode: str,
    max_papers_per_object: int,
    created_by: str | None = None,
    limit: int = 500,
) -> dict:
    ids = await _resolve_scope_ids(session, target_type, scope, limit)
    task_id = (
        await session.execute(
            text(
                "INSERT INTO paper_evidence_tasks "
                "(target_type, scope, mode, max_papers_per_object, status, created_by) "
                "VALUES (:tt, :scope, :mode, :maxp, 'pending', :cb) RETURNING id::text"
            ),
            {"tt": target_type, "scope": scope, "mode": mode, "maxp": max_papers_per_object, "cb": created_by},
        )
    ).scalar_one()
    for target_id in ids:
        await session.execute(
            text(
                "INSERT INTO paper_evidence_task_items (task_id, target_type, target_id) "
                "VALUES (:tid, :tt, :oid)"
            ),
            {"tid": task_id, "tt": target_type, "oid": target_id},
        )
    await session.commit()
    return {"task_id": task_id, "target_count": len(ids)}


async def run_batch_step(
    session: AsyncSession, task_id: str, limit: int = 20
) -> dict:
    task = (
        await session.execute(
            text(
                "SELECT target_type, mode, max_papers_per_object FROM paper_evidence_tasks "
                "WHERE id::text = :tid"
            ),
            {"tid": task_id},
        )
    ).first()
    if task is None:
        raise ValueError("task not found")
    target_type, mode, max_papers = task[0], task[1], task[2]
    rows = (
        await session.execute(
            text(
                "SELECT id::text, target_id::text FROM paper_evidence_task_items "
                "WHERE task_id::text = :tid AND status = 'pending' LIMIT :lim"
            ),
            {"tid": task_id, "lim": limit},
        )
    ).all()
    processed = done = failed = evidence_created = 0
    for item_id, target_id in rows:
        processed += 1
        try:
            info = await pack_target_info(
                session, target_type, uuid.UUID(target_id), mode=mode
            )
            papers = await search_papers(info["query"], limit=max_papers)
            if not papers:
                done += 1
                await session.execute(
                    text(
                        "UPDATE paper_evidence_task_items SET status='no_paper', updated_at=now() "
                        "WHERE id::text = :iid"
                    ),
                    {"iid": item_id},
                )
                continue
            paper = papers[0]
            abstract = paper.get("abstract") or ""
            extraction = await extract_passage(
                term=info["function_term"], title=paper.get("title") or "", abstract=abstract
            )
            if extraction["direction"] == "not_found":
                done += 1
                await session.execute(
                    text(
                        "UPDATE paper_evidence_task_items SET status='no_evidence', pmid=:pmid, "
                        "title=:title, abstract=:abstract, passage=:passage, direction=:dir, "
                        "confidence=:conf, updated_at=now() WHERE id::text = :iid"
                    ),
                    {"iid": item_id, "pmid": paper.get("pmid") or "", "title": paper.get("title") or "",
                     "abstract": abstract, "passage": extraction["passage"],
                     "dir": extraction["direction"], "conf": extraction["confidence"]},
                )
                continue
            attached = await attach_evidence(
                session,
                target_type=target_type,
                target_id=uuid.UUID(target_id),
                pmid=paper.get("pmid") or "",
                direction=extraction["direction"],
                reviewer_confidence=extraction["confidence"],
                passages=extraction["passages"],
                mode=mode,
                operator_id="batch",
                verification_status="ai_extracted",
            )
            evidence_created += 1
            done += 1
            await session.execute(
                text(
                    "UPDATE paper_evidence_task_items SET status='done', pmid=:pmid, title=:title, "
                    "abstract=:abstract, passage=:passage, direction=:dir, confidence=:conf, "
                    "evidence_id=:eid, updated_at=now() WHERE id::text = :iid"
                ),
                {"iid": item_id, "pmid": paper.get("pmid") or "", "title": paper.get("title") or "",
                 "abstract": abstract, "passage": extraction["passage"], "dir": extraction["direction"],
                 "conf": extraction["confidence"], "eid": attached["evidence_id"]},
            )
        except Exception as exc:  # noqa: BLE001
            failed += 1
            await session.execute(
                text(
                    "UPDATE paper_evidence_task_items SET status='failed', error_message=:err, "
                    "updated_at=now() WHERE id::text = :iid"
                ),
                {"iid": item_id, "err": str(exc)[:500]},
            )
        await session.commit()
    return {
        "task_id": task_id,
        "processed": processed,
        "done": done,
        "failed": failed,
        "evidence_created": evidence_created,
    }


async def get_batch_task(session: AsyncSession, task_id: str) -> dict:
    task = (
        await session.execute(
            text(
                "SELECT id::text, target_type, scope, mode, max_papers_per_object, status, summary, "
                "created_at, started_at, finished_at, error_message FROM paper_evidence_tasks "
                "WHERE id::text = :tid"
            ),
            {"tid": task_id},
        )
    ).first()
    if task is None:
        raise ValueError("task not found")
    counts = (
        await session.execute(
            text(
                "SELECT status, COUNT(*) FROM paper_evidence_task_items "
                "WHERE task_id::text = :tid GROUP BY 1"
            ),
            {"tid": task_id},
        )
    ).all()
    return {
        "task": {
            "id": task[0],
            "target_type": task[1],
            "scope": task[2],
            "mode": task[3],
            "max_papers_per_object": task[4],
            "status": task[5],
            "summary": task[6],
            "created_at": task[7].isoformat() if task[7] else None,
        },
        "counts": {r[0]: r[1] for r in counts},
    }


async def list_batch_items(
    session: AsyncSession, task_id: str, limit: int = 50, offset: int = 0
) -> dict:
    rows = (
        await session.execute(
            text(
                "SELECT id::text, target_type, target_id::text, status, pmid, title, passage, "
                "direction, confidence, evidence_id::text, error_message, updated_at "
                "FROM paper_evidence_task_items WHERE task_id::text = :tid "
                "ORDER BY updated_at DESC LIMIT :lim OFFSET :off"
            ),
            {"tid": task_id, "lim": limit, "off": offset},
        )
    ).all()
    return {
        "items": [
            {
                "id": r[0],
                "target_type": r[1],
                "target_id": r[2],
                "status": r[3],
                "pmid": r[4],
                "title": r[5],
                "passage": r[6],
                "direction": r[7],
                "confidence": float(r[8]) if r[8] is not None else None,
                "evidence_id": r[9],
                "error_message": r[10],
                "updated_at": r[11].isoformat() if r[11] else None,
            }
            for r in rows
        ]
    }


# ════════════════════════════════════════════════════════════════════════════
# Phase C: batch pre-processing state machine (overrides legacy batch helpers)
# ════════════════════════════════════════════════════════════════════════════

_TASK_STATUS = {"pending", "running", "paused", "completed", "partially_failed", "cancelled", "failed"}
_ITEM_ACTIVE_STATUS = {"pending", "searching", "paper_found", "extracting", "awaiting_review"}


async def _batch_scope_label(session: AsyncSession, target_type: str, target_id: uuid.UUID) -> tuple[str, float | None]:
    model = TARGET_MODELS.get(target_type)
    if model is None:
        return target_id, None
    row = await session.get(model, target_id)
    if row is None:
        return target_id, None
    parts = _name_parts(target_type, row)
    label = " · ".join(parts[:3]) if parts else target_id
    conf = float(row.confidence) if getattr(row, "confidence", None) is not None else None
    return label, conf


async def create_batch_task(
    session: AsyncSession,
    *,
    target_type: str,
    scope: str,
    mode: str,
    max_papers_per_object: int,
    created_by: str | None = None,
    limit: int = 200,
    start_paused: bool = False,
) -> dict:
    """Create a pre-processing task. Never writes formal evidence."""
    if target_type not in TARGET_MODELS:
        raise ValueError(f"unsupported target_type: {target_type}")
    ids = await _resolve_scope_ids(session, target_type, scope, limit)
    if not ids:
        raise ValueError("no targets matched scope")
    # skip targets already covered by an active task item
    busy = set(
        (
            await session.execute(
                text(
                    "SELECT target_id::text FROM paper_evidence_task_items "
                    "WHERE target_type = :tt AND target_id::text = ANY(:ids) "
                    "AND status IN ('pending','searching','paper_found','extracting','awaiting_review')"
                ),
                {"tt": target_type, "ids": ids},
            )
        ).scalars().all()
    )
    fresh_ids = [oid for oid in ids if oid not in busy]
    if not fresh_ids:
        raise ValueError("all matched targets already have an active evidence task")
    labels: list[tuple[str, float | None]] = []
    for oid in fresh_ids:
        labels.append(await _batch_scope_label(session, target_type, uuid.UUID(oid)))
    task_id = (
        await session.execute(
            text(
                "INSERT INTO paper_evidence_tasks "
                "(target_type, scope, mode, max_papers_per_object, status, created_by, total_items, config) "
                "VALUES (:tt, :scope, :mode, :maxp, :status, :cb, :total, CAST(:cfg AS jsonb)) RETURNING id::text"
            ),
            {
                "tt": target_type,
                "scope": scope,
                "mode": mode,
                "maxp": max_papers_per_object,
                "status": "paused" if start_paused else "pending",
                "cb": created_by,
                "total": len(fresh_ids),
                "cfg": json.dumps(
                    {"deepseek_concurrency": DEEPSEEK_CONCURRENCY, "europepmc_concurrency": EUROPE_PMC_CONCURRENCY},
                    ensure_ascii=False,
                ),
            },
        )
    ).scalar_one()
    await session.execute(
        text(
            "INSERT INTO paper_evidence_task_items "
            "(task_id, target_type, target_id, label, current_confidence, status) "
            "VALUES (:tid, :tt, :oid, :label, :conf, 'pending')"
        ),
        [
            {
                "tid": task_id,
                "tt": target_type,
                "oid": uuid.UUID(oid),
                "label": label,
                "conf": conf,
            }
            for oid, (label, conf) in zip(fresh_ids, labels)
        ],
    )
    await session.commit()
    await _write_audit(
        session,
        action_type="EVIDENCE_TASK_CREATE",
        entity_type="evidence_task",
        entity_id=uuid.UUID(task_id),
        after_data={"target_type": target_type, "scope": scope, "mode": mode, "target_count": len(fresh_ids), "skipped_active": len(busy)},
        operator_id=created_by,
        reason="batch evidence pre-processing task created",
    )
    await session.commit()
    return {"task_id": task_id, "target_count": len(fresh_ids), "skipped_active_targets": len(busy)}


async def _update_task_totals(session: AsyncSession, task_id: str) -> None:
    counts = (
        await session.execute(
            text(
                "SELECT status, COUNT(*) FROM paper_evidence_task_items "
                "WHERE task_id::text = :tid GROUP BY 1"
            ),
            {"tid": task_id},
        )
    ).all()
    status_map = {r[0]: r[1] for r in counts}
    done = sum(status_map.get(s, 0) for s in ("completed", "skipped", "failed", "cancelled"))
    awaiting = status_map.get("awaiting_review", 0)
    failed = status_map.get("failed", 0)
    await session.execute(
        text(
            "UPDATE paper_evidence_tasks SET processed_items = :done, "
            "awaiting_review_items = :aw, failed_items = :fail, "
            "summary = jsonb_build_object('counts', CAST(:counts AS jsonb)) WHERE id::text = :tid"
        ),
        {
            "tid": task_id,
            "done": done,
            "aw": awaiting,
            "fail": failed,
            "counts": json.dumps(status_map, ensure_ascii=False),
        },
    )


async def _process_batch_item(
    *,
    task_id: str,
    item_id: str,
    target_type: str,
    target_id: str,
    mode: str,
    max_papers: int,
    sem_epmc: asyncio.Semaphore,
    sem_deepseek: asyncio.Semaphore,
) -> None:
    from app.database import AsyncSessionLocal

    if AsyncSessionLocal is None:
        return
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(
                text("UPDATE paper_evidence_task_items SET status='searching', updated_at=now() WHERE id::text=:iid"),
                {"iid": item_id},
            )
            await session.commit()
            async with sem_epmc:
                info = await pack_target_info(session, target_type, uuid.UUID(target_id), mode=mode)
                context = await build_retrieval_context(session, target_type, uuid.UUID(target_id))
                papers = await _search_with_retry(info["query"], limit=max_papers)
            if not papers:
                await session.execute(
                    text(
                        "UPDATE paper_evidence_task_items SET status='skipped', last_error='no_paper', "
                        "paper_json=CAST(:pj AS jsonb), updated_at=now() WHERE id::text=:iid"
                    ),
                    {"iid": item_id, "pj": json.dumps({"papers": [], "reason": "no results from Europe PMC"}, ensure_ascii=False)},
                )
                await session.commit()
                return
            await session.execute(
                text(
                    "UPDATE paper_evidence_task_items SET status='paper_found', "
                    "paper_json=CAST(:pj AS jsonb), updated_at=now() WHERE id::text=:iid"
                ),
                {"iid": item_id, "pj": json.dumps({"papers": papers}, ensure_ascii=False)},
            )
            await session.commit()
            extraction = None
            used_paper = None
            paper_id = None
            for paper in papers[:max_papers]:
                pmid = (paper.get("pmid") or "").strip()
                if not pmid:
                    continue
                used_paper = paper
                async with sem_epmc:
                    verified_meta = await _verify_paper_with_retry(pmid)
                    xml_text = await pfs.fetch_oa_fulltext_xml(pmid=pmid)
                if verified_meta is None:
                    continue
                abstract = (verified_meta.get("abstract") or "").strip()
                paper_source = await ensure_paper_source(
                    session,
                    {**verified_meta, "abstract": abstract, "fulltext": ""},
                )
                paper_id = paper_source.id
                paragraphs: list[dict] = []
                if abstract:
                    paragraphs.append(
                        {
                            "source_scope": "abstract",
                            "section_title": "Abstract",
                            "paragraph_id": "abstract_p001",
                            "paragraph_index": 0,
                            "passage_text": abstract,
                            "text_hash": passage_hash(abstract),
                            "locator": "abstract:paragraph:0",
                        }
                    )
                if xml_text.strip():
                    paragraphs.extend(oa_xml_parser.parse_oa_xml(xml_text))
                await ensure_paper_passages(session, paper_source.id, paragraphs)
                await session.commit()
                all_paragraphs = await load_paper_passages(session, paper_source.id)
                ranked = score_paragraphs(
                    all_paragraphs,
                    source_region=context.get("source_region") or "",
                    target_region=context.get("target_region") or "",
                    source_region_synonyms=context.get("source_region_synonyms") or [],
                    target_region_synonyms=context.get("target_region_synonyms") or [],
                    function_terms=context.get("function_terms") or [],
                    function_synonyms=context.get("function_synonyms") or [],
                    relation_keywords=context.get("relation_keywords") or [],
                )
                windows = build_windows(ranked, all_paragraphs, top_k=20, window=1)
                async with sem_deepseek:
                    extraction = await _extract_from_paper_with_retry(
                        claim=context,
                        title=verified_meta.get("title") or paper.get("title") or "",
                        windows=windows,
                    )
                if any(p["source_verified"] for p in extraction["passages"]):
                    break
            if extraction is None:
                extraction = {"passages": [], "overall_direction": "not_found", "parse_status": "no_candidate", "retry_count": 0, "raw_response": ""}
            verified = [p for p in extraction["passages"] if p["source_verified"]]
            source_text = (used_paper or {}).get("abstract") or ""
            source_hash = hashlib.sha256((source_text or "").encode("utf-8")).hexdigest()[:64]
            status = "awaiting_review" if verified else "skipped"
            last_error = None if verified else "no_verified_passages"
            await session.execute(
                text(
                    "UPDATE paper_evidence_task_items SET status=:st, last_error=:err, "
                    "pmid=:pmid, title=:title, abstract=:abs, direction=:dir, confidence=:conf, "
                    "passages_json=CAST(:pj AS jsonb), raw_response=:raw, source_text_hash=:hash, parse_status=:ps, "
                    "paper_id=:paper_id, retry_count=retry_count+1, updated_at=now() WHERE id::text=:iid"
                ),
                {
                    "iid": item_id,
                    "st": status,
                    "err": last_error,
                    "pmid": (used_paper or {}).get("pmid") or "",
                    "title": (used_paper or {}).get("title") or "",
                    "abs": source_text,
                    "dir": extraction.get("overall_direction") or "not_found",
                    "conf": max((p["confidence"] for p in verified), default=0.0) if verified else None,
                    "pj": json.dumps({"papers": papers, "passages": extraction["passages"]}, ensure_ascii=False),
                    "raw": (extraction.get("raw_response") or "")[:4000],
                    "hash": source_hash,
                    "ps": extraction.get("parse_status") or "ok",
                    "paper_id": paper_id,
                },
            )
            await session.commit()
        except Exception as exc:  # noqa: BLE001
            try:
                await session.execute(
                    text(
                        "UPDATE paper_evidence_task_items SET retry_count=retry_count+1, last_error=:err, "
                        "status=CASE WHEN retry_count >= :maxr THEN 'failed' ELSE 'pending' END, "
                        "updated_at=now() WHERE id::text=:iid"
                    ),
                    {"iid": item_id, "err": str(exc)[:500], "maxr": BATCH_ITEM_RETRIES},
                )
                await session.commit()
            except Exception:  # noqa: BLE001
                await session.rollback()


async def _search_with_retry(query: str, limit: int) -> list[dict]:
    last_exc: Exception | None = None
    for attempt in range(BATCH_ITEM_RETRIES):
        try:
            return await search_papers(query, limit=limit)
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            last_exc = exc
            if attempt < BATCH_ITEM_RETRIES - 1:
                await asyncio.sleep(BATCH_BACKOFF_SECONDS[min(attempt, len(BATCH_BACKOFF_SECONDS) - 1)])
    raise last_exc or RuntimeError("search failed")


async def _extract_with_retry(*, term: str, title: str, abstract: str, fulltext: str) -> dict:
    last_exc: Exception | None = None
    for attempt in range(BATCH_ITEM_RETRIES):
        try:
            return await extract_passage(term=term, title=title, abstract=abstract, fulltext=fulltext)
        except (ValueError, ValidationError, httpx.HTTPError) as exc:
            last_exc = exc
            if attempt < BATCH_ITEM_RETRIES - 1:
                await asyncio.sleep(BATCH_BACKOFF_SECONDS[min(attempt, len(BATCH_BACKOFF_SECONDS) - 1)])
    raise last_exc or RuntimeError("extraction failed")


async def _verify_paper_with_retry(pmid: str) -> dict | None:
    last_exc: Exception | None = None
    for attempt in range(BATCH_ITEM_RETRIES):
        try:
            return await verify_paper(pmid)
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            last_exc = exc
            if attempt < BATCH_ITEM_RETRIES - 1:
                await asyncio.sleep(BATCH_BACKOFF_SECONDS[min(attempt, len(BATCH_BACKOFF_SECONDS) - 1)])
    raise last_exc or RuntimeError("paper verification failed")


async def _extract_from_paper_with_retry(*, claim: dict, title: str, windows: list[dict]) -> dict:
    last_exc: Exception | None = None
    for attempt in range(BATCH_ITEM_RETRIES):
        try:
            return await extract_passage_from_paper(claim=claim, title=title, windows=windows)
        except (ValueError, ValidationError, httpx.HTTPError) as exc:
            last_exc = exc
            if attempt < BATCH_ITEM_RETRIES - 1:
                await asyncio.sleep(BATCH_BACKOFF_SECONDS[min(attempt, len(BATCH_BACKOFF_SECONDS) - 1)])
    raise last_exc or RuntimeError("extraction failed")


async def _run_batch_loop(session: AsyncSession, task_id: str) -> None:
    while True:
        state = (
            await session.execute(
                text("SELECT status FROM paper_evidence_tasks WHERE id::text=:tid"),
                {"tid": task_id},
            )
        ).scalar_one_or_none()
        if state in ("cancelled", "paused"):
            return
        await session.execute(
            text(
                "UPDATE paper_evidence_tasks SET status='running', started_at=COALESCE(started_at, now()) "
                "WHERE id::text=:tid AND status IN ('pending','running')"
            ),
            {"tid": task_id},
        )
        await session.commit()
        task_row = (
            await session.execute(
                text(
                    "SELECT max_papers_per_object FROM paper_evidence_tasks WHERE id::text=:tid"
                ),
                {"tid": task_id},
            )
        ).scalar_one_or_none()
        rows = (
            await session.execute(
                text(
                    "SELECT id::text, target_type, target_id::text FROM paper_evidence_task_items "
                    "WHERE task_id::text=:tid AND status='pending' ORDER BY created_at LIMIT 8"
                ),
                {"tid": task_id},
            )
        ).all()
        if not rows:
            break
        max_papers = task_row or 3
        sem_epmc = asyncio.Semaphore(EUROPE_PMC_CONCURRENCY)
        sem_deepseek = asyncio.Semaphore(DEEPSEEK_CONCURRENCY)
        coros = [
            _process_batch_item(
                task_id=task_id,
                item_id=item_id,
                target_type=tt,
                target_id=oid,
                mode="function",
                max_papers=max_papers,
                sem_epmc=sem_epmc,
                sem_deepseek=sem_deepseek,
            )
            for item_id, tt, oid in rows
        ]
        await asyncio.gather(*coros, return_exceptions=True)
        await _update_task_totals(session, task_id)
        await session.commit()
    await _update_task_totals(session, task_id)
    counts = (
        await session.execute(
            text(
                "SELECT status, COUNT(*) FROM paper_evidence_task_items "
                "WHERE task_id::text=:tid GROUP BY 1"
            ),
            {"tid": task_id},
        )
    ).all()
    status_map = {r[0]: r[1] for r in counts}
    failed = status_map.get("failed", 0)
    terminal_done = sum(status_map.get(s, 0) for s in ("completed", "skipped"))
    if failed and terminal_done:
        final_status = "partially_failed"
    elif failed:
        final_status = "failed"
    else:
        final_status = "completed"
    await session.execute(
        text(
            "UPDATE paper_evidence_tasks SET status=:st, finished_at=now() "
            "WHERE id::text=:tid AND status NOT IN ('cancelled','paused')"
        ),
        {"tid": task_id, "st": final_status},
    )
    await session.commit()


async def execute_paper_evidence_batch_background(task_id: str) -> None:
    """Background entrypoint used by BackgroundTasks; recoverable after restart."""
    from app.database import AsyncSessionLocal

    if AsyncSessionLocal is None:
        return
    try:
        async with AsyncSessionLocal() as session:
            await _run_batch_loop(session, task_id)
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).exception("[paper-evidence-batch] background failure task_id=%s", task_id)


async def recover_interrupted_batch_tasks(session: AsyncSession) -> int:
    """On startup: reset running tasks to pending so they can be resumed."""
    result = await session.execute(
        text(
            "UPDATE paper_evidence_tasks SET status='pending', resumed_at=now() "
            "WHERE status IN ('running','pending') AND finished_at IS NULL"
        )
    )
    await session.commit()
    return result.rowcount or 0


async def pause_batch_task(session: AsyncSession, task_id: str, operator_id: str | None = None) -> dict:
    result = await session.execute(
        text(
            "UPDATE paper_evidence_tasks SET status='paused', paused_at=now() "
            "WHERE id::text=:tid AND status IN ('pending','running')"
        ),
        {"tid": task_id},
    )
    await session.commit()
    if result.rowcount == 0:
        raise ValueError("task is not pauseable in its current state")
    await _write_audit(
        session,
        action_type="EVIDENCE_TASK_PAUSE",
        entity_type="evidence_task",
        entity_id=uuid.UUID(task_id),
        after_data={"status": "paused"},
        operator_id=operator_id,
        reason="batch evidence task paused",
    )
    await session.commit()
    return {"task_id": task_id, "status": "paused"}


async def resume_batch_task(session: AsyncSession, task_id: str, operator_id: str | None = None) -> dict:
    result = await session.execute(
        text(
            "UPDATE paper_evidence_tasks SET status='pending', resumed_at=now(), paused_at=NULL "
            "WHERE id::text=:tid AND status='paused'"
        ),
        {"tid": task_id},
    )
    await session.commit()
    if result.rowcount == 0:
        raise ValueError("task is not paused")
    await _write_audit(
        session,
        action_type="EVIDENCE_TASK_RESUME",
        entity_type="evidence_task",
        entity_id=uuid.UUID(task_id),
        after_data={"status": "pending"},
        operator_id=operator_id,
        reason="batch evidence task resumed",
    )
    await session.commit()
    return {"task_id": task_id, "status": "pending"}


async def cancel_batch_task(session: AsyncSession, task_id: str, operator_id: str | None = None) -> dict:
    result = await session.execute(
        text(
            "UPDATE paper_evidence_tasks SET status='cancelled', cancelled_at=now() "
            "WHERE id::text=:tid AND status IN ('pending','running','paused')"
        ),
        {"tid": task_id},
    )
    await session.execute(
        text(
            "UPDATE paper_evidence_task_items SET status='skipped', last_error='cancelled', updated_at=now() "
            "WHERE task_id::text=:tid AND status='pending'"
        ),
        {"tid": task_id},
    )
    await session.commit()
    if result.rowcount == 0:
        raise ValueError("task is not cancellable in its current state")
    await _write_audit(
        session,
        action_type="EVIDENCE_TASK_CANCEL",
        entity_type="evidence_task",
        entity_id=uuid.UUID(task_id),
        after_data={"status": "cancelled"},
        operator_id=operator_id,
        reason="batch evidence task cancelled",
    )
    await session.commit()
    return {"task_id": task_id, "status": "cancelled"}


async def retry_failed_batch_items(session: AsyncSession, task_id: str, operator_id: str | None = None) -> dict:
    result = await session.execute(
        text(
            "UPDATE paper_evidence_task_items SET status='pending', last_error=NULL, "
            "retry_count=0, updated_at=now() WHERE task_id::text=:tid AND status='failed'"
        ),
        {"tid": task_id},
    )
    await session.execute(
        text(
            "UPDATE paper_evidence_tasks SET status='pending', finished_at=NULL "
            "WHERE id::text=:tid AND status IN ('failed','partially_failed','completed','cancelled')"
        ),
        {"tid": task_id},
    )
    await session.commit()
    await _write_audit(
        session,
        action_type="EVIDENCE_TASK_RETRY",
        entity_type="evidence_task",
        entity_id=uuid.UUID(task_id),
        after_data={"retried": result.rowcount or 0},
        operator_id=operator_id,
        reason="retry failed batch items",
    )
    await session.commit()
    return {"task_id": task_id, "retried": result.rowcount or 0}


async def list_paper_evidence_tasks(
    session: AsyncSession, limit: int = 50, offset: int = 0, status: str | None = None
) -> dict:
    where = ""
    params: dict = {"lim": limit, "off": offset}
    if status:
        where = "WHERE status = :st"
        params["st"] = status
    rows = (
        await session.execute(
            text(
                f"SELECT id::text, target_type, scope, mode, max_papers_per_object, status, "
                f"total_items, processed_items, awaiting_review_items, failed_items, summary, "
                f"created_by, created_at, started_at, finished_at, error_message "
                f"FROM paper_evidence_tasks {where} ORDER BY created_at DESC LIMIT :lim OFFSET :off"
            ),
            params,
        )
    ).all()
    total = (
        await session.execute(text(f"SELECT COUNT(*) FROM paper_evidence_tasks {where}"), params)
    ).scalar_one()
    return {
        "items": [
            {
                "id": r[0],
                "target_type": r[1],
                "scope": r[2],
                "mode": r[3],
                "max_papers_per_object": r[4],
                "status": r[5],
                "total_items": r[6],
                "processed_items": r[7],
                "awaiting_review_items": r[8],
                "failed_items": r[9],
                "summary": r[10],
                "created_by": r[11],
                "created_at": r[12].isoformat() if r[12] else None,
                "started_at": r[13].isoformat() if r[13] else None,
                "finished_at": r[14].isoformat() if r[14] else None,
                "error_message": r[15],
            }
            for r in rows
        ],
        "total": total,
    }


async def get_batch_task(session: AsyncSession, task_id: str) -> dict:
    task = (
        await session.execute(
            text(
                "SELECT id::text, target_type, scope, mode, max_papers_per_object, status, summary, "
                "total_items, processed_items, awaiting_review_items, failed_items, created_by, "
                "created_at, started_at, finished_at, error_message "
                "FROM paper_evidence_tasks WHERE id::text = :tid"
            ),
            {"tid": task_id},
        )
    ).first()
    if task is None:
        raise ValueError("task not found")
    counts = (
        await session.execute(
            text(
                "SELECT status, COUNT(*) FROM paper_evidence_task_items "
                "WHERE task_id::text = :tid GROUP BY 1"
            ),
            {"tid": task_id},
        )
    ).all()
    return {
        "task": {
            "id": task[0],
            "target_type": task[1],
            "scope": task[2],
            "mode": task[3],
            "max_papers_per_object": task[4],
            "status": task[5],
            "summary": task[6],
            "total_items": task[7],
            "processed_items": task[8],
            "awaiting_review_items": task[9],
            "failed_items": task[10],
            "created_by": task[11],
            "created_at": task[12].isoformat() if task[12] else None,
            "started_at": task[13].isoformat() if task[13] else None,
            "finished_at": task[14].isoformat() if task[14] else None,
            "error_message": task[15],
        },
        "counts": {r[0]: r[1] for r in counts},
    }


async def list_batch_items(
    session: AsyncSession, task_id: str, limit: int = 50, offset: int = 0
) -> dict:
    rows = (
        await session.execute(
            text(
                "SELECT id::text, target_type, target_id::text, status, pmid, title, passage, "
                "direction, confidence, evidence_id::text, error_message, updated_at, label, "
                "current_confidence, passages_json, last_error, retry_count "
                "FROM paper_evidence_task_items WHERE task_id::text = :tid "
                "ORDER BY created_at LIMIT :lim OFFSET :off"
            ),
            {"tid": task_id, "lim": limit, "off": offset},
        )
    ).all()
    return {
        "items": [
            {
                "id": r[0],
                "target_type": r[1],
                "target_id": r[2],
                "status": r[3],
                "pmid": r[4],
                "title": r[5],
                "passage": r[6],
                "direction": r[7],
                "confidence": float(r[8]) if r[8] is not None else None,
                "evidence_id": r[9],
                "error_message": r[10],
                "updated_at": r[11].isoformat() if r[11] else None,
                "label": r[12],
                "current_confidence": float(r[13]) if r[13] is not None else None,
                "passages_json": r[14],
                "last_error": r[15],
                "retry_count": r[16],
            }
            for r in rows
        ]
    }


async def complete_batch_item_reviewed(
    session: AsyncSession, task_id: str, item_id: str, operator_id: str | None = None
) -> dict:
    result = await session.execute(
        text(
            "UPDATE paper_evidence_task_items SET status='completed', reviewed_by=:rb, "
            "reviewed_at=now(), updated_at=now() "
            "WHERE task_id::text=:tid AND id::text=:iid AND status='awaiting_review'"
        ),
        {"tid": task_id, "iid": item_id, "rb": operator_id},
    )
    await session.commit()
    if result.rowcount == 0:
        raise ValueError("item is not awaiting review")
    await _update_task_totals(session, task_id)
    await session.commit()
    return {"task_id": task_id, "item_id": item_id, "status": "completed"}


async def write_evidence_audit_event(
    session: AsyncSession,
    *,
    action_type: str,
    entity_type: str,
    entity_id: uuid.UUID,
    before_data: dict | None = None,
    after_data: dict | None = None,
    operator_id: str | None = None,
    reason: str | None = None,
) -> dict:
    await _write_audit(
        session,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id,
        before_data=before_data,
        after_data=after_data,
        operator_id=operator_id,
        reason=reason,
    )
    await session.commit()
    return {"ok": True, "action_type": action_type}


async def paper_evidence_stats(
    session: AsyncSession, target_types: list[str] | None = None
) -> dict:
    """Evidence statistics. Optional target_types filters by object type."""
    tt_filter = ""
    params: dict = {}
    if target_types:
        tt_filter = "AND evidence_target_type = ANY(:tts)"
        params["tts"] = target_types
    obj_count = (
        await session.execute(
            text(
                "SELECT COUNT(DISTINCT evidence_target_id) FROM mirror_evidence_records "
                "WHERE evidence_type='paper_verification' "
                "AND verification_status IN ('human_verified','ai_extracted') " + tt_filter
            ),
            params,
        )
    ).scalar_one()
    status_rows = (
        await session.execute(
            text(
                "SELECT verification_status, COUNT(*) FROM mirror_evidence_records "
                "WHERE evidence_type='paper_verification' " + tt_filter + " GROUP BY 1"
            ),
            params,
        )
    ).all()
    status_map = {r[0]: r[1] for r in status_rows}
    direction_rows = (
        await session.execute(
            text(
                "SELECT evidence_direction, COUNT(*) FROM mirror_evidence_records "
                "WHERE evidence_type='paper_verification' "
                "AND verification_status='human_verified' " + tt_filter + " GROUP BY 1"
            ),
            params,
        )
    ).all()
    direction_map = {r[0]: r[1] for r in direction_rows}
    adjustment = (
        await session.execute(
            text(
                "SELECT COALESCE(AVG(after_confidence - before_confidence), 0) FROM confidence_adjustment_logs "
                "WHERE status='applied' " + ("AND target_type = ANY(:tts)" if target_types else "")
            ),
            params,
        )
    ).scalar_one()
    scope_rows = (
        await session.execute(
            text(
                "SELECT p.source_scope, COUNT(*) FROM mirror_evidence_passages p "
                "JOIN mirror_evidence_records r ON r.id = p.evidence_id "
                "WHERE p.is_selected AND r.evidence_type='paper_verification' "
                "AND r.verification_status='human_verified' "
                + ("AND r.evidence_target_type = ANY(:tts)" if target_types else "")
                + " GROUP BY 1"
            ),
            params,
        )
    ).all()
    scope_map = {r[0]: r[1] for r in scope_rows}
    by_type = {
        r[0]: r[1]
        for r in (
            await session.execute(
                text(
                    "SELECT evidence_target_type, COUNT(*) FROM mirror_evidence_records "
                    "WHERE evidence_type='paper_verification' "
                    "AND verification_status='human_verified' " + tt_filter + " GROUP BY 1"
                ),
                params,
            )
        ).all()
    }
    pending_review = (
        await session.execute(
            text("SELECT COUNT(*) FROM evidence_validation_records WHERE status='pending'")
        )
    ).scalar_one()
    draft_items = (
        await session.execute(
            text(
                "SELECT COUNT(*) FROM paper_evidence_task_items WHERE status='awaiting_review' "
                + ("AND target_type = ANY(:tts)" if target_types else "")
            ),
            params,
        )
    ).scalar_one()
    fulltext_hits = (
        await session.execute(
            text(
                "SELECT COUNT(*) FROM paper_evidence_task_items "
                "WHERE passages_json IS NOT NULL AND passages_json::text LIKE '%fulltext%' "
                + ("AND target_type = ANY(:tts)" if target_types else "")
            ),
            params,
        )
    ).scalar_one()
    with_paper = (
        await session.execute(
            text(
                "SELECT COUNT(*) FROM paper_evidence_task_items WHERE paper_json IS NOT NULL "
                + ("AND target_type = ANY(:tts)" if target_types else "")
            ),
            params,
        )
    ).scalar_one()
    return {
        "objects_with_evidence": obj_count,
        "pending_human_review": status_map.get("ai_extracted", 0) + pending_review + draft_items,
        "completed_verifications": status_map.get("human_verified", 0),
        "directions": direction_map,
        "avg_confidence_delta": round(float(adjustment or 0), 4),
        "invalidated_count": status_map.get("invalidated", 0),
        "source_scope": scope_map,
        "oa_fulltext_hit_rate": round(fulltext_hits / with_paper, 4) if with_paper else 0,
        "by_target_type": by_type,
    }


async def list_evidence_review_queue(
    session: AsyncSession, limit: int = 50, offset: int = 0, status: str = "pending"
) -> dict:
    records = (
        await session.execute(
            text(
                "SELECT id::text, evidence_id::text, rule_code, status, target_type, target_id::text, "
                "direction, paper_snapshot, detail, created_at, resolved_at, resolved_by, resolution_note "
                "FROM evidence_validation_records WHERE status=:st "
                "ORDER BY created_at DESC LIMIT :lim OFFSET :off"
            ),
            {"st": status, "lim": limit, "off": offset},
        )
    ).all()
    total = (
        await session.execute(
            text("SELECT COUNT(*) FROM evidence_validation_records WHERE status=:st"),
            {"st": status},
        )
    ).scalar_one()
    return {
        "items": [
            {
                "id": r[0],
                "evidence_id": r[1],
                "rule_code": r[2],
                "status": r[3],
                "target_type": r[4],
                "target_id": r[5],
                "direction": r[6],
                "paper_snapshot": r[7],
                "detail": r[8],
                "created_at": r[9].isoformat() if r[9] else None,
                "resolved_at": r[10].isoformat() if r[10] else None,
                "resolved_by": r[11],
                "resolution_note": r[12],
            }
            for r in records
        ],
        "total": total,
    }


async def list_confidence_adjustments(
    session: AsyncSession,
    *,
    target_type: str,
    target_id: uuid.UUID,
    limit: int = 50,
) -> dict:
    rows = (
        await session.execute(
            text(
                "SELECT id::text, evidence_id::text, before_confidence, suggested_confidence, "
                "after_confidence, direction, formula_version, status, applied_by, applied_at, "
                "rolled_back_by, rolled_back_at, rollback_reason "
                "FROM confidence_adjustment_logs "
                "WHERE target_type=:tt AND target_id=:oid "
                "ORDER BY applied_at DESC NULLS LAST LIMIT :lim"
            ),
            {"tt": target_type, "oid": target_id, "lim": limit},
        )
    ).all()
    return {
        "items": [
            {
                "id": r[0],
                "evidence_id": r[1],
                "before_confidence": float(r[2]) if r[2] is not None else None,
                "suggested_confidence": float(r[3]) if r[3] is not None else None,
                "after_confidence": float(r[4]) if r[4] is not None else None,
                "direction": r[5],
                "formula_version": r[6],
                "status": r[7],
                "applied_by": r[8],
                "applied_at": r[9].isoformat() if r[9] else None,
                "rolled_back_by": r[10],
                "rolled_back_at": r[11].isoformat() if r[11] else None,
                "rollback_reason": r[12],
            }
            for r in rows
        ]
    }


async def resolve_evidence_review_record(
    session: AsyncSession,
    record_id: uuid.UUID,
    *,
    note: str,
    operator_id: str | None = None,
) -> dict:
    row = (
        await session.execute(
            text(
                "UPDATE evidence_validation_records SET status='resolved', resolved_at=now(), "
                "resolved_by=:rb, resolution_note=:note WHERE id=:rid AND status='pending' RETURNING id::text"
            ),
            {"rid": record_id, "rb": operator_id, "note": note},
        )
    ).first()
    await session.commit()
    if row is None:
        raise ValueError("review record not found or already resolved")
    await _write_audit(
        session,
        action_type="EVIDENCE_REVIEW_RESOLVED",
        entity_type="evidence_validation_record",
        entity_id=record_id,
        after_data={"note": note},
        operator_id=operator_id,
        reason=note,
    )
    await session.commit()
    return {"id": str(record_id), "status": "resolved"}
