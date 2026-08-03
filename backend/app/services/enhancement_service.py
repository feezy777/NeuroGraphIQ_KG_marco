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
    """Backfill resource_id / batch_id from step -> region -> candidate chain."""
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
    """Normalize circuit_type, step_type, role to known enum values."""
    fixed = 0
    ctype = (circuit.circuit_type or "").lower()
    if ctype and ctype not in KNOWN_CIRCUIT_TYPES:
        for known in KNOWN_CIRCUIT_TYPES:
            if known in ctype or ctype in known:
                circuit.circuit_type = known
                fixed += 1
                break
        if not fixed:
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
    """Create MirrorCircuitRegion records from steps with region_candidate_id."""
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


async def _tier2_generate_evidence(
    session: AsyncSession, circuit: Any, steps: list[Any],
    provider: Any, sem: asyncio.Semaphore, dry_run: bool,
) -> list[dict]:
    """Generate evidence_text for a circuit via DeepSeek."""
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


async def run_enhancement(
    session: AsyncSession,
    run_id: uuid.UUID,
    circuit_ids: list[uuid.UUID],
    tier2_enabled: bool = True,
    dry_run: bool = False,
) -> EnhancementResponse:
    """Run Tier 1 auto-fixes and optionally Tier 2 LLM suggestions."""
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
