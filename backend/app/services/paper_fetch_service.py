"""Unified Europe PMC fetch service.

Separation of concerns:
  * HTTP / network concerns live here (timeouts, retry/backoff, Europe PMC endpoints);
  * DB caching lives here too (paper_sources reuse, hash-based skip);
  * routers / evidence service never call Europe PMC directly.

OA XML full text is fetched via PMCID when available, else via PMID.
Non-OA full text is never fetched through unauthorized channels.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import logging
import re
import uuid

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mirror_kg import PaperPassage, PaperSource

EUROPE_PMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
EUROPE_PMC_FULLTEXT = "https://www.ebi.ac.uk/europepmc/webservices/rest"
SEARCH_TIMEOUT = 25
RETRY_TIMEOUTS = (1.0, 2.0, 4.0)
METADATA_TTL_SECONDS = 7 * 86400  # 7 days

_log = logging.getLogger(__name__)


async def _get_with_retry(client: httpx.AsyncClient, url: str, params: dict) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            resp = await client.get(url, params=params)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                await asyncio.sleep(RETRY_TIMEOUTS[attempt])
                continue
            resp.raise_for_status()
            return resp
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            last_exc = exc
            if attempt < 2:
                await asyncio.sleep(RETRY_TIMEOUTS[attempt])
    raise last_exc or RuntimeError("Europe PMC request failed")


async def _get_json_with_retry(client: httpx.AsyncClient, url: str, params: dict) -> dict:
    """GET JSON with retries on HTTP errors AND on silent empty responses.

    Europe PMC intermittently answers 200 with only {"version":"6.9"} (no
    resultList) under load; treating that as success produces bogus "paper not
    found" errors downstream, so empty payloads are retried.
    """
    last_payload: dict = {}
    for attempt in range(3):
        resp = await _get_with_retry(client, url, params)
        payload = resp.json()
        if "resultList" in payload:
            return payload
        last_payload = payload
        await asyncio.sleep(RETRY_TIMEOUTS[min(attempt, len(RETRY_TIMEOUTS) - 1)])
    return last_payload


def normalize_doi(doi: str) -> str:
    value = (doi or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "http://dx.doi.org/", "https://dx.doi.org/", "doi:"):
        if value.startswith(prefix):
            value = value[len(prefix):]
    return value.strip()


def clean_html_text(text: str | None) -> str:
    """Strip HTML tags, decode HTML entities, collapse whitespace.

    Europe PMC abstractText carries tags/entities; DeepSeek copies the decoded
    plain text, so the verification source must be cleaned the same way.
    """
    t = re.sub(r"<[^>]+>", " ", text or "")
    t = html.unescape(t)
    return re.sub(r"\s+", " ", t).strip()


async def fetch_paper_metadata(
    *,
    pmid: str | None = None,
    pmcid: str | None = None,
    doi: str | None = None,
) -> dict | None:
    """Resolve paper metadata from Europe PMC by PMID / PMCID / DOI."""
    query = ""
    if pmid:
        query = f"EXT_ID:{pmid}"
    elif pmcid:
        clean_pmcid = re.sub(r"^PMC", "", pmcid or "").upper()
        query = f"PMCID:PMC{clean_pmcid}"
    elif doi:
        query = f'DOI:"{normalize_doi(doi)}"'
    else:
        raise ValueError("paper identifier required (pmid / pmcid / doi)")
    async with httpx.AsyncClient(trust_env=False, timeout=SEARCH_TIMEOUT) as client:
        payload = await _get_json_with_retry(
            client,
            EUROPE_PMC_SEARCH,
            {"query": query, "format": "json", "pageSize": 1, "resultType": "core"},
        )
    results = payload.get("resultList", {}).get("result", [])
    if not results:
        return None
    item = results[0]
    return {
        "pmid": item.get("pmid") or pmid or "",
        "pmcid": (item.get("pmcid") or pmcid or "").upper(),
        "doi": item.get("doi") or doi or "",
        "title": item.get("title") or "",
        "journal": item.get("journalTitle") or "",
        "year": item.get("pubYear") or "",
        "authors": item.get("authorString") or "",
        "abstract": clean_html_text(item.get("abstractText") or "")[:2000],
        "is_open_access": str(item.get("isOpenAccess") or "").lower() == "y",
        "source": "europepmc",
    }


async def _fetch_ncbi_efetch_xml(
    client: httpx.AsyncClient, clean_pmcid: str, pmid: str | None
) -> str:
    """Fallback full-text XML via NCBI eutils efetch (db=pmc, OA articles)."""
    if not clean_pmcid:
        return ""
    url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        f"?db=pmc&id=PMC{clean_pmcid}&rettype=xml&retmode=xml"
    )
    try:
        resp = await client.get(url, timeout=45)
        if resp.status_code != 200:
            return ""
        text = (resp.text or "").strip()
        # efetch answers with an error element for articles without XML full text
        if not text or "<error" in text.lower():
            return ""
        return text
    except (httpx.HTTPStatusError, httpx.TransportError) as exc:
        _log.warning("[eutils] efetch fulltext failed pmcid=PMC%s err=%s", clean_pmcid, exc)
        return ""


async def fetch_oa_fulltext_xml(*, pmid: str | None = None, pmcid: str | None = None) -> str:
    """Fetch OA full text XML. Prefers Europe PMC PMCID endpoint, falls back to NCBI efetch."""
    url = None
    clean_pmcid = ""
    if pmcid:
        clean_pmcid = re.sub(r"^PMC", "", pmcid or "").upper()
        url = f"{EUROPE_PMC_FULLTEXT}/PMC{clean_pmcid}/fullTextXML"
    elif pmid:
        url = f"{EUROPE_PMC_FULLTEXT}/MED/{pmid}/fullTextXML"
    else:
        return ""
    async with httpx.AsyncClient(trust_env=False, timeout=SEARCH_TIMEOUT) as client:
        try:
            resp = await client.get(url)
            if resp.status_code == 404:
                return await _fetch_ncbi_efetch_xml(client, clean_pmcid, pmid)
            resp.raise_for_status()
            return resp.text
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            _log.warning("[europepmc] fulltext fetch failed url=%s err=%s", url, exc)
            return await _fetch_ncbi_efetch_xml(client, clean_pmcid, pmid)


async def fetch_plain_fulltext(*, pmid: str | None = None, pmcid: str | None = None) -> str:
    """Legacy plain-text full text (used by attach re-verification)."""
    xml = await fetch_oa_fulltext_xml(pmid=pmid, pmcid=pmcid)
    if not xml:
        return ""
    plain = re.sub(r"<[^>]+>", " ", xml)
    return re.sub(r"\s+", " ", plain).strip()[:8000]


def is_metadata_stale(row: PaperSource) -> bool:
    if row.fetched_at is None:
        return True
    import datetime

    age = datetime.datetime.now(datetime.timezone.utc) - row.fetched_at
    return age.total_seconds() > METADATA_TTL_SECONDS


async def ensure_paper_cached(
    session: AsyncSession,
    *,
    pmid: str | None = None,
    pmcid: str | None = None,
    doi: str | None = None,
    force_refresh: bool = False,
) -> tuple[PaperSource, dict | None]:
    """Return cached paper source; fetch metadata only when stale/missing.

    Returns (paper_source, fresh_metadata_or_None). Abstract/fulltext hash reuse is
    handled by callers through ensure_paper_source + paper_passages dedup.
    """
    metadata = None
    existing = None
    if pmid:
        existing = (
            await session.execute(
                text("SELECT id FROM paper_sources WHERE pmid=:pmid"),
                {"pmid": pmid},
            )
        ).scalar_one_or_none()
    elif doi:
        existing = (
            await session.execute(
                text("SELECT id FROM paper_sources WHERE normalized_doi=:doi"),
                {"doi": normalize_doi(doi)},
            )
        ).scalar_one_or_none()
    if existing is not None:
        row = await session.get(PaperSource, existing)
        if row is not None and not force_refresh and not is_metadata_stale(row):
            return row, None
    metadata = await fetch_paper_metadata(pmid=pmid, pmcid=pmcid, doi=doi)
    if metadata is None:
        raise ValueError("paper not found or invalid identifier")
    return None, metadata
