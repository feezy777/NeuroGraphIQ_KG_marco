"""High-recall orchestrator — the state machine, on the real database.

What is REAL here: the loop, the zero-streak rule, View switching, the budget,
every orchestration row, every foreign key and the CHECKs that hold the rules
two zeros / non-negative budgets / one active orchestration per seed.

What is STUBBED: exactly two things that are irreducible — the provider call
(``execute_llm_discovery``) and the model judgement (``_assess_run``). Both are
replaced at the boundary, so the tests decide what a round found and what the
assessor concluded, and then assert what the LOOP does about it.

The stub for discovery still creates a REAL completed run: the orchestration
stores foreign keys to runs, so a fake id would test nothing.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable
from unittest.mock import patch

import pytest

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

BACKEND = Path(__file__).resolve().parents[1]
E2E_DB = os.environ.get("TEST_E2E_DB", "neurographiq_human_brain_v1_e2e")


def _dsn() -> str:
    cfg: dict[str, str] = {}
    env = BACKEND / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    return "postgresql+psycopg://%s:%s@%s:%s/%s" % (
        cfg.get("POSTGRES_USER"), cfg.get("POSTGRES_PASSWORD"),
        cfg.get("POSTGRES_HOST", "127.0.0.1"), cfg.get("POSTGRES_PORT", "5432"), E2E_DB)


def _resolve_seed() -> str:
    try:
        import psycopg

        with psycopg.connect(_dsn().replace("+psycopg", "")) as conn:
            row = conn.execute(
                "SELECT entity_id FROM kg_entities"
                " WHERE entity_type = 'brain_region' AND name_en = 'Left Hippocampus'"
                " ORDER BY entity_id LIMIT 1").fetchone()
        return row[0] if row else "NGIQ-BR-00001169"
    except Exception:  # pragma: no cover
        return "NGIQ-BR-00001169"


SEED = _resolve_seed()


def _resolve_empty_seed() -> str:
    """A BrainRegion with NO discovery runs at all.

    The state-machine tests are about a sweep starting from nothing, so they
    need a region whose Views have no history — otherwise the bootstrap
    correctly attaches to the history and never runs Round 1. Tests roll back,
    so the region stays empty.
    """
    try:
        import psycopg

        with psycopg.connect(_dsn().replace("+psycopg", "")) as conn:
            row = conn.execute(
                "SELECT e.entity_id FROM brain_regions b"
                " JOIN kg_entities e ON e.entity_pk = b.entity_pk"
                " WHERE NOT EXISTS (SELECT 1 FROM knowledge_discovery_runs r"
                "                    WHERE r.seed_region_pk = b.entity_pk)"
                " ORDER BY e.entity_id LIMIT 1").fetchone()
        return row[0] if row else SEED
    except Exception:  # pragma: no cover
        return SEED


#: No history: the sweep starts at Round 1 for every View.
EMPTY_SEED = _resolve_empty_seed()


def case(fn: Callable[[Any, Any], Awaitable[None]]):
    def wrapper() -> None:
        asyncio.run(_drive(fn))

    wrapper.__name__ = fn.__name__
    wrapper.__qualname__ = fn.__qualname__
    wrapper.__doc__ = fn.__doc__
    return wrapper


class H:
    """The session plus the tiny read helpers these tests need."""

    def __init__(self, db):
        self.db = db

    async def rows(self, sql: str, **p):
        from sqlalchemy import text

        return list((await self.db.execute(text(sql), p)).mappings().all())

    async def one(self, sql: str, **p):
        rows = await self.rows(sql, **p)
        return rows[0] if rows else None

    async def scalar(self, sql: str, **p):
        from sqlalchemy import text

        return (await self.db.execute(text(sql), p)).scalar_one_or_none()


async def _drive(fn) -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(_dsn(), poolclass=NullPool)
    try:
        connection = await engine.connect()
    except Exception as exc:  # pragma: no cover
        await engine.dispose()
        pytest.skip(f"isolated test database unavailable: {type(exc).__name__}")

    transaction = await connection.begin()
    db = AsyncSession(bind=connection, join_transaction_mode="create_savepoint")
    try:
        if (await connection.execute(text(
                "SELECT to_regclass('public.discovery_orchestrations')"))).scalar_one() is None:
            pytest.skip("gate7b_020 not applied to the isolated test database")
        await fn(H(db), None)
    finally:
        await db.close()
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


# ===========================================================================
# fixtures and stubs
# ===========================================================================
@dataclass
class Round:
    """One stubbed discovery round: its run id and what the assessor concludes."""

    run_id: str
    semantic_new_count: int


class Recorder:
    """Records every stubbed call so "did it spend?" is answerable."""

    def __init__(self, rounds: list[int] | None = None):
        #: semantic_new_count for each successive round, in order.
        self.plan = list(rounds or [])
        self.discovery_calls: list[dict[str, Any]] = []
        self.assessment_calls: list[str] = []
        self._i = 0

    def next_value(self) -> int:
        value = self.plan[self._i] if self._i < len(self.plan) else 0
        self._i += 1
        return value


def _stub_discovery(recorder: Recorder, h: H, seed_entity_id: str):
    """A discovery call that really creates a COMPLETED run, then says what it
    is worth. Returns an object shaped like the real execution result."""

    class _Run:
        def __init__(self, run_id):
            self.run_id = run_id

    class _Result:
        def __init__(self, run_id):
            self.run = _Run(run_id)

    async def _call(session, *, entity_id, discovery_view=None,
                    continuation_from_run_id=None):
        from app.llm_discovery_views import strategy_identifier
        from app.services import knowledge_discovery_run_lifecycle_service as lifecycle

        recorder.discovery_calls.append({
            "view": discovery_view,
            "continuation_from": continuation_from_run_id,
        })
        run = await lifecycle.create_discovery_run(
            session, entity_id=entity_id, discovery_type="LLM_DISCOVERY",
            query_strategy_version=strategy_identifier(discovery_view),
        )
        await lifecycle.start_discovery_run(session, run.run_id)
        await lifecycle.complete_discovery_run(session, run.run_id, "CANDIDATES_FOUND")
        return _Result(run.run_id)

    return _call


def _stub_assessment(recorder: Recorder, h: H):
    """A judgement that returns the planned number and records NOTHING durable.

    The durable-assessment path is covered by its own suite; what is under test
    here is what the loop decides once a number exists.
    """
    from app.services import high_recall_orchestrator_service as orch

    async def _call(session, *, orchestration_id, seed_entity_id, view, run_id,
                    ledger):
        recorder.assessment_calls.append(run_id)
        value = recorder.next_value()
        # No assessment_pk: this stub stores no assessment row, and inventing a
        # key would violate the FK (which is the correct behaviour). The durable
        # path has its own suite.
        return orch._Assessment(assessment_pk=None, semantic_new_count=value,
                                provider_calls=0)

    return _call


async def _orchestrate(h: H, recorder: Recorder, *, budget: int = 10,
                       seed_entity_id: str = EMPTY_SEED):
    """Run one execution of the orchestrator with both boundaries stubbed."""
    from app.services import high_recall_orchestrator_service as orch
    from app.services import llm_discovery_execution_service as execution
    from app.schemas.orchestration import OrchestrationStartRequest

    with patch.object(execution, "execute_llm_discovery",
                      _stub_discovery(recorder, h, seed_entity_id)), \
         patch.object(orch, "_assess_run", _stub_assessment(recorder, h)):
        return await orch.start_orchestration(
            h.db, entity_id=seed_entity_id,
            request=OrchestrationStartRequest(max_new_discovery_calls=budget))


async def _view(h: H, orchestration_id: str, view: str):
    return await h.one(
        "SELECT v.* FROM discovery_orchestration_view_states v"
        " JOIN discovery_orchestrations o ON o.orchestration_pk = v.orchestration_pk"
        " WHERE o.orchestration_id = :o AND v.discovery_view = :v",
        o=orchestration_id, v=view)


# ===========================================================================
# A / I / J / K — what counts as novelty
# ===========================================================================
@case
async def test_A_a_new_seed_starts_round_1_of_the_first_view(h, _):
    rec = Recorder([7])
    result = await _orchestrate(h, rec, budget=1)
    assert len(rec.discovery_calls) == 1
    assert rec.discovery_calls[0]["view"] == "NAMED_CLASSIC_CIRCUITS"
    assert rec.discovery_calls[0]["continuation_from"] is None, "R1 is not a continuation"
    assert result.status == "PAUSED_BY_BUDGET"
    a = await _view(h, result.orchestration_id, "NAMED_CLASSIC_CIRCUITS")
    assert a["successful_round_count"] == 1
    assert a["semantic_new_count"] == 7


@case
async def test_B_novelty_continues_the_same_view(h, _):
    """Non-zero novelty means another round — and a CONTINUATION, not a restart."""
    rec = Recorder([5, 3])
    result = await _orchestrate(h, rec, budget=2)
    assert [c["view"] for c in rec.discovery_calls] == ["NAMED_CLASSIC_CIRCUITS"] * 2
    assert rec.discovery_calls[0]["continuation_from"] is None, "R1 is not a continuation"
    assert rec.discovery_calls[1]["continuation_from"] is not None, (
        "a round after the first continues the run just judged"
    )
    # Two rounds of genuine novelty, then the SAFETY BUDGET stops it — which is
    # a pause, not saturation, and leaves the streak at zero.
    assert result.status == "PAUSED_BY_BUDGET"
    a = await _view(h, result.orchestration_id, "NAMED_CLASSIC_CIRCUITS")
    assert a["zero_streak"] == 0
    assert a["status"] == "RUNNING"
    assert a["successful_round_count"] == 2
    assert result.discovery_calls_used == 2, "the ledger must count what was spent"


@case
async def test_C_the_first_zero_buys_a_confirmation_round(h, _):
    """One zero is a measurement; the loop spends one round asking again."""
    rec = Recorder([0, 4])
    result = await _orchestrate(h, rec, budget=2)
    assert len(rec.discovery_calls) == 2, "a zero must NOT stop the View on its own"
    a = await _view(h, result.orchestration_id, "NAMED_CLASSIC_CIRCUITS")
    assert a["status"] == "RUNNING"
    assert a["zero_streak"] == 0, "the confirmation round found novelty and reset it"


@case
async def test_D_two_consecutive_zeros_saturate_the_view(h, _):
    rec = Recorder([0, 0])
    result = await _orchestrate(h, rec, budget=2)
    a = await _view(h, result.orchestration_id, "NAMED_CLASSIC_CIRCUITS")
    assert a["status"] == "SATURATED_BY_ZERO_NOVELTY"
    assert a["zero_streak"] == 2
    assert result.status != "COMPLETED", "one View saturating is not the sweep finishing"
    b = await _view(h, result.orchestration_id, "LOCAL_INTRINSIC_CIRCUITS")
    assert b["status"] == "RUNNING", "the sweep moved on to B"
    assert b["successful_round_count"] == 0, "and the budget stopped it before B ran"


@case
async def test_E_novelty_after_a_zero_resets_the_streak(h, _):
    """5 → 0 → 3 is NOT saturation: the streak resets and the View continues.

    The third round runs even though A's balancing allocation is 2: a View that
    has just produced its first zero always gets the round that resolves it, so
    a zero is never left dangling across an execution boundary.
    """
    rec = Recorder([5, 0, 3])
    result = await _orchestrate(h, rec, budget=3)
    a = await _view(h, result.orchestration_id, "NAMED_CLASSIC_CIRCUITS")
    assert a["status"] == "RUNNING"
    assert a["zero_streak"] == 0
    assert [c["view"] for c in rec.discovery_calls] == ["NAMED_CLASSIC_CIRCUITS"] * 3
    assert result.status == "PAUSED_BY_BUDGET", "still expanding, so it paused — not saturated"


@case
async def test_I_borderline_counts_as_novelty(h, _):
    """The counting rule lives in the assessor; the loop must not re-interpret it."""
    rec = Recorder([1])
    result = await _orchestrate(h, rec, budget=1)
    a = await _view(h, result.orchestration_id, "NAMED_CLASSIC_CIRCUITS")
    assert a["semantic_new_count"] == 1
    assert result.status == "PAUSED_BY_BUDGET", "novelty > 0 keeps the View alive"


@case
async def test_J_alias_only_does_not_count(h, _):
    rec = Recorder([0, 0])
    result = await _orchestrate(h, rec, budget=2)
    a = await _view(h, result.orchestration_id, "NAMED_CLASSIC_CIRCUITS")
    assert a["status"] == "SATURATED_BY_ZERO_NOVELTY"


@case
async def test_K_reformulation_only_does_not_count(h, _):
    """Same rule, different class: the loop reads ONE number, not a class list."""
    rec = Recorder([0, 0])
    result = await _orchestrate(h, rec, budget=2)
    assert (await _view(h, result.orchestration_id,
                        "NAMED_CLASSIC_CIRCUITS"))["semantic_new_count"] == 0


# ===========================================================================
# H — confidence is not part of any decision
# ===========================================================================
def test_H_no_decision_reads_a_confidence_value():
    """Structural: the orchestration layer never selects a confidence column.

    The check runs on the CODE, not the prose. The module docstring says the
    word "confidence" on purpose — it is explaining why no decision reads one —
    and a substring scan would call that explanation a violation.
    """
    import ast

    source = (BACKEND / "app/services/high_recall_orchestrator_service.py").read_text(
        encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                node.body.pop(0)          # drop the docstring
    code = ast.unparse(tree)               # comments are gone entirely
    assert "confidence" not in code, (
        "the orchestrator must not read a confidence value at all — the surest "
        "way to keep one out of a decision is not to have it"
    )


# ===========================================================================
# F / G — a failure is not a zero
# ===========================================================================
@case
async def test_F_a_failed_discovery_after_a_zero_is_BLOCKED_not_saturated(h, _):
    from app.services import high_recall_orchestrator_service as orch
    from app.services import llm_discovery_execution_service as execution
    from app.schemas.orchestration import OrchestrationStartRequest

    rec = Recorder([0])          # the bootstrap round finds zero
    calls = {"n": 0}

    async def _failing(session, *, entity_id, discovery_view=None,
                       continuation_from_run_id=None):
        calls["n"] += 1
        raise RuntimeError("provider exploded")

    with patch.object(execution, "execute_llm_discovery", _failing), \
         patch.object(orch, "_assess_run", _stub_assessment(rec, h)):
        result = await orch.start_orchestration(
            h.db, entity_id=EMPTY_SEED,
            request=OrchestrationStartRequest(max_new_discovery_calls=5))

    assert calls["n"] == 1
    assert result.status == "BLOCKED"
    assert "provider exploded" in (result.stop_reason or "")
    a = await _view(h, result.orchestration_id, "NAMED_CLASSIC_CIRCUITS")
    assert a["status"] == "BLOCKED"
    assert a["zero_streak"] == 0, "a failure must never advance the zero streak"


@case
async def test_G_a_failed_assessment_after_a_zero_is_BLOCKED_not_saturated(h, _):
    from app.services import high_recall_orchestrator_service as orch
    from app.services import llm_discovery_execution_service as execution
    from app.schemas.orchestration import OrchestrationStartRequest

    rec = Recorder([0])

    async def _failing_assessment(session, **kwargs):
        raise RuntimeError("the model reply did not satisfy the verdict contract")

    with patch.object(execution, "execute_llm_discovery",
                      _stub_discovery(rec, h, SEED)), \
         patch.object(orch, "_assess_run", _failing_assessment):
        result = await orch.start_orchestration(
            h.db, entity_id=EMPTY_SEED,
            request=OrchestrationStartRequest(max_new_discovery_calls=5))

    assert result.status == "BLOCKED"
    a = await _view(h, result.orchestration_id, "NAMED_CLASSIC_CIRCUITS")
    assert a["status"] == "BLOCKED"
    assert a["zero_streak"] == 0


# ===========================================================================
# view order and completion
# ===========================================================================
@case
async def test_view_order_is_A_then_B_then_C_then_D_then_COMPLETED(h, _):
    from app.services import high_recall_orchestrator_service as orch

    rec = Recorder([0, 0, 0, 0, 0, 0, 0, 0])
    result = await _orchestrate(h, rec, budget=10)

    assert result.status == "COMPLETED"
    assert [c["view"] for c in rec.discovery_calls] == [
        "NAMED_CLASSIC_CIRCUITS", "NAMED_CLASSIC_CIRCUITS",
        "LOCAL_INTRINSIC_CIRCUITS", "LOCAL_INTRINSIC_CIRCUITS",
        "AFFERENT_CIRCUITS", "AFFERENT_CIRCUITS",
        "EFFERENT_CIRCUITS", "EFFERENT_CIRCUITS",
    ], "two zero rounds per view, in the frozen order, and no view skipped"
    for view in orch.VIEW_ORDER:
        v = await _view(h, result.orchestration_id, view)
        assert v["status"] == "SATURATED_BY_ZERO_NOVELTY", view
    assert result.stop_reason


# ===========================================================================
# budget and resume
# ===========================================================================
@case
async def test_budget_pauses_and_never_saturates(h, _):
    rec = Recorder([9, 9])
    result = await _orchestrate(h, rec, budget=2)
    assert result.status == "PAUSED_BY_BUDGET"
    a = await _view(h, result.orchestration_id, "NAMED_CLASSIC_CIRCUITS")
    assert a["status"] == "RUNNING", "a budget pause is not a scientific outcome"
    assert a["zero_streak"] == 0


@case
async def test_resume_continues_the_same_view_without_repeating_a_round(h, _):
    from app.services import high_recall_orchestrator_service as orch
    from app.services import llm_discovery_execution_service as execution
    from app.schemas.orchestration import OrchestrationStartRequest

    first = Recorder([9, 9])
    started = await _orchestrate(h, first, budget=2)
    assert started.status == "PAUSED_BY_BUDGET"
    assert len(first.discovery_calls) == 2
    runs_after_first = await h.scalar(
        "SELECT count(*) FROM knowledge_discovery_runs r"
        " JOIN brain_regions b ON b.entity_pk = r.seed_region_pk"
        " JOIN kg_entities e ON e.entity_pk = b.entity_pk WHERE e.entity_id = :s",
        s=EMPTY_SEED)

    # Resume: the SAME orchestration, a fresh allowance, no repeated round.
    second = Recorder([9, 9])
    with patch.object(execution, "execute_llm_discovery",
                      _stub_discovery(second, h, SEED)), \
         patch.object(orch, "_assess_run", _stub_assessment(second, h)):
        resumed = await orch.resume_orchestration(
            h.db, orchestration_id=started.orchestration_id,
            request=OrchestrationStartRequest(max_new_discovery_calls=2))

    assert resumed.orchestration_id == started.orchestration_id, "no second orchestration"
    assert resumed.status == "PAUSED_BY_BUDGET"
    assert len(second.discovery_calls) == 2, "a fresh allowance, not zero"
    runs_after_resume = await h.scalar(
        "SELECT count(*) FROM knowledge_discovery_runs r"
        " JOIN brain_regions b ON b.entity_pk = r.seed_region_pk"
        " JOIN kg_entities e ON e.entity_pk = b.entity_pk WHERE e.entity_id = :s",
        s=EMPTY_SEED)
    assert runs_after_resume == runs_after_first + 2
    # continuity: the resumed rounds CONTINUE the last one, they do not restart
    assert second.discovery_calls[0]["continuation_from"] is not None
    assert second.discovery_calls[0]["view"] == "NAMED_CLASSIC_CIRCUITS"


@case
async def test_a_second_start_does_not_create_a_parallel_orchestration(h, _):
    from app.services import high_recall_orchestrator_service as orch

    rec = Recorder([9, 9])
    started = await _orchestrate(h, rec, budget=2)
    assert started.status == "PAUSED_BY_BUDGET"

    rec2 = Recorder([9, 9])
    again = await _orchestrate(h, rec2, budget=2)
    assert again.orchestration_id == started.orchestration_id
    assert await h.scalar(
        "SELECT count(*) FROM discovery_orchestrations o"
        " JOIN brain_regions b ON b.entity_pk = o.seed_region_pk"
        " JOIN kg_entities e ON e.entity_pk = b.entity_pk WHERE e.entity_id = :s",
        s=EMPTY_SEED) == 1, "one seed, one orchestration"


@case
async def test_a_start_while_RUNNING_is_refused(h, _):
    """The database is the real guard; this is the service-level one."""
    from app.services import high_recall_orchestrator_service as orch
    from app.schemas.orchestration import OrchestrationStartRequest

    created = await _orchestrate(h, Recorder([1]), budget=1)
    # No stubs below: this test must REFUSE before reaching the loop. If the
    # refusal ever stops working, the assertion below fails rather than quietly
    # spending provider calls — the seed must therefore match the one
    # _orchestrate used, or there would be no active orchestration to find.
    await h.db.execute(__import__("sqlalchemy").text(
        "UPDATE discovery_orchestrations SET status = 'RUNNING'"
        " WHERE orchestration_id = :o"), {"o": created.orchestration_id})
    await h.db.flush()

    with pytest.raises(orch.OrchestrationAlreadyRunning):
        await orch.start_orchestration(
            h.db, entity_id=EMPTY_SEED,
            request=OrchestrationStartRequest(max_new_discovery_calls=1))


@case
async def test_a_BLOCKED_orchestration_refuses_a_plain_start(h, _):
    from app.services import high_recall_orchestrator_service as orch
    from app.schemas.orchestration import OrchestrationStartRequest

    created = await _orchestrate(h, Recorder([1]), budget=1)
    await h.db.execute(__import__("sqlalchemy").text(
        "UPDATE discovery_orchestrations SET status = 'BLOCKED', stop_reason = 'x'"
        " WHERE orchestration_id = :o"), {"o": created.orchestration_id})
    await h.db.flush()

    with pytest.raises(orch.OrchestrationBlocked):
        await orch.start_orchestration(
            h.db, entity_id=EMPTY_SEED,
            request=OrchestrationStartRequest(max_new_discovery_calls=1))


# ===========================================================================
# existing history bootstrap
# ===========================================================================
@case
async def test_existing_history_is_picked_up_from_the_LATEST_run_not_R1(h, _):
    """The critical bootstrap rule: attach to history, never restart it."""
    from app.llm_discovery_views import strategy_identifier
    from app.services import knowledge_discovery_run_lifecycle_service as lifecycle
    from app.services import high_recall_orchestrator_service as orch
    from app.services import llm_discovery_execution_service as execution
    from app.schemas.orchestration import OrchestrationStartRequest

    view = "NAMED_CLASSIC_CIRCUITS"
    ids = []
    for _ in range(3):
        run = await lifecycle.create_discovery_run(
            h.db, entity_id=SEED, discovery_type="LLM_DISCOVERY",
            query_strategy_version=strategy_identifier(view))
        await lifecycle.start_discovery_run(h.db, run.run_id)
        await lifecycle.complete_discovery_run(h.db, run.run_id, "CANDIDATES_FOUND")
        ids.append(run.run_id)

    rec = Recorder([4])
    assessed: list[str] = []

    async def _assess(session, *, orchestration_id, seed_entity_id, view, run_id,
                      ledger):
        assessed.append(run_id)
        return orch._Assessment(assessment_pk=None, semantic_new_count=4,
                                provider_calls=0)

    discovery_calls = {"n": 0}

    async def _must_not_run(*a, **k):
        discovery_calls["n"] += 1
        raise AssertionError("the bootstrap must not execute a new discovery round")

    with patch.object(execution, "execute_llm_discovery", _must_not_run), \
         patch.object(orch, "_assess_run", _assess):
        result = await orch.start_orchestration(
            h.db, entity_id=SEED,
            request=OrchestrationStartRequest(max_new_discovery_calls=1))

    # str(): the driver hands back UUID objects for uuid columns.
    assert assessed and str(assessed[0]) == ids[-1], (
        "the first control action must assess the LATEST completed run, never R1"
    )
    assert discovery_calls["n"] == 1, "only the round the novelty bought"
    a = await _view(h, result.orchestration_id, view)
    # The View is ATTACHED to a run, which is what "bootstrapped from history"
    # means: a View that had restarted at Round 1 would have none yet. The
    # identity of that run is already pinned by `assessed[0]` above; this only
    # asserts the attachment was persisted.
    assert a["latest_successful_run_pk"] is not None


@case
async def test_a_view_with_history_is_not_restarted_when_the_sweep_reaches_it(h, _):
    """B already has rounds: the sweep continues B, it does not start B R1."""
    from app.llm_discovery_views import strategy_identifier
    from app.services import knowledge_discovery_run_lifecycle_service as lifecycle
    from app.services import high_recall_orchestrator_service as orch
    from app.services import llm_discovery_execution_service as execution
    from app.schemas.orchestration import OrchestrationStartRequest

    b_run = await lifecycle.create_discovery_run(
        h.db, entity_id=SEED, discovery_type="LLM_DISCOVERY",
        query_strategy_version=strategy_identifier("LOCAL_INTRINSIC_CIRCUITS"))
    await lifecycle.start_discovery_run(h.db, b_run.run_id)
    await lifecycle.complete_discovery_run(h.db, b_run.run_id, "CANDIDATES_FOUND")

    # A saturates immediately (two zeros); B is then entered with history.
    rec = Recorder([0, 0, 0])
    assessed: list[tuple[str, str]] = []

    async def _assess(session, *, orchestration_id, seed_entity_id, view, run_id,
                      ledger):
        assessed.append((view, run_id))
        return orch._Assessment(assessment_pk=None, semantic_new_count=0,
                                provider_calls=0)

    with patch.object(execution, "execute_llm_discovery",
                      _stub_discovery(rec, h, SEED)), \
         patch.object(orch, "_assess_run", _assess):
        result = await orch.start_orchestration(
            h.db, entity_id=SEED,
            request=OrchestrationStartRequest(max_new_discovery_calls=4))

    b_assessments = [str(r) for v, r in assessed if v == "LOCAL_INTRINSIC_CIRCUITS"]
    assert b_run.run_id in b_assessments, (
        "entering B must assess its existing latest run, not start a new one"
    )
    assert b_assessments[0] == b_run.run_id, "and it must be the FIRST B action"


# ===========================================================================
# the storage layer holds the rules
# ===========================================================================
@case
async def test_the_database_refuses_saturation_without_two_zeros(h, _):
    from sqlalchemy import text

    from app.services import high_recall_orchestrator_service as orch
    from app.schemas.orchestration import OrchestrationStartRequest

    created = await _orchestrate(h, Recorder([1]), budget=1)
    with pytest.raises(Exception) as exc:
        await h.db.execute(text(
            "UPDATE discovery_orchestration_view_states"
            " SET status = 'SATURATED_BY_ZERO_NOVELTY', zero_streak = 1,"
            "     stop_reason = 'x'"
            " WHERE orchestration_pk = (SELECT orchestration_pk"
            "   FROM discovery_orchestrations WHERE orchestration_id = :o)"
            "   AND discovery_view = 'NAMED_CLASSIC_CIRCUITS'"),
            {"o": created.orchestration_id})
    assert "ck_dcovs_saturated_requires_streak" in str(exc.value)


@case
async def test_the_database_refuses_a_budget_outside_the_envelope(h, _):
    from sqlalchemy import text

    created = await _orchestrate(h, Recorder([1]), budget=1)
    with pytest.raises(Exception) as exc:
        await h.db.execute(text(
            "UPDATE discovery_orchestrations SET discovery_call_budget = 999"
            " WHERE orchestration_id = :o"), {"o": created.orchestration_id})
    assert "ck_dco_budget_range" in str(exc.value)


@case
async def test_the_database_allows_only_one_ACTIVE_orchestration_per_seed(h, _):
    from sqlalchemy import text

    await _orchestrate(h, Recorder([1]), budget=1)
    with pytest.raises(Exception) as exc:
        await h.db.execute(text(
            "INSERT INTO discovery_orchestrations"
            " (seed_region_pk, strategy_family, strategy_version, status,"
            "  discovery_call_budget)"
            " SELECT seed_region_pk, 'G4_HIGH_RECALL_V1', 'G4HR1', 'RUNNING', 5"
            "   FROM discovery_orchestrations LIMIT 1"))
        await h.db.flush()
    assert "uq_dco_one_active_per_seed" in str(exc.value) or "duplicate" in str(exc.value).lower()


# ===========================================================================
# successful_round_count — one writer, one boundary, exactly once
# ===========================================================================
# The counter means: NEW Discovery runs THIS orchestration successfully
# COMPLETED for THIS View. It is settled the moment a run completes, not when
# the View happens to pause — a View that BLOCKS with completed rounds must not
# lose them, which is exactly how CA3 lost R6.
async def _count(h: H, orchestration_id: str, view: str = "NAMED_CLASSIC_CIRCUITS") -> int:
    row = await h.one(
        "SELECT v.successful_round_count AS n"
        "  FROM discovery_orchestration_view_states v"
        "  JOIN discovery_orchestrations o ON o.orchestration_pk = v.orchestration_pk"
        " WHERE o.orchestration_id = :o AND v.discovery_view = :v",
        o=orchestration_id, v=view)
    return int(row["n"])


async def _historical_runs(h: H, count: int, *, view: str = "NAMED_CLASSIC_CIRCUITS"):
    """Pre-existing COMPLETED history the orchestration did not create."""
    from app.llm_discovery_views import strategy_identifier
    from app.services import knowledge_discovery_run_lifecycle_service as lifecycle

    ids = []
    for _ in range(count):
        run = await lifecycle.create_discovery_run(
            h.db, entity_id=EMPTY_SEED, discovery_type="LLM_DISCOVERY",
            query_strategy_version=strategy_identifier(view))
        await lifecycle.start_discovery_run(h.db, run.run_id)
        await lifecycle.complete_discovery_run(h.db, run.run_id, "CANDIDATES_FOUND")
        ids.append(run.run_id)
    return ids


# --- A / B ------------------------------------------------------------------
@case
async def test_counter_A_bootstrap_from_history_does_NOT_count_those_runs(h, _):
    """Five historical rounds + exactly one new round must read 1, not 6 and not
    2: attaching to a run is not creating one."""
    history = await _historical_runs(h, 5)

    rec = Recorder([4])
    result = await _orchestrate(h, rec, budget=1)

    assert await _count(h, result.orchestration_id) == 1, (
        "one NEW round was created; the five historical rounds were only attached"
    )
    # The View IS attached to a run — the point is that attaching did not count.
    a = await _view(h, result.orchestration_id, "NAMED_CLASSIC_CIRCUITS")
    assert a["latest_successful_run_pk"] is not None
    assert len(history) == 5, "and the attached history is real and untouched"


@case
async def test_counter_B_one_new_successful_round_counts_exactly_one(h, _):
    rec = Recorder([4])
    result = await _orchestrate(h, rec, budget=1)
    assert len(rec.discovery_calls) == 1
    assert await _count(h, result.orchestration_id) == 1


# --- C / D ------------------------------------------------------------------
@case
async def test_counter_C_a_successful_novelty_does_not_change_the_count(h, _):
    """The round is counted once — the assessment does not add to it."""
    rec = Recorder([4])
    result = await _orchestrate(h, rec, budget=1)
    assert len(rec.assessment_calls) == 1, "the round WAS assessed"
    assert await _count(h, result.orchestration_id) == 1


@case
async def test_counter_D_a_FAILED_novelty_does_not_erase_the_completed_round(h, _):
    """Discovery succeeded, so the round counts even though the judgement died."""
    from app.services import high_recall_orchestrator_service as orch
    from app.services import llm_discovery_execution_service as execution
    from app.schemas.orchestration import OrchestrationStartRequest

    rec = Recorder([0])

    async def _failing_assessment(session, **kwargs):
        raise RuntimeError("the model reply did not satisfy the verdict contract")

    with patch.object(execution, "execute_llm_discovery",
                      _stub_discovery(rec, h, EMPTY_SEED)), \
         patch.object(orch, "_assess_run", _failing_assessment):
        result = await orch.start_orchestration(
            h.db, entity_id=EMPTY_SEED,
            request=OrchestrationStartRequest(max_new_discovery_calls=1))

    assert result.status == "BLOCKED"
    assert await _count(h, result.orchestration_id) == 1, (
        "a completed Discovery round counts whether or not its assessment worked"
    )
    assert (await _view(h, result.orchestration_id,
                        "NAMED_CLASSIC_CIRCUITS"))["status"] == "BLOCKED"


@case
async def test_counter_D2_a_failed_Novelty_after_an_earlier_SATURATING_round(h, _):
    """The counter is not a function of the zero streak."""
    from app.services import high_recall_orchestrator_service as orch
    from app.services import llm_discovery_execution_service as execution
    from app.schemas.orchestration import OrchestrationStartRequest

    rec = Recorder([0])
    calls = {"n": 0}

    async def _assessment(session, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return orch._Assessment(assessment_pk=None, semantic_new_count=5,
                                    provider_calls=0)
        raise RuntimeError("boom")

    with patch.object(execution, "execute_llm_discovery",
                      _stub_discovery(rec, h, EMPTY_SEED)), \
         patch.object(orch, "_assess_run", _assessment):
        result = await orch.start_orchestration(
            h.db, entity_id=EMPTY_SEED,
            request=OrchestrationStartRequest(max_new_discovery_calls=2))

    assert result.status == "BLOCKED"
    assert await _count(h, result.orchestration_id) == 2, (
        "two rounds completed before the assessment failed; both count"
    )


# --- E ----------------------------------------------------------------------
@case
async def test_counter_E_a_failed_Discovery_contributes_zero(h, _):
    from app.services import high_recall_orchestrator_service as orch
    from app.services import llm_discovery_execution_service as execution
    from app.schemas.orchestration import OrchestrationStartRequest

    rec = Recorder([5])

    async def _failing(session, **kw):
        raise RuntimeError("provider exploded")

    with patch.object(execution, "execute_llm_discovery", _failing), \
         patch.object(orch, "_assess_run", _stub_assessment(rec, h)):
        result = await orch.start_orchestration(
            h.db, entity_id=EMPTY_SEED,
            request=OrchestrationStartRequest(max_new_discovery_calls=1))

    assert result.status == "BLOCKED"
    assert await _count(h, result.orchestration_id) == 0


# --- F / G ------------------------------------------------------------------
@case
async def test_counter_F_a_successful_round_survives_a_budget_pause(h, _):
    rec = Recorder([9, 9])
    result = await _orchestrate(h, rec, budget=2)
    assert result.status == "PAUSED_BY_BUDGET"
    assert await _count(h, result.orchestration_id) == 2


@case
async def test_counter_G_a_successful_round_survives_a_later_BLOCK(h, _):
    """The exact CA3 shape: rounds complete, then something fails later."""
    from app.services import high_recall_orchestrator_service as orch
    from app.services import llm_discovery_execution_service as execution
    from app.schemas.orchestration import OrchestrationStartRequest

    rec = Recorder([5, 5])
    real = _stub_discovery(rec, h, EMPTY_SEED)

    async def _succeed_then_fail(session, **kw):
        # The recorder appends INSIDE the real stub, so by the second call the
        # recorded length is 1 — the first round.
        if len(rec.discovery_calls) >= 1:
            raise RuntimeError("second round exploded")
        return await real(session, **kw)

    with patch.object(execution, "execute_llm_discovery", _succeed_then_fail), \
         patch.object(orch, "_assess_run", _stub_assessment(rec, h)):
        result = await orch.start_orchestration(
            h.db, entity_id=EMPTY_SEED,
            request=OrchestrationStartRequest(max_new_discovery_calls=5))

    assert result.status == "BLOCKED"
    assert await _count(h, result.orchestration_id) == 1, (
        "the first round COMPLETED and must still be counted after the second failed"
    )


# --- H / I / J --------------------------------------------------------------
@case
async def test_counter_H_resume_does_not_recount_a_previous_success(h, _):
    first = Recorder([9])
    started = await _orchestrate(h, first, budget=1)
    assert await _count(h, started.orchestration_id) == 1

    # A resume whose own allowance is spent immediately still must not touch the
    # round that already counted.
    from app.services import high_recall_orchestrator_service as orch
    from app.services import llm_discovery_execution_service as execution
    from app.schemas.orchestration import OrchestrationStartRequest

    rec2 = Recorder([9])
    with patch.object(execution, "execute_llm_discovery",
                      _stub_discovery(rec2, h, EMPTY_SEED)), \
         patch.object(orch, "_assess_run", _stub_assessment(rec2, h)):
        await orch.resume_orchestration(
            h.db, orchestration_id=started.orchestration_id,
            request=OrchestrationStartRequest(max_new_discovery_calls=1))

    assert await _count(h, started.orchestration_id) == 2, (
        "exactly one more round: the resumed round counts, the earlier one is not recounted"
    )


@case
async def test_counter_I_resume_increments_by_exactly_one(h, _):
    from app.services import high_recall_orchestrator_service as orch
    from app.services import llm_discovery_execution_service as execution
    from app.schemas.orchestration import OrchestrationStartRequest

    first = Recorder([9, 9])
    started = await _orchestrate(h, first, budget=2)
    before = await _count(h, started.orchestration_id)
    assert before == 2

    rec2 = Recorder([9])
    with patch.object(execution, "execute_llm_discovery",
                      _stub_discovery(rec2, h, EMPTY_SEED)), \
         patch.object(orch, "_assess_run", _stub_assessment(rec2, h)):
        await orch.resume_orchestration(
            h.db, orchestration_id=started.orchestration_id,
            request=OrchestrationStartRequest(max_new_discovery_calls=1))

    assert len(rec2.discovery_calls) == 1, "one new round was created"
    assert await _count(h, started.orchestration_id) == before + 1


@case
async def test_counter_J_a_failed_attempt_between_two_successes_contributes_zero(h, _):
    from app.services import high_recall_orchestrator_service as orch
    from app.services import llm_discovery_execution_service as execution
    from app.schemas.orchestration import OrchestrationStartRequest

    rec = Recorder([5, 5, 5])
    real = _stub_discovery(rec, h, EMPTY_SEED)

    async def _fail_on_second(session, **kw):
        if len(rec.discovery_calls) == 1:
            raise RuntimeError("the middle attempt failed")
        return await real(session, **kw)

    # Round 1 succeeds, the continuation FAILS -> BLOCKED with count 1.
    with patch.object(execution, "execute_llm_discovery", _fail_on_second), \
         patch.object(orch, "_assess_run", _stub_assessment(rec, h)):
        blocked = await orch.start_orchestration(
            h.db, entity_id=EMPTY_SEED,
            request=OrchestrationStartRequest(max_new_discovery_calls=5))
    assert blocked.status == "BLOCKED"
    assert await _count(h, blocked.orchestration_id) == 1

    # Resume: one more success -> exactly 2. The failure contributed nothing.
    rec2 = Recorder([5])
    with patch.object(execution, "execute_llm_discovery",
                      _stub_discovery(rec2, h, EMPTY_SEED)), \
         patch.object(orch, "_assess_run", _stub_assessment(rec2, h)):
        await orch.resume_orchestration(
            h.db, orchestration_id=blocked.orchestration_id,
            request=OrchestrationStartRequest(max_new_discovery_calls=1))
    assert await _count(h, blocked.orchestration_id) == 2


# --- K / L ------------------------------------------------------------------
@case
async def test_counter_K_a_view_switch_does_not_modify_the_finished_view(h, _):
    """A saturates, then B works: A's count is frozen at what A did."""
    rec = Recorder([0, 0, 9, 9])
    result = await _orchestrate(h, rec, budget=4)

    a = await _count(h, result.orchestration_id, "NAMED_CLASSIC_CIRCUITS")
    assert a == 2, "A created exactly its two saturating rounds"
    assert (await _view(h, result.orchestration_id,
                        "NAMED_CLASSIC_CIRCUITS"))["status"] == "SATURATED_BY_ZERO_NOVELTY"
    assert await _count(h, result.orchestration_id,
                        "LOCAL_INTRINSIC_CIRCUITS") == 2


@case
async def test_counter_L_the_four_views_keep_independent_counters(h, _):
    rec = Recorder([0, 0, 0, 0, 0, 0, 0, 0])
    result = await _orchestrate(h, rec, budget=10)
    assert result.status == "COMPLETED"
    for view in ("NAMED_CLASSIC_CIRCUITS", "LOCAL_INTRINSIC_CIRCUITS",
                 "AFFERENT_CIRCUITS", "EFFERENT_CIRCUITS"):
        assert await _count(h, result.orchestration_id, view) == 2, view


# --- the counter has exactly one writer -------------------------------------
def test_counter_has_a_single_writer_and_an_exactly_once_guard():
    """Structural: one statement increments the counter, and it is guarded by the
    row's own latest_successful_run_pk — so the same run cannot be counted twice
    no matter how many times that statement is issued."""
    source = (BACKEND / "app/services/high_recall_orchestrator_service.py").read_text(
        encoding="utf-8")
    assert source.count("successful_round_count = successful_round_count + 1") == 1, (
        "exactly one statement may move the counter"
    )
    assert "latest_successful_run_pk IS DISTINCT FROM :run_pk" in source
    assert "round_delta" not in source, (
        "the counter must no longer be settled from a local tally at pause time"
    )


# ===========================================================================
# Bounded automatic retry for LLM_EMPTY_RESPONSE
# ===========================================================================
# These run the REAL discovery execution service and patch only the PROVIDER, so
# the failed attempts are genuine runs with genuine FAILED rows and the real
# LLM_EMPTY_RESPONSE code — not a hand-raised exception standing in for one.
def _discovery_payload(seed_entity_id: str, names) -> dict:
    return {
        "schema_version": "1.0",
        "seed_entity_id": seed_entity_id,
        "summary": "retry fixture",
        "regions": [{"local_id": "region_1", "name": "R1", "confidence": 0.5},
                    {"local_id": "region_2", "name": "R2", "confidence": 0.5}],
        "connections": [{"local_id": "connection_1", "confidence": 0.5,
                         "species_context": {"scope": "UNKNOWN", "taxon_ids": []},
                         "source_ref": "region_1", "target_ref": "region_2",
                         "connection_type": "PROJECTION", "directionality": "DIRECTED"}],
        "functions": [],
        "circuits": [{"local_id": f"circuit_{i}", "name": n, "confidence": 0.5,
                      "species_context": {"scope": "UNKNOWN", "taxon_ids": []},
                      "region_refs": ["region_1", "region_2"],
                      "connection_refs": ["connection_1"], "topology_hint": "LOOP"}
                     for i, n in enumerate(names, 1)],
        "source_hints": [],
        "warnings": [],
    }


class _Usage:
    prompt_tokens = 10
    completion_tokens = 0
    total_tokens = 10
    reasoning_tokens = 0

    def as_dict(self):
        return {}


class _ProviderResponse:
    def __init__(self, text: str):
        self.raw_text = text
        self.parsed_json = None
        self.transport_ok = True
        self.provider = "deepseek"
        self.model = "deepseek-flash"
        self.finish_reason = "length" if not text else "stop"
        self.error_message = None
        self.latency_ms = 1
        self.usage = _Usage()
        self.response_payload = {}
        self.request_payload_redacted = {}
        self.response_format = None
        self.fallback_raw_response_used = False


class _DiscoveryProvider:
    """Returns empty content for the first `empty_first` calls, then a valid one."""

    def __init__(self, seed_entity_id: str, *, empty_first: int = 0,
                 circuit_names=("Fixture circuit",)):
        self.seed = seed_entity_id
        self.empty_first = empty_first
        self.circuit_names = list(circuit_names)
        self.calls = 0

    async def complete_json(self, **kwargs):
        self.calls += 1
        if self.calls <= self.empty_first:
            return _ProviderResponse("")
        return _ProviderResponse(
            json.dumps(_discovery_payload(self.seed, self.circuit_names)))


async def _drive_with_provider(h: H, provider, recorder, *, budget: int,
                               entity_id: str = EMPTY_SEED):
    """Run the orchestrator with the REAL execution service and a fake provider."""
    from app.services import high_recall_orchestrator_service as orch
    from app.services import llm_discovery_execution_service as execution
    from app.schemas.orchestration import OrchestrationStartRequest

    with patch.object(execution, "get_llm_provider", lambda _n: provider), \
         patch.object(orch, "_assess_run", _stub_assessment(recorder, h)):
        return await orch.start_orchestration(
            h.db, entity_id=entity_id,
            request=OrchestrationStartRequest(max_new_discovery_calls=budget))


async def _resume_with_provider(h: H, provider, recorder, *, budget: int,
                                orchestration_id: str):
    from app.services import high_recall_orchestrator_service as orch
    from app.services import llm_discovery_execution_service as execution
    from app.schemas.orchestration import OrchestrationStartRequest

    with patch.object(execution, "get_llm_provider", lambda _n: provider), \
         patch.object(orch, "_assess_run", _stub_assessment(recorder, h)):
        return await orch.resume_orchestration(
            h.db, orchestration_id=orchestration_id,
            request=OrchestrationStartRequest(max_new_discovery_calls=budget))


async def _streak(h: H, orchestration_id: str, view: str = "NAMED_CLASSIC_CIRCUITS") -> int:
    row = await h.one(
        "SELECT v.consecutive_empty_response_failures AS n"
        "  FROM discovery_orchestration_view_states v"
        "  JOIN discovery_orchestrations o ON o.orchestration_pk = v.orchestration_pk"
        " WHERE o.orchestration_id = :o AND v.discovery_view = :v", o=orchestration_id, v=view)
    return int(row["n"])


async def _runs(h: H, view: str = "NAMED_CLASSIC_CIRCUITS", seed: str = EMPTY_SEED):
    # Ordered by run_pk, not created_at: runs created inside one test can share a
    # timestamp, and the point of the ordering here is causal, not decorative.
    return await h.rows(
        "SELECT r.run_id, r.status, r.error_code,"
        "       r.provenance_json ->> 'continuation_round' AS cr,"
        "       r.provenance_json ->> 'continuation_from_run_id' AS parent,"
        "       r.provenance_json ->> 'already_discovered_circuit_count' AS already,"
        "       (SELECT count(*) FROM discovery_candidates dc"
        "         WHERE dc.discovery_run_pk = r.run_pk) AS cands"
        "  FROM knowledge_discovery_runs r"
        "  JOIN brain_regions b ON b.entity_pk = r.seed_region_pk"
        "  JOIN kg_entities e ON e.entity_pk = b.entity_pk"
        " WHERE e.entity_id = :s AND r.query_strategy_version = :v"
        " ORDER BY r.run_pk", s=seed, v=f"G4HR1/{view}")


# --- A ----------------------------------------------------------------------
@case
async def test_retry_A_a_normal_success_never_retries(h, _):
    provider = _DiscoveryProvider(EMPTY_SEED)
    rec = Recorder([5])
    result = await _drive_with_provider(h, provider, rec, budget=1)
    assert provider.calls == 1, "no retry on success"
    assert result.discovery_calls_used == 1
    assert await _streak(h, result.orchestration_id) == 0
    assert result.status == "PAUSED_BY_BUDGET", result.stop_reason


# --- B / C ------------------------------------------------------------------
@case
async def test_retry_B_one_empty_response_gets_exactly_one_retry(h, _):
    provider = _DiscoveryProvider(EMPTY_SEED, empty_first=1)
    rec = Recorder([5])
    result = await _drive_with_provider(h, provider, rec, budget=2)
    assert provider.calls == 2, "exactly one automatic retry"
    assert result.discovery_calls_used == 2, "the retry is a PAID call, not a free one"


@case
async def test_retry_C_empty_then_success_continues_normally(h, _):
    provider = _DiscoveryProvider(EMPTY_SEED, empty_first=1)
    rec = Recorder([5])
    result = await _drive_with_provider(h, provider, rec, budget=2)

    runs = await _runs(h)
    assert [r["status"] for r in runs] == ["FAILED", "COMPLETED"]
    assert runs[0]["error_code"] == "LLM_EMPTY_RESPONSE"
    assert await _streak(h, result.orchestration_id) == 0, "success RESETS the streak"
    assert result.status == "PAUSED_BY_BUDGET"
    a = await _view(h, result.orchestration_id, "NAMED_CLASSIC_CIRCUITS")
    assert a["status"] == "RUNNING"


# --- D ----------------------------------------------------------------------
@case
async def test_retry_D_two_consecutive_empties_BLOCK(h, _):
    provider = _DiscoveryProvider(EMPTY_SEED, empty_first=99)
    rec = Recorder([5])
    # Budget enough for all four Views to exhaust their retry: with a smaller
    # one the GLOBAL budget ends the execution first, and this test is about
    # what the View-local rule does.
    result = await _drive_with_provider(h, provider, rec, budget=20)

    a_runs = await _runs(h, "NAMED_CLASSIC_CIRCUITS")
    assert len(a_runs) == 2, "one attempt plus one retry for A, and no more"
    assert all(r["error_code"] == "LLM_EMPTY_RESPONSE" for r in a_runs)
    # The VIEW is blocked; the orchestration is not. A provider that returned
    # nothing twice has said something about A's prompt, not about B/C/D — so
    # the sweep CONTINUES, and every View gets its own two attempts.
    assert result.status == "PAUSED_BY_BUDGET"
    assert "blocked on exhausted empty-response retries" in (result.stop_reason or "")
    assert provider.calls == 8, "two attempts for each of the four Views"
    assert await _streak(h, result.orchestration_id) == 2
    for view in ("NAMED_CLASSIC_CIRCUITS", "LOCAL_INTRINSIC_CIRCUITS",
                 "AFFERENT_CIRCUITS", "EFFERENT_CIRCUITS"):
        v = await _view(h, result.orchestration_id, view)
        assert v["status"] == "BLOCKED", view
        assert len(await _runs(h, view)) == 2, view
    assert result.status != "COMPLETED", "a blocked View must stay resumable"
    runs = await _runs(h)
    assert [r["status"] for r in runs] == ["FAILED", "FAILED"]
    assert all(r["error_code"] == "LLM_EMPTY_RESPONSE" for r in runs)


# --- E / F ------------------------------------------------------------------
@case
async def test_retry_E_a_schema_failure_is_never_retried(h, _):
    """The provider answers, and the answer does not satisfy the contract."""
    class _SchemaProvider:
        def __init__(self):
            self.calls = 0

        async def complete_json(self, **kwargs):
            self.calls += 1
            return _ProviderResponse(json.dumps({
                "schema_version": "1.0", "seed_entity_id": EMPTY_SEED,
                "regions": [], "connections": [], "functions": [],
                "circuits": [{"local_id": "circuit_1", "name": "X", "confidence": 0.5,
                              "species_context": {"scope": "UNKNOWN", "taxon_ids": []},
                              "region_refs": ["region_1", "region_2"],
                              "invented_field": "carries meaning"}],
                "source_hints": [], "warnings": [],
            }))

    provider = _SchemaProvider()
    rec = Recorder([5])
    result = await _drive_with_provider(h, provider, rec, budget=5)

    assert provider.calls == 1, "a contract failure is a statement, not a hiccup"
    assert result.status == "BLOCKED"
    assert await _streak(h, result.orchestration_id) == 0, "not an empty response"
    runs = await _runs(h)
    assert runs[0]["error_code"] == "LLM_DISCOVERY_PARSE_FAILED"


@case
async def test_retry_F_an_unknown_NON_empty_extra_is_never_retried(h, _):
    """The exact class the sanitizer refuses to drop — still immediate BLOCKED."""
    # one connection carries a POPULATED wrong-type field: content, not noise
    payload = _discovery_payload(EMPTY_SEED, ["X"])
    payload["connections"][0]["connection_refs"] = ["connection_1"]

    class _WrongTypeProvider:
        def __init__(self):
            self.calls = 0

        async def complete_json(self, **kwargs):
            self.calls += 1
            return _ProviderResponse(json.dumps(payload))

    p = _WrongTypeProvider()
    rec = Recorder([5])
    result = await _drive_with_provider(h, p, rec, budget=5)
    assert p.calls == 1
    assert result.status == "BLOCKED"


# --- G / H / I / J ----------------------------------------------------------
@case
async def test_retry_G_the_failed_empty_attempt_remains_FAILED_with_no_candidates(h, _):
    provider = _DiscoveryProvider(EMPTY_SEED, empty_first=1)
    rec = Recorder([5])
    await _drive_with_provider(h, provider, rec, budget=2)

    runs = await _runs(h)
    failed = runs[0]
    assert failed["status"] == "FAILED"
    assert failed["error_code"] == "LLM_EMPTY_RESPONSE"
    assert int(failed["cands"]) == 0, "a failed attempt persists nothing"


@case
async def test_retry_H_I_J_the_retry_reuses_the_parent_and_advances_nothing(h, _):
    """The retry is the SAME logical round: same parent, same round number, same
    exclusion pool. A failed attempt never enters the successful chain."""
    await _historical_runs(h, 2)                      # a parent to continue from
    parent = (await _runs(h))[-1]["run_id"]

    provider = _DiscoveryProvider(EMPTY_SEED, empty_first=1)
    rec = Recorder([5])
    result = await _drive_with_provider(h, provider, rec, budget=2)

    runs = await _runs(h)
    assert [r["status"] for r in runs] == ["COMPLETED", "COMPLETED", "FAILED", "COMPLETED"]
    failed, retried = runs[2], runs[3]

    # H — same parent as the attempt it replaces
    assert str(failed["parent"]) == str(parent)
    assert str(retried["parent"]) == str(parent)

    # I — the failed attempt did NOT advance the round; the retry is the same one
    assert str(failed["cr"]) == str(retried["cr"])

    # J — and did not enter the exclusion pool
    assert failed["already"] == retried["already"]


# --- K / L ------------------------------------------------------------------
@case
async def test_retry_K_both_attempts_are_counted_in_the_ledger(h, _):
    provider = _DiscoveryProvider(EMPTY_SEED, empty_first=1)
    rec = Recorder([5])
    result = await _drive_with_provider(h, provider, rec, budget=2)
    assert result.discovery_calls_used == 2, "the failed attempt still cost a call"


@case
async def test_retry_L_novelty_runs_only_for_the_successful_attempt(h, _):
    provider = _DiscoveryProvider(EMPTY_SEED, empty_first=1)
    rec = Recorder([5])
    result = await _drive_with_provider(h, provider, rec, budget=2)
    assert len(rec.assessment_calls) == 1, (
        "the empty attempt produced no result to assess"
    )
    # Not `novelty_calls_used`: the ledger's novelty counter is written by the
    # real assessor, which this suite replaces. That accounting is asserted by
    # the durable-assessor suite, against the real thing.
    assert rec.assessment_calls[0] == (await _runs(h))[1]["run_id"].__str__(), (
        "and the one assessment is of the SUCCESSFUL run"
    )


# --- M ----------------------------------------------------------------------
@case
async def test_retry_M_a_success_resets_a_previous_nonzero_streak(h, _):
    provider = _DiscoveryProvider(EMPTY_SEED, empty_first=1)
    rec = Recorder([9, 5])
    result = await _drive_with_provider(h, provider, rec, budget=3)
    assert await _streak(h, result.orchestration_id) == 0


# --- N ----------------------------------------------------------------------
@case
async def test_retry_N_a_resume_cannot_re_arm_an_exhausted_retry(h, _):
    """The streak is durable, so an unresolved empty-response chain stays blocked
    across a resume instead of earning a fresh retry each time."""
    provider = _DiscoveryProvider(EMPTY_SEED, empty_first=99)
    rec = Recorder([5])
    first = await _drive_with_provider(h, provider, rec, budget=20)
    assert first.status == "PAUSED_BY_BUDGET"
    a_runs = await _runs(h, "NAMED_CLASSIC_CIRCUITS")
    assert len(a_runs) == 2, "one attempt plus one retry for A, and no more"
    assert await _streak(h, first.orchestration_id) == 2

    before = provider.calls
    second = await _resume_with_provider(h, provider, Recorder([5]), budget=20,
                                         orchestration_id=first.orchestration_id)
    assert second.status == "PAUSED_BY_BUDGET"
    assert "blocked on exhausted empty-response retries" in (second.stop_reason or "")

    # The claim is about A, so it is asserted about A: exactly ONE attempt and
    # no retry re-armed. (The other Views now run in the same execution — that
    # is the point of View-local failure isolation — so a total call count would
    # no longer measure this.)
    a_runs = await _runs(h, "NAMED_CLASSIC_CIRCUITS")
    assert len(a_runs) == 3, "two from the first execution plus exactly one here"
    assert a_runs[-1]["status"] == "FAILED"
    assert provider.calls - before >= 1
    assert await _streak(h, first.orchestration_id) == 2, "and it saturates, not grows"


# --- the policy's shape ------------------------------------------------------
def test_retry_the_policy_is_one_code_and_one_retry():
    from app.services import high_recall_orchestrator_service as orch

    assert orch.EMPTY_RESPONSE_CODE == "LLM_EMPTY_RESPONSE"
    assert orch.MAX_CONSECUTIVE_EMPTY_RESPONSES == 2
    source = (BACKEND / "app/services/high_recall_orchestrator_service.py").read_text(
        encoding="utf-8")
    assert source.count("_bump_empty_response_failures") == 2  # def + one call
    assert "_reset_empty_response_failures" in source


def test_retry_zero_streak_and_empty_streak_are_separate_concepts():
    """A novelty zero is a scientific result; a provider-empty is an operational
    event. Overloading one column with both would make a transport hiccup look
    like saturation."""
    source = (BACKEND / "app/services/high_recall_orchestrator_service.py").read_text(
        encoding="utf-8")
    assert "consecutive_empty_response_failures" in source
    # the novelty zero streak is never written from the empty-response path
    assert "zero_streak = " not in source.split("_bump_empty_response_failures")[1][:400]


# ===========================================================================
# Per-View scheduling — each View gets its own slice of one execution
# ===========================================================================
# Before this, one View that kept producing novelty consumed the whole budget and
# the sweep never reached the next one: B, C and D had never run at all. A View
# now spends an ALLOCATION and yields; only the shared budget still pauses.
BUSY = [9] * 40          # novelty every round: a View never saturates on its own


def _views(rec: Recorder) -> list[str]:
    return [c["view"] for c in rec.discovery_calls]


def _short(view: str) -> str:
    return view.split("_")[0]


async def _views_from_db(h: H) -> list[str]:
    """The View order the DATABASE saw: runs of this seed, in creation order.

    The provider-driven tests run the REAL execution service, so the Recorder
    never sees those calls — the runs themselves are the record.
    """
    rows = await h.rows(
        "SELECT r.query_strategy_version AS strat FROM knowledge_discovery_runs r"
        "  JOIN brain_regions b ON b.entity_pk = r.seed_region_pk"
        "  JOIN kg_entities e ON e.entity_pk = b.entity_pk"
        " WHERE e.entity_id = :s ORDER BY r.run_pk", s=EMPTY_SEED)
    return [r["strat"].split("/")[-1] for r in rows]


# --- A / C ------------------------------------------------------------------
@case
async def test_sched_A_each_view_gets_its_balancing_allocation(h, _):
    """A=2, B=6, C=6, D=6 — and A stops because its ALLOCATION is spent."""
    rec = Recorder(BUSY)
    result = await _orchestrate(h, rec, budget=20)

    assert [_short(v) for v in _views(rec)] == (
        ["NAMED"] * 2 + ["LOCAL"] * 6 + ["AFFERENT"] * 6 + ["EFFERENT"] * 6
    ), _views(rec)
    assert result.status == "PAUSED_BY_BUDGET"


@case
async def test_sched_C_the_view_cap_is_not_a_global_pause(h, _):
    """A spends 2 of a 3-call budget and YIELDS — the third call goes to B.

    If A had paused the execution instead, the third call could not exist: at
    that moment only 2 of the 3 shared calls had been spent.
    """
    rec = Recorder(BUSY)
    result = await _orchestrate(h, rec, budget=3)

    assert [_short(v) for v in _views(rec)] == ["NAMED", "NAMED", "LOCAL"], _views(rec)
    a = await _view(h, result.orchestration_id, "NAMED_CLASSIC_CIRCUITS")
    assert a["status"] == "RUNNING", "a yield is not a scientific outcome"
    assert a["stop_reason"] is None

    # ...and the thing that eventually stopped the sweep was the SHARED budget,
    # not A's allocation.
    assert "safety budget of 3" in (result.stop_reason or ""), result.stop_reason
    assert "allocation" not in (result.stop_reason or "")


# --- B ----------------------------------------------------------------------
@case
async def test_sched_B_once_balancing_is_done_each_view_gets_five(h, _):
    from app.services import high_recall_orchestrator_service as orch
    from app.services import llm_discovery_execution_service as execution
    from app.schemas.orchestration import OrchestrationStartRequest

    first = Recorder(BUSY)
    started = await _orchestrate(h, first, budget=20)
    assert started.status == "PAUSED_BY_BUDGET"
    # every View completed at least one round, so balancing is over
    for view in orch.VIEW_ORDER:
        v = await _view(h, started.orchestration_id, view)
        assert v["successful_round_count"] > 0, view

    second = Recorder(BUSY)
    with patch.object(execution, "execute_llm_discovery",
                      _stub_discovery(second, h, EMPTY_SEED)), \
         patch.object(orch, "_assess_run", _stub_assessment(second, h)):
        resumed = await orch.resume_orchestration(
            h.db, orchestration_id=started.orchestration_id,
            request=OrchestrationStartRequest(max_new_discovery_calls=20))

    assert [_short(v) for v in _views(second)] == (
        ["NAMED"] * 5 + ["LOCAL"] * 5 + ["AFFERENT"] * 5 + ["EFFERENT"] * 5
    ), _views(second)
    assert resumed.status == "PAUSED_BY_BUDGET"


# --- D ----------------------------------------------------------------------
@case
async def test_sched_D_true_budget_exhaustion_still_pauses(h, _):
    rec = Recorder(BUSY)
    result = await _orchestrate(h, rec, budget=1)

    assert result.status == "PAUSED_BY_BUDGET"
    assert len(rec.discovery_calls) == 1
    assert "safety budget of 1" in (result.stop_reason or ""), result.stop_reason
    a = await _view(h, result.orchestration_id, "NAMED_CLASSIC_CIRCUITS")
    assert a["status"] == "RUNNING"


# --- E ----------------------------------------------------------------------
@case
async def test_sched_E_a_blocked_view_does_not_stop_the_sweep(h, _):
    """Two empty responses block A. B runs anyway, in the same execution."""
    provider = _DiscoveryProvider(EMPTY_SEED, empty_first=2)
    rec = Recorder(BUSY)
    result = await _drive_with_provider(h, provider, rec, budget=20)

    a = await _view(h, result.orchestration_id, "NAMED_CLASSIC_CIRCUITS")
    assert a["status"] == "BLOCKED"
    assert await _streak(h, result.orchestration_id) == 2
    assert len(await _runs(h, "NAMED_CLASSIC_CIRCUITS")) == 2, "one attempt, one retry"

    assert "LOCAL_INTRINSIC_CIRCUITS" in await _views_from_db(h), (
        "the View after the blocked one must still get its turn"
    )
    assert result.status != "BLOCKED", (
        "one View's provider hiccup is not the orchestration's failure"
    )


# --- F ----------------------------------------------------------------------
@case
async def test_sched_F_an_infrastructure_failure_is_still_fatal(h, _):
    """A contract failure is NOT View-local: it stops everything, as before."""
    class _SchemaProvider:
        def __init__(self):
            self.calls = 0

        async def complete_json(self, **kwargs):
            self.calls += 1
            return _ProviderResponse(json.dumps({
                "schema_version": "1.0", "seed_entity_id": EMPTY_SEED,
                "regions": [], "connections": [], "functions": [],
                "circuits": [{"local_id": "circuit_1", "name": "X", "confidence": 0.5,
                              "species_context": {"scope": "UNKNOWN", "taxon_ids": []},
                              "invented_field": "carries meaning"}],
                "source_hints": [], "warnings": [],
            }))

    provider = _SchemaProvider()
    rec = Recorder(BUSY)
    result = await _drive_with_provider(h, provider, rec, budget=20)

    assert provider.calls == 1, "not retryable, and not isolated"
    assert result.status == "BLOCKED"
    assert await _views_from_db(h) == ["NAMED_CLASSIC_CIRCUITS"], "no other View may run"


# --- G ----------------------------------------------------------------------
@case
async def test_sched_G_saturation_is_still_per_view(h, _):
    """A saturates on two zeros; B still runs in the SAME execution."""
    rec = Recorder([0, 0, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9])
    result = await _orchestrate(h, rec, budget=20)

    a = await _view(h, result.orchestration_id, "NAMED_CLASSIC_CIRCUITS")
    assert a["status"] == "SATURATED_BY_ZERO_NOVELTY"
    assert a["zero_streak"] == 2
    assert _views(rec)[:2] == ["NAMED_CLASSIC_CIRCUITS"] * 2
    assert "LOCAL_INTRINSIC_CIRCUITS" in _views(rec), "the sweep continued"


# --- H / I ------------------------------------------------------------------
@case
async def test_sched_H_each_view_continues_its_OWN_history(h, _):
    """B and D attach to their OWN latest run — never to A's, never at R1."""
    a_history = await _historical_runs(h, 1)
    b_history = await _historical_runs(h, 1, view="LOCAL_INTRINSIC_CIRCUITS")
    d_history = await _historical_runs(h, 1, view="EFFERENT_CIRCUITS")
    assert len({a_history[0], b_history[0], d_history[0]}) == 3

    rec = Recorder(BUSY)
    await _orchestrate(h, rec, budget=20)

    by_view: dict[str, list[dict]] = {}
    for call in rec.discovery_calls:
        by_view.setdefault(call["view"], []).append(call)

    for view, parent in (("NAMED_CLASSIC_CIRCUITS", a_history[0]),
                         ("LOCAL_INTRINSIC_CIRCUITS", b_history[0]),
                         ("EFFERENT_CIRCUITS", d_history[0])):
        assert str(by_view[view][0]["continuation_from"]) == str(parent), view
        # ...and it is that View's OWN run, not one belonging to another View.
        assert str(parent) in {str(r["run_id"]) for r in await _runs(h, view)}

    # A View with NO history still starts at Round 1 — the bootstrap decides
    # that, and the schedule says nothing about which run a View continues.
    assert by_view["AFFERENT_CIRCUITS"][0]["continuation_from"] is None


@case
async def test_sched_I_no_continuation_ever_crosses_a_view(h, _):
    """The scheduler moves between Views; it never merges their searches."""
    await _historical_runs(h, 1)
    await _historical_runs(h, 1, view="LOCAL_INTRINSIC_CIRCUITS")

    rec = Recorder(BUSY)
    await _orchestrate(h, rec, budget=20)

    owner: dict[str, str] = {}
    for view in ("NAMED_CLASSIC_CIRCUITS", "LOCAL_INTRINSIC_CIRCUITS",
                 "AFFERENT_CIRCUITS", "EFFERENT_CIRCUITS"):
        for run in await _runs(h, view):
            owner[str(run["run_id"])] = view

    continuations = [c for c in rec.discovery_calls if c["continuation_from"]]
    assert continuations, "the sweep produced continuation rounds"
    for call in continuations:
        assert owner[str(call["continuation_from"])] == call["view"], (
            f"a continuation crossed Views: {call}"
        )


# ===========================================================================
# A run's novelty verdict is applied to zero_streak AT MOST ONCE
# ===========================================================================
# A View's stored state belongs to a round, and ``latest_successful_run_pk``
# says which. A resume attaches to that same run, so re-applying its verdict
# would count ONE round twice — and one round counted twice saturates a View
# that produced a single zero, which is a scientific claim the run never made.
def _resume_patch(recorder: Recorder, h: H):
    from app.services import high_recall_orchestrator_service as orch
    from app.services import llm_discovery_execution_service as execution
    from app.schemas.orchestration import OrchestrationStartRequest

    async def _go(orchestration_id: str, budget: int):
        with patch.object(execution, "execute_llm_discovery",
                          _stub_discovery(recorder, h, EMPTY_SEED)), \
             patch.object(orch, "_assess_run", _stub_assessment(recorder, h)):
            return await orch.resume_orchestration(
                h.db, orchestration_id=orchestration_id,
                request=OrchestrationStartRequest(max_new_discovery_calls=budget))

    return _go


# --- A ----------------------------------------------------------------------
@case
async def test_zero_A_a_resume_does_not_re_count_the_same_run(h, _):
    """R1 → zero (streak 1) → pause → resume: R1 is NOT judged again."""
    first = Recorder([0])
    started = await _orchestrate(h, first, budget=1)
    assert started.status == "PAUSED_BY_BUDGET"
    a = await _view(h, started.orchestration_id, "NAMED_CLASSIC_CIRCUITS")
    assert a["zero_streak"] == 1

    # The bootstrap re-judges R1 (a REUSE in production) and gets its stored
    # verdict back — 0. That verdict is already in the streak, so the loop must
    # move on to a NEW round, which returns 9.
    second = Recorder([0, 9])
    resumed = await _resume_patch(second, h)(started.orchestration_id, budget=1)

    assert len(second.discovery_calls) == 1, "a NEW round, not a re-judged old one"
    assert len(await _runs(h)) == 2
    a = await _view(h, resumed.orchestration_id, "NAMED_CLASSIC_CIRCUITS")
    assert a["status"] == "RUNNING", "one zero must not saturate"
    assert a["zero_streak"] == 0, "the new round's novelty reset the streak"


# --- B ----------------------------------------------------------------------
@case
async def test_zero_B_saturation_needs_two_DISTINCT_zero_runs(h, _):
    first = Recorder([0])
    started = await _orchestrate(h, first, budget=1)
    assert (await _view(
        h, started.orchestration_id, "NAMED_CLASSIC_CIRCUITS"))["zero_streak"] == 1

    second = Recorder([0, 0])          # bootstrap reuse, then a NEW zero round
    resumed = await _resume_patch(second, h)(started.orchestration_id, budget=1)

    runs = await _runs(h)
    assert len(runs) == 2, "saturation must come from two runs, not one counted twice"
    assert all(r["status"] == "COMPLETED" for r in runs)
    a = await _view(h, resumed.orchestration_id, "NAMED_CLASSIC_CIRCUITS")
    assert a["status"] == "SATURATED_BY_ZERO_NOVELTY"
    assert a["zero_streak"] == 2


# --- C ----------------------------------------------------------------------
@case
async def test_zero_C_novelty_after_a_resumed_zero_resets_the_streak(h, _):
    first = Recorder([0])
    started = await _orchestrate(h, first, budget=1)

    second = Recorder([0, 9, 9])       # bootstrap reuse, then two positive rounds
    resumed = await _resume_patch(second, h)(started.orchestration_id, budget=2)

    assert len(await _runs(h)) == 3, "the View kept searching"
    a = await _view(h, resumed.orchestration_id, "NAMED_CLASSIC_CIRCUITS")
    assert a["status"] == "RUNNING"
    assert a["zero_streak"] == 0
    assert resumed.status == "PAUSED_BY_BUDGET"


# --- D ----------------------------------------------------------------------
@case
async def test_zero_D_reusing_a_stored_assessment_does_not_re_apply_its_effect(h, _):
    """The bootstrap's assessment is a REUSE. Reuse is not re-application."""
    first = Recorder([0])
    started = await _orchestrate(h, first, budget=1)
    r1 = (await _runs(h))[0]["run_id"]

    second = Recorder([0, 9])
    resumed = await _resume_patch(second, h)(started.orchestration_id, budget=1)

    assert str(second.assessment_calls[0]) == str(r1), (
        "the bootstrap re-judges the attached run — a reuse in production"
    )
    assert len(second.discovery_calls) == 1, "and a NEW round follows it"
    a = await _view(h, resumed.orchestration_id, "NAMED_CLASSIC_CIRCUITS")
    assert a["zero_streak"] == 0, "the reused verdict was not applied a second time"


# --- E ----------------------------------------------------------------------
@case
async def test_zero_E_the_zero_guard_still_cooperates_with_the_scheduler(h, _):
    """The fix touches the streak only: A resolves its zero and still yields."""
    rec = Recorder([0, 9] + BUSY)
    result = await _orchestrate(h, rec, budget=20)

    assert _views(rec)[:2] == ["NAMED_CLASSIC_CIRCUITS"] * 2, (
        "A took the round that resolved its zero"
    )
    assert "LOCAL_INTRINSIC_CIRCUITS" in _views(rec), "and the sweep still moved on"
    a = await _view(h, result.orchestration_id, "NAMED_CLASSIC_CIRCUITS")
    assert a["zero_streak"] == 0
    assert a["status"] == "RUNNING"
