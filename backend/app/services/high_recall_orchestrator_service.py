"""Automatic multi-view high-recall discovery orchestration.

What it does
------------
Drives the four Discovery Views in their frozen order, automatically:

    A NAMED_CLASSIC_CIRCUITS → B LOCAL_INTRINSIC_CIRCUITS
    → C AFFERENT_CIRCUITS → D EFFERENT_CIRCUITS → COMPLETED

keeping each View alive while it still produces SEMANTIC NOVELTY, and moving on
once TWO CONSECUTIVE successful rounds produce none.

What it is not
--------------
Not Canonicalization. It merges nothing across Views, resolves no identity,
promotes nothing, and changes no candidate's status. A, B, C and D are
independent search strategies: a circuit found under two of them is expected.
Not a second candidate universe either — Discovery Runs and Novelty Assessments
stay the authorities, and this layer stores only control state.

The three rules that decide everything
--------------------------------------
1. NOVELTY, NOT CONFIDENCE. `semantic_new_count = NEW + BORDERLINE` is the only
   number that keeps a View alive. Confidence never appears in a decision: a
   0.20-confidence circuit the assessor calls NEW outvotes a 0.95 one it calls
   an ALIAS.
2. FAILURE IS NOT ZERO. A failed Discovery round and a failed assessment both
   STOP the orchestration as BLOCKED. Neither advances the zero streak, because
   neither is evidence that the View stopped producing novelty.
3. BUDGET IS NOT SATURATION. Exhausting the safety budget pauses; it never
   marks a View exhausted. A pause is resumable and no round is repeated.

What `successful_round_count` means
-----------------------------------
    NEW Discovery runs this orchestration SUCCESSFULLY COMPLETED for this View

  * A round the orchestration CREATED and that reached COMPLETED counts — ONCE.
  * A historical run it merely ATTACHED to during bootstrap does NOT count. The
    bootstrap resolves pre-existing history; resolving a run is not creating one.
  * A FAILED run does NOT count, ever.
  * The novelty outcome does NOT decide it. The counter moves the moment the
    run completes, BEFORE the assessment, because the Discovery round succeeded
    whether or not the assessor later agrees — and a failed assessment must not
    erase a completed round.
  * It is settled at THAT boundary, not when the View happens to pause or
    saturate: a View that blocks with completed rounds must not lose them.
  * `_COUNT_SUCCESSFUL_ROUND_SQL` is its only writer, and the row's own
    ``latest_successful_run_pk`` is the exactly-once guard.

Bootstrap
---------
A View that already has discovery history is picked up from its LATEST
SUCCESSFUL run, never restarted at Round 1. If that run has no durable
assessment yet, one is produced and persisted now — a new authoritative
assessment, not a "backfill", and not a claim about what an earlier prose report
said.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm_discovery_views import DISCOVERY_VIEWS, strategy_identifier
from app.schemas.orchestration import (
    ZERO_STREAK_TO_SATURATE,
    OrchestrationRead,
    OrchestrationStartRequest,
    OrchestrationViewStateRead,
)
from app.services import llm_circuit_novelty_service as novelty
from app.services.llm_circuit_novelty_read_service import get_novelty_summary

logger = logging.getLogger(__name__)

#: The A→B→C→D search order. Server-owned: a caller cannot reorder, skip or add
#: a View, because that would silently change what "saturated" means.
VIEW_ORDER: tuple[str, ...] = DISCOVERY_VIEWS

STRATEGY_FAMILY = "G4_HIGH_RECALL_V1"
STRATEGY_VERSION = "G4HR1"

#: Non-working states. A View in one of these is done and must be skipped.
_VIEW_TERMINAL = ("SATURATED_BY_ZERO_NOVELTY", "COMPLETE")


# ===========================================================================
# typed failures
# ===========================================================================
class OrchestrationError(Exception):
    code = "ORCHESTRATION_ERROR"


class OrchestrationSeedNotFound(OrchestrationError):
    code = "ORCHESTRATION_SEED_NOT_FOUND"

    def __init__(self, entity_id: str) -> None:
        super().__init__(f"BrainRegion '{entity_id}' not found")
        self.entity_id = entity_id


class OrchestrationNotFound(OrchestrationError):
    code = "ORCHESTRATION_NOT_FOUND"

    def __init__(self, orchestration_id: str) -> None:
        super().__init__(f"orchestration '{orchestration_id}' not found")
        self.orchestration_id = orchestration_id


class OrchestrationAlreadyRunning(OrchestrationError):
    """Another execution holds this seed. Two loops over one seed would each
    continue from what they last saw and double-spend the provider."""

    code = "ORCHESTRATION_ALREADY_RUNNING"

    def __init__(self, orchestration_id: str) -> None:
        super().__init__(
            f"orchestration '{orchestration_id}' is already RUNNING for this seed"
        )
        self.orchestration_id = orchestration_id


class OrchestrationBlocked(OrchestrationError):
    """A previous execution stopped on a failure that has not been resolved."""

    code = "ORCHESTRATION_BLOCKED"

    def __init__(self, orchestration_id: str, reason: str) -> None:
        super().__init__(
            f"orchestration '{orchestration_id}' is BLOCKED: {reason}"
        )
        self.orchestration_id = orchestration_id
        self.reason = reason


# ===========================================================================
# SQL
# ===========================================================================
_SEED_SQL = text(
    "SELECT b.entity_pk FROM brain_regions b JOIN kg_entities e"
    "  ON e.entity_pk = b.entity_pk WHERE e.entity_id = :entity_id"
)

_INSERT_ORCH_SQL = text(
    """
    INSERT INTO discovery_orchestrations
        (seed_region_pk, strategy_family, strategy_version, status,
         discovery_call_budget)
    VALUES (:seed_pk, :family, :version, 'READY', :budget)
    RETURNING orchestration_pk, orchestration_id
    """
)

_INSERT_VIEW_STATES_SQL = text(
    """
    INSERT INTO discovery_orchestration_view_states
        (orchestration_pk, discovery_view, position, status)
    VALUES (:orchestration_pk, :discovery_view, :position, 'PENDING')
    ON CONFLICT (orchestration_pk, discovery_view) DO NOTHING
    """
)

_ACTIVE_SQL = text(
    """
    SELECT orchestration_pk, orchestration_id, status
    FROM discovery_orchestrations
    WHERE seed_region_pk = :seed_pk AND status <> 'COMPLETED'
    ORDER BY created_at DESC
    LIMIT 1
    """
)

_ORCH_SQL = text(
    """
    SELECT o.orchestration_pk, o.orchestration_id, o.status, o.current_view,
           o.zero_streak, o.discovery_call_budget, o.discovery_calls_used,
           o.novelty_calls_used, o.stop_reason, o.created_at, o.started_at,
           o.finished_at, o.strategy_family, o.strategy_version,
           e.entity_id AS seed_entity_id
    FROM discovery_orchestrations o
    JOIN brain_regions b ON b.entity_pk = o.seed_region_pk
    JOIN kg_entities e ON e.entity_pk = b.entity_pk
    WHERE o.orchestration_id = :orchestration_id
    """
)

_VIEW_STATES_SQL = text(
    """
    SELECT v.view_state_pk, v.discovery_view, v.position, v.status,
           v.zero_streak, v.successful_round_count, v.failed_attempt_count,
           v.semantic_new_count, v.stop_reason, v.started_at, v.completed_at,
           -- The internal keys the loop writes BACK, plus the public ids a
           -- caller reads. Both, because they answer different questions.
           v.latest_successful_run_pk, v.latest_novelty_assessment_pk,
           r.run_id AS latest_run_id, a.assessment_id AS latest_assessment_id
    FROM discovery_orchestration_view_states v
    LEFT JOIN knowledge_discovery_runs r ON r.run_pk = v.latest_successful_run_pk
    LEFT JOIN discovery_circuit_novelty_assessments a
           ON a.assessment_pk = v.latest_novelty_assessment_pk
    WHERE v.orchestration_pk = :orchestration_pk
    ORDER BY v.position
    """
)

_UPDATE_ORCH_SQL = text(
    """
    UPDATE discovery_orchestrations
       SET status = :status,
           current_view = :current_view,
           zero_streak = :zero_streak,
           discovery_call_budget = :budget,
           discovery_calls_used = discovery_calls_used + :discovery_delta,
           novelty_calls_used = novelty_calls_used + :novelty_delta,
           stop_reason = :stop_reason,
           started_at = COALESCE(started_at, now()),
           -- A separate boolean rather than re-testing :status: Postgres cannot
           -- infer one type for a parameter used both as a varchar value and
           -- inside a comparison.
           finished_at = CASE WHEN :terminal THEN now()
                              ELSE finished_at END
     WHERE orchestration_pk = :orchestration_pk
    """
)

_UPDATE_VIEW_SQL = text(
    """
    UPDATE discovery_orchestration_view_states
       SET status = :status,
           zero_streak = :zero_streak,
           latest_successful_run_pk = :latest_run_pk,
           latest_novelty_assessment_pk = :latest_assessment_pk,
           -- successful_round_count is deliberately NOT touched here. It has one
           -- writer, _COUNT_SUCCESSFUL_ROUND_SQL, which settles it the moment a
           -- new run completes rather than when the View happens to pause.
           failed_attempt_count = failed_attempt_count + :failed_delta,
           semantic_new_count = :semantic_new_count,
           stop_reason = :stop_reason,
           started_at = COALESCE(started_at, now()),
           completed_at = CASE WHEN :terminal THEN now()
                               ELSE completed_at END
     WHERE orchestration_pk = :orchestration_pk AND discovery_view = :discovery_view
    """
)

#: Count one successful Discovery round — EXACTLY ONCE.
#:
#: The guard is the row's own stored ``latest_successful_run_pk``: the same run
#: can never be counted twice, because the first write moves that column to the
#: run being counted. No new table, no in-memory bookkeeping, and no reliance on
#: a caller remembering what it already did — the database is the guard.
_COUNT_SUCCESSFUL_ROUND_SQL = text(
    """
    UPDATE discovery_orchestration_view_states
       SET successful_round_count = successful_round_count + 1,
           latest_successful_run_pk = :run_pk
     WHERE orchestration_pk = :orchestration_pk
       AND discovery_view = :discovery_view
       AND latest_successful_run_pk IS DISTINCT FROM :run_pk
    """
)

_ASSESSMENT_PK_SQL = text(
    "SELECT assessment_pk FROM discovery_circuit_novelty_assessments"
    " WHERE assessment_id = :assessment_id"
)


# ===========================================================================
# small helpers
# ===========================================================================
def _log(tag: str, **fields: Any) -> None:
    """Structured, single line. Never a model response."""
    body = " ".join(f"{k}={v}" for k, v in fields.items() if v is not None)
    logger.info("[orchestrator][%s] %s", tag, body)


@dataclass(frozen=True)
class _Assessment:
    """What the loop needs to know about one judgement."""

    #: Nullable, because the view-state column is: a judgement whose row is not
    #: reachable is still a judgement, and refusing to record the loop's
    #: position over a missing pointer would lose more than it protects.
    assessment_pk: int | None
    semantic_new_count: int
    #: Provider calls this judgement cost. ZERO when an existing assessment was
    #: reused, and zero for the deterministic empty-prior-pool judgement.
    provider_calls: int


@dataclass
class _Ledger:
    """Provider calls actually spent in ONE execution.

    Mutable and shared, deliberately: ``_Pause`` and ``_Blocked`` leave the loop
    by exception, so an integer returned from a helper would never reach the
    handler and calls that really were spent would be recorded as zero.
    Under-reporting cost is the one error a cost ledger must not make.
    """

    discovery: int = 0
    novelty: int = 0


class _Pause(Exception):
    """The safety budget is exhausted. Not a scientific outcome."""


class _Blocked(Exception):
    """A failure that must stop the orchestration. Never a zero."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# ===========================================================================
# start / resume
# ===========================================================================
async def start_orchestration(
    session: AsyncSession, *, entity_id: str, request: OrchestrationStartRequest | None = None
) -> OrchestrationRead:
    """Begin (or continue) the automatic sweep of one BrainRegion seed."""
    req = request or OrchestrationStartRequest()
    seed_pk = (await session.execute(_SEED_SQL, {"entity_id": entity_id})).scalars().first()
    if seed_pk is None:
        raise OrchestrationSeedNotFound(entity_id)

    active = (await session.execute(_ACTIVE_SQL, {"seed_pk": seed_pk})).mappings().first()
    if active is not None:
        # One orchestration per seed, in flight. A RUNNING one is a hard no: two
        # loops would each continue from what they last saw.
        if active["status"] == "RUNNING":
            raise OrchestrationAlreadyRunning(active["orchestration_id"])
        if active["status"] == "BLOCKED":
            row = (await session.execute(
                _ORCH_SQL, {"orchestration_id": active["orchestration_id"]})).mappings().one()
            raise OrchestrationBlocked(active["orchestration_id"], row["stop_reason"] or "unspecified")
        # PAUSED_BY_BUDGET / READY: continue the SAME orchestration rather than
        # starting a parallel one that would redo its work.
        _log("start", orchestration_id=active["orchestration_id"], seed=entity_id,
             note="resuming_active")
        return await resume_orchestration(
            session, orchestration_id=active["orchestration_id"], request=req
        )

    row = (await session.execute(_INSERT_ORCH_SQL, {
        "seed_pk": seed_pk, "family": STRATEGY_FAMILY, "version": STRATEGY_VERSION,
        "budget": req.max_new_discovery_calls,
    })).mappings().one()
    orchestration_pk = row["orchestration_pk"]
    orchestration_id = row["orchestration_id"]

    for position, view in enumerate(VIEW_ORDER, start=1):
        await session.execute(_INSERT_VIEW_STATES_SQL, {
            "orchestration_pk": orchestration_pk, "discovery_view": view,
            "position": position,
        })
    await session.commit()

    _log("start", orchestration_id=orchestration_id, seed=entity_id,
         budget=req.max_new_discovery_calls)
    return await _execute(session, orchestration_pk=orchestration_pk)


async def resume_orchestration(
    session: AsyncSession, *, orchestration_id: str,
    request: OrchestrationStartRequest | None = None,
) -> OrchestrationRead:
    """Continue a paused orchestration from exactly where it stopped.

    No round is repeated, no View restarts, and no run that already has a
    durable assessment is assessed again — so a resume that has nothing new to
    do costs zero provider calls.
    """
    row = (await session.execute(
        _ORCH_SQL, {"orchestration_id": orchestration_id})).mappings().one_or_none()
    if row is None:
        raise OrchestrationNotFound(orchestration_id)
    if row["status"] == "RUNNING":
        raise OrchestrationAlreadyRunning(orchestration_id)
    if row["status"] == "COMPLETED":
        return await _read(session, orchestration_id)

    if request is not None:
        await session.execute(text(
            "UPDATE discovery_orchestrations SET discovery_call_budget = :b,"
            " status = 'READY' WHERE orchestration_pk = :pk"
        ), {"b": request.max_new_discovery_calls, "pk": row["orchestration_pk"]})
        await session.commit()
        _log("start", orchestration_id=orchestration_id, budget=request.max_new_discovery_calls,
             note="resume_with_new_budget")

    return await _execute(session, orchestration_pk=row["orchestration_pk"])


# ===========================================================================
# the loop
# ===========================================================================
async def _execute(session: AsyncSession, *, orchestration_pk: int) -> OrchestrationRead:
    """One execution of the loop: a fresh allowance of Discovery calls, run
    until the sweep completes, the budget is spent, or something fails."""
    head = (await session.execute(text(
        "SELECT orchestration_id, discovery_call_budget,"
        "       (SELECT e.entity_id FROM brain_regions b"
        "          JOIN kg_entities e ON e.entity_pk = b.entity_pk"
        "         WHERE b.entity_pk = o.seed_region_pk) AS seed_entity_id"
        " FROM discovery_orchestrations o WHERE orchestration_pk = :pk"
    ), {"pk": orchestration_pk})).mappings().one()
    orchestration_id = head["orchestration_id"]
    budget = int(head["discovery_call_budget"])

    ledger = _Ledger()
    seed_entity_id = head["seed_entity_id"]

    try:
        await _update_orchestration(
            session, orchestration_pk, status="RUNNING", current_view=None,
            zero_streak=0, budget=budget, discovery_delta=0, novelty_delta=0,
            stop_reason=None,
        )

        states = (await session.execute(
            _VIEW_STATES_SQL, {"orchestration_pk": orchestration_pk})).mappings().all()

        worked_any = False
        active_view: str | None = None
        for state in states:
            view = state["discovery_view"]
            if state["status"] in _VIEW_TERMINAL:
                continue
            worked_any = True
            # Bound BEFORE the call, so the failure handler knows which View
            # blocked without having to read it back from the parent row.
            active_view = view
            await _run_view(
                session, orchestration_pk=orchestration_pk,
                orchestration_id=orchestration_id, seed_entity_id=seed_entity_id,
                view=view, state=state, budget=budget, ledger=ledger,
            )

        # Every View saturated (or was already terminal): the sweep is done.
        await _update_orchestration(
            session, orchestration_pk, status="COMPLETED", current_view=None,
            zero_streak=0, budget=budget, discovery_delta=0, novelty_delta=0,
            stop_reason=(
                "every discovery view reached SATURATED_BY_ZERO_NOVELTY"
                if worked_any
                else "every discovery view was already terminal when this "
                     "execution began"
            ),
        )
        _log("complete", orchestration_id=orchestration_id, seed=seed_entity_id,
             discovery_used=ledger.discovery, discovery_budget=budget, novelty_calls=ledger.novelty)

    except _Pause as pause:
        await _update_orchestration(
            session, orchestration_pk, status="PAUSED_BY_BUDGET", current_view=None,
            zero_streak=0, budget=budget, discovery_delta=0, novelty_delta=0,
            stop_reason=str(pause) or "safety budget exhausted",
        )
        _log("budget-pause", orchestration_id=orchestration_id, seed=seed_entity_id,
             discovery_used=ledger.discovery, discovery_budget=budget)

    except _Blocked as blocked:
        # The VIEW the failure happened in is marked too. Leaving it RUNNING
        # would record an orchestration that is BLOCKED inside a View that
        # claims to be working — and a reader would have to guess which View the
        # resume is about.
        await _mark_view_blocked(
            session, orchestration_pk, orchestration_id, active_view, blocked.reason
        )
        await _update_orchestration(
            session, orchestration_pk, status="BLOCKED", current_view=None,
            zero_streak=0, budget=budget, discovery_delta=0, novelty_delta=0,
            stop_reason=blocked.reason,
        )
        _log("blocked", orchestration_id=orchestration_id, seed=seed_entity_id,
             reason=blocked.reason)

    except Exception as exc:  # noqa: BLE001 — an unexpected failure must BLOCK, not vanish
        await session.rollback()
        # The same View marking as the typed branch: a failure that was not
        # wrapped still blocked THIS View, and a reader must not have to infer
        # which one from timestamps.
        await _mark_view_blocked(
            session, orchestration_pk, orchestration_id, active_view,
            f"{type(exc).__name__}: {exc}",
        )
        await _update_orchestration(
            session, orchestration_pk, status="BLOCKED", current_view=None,
            zero_streak=0, budget=budget, discovery_delta=0, novelty_delta=0,
            stop_reason=f"{type(exc).__name__}: {exc}",
        )
        _log("blocked", orchestration_id=orchestration_id, seed=seed_entity_id,
             reason=f"{type(exc).__name__}: {exc}")

    # The per-execution ledger is written ONCE, here, so a mid-loop accounting
    # mistake cannot lose calls that were really spent.
    await _add_execution_usage(session, orchestration_pk, ledger.discovery, ledger.novelty)
    return await _read(session, orchestration_id)


async def _run_view(
    session: AsyncSession, *, orchestration_pk: int, orchestration_id: str,
    seed_entity_id: str, view: str, state: Any, budget: int, ledger: _Ledger,
) -> None:
    """Work one View until it saturates or the budget runs out."""
    strategy = strategy_identifier(view)
    zero_streak = int(state["zero_streak"])
    latest_run_pk = state["latest_successful_run_pk"]
    latest_assessment_pk = state["latest_novelty_assessment_pk"]
    failures = int(state["failed_attempt_count"])

    await session.execute(_UPDATE_VIEW_SQL, {
        "orchestration_pk": orchestration_pk, "discovery_view": view,
        "status": "RUNNING", "terminal": False, "zero_streak": zero_streak,
        "latest_run_pk": latest_run_pk, "latest_assessment_pk": latest_assessment_pk,
        "failed_delta": 0,
        "semantic_new_count": state["semantic_new_count"], "stop_reason": state["stop_reason"],
    })
    await _update_orchestration(
        session, orchestration_pk, status="RUNNING", current_view=view,
        zero_streak=zero_streak, budget=budget, discovery_delta=0, novelty_delta=0,
        stop_reason=None,
    )
    _log("view", orchestration_id=orchestration_id, seed=seed_entity_id, view=view,
         zero_streak=zero_streak)

    # ---- bootstrap: attach to history that already exists -------------------
    latest = await _latest_run(
        session, seed_entity_id=seed_entity_id, strategy=strategy)

    if latest is None:
        # No history at all: this View starts at Round 1.
        run_id, assess = await _one_discovery_round(
            session, orchestration_pk=orchestration_pk,
            orchestration_id=orchestration_id, seed_entity_id=seed_entity_id,
            view=view, continuation_from=None, budget=budget, ledger=ledger,
        )
    else:
        run_id = latest["run_id"]
        assess = await _assess_run(
            session, orchestration_id=orchestration_id, seed_entity_id=seed_entity_id,
            view=view, run_id=run_id, ledger=ledger,
        )

    latest_run_pk = await _run_pk(session, run_id)

    # Record the attachment IMMEDIATELY, not only when the View pauses or
    # saturates. A View that blocks mid-bootstrap would otherwise leave a row
    # naming no run at all — and "which run was this View working from" is
    # exactly the question a resume has to answer.
    await session.execute(_UPDATE_VIEW_SQL, {
        "orchestration_pk": orchestration_pk, "discovery_view": view,
        "status": "RUNNING", "terminal": False, "zero_streak": zero_streak,
        "latest_run_pk": latest_run_pk, "latest_assessment_pk": assess.assessment_pk,
        "failed_delta": 0, "semantic_new_count": assess.semantic_new_count,
        "stop_reason": None,
    })
    await session.commit()

    while True:
        semantic_new = assess.semantic_new_count
        if semantic_new > 0:
            zero_streak = 0
            _log("continue", orchestration_id=orchestration_id, seed=seed_entity_id,
                 view=view, run_id=run_id, semantic_new_count=semantic_new,
                 zero_streak=zero_streak, discovery_used=ledger.discovery, discovery_budget=budget)
        else:
            zero_streak += 1
            _log("zero", orchestration_id=orchestration_id, seed=seed_entity_id,
                 view=view, run_id=run_id, semantic_new_count=0,
                 zero_streak=zero_streak, discovery_used=ledger.discovery, discovery_budget=budget)
            if zero_streak >= ZERO_STREAK_TO_SATURATE:
                await session.execute(_UPDATE_VIEW_SQL, {
                    "orchestration_pk": orchestration_pk, "discovery_view": view,
                    "status": "SATURATED_BY_ZERO_NOVELTY", "terminal": True,
                    "zero_streak": zero_streak,
                    "latest_run_pk": latest_run_pk,
                    "latest_assessment_pk": assess.assessment_pk,
                    "failed_delta": 0, "semantic_new_count": 0,
                    "stop_reason": (
                        f"{zero_streak} consecutive successful rounds produced no "
                        f"semantic novelty"
                    ),
                })
                await session.execute(text(
                    "UPDATE discovery_orchestrations SET zero_streak = 0 WHERE orchestration_pk = :pk"
                ), {"pk": orchestration_pk})
                await session.commit()
                _log("view-saturated", orchestration_id=orchestration_id,
                     seed=seed_entity_id, view=view, zero_streak=zero_streak)
                return ledger.discovery, ledger.novelty

        # Another round is needed — a continuation of the run just judged.
        if ledger.discovery >= budget:
            await session.execute(_UPDATE_VIEW_SQL, {
                "orchestration_pk": orchestration_pk, "discovery_view": view,
                "status": "RUNNING", "terminal": False, "zero_streak": zero_streak,
                "latest_run_pk": latest_run_pk,
                "latest_assessment_pk": assess.assessment_pk,
                "failed_delta": 0, "semantic_new_count": semantic_new,
                "stop_reason": None,
            })
            await session.commit()
            raise _Pause(
                f"safety budget of {budget} new discovery call(s) exhausted while "
                f"view {view} still produced novelty"
            )

        run_id, assess = await _one_discovery_round(
            session, orchestration_pk=orchestration_pk,
            orchestration_id=orchestration_id, seed_entity_id=seed_entity_id,
            view=view, continuation_from=run_id, budget=budget, ledger=ledger,
        )
        latest_run_pk = await _run_pk(session, run_id)


async def _one_discovery_round(
    session: AsyncSession, *, orchestration_pk: int, orchestration_id: str,
    seed_entity_id: str, view: str, continuation_from: str | None, budget: int,
    ledger: _Ledger,
) -> tuple[str, _Assessment]:
    """Execute ONE Discovery round and assess it.

    The call is counted BEFORE it is made: a call that fails still cost the
    provider, and under-reporting cost is worse than an unflattering number.
    """
    ledger.discovery += 1
    if ledger.discovery > budget:
        ledger.discovery -= 1
        raise _Pause(f"safety budget of {budget} new discovery call(s) exhausted")

    from app.services import llm_discovery_execution_service as execution

    try:
        result = await execution.execute_llm_discovery(
            session, entity_id=seed_entity_id, discovery_view=view,
            continuation_from_run_id=continuation_from,
        )
    except Exception as exc:  # noqa: BLE001 — a failed round is NOT a zero
        await session.rollback()
        _log("blocked", orchestration_id=orchestration_id, seed=seed_entity_id,
             view=view, reason=f"discovery failed: {type(exc).__name__}")
        raise _Blocked(
            f"discovery failed for view {view}: {type(exc).__name__}: {exc}"
        ) from None

    run_id = result.run.run_id
    _log("discovery", orchestration_id=orchestration_id, seed=seed_entity_id,
         view=view, run_id=run_id, discovery_used=ledger.discovery, discovery_budget=budget)

    # SETTLE THE COUNTER HERE — after the run is COMPLETED and BEFORE the
    # assessment. The round succeeded; whether the assessor later agrees is a
    # different question, and a failed assessment must not erase a completed
    # round. Waiting until the View pauses is what lost R6.
    run_pk = await _run_pk(session, run_id)
    await session.execute(_COUNT_SUCCESSFUL_ROUND_SQL, {
        "orchestration_pk": orchestration_pk, "discovery_view": view, "run_pk": run_pk,
    })
    await session.commit()

    assess = await _assess_run(
        session, orchestration_id=orchestration_id, seed_entity_id=seed_entity_id,
        view=view, run_id=run_id, ledger=ledger,
    )
    return run_id, assess


async def _assess_run(
    session: AsyncSession, *, orchestration_id: str, seed_entity_id: str, view: str,
    run_id: str, ledger: _Ledger,
) -> _Assessment:
    """The durable novelty judgement for one run, and what it cost.

    An existing assessment is reused and costs nothing. A View with no prior art
    at all is judged deterministically and also costs nothing — see
    ``novelty.EMPTY_POOL_ASSESSOR``. Only a genuine model judgement is charged.
    """
    scope = await novelty.resolve_assessable_run(session, run_id=run_id)
    prior = await novelty.collect_prior_circuits(session, scope=scope)
    target = await novelty.collect_target_circuits(session, scope=scope)
    identity = novelty.identity_for(prior, target)

    existing = await novelty.existing_assessment_id(session, scope=scope, identity=identity)
    if existing is not None:
        summary = await get_novelty_summary(session, assessment_id=existing)
        pk = (await session.execute(
            _ASSESSMENT_PK_SQL, {"assessment_id": existing})).scalars().one()
        _log("novelty", orchestration_id=orchestration_id, seed=seed_entity_id,
             view=view, run_id=run_id, semantic_new_count=summary.semantic_new_count,
             note="reused")
        return _Assessment(assessment_pk=pk,
                           semantic_new_count=summary.semantic_new_count,
                           provider_calls=0)

    charged = 0 if identity is novelty.EMPTY_POOL_ASSESSOR else 1
    ledger.novelty += charged

    try:
        result = await novelty.assess_and_persist_circuit_novelty(session, run_id=run_id)
    except Exception as exc:  # noqa: BLE001 — a failed assessment is NOT a zero
        await session.rollback()
        _log("blocked", orchestration_id=orchestration_id, seed=seed_entity_id,
             view=view, run_id=run_id, reason=f"assessment failed: {type(exc).__name__}")
        raise _Blocked(
            f"novelty assessment failed for run {run_id}: {type(exc).__name__}: {exc}"
        ) from None

    pk = (await session.execute(
        _ASSESSMENT_PK_SQL, {"assessment_id": result.assessment_id})).scalars().one()
    _log("novelty", orchestration_id=orchestration_id, seed=seed_entity_id,
         view=view, run_id=run_id, semantic_new_count=result.semantic_new_count,
         provider_calls=charged)
    return _Assessment(assessment_pk=pk,
                       semantic_new_count=result.semantic_new_count,
                       provider_calls=charged)


# ===========================================================================
# database helpers
# ===========================================================================
async def _latest_run(session: AsyncSession, *, seed_entity_id: str, strategy: str):
    return (await session.execute(text(
        """
        SELECT r.run_pk, r.run_id
        FROM knowledge_discovery_runs r
        JOIN brain_regions b ON b.entity_pk = r.seed_region_pk
        JOIN kg_entities e ON e.entity_pk = b.entity_pk
        WHERE e.entity_id = :entity_id
          AND r.discovery_type = 'LLM_DISCOVERY'
          AND r.status = 'COMPLETED'
          AND r.query_strategy_version = :strategy
        ORDER BY r.created_at DESC, r.run_pk DESC
        LIMIT 1
        """), {"entity_id": seed_entity_id, "strategy": strategy})).mappings().first()


async def _run_pk(session: AsyncSession, run_id: str) -> int:
    return int((await session.execute(
        text("SELECT run_pk FROM knowledge_discovery_runs WHERE run_id = :r"),
        {"r": run_id})).scalars().one())


async def _update_orchestration(
    session: AsyncSession, orchestration_pk: int, *, status: str, current_view: str | None,
    zero_streak: int, budget: int, discovery_delta: int, novelty_delta: int,
    stop_reason: str | None,
) -> None:
    await session.execute(_UPDATE_ORCH_SQL, {
        "orchestration_pk": orchestration_pk, "status": status,
        "terminal": status == "COMPLETED",
        "current_view": current_view, "zero_streak": zero_streak, "budget": budget,
        "discovery_delta": discovery_delta, "novelty_delta": novelty_delta,
        "stop_reason": stop_reason,
    })
    await session.commit()


async def _mark_view_blocked(
    session: AsyncSession, orchestration_pk: int, orchestration_id: str,
    view: str | None, reason: str,
) -> None:
    """Record WHICH View the orchestration blocked in."""
    if not view:
        return
    await session.execute(text(
        "UPDATE discovery_orchestration_view_states"
        "   SET status = 'BLOCKED', stop_reason = :reason"
        " WHERE orchestration_pk = :pk AND discovery_view = :view"
    ), {"pk": orchestration_pk, "view": view, "reason": reason[:2000]})
    await session.commit()
    _log("blocked", orchestration_id=orchestration_id, view=view, note="view marked")


async def _add_execution_usage(
    session: AsyncSession, orchestration_pk: int, discovery: int, novelty_calls: int
) -> None:
    if discovery or novelty_calls:
        await session.execute(text(
            "UPDATE discovery_orchestrations SET"
            " discovery_calls_used = discovery_calls_used + :d,"
            " novelty_calls_used = novelty_calls_used + :n"
            " WHERE orchestration_pk = :pk"
        ), {"d": discovery, "n": novelty_calls, "pk": orchestration_pk})
        await session.commit()


# ===========================================================================
# read
# ===========================================================================
async def _read(session: AsyncSession, orchestration_id: str) -> OrchestrationRead:
    row = (await session.execute(
        _ORCH_SQL, {"orchestration_id": orchestration_id})).mappings().one()
    views = (await session.execute(
        _VIEW_STATES_SQL, {"orchestration_pk": row["orchestration_pk"]})).mappings().all()
    return OrchestrationRead(
        orchestration_id=str(row["orchestration_id"]),
        seed_entity_id=row["seed_entity_id"],
        strategy_family=row["strategy_family"],
        strategy_version=row["strategy_version"],
        status=row["status"],
        current_view=row["current_view"],
        zero_streak=row["zero_streak"],
        discovery_call_budget=row["discovery_call_budget"],
        discovery_calls_used=row["discovery_calls_used"],
        novelty_calls_used=row["novelty_calls_used"],
        stop_reason=row["stop_reason"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        views=[
            OrchestrationViewStateRead(
                discovery_view=v["discovery_view"], position=v["position"],
                status=v["status"], zero_streak=v["zero_streak"],
                # str(): the driver hands back a UUID object for a uuid column,
                # and the contract promises a string.
                latest_successful_run_id=(
                    str(v["latest_run_id"]) if v["latest_run_id"] else None
                ),
                latest_novelty_assessment_id=(
                    str(v["latest_assessment_id"]) if v["latest_assessment_id"] else None
                ),
                successful_round_count=v["successful_round_count"],
                failed_attempt_count=v["failed_attempt_count"],
                semantic_new_count=v["semantic_new_count"],
                stop_reason=v["stop_reason"], started_at=v["started_at"],
                completed_at=v["completed_at"],
            )
            for v in views
        ],
    )


async def get_orchestration(session: AsyncSession, *, orchestration_id: str) -> OrchestrationRead:
    row = (await session.execute(
        _ORCH_SQL, {"orchestration_id": orchestration_id})).mappings().one_or_none()
    if row is None:
        raise OrchestrationNotFound(orchestration_id)
    return await _read(session, orchestration_id)


async def get_latest_orchestration(
    session: AsyncSession, *, entity_id: str
) -> OrchestrationRead | None:
    """The newest orchestration for a seed, active or completed, or None."""
    seed_pk = (await session.execute(_SEED_SQL, {"entity_id": entity_id})).scalars().first()
    if seed_pk is None:
        raise OrchestrationSeedNotFound(entity_id)
    row = (await session.execute(text(
        "SELECT orchestration_id FROM discovery_orchestrations"
        " WHERE seed_region_pk = :pk ORDER BY created_at DESC, orchestration_pk DESC LIMIT 1"
    ), {"pk": seed_pk})).scalars().first()
    if row is None:
        return None
    return await _read(session, str(row))


__all__ = [
    "VIEW_ORDER",
    "OrchestrationAlreadyRunning",
    "OrchestrationBlocked",
    "OrchestrationError",
    "OrchestrationNotFound",
    "OrchestrationSeedNotFound",
    "get_latest_orchestration",
    "get_orchestration",
    "resume_orchestration",
    "start_orchestration",
]
