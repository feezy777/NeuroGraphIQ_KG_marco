"""Paper evidence retrieval (Europe PMC) + attach to Mirror KG evidence."""

from __future__ import annotations

import uuid
import re

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mirror_kg import MirrorEvidenceRecord, MirrorRegionConnection, MirrorRegionFunction
from app.models.mirror_macro_clinical import MirrorCircuitFunction, MirrorProjectionFunction
from app.services.ontology_service import TERM_TABLE_BY_TYPE

EUROPE_PMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
SEARCH_TIMEOUT = 25


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
                "source": "europepmc",
            }
        )
    return papers


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
    session: AsyncSession, target_type: str, target_id: uuid.UUID
) -> dict:
    model = TERM_TABLE_BY_TYPE.get(target_type)
    if model is None:
        raise ValueError(f"unsupported target_type: {target_type}")
    row = await session.get(model, target_id)
    if row is None:
        raise ValueError("target not found")
    term_text = _term_text_for(row, target_type)
    context_parts = [term_text]
    if target_type == "projection_function" and row.projection_id:
        proj = await session.get(MirrorRegionConnection, row.projection_id)
        if proj is not None:
            for region_name in (proj.source_region_name_en, proj.target_region_name_en):
                name = (region_name or "").strip()
                # Only short, generic region names improve recall; layer/area
                # specific names over-constrain Europe PMC queries.
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
    excerpt: str,
    direction: str = "supports",
    operator_id: str | None = None,
) -> dict:
    paper = await verify_paper(pmid)
    if paper is None:
        raise ValueError("paper not found or invalid PMID")
    model = TERM_TABLE_BY_TYPE.get(target_type)
    if model is None:
        raise ValueError(f"unsupported target_type: {target_type}")
    row = await session.get(model, target_id)
    if row is None:
        raise ValueError("target not found")
    existing = (
        await session.execute(
            select(MirrorEvidenceRecord).where(
                MirrorEvidenceRecord.evidence_target_type == target_type,
                MirrorEvidenceRecord.evidence_target_id == target_id,
                MirrorEvidenceRecord.evidence_type == "paper_verification",
            )
        )
    ).scalars().first()
    record = existing or MirrorEvidenceRecord(
        evidence_target_type=target_type,
        evidence_target_id=target_id,
        evidence_type="paper_verification",
    )
    record.evidence_text = excerpt.strip()
    record.evidence_direction = direction
    record.verification_status = "pending"
    record.paper_source = paper["source"]
    record.paper_pmid = paper["pmid"]
    record.paper_doi = paper["doi"] or None
    record.paper_title = paper["title"] or None
    record.paper_journal = paper["journal"] or None
    record.paper_year = int(paper["year"]) if str(paper["year"]).isdigit() else None
    record.citation_json = {
        "pmid": paper["pmid"],
        "doi": paper["doi"],
        "title": paper["title"],
        "journal": paper["journal"],
        "year": paper["year"],
        "authors": paper["authors"],
    }
    record.source_reference_text = f"{paper['authors']} ({paper['year']}). {paper['title']}. {paper['journal']}."
    record.verification_by = operator_id
    session.add(record)
    snippet = excerpt.strip()[:500]
    old_text = (getattr(row, "evidence_text", None) or "").strip()
    line = f"[论文证据] {snippet} (PMID:{paper['pmid']}, DOI:{paper['doi'] or '-'})"
    row.evidence_text = f"{old_text}\n{line}" if old_text else line
    await session.flush()
    return {
        "evidence_id": str(record.id),
        "target_type": target_type,
        "target_id": str(target_id),
        "evidence_text": row.evidence_text,
        "paper": {
            "pmid": paper["pmid"],
            "doi": paper["doi"],
            "title": paper["title"],
            "journal": paper["journal"],
            "year": paper["year"],
            "links": {
                "pubmed": f"https://pubmed.ncbi.nlm.nih.gov/{paper['pmid']}/" if paper["pmid"] else None,
                "doi": f"https://doi.org/{paper['doi']}" if paper["doi"] else None,
            },
        },
    }
