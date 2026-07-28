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

    # Enrich with step counts
    items = []
    for r in rows:
        step_count = (await db.execute(
            select(func.count()).select_from(MirrorCircuitStep).where(MirrorCircuitStep.circuit_id == r.id)
        )).scalar_one()

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
