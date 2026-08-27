"""Paper Evidence Workbench 端点（证据候选工作台;ranking_id 任务级,只读评价+任务工作区）。

* POST /api/paper-evidence-workbench/search         —— 当前任务上下文自动检索（多源,未入库）
* POST /api/paper-evidence-workbench/papers         —— 检索结果入库去重 + 绑定任务论文工作区
* GET  /api/paper-evidence-workbench/papers         —— 任务论文工作区列表（按任务隔离）
* POST /api/paper-evidence-workbench/import-lines   —— 已有 Paper Discovery 线索导入（线索≠证据）
* POST /api/paper-evidence-workbench/segments/run   —— 函数规则初筛（零 LLM;复用既有纯函数）
* GET  /api/paper-evidence-workbench/segments       —— 待 AI 审核片段（按任务）
* POST /api/paper-evidence-workbench/reviews/run    —— LLM Semantic Review（仅判定片段）
* GET  /api/paper-evidence-workbench/reviews        —— 审核结果 + Evidence Candidate 计算
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.paper_evidence_workbench_service import (
    auto_init_task_papers,
    bind_workspace_papers,
    ensure_paper_library,
    import_line_papers,
    remove_task_paper,
    run_rule_segments,
    run_semantic_review,
    sync_evidence_candidates,
    translate_evidence_candidates,
    search_papers,
    suggest_discovery_queries,
)

router = APIRouter(tags=["Paper Evidence Workbench"])


# ── Schemas ──────────────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    source_region: str
    target_region: str
    connection_type: str | None = None
    query: str | None = None
    limit: int = 20


class PaperRecord(BaseModel):
    pmid: str | None = None
    doi: str | None = None
    title: str = ""
    authors: str | None = None
    journal: str | None = None
    year: int | None = None
    abstract_available: bool = False
    fulltext_available: bool = False
    source: str = "search"


class PapersRequest(BaseModel):
    ranking_id: str
    papers: list[PaperRecord]


class ImportLinesRequest(BaseModel):
    ranking_id: str


class SuggestQueriesRequest(BaseModel):
    source_region: str
    target_region: str
    connection_type: str | None = None


class RemovePaperRequest(BaseModel):
    ranking_id: str
    paper_id: str


class RunSegmentsRequest(BaseModel):
    ranking_id: str
    paper_ids: list[str]
    connection_type: str | None = None


class RunReviewRequest(BaseModel):
    ranking_id: str
    segment_ids: list[str]
    connection_type: str | None = None
    force: bool = False


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except Exception:
        raise HTTPException(status_code=422, detail=f"invalid uuid: {value}")


# ── 端点 ─────────────────────────────────────────────────────────────────────────

@router.post("/search")
async def search(req: SearchRequest):
    """检索(多源);自动基于当前任务上下文生成关键词;返回未入库记录。"""
    return {"results": await search_papers(
        req.source_region, req.target_region, req.connection_type,
        query_override=req.query, limit=req.limit)}


@router.post("/papers")
async def papers_upsert(req: PapersRequest, session: AsyncSession = Depends(get_db)):
    """检索结果 → Paper Library 去重入库(PMID→DOI→title) → 绑定任务工作区。"""
    ranking = (await session.execute(text(
        "SELECT 1 FROM paper_connection_candidate_rankings WHERE id = :rid"),
        {"rid": _uuid(req.ranking_id)})).first()
    if ranking is None:
        raise HTTPException(status_code=404, detail="ranking not found")
    records = [r.model_dump() for r in req.papers]
    enriched = await ensure_paper_library(session, records)
    bound = await bind_workspace_papers(session, req.ranking_id, enriched)
    return {"bound": bound, "papers": enriched}


@router.get("/papers")
async def papers_list(ranking_id: str = Query(...), session: AsyncSession = Depends(get_db)):
    rows = (await session.execute(text("""
        SELECT w.paper_id, w.role, w.title, w.authors, w.journal, w.publication_year,
               w.pmid, w.doi, w.abstract_available, w.fulltext_available, w.source,
               w.retrieved_at,
               EXISTS(SELECT 1 FROM pew_segments s WHERE s.paper_id = w.paper_id
                      AND s.ranking_id = w.ranking_id) AS has_segments
        FROM pew_papers w WHERE w.ranking_id = :rid ORDER BY w.created_at"""),
        {"rid": _uuid(ranking_id)})).all()
    return {"ranking_id": ranking_id, "items": [{
        "paper_id": str(r[0]), "role": r[1], "title": r[2], "authors": r[3],
        "journal": r[4], "year": r[5], "pmid": r[6], "doi": r[7],
        "abstract_available": bool(r[8]), "fulltext_available": bool(r[9]),
        "source": r[10], "retrieved_at": str(r[11]) if r[11] else None,
        "has_segments": bool(r[12]),
    } for r in rows]}


@router.post("/import-lines")
async def import_lines(req: ImportLinesRequest, session: AsyncSession = Depends(get_db)):
    """已有 Paper Discovery 线索(ranking→pair→paper)导入工作区;仅线索,非证据。"""
    result = await import_line_papers(session, req.ranking_id)
    return result


@router.post("/queries")
async def suggest_queries(req: SuggestQueriesRequest, session: AsyncSession = Depends(get_db)):
    """为当前任务生成 2~4 条可编辑默认检索词(canonical aliases + 连接类型同义词)。"""
    queries = await suggest_discovery_queries(
        session, req.source_region, req.target_region, req.connection_type)
    return {"queries": queries}


@router.post("/papers/remove")
async def papers_remove(req: RemovePaperRequest, session: AsyncSession = Depends(get_db)):
    """移出当前任务(Task Paper Workspace);论文保留在 Paper Library。"""
    removed = await remove_task_paper(session, req.ranking_id, req.paper_id)
    return {"removed": removed, "paper_id": req.paper_id}


class InitTaskPapersRequest(BaseModel):
    ranking_id: str
    force: bool = False


class TranslateCandidatesRequest(BaseModel):
    ranking_id: str
    segment_ids: list[str] | None = None
    force: bool = False


class SelectCandidateRequest(BaseModel):
    ranking_id: str
    segment_id: str
    selected: bool


class ExcludeCandidateRequest(BaseModel):
    ranking_id: str
    segment_id: str


@router.post("/papers/init")
async def papers_init(req: InitTaskPapersRequest, session: AsyncSession = Depends(get_db)):
    """进入任务自动整备(幂等):Paper Discovery 线索 → Paper Library 去重 → Task Workspace。
    已完成(workspace 非空)且非 force → skipped,直接返回现状;失败不阻塞(返回失败明细)。"""
    return await auto_init_task_papers(session, req.ranking_id, force=req.force)


@router.post("/candidates/sync")
async def candidates_sync(req: InitTaskPapersRequest, session: AsyncSession = Depends(get_db)):
    """Step 3 结果 → Evidence Candidate(仅 SUPPORTED/PARTIAL;引用不复制;Gate 不通过→review_required)。"""
    return await sync_evidence_candidates(session, req.ranking_id)


@router.get("/candidates")
async def candidates_list(ranking_id: str = Query(...), session: AsyncSession = Depends(get_db)):
    rows = (await session.execute(text("""
        SELECT c.segment_id, c.paper_id, c.candidate_status, c.evidence_type,
               c.ai_decision, c.ai_confidence, c.selected_for_review,
               tr.id, tr.translated_text, tr.target_language, tr.translation_model,
               tr.translation_prompt_version,
               s.section_name, s.sentence_text, s.context_before, s.context_after,
               s.candidate_level, s.rule_score, s.matched_source_term,
               s.matched_target_term, s.matched_relation_terms, s.proximity, s.source_type,
               p.title, p.pmid, p.doi, p.journal, p.publication_year,
               r.reason, r.connection_type_supported, r.direction_support,
               r.supporting_phrase, r.contradiction_reason, r.failed
        FROM pew_evidence_candidates c
        JOIN pew_segments s ON s.id = c.segment_id
        JOIN paper_sources p ON p.id = c.paper_id
        LEFT JOIN pew_reviews r ON r.id = c.llm_review_id
        LEFT JOIN LATERAL (
            SELECT t.id, t.translated_text, t.target_language, t.translation_model,
                   t.translation_prompt_version
            FROM evidence_segment_translations t
            WHERE t.segment_id = c.segment_id AND t.target_language = 'zh-CN'
            ORDER BY t.created_at DESC LIMIT 1
        ) tr ON true
        WHERE c.ranking_id = :rid ORDER BY c.created_at"""),
        {"rid": _uuid(ranking_id)})).all()
    items = [{
        "segment_id": str(r[0]), "paper_id": str(r[1]),
        "candidate_status": r[2], "evidence_type": r[3], "ai_decision": r[4],
        "ai_confidence": float(r[5]) if r[5] is not None else None,
        "selected_for_review": bool(r[6]),
        "translation_id": str(r[7]) if r[7] else None,
        "translated_text": r[8], "translation_language": r[9], "translation_model": r[10],
        "translation_prompt_version": r[11],
        "section": r[12], "sentence": r[13],
        "context_before": r[14] or "", "context_after": r[15] or "",
        "candidate_level": r[16], "rule_score": float(r[17]) if r[17] is not None else None,
        "matched_source": r[18], "matched_target": r[19],
        "relation_terms": r[20] or [], "proximity": r[21], "source_type": r[22],
        "paper_title": r[23], "paper_pmid": r[24] or "", "paper_doi": r[25],
        "paper_journal": r[26] or "", "paper_year": r[27],
        "reason": r[28], "connection_type_supported": r[29],
        "direction_support": r[30], "supporting_phrase": r[31],
        "contradiction_reason": r[32], "failed": bool(r[33]),
    } for r in rows]
    return {"ranking_id": ranking_id, "items": items}

@router.post("/candidates/translate")
async def candidates_translate(req: TranslateCandidatesRequest, session: AsyncSession = Depends(get_db)):
    """中文辅助翻译(仅 candidate 的 supported/partial;幂等;force=覆盖重译)。"""
    return await translate_evidence_candidates(
        session, req.ranking_id, req.segment_ids, force=req.force)


@router.post("/candidates/select")
async def candidates_select(req: SelectCandidateRequest, session: AsyncSession = Depends(get_db)):
    """研究者选择/取消某条候选证据(仅 candidate 状态)。"""
    await session.execute(text("""
        UPDATE pew_evidence_candidates SET selected_for_review = :sel, updated_at = now()
        WHERE ranking_id = :rid AND segment_id = :sid AND candidate_status = 'candidate'"""),
        {"sel": req.selected, "rid": req.ranking_id, "sid": req.segment_id})
    await session.commit()
    return {"segment_id": req.segment_id, "selected": req.selected}


@router.post("/candidates/exclude")
async def candidates_exclude(req: ExcludeCandidateRequest, session: AsyncSession = Depends(get_db)):
    """研究者排除(保留 Segment/LLM Review 历史;仅改 candidate_status)。"""
    await session.execute(text("""
        UPDATE pew_evidence_candidates SET candidate_status = 'excluded',
            selected_for_review = false, updated_at = now()
        WHERE ranking_id = :rid AND segment_id = :sid"""),
        {"rid": req.ranking_id, "sid": req.segment_id})
    await session.commit()
    return {"segment_id": req.segment_id, "candidate_status": "excluded"}


@router.post("/segments/run")
async def run_segments(req: RunSegmentsRequest, session: AsyncSession = Depends(get_db)):
    """Step 2 函数筛选(零 LLM):当前任务论文 → 疑似证据片段(strong/medium/weak)。
    幂等:唯一键冲突更新信号,不重复建行。返回 inserted/updated + 分类统计。"""
    result = await run_rule_segments(
        session, req.ranking_id, req.paper_ids, req.connection_type)
    return result


@router.get("/segments")
async def segments_list(ranking_id: str = Query(...),
                        paper_id: str | None = Query(None),
                        session: AsyncSession = Depends(get_db)):
    rows = (await session.execute(text("""
        SELECT s.id, s.paper_id, s.section_name, s.source_type, s.sentence_text,
               s.context_before, s.context_after,
               s.matched_source_term, s.matched_target_term, s.proximity,
               s.retrieval_method, s.rule_score, r.decision, r.confidence,
               r.evidence_type, r.reason,
               s.candidate_level, s.matched_relation_terms,
               p.title, p.pmid, p.doi
        FROM pew_segments s
        JOIN paper_sources p ON p.id = s.paper_id
        LEFT JOIN pew_reviews r ON r.segment_id = s.id
        WHERE s.ranking_id = :rid
          AND (CAST(:paper AS uuid) IS NULL OR s.paper_id = CAST(:paper AS uuid))
        ORDER BY s.rule_score DESC NULLS LAST,
          CASE s.candidate_level WHEN 'strong' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
          CASE s.source_type WHEN 'fulltext' THEN 0 WHEN 'abstract' THEN 1 ELSE 2 END,
          s.created_at"""),
        {"rid": _uuid(ranking_id), "paper": _uuid(paper_id) if paper_id else None})).all()
    return {"ranking_id": ranking_id, "items": [{
        "segment_id": str(r[0]), "paper_id": str(r[1]), "section": r[2],
        "source_type": r[3], "sentence": r[4],
        "context_before": r[5] or "", "context_after": r[6] or "",
        "matched_source": r[7], "matched_target": r[8], "proximity": r[9],
        "retrieval_method": r[10],
        "rule_score": float(r[11]) if r[11] is not None else None,
        "decision": r[12], "confidence": float(r[13]) if r[13] is not None else None,
        "evidence_type": r[14], "reason": r[15],
        "candidate_level": r[16],
        "relation_terms": r[17] or [],
        "paper_title": r[18], "paper_pmid": r[19], "paper_doi": r[20],
    } for r in rows]}


@router.post("/reviews/run")
async def run_review(req: RunReviewRequest, session: AsyncSession = Depends(get_db)):
    """LLM Semantic Review（仅判定片段;不搜库不重提取）。"""
    result = await run_semantic_review(
        session, req.ranking_id, req.segment_ids, req.connection_type, force=req.force)
    return result


@router.get("/reviews")
async def reviews_list(ranking_id: str = Query(...), session: AsyncSession = Depends(get_db)):
    rows = (await session.execute(text("""
        SELECT s.id, s.sentence_text, s.section_name,
               s.context_before, s.context_after,
               s.matched_source_term, s.matched_target_term, s.proximity,
               s.rule_score,
               p.title, p.pmid,
               r.decision, r.confidence, r.evidence_type, r.reason,
               r.suggested_connection_type, r.direction_support,
               r.connection_type_supported, r.supporting_phrase,
               r.contradiction_reason, r.failed, r.model_name
        FROM pew_segments s
        JOIN paper_sources p ON p.id = s.paper_id
        JOIN pew_reviews r ON r.segment_id = s.id
        WHERE s.ranking_id = :rid ORDER BY s.created_at"""),
        {"rid": _uuid(ranking_id)})).all()
    # Evidence Candidate 计算:segment + (SUPPORTED|PARTIAL)（本页只读,不写任何正式表）
    candidates = [{
        "segment_id": str(r[0]), "sentence": r[1], "section": r[2],
        "context_before": r[3] or "", "context_after": r[4] or "",
        "matched_source": r[5], "matched_target": r[6], "proximity": r[7],
        "rule_score": float(r[8]) if r[8] is not None else None,
        "paper_title": r[9], "paper_pmid": r[10],
        "decision": r[11],
        "confidence": float(r[12]) if r[12] is not None else None,
        "evidence_type": r[13], "reason": r[14],
        "suggested_connection_type": r[15], "direction_support": r[16],
        "connection_type_supported": r[17], "supporting_phrase": r[18],
        "contradiction_reason": r[19], "failed": bool(r[20]), "model_name": r[21],
        "candidate": r[11] in ("supported", "partial_support") and not bool(r[20]),
    } for r in rows]
    return {"ranking_id": ranking_id,
            "items": [c for c in candidates],
            "candidates": [c for c in candidates if c["candidate"]]}


@router.get("/translations")
async def translations_list(ranking_id: str | None = Query(None),
                            segment_ids: str | None = Query(None),
                            session: AsyncSession = Depends(get_db)):
    """翻译资产读取(供人工审核/晋升/图谱详情;零模型调用)。"""
    conds = []
    params: dict = {}
    if ranking_id:
        conds.append("c.ranking_id = CAST(:rid AS uuid)")
        params["rid"] = ranking_id
    if segment_ids:
        ids = [x.strip() for x in segment_ids.split(",") if x.strip()]
        conds.append("t.segment_id = ANY(CAST(:sids AS uuid[]))")
        params["sids"] = ids
    where = f"WHERE {' AND '.join(conds)}" if conds else ""
    rows = (await session.execute(text(f"""
        SELECT t.id, t.segment_id, t.paper_id, t.target_language, t.translated_text,
               t.translation_model, t.translation_prompt_version, t.provenance_json,
               c.ranking_id
        FROM evidence_segment_translations t
        LEFT JOIN pew_evidence_candidates c ON c.segment_id = t.segment_id
        {where}
        ORDER BY t.created_at DESC"""), params)).all()
    return {"items": [{
        "translation_id": str(r[0]), "segment_id": str(r[1]), "paper_id": str(r[2]),
        "target_language": r[3], "translated_text": r[4],
        "translation_model": r[5], "translation_prompt_version": r[6],
        "provenance_json": r[7] or {}, "ranking_id": str(r[8]) if r[8] else None,
    } for r in rows]}
