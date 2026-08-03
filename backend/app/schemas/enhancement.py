"""Enhancement request/response schemas."""
from __future__ import annotations
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


class EnhancementRequest(BaseModel):
    run_id: str
    circuit_ids: list[str] = Field(default_factory=list)
    tier2_enabled: bool = True
    dry_run: bool = False


class Tier1Stats(BaseModel):
    source_atlas_backfill: int = 0
    provenance_backfill: int = 0
    enum_normalization: int = 0
    topology_fix: int = 0
    region_creation: int = 0
    total: int = 0


class Tier2Stats(BaseModel):
    evidence_text: int = 0
    description: int = 0
    function_crosscheck: int = 0
    topology_flags: int = 0
    total: int = 0


class QualityScoreChange(BaseModel):
    before_avg: float = 0.0
    after_avg: float = 0.0


class EnhancementResponse(BaseModel):
    run_id: str
    tier1_fixes: Tier1Stats = Field(default_factory=Tier1Stats)
    tier2_suggestions: Tier2Stats = Field(default_factory=Tier2Stats)
    quality_score_change: QualityScoreChange = Field(default_factory=QualityScoreChange)
    circuit_scores: list[dict] = Field(default_factory=list)


class EnhancementSuggestionRead(BaseModel):
    id: str
    circuit_id: str
    field_path: str
    suggested_value: Optional[Any] = None
    original_value: Optional[Any] = None
    suggestion_type: str
    suggestion_source: str = "deepseek"
    confidence: Optional[float] = None
    approval_status: str = "proposed"
    created_at: Optional[datetime] = None
    model_config = {"from_attributes": True}
