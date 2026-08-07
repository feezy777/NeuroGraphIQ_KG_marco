"""Ontology REST API (Phase 1: quality-control-first)."""

from __future__ import annotations

import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.schemas.ontology import (
    AlignmentReviewRequest,
    BatchActivateRequest,
    BatchGroundingByTextRequest,
    CoverageResponse,
    EnumReplaceRequest,
    EvidenceExtractRequest,
    EvidenceAttachRequest,
    BatchTaskCreateRequest,
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
        papers = await pes.search_papers(info["query"], limit=body.limit)
        return {"target_info": info, "papers": papers}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail={"code": "PAPER_API_ERROR", "message": str(exc)})


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
            excerpt=body.excerpt,
            direction=body.direction,
            mode=body.mode,
            suggested_confidence=body.suggested_confidence,
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


@router.post("/evidence/extract")
async def paper_evidence_extract(
    body: EvidenceExtractRequest,
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("reviewer")),
):
    try:
        info = await pes.pack_target_info(session, body.target_type, body.target_id)
        result = await pes.extract_passage(
            term=info["function_term"], title=body.title, abstract=body.abstract
        )
        result["links"] = {
            "pubmed": f"https://pubmed.ncbi.nlm.nih.gov/{body.pmid}/" if body.pmid else None,
        }
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail={"code": "PAPER_API_ERROR", "message": str(exc)})


@router.post("/evidence/batch")
async def paper_evidence_batch_create(
    body: BatchTaskCreateRequest,
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("reviewer")),
):
    try:
        return await pes.create_batch_task(
            session,
            target_type=body.target_type,
            scope=body.scope,
            mode=body.mode,
            max_papers_per_object=body.max_papers_per_object,
            created_by=None,
            limit=body.limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.post("/evidence/batch/{task_id}/run")
async def paper_evidence_batch_run(
    task_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_role("reviewer")),
):
    try:
        return await pes.run_batch_step(session, task_id, limit=limit)
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
