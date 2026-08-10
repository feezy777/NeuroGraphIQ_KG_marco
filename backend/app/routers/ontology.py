"""Ontology REST API (Phase 1: quality-control-first)."""

from __future__ import annotations

import asyncio
import uuid

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.schemas.ontology import (
    AlignmentReviewRequest,
    BatchActivateRequest,
    BatchGroundingByTextRequest,
    AttachPreviewRequest,
    AttachPreviewResponse,
    CoverageResponse,
    EnumReplaceRequest,
    EvidenceExtractRequest,
    EvidenceExtractResponse,
    EvidenceAttachRequest,
    EvidenceRollbackRequest,
    BatchTaskCreateRequest,
    EvidenceAuditRequest,
    ExtractSelectedRequest,
    PassageSelectionRequest,
    TaskItemDraftRequest,
    TranslateRequest,
    ReviewResolveRequest,
    GroundingListResponse,
    GroundingRead,
    GroundingRunRequest,
    GroundingRunResponse,
    GroundingSkipRequest,
    ManualGroundingRequest,
    PaperSearchRequest,
    PanoramaResponse,
    TermCreateRequest,
    TermListResponse,
    TermMergeRequest,
    TermRead,
    TermSynonymCreateRequest,
    VocabularyCreateRequest,
    VocabularyListResponse,
    VocabularyRead,
)
from app.services import ontology_service as svc
from app.services import ontology_governance_service as gov
from app.services import paper_evidence_service as pes
from app.services import paper_fetch_service as pfs
from app.services import oa_xml_parser
from app.services.paragraph_retrieval import build_windows, score_paragraphs

router = APIRouter()

_ROLE_LEVELS = {"viewer": 0, "reviewer": 1, "ontology_admin": 2}


def _current_role() -> str:
    return (get_settings().ontology_role or "viewer").strip().lower()


def require_role(min_role: str):
    async def _dependency(role: str = Depends(_current_role)):
        if _ROLE_LEVELS.get(role, -1) < _ROLE_LEVELS.get(min_role, 99):
            raise HTTPException(
                status_code=403,
                detail={"code": "FORBIDDEN", "message": f"requires role {min_role}"},
            )
        return role

    return _dependency


@router.get("/governance/role")
async def governance_role():
    return {"role": _current_role()}


@router.get("/vocabularies", response_model=VocabularyListResponse)
async def get_vocabularies(
    vocab_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    try:
        items = await svc.list_vocabularies(session, vocab_type=vocab_type, status=status)
        return VocabularyListResponse(
            items=[VocabularyRead.model_validate(item) for item in items],
            total=len(items),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.post("/vocabularies", response_model=VocabularyRead, status_code=201)
async def create_vocabulary(
    body: VocabularyCreateRequest,
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("ontology_admin")),
):
    try:
        row = await svc.create_vocabulary(
            session,
            code=body.code,
            vocab_type=body.vocab_type,
            label_cn=body.label_cn,
            label_en=body.label_en,
            description=body.description,
            seq=body.seq,
        )
        await session.commit()
        return VocabularyRead.model_validate(row)
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.get("/terms", response_model=TermListResponse)
async def get_terms(
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    items, total = await svc.list_terms(
        session, status=status, q=q, limit=limit, offset=offset
    )
    return TermListResponse(
        items=[TermRead.model_validate(item) for item in items],
        total=total,
    )


@router.post("/terms", response_model=TermRead, status_code=201)
async def create_term(
    body: TermCreateRequest,
    session: AsyncSession = Depends(get_db),
):
    try:
        row = await svc.propose_term(
            session,
            canonical_term_en=body.canonical_term_en,
            canonical_term_cn=body.canonical_term_cn,
            term_type=body.term_type,
            category=body.category,
            domain=body.domain,
            role=body.role,
            effect_type=body.effect_type,
            description=body.description,
            created_by=body.created_by,
        )
        await session.commit()
        return TermRead.model_validate(row)
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.post("/terms/{term_id}/activate", response_model=TermRead)
async def activate_term(
    term_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("reviewer")),
):
    try:
        row = await svc.activate_term(session, term_id)
        await session.commit()
        return TermRead.model_validate(row)
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.post("/terms/{term_id}/deprecate", response_model=TermRead)
async def deprecate_term(
    term_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("ontology_admin")),
):
    try:
        row = await svc.deprecate_term(session, term_id)
        await session.commit()
        return TermRead.model_validate(row)
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.post("/terms/{term_id}/merge", response_model=TermRead)
async def merge_term(
    term_id: uuid.UUID,
    body: TermMergeRequest,
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("ontology_admin")),
):
    try:
        row = await svc.merge_term(session, term_id, body.target_id)
        await session.commit()
        return TermRead.model_validate(row)
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.post("/terms/{term_id}/synonyms", status_code=201)
async def add_term_synonym(
    term_id: uuid.UUID,
    body: TermSynonymCreateRequest,
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("ontology_admin")),
):
    try:
        row = await svc.add_synonym(
            session,
            term_id=term_id,
            synonym_text=body.synonym_text,
            lang=body.lang,
            match_type=body.match_type,
        )
        await session.commit()
        return {"id": str(row.id)}
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.get("/coverage", response_model=CoverageResponse)
async def get_coverage(
    granularity_level: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    data = await svc.coverage(session, granularity_level=granularity_level)
    return CoverageResponse.model_validate(data)


@router.get("/groundings", response_model=GroundingListResponse)
async def get_groundings(
    target_type: str | None = Query(default=None),
    target_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    items, total = await svc.list_groundings(
        session,
        target_type=target_type,
        target_id=target_id,
        limit=limit,
        offset=offset,
    )
    return GroundingListResponse(
        items=[GroundingRead.model_validate(item) for item in items],
        total=total,
    )


@router.post("/groundings/run", response_model=GroundingRunResponse)
async def run_deterministic_grounding(
    body: GroundingRunRequest,
    session: AsyncSession = Depends(get_db),
):
    try:
        result = await svc.run_deterministic_grounding_batch(
            session, body.target_type, limit=body.limit
        )
        await session.commit()
        return GroundingRunResponse.model_validate(result)
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.get("/report/term-panorama", response_model=PanoramaResponse)
async def get_term_panorama(
    target_type: str = Query(default="projection_function"),
    granularity_level: str | None = Query(default=None),
    limit: int = Query(default=5000, ge=1, le=50000),
    session: AsyncSession = Depends(get_db),
):
    try:
        data = await svc.term_panorama(
            session, target_type, granularity_level=granularity_level, limit=limit
        )
        return PanoramaResponse.model_validate(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.get("/regions/alignment")
async def get_region_alignment(
    granularity_level: str | None = Query(default=None),
    limit: int = Query(default=5000, ge=1, le=50000),
    session: AsyncSession = Depends(get_db),
):
    return await svc.region_alignment_summary(
        session, granularity_level=granularity_level, limit=limit
    )


# ---- Governance workbench ----


@router.get("/governance/dashboard")
async def governance_dashboard(
    granularity_level: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    return await gov.dashboard(session, granularity_level=granularity_level)


@router.get("/governance/issues")
async def governance_issues(
    granularity_level: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    return await gov.issues_summary(session, granularity_level=granularity_level)


@router.get("/governance/entity-summary")
async def governance_entity_summary(
    entity: str = Query(...),
    session: AsyncSession = Depends(get_db),
):
    try:
        return await gov.entity_summary(session, entity)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.get("/governance/ungrounded-records")
async def governance_ungrounded_records(
    granularity_level: str | None = Query(default=None),
    target_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    return await gov.ungrounded_records(
        session,
        granularity_level=granularity_level,
        target_type=target_type,
        limit=limit,
        offset=offset,
    )


@router.get("/terms/{term_id}/detail")
async def governance_term_detail(
    term_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
):
    try:
        return await gov.term_detail(session, term_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.get("/terms/{term_id}/references")
async def governance_term_references(
    term_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    return await gov.term_references(session, term_id, limit=limit, offset=offset)


@router.post("/terms/{source_id}/merge-preview")
async def governance_merge_preview(
    source_id: uuid.UUID,
    body: TermMergeRequest,
    session: AsyncSession = Depends(get_db),
):
    try:
        return await gov.merge_preview(session, source_id, body.target_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.post("/terms/batch-activate")
async def governance_batch_activate(
    body: BatchActivateRequest,
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("ontology_admin")),
):
    try:
        result = await gov.batch_activate(
            session, body.term_ids, operator_id=None, reason=body.reason
        )
        await session.commit()
        return result
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.post("/groundings/manual")
async def governance_manual_grounding(
    body: ManualGroundingRequest,
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("reviewer")),
):
    try:
        result = await gov.manual_grounding(
            session,
            target_type=body.target_type,
            target_id=body.target_id,
            term_id=body.term_id,
            reason=body.reason,
        )
        await session.commit()
        return result
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.post("/groundings/batch-by-text")
async def governance_batch_grounding_by_text(
    body: BatchGroundingByTextRequest,
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("reviewer")),
):
    try:
        result = await gov.batch_grounding_by_text(
            session,
            target_type=body.target_type,
            term_text=body.term_text,
            term_id=body.term_id,
        )
        await session.commit()
        return result
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.post("/groundings/skip")
async def governance_mark_skip(
    body: GroundingSkipRequest,
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("reviewer")),
):
    try:
        result = await gov.mark_skip(
            session,
            target_type=body.target_type,
            target_id=body.target_id,
            reason=body.reason or "manual skip",
        )
        await session.commit()
        return result
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.get("/vocabularies/usage")
async def governance_vocabulary_usage(
    vocab_type: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    return await gov.vocabulary_usage(session, vocab_type=vocab_type)


@router.get("/enum-anomalies")
async def governance_enum_anomalies(
    field: str = Query(...),
    granularity_level: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    try:
        return await gov.list_enum_anomalies(
            session,
            field=field,
            granularity_level=granularity_level,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.post("/enum-anomalies/replace")
async def governance_replace_enum_values(
    body: EnumReplaceRequest,
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("ontology_admin")),
):
    try:
        result = await gov.replace_enum_values(
            session,
            field=body.field,
            old_value=body.old_value,
            new_code=body.new_code,
            reason=body.reason,
        )
        await session.commit()
        return result
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.get("/terms/duplicates")
async def governance_duplicate_terms(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    return await gov.duplicate_terms(session, limit=limit, offset=offset)


@router.get("/alignment/candidates")
async def governance_alignment_candidates(
    status: str | None = Query(default=None),
    granularity_level: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    return await gov.list_alignment_candidates(
        session,
        status=status,
        granularity_level=granularity_level,
        limit=limit,
        offset=offset,
    )


@router.get("/alignment/candidates/stats")
async def governance_alignment_candidates_stats(
    granularity_level: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    return await gov.alignment_candidates_stats(
        session, granularity_level=granularity_level
    )


@router.post("/alignment/candidates/{candidate_id}/review")
async def governance_review_alignment_candidate(
    candidate_id: uuid.UUID,
    body: AlignmentReviewRequest,
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("reviewer")),
):
    try:
        result = await gov.review_alignment_candidate(
            session,
            candidate_id,
            action=body.action,
            reason=body.reason,
            external_iri=body.external_iri,
            external_label=body.external_label,
        )
        await session.commit()
        return result
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.post("/alignment/candidates/batch-accept-exact")
async def governance_batch_accept_exact(
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("ontology_admin")),
):
    result = await gov.batch_accept_exact_candidates(session)
    await session.commit()
    return result


@router.get("/change-logs")
async def governance_change_logs(
    entity_type: str | None = Query(default=None),
    entity_id: uuid.UUID | None = Query(default=None),
    action_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    return await gov.list_change_logs(
        session,
        entity_type=entity_type,
        entity_id=entity_id,
        action_type=action_type,
        limit=limit,
        offset=offset,
    )


@router.post("/audit/run")
async def governance_audit_run(
    granularity_level: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("reviewer")),
):
    result = await gov.run_audit(
        session, granularity_level=granularity_level, created_by="system"
    )
    await session.commit()
    return result


@router.get("/audit/runs")
async def governance_audit_runs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    return await gov.list_audit_runs(session, limit=limit, offset=offset)


# ---- Paper evidence (Phase B) ----


@router.post("/evidence/search")
async def paper_evidence_search(
    body: PaperSearchRequest,
    session: AsyncSession = Depends(get_db),
):
    try:
        info = await pes.pack_target_info(
            session, body.target_type, body.target_id, mode=body.mode
        )
        context = await pes.build_retrieval_context(session, body.target_type, body.target_id)
        query = (body.query_override or "").strip() or pes._build_epmc_query(context) or info["query"]
        papers = await pes.search_papers(query, limit=body.limit)
        ranked = pes._rank_papers(papers, context)
        for p in ranked:
            text_blob = f"{p.get('title') or ''} {p.get('abstract') or ''} {p.get('journal') or ''}".lower()
            reasons = []
            src = (context.get("source_region") or "").lower()
            tgt = (context.get("target_region") or "").lower()
            if src and src in text_blob:
                reasons.append("源脑区")
            if tgt and tgt in text_blob:
                reasons.append("靶脑区")
            if any(fn and fn.lower() in text_blob for fn in (context.get("function_terms") or [])):
                reasons.append("功能词")
            p["match_reason"] = "、".join(reasons) or "检索式命中"
        papers = ranked
        if body.query_override and (body.query_override or "").strip():
            info = {**info, "query": query}
        return {"target_info": info, "papers": papers}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail={"code": "PAPER_API_ERROR", "message": str(exc)})


@router.post("/evidence/extract-selected")
async def paper_evidence_extract_selected(
    body: ExtractSelectedRequest,
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("reviewer")),
):
    try:
        context = await pes.build_retrieval_context(session, body.target_type, body.target_id)
        cfg = pes.get_settings()
        sem_fetch = asyncio.Semaphore(cfg.paper_fetch_concurrency)
        sem_deepseek = asyncio.Semaphore(cfg.ontology_residual_concurrency)
        papers = [p.model_dump() for p in body.papers]
        results, llm_model = await pes.extract_candidates_for_target(
            session,
            context=context,
            papers=papers,
            max_papers=len(papers),
            only_oa=body.only_oa,
            stop_after_strong_support=body.stop_after_strong_support,
            sem_fetch=sem_fetch,
            sem_deepseek=sem_deepseek,
        )
        await session.commit()
        return {
            "claim": context.get("claim_text") or "",
            "claim_components": context.get("claim_components") or [],
            "results": results,
            "llm_model": llm_model,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.post("/evidence/attach")
async def paper_evidence_attach(
    body: EvidenceAttachRequest,
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("reviewer")),
):
    try:
        result = await pes.attach_evidence(
            session,
            target_type=body.target_type,
            target_id=body.target_id,
            pmid=body.pmid,
            direction=body.direction,
            evidence_level=body.evidence_level,
            model_direction=body.model_direction,
            model_assessment=body.model_assessment,
            reviewer_note=body.reviewer_note,
            reviewer_confidence=body.reviewer_confidence,
            passages=[p.model_dump() for p in body.passages],
            operator_id=None,
        )
        await session.commit()
        return result
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})
    except httpx.HTTPError as exc:
        await session.rollback()
        raise HTTPException(status_code=502, detail={"code": "PAPER_API_ERROR", "message": str(exc)})


@router.post("/evidence/attach-preview", response_model=AttachPreviewResponse)
async def paper_evidence_attach_preview(
    body: AttachPreviewRequest,
    session: AsyncSession = Depends(get_db),
):
    try:
        return await pes.attach_preview(
            session,
            target_type=body.target_type,
            target_id=body.target_id,
            pmid=body.pmid,
            direction=body.direction,
            reviewer_confidence=body.reviewer_confidence,
            passages=[p.model_dump() for p in body.passages],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.post("/evidence/{evidence_id}/rollback")
async def paper_evidence_rollback(
    evidence_id: uuid.UUID,
    body: EvidenceRollbackRequest,
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("reviewer")),
):
    try:
        result = await pes.rollback_evidence(
            session, evidence_id, reason=body.reason, operator_id=None
        )
        await session.commit()
        return result
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.get("/evidence/list")
async def paper_evidence_list(
    target_type: str = Query(...),
    target_id: uuid.UUID = Query(...),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
):
    return await pes.list_paper_evidence(
        session, target_type=target_type, target_id=target_id, limit=limit
    )


@router.get("/evidence/target/{target_type}/{target_id}")
async def paper_evidence_target_dto(
    target_type: str,
    target_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
):
    try:
        return await pes.build_target_dto(session, target_type, target_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.post("/evidence/extract", response_model=EvidenceExtractResponse)
async def paper_evidence_extract(
    body: EvidenceExtractRequest,
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("reviewer")),
):
    try:
        pmid = (body.pmid or "").strip()
        doi = (body.doi or "").strip()
        pmcid = (body.pmcid or "").strip()
        if not (pmid or doi or pmcid):
            raise ValueError("paper identifier required (pmid / pmcid / doi)")
        context = await pes.build_retrieval_context(session, body.target_type, body.target_id)
        cached, metadata = await pfs.ensure_paper_cached(
            session, pmid=pmid or None, pmcid=pmcid or None, doi=doi or None
        )
        if metadata is not None:
            paper = metadata
            paper_source = await pes.ensure_paper_source(
                session,
                {**paper, "abstract": (body.abstract or "").strip(), "fulltext": ""},
            )
        else:
            paper_source = cached
            meta = paper_source.metadata_json or {}
            paper = {
                "pmid": paper_source.pmid or body.pmid,
                "pmcid": paper_source.pmcid,
                "doi": paper_source.doi or "",
                "title": paper_source.title or body.title or "",
                "journal": paper_source.journal,
                "year": str(paper_source.publication_year or ""),
                "authors": meta.get("authors", ""),
                "source": paper_source.source,
            }
        abstract = (body.abstract or "").strip()
        xml_text = await pfs.fetch_oa_fulltext_xml(
            pmid=paper.get("pmid") or pmid or None,
            pmcid=paper.get("pmcid") or pmcid or None,
        )
        paragraphs: list[dict] = []
        if abstract:
            paragraphs.append(
                {
                    "source_scope": "abstract",
                    "section_title": "Abstract",
                    "paragraph_id": "abstract_p001",
                    "paragraph_index": 0,
                    "passage_text": abstract,
                    "text_hash": pes.passage_hash(abstract),
                    "locator": "abstract:paragraph:0",
                }
            )
        if xml_text.strip():
            paragraphs.extend(oa_xml_parser.parse_oa_xml(xml_text))
        saved = await pes.ensure_paper_passages(session, paper_source.id, paragraphs)
        await session.commit()
        all_paragraphs = await pes.load_paper_passages(session, paper_source.id)
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
        result = await pes.extract_passage_from_paper(
            claim=context,
            title=paper.get("title") or body.title or "",
            windows=windows,
        )
        result["paper_id"] = str(paper_source.id)
        result["paper"] = {
            "pmid": paper.get("pmid") or "",
            "pmcid": paper.get("pmcid") or "",
            "doi": paper.get("doi") or "",
            "title": paper.get("title") or "",
            "journal": paper.get("journal") or "",
            "year": paper.get("year") or "",
            "authors": paper.get("authors") or "",
            "source": paper.get("source") or "europepmc",
        }
        result["claim"] = {
            "claim_text": context.get("claim_text") or "",
            "structured_claim": context.get("structured_claim") or {},
            "object_type": context.get("object_type") or "",
            "granularity": context.get("granularity") or "",
        }
        result["retrieval_summary"] = {
            **result.get("retrieval_summary", {}),
            "total_paragraphs": len(all_paragraphs),
            "top_k": len(windows),
            "parsed_paragraphs": len(saved),
        }
        if saved:
            result["source_type"] = "fulltext" if any(p.get("source_scope") == "fulltext" for p in saved) else "abstract"
        result["links"] = {
            "pubmed": f"https://pubmed.ncbi.nlm.nih.gov/{paper.get('pmid') or pmid}/" if (paper.get("pmid") or pmid) else None,
        }
        await session.commit()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail={"code": "PAPER_API_ERROR", "message": str(exc)})


@router.post("/evidence/batch")
async def paper_evidence_batch_create(
    body: BatchTaskCreateRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("reviewer")),
):
    try:
        result = await pes.create_batch_task(
            session,
            target_type=body.target_type,
            scope=body.scope,
            mode=body.mode,
            max_papers_per_object=body.max_papers_per_object,
            created_by=None,
            limit=body.limit,
            start_paused=body.start_paused,
            name=body.name,
            granularity_level=body.granularity_level,
            only_oa=body.only_oa,
            confidence_lt=body.confidence_lt,
            stop_after_strong_support=body.stop_after_strong_support,
            target_ids=body.target_ids,
            filter_snapshot=body.filter_snapshot,
        )
        background_tasks.add_task(pes.materialize_task_items_background, result["task_id"])
        if not body.start_paused:
            background_tasks.add_task(pes.execute_paper_evidence_batch_background, result["task_id"])
        return {**result, "auto_started": not body.start_paused}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.get("/evidence/batch")
async def paper_evidence_batch_list(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    return await pes.list_paper_evidence_tasks(session, limit=limit, offset=offset, status=status)


@router.get("/evidence/batch/preview")
async def paper_evidence_batch_preview(
    target_type: str = Query(...),
    scope: str = Query(default="filter"),
    confidence_lt: float | None = Query(default=None),
    granularity_level: str | None = Query(default=None),
    search: str | None = Query(default=None),
    selected_ids: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    snapshot = {
        "target_type": target_type,
        "granularity_level": granularity_level,
        "confidence_lt": confidence_lt,
        "search": search,
    }
    return await pes.preview_batch_scope(
        session,
        target_type=target_type,
        filter_snapshot=snapshot,
        scope=scope,
        selected_ids=(selected_ids or "").split(",") if selected_ids else None,
    )


@router.post("/evidence/batch/{task_id}/pause")
async def paper_evidence_batch_pause(
    task_id: str,
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("reviewer")),
):
    try:
        return await pes.pause_batch_task(session, task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.post("/evidence/batch/{task_id}/resume")
async def paper_evidence_batch_resume(
    task_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("reviewer")),
):
    try:
        result = await pes.resume_batch_task(session, task_id)
        background_tasks.add_task(pes.execute_paper_evidence_batch_background, task_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.post("/evidence/batch/{task_id}/cancel")
async def paper_evidence_batch_cancel(
    task_id: str,
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("reviewer")),
):
    try:
        return await pes.cancel_batch_task(session, task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.post("/evidence/batch/{task_id}/retry-failed")
async def paper_evidence_batch_retry(
    task_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("reviewer")),
):
    try:
        result = await pes.retry_failed_batch_items(session, task_id)
        if result["retried"] > 0:
            background_tasks.add_task(pes.execute_paper_evidence_batch_background, task_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.get("/evidence/batch/{task_id}")
async def paper_evidence_batch_get(
    task_id: str,
    session: AsyncSession = Depends(get_db),
):
    try:
        return await pes.get_batch_task(session, task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.get("/evidence/batch/{task_id}/items")
async def paper_evidence_batch_items(
    task_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    return await pes.list_batch_items(session, task_id, limit=limit, offset=offset)


@router.post("/evidence/batch/{task_id}/items/{item_id}/reviewed")
async def paper_evidence_batch_item_reviewed(
    task_id: str,
    item_id: str,
    evidence_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("reviewer")),
):
    try:
        return await pes.complete_batch_item_reviewed(
            session, task_id, item_id, evidence_id=evidence_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.get("/evidence/batch/items/{item_id}/draft")
async def paper_evidence_batch_item_draft_get(
    item_id: str,
    session: AsyncSession = Depends(get_db),
):
    try:
        return await pes.get_task_item_draft(session, item_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.put("/evidence/batch/items/{item_id}/draft")
async def paper_evidence_batch_item_draft_put(
    item_id: str,
    body: TaskItemDraftRequest,
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("reviewer")),
):
    try:
        return await pes.save_task_item_draft(session, item_id, body.draft, revision=body.revision)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.post("/evidence/passage/validate-selection")
async def paper_evidence_passage_validate_selection(
    body: PassageSelectionRequest,
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("reviewer")),
):
    try:
        return await pes.validate_passage_selection(
            session, body.paper_passage_id, body.selected_text
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.get("/evidence/stats")
async def paper_evidence_stats(
    target_types: str | None = Query(default=None, description="comma-separated target types"),
    session: AsyncSession = Depends(get_db),
):
    types = [t.strip() for t in (target_types or "").split(",") if t.strip()] or None
    return await pes.paper_evidence_stats(session, target_types=types)


@router.post("/evidence/audit")
async def paper_evidence_audit(
    body: EvidenceAuditRequest,
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("reviewer")),
):
    return await pes.write_evidence_audit_event(
        session,
        action_type=body.action_type,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        before_data=body.before_data,
        after_data=body.after_data,
        operator_id=None,
        reason=body.reason,
    )


@router.get("/evidence/review-queue")
async def paper_evidence_review_queue(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: str = Query(default="pending"),
    session: AsyncSession = Depends(get_db),
):
    return await pes.list_evidence_review_queue(session, limit=limit, offset=offset, status=status)


@router.get("/evidence/adjustments")
async def paper_evidence_adjustments(
    target_type: str = Query(...),
    target_id: uuid.UUID = Query(...),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
):
    return await pes.list_confidence_adjustments(
        session, target_type=target_type, target_id=target_id, limit=limit
    )


@router.post("/evidence/review-queue/{record_id}/resolve")
async def paper_evidence_review_resolve(
    record_id: uuid.UUID,
    body: ReviewResolveRequest,
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("reviewer")),
):
    try:
        return await pes.resolve_evidence_review_record(session, record_id, note=body.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.post("/evidence/translate")
async def paper_evidence_translate(
    body: TranslateRequest,
    _auth: str = Depends(require_role("reviewer")),
):
    return await pes.translate_text(body.text)


@router.get("/evidence/queue")
async def paper_evidence_queue(
    target_type: str = Query(...),
    scope: str = Query(default="low_confidence"),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
):
    try:
        return await pes.queue_targets(session, target_type, scope, limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})
