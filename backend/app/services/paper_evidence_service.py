"""Paper evidence retrieval (Europe PMC) + attach to Mirror KG evidence."""

from __future__ import annotations

import asyncio
import json
import re
import uuid

import httpx
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.models.mirror_kg import (
    MirrorEvidenceRecord,
    MirrorRegionCircuit,
    MirrorRegionConnection,
    MirrorRegionFunction,
)
from app.models.mirror_macro_clinical import (
    MirrorCircuitFunction,
    MirrorCircuitStep,
    MirrorProjectionFunction,
)
from app.services.ontology_service import TERM_TABLE_BY_TYPE
from app.config import get_settings
from app.services.llm_providers.factory import get_llm_provider
from app.services.ontology_residual_schemas import PaperPassageExtraction

EUROPE_PMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
SEARCH_TIMEOUT = 25

TARGET_MODELS = {
    "projection_function": MirrorProjectionFunction,
    "circuit_function": MirrorCircuitFunction,
    "region_function": MirrorRegionFunction,
    "projection": MirrorRegionConnection,
    "connection": MirrorRegionConnection,
    "circuit": MirrorRegionCircuit,
    "circuit_step": MirrorCircuitStep,
}


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
    excerpt: str,
    direction: str = "supports",
    mode: str = "function",
    suggested_confidence: float | None = None,
    operator_id: str | None = None,
) -> dict:
    paper = await verify_paper(pmid)
    if paper is None:
        raise ValueError("paper not found or invalid PMID")
    model = TARGET_MODELS.get(target_type)
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
    if direction in ("supports", "partial") and suggested_confidence is not None:
        new_confidence = max(0.0, min(0.85, float(suggested_confidence)))
        current = getattr(row, "confidence", None)
        if current is None or float(current) < new_confidence:
            row.confidence = new_confidence
        record.verification_status = "verified_auto"
        record.suggested_confidence = new_confidence
        record.confidence_adjustment_status = "applied"
    else:
        record.verification_status = "pending"
        record.suggested_confidence = suggested_confidence
        record.confidence_adjustment_status = (
            "pending" if suggested_confidence is not None else "none"
        )
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
    record.citation_json = {**record.citation_json, "mode": mode}
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
        "confidence": float(row.confidence) if getattr(row, "confidence", None) is not None else None,
        "verification_status": record.verification_status,
        "confidence_adjustment_status": record.confidence_adjustment_status,
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
    return {
        "items": [
            {
                "evidence_id": str(r.id),
                "evidence_text": r.evidence_text,
                "direction": r.evidence_direction,
                "verification_status": r.verification_status,
                "pmid": r.paper_pmid,
                "doi": r.paper_doi,
                "title": r.paper_title,
                "journal": r.paper_journal,
                "year": r.paper_year,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "links": {
                    "pubmed": f"https://pubmed.ncbi.nlm.nih.gov/{r.paper_pmid}/" if r.paper_pmid else None,
                    "doi": f"https://doi.org/{r.paper_doi}" if r.paper_doi else None,
                },
            }
            for r in rows
        ]
    }


async def extract_passage(*, term: str, title: str, abstract: str) -> dict:
    cfg = get_settings()
    provider = get_llm_provider("deepseek")
    system = "You are a strict JSON API. Reply only with the requested JSON object. Never explain."
    user = (
        f'Find the passage most relevant to the neuroscience claim "{term}". '
        "Determine the direction (supports / partial / contradicts / not_found) and confidence 0-1. "
        'Return JSON exactly like: {"direction": "supports", "passage": "<original passage>", '
        '"reason": "<one sentence>", "confidence": 0.9}. '
        f"Paper title: {title}\nAbstract: {abstract[:6000]}"
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
                if resp.parsed_json is not None:
                    parsed = PaperPassageExtraction.model_validate(resp.parsed_json)
                else:
                    text_value = (raw_response or "").strip()
                    fence = re.search(r"```(?:json|JSON)?\s*(.*?)```", text_value, re.DOTALL)
                    if fence:
                        text_value = fence.group(1).strip()
                    parsed = PaperPassageExtraction.model_validate(json.loads(text_value))
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
                text_value = (raw_response or "").strip()
                fence = re.search(r"```(?:json|JSON)?\s*(.*?)```", text_value, re.DOTALL)
                if fence:
                    text_value = fence.group(1).strip()
                parsed = PaperPassageExtraction.model_validate(json.loads(text_value))
            parse_status = "ok"
            break
        except (ValidationError, ValueError, json.JSONDecodeError):
            parse_status = "parse_error"
            if attempt < 2:
                await asyncio.sleep(cfg.ontology_residual_backoff_seconds)
    if parsed is None:
        raise ValueError(f"passage extraction failed: {parse_status}")
    return {
        **parsed.model_dump(),
        "parse_status": parse_status,
        "retry_count": retry_count,
        "raw_response": raw_response[:1000],
    }


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
                excerpt=extraction["passage"],
                direction=extraction["direction"],
                mode=mode,
                suggested_confidence=extraction["confidence"],
                operator_id="batch",
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
