"""API router for circuit validation orchestration.

Provides endpoints to create, start (background), list, detail, progress,
and cancel circuit validation runs.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.mirror_circuit_validation import (
    MirrorCircuitValidationResult,
    MirrorCircuitValidationRun,
)
from app.schemas.mirror_circuit_validation import (
    CircuitValidationCreateRequest,
    CircuitValidationProgressResponse,
    CircuitValidationResultRead,
    CircuitValidationRunDetail,
    CircuitValidationRunRead,
)
from app.services import mirror_circuit_validation_service as vc

router = APIRouter(tags=["Circuit Validation"])


# ---------------------------------------------------------------------------
# POST /api/validation/circuit/runs
# ---------------------------------------------------------------------------


@router.post(
    "/runs",
    status_code=201,
)
async def create_run(
    req: CircuitValidationCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new circuit validation run. Returns run + scan stats."""
    run, stats = await vc.create_validation_run(db, req)
    await db.commit()
    result = _run_to_read(run).model_dump()
    result["scan_stats"] = stats
    return result


# ---------------------------------------------------------------------------
# POST /api/validation/circuit/runs/{run_id}/start
# ---------------------------------------------------------------------------


@router.post(
    "/runs/{run_id}/start",
    response_model=CircuitValidationRunRead,
)
async def start_run(
    run_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> CircuitValidationRunRead:
    """Start the full validation pipeline as a background task."""
    run = await db.get(MirrorCircuitValidationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Validation run not found")
    if run.status not in ("created", "queued"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot start run with status '{run.status}'",
        )

    background_tasks.add_task(vc.run_full_validation_background, run_id)
    run.status = "queued"
    await db.commit()
    await db.refresh(run)
    return _run_to_read(run)


# ---------------------------------------------------------------------------
# GET /api/validation/circuit/runs
# ---------------------------------------------------------------------------


@router.get(
    "/runs",
    response_model=list[CircuitValidationRunRead],
)
async def list_runs(
    status: Optional[str] = Query(None, description="Filter by status"),
    granularity_level: Optional[str] = Query(None, description="Filter by granularity level"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[CircuitValidationRunRead]:
    """List validation runs with optional filters."""
    stmt = select(MirrorCircuitValidationRun).order_by(
        desc(MirrorCircuitValidationRun.created_at),
    )
    if status:
        stmt = stmt.where(MirrorCircuitValidationRun.status == status)
    if granularity_level:
        stmt = stmt.where(
            MirrorCircuitValidationRun.granularity_level == granularity_level,
        )
    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    runs = result.scalars().all()
    return [_run_to_read(r) for r in runs]


# ---------------------------------------------------------------------------
# GET /api/validation/circuit/runs/{run_id}
# ---------------------------------------------------------------------------


@router.get(
    "/runs/{run_id}",
    response_model=CircuitValidationRunDetail,
)
async def get_run_detail(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> CircuitValidationRunDetail:
    """Get validation run detail with results."""
    run = await db.get(MirrorCircuitValidationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Validation run not found")

    stmt_res = (
        select(MirrorCircuitValidationResult)
        .where(MirrorCircuitValidationResult.run_id == run_id)
        .order_by(MirrorCircuitValidationResult.created_at)
    )
    result_res = await db.execute(stmt_res)
    results = result_res.scalars().all()

    return CircuitValidationRunDetail(
        **_run_to_read(run).model_dump(),
        results=[_result_to_read(r) for r in results],
    )


# ---------------------------------------------------------------------------
# GET /api/validation/circuit/runs/{run_id}/progress
# ---------------------------------------------------------------------------


@router.get(
    "/runs/{run_id}/progress",
    response_model=CircuitValidationProgressResponse,
)
async def get_progress(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> CircuitValidationProgressResponse:
    """Poll validation progress."""
    try:
        return await vc.get_validation_progress(db, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ---------------------------------------------------------------------------
# POST /api/validation/circuit/runs/{run_id}/cancel
# ---------------------------------------------------------------------------


@router.post(
    "/runs/{run_id}/cancel",
    response_model=CircuitValidationRunRead,
)
async def cancel_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> CircuitValidationRunRead:
    """Cancel a validation run."""
    run = await db.get(MirrorCircuitValidationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Validation run not found")
    if run.status in ("completed", "failed", "cancelled"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot cancel run with status '{run.status}'",
        )
    run.status = "cancelled"
    run.error_message = "Cancelled by user"
    await db.commit()
    await db.refresh(run)
    return _run_to_read(run)


# ---------------------------------------------------------------------------
# GET /api/validation/circuit/candidates
# ---------------------------------------------------------------------------


@router.get("/candidates")
async def list_candidates(
    granularity_level: Optional[str] = Query(None, description="Filter by granularity"),
    topology_type: Optional[str] = Query(None, description="Filter by topology/circuit type"),
    min_confidence: Optional[float] = Query(None, ge=0, le=1, description="Minimum confidence"),
    max_confidence: Optional[float] = Query(None, ge=0, le=1, description="Maximum confidence"),
    min_evidence: Optional[int] = Query(None, ge=0, description="Min evidence length"),
    search: Optional[str] = Query(None, description="Search circuit_name"),
    rule_status: Optional[str] = Query(None, description="Rule overall status"),
    review_status: Optional[str] = Query(None, description="Review status"),
    adjudication_status: Optional[str] = Query(None, description="Adjudication status"),
    promotion_status: Optional[str] = Query(None, description="Promotion status"),
    only_unvalidated: bool = Query(False, description="Only circuits with no validation results"),
    only_pending_review: bool = Query(False, description="Only pending review circuits"),
    only_not_promoted: bool = Query(False, description="Only not promoted circuits"),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List candidate circuits for direct selection."""
    from app.models.mirror_kg import MirrorRegionCircuit
    from app.models.mirror_macro_clinical import MirrorCircuitStep

    q = select(MirrorRegionCircuit)
    count_q = select(func.count()).select_from(MirrorRegionCircuit)

    if granularity_level and granularity_level != "all":
        q = q.where(MirrorRegionCircuit.granularity_level == granularity_level)
        count_q = count_q.where(MirrorRegionCircuit.granularity_level == granularity_level)
    if topology_type:
        q = q.where(MirrorRegionCircuit.circuit_type == topology_type)
        count_q = count_q.where(MirrorRegionCircuit.circuit_type == topology_type)
    if min_confidence is not None:
        q = q.where(MirrorRegionCircuit.confidence >= min_confidence)
        count_q = count_q.where(MirrorRegionCircuit.confidence >= min_confidence)
    if max_confidence is not None:
        q = q.where(MirrorRegionCircuit.confidence <= max_confidence)
        count_q = count_q.where(MirrorRegionCircuit.confidence <= max_confidence)
    if search:
        q = q.where(MirrorRegionCircuit.circuit_name.ilike(f'%{search}%'))
        count_q = count_q.where(MirrorRegionCircuit.circuit_name.ilike(f'%{search}%'))
    if min_evidence is not None:
        q = q.where(func.length(MirrorRegionCircuit.evidence_text) >= min_evidence)
        count_q = count_q.where(func.length(MirrorRegionCircuit.evidence_text) >= min_evidence)
    if review_status:
        q = q.where(MirrorRegionCircuit.review_status == review_status)
        count_q = count_q.where(MirrorRegionCircuit.review_status == review_status)
    if promotion_status:
        q = q.where(MirrorRegionCircuit.promotion_status == promotion_status)
        count_q = count_q.where(MirrorRegionCircuit.promotion_status == promotion_status)
    if only_not_promoted:
        q = q.where(MirrorRegionCircuit.promotion_status != 'promoted_to_final')
        count_q = count_q.where(MirrorRegionCircuit.promotion_status != 'promoted_to_final')

    q = q.order_by(MirrorRegionCircuit.created_at.desc()).offset(offset).limit(limit)

    total = (await db.execute(count_q)).scalar_one()
    rows = list((await db.execute(q)).scalars().all())

    # Enrich with step counts and latest validation results
    items = []
    for r in rows:
        step_count = (await db.execute(
            select(func.count()).select_from(MirrorCircuitStep).where(MirrorCircuitStep.circuit_id == r.id)
        )).scalar_one()

        # Get latest validation result for this circuit
        latest_val = (await db.execute(
            select(MirrorCircuitValidationResult)
            .where(
                MirrorCircuitValidationResult.target_id == r.id,
                MirrorCircuitValidationResult.target_type == "circuit",
            )
            .order_by(MirrorCircuitValidationResult.created_at.desc())
            .limit(1)
        )).scalars().first()

        rule_overall_status = None
        reviewer_a_decision = None
        reviewer_b_decision = None
        adjudication_status = None
        if latest_val:
            rule_overall_status = latest_val.rule_overall_status
            reviewer_a_decision = latest_val.reviewer_a_decision
            reviewer_b_decision = latest_val.reviewer_b_decision
            adjudication_status = latest_val.adjudication_status

        items.append({
            "id": str(r.id),
            "circuit_name": r.circuit_name or str(r.id)[:12],
            "granularity_level": r.granularity_level,
            "circuit_type": r.circuit_type or "unknown",
            "topology_type": "unknown",
            "closed_loop": False,
            "step_count": step_count,
            "confidence": float(r.confidence) if r.confidence else 0.0,
            "function_association": r.function_association or "",
            "evidence_text": (r.evidence_text or "")[:200],
            "review_status": r.review_status or "pending",
            "promotion_status": r.promotion_status or "not_promoted",
            "mirror_status": r.mirror_status or "llm_suggested",
            "source_atlas": r.source_atlas or "",
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "rule_overall_status": rule_overall_status,
            "reviewer_a_decision": reviewer_a_decision,
            "reviewer_b_decision": reviewer_b_decision,
            "adjudication_status": adjudication_status,
        })

    return {"items": items, "total": total}


# ---------------------------------------------------------------------------
# GET /api/validation/circuit/candidates/counts
# ---------------------------------------------------------------------------


@router.get("/candidates/counts")
async def get_candidate_counts(
    granularity_level: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Get aggregate counts for the candidate circuit table."""
    from app.models.mirror_kg import MirrorRegionCircuit
    from app.models.mirror_macro_clinical import MirrorCircuitStep

    base_q = select(func.count()).select_from(MirrorRegionCircuit)
    if granularity_level and granularity_level != "all":
        base_q = base_q.where(MirrorRegionCircuit.granularity_level == granularity_level)

    total = (await db.execute(base_q)).scalar_one()

    # Count by circuit_type
    type_counts_q = select(
        MirrorRegionCircuit.circuit_type,
        func.count().label("cnt")
    )
    if granularity_level and granularity_level != "all":
        type_counts_q = type_counts_q.where(MirrorRegionCircuit.granularity_level == granularity_level)
    type_counts_q = type_counts_q.group_by(MirrorRegionCircuit.circuit_type)
    type_rows = list((await db.execute(type_counts_q)).all())
    type_counts = {r.circuit_type: r.cnt for r in type_rows}

    # Count by review_status
    review_q = select(
        MirrorRegionCircuit.review_status,
        func.count().label("cnt")
    )
    if granularity_level and granularity_level != "all":
        review_q = review_q.where(MirrorRegionCircuit.granularity_level == granularity_level)
    review_q = review_q.group_by(MirrorRegionCircuit.review_status)
    review_rows = list((await db.execute(review_q)).all())
    review_counts = {r.review_status: r.cnt for r in review_rows}

    # Step count
    steps_q = select(func.count()).select_from(MirrorCircuitStep)
    if granularity_level and granularity_level != "all":
        steps_q = steps_q.where(MirrorCircuitStep.granularity_level == granularity_level)
    total_steps = (await db.execute(steps_q)).scalar_one()

    return {
        "total_circuits": total,
        "total_steps": total_steps,
        "types": type_counts,
        "review_status": review_counts,
    }


# ---------------------------------------------------------------------------
# POST /api/validation/circuit/selection/rule-validate
# ---------------------------------------------------------------------------


@router.post("/selection/rule-validate")
async def selection_rule_validate(
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Direct selection: send circuits to rule validation."""
    circuit_ids = body.get("circuit_ids", [])
    force = body.get("force_revalidate", False)

    if not circuit_ids:
        raise HTTPException(status_code=400, detail="circuit_ids required")

    # Count and filter
    from app.models.mirror_kg import MirrorRegionCircuit

    valid = list((await db.execute(
        select(MirrorRegionCircuit).where(MirrorRegionCircuit.id.in_([uuid.UUID(c) for c in circuit_ids]))
    )).scalars().all())

    stats = {
        "selected_count": len(circuit_ids),
        "eligible_count": len(valid),
        "skipped_count": len(circuit_ids) - len(valid),
        "skip_reasons": {"invalid_id": len(circuit_ids) - len(valid)},
        "status": "queued",
    }

    if not valid:
        return {**stats, "message": "No valid circuits found"}

    # Create validation run for the selected circuits
    req = CircuitValidationCreateRequest(
        granularity_level=valid[0].granularity_level if valid else "all",
        circuit_ids=[str(v.id) for v in valid],
    )
    run, scan_stats = await vc.create_validation_run(db, req)
    stats["internal_run_id"] = str(run.id)
    stats.update(scan_stats)
    await db.commit()

    # Start async
    import asyncio

    asyncio.create_task(vc.run_full_validation_background(run.id))

    return stats


# ---------------------------------------------------------------------------
# GET /api/validation/circuit/counts
# ---------------------------------------------------------------------------

@router.get("/counts")
async def get_counts(
    granularity_level: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get aggregate counts for the validation center stats bar."""
    total_runs_q = select(func.count()).select_from(MirrorCircuitValidationRun)
    completed_q = select(func.count()).select_from(MirrorCircuitValidationRun).where(MirrorCircuitValidationRun.status == "completed")
    if granularity_level:
        total_runs_q = total_runs_q.where(MirrorCircuitValidationRun.granularity_level == granularity_level)
        completed_q = completed_q.where(MirrorCircuitValidationRun.granularity_level == granularity_level)

    total_runs = (await db.execute(total_runs_q)).scalar_one()
    completed_runs = (await db.execute(completed_q)).scalar_one()

    # Count approved circuits from mirror_region_circuits
    from app.models.mirror_kg import MirrorRegionCircuit
    approved_q = select(func.count()).select_from(MirrorRegionCircuit).where(
        MirrorRegionCircuit.review_status == "approved"
    )
    if granularity_level:
        approved_q = approved_q.where(MirrorRegionCircuit.granularity_level == granularity_level)
    approved_count = (await db.execute(approved_q)).scalar_one()

    # Real circuit count from mirror_region_circuits
    total_circuits_q = select(func.count()).select_from(MirrorRegionCircuit)
    if granularity_level:
        total_circuits_q = total_circuits_q.where(MirrorRegionCircuit.granularity_level == granularity_level)
    total_circuits = (await db.execute(total_circuits_q)).scalar_one()

    # Real step count from mirror_circuit_steps
    from app.models.mirror_macro_clinical import MirrorCircuitStep
    total_steps_q = select(func.count()).select_from(MirrorCircuitStep)
    if granularity_level:
        total_steps_q = total_steps_q.where(MirrorCircuitStep.granularity_level == granularity_level)
    total_steps = (await db.execute(total_steps_q)).scalar_one()

    # Rule-checked count (circuits that have completed rule validation)
    rule_checked_q = select(func.count()).select_from(MirrorCircuitValidationResult).where(
        MirrorCircuitValidationResult.rule_overall_status.isnot(None)
    )
    rule_checked = (await db.execute(rule_checked_q)).scalar_one()

    # Aggregate rule_passed_count and dual_review_agreement_count from completed runs
    agg_q = select(
        func.coalesce(func.sum(MirrorCircuitValidationRun.rule_passed_count), 0),
        func.coalesce(func.sum(MirrorCircuitValidationRun.dual_review_agreement_count), 0),
    ).where(MirrorCircuitValidationRun.status == "completed")
    if granularity_level:
        agg_q = agg_q.where(MirrorCircuitValidationRun.granularity_level == granularity_level)
    agg_row = (await db.execute(agg_q)).one()
    rule_passed_total = agg_row[0] or 0
    dual_agreement_total = agg_row[1] or 0

    return {
        "total_runs": total_runs,
        "completed_runs": completed_runs,
        "pending_review": approved_count or 0,
        "rule_passed": rule_passed_total or 0,
        "dual_agreement": dual_agreement_total or 0,
        "promoted": 0,
        "total_circuits": total_circuits or 0,
        "total_steps": total_steps or 0,
        "rule_checked": rule_checked or 0,
    }


# ---------------------------------------------------------------------------
# GET /api/validation/circuit/candidates/{circuit_id}
# ---------------------------------------------------------------------------


@router.get("/candidates/{circuit_id}")
async def get_circuit_detail(
    circuit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get complete circuit detail with all related data (steps, regions, functions, evidence, validation)."""
    from app.models.mirror_kg import (
        MirrorCircuitRegion,
        MirrorEvidenceRecord,
        MirrorRegionCircuit,
    )
    from app.models.mirror_macro_clinical import MirrorCircuitFunction, MirrorCircuitStep
    from app.models.mirror_circuit_validation import MirrorCircuitValidationResult
    from app.models.candidate import CandidateBrainRegion

    circuit = await db.get(MirrorRegionCircuit, circuit_id)
    if circuit is None:
        raise HTTPException(404, f"Circuit {circuit_id} not found")

    # Load steps ordered by step_order
    steps = list(
        (
            await db.execute(
                select(MirrorCircuitStep)
                .where(MirrorCircuitStep.circuit_id == circuit_id)
                .order_by(MirrorCircuitStep.step_order)
            )
        )
        .scalars()
        .all()
    )

    # Load functions
    functions = list(
        (
            await db.execute(
                select(MirrorCircuitFunction).where(
                    MirrorCircuitFunction.circuit_id == circuit_id
                )
            )
        )
        .scalars()
        .all()
    )

    # Load regions from mirror_circuit_regions
    regions = list(
        (
            await db.execute(
                select(MirrorCircuitRegion).where(
                    MirrorCircuitRegion.circuit_id == circuit_id
                )
            )
        )
        .scalars()
        .all()
    )

    # Load candidate region details
    region_ids = [r.region_candidate_id for r in regions if r.region_candidate_id]
    candidate_regions = []
    if region_ids:
        candidate_regions = list(
            (
                await db.execute(
                    select(CandidateBrainRegion).where(
                        CandidateBrainRegion.id.in_(region_ids)
                    )
                )
            )
            .scalars()
            .all()
        )

    # Load validation results (target_type == "circuit")
    val_results = list(
        (
            await db.execute(
                select(MirrorCircuitValidationResult).where(
                    MirrorCircuitValidationResult.target_id == circuit_id,
                    MirrorCircuitValidationResult.target_type == "circuit",
                )
            )
        )
        .scalars()
        .all()
    )

    # Load evidence records
    evidence = list(
        (
            await db.execute(
                select(MirrorEvidenceRecord).where(
                    MirrorEvidenceRecord.evidence_target_id == circuit_id,
                )
            )
        )
        .scalars()
        .all()
    )

    candidate_map = {str(cr.id): cr for cr in candidate_regions}

    return {
        "circuit": {
            "id": str(circuit.id),
            "circuit_name": circuit.circuit_name,
            "name_cn": getattr(circuit, "name_cn", None),
            "circuit_type": circuit.circuit_type,
            "description": getattr(circuit, "description", None),
            "function_association": circuit.function_association,
            "confidence": float(circuit.confidence) if circuit.confidence else None,
            "granularity_level": circuit.granularity_level,
            "granularity_family": getattr(circuit, "granularity_family", None),
            "source_atlas": circuit.source_atlas,
            "source_version": getattr(circuit, "source_version", None),
            "mirror_status": circuit.mirror_status,
            "review_status": circuit.review_status,
            "promotion_status": circuit.promotion_status,
            "evidence_text": circuit.evidence_text,
            "uncertainty_reason": getattr(circuit, "uncertainty_reason", None),
            "canonical_start_region_id": str(circuit.canonical_start_region_id)
            if getattr(circuit, "canonical_start_region_id", None)
            else None,
            "canonical_end_region_id": str(circuit.canonical_end_region_id)
            if getattr(circuit, "canonical_end_region_id", None)
            else None,
            "circuit_strength": float(circuit.circuit_strength)
            if getattr(circuit, "circuit_strength", None)
            else None,
            "created_at": circuit.created_at.isoformat() if circuit.created_at else None,
            "updated_at": circuit.updated_at.isoformat() if circuit.updated_at else None,
            "resource_id": str(circuit.resource_id) if circuit.resource_id else None,
            "batch_id": str(circuit.batch_id) if circuit.batch_id else None,
            "llm_run_id": str(circuit.llm_run_id)
            if getattr(circuit, "llm_run_id", None)
            else None,
        },
        "granularity": {
            "level": circuit.granularity_level,
            "family": getattr(circuit, "granularity_family", None),
            "atlas": circuit.source_atlas,
            "version": getattr(circuit, "source_version", None),
            "region_pool_match": True,
            "mixed_granularity_warning": None,
        },
        "topology": {
            "circuit_type": circuit.circuit_type,
            "closed_loop": False,
            "canonical_key": None,
            "node_count": len(steps),
            "start_region": steps[0].step_name if steps else None,
            "end_region": steps[-1].step_name if steps else None,
        },
        "steps": [
            {
                "step_order": s.step_order,
                "step_name": s.step_name,
                "step_type": s.step_type,
                "role": s.role,
                "description": s.description,
                "confidence": float(s.confidence) if s.confidence else None,
                "evidence_text": s.evidence_text,
                "region_candidate_id": str(s.region_candidate_id)
                if s.region_candidate_id
                else None,
                "source_atlas": s.source_atlas,
                "granularity_level": s.granularity_level,
            }
            for s in steps
        ],
        "regions": [
            {
                "role": r.role,
                "sort_order": r.sort_order,
                "candidate_id": str(r.region_candidate_id)
                if r.region_candidate_id
                else None,
                "candidate": (
                    {
                        "id": str(cr.id),
                        "name": getattr(cr, "en_name", None)
                        or getattr(cr, "raw_name", str(cr.id)[:12]),
                        "granularity_level": getattr(cr, "granularity_level", None),
                        "source_atlas": getattr(cr, "source_atlas", None),
                    }
                    if (cr := candidate_map.get(str(r.region_candidate_id)))
                    else None
                ),
            }
            for r in regions
        ],
        "functions": [
            {
                "id": str(f.id),
                "function_term_en": f.function_term_en,
                "function_term_cn": f.function_term_cn,
                "function_domain": f.function_domain,
                "function_role": f.function_role,
                "effect_type": f.effect_type,
                "confidence_score": float(f.confidence_score)
                if f.confidence_score
                else None,
                "evidence_level": f.evidence_level,
                "description": f.description,
                "evidence_text": f.evidence_text,
            }
            for f in functions
        ],
        "evidence": [
            {
                "id": str(e.id),
                "evidence_type": getattr(e, "evidence_type", None),
                "evidence_text": getattr(e, "evidence_text", None),
                "source": getattr(e, "source_reference_text", None),
            }
            for e in evidence
        ],
        "validation": {
            "results": [
                {
                    "id": str(v.id),
                    "run_id": str(v.run_id),
                    "rule_overall_status": v.rule_overall_status,
                    "rule_blocked": v.rule_blocked,
                    "rule_validation_result_json": v.rule_validation_result_json,
                    "reviewer_a_decision": v.reviewer_a_decision,
                    "reviewer_a_confidence": v.reviewer_a_confidence,
                    "reviewer_b_decision": v.reviewer_b_decision,
                    "reviewer_b_confidence": v.reviewer_b_confidence,
                    "adjudication_status": v.adjudication_status,
                }
                for v in val_results
            ],
        },
        "extraction": {
            "resource_id": str(circuit.resource_id) if circuit.resource_id else None,
            "batch_id": str(circuit.batch_id) if circuit.batch_id else None,
            "llm_run_id": str(circuit.llm_run_id)
            if getattr(circuit, "llm_run_id", None)
            else None,
            "source_atlas": circuit.source_atlas,
            "confidence": float(circuit.confidence) if circuit.confidence else None,
        },
        "raw_fields": {
            "circuit": {
                k: str(v)
                for k, v in circuit.__dict__.items()
                if not k.startswith("_")
            },
        },
    }


# ---------------------------------------------------------------------------
# GET /api/validation/circuit/rules
# ---------------------------------------------------------------------------


@router.get("/rules")
async def get_rules():
    """Return the authoritative 12-rule registry."""
    rules = vc.get_rule_registry()
    return {"rules": rules, "enabled_rule_count": len(rules)}


# ---------------------------------------------------------------------------
# POST /api/validation/circuit/selection/dual-review
# ---------------------------------------------------------------------------


@router.post("/selection/dual-review")
async def selection_dual_review(body: dict, db: AsyncSession = Depends(get_db)):
    """Direct selection: send circuits to dual-review (skip rule validation)."""
    circuit_ids = body.get("circuit_ids", [])
    force = body.get("force_review", False)
    if not circuit_ids:
        raise HTTPException(status_code=400, detail="circuit_ids required")

    from app.models.mirror_kg import MirrorRegionCircuit

    valid = list((await db.execute(
        select(MirrorRegionCircuit).where(MirrorRegionCircuit.id.in_([uuid.UUID(c) for c in circuit_ids]))
    )).scalars().all())

    # Check reviewer configuration
    from app.services.llm_providers import get_llm_provider
    a_ok = True
    b_ok = True
    try:
        get_llm_provider("deepseek")
    except Exception:
        a_ok = False
    try:
        get_llm_provider("kimi")
    except Exception:
        b_ok = False

    skip_reasons = {}
    if not a_ok:
        skip_reasons["reviewer_a"] = "DeepSeek not configured"
    if not b_ok:
        skip_reasons["reviewer_b"] = "Kimi not configured"

    if not valid:
        return {
            "selected_count": len(circuit_ids),
            "eligible_count": 0,
            "skipped_count": len(circuit_ids),
            "skip_reasons": skip_reasons,
            "reviewer_a_configured": a_ok,
            "reviewer_b_configured": b_ok,
            "status": "no_eligible",
        }

    # Create internal run (dual-review only, no rule validation)
    req = CircuitValidationCreateRequest(
        granularity_level=valid[0].granularity_level if valid else "all",
        circuit_ids=[str(v.id) for v in valid],
        reviewer_a_provider="deepseek",
        reviewer_b_provider="kimi",
    )
    run, stats = await vc.create_validation_run(db, req)
    await db.commit()

    # Start async dual review in background
    import asyncio

    async def dual_only():
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as s:
            await vc.run_dual_review(s, run)

    asyncio.create_task(dual_only())

    return {
        "internal_run_id": str(run.id),
        "selected_count": len(circuit_ids),
        "eligible_count": len(valid),
        "skipped_count": len(circuit_ids) - len(valid),
        "skip_reasons": skip_reasons,
        "reviewer_a_configured": a_ok,
        "reviewer_b_configured": b_ok,
        "status": "queued",
    }


# ---------------------------------------------------------------------------
# POST /api/validation/circuit/selection/retry-reviewer-a
# ---------------------------------------------------------------------------


@router.post("/selection/retry-reviewer-a")
async def selection_retry_reviewer_a(body: dict, db: AsyncSession = Depends(get_db)):
    """Rerun Reviewer A (anatomical) for selected circuits."""
    circuit_ids = body.get("circuit_ids", [])
    if not circuit_ids:
        raise HTTPException(status_code=400, detail="circuit_ids required")

    from app.models.mirror_circuit_validation import MirrorCircuitValidationResult
    from app.models.mirror_kg import MirrorRegionCircuit
    from app.models.mirror_macro_clinical import MirrorCircuitStep

    uuids = [uuid.UUID(c) for c in circuit_ids]
    results = list((await db.execute(
        select(MirrorCircuitValidationResult).where(
            MirrorCircuitValidationResult.target_id.in_(uuids),
            MirrorCircuitValidationResult.target_type == "circuit",
        )
    )).scalars().all())

    if not results:
        raise HTTPException(status_code=404, detail="No validation results found for given circuits")

    rerun_count = 0
    for result in results:
        circuit = await db.get(MirrorRegionCircuit, result.target_id)
        if circuit is None:
            continue
        steps = list((await db.execute(
            select(MirrorCircuitStep).where(MirrorCircuitStep.circuit_id == result.target_id)
        )).scalars().all())
        a_result = await vc._call_reviewer_a(
            await db.get(MirrorCircuitValidationRun, result.run_id), circuit, steps  # type: ignore
        )
        result.reviewer_a_decision = a_result.get("decision")
        result.reviewer_a_confidence = a_result.get("confidence")
        result.reviewer_a_payload_json = a_result
        # Re-adjudicate
        adj = vc._adjudicate(
            a_result,
            {"decision": result.reviewer_b_decision or "uncertain",
             "confidence": result.reviewer_b_confidence or 0.0},
        )
        result.adjudication_status = adj["status"]
        result.adjudication_confidence_diff = adj["confidence_diff"]
        result.adjudication_summary = adj["summary"]
        result.recommended_review_priority = adj["priority"]
        rerun_count += 1

    await db.commit()
    return {"rerun_count": rerun_count, "reviewer": "a"}


# ---------------------------------------------------------------------------
# POST /api/validation/circuit/selection/retry-reviewer-b
# ---------------------------------------------------------------------------


@router.post("/selection/retry-reviewer-b")
async def selection_retry_reviewer_b(body: dict, db: AsyncSession = Depends(get_db)):
    """Rerun Reviewer B (functional) for selected circuits."""
    circuit_ids = body.get("circuit_ids", [])
    if not circuit_ids:
        raise HTTPException(status_code=400, detail="circuit_ids required")

    from app.models.mirror_circuit_validation import MirrorCircuitValidationResult
    from app.models.mirror_kg import MirrorRegionCircuit
    from app.models.mirror_macro_clinical import MirrorCircuitStep

    uuids = [uuid.UUID(c) for c in circuit_ids]
    results = list((await db.execute(
        select(MirrorCircuitValidationResult).where(
            MirrorCircuitValidationResult.target_id.in_(uuids),
            MirrorCircuitValidationResult.target_type == "circuit",
        )
    )).scalars().all())

    if not results:
        raise HTTPException(status_code=404, detail="No validation results found for given circuits")

    rerun_count = 0
    for result in results:
        circuit = await db.get(MirrorRegionCircuit, result.target_id)
        if circuit is None:
            continue
        steps = list((await db.execute(
            select(MirrorCircuitStep).where(MirrorCircuitStep.circuit_id == result.target_id)
        )).scalars().all())
        b_result = await vc._call_reviewer_b(
            await db.get(MirrorCircuitValidationRun, result.run_id), circuit, steps  # type: ignore
        )
        result.reviewer_b_decision = b_result.get("decision")
        result.reviewer_b_confidence = b_result.get("confidence")
        result.reviewer_b_payload_json = b_result
        # Re-adjudicate
        adj = vc._adjudicate(
            {"decision": result.reviewer_a_decision or "uncertain",
             "confidence": result.reviewer_a_confidence or 0.0},
            b_result,
        )
        result.adjudication_status = adj["status"]
        result.adjudication_confidence_diff = adj["confidence_diff"]
        result.adjudication_summary = adj["summary"]
        result.recommended_review_priority = adj["priority"]
        rerun_count += 1

    await db.commit()
    return {"rerun_count": rerun_count, "reviewer": "b"}


# ---------------------------------------------------------------------------
# GET /api/validation/circuit/review-queue
# ---------------------------------------------------------------------------


@router.get("/review-queue")
async def review_queue(
    limit: int = 25,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Return candidates whose dual-review is complete and need human review."""
    from app.models.mirror_circuit_validation import MirrorCircuitValidationResult

    q = select(MirrorCircuitValidationResult).where(
        MirrorCircuitValidationResult.adjudication_status.in_([
            "consensus_supported", "confidence_divergence", "model_conflict",
            "insufficient_information", "low_evidence",
        ]),
        MirrorCircuitValidationResult.adjudication_status.isnot(None),
    ).order_by(
        MirrorCircuitValidationResult.recommended_review_priority,
        MirrorCircuitValidationResult.created_at,
    ).offset(offset).limit(limit)

    count_q = select(func.count()).select_from(MirrorCircuitValidationResult).where(
        MirrorCircuitValidationResult.adjudication_status.in_([
            "consensus_supported", "confidence_divergence", "model_conflict",
            "insufficient_information", "low_evidence",
        ]),
        MirrorCircuitValidationResult.adjudication_status.isnot(None),
    )

    total = (await db.execute(count_q)).scalar_one()
    rows = list((await db.execute(q)).scalars().all())

    return {
        "items": [{
            "id": str(r.id),
            "circuit_id": str(r.target_id),
            "circuit_label": r.object_label,
            "adjudication_status": r.adjudication_status,
            "priority": r.recommended_review_priority,
            "reviewer_a_decision": r.reviewer_a_decision,
            "reviewer_b_decision": r.reviewer_b_decision,
            "reviewer_a_confidence": r.reviewer_a_confidence,
            "reviewer_b_confidence": r.reviewer_b_confidence,
        } for r in rows],
        "total": total,
    }


# ---------------------------------------------------------------------------
# POST /api/validation/circuit/human-review/approve
# ---------------------------------------------------------------------------


@router.post("/human-review/approve")
async def human_review_approve(body: dict, db: AsyncSession = Depends(get_db)):
    """Human reviewer approves a circuit (accepts LLM suggestion)."""
    circuit_id = body.get("circuit_id")
    note = body.get("note", "")
    if not circuit_id:
        raise HTTPException(status_code=400, detail="circuit_id required")

    from app.models.mirror_kg import MirrorRegionCircuit
    circuit = await db.get(MirrorRegionCircuit, uuid.UUID(circuit_id))
    if circuit is None:
        raise HTTPException(status_code=404, detail="Circuit not found")

    circuit.review_status = "approved"
    await db.commit()
    return {"status": "approved", "circuit_id": circuit_id, "note": note}


# ---------------------------------------------------------------------------
# POST /api/validation/circuit/human-review/reject
# ---------------------------------------------------------------------------


@router.post("/human-review/reject")
async def human_review_reject(body: dict, db: AsyncSession = Depends(get_db)):
    """Human reviewer rejects a circuit."""
    circuit_id = body.get("circuit_id")
    note = body.get("note", "")
    if not circuit_id:
        raise HTTPException(status_code=400, detail="circuit_id required")

    from app.models.mirror_kg import MirrorRegionCircuit
    circuit = await db.get(MirrorRegionCircuit, uuid.UUID(circuit_id))
    if circuit is None:
        raise HTTPException(status_code=404, detail="Circuit not found")

    circuit.review_status = "rejected"
    await db.commit()
    return {"status": "rejected", "circuit_id": circuit_id, "note": note}


# ---------------------------------------------------------------------------
# POST /api/validation/circuit/human-review/retain
# ---------------------------------------------------------------------------


@router.post("/human-review/retain")
async def human_review_retain(body: dict, db: AsyncSession = Depends(get_db)):
    """Human reviewer retains a circuit for further investigation."""
    circuit_id = body.get("circuit_id")
    note = body.get("note", "")
    if not circuit_id:
        raise HTTPException(status_code=400, detail="circuit_id required")

    from app.models.mirror_kg import MirrorRegionCircuit
    circuit = await db.get(MirrorRegionCircuit, uuid.UUID(circuit_id))
    if circuit is None:
        raise HTTPException(status_code=404, detail="Circuit not found")

    circuit.review_status = "manual_review_needed"
    await db.commit()
    return {"status": "retained", "circuit_id": circuit_id, "note": note}


# ---------------------------------------------------------------------------
# POST /api/validation/circuit/human-review/return-review
# ---------------------------------------------------------------------------


@router.post("/human-review/return-review")
async def human_review_return_review(body: dict, db: AsyncSession = Depends(get_db)):
    """Human reviewer returns a circuit to re-run dual review."""
    circuit_id = body.get("circuit_id")
    note = body.get("note", "")
    if not circuit_id:
        raise HTTPException(status_code=400, detail="circuit_id required")

    # Reset review status to trigger re-review
    from app.models.mirror_kg import MirrorRegionCircuit
    circuit = await db.get(MirrorRegionCircuit, uuid.UUID(circuit_id))
    if circuit is None:
        raise HTTPException(status_code=404, detail="Circuit not found")

    circuit.review_status = "pending"
    await db.commit()
    return {"status": "returned_for_review", "circuit_id": circuit_id, "note": note}


# ---------------------------------------------------------------------------
# POST /api/validation/circuit/human-review/topology-only
# ---------------------------------------------------------------------------


@router.post("/human-review/topology-only")
async def human_review_topology_only(body: dict, db: AsyncSession = Depends(get_db)):
    """Human reviewer approves circuit but only the topology, not the full content."""
    circuit_id = body.get("circuit_id")
    note = body.get("note", "")
    if not circuit_id:
        raise HTTPException(status_code=400, detail="circuit_id required")

    from app.models.mirror_kg import MirrorRegionCircuit
    circuit = await db.get(MirrorRegionCircuit, uuid.UUID(circuit_id))
    if circuit is None:
        raise HTTPException(status_code=404, detail="Circuit not found")

    circuit.review_status = "approved"
    await db.commit()
    return {"status": "approved_topology_only", "circuit_id": circuit_id, "note": note}


# ---------------------------------------------------------------------------
# POST /api/validation/circuit/human-review/merge-duplicate
# ---------------------------------------------------------------------------


@router.post("/human-review/merge-duplicate")
async def human_review_merge_duplicate(body: dict, db: AsyncSession = Depends(get_db)):
    """Human reviewer identifies a circuit as duplicate and merges it."""
    circuit_id = body.get("circuit_id")
    target_circuit_id = body.get("target_circuit_id")
    note = body.get("note", "")
    if not circuit_id or not target_circuit_id:
        raise HTTPException(status_code=400, detail="circuit_id and target_circuit_id required")

    from app.models.mirror_kg import MirrorRegionCircuit
    circuit = await db.get(MirrorRegionCircuit, uuid.UUID(circuit_id))
    target = await db.get(MirrorRegionCircuit, uuid.UUID(target_circuit_id))
    if circuit is None or target is None:
        raise HTTPException(status_code=404, detail="Circuit or target not found")

    circuit.review_status = "merged_into_other"
    # Optionally increase confidence of the target
    if target.confidence and circuit.confidence:
        target.confidence = max(target.confidence, circuit.confidence)
    await db.commit()
    return {
        "status": "merged",
        "circuit_id": circuit_id,
        "target_circuit_id": target_circuit_id,
        "note": note,
    }


# ---------------------------------------------------------------------------
# GET /api/validation/circuit/promotion/queue
# ---------------------------------------------------------------------------


@router.get("/promotion/queue")
async def promotion_queue(db: AsyncSession = Depends(get_db)):
    """Get human-approved candidates ready for promotion."""
    from app.models.mirror_kg import MirrorRegionCircuit

    q = select(MirrorRegionCircuit).where(
        MirrorRegionCircuit.review_status.in_(["approved", "manual_approved"]),
        MirrorRegionCircuit.promotion_status == "not_promoted",
    ).limit(50)
    rows = list((await db.execute(q)).scalars().all())
    return {
        "items": [{
            "id": str(r.id),
            "name": r.circuit_name,
            "type": r.circuit_type,
            "confidence": float(r.confidence) if r.confidence else 0,
        } for r in rows],
        "total": len(rows),
    }


# ---------------------------------------------------------------------------
# GET /api/validation/circuit/promotion/{circuit_id}/preview
# ---------------------------------------------------------------------------


@router.get("/promotion/{circuit_id}/preview")
async def promotion_preview(circuit_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Preview what would be promoted for a circuit."""
    from app.models.mirror_kg import MirrorRegionCircuit

    circuit = await db.get(MirrorRegionCircuit, circuit_id)
    if circuit is None:
        raise HTTPException(status_code=404, detail="Circuit not found")

    eligible = circuit.review_status in ("approved", "manual_approved") and circuit.promotion_status == "not_promoted"
    blockers = []
    if circuit.review_status not in ("approved", "manual_approved"):
        blockers.append("circuit not human-approved")
    if circuit.promotion_status != "not_promoted":
        blockers.append(f"promotion status is '{circuit.promotion_status}'")

    return {
        "circuit_id": str(circuit.id),
        "circuit_name": circuit.circuit_name,
        "review_status": circuit.review_status,
        "promotion_status": circuit.promotion_status,
        "eligible": eligible,
        "details": {
            "circuit_record": {
                "name": circuit.circuit_name,
                "type": circuit.circuit_type,
                "confidence": float(circuit.confidence) if circuit.confidence else 0,
            },
        },
        "blockers": blockers,
    }


# ---------------------------------------------------------------------------
# POST /api/validation/circuit/promotion/{circuit_id}/execute
# ---------------------------------------------------------------------------


@router.post("/promotion/{circuit_id}/execute")
async def promotion_execute(
    circuit_id: uuid.UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Execute promotion (dry-run by default)."""
    from app.models.mirror_kg import MirrorRegionCircuit

    dry_run = body.get("dry_run", True)
    idempotency_key = body.get("idempotency_key", str(uuid.uuid4()))

    circuit = await db.get(MirrorRegionCircuit, circuit_id)
    if circuit is None:
        raise HTTPException(status_code=404, detail="Circuit not found")
    if circuit.review_status not in ("approved", "manual_approved"):
        raise HTTPException(
            status_code=400,
            detail=f"Circuit not human-approved (status: {circuit.review_status})",
        )

    if dry_run:
        return {
            "dry_run": True,
            "circuit_id": str(circuit.id),
            "eligible": True,
            "target_records": {
                "circuit": {
                    "name": circuit.circuit_name,
                    "type": circuit.circuit_type,
                    "confidence": float(circuit.confidence) if circuit.confidence else 0,
                },
            },
            "idempotency_key": idempotency_key,
            "status": "dry_run_complete",
            "warnings": ["Dry run — no data written to formal library"],
        }

    # Real promotion (transactional)
    try:
        circuit.promotion_status = "promoted_to_final"
        await db.commit()
        return {
            "status": "promoted",
            "idempotency_key": idempotency_key,
            "circuit_id": str(circuit.id),
        }
    except Exception as e:
        await db.rollback()
        return {"status": "rollback", "error": str(e)}


# ---------------------------------------------------------------------------
# GET /api/validation/circuit/promotion/{circuit_id}/history
# ---------------------------------------------------------------------------


@router.get("/promotion/{circuit_id}/history")
async def promotion_history(circuit_id: uuid.UUID):
    """Return promotion history for a circuit (stub — returns empty array)."""
    return {"items": [], "total": 0}


# ---------------------------------------------------------------------------
# POST /api/validation/circuit/selection/promote
# ---------------------------------------------------------------------------


@router.post("/selection/promote")
async def selection_promote(body: dict, db: AsyncSession = Depends(get_db)):
    """Batch promote selected circuits to Final KG."""
    from app.models.mirror_kg import MirrorRegionCircuit

    circuit_ids = body.get("circuit_ids", [])
    if not circuit_ids:
        raise HTTPException(status_code=400, detail="circuit_ids required")

    uuids = [uuid.UUID(c) for c in circuit_ids]
    circuits = list((await db.execute(
        select(MirrorRegionCircuit).where(MirrorRegionCircuit.id.in_(uuids))
    )).scalars().all())

    eligible = [c for c in circuits if c.review_status in ("approved", "manual_approved") and c.promotion_status == "not_promoted"]
    promoted_count = 0
    for c in eligible:
        c.promotion_status = "promoted_to_final"
        promoted_count += 1

    await db.commit()
    return {
        "selected_count": len(circuit_ids),
        "eligible_count": len(eligible),
        "promoted_count": promoted_count,
        "status": "completed",
    }


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------


def _run_to_read(run: MirrorCircuitValidationRun) -> CircuitValidationRunRead:
    return CircuitValidationRunRead(
        id=str(run.id),
        granularity_level=run.granularity_level,
        status=run.status,
        rule_validation_status=run.rule_validation_status,
        dual_review_status=run.dual_review_status,
        adjudication_status=run.adjudication_status,
        rule_total_count=run.rule_total_count or 0,
        rule_passed_count=run.rule_passed_count or 0,
        rule_failed_count=run.rule_failed_count or 0,
        rule_blocked_count=run.rule_blocked_count or 0,
        dual_review_agreement_count=run.dual_review_agreement_count or 0,
        dual_review_conflict_count=run.dual_review_conflict_count or 0,
        dual_review_rejection_count=run.dual_review_rejection_count or 0,
        reviewer_a_provider=run.reviewer_a_provider,
        reviewer_b_provider=run.reviewer_b_provider,
        dry_run=run.dry_run or False,
        error_message=run.error_message,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
    )


def _result_to_read(res: MirrorCircuitValidationResult) -> CircuitValidationResultRead:
    return CircuitValidationResultRead(
        id=str(res.id),
        run_id=str(res.run_id),
        target_type=res.target_type,
        target_id=str(res.target_id),
        object_label=res.object_label,
        rule_overall_status=res.rule_overall_status,
        rule_blocked=res.rule_blocked or False,
        rule_validation_result_json=res.rule_validation_result_json or [],
        reviewer_a_decision=res.reviewer_a_decision,
        reviewer_a_confidence=res.reviewer_a_confidence,
        reviewer_a_payload_json=res.reviewer_a_payload_json,
        reviewer_b_decision=res.reviewer_b_decision,
        reviewer_b_confidence=res.reviewer_b_confidence,
        reviewer_b_payload_json=res.reviewer_b_payload_json,
        adjudication_status=res.adjudication_status,
        adjudication_confidence_diff=res.adjudication_confidence_diff,
        adjudication_summary=res.adjudication_summary,
        recommended_review_priority=res.recommended_review_priority,
        created_at=res.created_at,
    )
