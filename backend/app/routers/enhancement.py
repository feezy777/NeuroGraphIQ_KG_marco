"""API router for data enhancement operations."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.mirror_enhancement_suggestion import MirrorEnhancementSuggestion
from app.schemas.enhancement import (
    EnhancementRequest, EnhancementResponse, EnhancementSuggestionRead,
)
from app.services import enhancement_service

router = APIRouter(tags=["Enhancement"])


@router.post("/selection/enhance")
async def trigger_enhancement(
    body: EnhancementRequest,
    db: AsyncSession = Depends(get_db),
) -> EnhancementResponse:
    """Trigger data enhancement for circuits from a validation run."""
    run_id = uuid.UUID(body.run_id)
    circuit_ids = [
        uuid.UUID(c) for c in body.circuit_ids
    ] if body.circuit_ids else []

    if not circuit_ids:
        # Get all circuits from the run
        from app.models.mirror_circuit_validation import MirrorCircuitValidationResult
        results = list((await db.execute(
            select(MirrorCircuitValidationResult).where(
                MirrorCircuitValidationResult.run_id == run_id,
            )
        )).scalars().all())
        circuit_ids = [r.target_id for r in results]

    if not circuit_ids:
        raise HTTPException(status_code=400, detail="No circuits found for this run")

    return await enhancement_service.run_enhancement(
        db, run_id, circuit_ids,
        tier2_enabled=body.tier2_enabled,
        dry_run=body.dry_run,
    )


@router.get("/candidates/{circuit_id}/enhancements")
async def list_enhancements(
    circuit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """List enhancement suggestions for a circuit."""
    rows = list((await db.execute(
        select(MirrorEnhancementSuggestion)
        .where(MirrorEnhancementSuggestion.circuit_id == circuit_id)
        .order_by(MirrorEnhancementSuggestion.created_at)
    )).scalars().all())
    return {
        "items": [EnhancementSuggestionRead.model_validate(r) for r in rows],
        "total": len(rows),
    }


@router.post("/enhancements/{suggestion_id}/approve")
async def approve_enhancement(
    suggestion_id: uuid.UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Approve an enhancement suggestion and apply to source."""
    sugg = await db.get(MirrorEnhancementSuggestion, suggestion_id)
    if sugg is None:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    sugg.approval_status = "approved"
    sugg.approved_by = body.get("reviewer", "admin")
    sugg.approved_at = datetime.now(timezone.utc)

    # Apply to source table using existing correction-apply function
    from app.routers.validation_circuit import _apply_correction_to_source
    # Build a minimal object for _apply_correction_to_source
    class _SuggCompat:
        def __init__(self, s):
            self.circuit_id = s.circuit_id
            self.field_path = s.field_path
            self.approved_value = s.suggested_value
            self.suggested_value = s.suggested_value
    compat = _SuggCompat(sugg)
    applied, msg = await _apply_correction_to_source(db, compat)
    await db.commit()
    return {
        "status": "approved",
        "suggestion_id": str(suggestion_id),
        "applied_to_source": applied,
        "apply_message": msg,
    }


@router.post("/enhancements/{suggestion_id}/reject")
async def reject_enhancement(
    suggestion_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Reject an enhancement suggestion."""
    sugg = await db.get(MirrorEnhancementSuggestion, suggestion_id)
    if sugg is None:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    sugg.approval_status = "rejected"
    await db.commit()
    return {"status": "rejected", "suggestion_id": str(suggestion_id)}
