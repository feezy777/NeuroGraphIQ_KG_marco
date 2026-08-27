"""Macro Candidate Governance 只读查询端点(治理工作流前端融合用)。

* GET /api/macro-candidates/rankings
  — 候选连接排名列表(pair 聚合):source/target region 名、paper_count、
    evidence_count、score、priority_level、created_at;可选 status 过滤。
* GET /api/macro-candidates/rankings/{ranking_id}
  — 单条排名详情:candidate_pair_ids + ranking_reason(五因素分解)。
* GET /api/macro-candidates/reviews
  — LLM 科学审核结果列表(macro_candidate_connection_llm_reviews):
    decision / connection_type / direction / confidence / reason / model /
    raw_response_json / created_at。

只读查询,不写任何表;不调用 LLM;数据源:
  paper_connection_candidate_rankings  +  macro_candidate_connection_llm_reviews
  (均为 Macro 论文候选治理链已有产物)。
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import macro_candidate_rule_validation_service as rvs

router = APIRouter(tags=["Macro Candidate Governance"])


class RuleValidateRequest(BaseModel):
    ranking_id: uuid.UUID | None = None

RANKINGS_LIST_SQL = """\
SELECT r.id, r.source_region_id, r.target_region_id,
       rs.canonical_name_en AS source_name,
       rt.canonical_name_en AS target_name,
       r.paper_count, r.evidence_count, r.score, r.priority_level,
       r.created_at
FROM paper_connection_candidate_rankings r
JOIN canonical_brain_regions rs ON rs.id = r.source_region_id
JOIN canonical_brain_regions rt ON rt.id = r.target_region_id
"""


def _fmt_ts(v) -> str | None:
    """时间戳 → ISO 字符串(datetime / 字符串 / None 统一)。"""
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def _ranking_row_to_dict(row) -> dict:
    return {
        "id": str(row[0]),
        "source_region_id": str(row[1]),
        "target_region_id": str(row[2]),
        "source_name": row[3],
        "target_name": row[4],
        "paper_count": row[5],
        "evidence_count": row[6],
        "score": float(row[7]) if row[7] is not None else None,
        "priority_level": row[8],
        "created_at": _fmt_ts(row[9]),
    }


@router.get("/rankings")
async def list_rankings(
    priority_level: str | None = Query(None, description="A|B|C 过滤"),
    source_region_id: uuid.UUID | None = Query(None),
    target_region_id: uuid.UUID | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    """候选连接排名列表(score 降序;支持优先级/脑区过滤)。"""
    clauses = []
    params: dict = {"lim": limit, "off": offset}
    if priority_level:
        clauses.append("r.priority_level = :pl")
        params["pl"] = priority_level
    if source_region_id:
        clauses.append("r.source_region_id = :src")
        params["src"] = str(source_region_id)
    if target_region_id:
        clauses.append("r.target_region_id = :tgt")
        params["tgt"] = str(target_region_id)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = (await session.execute(
        text(RANKINGS_LIST_SQL + where +
             " ORDER BY r.score DESC, r.paper_count DESC, r.id ASC LIMIT :lim OFFSET :off"),
        params)).all()
    total = (await session.execute(
        text("SELECT count(*) FROM paper_connection_candidate_rankings"))).scalar()
    return {"total": total, "limit": limit, "offset": offset,
            "items": [_ranking_row_to_dict(r) for r in rows]}


@router.get("/rankings/{ranking_id}")
async def get_ranking_detail(
    ranking_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
):
    """单条排名详情(含五因素 ranking_reason 与候选对 id 溯源)。"""
    row = (await session.execute(
        text(RANKINGS_LIST_SQL + "WHERE r.id = :rid"),
        {"rid": str(ranking_id)})).first()
    if row is None:
        raise HTTPException(status_code=404, detail="ranking not found")
    detail = (await session.execute(
        text("""\
SELECT r.candidate_pair_ids, r.ranking_reason, r.provenance_json,
       (SELECT p.canonical_name_en FROM canonical_region_hierarchy h
          JOIN canonical_brain_regions p ON p.id = h.parent_region_id
         WHERE h.child_region_id = r.source_region_id LIMIT 1) AS source_parent,
       (SELECT p.canonical_name_en FROM canonical_region_hierarchy h
          JOIN canonical_brain_regions p ON p.id = h.parent_region_id
         WHERE h.child_region_id = r.target_region_id LIMIT 1) AS target_parent
FROM paper_connection_candidate_rankings r WHERE r.id = :rid"""),
        {"rid": str(ranking_id)})).first()
    item = _ranking_row_to_dict(row)
    item["candidate_pair_ids"] = [str(x) for x in (detail[0] or [])] if detail else []
    item["ranking_reason"] = detail[1] if detail else {}
    item["provenance_json"] = detail[2] if detail else {}
    item["source_parent_name"] = detail[3] if detail else None
    item["target_parent_name"] = detail[4] if detail else None
    return item


@router.get("/reviews")
async def list_reviews(
    decision: str | None = Query(None, description="supported|uncertain|not_supported"),
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    """LLM 科学审核结果列表(按 created_at 倒序;decision 可选过滤)。"""
    clauses = []
    params: dict = {"lim": limit, "off": offset}
    if decision:
        clauses.append("rv.decision = :dec")
        params["dec"] = decision
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = (await session.execute(
        text("""\
SELECT rv.ranking_id, rv.source_region_id, rv.target_region_id,
       rs.canonical_name_en AS source_name,
       rt.canonical_name_en AS target_name,
       rv.decision, rv.connection_type, rv.direction,
       rv.confidence, rv.evidence_strength, rv.reasoning,
       rv.model_name, rv.raw_response_json, rv.created_at,
       r.paper_count, r.evidence_count, r.score
FROM macro_candidate_connection_llm_reviews rv
JOIN canonical_brain_regions rs ON rs.id = rv.source_region_id
JOIN canonical_brain_regions rt ON rt.id = rv.target_region_id
LEFT JOIN paper_connection_candidate_rankings r ON r.id = rv.ranking_id
""" + where + " ORDER BY rv.created_at DESC, rv.id ASC LIMIT :lim OFFSET :off"),
        params)).all()
    total = (await session.execute(
        text("SELECT count(*) FROM macro_candidate_connection_llm_reviews"))).scalar()
    items = []
    for r in rows:
        items.append({
            "ranking_id": str(r[0]),
            "source_region_id": str(r[1]),
            "target_region_id": str(r[2]),
            "source_name": r[3],
            "target_name": r[4],
            "decision": r[5],
            "connection_type": r[6],
            "direction": r[7],
            "confidence": float(r[8]) if r[8] is not None else None,
            "evidence_strength": r[9],
            "reasoning": r[10],
            "model_name": r[11],
            "raw_response_json": r[12] or {},
            "created_at": _fmt_ts(r[13]),
            "paper_count": r[14],
            "evidence_count": r[15],
            "score": float(r[16]) if r[16] is not None else None,
        })
    return {"total": total, "limit": limit, "offset": offset, "items": items}


@router.post("/rule-validate")
async def rule_validate(
    body: RuleValidateRequest,
    session: AsyncSession = Depends(get_db),
):
    """运行 Macro 候选规则验证(candidate 层;仅写本组结果表)。

    * 无 body / ranking_id=None → 全量 1129 幂等跑批(validator_key 覆盖旧 run)
    * 指定 ranking_id → 仅重算该条(upsert 进最新 run 所在? 单条独立写入)
    只读源表;不修改 final/canonical/mirror/ontology。
    """
    if body.ranking_id is None:
        return await rvs.run_batch(session)
    rid = str(body.ranking_id)
    res = await rvs.run_rule_checks(session, rid)
    return {"ranking_id": rid, **res}


@router.get("/rule-validations")
async def list_rule_validations(
    ranking_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None, description="PASS|FAIL|BLOCKED"),
    limit: int = Query(1000, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    """规则验证结果列表(最近一次跑批;按 ranking/status 过滤)。"""
    clauses = []
    params: dict = {"lim": limit, "off": offset}
    if ranking_id:
        clauses.append("r.ranking_id = :rid")
        params["rid"] = str(ranking_id)
    if status:
        clauses.append("r.validation_status = :status")
        params["status"] = status
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = (await session.execute(
        text("""\
SELECT r.ranking_id, r.validation_status, r.rule_results, r.duplicate_existing,
       r.failed_rules, r.validator_version, r.validation_timestamp,
       rs.canonical_name_en AS source_name, rt.canonical_name_en AS target_name,
       rk.paper_count, rk.score::float
FROM macro_candidate_rule_validation_results r
JOIN paper_connection_candidate_rankings rk ON rk.id = r.ranking_id
JOIN canonical_brain_regions rs ON rs.id = rk.source_region_id
JOIN canonical_brain_regions rt ON rt.id = rk.target_region_id
""" + where + " ORDER BY r.validation_timestamp DESC LIMIT :lim OFFSET :off"),
        params)).all()
    total = (await session.execute(text(
        "SELECT count(*) FROM macro_candidate_rule_validation_results"))).scalar()
    items = []
    for r in rows:
        items.append({
            "ranking_id": str(r[0]),
            "validation_status": r[1],
            "rule_results": r[2] or [],
            "duplicate_existing": r[3] or {},
            "failed_rules": r[4] or [],
            "validator_version": r[5],
            "validation_timestamp": r[6].isoformat() if r[6] else None,
            "source_name": r[7],
            "target_name": r[8],
            "paper_count": r[9],
            "score": float(r[10]) if r[10] is not None else None,
        })
    return {"total": total, "limit": limit, "offset": offset, "items": items}


@router.get("/review-queue")
async def list_review_queue(
    kind: str = Query("enhancement", description="enhancement|novel"),
    limit: int = Query(300, ge=1, le=1000),
    session: AsyncSession = Depends(get_db),
):
    """Macro 治理人工审核双队列(复用现有 HumanReviewPanel;只读计算)。

    * enhancement —— 证据增强:rule BLOCKED + duplicate_existing + 已有 AI review
      对象类型 existing_connection_evidence,target_id = ranking_id
    * novel —— 新增连接候选:rule PASS + AI decision=SUPPORTED
      对象类型 macro_connection_candidate,target_id = ranking_id

    不落库;data 由 rankings + rule results + LLM reviews join。
    """
    kind_key = "macro_connection_candidate" if kind == "novel" else "existing_connection_evidence"
    rows = (await session.execute(
        text("""\
SELECT rk.id, rs.canonical_name_en AS src, rt.canonical_name_en AS tgt,
       rk.score, rk.paper_count, rk.priority_level,
       rv.decision, rv.confidence, rv.connection_type,
       v.validation_status
FROM paper_connection_candidate_rankings rk
JOIN canonical_brain_regions rs ON rs.id = rk.source_region_id
JOIN canonical_brain_regions rt ON rt.id = rk.target_region_id
LEFT JOIN macro_candidate_rule_validation_results v ON v.ranking_id = rk.id
LEFT JOIN macro_candidate_connection_llm_reviews rv ON rv.ranking_id = rk.id
WHERE (v.validation_status = 'PASS' AND rv.decision = 'supported'
       OR v.validation_status = 'BLOCKED' AND rv.decision IS NOT NULL)
ORDER BY (rv.decision = 'supported') DESC, rk.score DESC LIMIT :lim"""),
        {"lim": limit})).all()
    items = []
    for r in rows:
        status_val = (r[9] or "")
        decision_val = (r[6] or "")
        if kind == "novel":
            if not (status_val == "PASS" and decision_val == "supported"):
                continue
        else:
            if not (status_val == "BLOCKED" and decision_val is not None):
                continue
        items.append({
            "target_type": kind_key,
            "target_id": str(r[0]),
            "label": f"{r[1]} → {r[2]}",
            "confidence": float(r[7]) if r[7] is not None else None,
            "status": "awaiting_review",
            "evidenceCount": r[4],
            "ranking_score": float(r[3]) if r[3] is not None else None,
            "priority_level": r[5],
            "ai_decision": decision_val,
            "ai_connection_type": r[8],
            "rule_status": status_val,
        })
    return {"kind": kind, "total": len(items), "limit": limit, "items": items}
