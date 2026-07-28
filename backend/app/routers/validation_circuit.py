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
    response_model=CircuitValidationRunRead,
    status_code=201,
)
async def create_run(
    req: CircuitValidationCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new circuit validation run. Returns run + scan stats."""
    run, stats = await vc.create_validation_run(db, req)
    await db.commit()
    return {**_run_to_read(run).model_dump(), "scan_stats": stats}


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

    return {
        "total_runs": total_runs,
        "completed_runs": completed_runs,
        "pending_review": approved_count or 0,
        "rule_passed": 0,
        "dual_agreement": 0,
        "promoted": 0,
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
