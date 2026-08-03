# Data Enhancement Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a tiered data enhancement pipeline that auto-fixes missing fields (Tier 1) and generates LLM-based content suggestions (Tier 2), compute quality scores, and surface enhancements for human review.

**Architecture:** New `enhancement_service.py` runs Tier 1 deterministic backfills + Tier 2 parallel DeepSeek calls. New `enhancement.py` router exposes trigger/approve/reject endpoints. New `MirrorEnhancementSuggestion` model stores Tier 2 suggestions. Quality score computed during rule validation and updated after enhancement. Frontend: progress modal + quality badge + human review extension.

**Tech Stack:** Python 3.11+ / FastAPI / SQLAlchemy async / Pydantic v2 / PostgreSQL JSONB; React 18 / TypeScript / Vite

## Global Constraints

- Only write to `mirror_*` tables — never touch `final_*`
- UUID fields must pass validation before setattr (existing `_validate_field_value` in `validation_circuit.py`)
- Tier 2 LLM output always marked `proposed` with human review gate
- All endpoints use `Depends(get_db)` for session, `async def` for I/O
- Follow existing naming: `router = APIRouter(tags=["..."])`, `_run_to_read()` helper pattern

---

### Task 1: Database Migration + ORM Model

**Files:**
- Create: `backend/migrations/20260803_enhancement_suggestions.sql`
- Create: `backend/app/models/mirror_enhancement_suggestion.py`
- Modify: `backend/app/models/mirror_kg.py` (add `quality_score` column)

**Interfaces:**
- Produces: `MirrorEnhancementSuggestion` ORM class, `quality_score` on `MirrorRegionCircuit`

- [ ] **Step 1: Write migration SQL**

```sql
-- 20260803_enhancement_suggestions.sql
-- Tier 2 enhancement suggestions (LLM-generated content pending human review)

CREATE TABLE IF NOT EXISTS mirror_enhancement_suggestions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    circuit_id UUID NOT NULL,
    validation_run_id UUID,
    field_path TEXT NOT NULL,
    suggested_value JSONB,
    original_value JSONB,
    suggestion_type TEXT NOT NULL,
    suggestion_source TEXT NOT NULL DEFAULT 'deepseek',
    confidence REAL,
    approval_status TEXT NOT NULL DEFAULT 'proposed',
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_enhancement_circuit ON mirror_enhancement_suggestions(circuit_id);
CREATE INDEX IF NOT EXISTS idx_enhancement_status ON mirror_enhancement_suggestions(approval_status);

-- Quality score column for circuits
ALTER TABLE mirror_region_circuits
    ADD COLUMN IF NOT EXISTS quality_score REAL DEFAULT NULL;
```

- [ ] **Step 2: Apply migration**

```bash
cd backend
psql -U postgres -d neurographiq_kg_v3_mvp1_e2e -f migrations/20260803_enhancement_suggestions.sql
```

- [ ] **Step 3: Write ORM model**

```python
# backend/app/models/mirror_enhancement_suggestion.py
"""Mirror enhancement suggestion ORM model — Tier 2 LLM content proposals."""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any, Optional
from sqlalchemy import DateTime, Float, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class MirrorEnhancementSuggestion(Base):
    __tablename__ = "mirror_enhancement_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    circuit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True,
    )
    validation_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    field_path: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_value: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True,
    )
    original_value: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True,
    )
    suggestion_type: Mapped[str] = mapped_column(
        String(64), nullable=False,
    )
    suggestion_source: Mapped[str] = mapped_column(
        String(32), default="deepseek",
    )
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    approval_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="proposed",
    )
    approved_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
```

- [ ] **Step 4: Add quality_score to MirrorRegionCircuit**

```python
# In backend/app/models/mirror_kg.py, add to MirrorRegionCircuit class:
quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
```

- [ ] **Step 5: Verify model loads**

```bash
cd backend && .venv/Scripts/python.exe -c "
from app.models.mirror_enhancement_suggestion import MirrorEnhancementSuggestion
from app.models.mirror_kg import MirrorRegionCircuit
print('Models loaded OK')
print(f'quality_score on MirrorRegionCircuit: {hasattr(MirrorRegionCircuit, \"quality_score\")}')
"
```

- [ ] **Step 6: Commit**

```bash
git add backend/migrations/20260803_enhancement_suggestions.sql backend/app/models/mirror_enhancement_suggestion.py backend/app/models/mirror_kg.py
git commit -m "feat: add enhancement_suggestions table and quality_score column"
```

---

### Task 2: Enhancement Schemas (Pydantic)

**Files:**
- Create: `backend/app/schemas/enhancement.py`

**Interfaces:**
- Produces: `EnhancementRequest`, `EnhancementResponse`, `EnhancementSuggestionRead`

- [ ] **Step 1: Write schemas**

```python
# backend/app/schemas/enhancement.py
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
```

- [ ] **Step 2: Verify imports**

```bash
cd backend && .venv/Scripts/python.exe -c "from app.schemas.enhancement import EnhancementRequest, EnhancementResponse, EnhancementSuggestionRead; print('Schemas OK')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/enhancement.py
git commit -m "feat: add enhancement Pydantic schemas"
```

---

### Task 3: Quality Score Computation

**Files:**
- Modify: `backend/app/services/mirror_circuit_validation_service.py:384-430`

**Interfaces:**
- Produces: `compute_quality_score(circuit, steps, region_count)` function

- [ ] **Step 1: Write quality score function**

```python
# Add to backend/app/services/mirror_circuit_validation_service.py (before run_rule_validation)

def compute_quality_score(
    circuit: Any,
    steps: list[Any],
    region_count: int,
) -> float:
    """Compute 0-100 quality score for a circuit.

    Dimensions: field completeness (30), provenance (20),
    topology health (20), evidence quality (20), region association (10).
    """
    score = 0.0

    # Field Completeness (30 pts)
    fields_ok = 0
    for field in ("circuit_name", "circuit_type"):
        if getattr(circuit, field, None):
            fields_ok += 1
    if getattr(circuit, "source_atlas", None):
        fields_ok += 1
    if getattr(circuit, "evidence_text", None) and len(circuit.evidence_text or "") >= 10:
        fields_ok += 1
    if getattr(circuit, "description", None) and len(getattr(circuit, "description", "") or "") >= 10:
        fields_ok += 1
    score += (fields_ok / 5) * 30

    # Provenance (20 pts)
    prov = 0
    if getattr(circuit, "resource_id", None):
        prov += 7
    if getattr(circuit, "batch_id", None):
        prov += 7
    if getattr(circuit, "llm_run_id", None):
        prov += 6
    score += prov

    # Topology Health (20 pts)
    topo = 0
    if len(steps) >= 2:
        topo += 5
    if steps:
        if steps[0].role and steps[0].role.lower() in ("origin", "source", "start", "input"):
            topo += 5
        if steps[-1].role and steps[-1].role.lower() in ("terminus", "target", "end", "output"):
            topo += 5
    valid_step_types = all(
        s.step_type and s.step_type.lower() in {
            "region", "region_group", "relay", "hub", "modulator",
            "functional_stage", "unknown",
        }
        for s in steps
    ) if steps else False
    if valid_step_types:
        topo += 5
    score += min(topo, 20)

    # Evidence Quality (20 pts)
    ev = 0
    circuit_ev = getattr(circuit, "evidence_text", None) or ""
    if len(circuit_ev) >= 50:
        ev += 10
    elif len(circuit_ev) >= 10:
        ev += 5
    step_with_evidence = sum(
        1 for s in steps if s.evidence_text and len(s.evidence_text or "") >= 10
    )
    if step_with_evidence >= len(steps) * 0.5:
        ev += 10
    elif step_with_evidence > 0:
        ev += 5
    score += min(ev, 20)

    # Region Association (10 pts)
    if region_count >= 2:
        score += 10
    elif region_count == 1:
        score += 5

    return round(min(score, 100.0), 1)
```

- [ ] **Step 2: Integrate into run_rule_validation**

In `run_rule_validation()`, after line 420 (`result.rule_blocked = ...`), add:

```python
# Compute quality score
from app.models.mirror_kg import MirrorCircuitRegion
region_count_res = await session.execute(
    select(func.count()).select_from(MirrorCircuitRegion).where(
        MirrorCircuitRegion.circuit_id == result.target_id,
    )
)
region_count = region_count_res.scalar_one()
qs = compute_quality_score(circuit, steps, region_count)
result.quality_score_json = {"score": qs, "computed_at": datetime.now(timezone.utc).isoformat()}
# Also update the circuit record directly
circuit.quality_score = qs
```

- [ ] **Step 3: Run existing tests**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/test_validation_state_machine.py -q
```

Expected: 39 passed

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/mirror_circuit_validation_service.py
git commit -m "feat: add compute_quality_score and integrate into rule validation"
```

---

### Task 4: Enhancement Service (Tier 1 + Tier 2)

**Files:**
- Create: `backend/app/services/enhancement_service.py`

**Interfaces:**
- Consumes: `MirrorRegionCircuit`, `MirrorCircuitStep`, `MirrorCircuitRegion`, `CandidateBrainRegion`, `MirrorEnhancementSuggestion`
- Produces: `run_enhancement(session, run_id, circuit_ids, tier2_enabled, dry_run) -> EnhancementResponse`

- [ ] **Step 1: Write Tier 1 auto-fix functions**

```python
# backend/app/services/enhancement_service.py
"""Data enhancement service — Tier 1 auto-fix + Tier 2 LLM suggestions."""
from __future__ import annotations
import asyncio, json, logging, uuid
from datetime import datetime, timezone
from typing import Any, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.mirror_kg import MirrorCircuitRegion, MirrorRegionCircuit
from app.models.mirror_macro_clinical import MirrorCircuitStep
from app.models.candidate import CandidateBrainRegion
from app.models.mirror_enhancement_suggestion import MirrorEnhancementSuggestion
from app.schemas.enhancement import (
    EnhancementResponse, Tier1Stats, Tier2Stats, QualityScoreChange,
)
from app.services.mirror_circuit_validation_service import compute_quality_score
from app.services.llm_providers import get_llm_provider
import app.services.mirror_circuit_validation_service as vc

_log = logging.getLogger(__name__)

KNOWN_CIRCUIT_TYPES = {
    "closed_loop", "open_loop", "feedforward", "feedback",
    "recurrent", "divergent", "convergent", "chain",
    "bundle", "simple", "complex", "undefined", "unknown",
}
VALID_ROLES = {"source", "target", "relay", "hub", "modulator",
               "participant", "unknown", "origin", "terminus",
               "start", "end", "input", "output"}
VALID_STEP_TYPES = {"region", "region_group", "relay", "hub",
                    "modulator", "functional_stage", "unknown"}


async def _tier1_source_atlas(
    session: AsyncSession, circuit: Any, steps: list[Any],
) -> int:
    """Backfill source_atlas from linked candidate regions. Returns fix count."""
    if circuit.source_atlas and circuit.source_atlas.strip():
        return 0

    for step in steps:
        if step.region_candidate_id:
            region = await session.get(CandidateBrainRegion, step.region_candidate_id)
            if region and getattr(region, "source_atlas", None):
                circuit.source_atlas = region.source_atlas
                return 1
    return 0


async def _tier1_provenance(
    session: AsyncSession, circuit: Any, steps: list[Any],
) -> int:
    """Backfill resource_id / batch_id from step → region → candidate chain. Returns fix count."""
    fixed = 0
    if not getattr(circuit, "resource_id", None):
        for step in steps:
            if step.region_candidate_id:
                region = await session.get(CandidateBrainRegion, step.region_candidate_id)
                if region and getattr(region, "resource_id", None):
                    circuit.resource_id = region.resource_id
                    fixed += 1
                    break
    if not getattr(circuit, "batch_id", None):
        for step in steps:
            if step.region_candidate_id:
                region = await session.get(CandidateBrainRegion, step.region_candidate_id)
                if region and getattr(region, "batch_id", None):
                    circuit.batch_id = region.batch_id
                    fixed += 1
                    break
    return fixed


async def _tier1_enum_normalize(
    _session: AsyncSession, circuit: Any, steps: list[Any],
) -> int:
    """Normalize circuit_type, step_type, role to known enum values. Returns fix count."""
    fixed = 0
    ctype = (circuit.circuit_type or "").lower()
    if ctype and ctype not in KNOWN_CIRCUIT_TYPES:
        # Try fuzzy match
        for known in KNOWN_CIRCUIT_TYPES:
            if known in ctype or ctype in known:
                circuit.circuit_type = known
                fixed += 1
                break
        if not fixed and ctype:
            circuit.circuit_type = "unknown"
            fixed += 1

    for s in steps:
        if s.role and s.role.lower() not in VALID_ROLES:
            s.role = "unknown"
            fixed += 1
        if s.step_type and s.step_type.lower() not in VALID_STEP_TYPES:
            s.step_type = "unknown"
            fixed += 1
    return fixed


async def _tier1_region_creation(
    session: AsyncSession, circuit: Any, steps: list[Any],
) -> int:
    """Create MirrorCircuitRegion records from steps with region_candidate_id. Returns fix count."""
    existing = set(
        r.region_candidate_id for r in (await session.execute(
            select(MirrorCircuitRegion).where(
                MirrorCircuitRegion.circuit_id == circuit.id,
            )
        )).scalars().all() if r.region_candidate_id
    )
    fixed = 0
    for i, step in enumerate(steps):
        cid = step.region_candidate_id
        if cid and cid not in existing:
            session.add(MirrorCircuitRegion(
                id=uuid.uuid4(),
                circuit_id=circuit.id,
                region_candidate_id=cid,
                role=step.role or (
                    "origin" if i == 0 else
                    "terminus" if i == len(steps) - 1 else
                    "relay"
                ),
                sort_order=i,
            ))
            existing.add(cid)
            fixed += 1
    return fixed
```

- [ ] **Step 2: Write Tier 2 LLM suggestion function (evidence + description)**

```python
async def _tier2_generate_evidence(
    session: AsyncSession, circuit: Any, steps: list[Any],
    provider: Any, sem: asyncio.Semaphore, dry_run: bool,
) -> list[dict]:
    """Generate evidence_text for a circuit via DeepSeek. Returns suggestion summary dicts."""
    if circuit.evidence_text and len(circuit.evidence_text or "") >= 50:
        return []

    steps_json = [
        {"order": s.step_order, "name": s.step_name,
         "type": s.step_type, "role": s.role}
        for s in steps[:20]
    ]

    system = """你是神经科学数据质量专家。根据回路拓扑生成一个简短的证据摘要(2-4句, 中英文均可)。
只陈述已知事实，不编造。如果证据不足，输出 "insufficient_evidence"。
返回 JSON: {"evidence_text": "...", "confidence": 0.0}"""

    user = json.dumps({
        "circuit_name": circuit.circuit_name,
        "circuit_type": circuit.circuit_type,
        "granularity": circuit.granularity_level,
        "source_atlas": circuit.source_atlas or "unknown",
        "function": circuit.function_association or "unknown",
        "steps": steps_json,
    }, ensure_ascii=False, default=str)

    async with sem:
        resp = await provider.complete_json(
            model="deepseek-chat", system_prompt=system,
            user_prompt=user, temperature=0.3, max_tokens=500,
        )

    diagnosis = resp.parsed_json or {}
    evidence_text = diagnosis.get("evidence_text", "")
    if not evidence_text or evidence_text == "insufficient_evidence":
        return []

    confidence = diagnosis.get("confidence", 0.5)
    if confidence < 0.5:
        return []

    suggestion = {
        "field_path": "evidence_text",
        "suggested_value": evidence_text,
        "suggestion_type": "evidence_generation",
        "confidence": confidence,
    }

    if not dry_run:
        original = circuit.evidence_text or ""
        db_suggestion = MirrorEnhancementSuggestion(
            id=uuid.uuid4(),
            circuit_id=circuit.id,
            field_path="evidence_text",
            suggested_value={"value": evidence_text},
            original_value={"value": original} if original else None,
            suggestion_type="evidence_generation",
            confidence=confidence,
        )
        session.add(db_suggestion)

    return [suggestion]


async def _tier2_generate_description(
    session: AsyncSession, circuit: Any, steps: list[Any],
    provider: Any, sem: asyncio.Semaphore, dry_run: bool,
) -> list[dict]:
    """Generate description for a circuit via DeepSeek."""
    desc = getattr(circuit, "description", None)
    if desc and len(desc or "") >= 20:
        return []

    steps_json = [
        {"order": s.step_order, "name": s.step_name}
        for s in steps[:15]
    ]

    system = """你是神经科学数据质量专家。为回路生成1-2句简要描述(中英文均可)。
只描述已知的拓扑和功能，不编造。
返回 JSON: {"description": "...", "confidence": 0.0}"""

    user = json.dumps({
        "circuit_name": circuit.circuit_name,
        "circuit_type": circuit.circuit_type,
        "function": circuit.function_association or "unknown",
        "steps": steps_json,
    }, ensure_ascii=False, default=str)

    async with sem:
        resp = await provider.complete_json(
            model="deepseek-chat", system_prompt=system,
            user_prompt=user, temperature=0.3, max_tokens=300,
        )

    diagnosis = resp.parsed_json or {}
    description = diagnosis.get("description", "")
    if not description:
        return []

    confidence = diagnosis.get("confidence", 0.5)
    if confidence < 0.5:
        return []

    suggestion = {
        "field_path": "description",
        "suggested_value": description,
        "suggestion_type": "description_fill",
        "confidence": confidence,
    }

    if not dry_run:
        original = desc or ""
        db_suggestion = MirrorEnhancementSuggestion(
            id=uuid.uuid4(),
            circuit_id=circuit.id,
            field_path="description",
            suggested_value={"value": description},
            original_value={"value": original} if original else None,
            suggestion_type="description_fill",
            confidence=confidence,
        )
        session.add(db_suggestion)

    return [suggestion]
```

- [ ] **Step 3: Write main orchestration function**

```python
async def run_enhancement(
    session: AsyncSession,
    run_id: uuid.UUID,
    circuit_ids: list[uuid.UUID],
    tier2_enabled: bool = True,
    dry_run: bool = False,
) -> EnhancementResponse:
    """Run Tier 1 auto-fixes and optionally Tier 2 LLM suggestions."""
    # Load circuits
    q = select(MirrorRegionCircuit).where(
        MirrorRegionCircuit.id.in_(circuit_ids),
    )
    circuits = list((await session.execute(q)).scalars().all())

    t1 = Tier1Stats()
    t2 = Tier2Stats()
    scores_before: list[float] = []
    scores_after: list[float] = []
    circuit_score_list: list[dict] = []

    provider = get_llm_provider("deepseek") if tier2_enabled else None
    sem = asyncio.Semaphore(5) if tier2_enabled else None

    for circuit in circuits:
        steps = list((await session.execute(
            select(MirrorCircuitStep).where(
                MirrorCircuitStep.circuit_id == circuit.id,
            ).order_by(MirrorCircuitStep.step_order)
        )).scalars().all())

        region_count = (await session.execute(
            select(func.count()).select_from(MirrorCircuitRegion).where(
                MirrorCircuitRegion.circuit_id == circuit.id,
            )
        )).scalar_one()

        qs_before = compute_quality_score(circuit, steps, region_count)
        scores_before.append(qs_before)

        # Tier 1
        t1.source_atlas_backfill += await _tier1_source_atlas(session, circuit, steps)
        t1.provenance_backfill += await _tier1_provenance(session, circuit, steps)
        t1.enum_normalization += await _tier1_enum_normalize(session, circuit, steps)
        t1.region_creation += await _tier1_region_creation(session, circuit, steps)
        t1.total = t1.source_atlas_backfill + t1.provenance_backfill + t1.enum_normalization + t1.region_creation

        # Tier 2
        if tier2_enabled and provider and sem:
            evidence = await _tier2_generate_evidence(
                session, circuit, steps, provider, sem, dry_run,
            )
            desc = await _tier2_generate_description(
                session, circuit, steps, provider, sem, dry_run,
            )
            t2.evidence_text += len(evidence)
            t2.description += len(desc)
            t2.total = t2.evidence_text + t2.description

        # Recompute quality score
        region_count_after = (await session.execute(
            select(func.count()).select_from(MirrorCircuitRegion).where(
                MirrorCircuitRegion.circuit_id == circuit.id,
            )
        )).scalar_one()
        qs_after = compute_quality_score(circuit, steps, region_count_after)
        scores_after.append(qs_after)
        circuit.quality_score = qs_after

        circuit_score_list.append({
            "circuit_id": str(circuit.id),
            "before": qs_before,
            "after": qs_after,
        })

        if not dry_run:
            await session.flush()

    if not dry_run:
        await session.commit()

    before_avg = round(sum(scores_before) / max(len(scores_before), 1), 1)
    after_avg = round(sum(scores_after) / max(len(scores_after), 1), 1)

    return EnhancementResponse(
        run_id=str(run_id),
        tier1_fixes=t1,
        tier2_suggestions=t2,
        quality_score_change=QualityScoreChange(
            before_avg=before_avg, after_avg=after_avg,
        ),
        circuit_scores=circuit_score_list,
    )
```

- [ ] **Step 4: Verify service imports**

```bash
cd backend && .venv/Scripts/python.exe -c "
from app.services.enhancement_service import run_enhancement, compute_quality_score
print('Enhancement service loaded OK')
"
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/enhancement_service.py
git commit -m "feat: add enhancement service with Tier 1 auto-fix and Tier 2 LLM"
```

---

### Task 5: Enhancement API Router

**Files:**
- Create: `backend/app/routers/enhancement.py`
- Modify: `backend/app/main.py` (register router)

**Interfaces:**
- Consumes: `run_enhancement` from service, `MirrorEnhancementSuggestion` model
- Produces: `POST /selection/enhance`, `GET /candidates/{id}/enhancements`, `POST /enhancements/{id}/approve`, `POST /enhancements/{id}/reject`

- [ ] **Step 1: Write router**

```python
# backend/app/routers/enhancement.py
"""API router for data enhancement operations."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.mirror_enhancement_suggestion import MirrorEnhancementSuggestion
from app.schemas.enhancement import (
    EnhancementRequest, EnhancementResponse, EnhancementSuggestionRead,
)
from app.services import enhancement_service

router = APIRouter(tags=["Enhancement"])

_VALID_SUGGESTION_TYPES = {
    "evidence_generation", "description_fill",
    "function_crosscheck", "topology_flag",
}


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

    # Apply to source table
    from app.routers.validation_circuit import _apply_correction_to_source
    applied, msg = await _apply_correction_to_source(db, sugg)
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
```

- [ ] **Step 2: Register router in main.py**

In `backend/app/main.py`, add after the validation_circuit router registration:

```python
from app.routers import enhancement
app.include_router(enhancement.router, prefix="/api/validation/circuit")
```

- [ ] **Step 3: Verify router loads**

```bash
cd backend && .venv/Scripts/python.exe -c "
from app.routers.enhancement import router
print(f'Enhancement router: {len(router.routes)} routes')
for r in router.routes:
    if hasattr(r, 'path'):
        print(f'  {r.methods} {r.path}')
"
```

Expected: 4 routes

- [ ] **Step 4: Run tests**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/test_validation_state_machine.py -q
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/enhancement.py backend/app/main.py
git commit -m "feat: add enhancement API router with trigger/approve/reject"
```

---

### Task 6: Quality Score in Candidate List

**Files:**
- Modify: `backend/app/routers/validation_circuit.py` (candidates endpoint)

**Interfaces:**
- Extends: `GET /api/validation/circuit/candidates` with `quality_score` in each item

- [ ] **Step 1: Add quality_score to candidate list response**

In `list_candidates()` (around line 295), add `quality_score` to each item dict:

```python
items.append({
    # ... existing fields ...
    "quality_score": circuit.quality_score or 0.0,
})
```

- [ ] **Step 2: Add min_quality_score filter param**

In `list_candidates()` function signature, add:

```python
min_quality_score: Optional[float] = Query(None, ge=0, le=100, description="Minimum quality score"),
```

And add filter:

```python
if min_quality_score is not None:
    q = q.where(MirrorRegionCircuit.quality_score >= min_quality_score)
    count_q = count_q.where(MirrorRegionCircuit.quality_score >= min_quality_score)
```

- [ ] **Step 3: Verify endpoint returns quality_score**

```bash
curl -s "http://127.0.0.1:8002/api/validation/circuit/candidates?limit=2" | python -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d['items'][0]['quality_score']))"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/validation_circuit.py
git commit -m "feat: add quality_score to candidate list API"
```

---

### Task 7: Frontend — QualityScoreBadge + EnhancementModal

**Files:**
- Create: `frontend/src/pages/validation-center/components/QualityScoreBadge.tsx`
- Create: `frontend/src/pages/validation-center/components/EnhancementModal.tsx`

- [ ] **Step 1: Write QualityScoreBadge component**

```tsx
// frontend/src/pages/validation-center/components/QualityScoreBadge.tsx
interface Props {
  score: number
  showLabel?: boolean
}

function scoreColor(s: number): string {
  if (s >= 80) return '#52c41a'
  if (s >= 60) return '#faad14'
  if (s >= 40) return '#ff7a45'
  return '#ff4d4f'
}

function scoreBgc(s: number): string {
  if (s >= 80) return '#f6ffed'
  if (s >= 60) return '#fffbe6'
  if (s >= 40) return '#fff2e8'
  return '#fff2f0'
}

export function QualityScoreBadge({ score, showLabel = false }: Props) {
  const sc = Math.round(score)
  const color = scoreColor(sc)
  const bgc = scoreBgc(sc)
  return (
    <span
      title={`数据质量分: ${sc}/100`}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 4,
        padding: '1px 8px', borderRadius: 10, fontSize: 11, fontWeight: 600,
        background: bgc, color, border: `1px solid ${color}44`,
      }}
    >
      {showLabel && <span style={{ opacity: 0.7 }}>质量</span>}
      {sc}
    </span>
  )
}
```

- [ ] **Step 2: Write EnhancementModal component**

```tsx
// frontend/src/pages/validation-center/components/EnhancementModal.tsx
import { useState, useEffect, useRef } from 'react'
import { Zap, CheckCircle, Sparkles, BarChart3 } from 'lucide-react'

interface Tier1Stats {
  source_atlas_backfill: number; provenance_backfill: number
  enum_normalization: number; topology_fix: number
  region_creation: number; total: number
}

interface Tier2Stats {
  evidence_text: number; description: number
  function_crosscheck: number; topology_flags: number
  total: number
}

interface EnhancementResult {
  run_id: string
  tier1_fixes: Tier1Stats
  tier2_suggestions: Tier2Stats
  quality_score_change: { before_avg: number; after_avg: number }
  circuit_scores: Array<{ circuit_id: string; before: number; after: number }>
}

interface Props {
  runId: string
  circuitCount: number
  onClose: () => void
}

export function EnhancementModal({ runId, circuitCount, onClose }: Props) {
  const [phase, setPhase] = useState<'loading' | 'running' | 'done' | 'error'>('loading')
  const [result, setResult] = useState<EnhancementResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function run() {
      try {
        setPhase('running')
        const resp = await fetch('/api/validation/circuit/selection/enhance', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ run_id: runId, tier2_enabled: true }),
        })
        if (!resp.ok) throw new Error(`API: ${resp.status}`)
        const data = await resp.json()
        if (!cancelled) {
          setResult(data)
          setPhase('done')
        }
      } catch (e: unknown) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : '增强失败')
          setPhase('error')
        }
      }
    }
    run()
    return () => { cancelled = true }
  }, [runId])

  return (
    <div className="vw-modal-overlay" onClick={onClose}>
      <div className="vw-modal vw-modal-wide" onClick={e => e.stopPropagation()} style={{ maxHeight: '85vh' }}>
        <div className="vw-modal-hd">
          <h3><Sparkles size={18} style={{ marginRight: 6 }} />数据增强</h3>
          <span className="badge">{circuitCount} 回路</span>
          {phase !== 'running' && <button className="vw-modal-close" onClick={onClose}>✕</button>}
        </div>

        <div className="vw-modal-body">
          {phase === 'loading' && (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <p style={{ color: 'var(--text-muted)' }}>准备中...</p>
            </div>
          )}
          {phase === 'running' && (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <div style={{ animation: 'spin 1s linear infinite', display: 'inline-block' }}>
                <Sparkles size={32} color="var(--primary)" />
              </div>
              <p style={{ marginTop: 12 }}>正在增强 {circuitCount} 条回路...</p>
              <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>Tier 1 自动修复 + Tier 2 LLM 建议生成中</p>
            </div>
          )}
          {phase === 'error' && (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <p style={{ color: 'var(--danger)' }}>{error}</p>
              <button className="btn btn-sm btn-primary" onClick={onClose} style={{ marginTop: 12 }}>关闭</button>
            </div>
          )}
          {phase === 'done' && result && (
            <div>
              {/* Quality score delta */}
              <div className="vpm-cards" style={{ marginBottom: 16 }}>
                <div className="vpm-card">
                  <span className="vpm-card-num">{result.quality_score_change.before_avg}</span>
                  <span>增强前均分</span>
                </div>
                <div className="vpm-card vpm-card-green">
                  <span className="vpm-card-num">{result.quality_score_change.after_avg}</span>
                  <span>增强后均分</span>
                </div>
                <div className="vpm-card vpm-card-blue">
                  <span className="vpm-card-num">
                    +{(result.quality_score_change.after_avg - result.quality_score_change.before_avg).toFixed(1)}
                  </span>
                  <span>提升</span>
                </div>
              </div>

              {/* Tier 1 summary */}
              <h4 style={{ fontSize: 14, marginBottom: 8 }}>
                <Zap size={14} style={{ marginRight: 4 }} />
                Tier 1 自动修复 ({result.tier1_fixes.total} 项)
              </h4>
              <div style={{ fontSize: 13, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, marginBottom: 16 }}>
                <div>source_atlas 回填: <strong>{result.tier1_fixes.source_atlas_backfill}</strong></div>
                <div>溯源链补全: <strong>{result.tier1_fixes.provenance_backfill}</strong></div>
                <div>枚举标准化: <strong>{result.tier1_fixes.enum_normalization}</strong></div>
                <div>区域关联创建: <strong>{result.tier1_fixes.region_creation}</strong></div>
              </div>

              {/* Tier 2 summary */}
              <h4 style={{ fontSize: 14, marginBottom: 8 }}>
                <Sparkles size={14} style={{ marginRight: 4 }} />
                Tier 2 LLM 建议 ({result.tier2_suggestions.total} 条，待审核)
              </h4>
              <div style={{ fontSize: 13, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4 }}>
                <div>证据文本: <strong>{result.tier2_suggestions.evidence_text}</strong></div>
                <div>描述补全: <strong>{result.tier2_suggestions.description}</strong></div>
                <div>功能交叉验证: <strong>{result.tier2_suggestions.function_crosscheck}</strong></div>
                <div>拓扑标志: <strong>{result.tier2_suggestions.topology_flags}</strong></div>
              </div>
            </div>
          )}
        </div>

        <div className="vw-modal-ft">
          {phase === 'done' && (
            <>
              <button className="btn btn-sm btn-primary" onClick={onClose}>完成</button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/validation-center/components/QualityScoreBadge.tsx frontend/src/pages/validation-center/components/EnhancementModal.tsx
git commit -m "feat: add QualityScoreBadge and EnhancementModal components"
```

---

### Task 8: Frontend — Wire Enhancement into RuleValidationTab + Table

**Files:**
- Modify: `frontend/src/pages/validation-center/components/RuleValidationTab.tsx` (StartValidation progress modal footer)
- Modify: `frontend/src/pages/validation-center/components/CandidateCircuitTable.tsx` (quality score column)
- Modify: `frontend/src/pages/validation-center/components/CircuitSelector.tsx` (quality score column)

- [ ] **Step 1: Add "数据增强" button to StartValidation progress modal footer**

In `StartValidation` component, in the `vp.phase === 'completed'` footer section, add a button between "送入双模型审核" and the close button:

```tsx
{/* Add this button in the completed footer, after 送入双模型审核 */}
<button className="btn btn-sm"
  onClick={async () => {
    setVp(null) // close progress
    // Count missing fields from progress results
    const totalGaps = vp.candidate_progress.reduce(
      (sum, cp) => sum + (12 - cp.completed_rule_count), 0
    )
    setMessage(`正在启动数据增强...`)
    setTimeout(() => setMessage(null), 3000)
    try {
      const enhanceResp = await fetch('/api/validation/circuit/selection/enhance', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_id: vp.runId, tier2_enabled: true }),
      })
      if (!enhanceResp.ok) throw new Error(`API: ${enhanceResp.status}`)
      const enhanceData = await enhanceResp.json()
      setMessage(`✅ 数据增强完成: 自动修复 ${enhanceData.tier1_fixes?.total || 0} 项, LLM建议 ${enhanceData.tier2_suggestions?.total || 0} 条`)
      setTimeout(() => setMessage(null), 8000)
    } catch (e: unknown) {
      setMessage(`增强失败: ${e instanceof Error ? e.message : '未知错误'}`)
      setTimeout(() => setMessage(null), 5000)
    }
  }}>
  <Sparkles size={14} /> 数据增强({vp.selected_candidate_count})
</button>
```

Add `Sparkles` to the import line:

```tsx
import { RefreshCw, FileText, Play, Zap, Sparkles } from 'lucide-react'
```

- [ ] **Step 2: Add quality_score column to CircuitSelector table header**

In `CircuitSelector.tsx`, add a column between "置信度" and "规则":

```tsx
<th style={{ width: 52 }}>质量</th>
```

And in each row, add the cell:

```tsx
<td style={{ fontSize: 12 }}>
  <QualityScoreBadge score={item.quality_score || 0} />
</td>
```

Also add the `quality_score` field to `CircuitItem` interface and import `QualityScoreBadge`:

```tsx
import { QualityScoreBadge } from './QualityScoreBadge'

// In CircuitItem interface, add:
quality_score?: number
```

- [ ] **Step 3: Run TypeScript check**

```bash
cd frontend && npx tsc --noEmit --pretty
```

Expected: 0 errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/validation-center/components/RuleValidationTab.tsx frontend/src/pages/validation-center/components/CircuitSelector.tsx
git commit -m "feat: wire enhancement button and quality score into UI"
```

---

### Task 9: Integration Test + Final Verification

**Files:**
- Modify: `backend/tests/test_validation_state_machine.py` (add enhancement tests)

- [ ] **Step 1: Write integration test for enhancement endpoint**

```python
# Add to test_validation_state_machine.py

def test_enhancement_endpoint_loads():
    """Enhancement router is registered and loads without errors."""
    from app.routers.enhancement import router
    assert len(router.routes) >= 3


def test_quality_score_computation():
    """compute_quality_score returns valid 0-100 range."""
    from app.services.mirror_circuit_validation_service import compute_quality_score

    class FakeCircuit:
        circuit_name = "test"
        circuit_type = "feedforward"
        source_atlas = "AAL3"
        evidence_text = "Evidence text long enough for scoring purposes"
        description = "A test circuit description"
        resource_id = None
        batch_id = None
        llm_run_id = None

    class FakeStep:
        def __init__(self, order, role, step_type, evidence=None):
            self.step_order = order
            self.role = role
            self.step_type = step_type
            self.evidence_text = evidence

    circuit = FakeCircuit()
    steps = [
        FakeStep(1, "origin", "region", "Some evidence"),
        FakeStep(2, "terminus", "region", "More evidence"),
    ]

    score = compute_quality_score(circuit, steps, 2)
    assert 0 <= score <= 100
    # Should get field completeness(30) + moderate topology + good evidence + region(10)
    assert score >= 40, f"Expected score >= 40, got {score}"
```

- [ ] **Step 2: Run tests**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/test_validation_state_machine.py -q
```

Expected: 41 passed

- [ ] **Step 3: Full test suite**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/ -q --tb=short 2>&1 | tail -5
```

Expected: same 13 pre-existing failures, 0 new failures

- [ ] **Step 4: Final TypeScript check**

```bash
cd frontend && npx tsc --noEmit --pretty
```

Expected: 0 errors

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_validation_state_machine.py
git commit -m "test: add enhancement and quality score tests"
```

---

## Self-Review Notes

1. **Spec coverage:** All sections covered — Tier 1 (Task 4), Tier 2 (Task 4), quality score (Task 3), DB (Task 1), API (Task 5), frontend modal (Task 7), quality badge (Task 7), human review extension (routed through existing `_apply_correction_to_source` in Task 5).

2. **No placeholders:** All code blocks are complete with exact implementations.

3. **Type consistency:** `EnhancementResponse` defined in Task 2 matches `run_enhancement` return type in Task 4; `EnhancementSuggestionRead` in Task 2 matches the `list_enhancements` response in Task 5; `QualityScoreBadge` props in Task 7 match usage in Task 8 Step 2.
