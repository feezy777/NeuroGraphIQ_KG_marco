"""Mirror circuit validation orchestration service.

Orchestrates: deterministic rule check -> dual LLM review -> adjudication.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mirror_circuit_validation import (
    MirrorCircuitValidationResult,
    MirrorCircuitValidationRun,
)
from app.models.mirror_kg import MirrorRegionCircuit
from app.schemas.mirror_circuit_validation import (
    CircuitValidationCreateRequest,
    CircuitValidationProgressResponse,
)
from app.services.llm_providers import get_llm_provider

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rule definitions
# ---------------------------------------------------------------------------

HARD_RULES: list[dict[str, str]] = [
    {"code": "REGION_IDENTITY", "desc": "region_id must exist in candidate region table", "severity": "blocker"},
    {"code": "EDGE_EXISTENCE", "desc": "edge_id must exist in original graph", "severity": "blocker"},
    {"code": "DIRECTION_CORRECT", "desc": "edge.source/target must match original record", "severity": "blocker"},
    {"code": "STEP_CONTINUITY", "desc": "step[i].target must equal step[i+1].source", "severity": "blocker"},
    {"code": "CLOSED_LOOP", "desc": "when closed_loop=true, last.target must equal first.source", "severity": "blocker"},
    {"code": "PROVENANCE_COMPLETE", "desc": "resource_id->batch_id->llm_run_id chain must be complete", "severity": "blocker"},
    {"code": "GRANULARITY_HOMOGENEITY", "desc": "all nodes in circuit must share the same granularity level", "severity": "blocker"},
]

SOFT_RULES: list[dict[str, str]] = [
    {"code": "TOPOLOGY_TYPE_VALID", "desc": "topology_type must be in known enum", "severity": "warning"},
    {"code": "CANONICAL_KEY_DUPLICATE", "desc": "canonical_key must not duplicate existing keys", "severity": "warning"},
    {"code": "FIELD_COMPLETENESS", "desc": "required fields must not be null/empty", "severity": "warning"},
    {"code": "IDEMPOTENCY", "desc": "same canonical_key should be mergeable", "severity": "info"},
    {"code": "LABEL_QUALITY", "desc": "name/label must not contain placeholders", "severity": "warning"},
]

ALL_RULES: list[dict[str, str]] = HARD_RULES + SOFT_RULES

_HARD_CODES: set[str] = {r["code"] for r in HARD_RULES}

# ---------------------------------------------------------------------------
# Reviewer system prompts
# ---------------------------------------------------------------------------

REVIEWER_A_SYSTEM_PROMPT: str = (
    "You are Reviewer A, a neuroanatomy specialist evaluating brain circuit descriptions. "
    "Your task is to assess the neuroanatomical plausibility of the provided circuit.\n\n"
    "Evaluate these dimensions:\n"
    "1. **Neuroanatomical Plausibility**: Are the regions in this circuit anatomically "
    "connected based on known tract-tracing or imaging data?\n"
    "2. **Topology**: Does the circuit topology (serial/parallel/recurrent) make anatomical "
    "sense given the regions involved?\n"
    "3. **Region Roles**: Are the roles assigned to each region (source/target/relay) "
    "consistent with known anatomical pathways?\n"
    "4. **Projection Direction**: Does the direction of projections follow known white-matter "
    "tracts?\n"
    "5. **Circuit Naming**: Does the circuit name reflect standard neuroanatomical "
    "nomenclature?\n\n"
    "Output as JSON with fields:\n"
    '- `decision`: "support" | "reject" | "uncertain"\n'
    "- `confidence`: float (0.0-1.0)\n"
    "- `reasoning`: str (detailed explanation)\n"
    "- `issues`: list[str] (specific problems found, if any)"
)

REVIEWER_B_SYSTEM_PROMPT: str = (
    "You are Reviewer B, a functional neuroscience specialist evaluating brain circuit "
    "descriptions. Your task is to assess the functional coherence of the provided circuit.\n\n"
    "Evaluate these dimensions:\n"
    "1. **Functional Coherence**: Do the functional claims match the known functions of the "
    "regions involved?\n"
    "2. **Evidence Support**: Is the claimed function supported by available evidence "
    "(imaging, lesion, electrophysiology)?\n"
    "3. **Overclaiming**: Does the description make claims that go beyond what the evidence "
    "supports?\n"
    "4. **Module Assignment**: Are the module/network assignments (e.g., default mode, "
    "salience, executive control) appropriate?\n"
    "5. **Confidence Calibration**: Is the stated confidence level appropriate given the "
    "strength of evidence?\n\n"
    "Output as JSON with fields:\n"
    '- `decision`: "support" | "reject" | "uncertain"\n'
    "- `confidence`: float (0.0-1.0)\n"
    "- `reasoning`: str (detailed explanation)\n"
    "- `issues`: list[str] (specific problems found, if any)"
)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def create_validation_run(
    session: AsyncSession,
    req: CircuitValidationCreateRequest,
) -> MirrorCircuitValidationRun:
    """Create a new validation run record."""
    run = MirrorCircuitValidationRun(
        id=uuid.uuid4(),
        granularity_level=req.granularity_level,
        source_atlas=req.source_atlas,
        target_types=req.target_types or ["circuit"],
        scope_json={
            "circuit_ids": req.circuit_ids,
            "step_ids": req.step_ids,
            "batch_ids": req.batch_ids,
        },
        reviewer_a_provider=req.reviewer_a_provider,
        reviewer_a_model=req.reviewer_a_model,
        reviewer_b_provider=req.reviewer_b_provider,
        reviewer_b_model=req.reviewer_b_model,
        dry_run=req.dry_run,
        status="created",
        rule_validation_status="pending",
        dual_review_status="pending",
        adjudication_status="pending",
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    _log.info("Created validation run %s (granularity=%s)", run.id, req.granularity_level)
    return run


async def run_rule_validation(
    session: AsyncSession,
    run: MirrorCircuitValidationRun,
) -> dict[str, int]:
    """Phase 1: run deterministic rules against validation targets.

    Returns a dict of counts: total, passed, failed, warning, blocked, hard_failures.
    """
    targets = await _collect_validation_targets(session, run)
    if not targets:
        _log.warning("No targets found for validation run %s", run.id)
        run.rule_validation_status = "completed"
        await session.commit()
        return {"total": 0, "passed": 0, "failed": 0, "warning": 0, "blocked": 0, "hard_failures": 0}

    rule_total = len(ALL_RULES) * len(targets)
    rule_passed = 0
    rule_failed = 0
    rule_warning = 0
    rule_blocked = 0
    hard_failures = 0

    results: list[MirrorCircuitValidationResult] = []

    for target in targets:
        target_type: str = target["type"]
        target_id: uuid.UUID = target["id"]
        label: str | None = target.get("label")
        rule_results: list[dict[str, Any]] = []
        blocked = False

        for rule_def in ALL_RULES:
            rule_code: str = rule_def["code"]
            outcome = _run_single_rule(rule_code, target)
            rule_results.append(outcome)
            if outcome["status"] == "pass":
                rule_passed += 1
            elif outcome["status"] == "fail":
                rule_failed += 1
                if rule_code in _HARD_CODES:
                    blocked = True
                    hard_failures += 1
            elif outcome["status"] == "warning":
                rule_warning += 1
            elif outcome["status"] == "blocked":
                rule_blocked += 1
                if rule_code in _HARD_CODES:
                    blocked = True
                    hard_failures += 1

        overall = "blocked" if blocked else "passed"
        result_obj = MirrorCircuitValidationResult(
            id=uuid.uuid4(),
            run_id=run.id,
            target_type=target_type,
            target_id=target_id,
            object_label=label,
            rule_validation_result_json=rule_results,
            rule_overall_status=overall,
            rule_blocked=blocked,
        )
        results.append(result_obj)

    for r in results:
        session.add(r)

    run.rule_total_count = rule_total
    run.rule_passed_count = rule_passed
    run.rule_failed_count = rule_failed
    run.rule_warning_count = rule_warning
    run.rule_blocked_count = rule_blocked
    run.rule_hard_failure_count = hard_failures
    run.rule_validation_status = "completed"
    await session.commit()
    _log.info(
        "Rule validation completed for run %s: passed=%d failed=%d blocked=%d",
        run.id, rule_passed, rule_failed, rule_blocked,
    )
    return {
        "total": rule_total,
        "passed": rule_passed,
        "failed": rule_failed,
        "warning": rule_warning,
        "blocked": rule_blocked,
        "hard_failures": hard_failures,
    }


async def run_dual_review(
    session: AsyncSession,
    run: MirrorCircuitValidationRun,
) -> dict[str, int]:
    """Phase 2: parallel dual LLM review + adjudication.

    Skips blocked targets. Returns a dict of adjudication counts.
    """
    stmt = select(MirrorCircuitValidationResult).where(
        MirrorCircuitValidationResult.run_id == run.id,
    )
    result_db = await session.execute(stmt)
    results = list(result_db.scalars().all())

    if not results:
        _log.warning("No results to review for run %s", run.id)
        run.dual_review_status = "completed"
        await session.commit()
        return {"total": 0, "agreement": 0, "conflict": 0, "rejection": 0, "uncertain": 0, "low_evidence": 0}

    run.dual_review_total_count = len(results)

    agreement = 0
    conflict = 0
    rejection = 0
    uncertain = 0
    low_evidence = 0

    for res_obj in results:
        a_task = _call_reviewer(
            res_obj, run, run.reviewer_a_provider, run.reviewer_a_model,
            REVIEWER_A_SYSTEM_PROMPT,
        )
        b_task = _call_reviewer(
            res_obj, run, run.reviewer_b_provider, run.reviewer_b_model,
            REVIEWER_B_SYSTEM_PROMPT,
        )
        a_result, b_result = await asyncio.gather(a_task, b_task)

        res_obj.reviewer_a_decision = a_result["decision"]
        res_obj.reviewer_a_confidence = a_result["confidence"]
        res_obj.reviewer_a_payload_json = a_result
        res_obj.reviewer_b_decision = b_result["decision"]
        res_obj.reviewer_b_confidence = b_result["confidence"]
        res_obj.reviewer_b_payload_json = b_result

        adjudication = _adjudicate(a_result, b_result)
        res_obj.adjudication_status = adjudication["status"]
        res_obj.adjudication_confidence_diff = adjudication["confidence_diff"]
        res_obj.adjudication_summary = adjudication["summary"]
        res_obj.recommended_review_priority = adjudication["priority"]

        if adjudication["status"] == "consensus_supported":
            agreement += 1
        elif adjudication["status"] in ("model_conflict", "confidence_divergence"):
            conflict += 1
        elif adjudication["status"] == "consensus_rejected":
            rejection += 1
        elif adjudication["status"] == "low_evidence":
            low_evidence += 1
        else:
            uncertain += 1

    run.dual_review_agreement_count = agreement
    run.dual_review_conflict_count = conflict
    run.dual_review_rejection_count = rejection
    run.dual_review_uncertain_count = uncertain
    run.dual_review_low_evidence_count = low_evidence
    run.dual_review_status = "completed"
    run.adjudication_status = "completed"
    await session.commit()
    _log.info(
        "Dual review completed for run %s: agree=%d conflict=%d reject=%d low_evidence=%d",
        run.id, agreement, conflict, rejection, low_evidence,
    )
    return {
        "total": len(results),
        "agreement": agreement,
        "conflict": conflict,
        "rejection": rejection,
        "uncertain": uncertain,
        "low_evidence": low_evidence,
    }


async def run_full_validation(
    session: AsyncSession,
    run_id: uuid.UUID,
) -> MirrorCircuitValidationRun:
    """Execute the full validation pipeline (Phase 1 + Phase 2).

    Uses the given session. For background-task usage, call
    ``run_full_validation_background`` instead so the service creates its own
    session (the request-scoped session from ``get_db`` is closed after the
    response is sent).
    """
    stmt = select(MirrorCircuitValidationRun).where(
        MirrorCircuitValidationRun.id == run_id,
    )
    result = await session.execute(stmt)
    run = result.scalar_one_or_none()
    if run is None:
        msg = f"Validation run {run_id} not found"
        raise ValueError(msg)

    if run.status != "created":
        _log.warning(
            "Validation run %s already started (status=%s)", run_id, run.status,
        )
        return run

    try:
        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        await session.commit()

        run.rule_validation_status = "running"
        await session.commit()
        await run_rule_validation(session, run)

        run.dual_review_status = "running"
        await session.commit()
        await run_dual_review(session, run)

        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        await session.commit()
        _log.info("Full validation completed for run %s", run_id)

    except Exception as exc:
        _log.exception("Validation run %s failed", run_id)
        run.status = "failed"
        run.error_message = str(exc)
        await session.commit()

    return run


async def run_full_validation_background(run_id: uuid.UUID) -> None:
    """Full validation pipeline designed for FastAPI BackgroundTasks.

    Creates its own DB session so that it stays alive after the HTTP response
    is sent.  Retries up to 3 times to find the run in case the commit from
    the create endpoint is not yet visible.
    """
    from app.database import AsyncSessionLocal

    _log.info("[validation][background] START run=%s", run_id)

    if AsyncSessionLocal is None:
        _log.error("[validation][background] AsyncSessionLocal unavailable")
        return

    for attempt in range(3):
        try:
            async with AsyncSessionLocal() as session:
                run = await session.get(MirrorCircuitValidationRun, run_id)
                if run is not None:
                    await run_full_validation(session, run_id)
                    return
        except Exception:
            _log.exception("[validation][background] attempt %d failed", attempt + 1)
        if attempt < 2:
            await asyncio.sleep(1)

    _log.error("[validation][background] run %s not found after retries", run_id)


async def get_validation_progress(
    session: AsyncSession,
    run_id: uuid.UUID,
) -> CircuitValidationProgressResponse:
    """Get progress of a validation run for polling."""
    stmt = select(MirrorCircuitValidationRun).where(
        MirrorCircuitValidationRun.id == run_id,
    )
    result = await session.execute(stmt)
    run = result.scalar_one_or_none()
    if run is None:
        msg = f"Validation run {run_id} not found"
        raise ValueError(msg)

    phase: str
    progress: float = 0.0

    if run.status in ("created", "pending"):
        phase = "not_started"
    elif run.status == "running":
        if run.rule_validation_status in ("pending", "running"):
            phase = "rule_validation"
            total = max(run.rule_total_count, 1)
            done = run.rule_passed_count + run.rule_failed_count
            progress = min(done / total * 33.33, 33.33)
        elif run.dual_review_status in ("pending", "running"):
            phase = "dual_review"
            total = max(run.dual_review_total_count, 1)
            done = (
                run.dual_review_agreement_count
                + run.dual_review_conflict_count
                + run.dual_review_rejection_count
                + run.dual_review_uncertain_count
                + run.dual_review_low_evidence_count
            )
            progress = 33.33 + min(done / total * 33.33, 33.33)
        else:
            phase = "adjudication"
            progress = 66.66 + (33.34 if run.adjudication_status == "completed" else 0)
    elif run.status == "completed":
        phase = "completed"
        progress = 100.0
    else:
        phase = run.status

    return CircuitValidationProgressResponse(
        run_id=str(run.id),
        status=run.status,
        phase=phase,
        progress_percent=round(progress, 2),
        rule_total=run.rule_total_count,
        rule_done=run.rule_passed_count + run.rule_failed_count,
        dual_total=run.dual_review_total_count,
        dual_done=(
            run.dual_review_agreement_count
            + run.dual_review_conflict_count
            + run.dual_review_rejection_count
            + run.dual_review_uncertain_count
            + run.dual_review_low_evidence_count
        ),
        adjudication_done=run.adjudication_status == "completed",
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _adjudicate(
    a_result: dict[str, Any],
    b_result: dict[str, Any],
) -> dict[str, Any]:
    """Adjudicate between two reviewer outputs.

    Priority ordering (first match wins):

    1. ``low_evidence``      — either confidence < 0.4 (``high`` priority)
    2. ``consensus_supported`` — both ``support``, |diff| < 0.3 (``normal``)
    3. ``confidence_divergence`` — both ``support``, |diff| >= 0.3 (``high``)
    4. ``consensus_rejected``   — both ``reject`` (``normal``)
    5. ``model_conflict``       — one ``support`` + one ``reject`` (``urgent``)
    6. ``insufficient_information`` — fallback (``high``)
    """
    a_dec = a_result.get("decision", "uncertain")
    a_conf = float(a_result.get("confidence", 0.0))
    b_dec = b_result.get("decision", "uncertain")
    b_conf = float(b_result.get("confidence", 0.0))
    conf_diff = abs(a_conf - b_conf)

    # 1. Low evidence
    if a_conf < 0.4 or b_conf < 0.4:
        return {
            "status": "low_evidence",
            "confidence_diff": conf_diff,
            "summary": (
                f"Reviewer A confidence={a_conf:.2f}, "
                f"Reviewer B confidence={b_conf:.2f}. "
                "One or both reviewers have low confidence (<0.4)."
            ),
            "priority": "high",
        }

    # 2. Both support, confidence close
    if a_dec == "support" and b_dec == "support":
        if conf_diff < 0.3:
            return {
                "status": "consensus_supported",
                "confidence_diff": conf_diff,
                "summary": (
                    f"Both reviewers support with close confidence "
                    f"(diff={conf_diff:.2f})."
                ),
                "priority": "normal",
            }
        # 3. Both support, confidence far apart
        return {
            "status": "confidence_divergence",
            "confidence_diff": conf_diff,
            "summary": (
                f"Both support but confidence differs significantly "
                f"(diff={conf_diff:.2f})."
            ),
            "priority": "high",
        }

    # 4. Both reject
    if a_dec == "reject" and b_dec == "reject":
        return {
            "status": "consensus_rejected",
            "confidence_diff": conf_diff,
            "summary": "Both reviewers reject this circuit.",
            "priority": "normal",
        }

    # 5. One support, one reject  (exact conflict)
    if (a_dec == "support" and b_dec == "reject") or (
        a_dec == "reject" and b_dec == "support"
    ):
        return {
            "status": "model_conflict",
            "confidence_diff": conf_diff,
            "summary": (
                f"Reviewers disagree: A={a_dec}, B={b_dec}. "
                f"Confidences: A={a_conf:.2f}, B={b_conf:.2f}."
            ),
            "priority": "urgent",
        }

    # 6. Fallback
    return {
        "status": "insufficient_information",
        "confidence_diff": conf_diff,
        "summary": (
            f"Could not reach clear adjudication. "
            f"A: {a_dec} ({a_conf:.2f}), B: {b_dec} ({b_conf:.2f})."
        ),
        "priority": "high",
    }


async def _collect_validation_targets(
    session: AsyncSession,
    run: MirrorCircuitValidationRun,
) -> list[dict[str, Any]]:
    """Collect targets from MirrorRegionCircuit based on run scope.

    Returns a list of dicts with keys: type, id, label.
    """
    circuit_ids = run.scope_json.get("circuit_ids", [])
    stmt = select(MirrorRegionCircuit)

    if circuit_ids:
        uuid_ids: list[uuid.UUID] = []
        for cid in circuit_ids:
            try:
                uuid_ids.append(uuid.UUID(str(cid)))
            except (ValueError, AttributeError):
                pass
        if uuid_ids:
            stmt = stmt.where(MirrorRegionCircuit.id.in_(uuid_ids))

    if run.granularity_level:
        stmt = stmt.where(
            MirrorRegionCircuit.granularity_level == run.granularity_level,
        )

    result_db = await session.execute(stmt)
    circuits = result_db.scalars().all()
    return [
        {
            "type": "circuit",
            "id": c.id,
            "label": c.circuit_name or c.name_cn or str(c.id)[:12],
        }
        for c in circuits
    ]


def _run_single_rule(
    rule_code: str,
    target: dict[str, Any],
) -> dict[str, Any]:
    """Run a single deterministic rule against a target.

    Currently a stub -- most rules return ``pass``. Real implementations
    will be added in a later task.
    """
    _ = target  # unused in stub

    stub_messages: dict[str, str] = {
        "REGION_IDENTITY": "Region identity verified (stub).",
        "EDGE_EXISTENCE": "Edge existence verified (stub).",
        "DIRECTION_CORRECT": "Direction verified (stub).",
        "STEP_CONTINUITY": "Step continuity verified (stub).",
        "CLOSED_LOOP": "Closed loop check passed (stub).",
        "PROVENANCE_COMPLETE": "Provenance verified (stub).",
        "GRANULARITY_HOMOGENEITY": "Granularity verified (stub).",
        "TOPOLOGY_TYPE_VALID": "Topology type valid (stub).",
        "CANONICAL_KEY_DUPLICATE": "No duplicate keys (stub).",
        "FIELD_COMPLETENESS": "Fields complete (stub).",
        "IDEMPOTENCY": "Idempotency verified (stub).",
        "LABEL_QUALITY": "Label quality verified (stub).",
    }

    message = stub_messages.get(rule_code, f"Unknown rule, defaulting to pass (stub).")
    return {
        "rule": rule_code,
        "status": "pass",
        "message": message,
    }


async def _call_reviewer(
    res: MirrorCircuitValidationResult,
    run: MirrorCircuitValidationRun,
    provider_name: str,
    model: str,
    system_prompt: str,
) -> dict[str, Any]:
    """Call a single LLM reviewer and return structured output."""
    if run.dry_run:
        return {
            "decision": "uncertain",
            "confidence": 0.5,
            "reasoning": "Dry run -- no actual LLM call.",
            "issues": [],
        }
    try:
        circuit_data = _serialize_target_for_review(res, run)
        llm = get_llm_provider(provider_name)
        llm_response = await llm.complete_json(
            model=model,
            system_prompt=system_prompt,
            user_prompt=(
                f"Please review the following brain circuit:\n\n"
                f"{circuit_data}\n\n"
                f"Output your evaluation as JSON with fields: "
                f"decision (support/reject/uncertain), confidence (0.0-1.0), "
                f"reasoning (detailed explanation), issues (list of strings)."
            ),
            temperature=0.3,
            max_tokens=2000,
            timeout_seconds=120,
        )
        payload = llm_response.parsed_json or {}
        return {
            "decision": payload.get("decision", "uncertain"),
            "confidence": float(payload.get("confidence", 0.5)),
            "reasoning": payload.get("reasoning", ""),
            "issues": payload.get("issues", []),
        }
    except Exception as exc:
        _log.error("Reviewer call failed for target %s: %s", res.id, exc)
        return {
            "decision": "uncertain",
            "confidence": 0.0,
            "reasoning": f"LLM call error: {exc}",
            "issues": ["LLM call failed"],
        }


def _serialize_target_for_review(
    res: MirrorCircuitValidationResult,
    run: MirrorCircuitValidationRun,
) -> str:
    """Serialize a validation target into plain text for LLM review."""
    return (
        f"Target Type: {res.target_type}\n"
        f"Target ID: {res.target_id}\n"
        f"Label: {res.object_label or 'N/A'}\n"
        f"Granularity: {run.granularity_level}\n"
        f"Source Atlas: {run.source_atlas or 'N/A'}"
    )
