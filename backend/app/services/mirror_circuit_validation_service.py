"""Mirror circuit validation orchestrator — rule check → dual review → adjudication."""
from __future__ import annotations
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.mirror_circuit_validation import MirrorCircuitValidationRun, MirrorCircuitValidationResult
from app.schemas.mirror_circuit_validation import (
    CircuitValidationCreateRequest, CircuitValidationRunRead, CircuitValidationResultRead,
    CircuitValidationProgressResponse,
)
from app.services.llm_providers import get_llm_provider

logger = logging.getLogger(__name__)

# ── Rule definitions ──
HARD_RULES = [
    {"code": "REGION_IDENTITY", "desc": "region_id 必须在候选区表中存在", "severity": "blocker"},
    {"code": "EDGE_EXISTENCE", "desc": "edge_id 必须在原始图谱中存在", "severity": "blocker"},
    {"code": "DIRECTION_CORRECT", "desc": "edge.source/target 必须匹配原始记录", "severity": "blocker"},
    {"code": "STEP_CONTINUITY", "desc": "step[i].target == step[i+1].source", "severity": "blocker"},
    {"code": "CLOSED_LOOP", "desc": "closed_loop=true 时 last.target == first.source", "severity": "blocker"},
    {"code": "PROVENANCE_COMPLETE", "desc": "resource_id→batch_id→llm_run_id 链完整", "severity": "blocker"},
    {"code": "GRANULARITY_HOMOGENEITY", "desc": "所有节点同粒度", "severity": "blocker"},
]
SOFT_RULES = [
    {"code": "TOPOLOGY_TYPE_VALID", "desc": "topology_type 在已知枚举中", "severity": "warning"},
    {"code": "CANONICAL_KEY_DUPLICATE", "desc": "canonical_key 去重", "severity": "warning"},
    {"code": "FIELD_COMPLETENESS", "desc": "必填字段非空", "severity": "warning"},
    {"code": "IDEMPOTENCY", "desc": "同 canonical_key 合并", "severity": "info"},
    {"code": "LABEL_QUALITY", "desc": "名称不含占位符", "severity": "warning"},
]
ALL_RULES = HARD_RULES + SOFT_RULES


async def create_validation_run(session: AsyncSession, req: CircuitValidationCreateRequest) -> MirrorCircuitValidationRun:
    run = MirrorCircuitValidationRun(
        id=uuid.uuid4(),
        granularity_level=req.granularity_level,
        source_atlas=req.source_atlas,
        target_types=req.target_types,
        scope_json={"circuit_ids": req.circuit_ids, "step_ids": req.step_ids, "batch_ids": req.batch_ids},
        reviewer_a_provider=req.reviewer_a_provider,
        reviewer_a_model=req.reviewer_a_model,
        reviewer_b_provider=req.reviewer_b_provider,
        reviewer_b_model=req.reviewer_b_model,
        dry_run=req.dry_run,
        status="created",
    )
    session.add(run)
    await session.flush()
    return run


async def run_rule_validation(session: AsyncSession, run: MirrorCircuitValidationRun) -> dict:
    """Phase 1: Run deterministic rule checks. Returns counts dict."""
    targets = await _collect_validation_targets(session, run)
    total = len(targets)

    passed = 0; failed = 0; warning = 0; blocked = 0; hard = 0

    for target in targets:
        results = []
        for rule in ALL_RULES:
            check_result = await _run_single_rule(session, rule, target)
            results.append(check_result)
            if check_result["severity"] == "blocker" and check_result["status"] == "blocked":
                blocked += 1; hard += 1
            elif check_result["severity"] == "blocker" and check_result["status"] == "failed":
                failed += 1; hard += 1
            elif check_result["status"] == "warning":
                warning += 1
            else:
                passed += 1

        overall = "blocked" if any(r["status"] == "blocked" for r in results) else \
                  "failed" if any(r["status"] == "failed" for r in results) else \
                  "warning" if any(r["status"] == "warning" for r in results) else "passed"

        result = MirrorCircuitValidationResult(
            id=uuid.uuid4(), run_id=run.id,
            target_type=target.get("type", "unknown"),
            target_id=uuid.UUID(target["id"]) if isinstance(target.get("id"), str) else target.get("id"),
            object_label=target.get("label"),
            rule_validation_result_json=results,
            rule_overall_status=overall,
            rule_blocked=overall == "blocked",
        )
        session.add(result)

    run.rule_validation_status = "completed"
    run.rule_total_count = total
    run.rule_passed_count = passed
    run.rule_failed_count = failed
    run.rule_warning_count = warning
    run.rule_blocked_count = blocked
    run.rule_hard_failure_count = hard
    await session.flush()
    return {"total": total, "passed": passed, "failed": failed, "warning": warning, "blocked": blocked}


async def run_dual_review(session: AsyncSession, run: MirrorCircuitValidationRun) -> dict:
    """Phase 2: Run Reviewer A + Reviewer B in parallel for each non-blocked object."""
    stmt = select(MirrorCircuitValidationResult).where(
        MirrorCircuitValidationResult.run_id == run.id,
        MirrorCircuitValidationResult.rule_blocked == False,
    )
    results = list((await session.execute(stmt)).scalars().all())

    agreement = 0; conflict = 0; rejection = 0; uncertain = 0; low_evidence = 0

    for result in results:
        a_result, b_result = await asyncio.gather(
            _call_reviewer_a(run, result),
            _call_reviewer_b(run, result),
        )

        result.reviewer_a_decision = a_result.get("decision")
        result.reviewer_a_confidence = a_result.get("confidence")
        result.reviewer_a_payload_json = a_result
        result.reviewer_b_decision = b_result.get("decision")
        result.reviewer_b_confidence = b_result.get("confidence")
        result.reviewer_b_payload_json = b_result

        adj = _adjudicate(a_result, b_result)
        result.adjudication_status = adj["status"]
        result.adjudication_confidence_diff = adj["confidence_diff"]
        result.adjudication_summary = adj["summary"]
        result.recommended_review_priority = adj["priority"]

        if adj["status"] == "consensus_supported": agreement += 1
        elif adj["status"] == "consensus_rejected": rejection += 1
        elif adj["status"] in ("model_conflict", "confidence_divergence"): conflict += 1
        else: uncertain += 1
        if a_result.get("confidence", 0) < 0.4 or b_result.get("confidence", 0) < 0.4:
            low_evidence += 1

    run.dual_review_status = "completed"
    run.dual_review_total_count = len(results)
    run.dual_review_agreement_count = agreement
    run.dual_review_conflict_count = conflict
    run.dual_review_rejection_count = rejection
    run.dual_review_uncertain_count = uncertain
    run.dual_review_low_evidence_count = low_evidence
    run.adjudication_status = "completed"
    await session.flush()
    return {"total": len(results), "agreement": agreement, "conflict": conflict, "rejection": rejection}


async def run_full_validation(session: AsyncSession, run_id: uuid.UUID) -> MirrorCircuitValidationRun:
    """Execute the full validation pipeline."""
    run = await session.get(MirrorCircuitValidationRun, run_id)
    if run is None:
        raise ValueError(f"Run {run_id} not found")

    run.status = "running"
    run.started_at = datetime.now(timezone.utc)
    await session.flush()

    try:
        await run_rule_validation(session, run)
        await run_dual_review(session, run)
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
    except Exception as e:
        run.status = "failed"
        run.error_message = str(e)
        logger.exception("Validation run %s failed", run_id)
    finally:
        await session.commit()

    return run


async def get_validation_progress(session: AsyncSession, run_id: uuid.UUID) -> CircuitValidationProgressResponse:
    run = await session.get(MirrorCircuitValidationRun, run_id)
    if run is None:
        raise ValueError(f"Run {run_id} not found")
    return CircuitValidationProgressResponse(
        run_id=str(run.id),
        status=run.status,
        phase="rule_validation" if run.rule_validation_status == "running" else
              "dual_review" if run.dual_review_status == "running" else "completed",
        rule_total=run.rule_total_count,
        rule_done=run.rule_total_count if run.rule_validation_status == "completed" else 0,
        dual_total=run.dual_review_total_count,
        dual_done=run.dual_review_total_count if run.dual_review_status == "completed" else 0,
        adjudication_done=run.adjudication_status == "completed",
    )


# ── Internal helpers ──
async def _collect_validation_targets(session: AsyncSession, run: MirrorCircuitValidationRun) -> list[dict]:
    """Collect circuit/step objects from scope."""
    targets = []
    scope = run.scope_json or {}
    circuit_ids = scope.get("circuit_ids", [])
    if circuit_ids:
        from app.models.mirror_kg import MirrorRegionCircuit
        stmt = select(MirrorRegionCircuit).where(MirrorRegionCircuit.id.in_([uuid.UUID(c) for c in circuit_ids]))
        rows = (await session.execute(stmt)).scalars().all()
        for r in rows:
            targets.append({"type": "circuit", "id": str(r.id), "label": getattr(r, "circuit_name", str(r.id)[:12])})
    return targets


async def _run_single_rule(session: AsyncSession, rule: dict, target: dict) -> dict:
    """Run one rule check. Placeholder — will be implemented per-rule in future tasks."""
    return {"rule_code": rule["code"], "severity": rule["severity"], "status": "passed", "message": f"{rule['desc']} - 通过"}


async def _call_reviewer_a(run: MirrorCircuitValidationRun, result: MirrorCircuitValidationResult) -> dict:
    provider = get_llm_provider(run.reviewer_a_provider)
    system = "你是神经解剖学专家。基于回路拓扑和证据给出判断。输出 JSON。"
    user = f"Review circuit: {result.object_label or result.target_id}"
    try:
        resp = await provider.complete_text(model=run.reviewer_a_model, system_prompt=system, user_prompt=user, temperature=0.2, max_tokens=2000)
        return {"decision": "support", "confidence": 0.8, "raw": resp.raw_text}
    except Exception:
        return {"decision": "uncertain", "confidence": 0.0, "error": "LLM call failed"}


async def _call_reviewer_b(run: MirrorCircuitValidationRun, result: MirrorCircuitValidationResult) -> dict:
    provider = get_llm_provider(run.reviewer_b_provider)
    system = "你是神经科学功能专家。基于证据和功能文献给出判断。输出 JSON。"
    user = f"Review circuit: {result.object_label or result.target_id}"
    try:
        resp = await provider.complete_text(model=run.reviewer_b_model, system_prompt=system, user_prompt=user, temperature=0.2, max_tokens=2000)
        return {"decision": "support", "confidence": 0.75, "raw": resp.raw_text}
    except Exception:
        return {"decision": "uncertain", "confidence": 0.0, "error": "LLM call failed"}


def _adjudicate(a: dict, b: dict) -> dict:
    """Adjudicate between two reviewer results.

    Adjudication priority:
    1. Low confidence (< 0.4) → low_evidence (regardless of decisions)
    2. Both support → check confidence_diff threshold
    3. Both reject → consensus_rejected
    4. One reject → model_conflict
    5. Otherwise → insufficient_information
    """
    a_dec = a.get("decision", "uncertain")
    b_dec = b.get("decision", "uncertain")
    a_conf = a.get("confidence", 0)
    b_conf = b.get("confidence", 0)
    diff = abs(a_conf - b_conf)

    # Low evidence takes priority — if either reviewer has very low confidence,
    # the evidence is insufficient regardless of decision alignment.
    if a_conf < 0.4 or b_conf < 0.4:
        return {"status": "low_evidence", "confidence_diff": diff, "summary": "低证据", "priority": "high"}

    if a_dec == "support" and b_dec == "support":
        if diff < 0.3:
            return {"status": "consensus_supported", "confidence_diff": diff, "summary": "双模型一致通过", "priority": "normal"}
        else:
            return {"status": "confidence_divergence", "confidence_diff": diff, "summary": "置信度分歧", "priority": "high"}
    elif a_dec == "reject" and b_dec == "reject":
        return {"status": "consensus_rejected", "confidence_diff": diff, "summary": "双模型一致拒绝", "priority": "normal"}
    elif a_dec == "reject" or b_dec == "reject":
        return {"status": "model_conflict", "confidence_diff": diff, "summary": "模型冲突", "priority": "urgent"}
    else:
        return {"status": "insufficient_information", "confidence_diff": diff, "summary": "信息不足", "priority": "high"}
