"""Paper evidence retrieval (Europe PMC) + attach to Mirror KG evidence."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import unicodedata
import uuid
from difflib import SequenceMatcher

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
from app.services.ontology_residual_schemas import (
    PaperMultiPassageExtraction,
    PaperPassageExtraction,
    PaperRelevanceBatch,
)
from app.services.confidence_rules import (
    FORMULA_VERSION,
    PARTIAL_CAP,
    SUPPORT_CAP,
    compute_adjustment,
)
from app.services.evidence_target_adapter import (
    TARGET_MODELS as ADAPTER_TARGET_MODELS,
    build_search_query,
    build_target_dto,
    build_retrieval_context,
)
from app.services.paragraph_retrieval import build_windows, score_paragraphs
from app.services import oa_xml_parser
from app.services import paper_fetch_service as pfs

# Similarity tier: token Jaccard (word overlap) or character ratio for LLM
# passages that are not verbatim. Exact / whitespace / unicode-normalized
# matches stay preferred; similarity is a controlled fallback for human review.
SIMILARITY_TOKEN_JACCARD_THRESHOLD = 0.75
SIMILARITY_RATIO_THRESHOLD = 0.8
LOCATE_SIMILARITY_THRESHOLD = 0.6

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


def _token_jaccard(passage: str, source: str) -> float:
    tokens_a = set(re.findall(r"[a-z0-9]+", normalize_for_match(passage)))
    tokens_b = set(re.findall(r"[a-z0-9]+", normalize_for_match(source)))
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def passage_similarity_score(passage: str, source: str) -> float:
    """0–1 similarity between a passage and a source text (max of token Jaccard / char ratio)."""
    norm_p = normalize_for_match(passage)
    norm_s = normalize_for_match(source)
    if not norm_p or not norm_s:
        return 0.0
    jaccard = _token_jaccard(passage, source)
    ratio = SequenceMatcher(None, norm_p, norm_s).ratio()
    return max(jaccard, ratio)


def locate_passage(passage: str, source: str) -> tuple[int | None, str | None]:
    """Find containing paragraph index (paragraph split by blank lines)."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", source or "")]
    for idx, para in enumerate(paragraphs):
        if passage in para or normalized_passage_match(passage, para):
            return idx, f"paragraph:{idx}"
    return None, None


def verify_passage_against_source(passage: str, source: str) -> tuple[bool, str | None]:
    """Tiered verification: exact → normalized → similarity.

    Similarity is a controlled fallback for LLM passages with light rewrites;
    it still requires strong token/character overlap so unrelated text never passes.
    """
    if not passage or not source:
        return False, None
    if exact_passage_match(passage, source):
        return True, "exact"
    if _normalize_whitespace_only(passage) and _normalize_whitespace_only(passage) in _normalize_whitespace_only(source):
        return True, "normalized_whitespace"
    if normalized_passage_match(passage, source):
        return True, "normalized_unicode"
    score = passage_similarity_score(passage, source)
    if score >= SIMILARITY_TOKEN_JACCARD_THRESHOLD and _token_jaccard(passage, source) >= SIMILARITY_TOKEN_JACCARD_THRESHOLD:
        return True, "similarity"
    if score >= SIMILARITY_RATIO_THRESHOLD:
        return True, "similarity"
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
        section_slug = re.sub(r"[^a-z0-9]+", "_", (current_section or "").lower()).strip("_")[:64]
        para_id = f"{section_slug}_p{idx + 1:03d}" if section_slug else f"fulltext_p{idx + 1:03d}"
        paragraphs.append(
            {
                "source_scope": source_scope,
                "section_title": current_section or None,
                "paragraph_id": para_id,
                "paragraph_index": idx,
                "passage_text": paragraph_text,
                "text_hash": passage_hash(paragraph_text),
                "locator": f"{section_slug}:paragraph:{idx}" if section_slug else f"paragraph:{idx}",
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
        plain = re.sub(r"\b(ABSTRACT|BODY|TITLE)\s*:", "", query)
        plain = re.sub(r"\s+(AND|OR)\s+", " ", plain).strip()
        tokens = [t for t in re.split(r"[^a-zA-Z0-9]+", plain) if t]
        fallback = " AND ".join(tokens)
        if fallback and fallback != query:
            papers = await _search(fallback, limit)
    return papers


_CONFERENCE_NOISE_PATTERNS = (
    "poster session",
    "annual meeting",
    "abstracts of the",
    "meeting abstracts",
    "conference proceedings",
    "computational neuroscience meeting",
    "annual computational",
    "proceedings of the",
)


def _is_conference_noise(title: str) -> bool:
    t = (title or "").lower()
    return any(p in t for p in _CONFERENCE_NOISE_PATTERNS)


async def _search(query: str, limit: int) -> list[dict]:
    async with httpx.AsyncClient(trust_env=False, timeout=SEARCH_TIMEOUT) as client:
        payload = await pfs._get_json_with_retry(
            client,
            EUROPE_PMC_SEARCH,
            {"query": query, "format": "json", "pageSize": limit, "resultType": "core"},
        )
    results = payload.get("resultList", {}).get("result", [])
    papers = []
    for item in results:
        title = item.get("title") or ""
        if _is_conference_noise(title):
            continue
        pmcid = (item.get("pmcid") or "").upper()
        is_oa = str(item.get("isOpenAccess") or "").lower() == "y"
        papers.append(
            {
                "pmid": item.get("pmid") or "",
                "pmcid": pmcid,
                "doi": item.get("doi") or "",
                "title": title,
                "journal": item.get("journalTitle") or "",
                "year": item.get("pubYear") or "",
                "authors": item.get("authorString") or "",
                "abstract": pfs.clean_html_text(item.get("abstractText") or "")[:4000],
                "is_open_access": is_oa,
                "fulltext_available": bool(pmcid) and is_oa,
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
    return pfs.clean_html_text(text_xml)[:8000]


async def verify_paper(pmid: str) -> dict | None:
    if not pmid:
        return None
    async with httpx.AsyncClient(trust_env=False, timeout=SEARCH_TIMEOUT) as client:
        payload = await pfs._get_json_with_retry(
            client,
            EUROPE_PMC_SEARCH,
            {"query": f"EXT_ID:{pmid}", "format": "json", "pageSize": 1, "resultType": "core"},
        )
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
        "abstract": pfs.clean_html_text(item.get("abstractText") or "")[:4000],
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
    evidence_level: str | None = None,
    model_direction: str | None = None,
    model_assessment: str | None = None,
    reviewer_note: str | None = None,
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
    # backend-authoritative claim snapshot (never trusts client claim_text)
    claim = await build_target_dto(session, target_type, target_id)
    claim_components = claim.get("claim_components") or []
    claim_version = claim.get("claim_version") or "claim_v1"
    claim_text = claim.get("claim_text") or ""
    # 2) re-verify passages against source (backend never trusts the client)
    source, source_scope = await _load_source(session, pmid)
    if not source:
        raise ValueError("no source text available for passage verification")
    verified = _verify_passages(passages, source, source_scope)
    if not verified:
        raise ValueError("no passage could be verified against the original source")
    if any(
        p.get("source_verification_method") in ("similarity", "similarity_located")
        for p in verified
    ) and not (reviewer_note or "").strip():
        raise ValueError(
            "approximate (similarity) passages require a reviewer note confirming the original text"
        )
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
        allowed = {c["component_type"] for c in claim_components}
        declared = p.get("supported_components") or []
        if not declared:
            # legacy clients without component annotations: treat as supporting the whole claim
            declared = [c["component_type"] for c in claim_components]
        p["supported_components"] = [
            c for c in declared if c in allowed
        ]
    # backend-authoritative coverage snapshot from human-final passages
    coverage = compute_coverage_summary(claim_components, verified)
    coverage_overall = aggregate_overall_direction(coverage, verified)
    coverage_snapshot = {**coverage, "overall_direction": coverage_overall}
    if verification_status == "human_verified":
        if direction != coverage_overall and not (reviewer_note or "").strip():
            raise ValueError(
                f"reviewer direction ({direction}) differs from coverage overall "
                f"({coverage_overall}); reviewer_note is required for manual override"
            )
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
        evidence_level=evidence_level
        or next((p.get("evidence_level") for p in verified if p.get("evidence_level")), "indirect"),
        model_direction=model_direction,
        model_assessment=model_assessment,
        reviewer_note=reviewer_note,
        claim_version=claim_version,
        claim_text_snapshot=claim_text,
        claim_components_snapshot=claim_components,
        coverage_summary_snapshot=coverage_snapshot,
        coverage_formula_version="paper_evidence_coverage_v1",
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
                supported_components=list(p.get("supported_components") or []),
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
                "evidence_level": record.evidence_level,
                "model_direction": model_direction,
                "reviewer_confidence": reviewer_confidence,
                "passage_count": len(verified),
                "verification_status": record.verification_status,
                "claim_version": claim_version,
                "coverage": coverage_snapshot,
                "override": direction != coverage_overall,
            },
            operator_id=operator_id,
            reason=(
                f"paper evidence attached after human review"
                + (f"; override reason: {reviewer_note}" if direction != coverage_overall else "")
            ),
        )
        await _write_validation_record(
            session,
            evidence_id=record.id,
            rule_code=(
                "EV_PAPER_EVIDENCE_MIXED"
                if direction == "mixed"
                else "EV_PAPER_EVIDENCE_CONTRADICTORY"
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
                "status": (
                    "pending_review"
                    if direction in ("contradicts", "mixed")
                    else "resolved_by_attach"
                ),
            },
            created_by=operator_id,
        )
        if adjustment and not adjustment.apply and direction in ("contradicts", "mixed"):
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


async def _load_source(session: AsyncSession, pmid: str) -> tuple[str, str]:
    """Load verification source, preferring cached structured passages.

    Extraction stores normalized paragraphs in paper_passages; attach must
    re-verify against the SAME text (not a re-fetched, differently-normalized
    plain-text dump) or previously verified passages get rejected on attach.
    """
    row_id = (
        await session.execute(
            text("SELECT id FROM paper_sources WHERE pmid=:pmid"),
            {"pmid": pmid},
        )
    ).scalar_one_or_none()
    if row_id is not None:
        paras = (
            await session.execute(
                text(
                    "SELECT passage_text, source_scope FROM paper_passages "
                    "WHERE paper_id=:pid ORDER BY paragraph_index"
                ),
                {"pid": row_id},
            )
        ).all()
        if paras:
            joined = "\n\n".join(p for p, _ in paras).strip()
            scopes = {s for _, s in paras}
            if joined:
                return joined, ("fulltext" if "fulltext" in scopes else "abstract")
    # fallback: network fetch (paper not cached / no passages stored)
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
    source, source_scope = await _load_source(session, pmid)
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
                "model_direction": r.model_direction,
                "model_assessment": r.model_assessment,
                "reviewer_note": r.reviewer_note,
                "claim_version": r.claim_version,
                "claim_text_snapshot": r.claim_text_snapshot,
                "claim_components_snapshot": r.claim_components_snapshot,
                "coverage_summary_snapshot": r.coverage_summary_snapshot,
                "coverage_formula_version": r.coverage_formula_version,
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
                        "supported_components": p.supported_components or [],
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


def _normalize_extraction_payload(payload: dict | None) -> dict:
    """Tolerate common DeepSeek output variants before Pydantic validation."""
    p = dict(payload or {})
    direction = str(p.get("overall_direction") or "").strip().lower()
    if direction in ("no_evidence", "no evidence", "none", "no evidence found"):
        direction = "not_found"
    if direction not in ("supports", "partial", "contradicts", "mixed", "not_found"):
        direction = "not_found"
    p["overall_direction"] = direction
    rel = p.get("paper_relevance")
    if isinstance(rel, str):
        try:
            p["paper_relevance"] = max(0.0, min(1.0, float(rel.strip() or 0)))
        except ValueError:
            p["paper_relevance"] = 0.0
    p["passages"] = p.get("passages") or []
    return p


def _parse_multi(raw_text: str) -> PaperMultiPassageExtraction:
    text_value = (raw_text or "").strip()
    fence = re.search(r"```(?:json|JSON)?\s*(.*?)```", text_value, re.DOTALL)
    if fence:
        text_value = fence.group(1).strip()
    text_value = _extract_json_object(text_value)
    # JSON does not allow trailing commas; LLM responses often include them.
    text_value = re.sub(r",\s*([}\]])", r"\1", text_value)
    parsed = _normalize_extraction_payload(json.loads(text_value))
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
    resp = None
    text_result = None
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
                    parsed = PaperMultiPassageExtraction.model_validate(
                        _normalize_extraction_payload(resp.parsed_json)
                    )
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
    llm_model = getattr(resp, "model", None) or getattr(text_result, "model", None) or ""
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
        "llm_model": llm_model,
    }


def _locate_best_paragraph(
    passage: str, paragraph_map: dict[str, dict]
) -> tuple[dict | None, float]:
    """Find the paragraph with the highest similarity to the passage (0–1)."""
    best: dict | None = None
    best_score = 0.0
    for para in paragraph_map.values():
        source_text = (para or {}).get("passage_text") or ""
        if not source_text:
            continue
        score = passage_similarity_score(passage, source_text)
        if score > best_score:
            best, best_score = para, score
    return best, best_score


def _verify_extraction_passages(
    passages: list[dict],
    paragraph_map: dict[str, dict],
) -> list[dict]:
    """Backend verification: paragraph_id hit first, fuzzy locate as fallback.

    1) paragraph_id hit → tiered match (exact / normalized / similarity).
    2) unknown/missing paragraph_id → locate best-matching paragraph across the
       paper; verified only if similarity ≥ LOCATE_SIMILARITY_THRESHOLD (no guesswork).
    """
    verified_out: list[dict] = []
    for item in passages:
        para_id = (item.get("paragraph_id") or "").strip()
        candidate = paragraph_map.get(para_id)
        ok, method = False, None
        if candidate is not None:
            source_text = (candidate or {}).get("passage_text") or ""
            ok, method = (
                verify_passage_against_source(item.get("passage") or "", source_text)
                if source_text
                else (False, None)
            )
        if not ok:
            located, loc_score = _locate_best_paragraph(
                item.get("passage") or "", paragraph_map
            )
            if located is not None and loc_score >= LOCATE_SIMILARITY_THRESHOLD:
                candidate = located
                ok = True
                method = "similarity_located"
        verified_out.append(
            {
                **item,
                "source_scope": (candidate or {}).get("source_scope") or "fulltext",
                "section_title": (candidate or {}).get("section_title") or item.get("section"),
                "paragraph_index": (candidate or {}).get("paragraph_index"),
                "paragraph_id": (candidate or {}).get("paragraph_id") or item.get("paragraph_id"),
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
        return "mixed"
    if "contradicts" in directions:
        return "contradicts"
    if "supports" in directions:
        return "supports"
    if "partial" in directions:
        return "partial"
    return parsed.overall_direction


def compute_coverage_summary(
    claim_components: list[dict],
    passages: list[dict],
) -> dict:
    """Backend-computed claim coverage from verified passages only.

    DeepSeek provides semantic judgment; coverage is aggregated here from
    source-verified passages and their supported_components.
    """
    required = {
        c.get("component_type")
        for c in claim_components
        if c.get("required") and c.get("component_type")
    }
    supported: set[str] = set()
    contradicted: set[str] = set()
    for p in passages:
        if not p.get("source_verified"):
            continue
        comps = {c for c in (p.get("supported_components") or []) if c}
        if p.get("direction") == "contradicts":
            contradicted |= comps
        else:
            supported |= comps
    supported_in_required = supported & required
    contradicted_in_required = contradicted & required
    uncovered = required - supported
    has_conflict = bool(supported_in_required) and bool(contradicted_in_required)
    coverage_ratio = round(len(supported_in_required) / len(required), 4) if required else 0.0
    full_claim_supported = bool(required and required <= supported and not has_conflict)
    return {
        "required_components": sorted(required),
        "supported_components": sorted(supported_in_required),
        "contradicted_components": sorted(contradicted_in_required),
        "uncovered_components": sorted(uncovered),
        "coverage_ratio": coverage_ratio,
        "has_conflict": has_conflict,
        "full_claim_supported": full_claim_supported,
    }


def aggregate_overall_direction(coverage: dict, passages: list[dict]) -> str:
    """Derive overall_direction from verified coverage (backend authority)."""
    verified = [p for p in passages if p.get("source_verified")]
    if not verified:
        return "not_found"
    if coverage.get("has_conflict"):
        return "mixed"
    required = set(coverage.get("required_components") or [])
    if not required:
        return "not_found"
    supported = set(coverage.get("supported_components") or [])
    contradicted = set(coverage.get("contradicted_components") or [])
    if required <= supported:
        return "supports"
    if contradicted and contradicted >= required and not supported:
        return "contradicts"
    if supported or contradicted:
        return "partial"
    return "not_found"


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
    claim_components = claim.get("claim_components") or []
    allowed_components = sorted(
        {c.get("component_type") for c in claim_components if c.get("component_type")}
    )
    direction_rule = (
        "8. Existence mode: the claim is about the OBJECT EXISTING (a projection/connection "
        "between the two regions). If the paper establishes connectivity between the two regions "
        "(even without exact laterality or direction), return a partial passage with "
        "supported_components excluding 'direction', rather than not_found.\n"
        "8b. INDIRECT evidence is still evidence: if the paper establishes connectivity involving "
        "a structure that CONTAINS one of the regions (e.g. 'striatal-thalamic connections' for a "
        "putamen-thalamus claim, since putamen is part of the striatum), return the passage as "
        "partial with evidence_level 'background' or 'indirect' and confidence 0.3-0.5, and say so "
        "in reason. Only return not_found when the paper does not involve either region's "
        "structure at all.\n"
        if claim.get("claim_mode") == "existence"
        else "8. Direction matters: 'B -> A' does not support 'A -> B'; functional connectivity "
        "is not an anatomical projection.\n"
    )
    user = (
        f'Knowledge claim to verify: "{claim.get("claim_text") or claim.get("function_term") or ""}"\n'
        "Structured claim (relation direction matters): "
        f"{claim.get('structured_claim') or claim.get('claim_text') or ''}\n"
        f"Claim components that must hold: {', '.join(allowed_components) or 'none'}\n"
        "Rules:\n"
        "1. Use ONLY the given paragraphs; never add model knowledge.\n"
        "2. Output passages verbatim (copy exactly); never rewrite or invent sentences.\n"
        "3. Reuse the exact paragraph ids from the <id=...> markers; never invent ids.\n"
        "4. If no paragraph truly supports or contradicts the claim, return not_found with passages=[] (do NOT fabricate weak evidence).\n"
        "5. Search for BOTH supporting and contradicting evidence; you may return 1-8 passages.\n"
        "6. Distinguish experimental Results (direct) from author interpretation (interpretive) and background (background).\n"
        "7. Keyword co-occurrence is NOT evidence: 'A and B both participate in X' does not mean 'A projects to B'.\n"
        + direction_rule
        + "9. evidence_level: direct (experiment proves the claim/core relation), indirect (needs reasonable inference), "
        "interpretive (author explanation in Discussion/Conclusion), background (Introduction/review-like).\n"
        "10. overall_direction must reflect ALL returned passages (support+contradict -> mixed).\n"
        "11. For each passage set supported_components to the claim components it actually supports "
        "(for a contradicting passage: the components it refutes). Use ONLY component names from the "
        "Claim components list; never invent components. A passage may support only part of the claim.\n"
        "12. evidence_dimension: 'existence' = the paper establishes the OBJECT itself (e.g. an "
        "anatomical projection between the two regions, the circuit exists); 'function' = it describes "
        "what the object does (function, effect, role); 'mixed' = both. Pick per passage; "
        "overall evidence_dimension must reflect the dominant kind.\n"
        "Return ONLY one raw JSON object (no markdown, no code fences, no trailing commas):\n"
        '{"overall_direction": "supports|partial|contradicts|mixed|not_found", "paper_relevance": 0.9, '
        '"assessment": "<one or two sentences summarizing the judgment>", '
        '"evidence_dimension": "existence|function|mixed", '
        '"passages": [{"paragraph_id": "<id>", "section": "<section>", "passage": "<verbatim>", '
        '"direction": "supports", "evidence_level": "direct|indirect|interpretive|background", '
        '"reason": "<one sentence>", "confidence": 0.9, "semantic_confidence": 0.9, '
        '"supported_components": ["source_region", "target_region", "relation"], '
        '"evidence_dimension": "existence"}]}\n'
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
                    parsed = PaperMultiPassageExtraction.model_validate(
                        _normalize_extraction_payload(resp.parsed_json)
                    )
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
            "supported_components": [
                c for c in (item.supported_components or []) if c in allowed_components
            ],
            "evidence_dimension": item.evidence_dimension,
        }
        for item in parsed.passages
    ]
    verified_passages = _verify_extraction_passages(raw_items, paragraph_map)
    deduped = _dedupe_extraction_passages(verified_passages)
    coverage = compute_coverage_summary(claim_components, deduped)
    overall = aggregate_overall_direction(coverage, deduped)
    source_type = (
        "fulltext"
        if any((p.get("source_scope") == "fulltext") for p in paragraph_map.values())
        else "abstract"
    )
    return {
        "overall_direction": overall,
        "paper_relevance": parsed.paper_relevance,
        "assessment": parsed.assessment,
        "evidence_dimension": parsed.evidence_dimension,
        "source_type": source_type,
        "passages": deduped,
        "claim_components": claim_components,
        "coverage_summary": coverage,
        "retrieval_summary": {
            "candidate_windows": len(windows),
            "input_truncated": truncated,
            "verified_count": sum(1 for p in deduped if p.get("source_verified")),
            "unverified_count": sum(1 for p in deduped if not p.get("source_verified")),
            "model_overall_direction": parsed.overall_direction,
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
    name: str | None = None,
    granularity_level: str | None = None,
    only_oa: bool = False,
    confidence_lt: float | None = None,
    stop_after_strong_support: bool = False,
    target_ids: list[str] | None = None,
) -> dict:
    """Create a pre-processing task. Never writes formal evidence."""
    if target_type not in TARGET_MODELS:
        raise ValueError(f"unsupported target_type: {target_type}")
    if target_ids:
        ids = target_ids
    elif scope == "low_confidence":
        ids = await _resolve_scope_ids_low_confidence(session, target_type, confidence_lt, limit)
    else:
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
                "(target_type, scope, mode, max_papers_per_object, status, created_by, total_items, config, "
                "name, granularity_level, only_oa, confidence_lt, stop_after_strong_support, review_status) "
                "VALUES (:tt, :scope, :mode, :maxp, :status, :cb, :total, CAST(:cfg AS jsonb), "
                ":name, :gl, :only_oa, :clt, :stop, 'not_started') RETURNING id::text"
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
                "name": name,
                "gl": granularity_level,
                "only_oa": only_oa,
                "clt": confidence_lt,
                "stop": stop_after_strong_support,
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
                windows = build_windows(ranked, all_paragraphs)
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


def _parse_relevance_batch(raw_text: str) -> PaperRelevanceBatch:
    """Parse a noisy DeepSeek relevance response into the batch schema."""
    text_value = (raw_text or "").strip()
    fence = re.search(r"```(?:json|JSON)?\s*(.*?)```", text_value, re.DOTALL)
    if fence:
        text_value = fence.group(1).strip()
    text_value = _extract_json_object(text_value)
    text_value = re.sub(r",\s*([}\]])", r"\1", text_value)
    parsed = json.loads(text_value)
    items = parsed.get("items") or []
    for it in items:
        rel = it.get("relevance")
        if isinstance(rel, str):
            try:
                it["relevance"] = max(0.0, min(1.0, float(rel.strip() or 0)))
            except ValueError:
                it["relevance"] = 0.0
    return PaperRelevanceBatch.model_validate({"items": items})


async def semantic_filter_papers(
    papers: list[dict],
    context: dict,
    *,
    threshold: float | None = None,
) -> tuple[list[dict], list[dict]]:
    """DeepSeek relevance scoring over candidate papers (title + abstract).

    Returns (keep, skipped); skipped papers carry semantic_relevance and
    semantic_skip_reason for audit. Threshold <= 0 disables filtering;
    provider failure degrades to keep-all (papers are never dropped because
    the filter itself failed).
    """
    cfg = get_settings()
    if threshold is None:
        threshold = float(getattr(cfg, "paper_semantic_threshold", 0.4) or 0)
    if threshold <= 0 or not papers:
        return papers, []
    try:
        provider = get_llm_provider("deepseek")
    except Exception:  # noqa: BLE001 — advisory filter: never block extraction
        return papers, []
    claim_text = context.get("claim_text") or context.get("function_term") or ""
    lines = []
    for p in papers:
        pmid = (p.get("pmid") or "").strip()
        ident = pmid or (p.get("doi") or "").strip() or "?"
        title = (p.get("title") or "").strip()
        abstract = (p.get("abstract") or "").strip()[:1000]
        lines.append(f"- id: {ident} | title: {title} | abstract: {abstract}")
    system = "You are a strict JSON API. Reply only with the requested JSON object. Never explain."
    user = (
        f'Rate how relevant each paper is to the neuroscience claim: "{claim_text}".\n'
        "Rules:\n"
        "1. relevance is 0-1: 1 = the paper directly studies the claim "
        "(same regions and relation/function); 0 = unrelated.\n"
        "2. A paper that merely mentions a region name in passing is NOT relevant.\n"
        "3. Keyword co-occurrence is not evidence: 'A and B both participate in X' "
        "does not mean the paper supports the claim.\n"
        "4. Output ONLY one raw JSON object (no markdown, no code fences, no trailing commas):\n"
        '{"items": [{"pmid": "<id>", "relevance": 0.8, "reason": "<one sentence>"}]}\n'
        f"Papers:\n{chr(10).join(lines)}"
    )
    parsed = None
    for attempt in range(3):
        try:
            if attempt == 0:
                resp = await provider.complete_json(
                    model=cfg.ontology_residual_model,
                    system_prompt=system,
                    user_prompt=user,
                    temperature=0.1,
                    max_tokens=cfg.paper_semantic_max_tokens,
                )
                raw_response = resp.raw_text or ""
                if not getattr(resp, "transport_ok", True):
                    raise httpx.TransportError(
                        getattr(resp, "error", None) or "DeepSeek transport error"
                    )
                if resp.parsed_json is not None:
                    parsed = PaperRelevanceBatch.model_validate(resp.parsed_json)
                else:
                    parsed = _parse_relevance_batch(raw_response)
            else:
                text_result = await provider.complete_text(
                    model=cfg.ontology_residual_model,
                    system_prompt=system,
                    user_prompt=user + "\n\nIMPORTANT: Respond with ONLY the raw JSON object.",
                    temperature=0.2,
                    max_tokens=cfg.paper_semantic_max_tokens,
                    json_mode=False,
                )
                if not getattr(text_result, "transport_ok", True):
                    raise httpx.TransportError(
                        getattr(text_result, "error", None) or "DeepSeek transport error"
                    )
                parsed = _parse_relevance_batch(text_result.raw_text or "")
            break
        except httpx.HTTPError:
            if attempt < 2:
                await asyncio.sleep(cfg.ontology_residual_backoff_seconds)
        except (ValidationError, ValueError, json.JSONDecodeError):
            if attempt < 2:
                await asyncio.sleep(cfg.ontology_residual_backoff_seconds)
        except Exception:  # noqa: BLE001 — pre-filter is advisory: never block extraction
            if attempt < 2:
                await asyncio.sleep(cfg.ontology_residual_backoff_seconds)
    if parsed is None:
        return papers, []
    scores = {it.pmid: (it.relevance, it.reason) for it in parsed.items}
    keep: list[dict] = []
    skipped: list[dict] = []
    for p in papers:
        pmid = (p.get("pmid") or "").strip()
        ident = pmid or (p.get("doi") or "").strip()
        rel, reason = scores.get(pmid) or scores.get(ident) or (0.0, "")
        if rel >= threshold:
            keep.append({**p, "semantic_relevance": rel})
        else:
            skipped.append(
                {
                    **p,
                    "semantic_relevance": rel,
                    "semantic_skip_reason": reason or "relevance below threshold",
                }
            )
    return keep, skipped


async def extract_candidates_for_target(
    session: AsyncSession,
    *,
    context: dict,
    papers: list[dict],
    max_papers: int,
    only_oa: bool = False,
    stop_after_strong_support: bool = False,
    mode: str = "function",
    sem_fetch: asyncio.Semaphore,
    sem_deepseek: asyncio.Semaphore,
    on_stage=None,
) -> tuple[list[dict], str | None]:
    """Run the full fetch→parse→retrieve→DeepSeek→verify pipeline for multiple papers.

    Returns (candidates, last_llm_model). Each candidate keeps paper metadata,
    model judgment, coverage and verified passages. A single paper failure is
    captured with an error code and does not stop the remaining papers.
    """
    kept, semantic_skipped = await semantic_filter_papers(papers, context)
    ranked = _rank_papers(kept, context)
    selected = ranked[:max_papers]
    candidates: list[dict] = []
    last_llm_model: str | None = None
    for paper in selected:
        pmid = (paper.get("pmid") or "").strip()
        doi = (paper.get("doi") or "").strip()
        pmcid = (paper.get("pmcid") or "").strip()
        if not (pmid or doi or pmcid):
            candidates.append(
                {
                    **paper,
                    "error_code": "PAPER_FETCH_FAILED",
                    "error_message": "paper has no identifier (pmid / pmcid / doi)",
                    "passages": [],
                }
            )
            continue
        if on_stage is not None:
            await on_stage("fetching")
        try:
            async with sem_fetch:
                meta = await _verify_paper_with_retry(pmid) if pmid else None
                if meta is None and (doi or pmcid):
                    meta = await pfs.fetch_paper_metadata(doi=doi, pmcid=pmcid)
                if meta is None:
                    candidates.append(
                        {**paper, "error_code": "PAPER_FETCH_FAILED", "error_message": "paper not found", "passages": []}
                    )
                    continue
                xml_text = await pfs.fetch_oa_fulltext_xml(
                    pmid=pmid or meta.get("pmid") or None,
                    pmcid=pmcid or meta.get("pmcid") or None,
                )
            if only_oa and not meta.get("is_open_access"):
                continue
            abstract = (meta.get("abstract") or "").strip()
            paper_source = await ensure_paper_source(
                session, {**meta, "abstract": abstract, "fulltext": ""}
            )
            if on_stage is not None:
                await on_stage("retrieving")
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
            ranked_paras = score_paragraphs(
                all_paragraphs,
                source_region=context.get("source_region") or "",
                target_region=context.get("target_region") or "",
                source_region_synonyms=context.get("source_region_synonyms") or [],
                target_region_synonyms=context.get("target_region_synonyms") or [],
                function_terms=context.get("function_terms") or [],
                function_synonyms=context.get("function_synonyms") or [],
                relation_keywords=context.get("relation_keywords") or [],
            )
            windows = build_windows(ranked_paras, all_paragraphs)
            if on_stage is not None:
                await on_stage("extracting")
            async with sem_deepseek:
                extraction = await _extract_from_paper_with_retry(
                    claim=context,
                    title=meta.get("title") or paper.get("title") or "",
                    windows=windows,
                )
            last_llm_model = extraction.get("llm_model") or last_llm_model
            if on_stage is not None:
                await on_stage("verifying")
            coverage = compute_coverage_summary(
                context.get("claim_components") or [],
                extraction.get("passages") or [],
            )
            coverage_overall = aggregate_overall_direction(
                coverage, extraction.get("passages") or []
            )
            passage_id_map: dict[str, uuid.UUID] = {}
            for p in extraction.get("passages") or []:
                p["paper_id"] = str(paper_source.id)
                if p.get("source_verified"):
                    found = (
                        await session.execute(
                            text(
                                "SELECT id FROM paper_passages WHERE paper_id=:pid AND text_hash=:h"
                            ),
                            {"pid": paper_source.id, "h": passage_hash(p.get("passage") or "")},
                        )
                    ).first()
                    p["paper_passage_id"] = str(found[0]) if found else None
            candidates.append(
                {
                    "paper_id": str(paper_source.id),
                    "pmid": meta.get("pmid") or pmid or "",
                    "doi": meta.get("doi") or doi or "",
                    "pmcid": meta.get("pmcid") or pmcid or "",
                    "title": meta.get("title") or "",
                    "journal": meta.get("journal") or "",
                    "year": meta.get("year") or "",
                    "is_oa": bool(meta.get("is_open_access")),
                    "fulltext_fetched": bool((xml_text or "").strip()),
                    "paper_match_score": paper.get("paper_match_score", 0),
                    "model_direction": extraction.get("overall_direction"),
                    "model_assessment": extraction.get("assessment"),
                    "coverage_summary": {**coverage, "overall_direction": coverage_overall},
                    "passages": extraction.get("passages") or [],
                }
            )
            if (
                stop_after_strong_support
                and coverage_overall == "supports"
                and coverage.get("full_claim_supported")
            ):
                break
        except Exception as exc:  # noqa: BLE001
            candidates.append(
                {
                    **paper,
                    "error_code": _classify_error(exc, "extract"),
                    "error_message": str(exc)[:500],
                    "passages": [],
                }
            )
    # audit-visible semantic skips (never silently dropped)
    for p in semantic_skipped:
        candidates.append(
            {
                **p,
                "error_code": "SEMANTIC_SKIPPED",
                "error_message": p.get("semantic_skip_reason") or "relevance below threshold",
                "passages": [],
            }
        )
    return candidates, last_llm_model


async def _run_batch_loop(session: AsyncSession, task_id: str) -> None:
    cfg = get_settings()
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
                    "SELECT max_papers_per_object, only_oa, stop_after_strong_support, config, mode "
                    "FROM paper_evidence_tasks WHERE id::text=:tid"
                ),
                {"tid": task_id},
            )
        ).first()
        rows = (
            await session.execute(
                text(
                    "SELECT id::text, target_type, target_id::text FROM paper_evidence_task_items "
                    "WHERE task_id::text=:tid AND status='pending' "
                    "AND (next_retry_at IS NULL OR next_retry_at <= now()) "
                    "ORDER BY created_at LIMIT 8 FOR UPDATE SKIP LOCKED"
                ),
                {"tid": task_id},
            )
        ).all()
        if not rows:
            break
        # release FOR UPDATE row locks before workers update rows in their own sessions
        await session.commit()
        max_papers = task_row[0] if task_row else 3
        only_oa = bool(task_row[1]) if task_row else False
        stop_after_strong_support = bool(task_row[2]) if task_row else False
        task_config = task_row[3] if task_row else {}
        task_mode = (task_row[4] if task_row else None) or "function"
        sem_search = asyncio.Semaphore(cfg.paper_search_concurrency)
        sem_fetch = asyncio.Semaphore(cfg.paper_fetch_concurrency)
        deepseek_cfg = (task_config or {}).get("deepseek_concurrency") or cfg.ontology_residual_concurrency
        sem_deepseek = asyncio.Semaphore(int(deepseek_cfg))
        max_retries = cfg.evidence_batch_max_retries
        coros = [
            _process_batch_item_v2(
                task_id=task_id,
                item_id=item_id,
                target_type=tt,
                target_id=oid,
                mode=task_mode,
                max_papers=max_papers,
                only_oa=only_oa,
                stop_after_strong_support=stop_after_strong_support,
                sem_search=sem_search,
                sem_fetch=sem_fetch,
                sem_deepseek=sem_deepseek,
                max_retries=max_retries,
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
    terminal_done = sum(
        status_map.get(s, 0)
        for s in ("awaiting_review", "completed", "skipped")
    )
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
    await _update_task_review_status(session, task_id)
    await session.commit()


async def execute_paper_evidence_batch_background(task_id: str) -> None:
    """Background entrypoint used by BackgroundTasks; recoverable after restart."""
    from app.database import AsyncSessionLocal

    if AsyncSessionLocal is None:
        return
    try:
        await materialize_task_items_background(task_id)
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
    await session.execute(
        text(
            "UPDATE paper_evidence_task_items SET status='pending', updated_at=now() "
            "WHERE status IN ('searching','fetching','retrieving','extracting','verifying') "
            "AND task_id IN (SELECT id FROM paper_evidence_tasks WHERE status='pending')"
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
    await session.execute(
        text(
            "UPDATE paper_evidence_task_items SET status='pending', next_retry_at=NULL, updated_at=now() "
            "WHERE task_id::text=:tid AND status='failed' AND "
            "(next_retry_at IS NULL OR next_retry_at <= now())"
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
            "UPDATE paper_evidence_tasks SET status='cancelled', cancelled_at=now(), "
            "materialization_status='cancelled' "
            "WHERE id::text=:tid AND status IN ('pending','running','paused')"
        ),
        {"tid": task_id},
    )
    await session.execute(
        text(
            "UPDATE paper_evidence_task_items SET status='skipped', last_error_code='CANCELLED', "
            "last_error_message='cancelled by user', last_error_at=now(), updated_at=now() "
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
            "last_error_code=NULL, next_retry_at=NULL, updated_at=now() "
            "WHERE task_id::text=:tid AND status='failed'"
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
                f"created_by, created_at, started_at, finished_at, error_message, "
                f"review_status, name, granularity_level, materialization_status, "
                f"estimated_target_count, materialized_target_count "
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
                "review_status": r[16],
                "name": r[17],
                "granularity_level": r[18],
                "materialization_status": r[19],
                "estimated_target_count": r[20],
                "materialized_target_count": r[21],
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
                "created_at, started_at, finished_at, error_message, review_status, name, "
                "granularity_level, only_oa, confidence_lt, stop_after_strong_support, "
                "scope_type, filter_snapshot, estimated_target_count, materialized_target_count, "
                "materialization_status, materialization_cursor, materialization_error "
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
    status_map = {r[0]: r[1] for r in counts}
    processed = sum(
        status_map.get(s, 0)
        for s in ("awaiting_review", "completed", "skipped", "failed")
    )
    versions = (
        await session.execute(
            text(
                "SELECT preprocessing_version, retrieval_version, prompt_version, llm_model "
                "FROM paper_evidence_task_items WHERE task_id::text=:tid "
                "AND preprocessing_version IS NOT NULL "
                "ORDER BY updated_at DESC LIMIT 1"
            ),
            {"tid": task_id},
        )
    ).first()
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
            "review_status": task[16],
            "name": task[17],
            "granularity_level": task[18],
            "only_oa": task[19],
            "confidence_lt": float(task[20]) if task[20] is not None else None,
            "stop_after_strong_support": task[21],
            "scope_type": task[22],
            "filter_snapshot": task[23],
            "estimated_target_count": task[24],
            "materialized_target_count": task[25],
            "materialization_status": task[26],
            "materialization_cursor": str(task[27]) if task[27] else None,
            "materialization_error": task[28],
            "versions": {
                "preprocessing_version": versions[0] if versions else None,
                "retrieval_version": versions[1] if versions else None,
                "prompt_version": versions[2] if versions else None,
                "llm_model": versions[3] if versions else None,
            },
        },
        "counts": status_map,
        "processed": processed,
    }


async def list_batch_items(
    session: AsyncSession, task_id: str, limit: int = 50, offset: int = 0
) -> dict:
    rows = (
        await session.execute(
            text(
                "SELECT id::text, target_type, target_id::text, status, pmid, title, passage, "
                "direction, confidence, evidence_id::text, error_message, updated_at, label, "
                "current_confidence, passages_json, last_error, retry_count, attempt_count, "
                "last_error_code, last_error_message, preprocess_outcome, paper_id::text, model_direction, "
                "candidate_papers, review_draft, claim_text_snapshot, claim_components_snapshot, "
                "retrieval_version, draft_revision "
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
                "attempt_count": r[17],
                "last_error_code": r[18],
                "last_error_message": r[19],
                "preprocess_outcome": r[20],
                "paper_id": r[21],
                "model_direction": r[22],
                "candidate_papers": r[23],
                "review_draft": r[24],
                "claim_text_snapshot": r[25],
                "claim_components_snapshot": r[26],
                "retrieval_version": r[27],
                "draft_revision": r[28],
            }
            for r in rows
        ]
    }


async def complete_batch_item_reviewed(
    session: AsyncSession,
    task_id: str,
    item_id: str,
    evidence_id: str | None = None,
    operator_id: str | None = None,
) -> dict:
    result = await session.execute(
        text(
            "UPDATE paper_evidence_task_items SET status='completed', reviewed_by=:rb, "
            "evidence_id=:eid, "
            "reviewed_at=now(), updated_at=now() "
            "WHERE task_id::text=:tid AND id::text=:iid AND status='awaiting_review'"
        ),
        {"tid": task_id, "iid": item_id, "rb": operator_id, "eid": evidence_id},
    )
    await session.commit()
    if result.rowcount == 0:
        raise ValueError("item is not awaiting review")
    await _update_task_totals(session, task_id)
    await session.commit()
    await _update_task_review_status(session, task_id)
    await session.commit()
    return {"task_id": task_id, "item_id": item_id, "status": "completed", "evidence_id": evidence_id}


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


# ════════════════════════════════════════════════════════════════════════════
# Phase 4: multi-paper batch preprocessing, error taxonomy, review drafts
# ════════════════════════════════════════════════════════════════════════════

BATCH_RETRYABLE_CODES = {
    "EUROPE_PMC_TIMEOUT",
    "EUROPE_PMC_RATE_LIMIT",
    "PAPER_FETCH_FAILED",
    "OA_PARSE_FAILED",
    "DEEPSEEK_TIMEOUT",
    "DEEPSEEK_PARSE_FAILED",
    "UNKNOWN",
}


def _classify_error(exc: Exception, stage: str) -> str:
    msg = str(exc).lower()
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None and exc.response.status_code == 429:
        return "EUROPE_PMC_RATE_LIMIT"
    if "parse" in msg or "parse_error" in msg:
        return "DEEPSEEK_PARSE_FAILED" if stage == "extract" else "OA_PARSE_FAILED"
    if "timeout" in msg or "timed out" in msg:
        return "DEEPSEEK_TIMEOUT" if stage == "extract" else "EUROPE_PMC_TIMEOUT"
    if "transport" in msg or "connection" in msg or "http" in msg:
        return "PAPER_FETCH_FAILED" if stage == "fetch" else "EUROPE_PMC_TIMEOUT"
    if "no passage" in msg or "no_verified" in msg:
        return "SOURCE_VERIFICATION_FAILED"
    return "UNKNOWN"


def _rank_papers(papers: list[dict], context: dict) -> list[dict]:
    """Paper-level ranking: query/term relevance + OA full text + abstract (no impact factor)."""
    source = (context.get("source_region") or "").lower()
    target = (context.get("target_region") or "").lower()
    functions = [(f or "").lower() for f in (context.get("function_terms") or [])]
    ranked = []
    for p in papers:
        text = f"{p.get('title') or ''} {p.get('abstract') or ''} {p.get('journal') or ''}".lower()
        score = 0
        if source and source in text:
            score += 10
        if target and target in text:
            score += 10
        for fn in functions:
            if fn and fn in text:
                score += 5
        if p.get("fulltext_available"):
            score += 4
        elif p.get("is_open_access"):
            score += 3
        if p.get("abstract"):
            score += 2
        try:
            score += max(0, 2 - (2026 - int(p.get("year") or 0))) * 0.1
        except (TypeError, ValueError):
            pass
        ranked.append({**p, "paper_match_score": round(score, 2)})
    ranked.sort(key=lambda x: (-x["paper_match_score"], str(x.get("year") or "")))
    return ranked


# Connection-evidence vocabulary: papers rarely write "structural_connection";
# they use tractography / projection / fiber / DTI / white matter and specialized
# terms like "thalamostriatal". NOTE: "connectivity" alone is deliberately absent —
# it mostly matches fMRI functional-connectivity papers, which are NOT evidence
# for an anatomical projection. Ordered by generality so the OR-group limit keeps
# the most useful terms.
CONNECTION_EVIDENCE_TERMS = [
    "projection",
    "tractography",
    "fiber",
    "tract",
    "DTI",
    "structural connectivity",
    "white matter",
    "thalamostriatal",
    "thalamo-striatal",
]

# Region synonyms papers actually use: "putamen" is part of the striatum, so
# striatum-only papers (the majority) must also be retrieved.
_REGION_SYNONYM_HINTS = {
    "putamen": ["striatum", "caudate putamen", "neostriatum"],
    "striatum": ["putamen"],
    "thalamus": ["thalamic"],
    "thalamic": ["thalamus"],
}


def _region_search_terms(region: str) -> list[str]:
    core = _core_region_term(region)
    terms = [region, core]
    hints = _REGION_SYNONYM_HINTS.get((core or "").lower(), [])
    return [t for t in dict.fromkeys(terms + hints) if t]

# Lateral/qualifier words stripped when deriving the core region term, so
# "right thalamus proper" searches as "thalamus" too (papers rarely use the full phrase).
_REGION_MODIFIER_WORDS = {
    "right", "left", "proper", "superior", "inferior", "medial", "lateral",
    "anterior", "posterior", "dorsal", "ventral", "caudal", "rostral",
    "central", "deep", "superficial", "primary", "secondary", "bilateral",
    "motor", "related", "gray", "white", "intermediate",
}

# Structural suffixes stripped as well, so "Agranular insular area, posterior
# part, layer 6b" → "Agranular insular" instead of the unwieldy full phrase.
_REGION_STRUCTURAL_WORDS = {
    "layer", "part", "area", "sublayer", "region", "sector", "division",
}


def _core_region_term(region: str) -> str:
    """Derive the core region noun phrase, e.g. 'right thalamus proper' → 'thalamus'.

    Modifiers (right/posterior/...) and structural suffixes (layer/part/area/...)
    are stripped; numeric labels (6b) dropped; a long remainder is trimmed to its
    last 3 words (the distinctive head noun phrase).
    """
    words = [
        w for w in re.split(r"[\s\-,\/]+", region or "")
        if w
        and len(w) > 1
        and not re.fullmatch(r"\d+[a-z]?|\d+", w)
        and w.lower() not in _REGION_MODIFIER_WORDS
        and w.lower() not in _REGION_STRUCTURAL_WORDS
    ]
    if not words:
        return (region or "").strip()
    core = " ".join(words).strip()
    parts = core.split()
    return " ".join(parts[-3:]) if len(parts) > 3 else core


def _build_epmc_query(context: dict, *, abstract_only: bool = True) -> str:
    """Build a Europe PMC query from the retrieval context.

    abstract_only=True (default): all clauses target ABSTRACT — far less noise
    than BODY (where "fiber"/"projection" appear everywhere). Callers fall back
    to abstract_only=False when ABSTRACT-only returns nothing.

    Each concept (source / target / function, canonical + synonyms + core term)
    becomes an OR-group of `ABSTRACT:"term"` (or `OR BODY:"term"`) clauses joined
    with AND. Connection-type objects also OR in the connection-evidence
    vocabulary (tractography / fiber / projection / ...) instead of requiring
    the rare exact phrase "structural_connection".
    """
    def group(terms: list[str], limit: int = 4) -> str | None:
        clauses: list[str] = []
        seen: set[str] = set()
        for t in terms:
            t = (t or "").strip().strip('"')
            key = t.lower()
            if t and len(t) <= 80 and key not in ("unknown", "none") and key not in seen:
                seen.add(key)
                clauses.append(f'ABSTRACT:"{t}"')
                if not abstract_only:
                    clauses.append(f'BODY:"{t}"')
            if len(clauses) // (1 if abstract_only else 2) >= limit:
                break
        return "(" + " OR ".join(clauses) + ")" if clauses else None

    src = context.get("source_region") or ""
    tgt = context.get("target_region") or ""
    parts: list[str] = []
    src_group = group(
        _region_search_terms(src)
        + (context.get("source_region_synonyms") or [])
    )
    tgt_group = group(
        _region_search_terms(tgt)
        + (context.get("target_region_synonyms") or [])
    )
    if src_group:
        parts.append(src_group)
    if tgt_group:
        parts.append(tgt_group)
    fn_terms = list((context.get("function_terms") or []) + (context.get("function_synonyms") or []))
    if context.get("object_type") in ("connection", "projection") or context.get("relation_keywords"):
        fn_terms = fn_terms + CONNECTION_EVIDENCE_TERMS
    fn = group(fn_terms, limit=6)
    if fn:
        parts.append(fn)
    return " AND ".join(parts)


async def _set_item_stage(session: AsyncSession, item_id: str, status: str, **extra) -> None:
    sets = "status=:st, updated_at=now()"
    params: dict = {"iid": item_id, "st": status}
    for key, value in extra.items():
        if isinstance(value, str) and value.startswith("SQL:"):
            sets += f", {key}={value[4:]}"
        elif isinstance(value, (dict, list)):
            sets += f", {key}=CAST(:p_{key} AS jsonb)"
            params[f"p_{key}"] = json.dumps(value, ensure_ascii=False)
        else:
            sets += f", {key}=:p_{key}"
            params[f"p_{key}"] = value
    await session.execute(text(f"UPDATE paper_evidence_task_items SET {sets} WHERE id::text=:iid"), params)
    await session.commit()


async def _save_item_candidates(
    session: AsyncSession,
    item_id: str,
    candidates: list[dict],
) -> None:
    """Persist candidate papers + draft passages (review-only, never formal evidence)."""
    await session.execute(
        text(
            "UPDATE paper_evidence_task_items SET candidate_papers=CAST(:cp AS jsonb), "
            "model_direction=:md, model_assessment=:ma, coverage_summary=CAST(:cs AS jsonb), "
            "updated_at=now() WHERE id::text=:iid"
        ),
        {
            "iid": item_id,
            "cp": json.dumps(candidates, ensure_ascii=False),
            "md": candidates[0].get("model_direction") if candidates else None,
            "ma": candidates[0].get("model_assessment") if candidates else None,
            "cs": json.dumps(candidates[0].get("coverage_summary") or {}, ensure_ascii=False) if candidates else "{}",
        },
    )
    await session.execute(
        text("DELETE FROM paper_evidence_task_item_passages WHERE task_item_id=:iid"),
        {"iid": item_id},
    )
    rank = 0
    for cand in candidates:
        for p in cand.get("passages") or []:
            rank += 1
            await session.execute(
                text(
                    "INSERT INTO paper_evidence_task_item_passages "
                    "(task_item_id, paper_id, paper_passage_id, paragraph_id, passage_text_snapshot, "
                    "translation_zh, direction, evidence_level, supported_components, reason, "
                    "semantic_confidence, source_verified, source_verification_method, rank, is_recommended) "
                    "VALUES (:iid, :paper_id, :ppid, :pid, :txt, :trans, :dir, :lvl, "
                    "CAST(:sc AS jsonb), :reason, :conf, :sv, :method, :rank, :rec)"
                ),
                {
                    "iid": item_id,
                    "paper_id": uuid.UUID(p["paper_id"]) if p.get("paper_id") else None,
                    "ppid": p.get("paper_passage_id"),
                    "pid": p.get("paragraph_id"),
                    "txt": p.get("passage") or "",
                    "trans": None,
                    "dir": p.get("direction") or "supports",
                    "lvl": p.get("evidence_level") or "indirect",
                    "sc": json.dumps(p.get("supported_components") or [], ensure_ascii=False),
                    "reason": p.get("reason") or "",
                    "conf": p.get("semantic_confidence") or p.get("confidence"),
                    "sv": bool(p.get("source_verified")),
                    "method": p.get("source_verification_method"),
                    "rank": rank,
                    "rec": rank == 1,
                },
            )
    await session.commit()


async def _process_batch_item_v2(
    *,
    task_id: str,
    item_id: str,
    target_type: str,
    target_id: str,
    mode: str,
    max_papers: int,
    only_oa: bool,
    stop_after_strong_support: bool,
    sem_search: asyncio.Semaphore,
    sem_fetch: asyncio.Semaphore,
    sem_deepseek: asyncio.Semaphore,
    max_retries: int,
) -> None:
    from app.database import AsyncSessionLocal

    if AsyncSessionLocal is None:
        return
    async with AsyncSessionLocal() as session:
        stage = "search"
        try:
            context = await build_retrieval_context(
                session, target_type, uuid.UUID(target_id), mode=mode
            )
            await _set_item_stage(
                session, item_id, "searching",
                started_at="SQL:COALESCE(started_at, now())",
                attempt_count="SQL:attempt_count + 1",
                search_query=context.get("claim_text") or "",
                claim_version=context.get("claim_version") or "claim_v1",
                claim_text_snapshot=context.get("claim_text") or "",
                claim_components_snapshot=context.get("claim_components") or [],
            )
            query = await build_search_query(
                session, target_type, uuid.UUID(target_id), mode=mode
            )
            async with sem_search:
                papers = await _search_with_retry(query, limit=max(10, max_papers * 3))
            if not papers:
                # ABSTRACT-only missed everything → retry with BODY-inclusive query
                wide_query = await build_search_query(
                    session, target_type, uuid.UUID(target_id), mode=mode, abstract_only=False
                )
                if wide_query and wide_query != query:
                    async with sem_search:
                        papers = await _search_with_retry(wide_query, limit=max(10, max_papers * 3))
                    if papers:
                        query = wide_query
            if not papers:
                await _set_item_stage(
                    session, item_id, "awaiting_review",
                    preprocess_outcome="no_evidence_found",
                    last_error_code="EUROPE_PMC_NO_RESULT",
                    last_error_message="no papers matched the query",
                    last_error_at="SQL:now()",
                    finished_preprocessing_at="SQL:now()",
                )
                return
            ranked = _rank_papers(papers, context)
            selected = ranked[:max_papers]
            kept, semantic_skipped = await semantic_filter_papers(selected, context)
            candidates: list[dict] = []
            last_llm_model: str | None = None
            for paper in kept:
                pmid = (paper.get("pmid") or "").strip()
                if not pmid:
                    continue
                stage = "fetch"
                await _set_item_stage(session, item_id, "fetching")
                async with sem_fetch:
                    meta = await _verify_paper_with_retry(pmid)
                    if meta is None:
                        continue
                    xml_text = await pfs.fetch_oa_fulltext_xml(
                        pmid=pmid, pmcid=meta.get("pmcid") or paper.get("pmcid") or ""
                    )
                if only_oa and not meta.get("is_open_access"):
                    continue
                abstract = (meta.get("abstract") or "").strip()
                paper_source = await ensure_paper_source(
                    session,
                    {**meta, "abstract": abstract, "fulltext": ""},
                )
                stage = "retrieve"
                await _set_item_stage(session, item_id, "retrieving")
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
                ranked_paras = score_paragraphs(
                    all_paragraphs,
                    source_region=context.get("source_region") or "",
                    target_region=context.get("target_region") or "",
                    source_region_synonyms=context.get("source_region_synonyms") or [],
                    target_region_synonyms=context.get("target_region_synonyms") or [],
                    function_terms=context.get("function_terms") or [],
                    function_synonyms=context.get("function_synonyms") or [],
                    relation_keywords=context.get("relation_keywords") or [],
                )
                windows = build_windows(ranked_paras, all_paragraphs)
                stage = "extract"
                await _set_item_stage(session, item_id, "extracting")
                async with sem_deepseek:
                    extraction = await _extract_from_paper_with_retry(
                        claim=context,
                        title=meta.get("title") or paper.get("title") or "",
                        windows=windows,
                    )
                last_llm_model = extraction.get("llm_model")
                stage = "verify"
                await _set_item_stage(session, item_id, "verifying")
                coverage = compute_coverage_summary(
                    context.get("claim_components") or [],
                    extraction.get("passages") or [],
                )
                coverage_overall = aggregate_overall_direction(
                    coverage, extraction.get("passages") or []
                )
                passage_id_map: dict[str, uuid.UUID] = {}
                for p in extraction.get("passages") or []:
                    p["paper_id"] = str(paper_source.id)
                    if p.get("source_verified"):
                        hash_rows = (
                            await session.execute(
                                text(
                                    "SELECT id FROM paper_passages WHERE paper_id=:pid AND text_hash=:h"
                                ),
                                {"pid": paper_source.id, "h": passage_hash(p.get("passage") or "")},
                            )
                        ).first()
                        p["paper_passage_id"] = str(hash_rows[0]) if hash_rows else None
                candidates.append(
                    {
                        "paper_id": str(paper_source.id),
                        "pmid": pmid,
                        "doi": meta.get("doi") or "",
                        "title": meta.get("title") or "",
                        "journal": meta.get("journal") or "",
                        "year": meta.get("year") or "",
                        "is_oa": bool(meta.get("is_open_access")),
                        "paper_match_score": paper.get("paper_match_score", 0),
                        "model_direction": extraction.get("overall_direction"),
                        "model_assessment": extraction.get("assessment"),
                        "coverage_summary": {**coverage, "overall_direction": coverage_overall},
                        "passages": extraction.get("passages") or [],
                    }
                )
                if (
                    stop_after_strong_support
                    and coverage_overall == "supports"
                    and coverage.get("full_claim_supported")
                ):
                    break
            # audit-visible semantic skips (never silently dropped)
            for p in semantic_skipped:
                candidates.append(
                    {
                        **p,
                        "error_code": "SEMANTIC_SKIPPED",
                        "error_message": p.get("semantic_skip_reason") or "relevance below threshold",
                        "passages": [],
                    }
                )
            await _save_item_candidates(session, item_id, candidates)
            verified_any = any(
                p.get("source_verified")
                for cand in candidates
                for p in cand.get("passages") or []
            )
            await _set_item_stage(
                session, item_id, "awaiting_review",
                preprocess_outcome="evidence_found" if verified_any else "no_evidence_found",
                last_error_code=None if verified_any else "NO_RELEVANT_PASSAGE",
                last_error_message=None if verified_any else "no verified passage across candidates",
                last_error_at=None if verified_any else "SQL:now()",
                finished_preprocessing_at="SQL:now()",
                paper_id=uuid.UUID(candidates[0]["paper_id"]) if candidates else None,
                preprocessing_version=PAPER_EVIDENCE_PREPROCESS_VERSION,
                retrieval_version=PAPER_PASSAGE_RETRIEVAL_VERSION,
                prompt_version=PAPER_EVIDENCE_EXTRACTION_PROMPT_VERSION,
                llm_model=last_llm_model,
            )
        except Exception as exc:  # noqa: BLE001
            code = _classify_error(exc, stage)
            try:
                with open("diag_v2.log", "a", encoding="utf-8") as f:
                    f.write(f"[{item_id}] stage={stage} code={code} err={str(exc)[:300]}\n")
            except Exception:
                pass
            try:
                async with AsyncSessionLocal() as err_session:
                    row = (
                        await err_session.execute(
                            text("SELECT attempt_count FROM paper_evidence_task_items WHERE id::text=:iid"),
                            {"iid": item_id},
                        )
                    ).first()
                    attempts = (row[0] if row else 0) or 0
                    if code in BATCH_RETRYABLE_CODES and attempts < max_retries:
                        await err_session.execute(
                            text(
                                "UPDATE paper_evidence_task_items SET status='pending', "
                                "last_error_code=:code, last_error_message=:msg, last_error_at=now(), "
                                "next_retry_at=now() + make_interval(secs => :backoff), "
                                "updated_at=now() WHERE id::text=:iid"
                            ),
                            {
                                "iid": item_id,
                                "code": code,
                                "msg": str(exc)[:500],
                                "backoff": min(60, (2 ** attempts) * 5),
                            },
                        )
                    else:
                        await err_session.execute(
                            text(
                                "UPDATE paper_evidence_task_items SET status='failed', "
                                "last_error_code=:code, last_error_message=:msg, last_error_at=now(), "
                                "next_retry_at=NULL, updated_at=now() WHERE id::text=:iid"
                            ),
                            {"iid": item_id, "code": code, "msg": str(exc)[:500]},
                        )
                    await err_session.commit()
            except Exception:  # noqa: BLE001
                await err_session.rollback()


async def _resolve_scope_ids_low_confidence(
    session: AsyncSession,
    target_type: str,
    confidence_lt: float | None,
    limit: int,
) -> list[str]:
    table = TARGET_MODELS.get(target_type)
    if table is None:
        raise ValueError(f"unsupported target_type: {target_type}")
    threshold = confidence_lt if confidence_lt is not None else 0.5
    rows = (
        await session.execute(
            text(
                f"SELECT id::text FROM {table.__tablename__} "
                "WHERE confidence < :thr ORDER BY confidence ASC LIMIT :lim"
            ),
            {"thr": threshold, "lim": limit},
        )
    ).all()
    return [str(r[0]) for r in rows]


async def _update_task_review_status(session: AsyncSession, task_id: str) -> None:
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
    awaiting = status_map.get("awaiting_review", 0)
    done = status_map.get("completed", 0)
    pending_active = sum(status_map.get(s, 0) for s in ("pending", "searching", "fetching", "retrieving", "extracting", "verifying"))
    if awaiting == 0 and done == 0 and pending_active == 0:
        review_status = "not_started"
    elif awaiting == 0 and done > 0 and pending_active == 0:
        review_status = "completed"
    else:
        review_status = "in_review"
    await session.execute(
        text("UPDATE paper_evidence_tasks SET review_status=:rs WHERE id::text=:tid"),
        {"tid": task_id, "rs": review_status},
    )


async def get_task_item_draft(session: AsyncSession, item_id: str) -> dict:
    row = (
        await session.execute(
            text(
                "SELECT review_draft, candidate_papers, passages_json, target_type, target_id::text, "
                "status, preprocess_outcome, model_direction, model_assessment, coverage_summary, "
                "paper_id::text, claim_text_snapshot, claim_components_snapshot "
                "FROM paper_evidence_task_items WHERE id::text=:iid"
            ),
            {"iid": item_id},
        )
    ).first()
    if row is None:
        raise ValueError("task item not found")
    return {
        "item_id": item_id,
        "status": row[5],
        "preprocess_outcome": row[6],
        "target_type": row[2],
        "target_id": row[3],
        "model_direction": row[7],
        "model_assessment": row[8],
        "coverage_summary": row[9],
        "paper_id": row[10],
        "claim_text_snapshot": row[11],
        "claim_components_snapshot": row[12],
        "review_draft": row[0],
        "candidate_papers": row[1],
    }


async def save_task_item_draft(
    session: AsyncSession,
    item_id: str,
    draft: dict,
    operator_id: str | None = None,
    revision: int = 0,
) -> dict:
    row = (
        await session.execute(
            text(
                "UPDATE paper_evidence_task_items SET review_draft=CAST(:d AS jsonb), "
                "draft_revision=:rev, updated_at=now() "
                "WHERE id::text=:iid AND (draft_revision IS NULL OR draft_revision <= :rev) "
                "RETURNING id::text"
            ),
            {"iid": item_id, "d": json.dumps(draft, ensure_ascii=False), "rev": revision},
        )
    ).first()
    await session.commit()
    if row is None:
        raise ValueError("stale draft revision rejected (a newer draft already saved)")
    await _write_audit(
        session,
        action_type="EVIDENCE_REVIEW_DRAFT_SAVED",
        entity_type="evidence_task_item",
        entity_id=uuid.UUID(item_id),
        after_data={"draft_keys": sorted(draft.keys())},
        operator_id=operator_id,
        reason="review draft saved",
    )
    await session.commit()
    return {"item_id": item_id, "saved": True, "server_revision": revision}


async def validate_passage_selection(
    session: AsyncSession, paper_passage_id: uuid.UUID, selected_text: str
) -> dict:
    row = (
        await session.execute(
            text(
                "SELECT passage_text FROM paper_passages WHERE id=:pid"
            ),
            {"pid": paper_passage_id},
        )
    ).first()
    if row is None:
        raise ValueError("paper passage not found")
    source = row[0] or ""
    verified, method = verify_passage_against_source(selected_text, source)
    if not verified:
        return {
            "source_verified": False,
            "verification_method": None,
            "normalized_selection": None,
            "char_start": None,
            "char_end": None,
        }
    char_start = source.find(selected_text)
    return {
        "source_verified": True,
        "verification_method": method,
        "normalized_selection": re.sub(r"\s+", " ", selected_text).strip(),
        "char_start": char_start if char_start >= 0 else None,
        "char_end": char_start + len(selected_text) if char_start >= 0 else None,
    }


# ════════════════════════════════════════════════════════════════════════════
# Phase 4 closure: filter snapshot, async materializer, version metadata,
# draft optimistic concurrency.
# ════════════════════════════════════════════════════════════════════════════

PAPER_EVIDENCE_PREPROCESS_VERSION = "paper_evidence_preprocess_v1"
PAPER_PASSAGE_RETRIEVAL_VERSION = "paper_passage_retrieval_v1"
PAPER_EVIDENCE_EXTRACTION_PROMPT_VERSION = "paper_evidence_extract_v2"


def _build_filter_clause(target_type: str, snapshot: dict | None) -> tuple[str, dict]:
    table = TARGET_MODELS.get(target_type)
    if table is None:
        raise ValueError(f"unsupported target_type: {target_type}")
    where = ["1=1"]
    params: dict = {}
    snapshot = snapshot or {}
    conf = snapshot.get("confidence_lt")
    if conf is not None:
        where.append("confidence < :conf")
        params["conf"] = float(conf)
    gran = snapshot.get("granularity_level")
    if gran:
        where.append("granularity_level = :gran")
        params["gran"] = gran
    search = snapshot.get("search")
    if search:
        where.append("(source_region_name_en ILIKE :q OR target_region_name_en ILIKE :q OR function_term ILIKE :q)")
        params["q"] = f"%{search}%"
    return " AND ".join(where), params


async def count_scope_targets(
    session: AsyncSession, target_type: str, filter_snapshot: dict | None
) -> int:
    table = TARGET_MODELS.get(target_type)
    if table is None:
        raise ValueError(f"unsupported target_type: {target_type}")
    where, params = _build_filter_clause(target_type, filter_snapshot)
    return int(
        (
            await session.execute(
                text(f"SELECT COUNT(*) FROM {table.__tablename__} WHERE {where}"),
                params,
            )
        ).scalar_one()
    )


async def preview_batch_scope(
    session: AsyncSession,
    *,
    target_type: str,
    filter_snapshot: dict | None = None,
    scope: str = "filter",
    selected_ids: list[str] | None = None,
) -> dict:
    cfg = get_settings()
    if scope == "selected":
        estimate = len(selected_ids or [])
    else:
        estimate = await count_scope_targets(session, target_type, filter_snapshot)
    max_items = cfg.paper_evidence_max_task_items
    return {
        "estimated_target_count": estimate,
        "max_task_items": max_items,
        "over_limit": estimate > max_items,
        "message": (
            f"当前筛选结果共 {estimate} 条，单任务最大 {max_items} 条，请进一步筛选或拆分任务。"
            if estimate > max_items
            else None
        ),
    }


async def _materialize_page(
    session: AsyncSession,
    *,
    task_id: str,
    target_type: str,
    filter_snapshot: dict | None,
    cursor: uuid.UUID | None,
    batch_size: int,
    selected_ids: list[str] | None = None,
) -> tuple[int, uuid.UUID | None]:
    """Materialize one keyset page; returns (inserted_count, next_cursor)."""
    table = TARGET_MODELS.get(target_type)
    if table is None:
        raise ValueError(f"unsupported target_type: {target_type}")
    if selected_ids is not None:
        rows = (
            await session.execute(
                text(
                    f"SELECT id FROM {table.__tablename__} WHERE id::text = ANY(:ids) "
                    "ORDER BY id LIMIT :lim"
                ),
                {"ids": selected_ids, "lim": batch_size},
            )
        ).all()
        page_ids = [r[0] for r in rows]
        next_cursor = None
    else:
        where, params = _build_filter_clause(target_type, filter_snapshot)
        if cursor is not None:
            where += " AND id > :cur"
            params["cur"] = cursor
        params["lim"] = batch_size
        rows = (
            await session.execute(
                text(
                    f"SELECT id FROM {table.__tablename__} WHERE {where} "
                    "ORDER BY id LIMIT :lim"
                ),
                params,
            )
        ).all()
        page_ids = [r[0] for r in rows]
        next_cursor = page_ids[-1] if page_ids else None
    if not page_ids:
        return 0, next_cursor
    inserted = 0
    for oid in page_ids:
        result = await session.execute(
            text(
                "INSERT INTO paper_evidence_task_items "
                "(task_id, target_type, target_id, label, current_confidence, status) "
                "SELECT CAST(:tid AS uuid), CAST(:tt AS varchar), t.id, CAST(:lbl AS varchar), :conf, 'pending' "
                "FROM unnest(ARRAY[:oid]::uuid[]) t(id) "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM paper_evidence_task_items a "
                "  WHERE a.target_type = CAST(:tt AS varchar) AND a.target_id=t.id "
                "  AND a.status NOT IN ('completed','skipped','failed','cancelled')"
                ") "
                "ON CONFLICT (task_id, target_type, target_id) DO NOTHING"
            ),
            {
                "tid": task_id,
                "tt": target_type,
                "oid": oid,
                "lbl": str(oid),
                "conf": None,
            },
        )
        inserted += result.rowcount or 0
    return inserted, next_cursor


async def materialize_task_items_background(task_id: str) -> None:
    from app.database import AsyncSessionLocal

    if AsyncSessionLocal is None:
        return
    cfg = get_settings()
    async with AsyncSessionLocal() as session:
        try:
            task = (
                await session.execute(
                    text(
                        "SELECT target_type, scope, scope_type, filter_snapshot, materialization_status, "
                        "materialization_cursor, materialized_target_count "
                        "FROM paper_evidence_tasks WHERE id::text=:tid"
                    ),
                    {"tid": task_id},
                )
            ).first()
            if task is None:
                return
            if task[4] == "completed":
                return
            state = (
                await session.execute(
                    text("SELECT status FROM paper_evidence_tasks WHERE id::text=:tid"),
                    {"tid": task_id},
                )
            ).scalar_one_or_none()
            if state == "cancelled":
                await session.execute(
                    text(
                        "UPDATE paper_evidence_tasks SET materialization_status='cancelled' "
                        "WHERE id::text=:tid"
                    ),
                    {"tid": task_id},
                )
                await session.commit()
                return
            await session.execute(
                text(
                    "UPDATE paper_evidence_tasks SET materialization_status='running', "
                    "materialized_target_count=COALESCE(materialized_target_count,0) WHERE id::text=:tid"
                ),
                {"tid": task_id},
            )
            await session.commit()
            target_type = task[0]
            snapshot = task[3]
            cursor = task[5]
            selected_ids = None
            if task[2] == "selected":
                selected_ids = (snapshot or {}).get("target_ids") or []
            while True:
                state = (
                    await session.execute(
                        text("SELECT status FROM paper_evidence_tasks WHERE id::text=:tid"),
                        {"tid": task_id},
                    )
                ).scalar_one_or_none()
                if state in ("cancelled", "paused"):
                    break
                inserted, next_cursor = await _materialize_page(
                    session,
                    task_id=task_id,
                    target_type=target_type,
                    filter_snapshot=snapshot,
                    cursor=cursor,
                    batch_size=cfg.paper_evidence_materialize_batch_size,
                    selected_ids=selected_ids,
                )
                if next_cursor is None and selected_ids is None:
                    await session.execute(
                        text(
                            "UPDATE paper_evidence_tasks SET materialization_status='completed', "
                            "materialization_cursor=NULL, "
                            "materialized_target_count=(SELECT COUNT(*) FROM paper_evidence_task_items "
                            "WHERE task_id::text=:tid) WHERE id::text=:tid"
                        ),
                        {"tid": task_id},
                    )
                    await session.commit()
                    break
                if inserted == 0 and next_cursor == cursor and selected_ids is None:
                    await session.execute(
                        text(
                            "UPDATE paper_evidence_tasks SET materialization_status='completed', "
                            "materialization_cursor=NULL WHERE id::text=:tid"
                        ),
                        {"tid": task_id},
                    )
                    await session.commit()
                    break
                cursor = next_cursor
                await session.execute(
                    text(
                        "UPDATE paper_evidence_tasks SET materialization_cursor=:cur, "
                        "materialized_target_count=materialized_target_count + :inc, "
                        "materialization_status=CASE WHEN :sel THEN 'completed' ELSE 'running' END "
                        "WHERE id::text=:tid"
                    ),
                    {
                        "tid": task_id,
                        "cur": cursor,
                        "inc": inserted,
                        "sel": selected_ids is not None,
                    },
                )
                await session.commit()
        except Exception as exc:  # noqa: BLE001
            try:
                await session.execute(
                    text(
                        "UPDATE paper_evidence_tasks SET materialization_status='failed', "
                        "materialization_error=:err WHERE id::text=:tid"
                    ),
                    {"tid": task_id, "err": str(exc)[:500]},
                )
                await session.commit()
            except Exception:  # noqa: BLE001
                await session.rollback()


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
    name: str | None = None,
    granularity_level: str | None = None,
    only_oa: bool = False,
    confidence_lt: float | None = None,
    stop_after_strong_support: bool = False,
    target_ids: list[str] | None = None,
    filter_snapshot: dict | None = None,
) -> dict:
    """Create task + structured scope snapshot. Items materialized async (small sync)."""
    if target_type not in TARGET_MODELS:
        raise ValueError(f"unsupported target_type: {target_type}")
    cfg = get_settings()
    scope_type = "selected" if scope == "selected" else "filter"
    if scope == "selected":
        snapshot = {
            "target_type": target_type,
            "granularity_level": granularity_level,
            "target_ids": target_ids or [],
        }
        estimate = len(target_ids or [])
        if target_ids:
            active = set(
                (
                    await session.execute(
                        text(
                            "SELECT target_id::text FROM paper_evidence_task_items "
                            "WHERE target_type=:tt AND target_id::text = ANY(:ids) "
                            "AND status IN ('pending','searching','fetching','retrieving','extracting','verifying','awaiting_review')"
                        ),
                        {"tt": target_type, "ids": target_ids},
                    )
                ).scalars().all()
            )
            if active and active == set(target_ids):
                raise ValueError("all matched targets already have an active evidence task")
    else:
        snapshot = filter_snapshot or {
            "target_type": target_type,
            "granularity_level": granularity_level,
            "confidence_lt": confidence_lt if scope == "low_confidence" else None,
        }
        estimate = await count_scope_targets(session, target_type, snapshot)
    if estimate > cfg.paper_evidence_max_task_items:
        raise ValueError(
            f"当前筛选结果共 {estimate} 条，单任务最大 {cfg.paper_evidence_max_task_items} 条，"
            "请进一步筛选或拆分任务。"
        )
    task_id = (
        await session.execute(
            text(
                "INSERT INTO paper_evidence_tasks "
                "(target_type, scope, scope_type, mode, max_papers_per_object, status, created_by, "
                "total_items, config, name, granularity_level, only_oa, confidence_lt, "
                "stop_after_strong_support, review_status, filter_snapshot, estimated_target_count, "
                "materialization_status) "
                "VALUES (:tt, :scope, :scope_type, :mode, :maxp, :status, :cb, :total, CAST(:cfg AS jsonb), "
                ":name, :gl, :only_oa, :clt, :stop, 'not_started', CAST(:fs AS jsonb), :est, 'pending') "
                "RETURNING id::text"
            ),
            {
                "tt": target_type,
                "scope": scope,
                "scope_type": scope_type,
                "mode": mode,
                "maxp": max_papers_per_object,
                "status": "paused" if start_paused else "pending",
                "cb": created_by,
                "total": estimate,
                "cfg": json.dumps(
                    {"deepseek_concurrency": DEEPSEEK_CONCURRENCY, "europepmc_concurrency": EUROPE_PMC_CONCURRENCY},
                    ensure_ascii=False,
                ),
                "name": name,
                "gl": granularity_level,
                "only_oa": only_oa,
                "clt": confidence_lt,
                "stop": stop_after_strong_support,
                "fs": json.dumps(snapshot, ensure_ascii=False),
                "est": estimate,
            },
        )
    ).scalar_one()
    await session.commit()
    await _write_audit(
        session,
        action_type="EVIDENCE_TASK_CREATE",
        entity_type="evidence_task",
        entity_id=uuid.UUID(task_id),
        after_data={
            "target_type": target_type,
            "scope_type": scope_type,
            "estimated_target_count": estimate,
            "filter_snapshot": snapshot,
        },
        operator_id=created_by,
        reason="batch evidence task created",
    )
    await session.commit()
    return {
        "task_id": task_id,
        "target_count": estimate,
        "skipped_active_targets": 0,
        "auto_started": not start_paused,
    }


# ---- Paper Library (read-only) ----


async def list_papers(
    session: AsyncSession,
    *,
    search: str = "",
    oa: bool | None = None,
    year: int | None = None,
    has_fulltext: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Paper Library: paginated read-only list over paper_sources."""
    where = ["1=1"]
    params: dict = {}
    if search:
        where.append("(title ILIKE :q OR journal ILIKE :q OR pmid ILIKE :q OR doi ILIKE :q)")
        params["q"] = f"%{search}%"
    if oa is not None:
        where.append("is_oa = :oa")
        params["oa"] = oa
    if year is not None:
        where.append("publication_year = :yr")
        params["yr"] = year
    if has_fulltext is not None:
        where.append("fulltext_available = :ft")
        params["ft"] = has_fulltext
    clause = " AND ".join(where)
    params["lim"] = page_size
    params["off"] = (max(1, page) - 1) * page_size
    rows = (
        await session.execute(
            text(
                f"SELECT ps.id, ps.pmid, ps.pmcid, ps.doi, ps.title, ps.journal, "
                f"ps.publication_year, ps.is_oa, ps.abstract_available, ps.fulltext_available, "
                f"(SELECT COUNT(*) FROM paper_passages pp WHERE pp.paper_id = ps.id) AS paragraph_count, "
                f"(SELECT COUNT(*) FROM mirror_evidence_records er WHERE er.paper_id = ps.id) AS evidence_count "
                f"FROM paper_sources ps WHERE {clause} ORDER BY ps.fetched_at DESC NULLS LAST "
                f"LIMIT :lim OFFSET :off"
            ),
            params,
        )
    ).all()
    total = (
        await session.execute(text(f"SELECT COUNT(*) FROM paper_sources WHERE {clause}"), params)
    ).scalar_one()
    return {
        "items": [
            {
                "id": str(r[0]),
                "pmid": r[1],
                "pmcid": r[2],
                "doi": r[3],
                "title": r[4],
                "journal": r[5],
                "publication_year": r[6],
                "is_oa": bool(r[7]),
                "abstract_available": bool(r[8]),
                "fulltext_available": bool(r[9]),
                "paragraph_count": int(r[10] or 0),
                "evidence_count": int(r[11] or 0),
            }
            for r in rows
        ],
        "total": int(total),
    }


async def get_paper_detail(session: AsyncSession, paper_id: uuid.UUID) -> dict:
    """Paper Library detail: metadata + paragraphs + linked evidence targets."""
    row = (
        await session.execute(
            text(
                "SELECT id, source, pmid, pmcid, doi, title, journal, publication_year, "
                "is_oa, abstract_available, fulltext_available, metadata_json "
                "FROM paper_sources WHERE id = :pid"
            ),
            {"pid": paper_id},
        )
    ).first()
    if row is None:
        raise ValueError("paper not found")
    paragraphs = (
        await session.execute(
            text(
                "SELECT paragraph_id, section_title, paragraph_index, passage_text, source_scope "
                "FROM paper_passages WHERE paper_id = :pid ORDER BY paragraph_index"
            ),
            {"pid": paper_id},
        )
    ).all()
    evidence = (
        await session.execute(
            text(
                "SELECT evidence_target_type, evidence_target_id FROM mirror_evidence_records "
                "WHERE paper_id = :pid AND verification_status IN ('human_verified','ai_extracted')"
            ),
            {"pid": paper_id},
        )
    ).all()
    return {
        "paper": {
            "id": str(row[0]),
            "source": row[1],
            "pmid": row[2],
            "pmcid": row[3],
            "doi": row[4],
            "title": row[5],
            "journal": row[6],
            "publication_year": row[7],
            "is_oa": bool(row[8]),
            "abstract_available": bool(row[9]),
            "fulltext_available": bool(row[10]),
            "metadata_json": row[11],
        },
        "paragraphs": [
            {
                "paragraph_id": p[0],
                "section_title": p[1],
                "paragraph_index": p[2],
                "passage_text": p[3],
                "source_scope": p[4],
            }
            for p in paragraphs
        ],
        "evidence_count": len(evidence),
        "targets": [{"target_type": t[0], "target_id": str(t[1])} for t in evidence],
    }


# ════════════════════════════════════════════════════════════════════════════
# Review/Promotion Lifecycle (Phase 1: paper_evidence_reviews)
# ════════════════════════════════════════════════════════════════════════════


async def _map_review_passage(p: dict, review_id: uuid.UUID, rank: int) -> dict:
    """Convert a raw passage dict to a review_passages row params dict."""
    return {
        "rid": review_id,
        "ppid": p.get("paper_passage_id") or p.get("paperPassageId"),
        "pt": p.get("passage_text") or p.get("passage") or "",
        "pts": p.get("passage_text_snapshot") or p.get("passage_text") or p.get("passage") or "",
        "ss": p.get("source_scope"),
        "st": p.get("section_title"),
        "pi": p.get("paragraph_index"),
        "pid": p.get("paragraph_id"),
        "tz": p.get("translation_zh"),
        "dir": p.get("direction"),
        "el": p.get("evidence_level"),
        "reason": p.get("reason"),
        "conf": p.get("confidence"),
        "sc": p.get("semantic_confidence") or p.get("confidence"),
        "sl": p.get("source_locator"),
        "sv": bool(p.get("source_verified", False)),
        "svm": p.get("source_verification_method"),
        "scm": json.dumps(list(p.get("supported_components") or []), ensure_ascii=False),
        "ph": p.get("passage_hash") or passage_hash(p.get("passage") or p.get("passage_text") or ""),
        "rank": rank,
        "is_sel": bool(p.get("is_selected", True)),
    }


async def build_review(
    session: AsyncSession,
    *,
    target_type: str,
    target_id: uuid.UUID,
    paper_id: uuid.UUID | None,
    task_id: uuid.UUID | None,
    task_item_id: uuid.UUID | None,
    reviewer_id: str | None,
    claim_version: str,
    claim_text_snapshot: str,
    claim_components_snapshot: list[dict],
    model_direction: str | None,
    model_assessment: str | None,
    reviewer_direction: str,
    reviewer_evidence_level: str,
    reviewer_confidence: float,
    reviewer_note: str | None,
    coverage_summary_snapshot: dict,
    coverage_formula_version: str,
    draft_revision: int,
    passages: list[dict],
) -> dict:
    """Create a formal review record from reviewer decision + frozen passages.

    Returns {review_id, status: 'awaiting_review'|'rejected'}.
    Side effect: never writes mirror_evidence_records, never modifies confidence.
    promotion_status is always 'not_ready' -- approve_review() must be called
    explicitly to advance to 'awaiting_promotion'.
    """
    # Determine review_status from reviewer_direction.
    # 'approved' is reserved for approve_review() — build_review enters
    # 'awaiting_review' so the explicit approve step is mandatory.
    review_status = (
        "awaiting_review"
        if reviewer_direction not in ("not_found",)
        else "rejected"
    )
    review_id = (
        await session.execute(
            text(
                "INSERT INTO paper_evidence_reviews "
                "(target_type, target_id, paper_id, task_id, task_item_id, reviewer_id, "
                "review_status, promotion_status, claim_version, claim_text_snapshot, "
                "claim_components_snapshot, model_direction, model_assessment, "
                "reviewer_direction, reviewer_evidence_level, reviewer_confidence, "
                "reviewer_note, coverage_summary_snapshot, coverage_formula_version, "
                "draft_revision, reviewed_at, approved_at, rejected_at) "
                "VALUES (:tt, :tid, :pid, :taskid, :itemid, :rev_id, :rstatus, :pstatus, "
                ":cv, :cs, CAST(:cc AS jsonb), :md, :ma, :rd, :rel, :rc, :rn, "
                "CAST(:cov AS jsonb), :cfv, :dr, now(), "
                "CASE WHEN :is_approved THEN now() ELSE NULL END, "
                "CASE WHEN :is_rejected THEN now() ELSE NULL END) "
                "RETURNING id"
            ),
            {
                "tt": target_type,
                "tid": target_id,
                "pid": paper_id,
                "taskid": task_id,
                "itemid": task_item_id,
                "rev_id": reviewer_id,
                "rstatus": review_status,
                "pstatus": "not_ready",  # promotion_status always starts at not_ready
                "cv": claim_version,
                "cs": claim_text_snapshot,
                "cc": json.dumps(claim_components_snapshot, ensure_ascii=False),
                "md": model_direction,
                "ma": model_assessment,
                "rd": reviewer_direction,
                "rel": reviewer_evidence_level,
                "rc": reviewer_confidence,
                "rn": reviewer_note,
                "cov": json.dumps(coverage_summary_snapshot, ensure_ascii=False),
                "cfv": coverage_formula_version,
                "dr": draft_revision,
                "is_approved": review_status == "approved",
                "is_rejected": review_status == "rejected",
            },
        )
    ).scalar_one()
    # Insert frozen passages
    for rank, p in enumerate(passages, 1):
        params = await _map_review_passage(p, review_id, rank)
        await session.execute(
            text(
                "INSERT INTO paper_evidence_review_passages "
                "(review_id, paper_passage_id, passage_text, passage_text_snapshot, "
                "source_scope, section_title, paragraph_index, paragraph_id, "
                "translation_zh, direction, evidence_level, reason, confidence, "
                "semantic_confidence, source_locator, source_verified, "
                "source_verification_method, supported_components, passage_hash, "
                "rank, is_selected) "
                "VALUES (:rid, :ppid, :pt, :pts, :ss, :st, :pi, :pid, :tz, :dir, :el, "
                ":reason, :conf, :sc, :sl, :sv, :svm, CAST(:scm AS jsonb), :ph, "
                ":rank, :is_sel)"
            ),
            params,
        )
    # Audit
    await _write_audit(
        session,
        action_type="EVIDENCE_REVIEW_CREATED",
        entity_type="evidence_review",
        entity_id=review_id,
        after_data={
            "target_type": target_type,
            "target_id": str(target_id),
            "review_status": review_status,
            "promotion_status": "not_ready",
            "passage_count": len(passages),
        },
        operator_id=reviewer_id,
        reason="formal review record created",
    )
    await session.commit()
    return {"review_id": str(review_id), "status": review_status}


async def approve_review(
    session: AsyncSession,
    review_id: uuid.UUID,
    *,
    operator_id: str | None = None,
) -> dict:
    """Approve a review: locks snapshot, sets awaiting_promotion.

    Can only be called from awaiting_review or returned states.
    ('draft' is reserved for future multi-step review workflows and is not
    reachable via the current build_review path.)
    """
    row = await session.execute(
        text(
            "SELECT id, review_status FROM paper_evidence_reviews "
            "WHERE id = :rid FOR UPDATE"
        ),
        {"rid": review_id},
    )
    r = row.first()
    if r is None:
        raise ValueError("review not found")
    current_status = r[1]
    if current_status not in ("awaiting_review", "returned"):
        raise ValueError(f"cannot approve review in status '{current_status}'; must be awaiting_review/returned")
    await session.execute(
        text(
            "UPDATE paper_evidence_reviews "
            "SET review_status='approved', promotion_status='awaiting_promotion', "
            "approved_at=now(), updated_at=now() "
            "WHERE id = :rid"
        ),
        {"rid": review_id},
    )
    await _write_audit(
        session,
        action_type="EVIDENCE_REVIEW_APPROVED",
        entity_type="evidence_review",
        entity_id=review_id,
        after_data={"review_status": "approved", "promotion_status": "awaiting_promotion"},
        operator_id=operator_id,
        reason="review approved for promotion",
    )
    await session.commit()
    return {"review_id": str(review_id), "status": "approved"}


async def reject_review(
    session: AsyncSession,
    review_id: uuid.UUID,
    *,
    operator_id: str | None = None,
) -> dict:
    """Reject a review. Cannot be called on already-promoted or already-rejected reviews."""
    row = await session.execute(
        text(
            "SELECT id, review_status, promotion_status "
            "FROM paper_evidence_reviews WHERE id = :rid FOR UPDATE"
        ),
        {"rid": review_id},
    )
    r = row.first()
    if r is None:
        raise ValueError("review not found")
    if r[2] == "promoted":
        raise ValueError("review has already been promoted; cannot reject")
    if r[1] == "rejected":
        raise ValueError("review is already rejected")
    await session.execute(
        text(
            "UPDATE paper_evidence_reviews "
            "SET review_status='rejected', rejected_at=now(), updated_at=now() "
            "WHERE id = :rid"
        ),
        {"rid": review_id},
    )
    await _write_audit(
        session,
        action_type="EVIDENCE_REVIEW_REJECTED",
        entity_type="evidence_review",
        entity_id=review_id,
        after_data={"review_status": "rejected"},
        operator_id=operator_id,
        reason="review rejected",
    )
    await session.commit()
    return {"review_id": str(review_id), "status": "rejected"}


async def promote_review(
    session: AsyncSession,
    review_id: uuid.UUID,
    *,
    promoted_by: str | None = None,
) -> dict:
    """Promote a review: reads frozen snapshot, calls attach_evidence, updates review.

    Idempotent: if already promoted (promotion_status='promoted'), returns existing
    evidence_id without re-attaching.
    """
    # Lock the review row
    row = await session.execute(
        text(
            "SELECT id, target_type, target_id, paper_id, promotion_status, evidence_id, "
            "review_status, reviewer_direction, reviewer_evidence_level, "
            "reviewer_confidence, reviewer_note, model_direction, model_assessment, "
            "claim_version, claim_text_snapshot, claim_components_snapshot "
            "FROM paper_evidence_reviews WHERE id = :rid FOR UPDATE"
        ),
        {"rid": review_id},
    )
    r = row.first()
    if r is None:
        raise ValueError("review not found")
    review_data = r._mapping
    # Idempotent: already promoted
    if review_data["promotion_status"] == "promoted":
        return {
            "review_id": str(review_id),
            "evidence_id": str(review_data["evidence_id"]) if review_data["evidence_id"] else None,
            "status": "already_promoted",
        }
    # Must be in approved state
    if review_data["review_status"] != "approved":
        raise ValueError(
            f"cannot promote review in status '{review_data['review_status']}'; must be 'approved'"
        )
    # Look up paper source to get pmid
    paper_id = review_data["paper_id"]
    if paper_id is None:
        raise ValueError("review has no paper_id; cannot attach evidence")
    paper_row = await session.execute(
        text(
            "SELECT pmid, doi, title, journal, publication_year, metadata_json "
            "FROM paper_sources WHERE id = :pid"
        ),
        {"pid": paper_id},
    )
    paper = paper_row.first()
    if paper is None:
        raise ValueError("paper not found")
    paper_info = paper._mapping
    pmid = (paper_info["pmid"] or "").strip()
    if not pmid:
        raise ValueError("paper has no pmid; cannot verify via Europe PMC")
    # Read frozen review passages
    passage_rows = await session.execute(
        text(
            "SELECT passage_text, passage_text_snapshot, source_scope, section_title, "
            "paragraph_index, paragraph_id, direction, evidence_level, reason, "
            "confidence, semantic_confidence, source_locator, source_verified, "
            "source_verification_method, supported_components, passage_hash, "
            "is_selected "
            "FROM paper_evidence_review_passages "
            "WHERE review_id = :rid AND is_selected = true "
            "ORDER BY rank"
        ),
        {"rid": review_id},
    )
    review_passages = passage_rows.all()
    if not review_passages:
        raise ValueError("review has no selected passages")
    source_verified_passages = [
        row._mapping for row in review_passages if row._mapping["source_verified"]
    ]
    if not source_verified_passages:
        raise ValueError("review has no source_verified passages; cannot attach evidence")
    # Build passages list in the format expected by attach_evidence
    attach_passages = []
    for rp in source_verified_passages:
        attach_passages.append({
            "passage": rp["passage_text"],
            "source_scope": rp["source_scope"] or "abstract",
            "section_title": rp["section_title"],
            "paragraph_index": rp["paragraph_index"],
            "direction": rp["direction"] or review_data["reviewer_direction"] or "partial",
            "evidence_level": rp["evidence_level"] or review_data["reviewer_evidence_level"] or "indirect",
            "reason": rp["reason"],
            "confidence": float(rp["confidence"]) if rp["confidence"] is not None else None,
            "semantic_confidence": float(rp["semantic_confidence"]) if rp["semantic_confidence"] is not None else None,
            "source_locator": rp["source_locator"],
            "source_verified": bool(rp["source_verified"]),
            "source_verification_method": rp["source_verification_method"],
            "passage_hash": rp["passage_hash"],
            "supported_components": list(rp["supported_components"] or []),
        })
    # Call attach_evidence
    result = await attach_evidence(
        session,
        target_type=review_data["target_type"],
        target_id=review_data["target_id"],
        pmid=pmid,
        direction=review_data["reviewer_direction"] or "partial",
        reviewer_confidence=float(review_data["reviewer_confidence"] or 0.5),
        passages=attach_passages,
        operator_id=promoted_by,
        verification_status="human_verified",
        evidence_level=review_data["reviewer_evidence_level"],
        model_direction=review_data["model_direction"],
        model_assessment=review_data["model_assessment"],
        reviewer_note=review_data["reviewer_note"],
    )
    evidence_id = result["evidence_id"]
    # Update review record
    await session.execute(
        text(
            "UPDATE paper_evidence_reviews "
            "SET promotion_status='promoted', evidence_id=CAST(:eid AS uuid), "
            "promoted_at=now(), promoted_by=:pb, updated_at=now() "
            "WHERE id = :rid"
        ),
        {"rid": review_id, "eid": evidence_id, "pb": promoted_by},
    )
    await _write_audit(
        session,
        action_type="EVIDENCE_REVIEW_PROMOTED",
        entity_type="evidence_review",
        entity_id=review_id,
        after_data={
            "evidence_id": evidence_id,
            "promotion_status": "promoted",
            "promoted_by": promoted_by,
        },
        operator_id=promoted_by,
        reason="review promoted to mirror evidence",
    )
    await session.commit()
    return {"review_id": str(review_id), "evidence_id": evidence_id, "status": "promoted"}


async def return_review(
    session: AsyncSession,
    review_id: uuid.UUID,
    *,
    reason: str,
    returned_by: str | None = None,
) -> dict:
    """Return a review for rework. Sets promotion_status='returned', review_status='awaiting_review'.

    Cannot be called on already-promoted or already-returned reviews.
    """
    row = await session.execute(
        text(
            "SELECT id, promotion_status "
            "FROM paper_evidence_reviews WHERE id = :rid FOR UPDATE"
        ),
        {"rid": review_id},
    )
    r = row.first()
    if r is None:
        raise ValueError("review not found")
    if r[1] == "promoted":
        raise ValueError("review has already been promoted; cannot return")
    if r[1] == "returned":
        raise ValueError("review has already been returned")
    await session.execute(
        text(
            "UPDATE paper_evidence_reviews "
            "SET promotion_status='returned', review_status='awaiting_review', "
            "returned_at=now(), returned_by=:rb, return_reason=:rr, updated_at=now() "
            "WHERE id = :rid"
        ),
        {"rid": review_id, "rb": returned_by, "rr": reason},
    )
    await _write_audit(
        session,
        action_type="EVIDENCE_REVIEW_RETURNED",
        entity_type="evidence_review",
        entity_id=review_id,
        after_data={"return_reason": reason, "returned_by": returned_by},
        operator_id=returned_by,
        reason=reason,
    )
    await session.commit()
    return {"review_id": str(review_id), "status": "returned"}


async def cancel_review(
    session: AsyncSession,
    review_id: uuid.UUID,
    *,
    cancelled_by: str | None = None,
    reason: str | None = None,
) -> dict:
    """Cancel a review that is awaiting_promotion. Sets promotion_status='cancelled'.

    Only allowed when promotion_status='awaiting_promotion' (i.e., after
    approve_review but before promote_review).  No route is exposed yet;
    callers import the function directly when needed.
    """
    row = await session.execute(
        text(
            "SELECT id, promotion_status "
            "FROM paper_evidence_reviews WHERE id = :rid FOR UPDATE"
        ),
        {"rid": review_id},
    )
    r = row.first()
    if r is None:
        raise ValueError("review not found")
    if r[1] != "awaiting_promotion":
        raise ValueError(
            f"cannot cancel review with promotion_status '{r[1]}'; must be 'awaiting_promotion'"
        )
    await session.execute(
        text(
            "UPDATE paper_evidence_reviews "
            "SET promotion_status='cancelled', updated_at=now() "
            "WHERE id = :rid"
        ),
        {"rid": review_id},
    )
    await _write_audit(
        session,
        action_type="EVIDENCE_REVIEW_CANCELLED",
        entity_type="evidence_review",
        entity_id=review_id,
        after_data={"promotion_status": "cancelled", "cancel_reason": reason},
        operator_id=cancelled_by,
        reason=reason or "review cancelled",
    )
    await session.commit()
    return {"review_id": str(review_id), "status": "cancelled"}


def _review_row_to_dict(r: dict) -> dict:
    """Convert a raw review row mapping to a response dict."""
    return {
        "id": str(r["id"]),
        "target_type": r["target_type"],
        "target_id": str(r["target_id"]),
        "paper_id": str(r["paper_id"]) if r.get("paper_id") else None,
        "task_id": str(r["task_id"]) if r.get("task_id") else None,
        "task_item_id": str(r["task_item_id"]) if r.get("task_item_id") else None,
        "reviewer_id": r.get("reviewer_id"),
        "review_status": r["review_status"],
        "promotion_status": r["promotion_status"],
        "claim_version": r.get("claim_version"),
        "claim_text_snapshot": r.get("claim_text_snapshot"),
        "claim_components_snapshot": r.get("claim_components_snapshot"),
        "model_direction": r.get("model_direction"),
        "model_assessment": r.get("model_assessment"),
        "reviewer_direction": r.get("reviewer_direction"),
        "reviewer_evidence_level": r.get("reviewer_evidence_level"),
        "reviewer_confidence": float(r["reviewer_confidence"]) if r.get("reviewer_confidence") is not None else None,
        "reviewer_note": r.get("reviewer_note"),
        "coverage_summary_snapshot": r.get("coverage_summary_snapshot"),
        "coverage_formula_version": r.get("coverage_formula_version"),
        "draft_revision": int(r.get("draft_revision", 0)),
        "reviewed_at": r["reviewed_at"].isoformat() if r.get("reviewed_at") else None,
        "approved_at": r["approved_at"].isoformat() if r.get("approved_at") else None,
        "rejected_at": r["rejected_at"].isoformat() if r.get("rejected_at") else None,
        "promoted_at": r["promoted_at"].isoformat() if r.get("promoted_at") else None,
        "promoted_by": r.get("promoted_by"),
        "returned_at": r["returned_at"].isoformat() if r.get("returned_at") else None,
        "returned_by": r.get("returned_by"),
        "return_reason": r.get("return_reason"),
        "evidence_id": str(r["evidence_id"]) if r.get("evidence_id") else None,
        "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else None,
        "passages": [],
    }


def _passage_row_to_dict(p: dict) -> dict:
    """Convert a raw review_passage row mapping to a response dict."""
    return {
        "id": str(p["id"]),
        "review_id": str(p["review_id"]),
        "paper_passage_id": str(p["paper_passage_id"]) if p.get("paper_passage_id") else None,
        "passage_text": p.get("passage_text") or "",
        "passage_text_snapshot": p.get("passage_text_snapshot") or "",
        "source_scope": p.get("source_scope"),
        "section_title": p.get("section_title"),
        "paragraph_index": p.get("paragraph_index"),
        "paragraph_id": p.get("paragraph_id"),
        "translation_zh": p.get("translation_zh"),
        "direction": p.get("direction"),
        "evidence_level": p.get("evidence_level"),
        "reason": p.get("reason"),
        "confidence": float(p["confidence"]) if p.get("confidence") is not None else None,
        "semantic_confidence": float(p["semantic_confidence"]) if p.get("semantic_confidence") is not None else None,
        "source_locator": p.get("source_locator"),
        "source_verified": bool(p.get("source_verified", False)),
        "source_verification_method": p.get("source_verification_method"),
        "supported_components": list(p.get("supported_components") or []),
        "passage_hash": p.get("passage_hash"),
        "rank": int(p.get("rank", 0)),
        "is_selected": bool(p.get("is_selected", True)),
        "created_at": p["created_at"].isoformat() if p.get("created_at") else None,
    }


async def list_reviews(
    session: AsyncSession,
    *,
    review_status: str | None = None,
    promotion_status: str | None = None,
    target_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """List reviews with pagination and optional filters."""
    where = ["1=1"]
    params: dict = {}
    if review_status:
        where.append("review_status = :rs")
        params["rs"] = review_status
    if promotion_status:
        where.append("promotion_status = :ps")
        params["ps"] = promotion_status
    if target_type:
        where.append("target_type = :tt")
        params["tt"] = target_type
    clause = " AND ".join(where)
    params["lim"] = page_size
    params["off"] = (max(1, page) - 1) * page_size
    rows = await session.execute(
        text(
            f"SELECT * FROM paper_evidence_reviews WHERE {clause} "
            "ORDER BY created_at DESC LIMIT :lim OFFSET :off"
        ),
        params,
    )
    total = (
        await session.execute(
            text(f"SELECT COUNT(*) FROM paper_evidence_reviews WHERE {clause}"),
            {k: v for k, v in params.items() if k not in ("lim", "off")},
        )
    ).scalar_one()
    items = []
    for r in rows:
        item = _review_row_to_dict(r._mapping)
        items.append(item)
    return {"items": items, "total": int(total)}


async def get_review(
    session: AsyncSession,
    review_id: uuid.UUID,
) -> dict:
    """Get a review with its frozen passages."""
    row = await session.execute(
        text("SELECT * FROM paper_evidence_reviews WHERE id = :rid"),
        {"rid": review_id},
    )
    r = row.first()
    if r is None:
        raise ValueError("review not found")
    item = _review_row_to_dict(r._mapping)
    passage_rows = await session.execute(
        text(
            "SELECT * FROM paper_evidence_review_passages "
            "WHERE review_id = :rid ORDER BY rank"
        ),
        {"rid": review_id},
    )
    item["passages"] = [_passage_row_to_dict(p._mapping) for p in passage_rows]
    return item
