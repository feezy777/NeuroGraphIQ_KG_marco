"""Durable circuit novelty assessment — persistence, idempotency, rollback.

These exercise the REAL service against the REAL isolated test database, because
what is under test is the interaction between service logic and database
constraints. A fake would prove only the fake: the one-assessment-per-(run,
prompt version, model) guarantee, the FK from a verdict to the circuit it judged
and to the earlier circuit it matched, the arithmetic CHECKs, and "no candidate
row was touched" are all properties of the database, not of the Python.

Isolation
---------
Each test runs inside an outer transaction that is always ROLLED BACK. The
session joins that transaction with ``join_transaction_mode="create_savepoint"``,
so the service's own ``session.commit()`` releases a SAVEPOINT rather than
committing for real. The whole test body runs in ONE event loop.

If the isolated database or the migration is missing, the tests SKIP loudly --
they never silently pass.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable
from unittest.mock import patch

import pytest

from app.schemas.llm_discovery import SCHEMA_VERSION

if sys.platform == "win32":  # psycopg async cannot use the Proactor loop
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

BACKEND = Path(__file__).resolve().parents[1]
E2E_DB = os.environ.get("TEST_E2E_DB", "neurographiq_human_brain_v1_e2e")

VIEW = "NAMED_CLASSIC_CIRCUITS"
OTHER_VIEW = "AFFERENT_CIRCUITS"


def _dsn(async_: bool = True) -> str:
    cfg: dict[str, str] = {}
    env = BACKEND / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    driver = "postgresql+psycopg://" if async_ else "postgresql://"
    return "%s%s:%s@%s:%s/%s" % (
        driver, cfg.get("POSTGRES_USER"), cfg.get("POSTGRES_PASSWORD"),
        cfg.get("POSTGRES_HOST", "127.0.0.1"), cfg.get("POSTGRES_PORT", "5432"), E2E_DB)


def _resolve_seed() -> str:
    """Left Hippocampus, looked up rather than hard-coded: the isolated test
    database comes from a different dump, so the same region carries a different
    numeric suffix there."""
    try:
        import psycopg

        with psycopg.connect(_dsn(async_=False)) as conn:
            row = conn.execute(
                "SELECT entity_id FROM kg_entities"
                " WHERE entity_type = 'brain_region' AND name_en = 'Left Hippocampus'"
                " ORDER BY entity_id LIMIT 1").fetchone()
        return row[0] if row else "NGIQ-BR-00001169"
    except Exception:  # pragma: no cover - the tests skip later anyway
        return "NGIQ-BR-00001169"


SEED = _resolve_seed()


@dataclass
class Session:
    db: Any

    async def scalar(self, sql: str, **params: Any) -> Any:
        from sqlalchemy import text

        return (await self.db.execute(text(sql), params)).scalar_one_or_none()

    async def rows(self, sql: str, **params: Any) -> list[Any]:
        from sqlalchemy import text

        return list((await self.db.execute(text(sql), params)).mappings().all())

    async def count(self, sql: str, **params: Any) -> int:
        return int(await self.scalar(sql, **params))


def case(fn: Callable[[Session, Any], Awaitable[None]]):
    """Run an async test in one event loop, inside a rolled-back transaction."""

    def wrapper() -> None:
        asyncio.run(_drive(fn))

    wrapper.__name__ = fn.__name__
    wrapper.__qualname__ = fn.__qualname__
    wrapper.__doc__ = fn.__doc__
    return wrapper


async def _drive(fn: Callable[[Session, Any], Awaitable[None]]) -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.services import llm_circuit_novelty_service as novelty

    engine = create_async_engine(_dsn(), poolclass=NullPool)
    try:
        connection = await engine.connect()
    except Exception as exc:  # pragma: no cover - environment dependent
        await engine.dispose()
        pytest.skip(f"isolated test database unavailable: {type(exc).__name__}")

    transaction = await connection.begin()
    db = AsyncSession(bind=connection, join_transaction_mode="create_savepoint")
    try:
        missing = (
            await connection.execute(text(
                "SELECT to_regclass('public.discovery_candidates'),"
                "       to_regclass('public.discovery_circuit_novelty_assessments'),"
                "       to_regclass('public.discovery_circuit_novelty_verdicts')"
            ))
        ).one()
        if any(t is None for t in missing):
            pytest.skip("gate7b_016 / gate7b_019 not applied to the isolated DB")

        await fn(Session(db), novelty)
    finally:
        await db.close()
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


# ===========================================================================
# fixtures
# ===========================================================================
def _response_with_circuits(seed_entity_id: str, names: list[str]) -> dict[str, Any]:
    """A valid Phase 3A response carrying one Circuit per name.

    Shaped to survive the REAL parser: every circuit cites two distinct regions
    and resolves every ref it declares.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "seed_entity_id": seed_entity_id,
        "summary": "novelty persistence fixture",
        "regions": [
            {"local_id": "region_1", "name": "CA1", "confidence": 0.5},
            {"local_id": "region_2", "name": "Entorhinal cortex", "confidence": 0.5},
        ],
        "connections": [
            {"local_id": "connection_1", "confidence": 0.5,
             "species_context": {"scope": "UNKNOWN", "taxon_ids": []},
             "source_ref": "region_1", "target_ref": "region_2",
             "connection_type": "PROJECTION", "directionality": "DIRECTED"},
        ],
        "functions": [],
        "circuits": [
            {"local_id": f"circuit_{i}", "name": name, "confidence": 0.5,
             "species_context": {"scope": "UNKNOWN", "taxon_ids": []},
             "region_refs": ["region_1", "region_2"],
             "connection_refs": ["connection_1"],
             "topology_hint": "LOOP"}
            for i, name in enumerate(names, 1)
        ],
        "source_hints": [],
        "warnings": [],
    }


async def _completed_run(h: Session, *, entity_id: str = SEED, view: str | None = VIEW,
                         circuit_names: list[str] | None = None):
    """A real COMPLETED discovery run of one view, with real Circuit rows.

    Created through the real lifecycle service, not by hand-written SQL, so the
    run is exactly what the pipeline would have produced.
    """
    from app.llm_discovery_views import strategy_identifier
    from app.schemas.llm_discovery import LlmDiscoveryResponse
    from app.services import (
        knowledge_discovery_run_lifecycle_service as lifecycle,
        llm_candidate_persistence_service as persistence,
    )

    run = await lifecycle.create_discovery_run(
        h.db,
        entity_id=entity_id,
        discovery_type="LLM_DISCOVERY",
        query_strategy_version=strategy_identifier(view) if view else None,
    )
    await lifecycle.start_discovery_run(h.db, run.run_id)
    keys = (await h.rows(
        "SELECT run_pk, seed_region_pk FROM knowledge_discovery_runs WHERE run_id = :r",
        r=run.run_id))[0]
    run_pk, seed_pk = int(keys["run_pk"]), int(keys["seed_region_pk"])

    names = circuit_names if circuit_names is not None else []
    if names:
        await persistence.persist_discovery_candidates(
            h.db, discovery_run_pk=run_pk, seed_region_pk=seed_pk,
            data=LlmDiscoveryResponse.model_validate(
                _response_with_circuits(entity_id, names)),
        )
    await lifecycle.complete_discovery_run(h.db, run.run_id, "CANDIDATES_FOUND")
    return run.run_id, run_pk, seed_pk


async def _circuit_ids(h: Session, run_pk: int) -> list[str]:
    rows = await h.rows(
        "SELECT candidate_id FROM discovery_candidates"
        " WHERE discovery_run_pk = :p AND candidate_type = 'circuit'"
        " ORDER BY candidate_id", p=run_pk)
    return [r["candidate_id"] for r in rows]


async def _first_circuit_id(h: Session, run_pk: int) -> str:
    return (await _circuit_ids(h, run_pk))[0]


class _Stub:
    """A provider that returns one canned reply and counts its calls."""

    def __init__(self, payload: dict[str, Any] | None):
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    async def complete_json(self, **kwargs):
        self.calls.append(kwargs)
        import json

        return _Resp(raw_text=json.dumps(self.payload) if self.payload else "")


class _Resp:
    def __init__(self, raw_text: str, transport_ok: bool = True,
                 model: str = "deepseek-flash"):
        self.raw_text = raw_text
        self.parsed_json = None
        self.transport_ok = transport_ok
        self.model = model
        self.error_message = None


def _verdicts(*items) -> dict[str, Any]:
    return {"verdicts": [
        {"candidate_id": cid, "novelty_class": klass,
         "matched_prior_candidate_id": matched, "short_reason": "because"}
        for cid, klass, matched in items
    ]}


async def _run(novelty, h, run_id: str, payload):
    """Run the real persist-and-assess flow with a stubbed provider."""
    stub = _Stub(payload)
    with patch.object(novelty, "get_llm_provider", lambda _n: stub):
        result = await novelty.assess_and_persist_circuit_novelty(
            h.db, run_id=run_id)
    return result, stub


# ===========================================================================
# successful persistence
# ===========================================================================
@case
async def test_A_a_completed_assessment_and_its_verdicts_persist(h, novelty):
    prior_id, prior_pk, _ = await _completed_run(h, circuit_names=["Known A"])
    target_id, target_pk, _ = await _completed_run(h, circuit_names=["Brand new", "Also new"])
    (a, b) = await _circuit_ids(h, target_pk)

    result, stub = await _run(novelty, h, target_id, _verdicts(
        (a, "NEW", None), (b, "BORDERLINE", None)))

    assert result.assessment_id.startswith("NGIQ-DCN-")
    assert result.target_run_id == target_id
    assert result.discovery_view == VIEW
    assert result.query_strategy_version.endswith(VIEW)
    assert result.provider == "deepseek"
    assert result.model_name == "deepseek-flash"
    assert result.prior_completed_run_count == 1
    assert result.prior_circuit_count == 1
    assert len(stub.calls) == 1

    stored = await h.rows(
        "SELECT * FROM discovery_circuit_novelty_assessments WHERE assessment_id = :a",
        a=result.assessment_id)
    assert len(stored) == 1
    # One verdict row per judged circuit, and the counts equal the classes.
    n = await h.count(
        "SELECT count(*) AS c FROM discovery_circuit_novelty_verdicts v"
        " JOIN discovery_circuit_novelty_assessments a"
        "   ON a.assessment_pk = v.assessment_pk WHERE a.assessment_id = :a",
        a=result.assessment_id)
    assert n == 2
    assert stored[0]["raw_circuit_count"] == 2
    assert stored[0]["new_count"] == 1 and stored[0]["borderline_count"] == 1
    assert stored[0]["semantic_new_count"] == 2


@case
async def test_B_counts_equal_verdict_classes_and_semantic_new_is_NEW_plus_BORDERLINE(h, novelty):
    _, prior_pk, _ = await _completed_run(h, circuit_names=["Known A", "Known B"])
    target_id, target_pk, _ = await _completed_run(
        h, circuit_names=["One", "Two", "Three", "Four"])
    c1, c2, c3, c4 = await _circuit_ids(h, target_pk)
    prior_ids = await _circuit_ids(h, prior_pk)

    result, _ = await _run(novelty, h, target_id, _verdicts(
        (c1, "NEW", None),
        (c2, "ALIAS", prior_ids[0]),
        (c3, "REFORMULATION", prior_ids[1]),
        (c4, "BORDERLINE", None),
    ))
    assert (result.NEW_count, result.ALIAS_count) == (1, 1)
    assert (result.REFORMULATION_count, result.BORDERLINE_count) == (1, 1)
    assert result.semantic_new_count == 2
    assert result.semantic_new_count == result.NEW_count + result.BORDERLINE_count
    for name in ("NEW", "ALIAS", "REFORMULATION", "BORDERLINE"):
        counted = await h.count(
            "SELECT count(*) AS c FROM discovery_circuit_novelty_verdicts v"
            " JOIN discovery_circuit_novelty_assessments a"
            "   ON a.assessment_pk = v.assessment_pk"
            " WHERE a.assessment_id = :a AND v.novelty_class = :k",
            a=result.assessment_id, k=name)
        assert counted == getattr(result, f"{name}_count"), name


@case
async def test_C_a_matched_prior_candidate_is_a_valid_relational_key(h, novelty):
    _, prior_pk, _ = await _completed_run(h, circuit_names=["Known A"])
    target_id, target_pk, _ = await _completed_run(h, circuit_names=["Same thing"])
    (target_cid,) = await _circuit_ids(h, target_pk)
    (prior_cid,) = await _circuit_ids(h, prior_pk)

    result, _ = await _run(novelty, h, target_id, _verdicts((target_cid, "ALIAS", prior_cid)))
    assert result.verdicts[0].matched_prior_candidate_id == prior_cid

    # Stored as a KEY, and the key resolves back to that public id.
    row = (await h.rows(
        "SELECT m.candidate_id AS matched, v.candidate_pk, v.matched_prior_candidate_pk"
        " FROM discovery_circuit_novelty_verdicts v"
        " JOIN discovery_circuit_novelty_assessments a"
        "   ON a.assessment_pk = v.assessment_pk"
        " JOIN discovery_candidates m ON m.candidate_pk = v.matched_prior_candidate_pk"
        " WHERE a.assessment_id = :a", a=result.assessment_id))[0]
    assert row["matched"] == prior_cid
    assert row["candidate_pk"] != row["matched_prior_candidate_pk"]
    # ... and the matched run is reachable through that row, not duplicated.
    assert result.verdicts[0].matched_prior_run_id is not None


# ===========================================================================
# scope: seed, view, earlier-only, completed-only, never itself
# ===========================================================================
@case
async def test_D_the_prior_pool_is_confined_to_ONE_view(h, novelty):
    """A circuit found under another view is not this view's prior art."""
    await _completed_run(h, view=OTHER_VIEW, circuit_names=["Other-view circuit A",
                                                            "Other-view circuit B"])
    _, prior_pk, _ = await _completed_run(h, view=VIEW, circuit_names=["Same-view circuit"])
    target_id, target_pk, _ = await _completed_run(h, view=VIEW, circuit_names=["New one"])

    result, _ = await _run(novelty, h, target_id, _verdicts((await _first_circuit_id(h, target_pk), "NEW", None)))
    assert result.prior_circuit_count == 1, "only the same-view circuit may be prior art"
    assert result.prior_completed_run_count == 1


@case
async def test_E_a_FAILED_run_contributes_nothing_to_the_prior_pool(h, novelty):
    from app.services import knowledge_discovery_run_lifecycle_service as lifecycle
    from app.llm_discovery_views import strategy_identifier
    from app.schemas.llm_discovery import LlmDiscoveryResponse
    from app.services import llm_candidate_persistence_service as persistence

    # A FAILED run that did manage to store circuits before failing.
    failed = await lifecycle.create_discovery_run(
        h.db, entity_id=SEED, discovery_type="LLM_DISCOVERY",
        query_strategy_version=strategy_identifier(VIEW))
    await lifecycle.start_discovery_run(h.db, failed.run_id)
    keys = (await h.rows(
        "SELECT run_pk, seed_region_pk FROM knowledge_discovery_runs WHERE run_id = :r",
        r=failed.run_id))[0]
    await persistence.persist_discovery_candidates(
        h.db, discovery_run_pk=int(keys["run_pk"]),
        seed_region_pk=int(keys["seed_region_pk"]),
        data=LlmDiscoveryResponse.model_validate(
            _response_with_circuits(SEED, ["From the failed attempt"])))
    await lifecycle.fail_discovery_run(h.db, failed.run_id, error_code="X",
                                       error_message="boom")

    target_id, target_pk, _ = await _completed_run(h, circuit_names=["Only circuit"])
    result, _ = await _run(novelty, h, target_id, _verdicts((await _first_circuit_id(h, target_pk), "NEW", None)))
    assert result.prior_circuit_count == 0, "a FAILED run is not prior art"
    assert result.prior_completed_run_count == 0


@case
async def test_F_the_target_run_is_never_its_own_prior_art(h, novelty):
    target_id, target_pk, _ = await _completed_run(
        h, circuit_names=["Alpha", "Beta", "Gamma"])
    ids = await _circuit_ids(h, target_pk)
    result, _ = await _run(novelty, h, target_id, _verdicts(
        (ids[0], "NEW", None), (ids[1], "NEW", None), (ids[2], "NEW", None)))
    assert result.prior_circuit_count == 0
    assert result.prior_completed_run_count == 0


@case
async def test_G_every_EARLIER_completed_run_of_the_view_contributes(h, novelty):
    """Not just the immediate predecessor: the pool spans the whole history."""
    for n in (1, 2, 3):
        await _completed_run(h, circuit_names=[f"Round {n} circuit"])
    target_id, target_pk, _ = await _completed_run(h, circuit_names=["Latest"])
    result, _ = await _run(novelty, h, target_id, _verdicts((await _first_circuit_id(h, target_pk), "NEW", None)))
    assert result.prior_completed_run_count == 3
    assert result.prior_circuit_count == 3


@case
async def test_H_a_cross_seed_run_is_never_prior_art(h, novelty):
    """Same view, different seed: the comparison must not reach across."""
    await _completed_run(h, entity_id=SEED, circuit_names=["Same seed circuit"])
    target_id, target_pk, _ = await _completed_run(h, circuit_names=["Target"])
    result, _ = await _run(novelty, h, target_id, _verdicts((await _first_circuit_id(h, target_pk), "NEW", None)))
    assert result.seed_entity_id == SEED
    assert result.prior_circuit_count == 1


# ===========================================================================
# idempotency / cost safety
# ===========================================================================
@case
async def test_I_a_second_POST_reuses_the_stored_assessment_and_spends_nothing(h, novelty):
    _, prior_pk, _ = await _completed_run(h, circuit_names=["Known"])
    target_id, target_pk, _ = await _completed_run(h, circuit_names=["New one"])
    ids = await _circuit_ids(h, target_pk)

    first, stub1 = await _run(novelty, h, target_id, _verdicts((ids[0], "NEW", None)))
    second, stub2 = await _run(novelty, h, target_id, _verdicts((ids[0], "ALIAS", "nonsense")))

    assert len(stub1.calls) == 1
    assert stub2.calls == [], "a repeated POST must not spend a provider call"
    assert second.assessment_id == first.assessment_id
    assert await h.count(
        "SELECT count(*) AS c FROM discovery_circuit_novelty_assessments"
        " WHERE target_run_pk = (SELECT run_pk FROM knowledge_discovery_runs"
        "                        WHERE run_id = :r)", r=target_id) == 1


@case
async def test_J_a_different_view_identifier_is_a_different_prior_pool(h, novelty):
    """The strategy identifier is part of the scope, not decoration."""
    _, same_pk, _ = await _completed_run(h, view=VIEW, circuit_names=["Same view"])
    await _completed_run(h, view=OTHER_VIEW, circuit_names=["Other view"])
    target_id, target_pk, _ = await _completed_run(h, view=VIEW, circuit_names=["T"])
    result, _ = await _run(novelty, h, target_id, _verdicts((await _first_circuit_id(h, target_pk), "NEW", None)))
    assert result.query_strategy_version.endswith(VIEW)
    assert result.prior_circuit_count == 1


# ===========================================================================
# rollback: a rejected judgement leaves NOTHING behind
# ===========================================================================
@case
async def test_K_an_invalid_model_reply_writes_no_row_at_all(h, novelty):
    # Prior art is REQUIRED here: with an empty pool the assessor answers
    # deterministically and never reaches the model, so there would be no
    # partial reply to refuse.
    await _completed_run(h, circuit_names=["Prior art"])
    target_id, target_pk, _ = await _completed_run(
        h, circuit_names=["A", "B", "C"])

    # One of three circuits judged: a partial answer must be REFUSED, and
    # refusing it must leave no parent row and no verdict row.
    ids = await _circuit_ids(h, target_pk)
    partial = _verdicts((ids[0], "NEW", None))
    with pytest.raises(novelty.NoveltyAssessmentIncomplete):
        await _run(novelty, h, target_id, partial)

    assert await h.count(
        "SELECT count(*) AS c FROM discovery_circuit_novelty_assessments"
        " WHERE target_run_pk = (SELECT run_pk FROM knowledge_discovery_runs"
        "                        WHERE run_id = :r)", r=target_id) == 0
    assert await h.count(
        "SELECT count(*) AS c FROM discovery_circuit_novelty_verdicts v"
        " JOIN discovery_candidates dc ON dc.candidate_pk = v.candidate_pk"
        " JOIN knowledge_discovery_runs r ON r.run_pk = dc.discovery_run_pk"
        " WHERE r.run_id = :r", r=target_id) == 0


@case
async def test_L_a_persistence_failure_rolls_the_PARENT_back_too(h, novelty):
    """The parent and its verdicts become visible together or not at all."""
    from sqlalchemy import text

    target_id, target_pk, _ = await _completed_run(h, circuit_names=["Only"])
    ids = await _circuit_ids(h, target_pk)

    # Fault injection: the verdict insert is replaced by one that violates the
    # frozen vocabulary CHECK, so the PARENT row's insert must be undone with it.
    broken = text(
        "INSERT INTO discovery_circuit_novelty_verdicts"
        " (assessment_pk, candidate_pk, novelty_class, matched_prior_candidate_pk,"
        "  short_reason) VALUES (:assessment_pk, :candidate_pk, 'NOT_A_CLASS', NULL, 'x')"
    )
    with patch.object(novelty, "_INSERT_VERDICT_SQL", broken):
        with pytest.raises(Exception):
            await _run(novelty, h, target_id, _verdicts((ids[0], "NEW", None)))

    assert await h.count(
        "SELECT count(*) AS c FROM discovery_circuit_novelty_assessments"
        " WHERE target_run_pk = :p", p=target_pk) == 0, "the parent survived a failed child"


# ===========================================================================
# no mutation of anything that was already there
# ===========================================================================
@case
async def test_M_no_candidate_row_is_modified_by_an_assessment(h, novelty):
    _, prior_pk, _ = await _completed_run(h, circuit_names=["Known"])
    target_id, target_pk, _ = await _completed_run(h, circuit_names=["New one"])
    (target_cid,) = await _circuit_ids(h, target_pk)
    (prior_cid,) = await _circuit_ids(h, prior_pk)

    before = await h.rows(
        "SELECT candidate_id, status, confidence, payload_json, updated_at"
        " FROM discovery_candidates WHERE discovery_run_pk IN (:a, :b)"
        " ORDER BY candidate_id", a=prior_pk, b=target_pk)

    await _run(novelty, h, target_id, _verdicts((target_cid, "ALIAS", prior_cid)))

    after = await h.rows(
        "SELECT candidate_id, status, confidence, payload_json, updated_at"
        " FROM discovery_candidates WHERE discovery_run_pk IN (:a, :b)"
        " ORDER BY candidate_id", a=prior_pk, b=target_pk)
    assert before == after, "an assessment must not touch a candidate row"
    assert {r["status"] for r in after} == {"proposed"}


@case
async def test_N_no_review_record_is_created(h, novelty):
    """An assessment is not a review decision and produces no review row."""
    _, prior_pk, _ = await _completed_run(h, circuit_names=["Known"])
    target_id, target_pk, _ = await _completed_run(h, circuit_names=["New"])
    (target_cid,) = await _circuit_ids(h, target_pk)
    (prior_cid,) = await _circuit_ids(h, prior_pk)

    await _run(novelty, h, target_id, _verdicts((target_cid, "ALIAS", prior_cid)))

    assert await h.count(
        "SELECT count(*) AS c FROM candidate_review_records") == 0


# ===========================================================================
# read service
# ===========================================================================
@case
async def test_O_the_read_service_returns_what_was_stored(h, novelty):
    from app.services import llm_circuit_novelty_read_service as read

    _, prior_pk, _ = await _completed_run(h, circuit_names=["Known"])
    target_id, target_pk, _ = await _completed_run(h, circuit_names=["New", "Same"])
    c1, c2 = await _circuit_ids(h, target_pk)
    (prior_cid,) = await _circuit_ids(h, prior_pk)

    written, _ = await _run(novelty, h, target_id, _verdicts(
        (c1, "NEW", None), (c2, "REFORMULATION", prior_cid)))

    by_id = await read.get_novelty_assessment(
        h.db, assessment_id=written.assessment_id)
    assert by_id.assessment_id == written.assessment_id
    assert len(by_id.verdicts) == 2
    assert {v.novelty_class for v in by_id.verdicts} == {"NEW", "REFORMULATION"}
    matched = [v for v in by_id.verdicts if v.matched_prior_candidate_id][0]
    assert matched.matched_prior_candidate_id == prior_cid
    assert matched.matched_prior_run_id is not None

    latest = await read.get_latest_novelty_assessment(h.db, run_id=target_id)
    assert latest.assessment_id == written.assessment_id

    verdicts = await read.list_novelty_verdicts(
        h.db, assessment_id=written.assessment_id)
    assert len(verdicts) == 2

    summary = await read.get_novelty_summary(
        h.db, assessment_id=written.assessment_id)
    assert summary.semantic_new_count == 1
    assert summary.raw_circuit_count == 2


@case
async def test_P_reading_a_run_that_was_never_assessed_is_None_not_an_error(h, novelty):
    from app.services import llm_circuit_novelty_read_service as read

    target_id, _, _ = await _completed_run(h, circuit_names=["Unassessed"])
    assert await read.get_latest_novelty_assessment(h.db, run_id=target_id) is None


@case
async def test_Q_reading_an_unknown_assessment_id_raises_not_found(h, novelty):
    from app.services import llm_circuit_novelty_read_service as read

    with pytest.raises(read.NoveltyAssessmentNotFound):
        await read.get_novelty_assessment(h.db, assessment_id="NGIQ-DCN-99999999")


def test_R_the_read_service_cannot_call_a_provider():
    """Structural, not a promise: the module imports no provider at all."""
    source = (BACKEND / "app/services/llm_circuit_novelty_read_service.py").read_text(
        encoding="utf-8")

    for forbidden in ("get_llm_provider", "llm_providers", "complete_json",
                      "llm_model_policy", "settings_service"):
        assert forbidden not in source, forbidden


# ===========================================================================
# the storage layer holds the recall-first rule itself
# ===========================================================================
@case
async def test_S_the_database_refuses_a_semantic_count_that_breaks_the_rule(h, novelty):
    """NEW + BORDERLINE is enforced by CHECK, so no writer can redefine it."""
    from sqlalchemy import text

    _, _, seed_pk = await _completed_run(h, circuit_names=[])
    run_pk = (await h.rows(
        "SELECT run_pk FROM knowledge_discovery_runs ORDER BY created_at DESC LIMIT 1"))[0]["run_pk"]

    bad = text(
        "INSERT INTO discovery_circuit_novelty_assessments"
        " (target_run_pk, seed_region_pk, discovery_view, query_strategy_version,"
        "  provider, model_name, assessor_prompt_key, assessor_prompt_version,"
        "  raw_circuit_count, new_count, alias_count, reformulation_count,"
        "  borderline_count, semantic_new_count,"
        "  prior_completed_run_count, prior_circuit_count)"
        " VALUES (:r, :s, 'V', 'G4HR1/V', 'deepseek', 'deepseek-flash', 'k', '1.0.0',"
        "         2, 1, 0, 0, 1, 99, 0, 0)"
    )
    with pytest.raises(Exception):
        await h.db.execute(bad, {"r": run_pk, "s": seed_pk})


@case
async def test_T_the_database_refuses_an_ALIAS_with_no_matched_circuit(h, novelty):
    """A claim about the past must point at a row that exists.

    Written by hand on purpose: this is the CHECK doing the refusing, not the
    service. A future writer that skips the service must still be unable to
    store an ALIAS that matches nothing.
    """
    from sqlalchemy import text

    target_id, target_pk, _ = await _completed_run(h, circuit_names=["One", "Two"])
    first, second = await _circuit_ids(h, target_pk)
    written, _ = await _run(novelty, h, target_id, _verdicts(
        (first, "NEW", None), (second, "NEW", None)))

    bad = text(
        "INSERT INTO discovery_circuit_novelty_verdicts"
        " (assessment_pk, candidate_pk, novelty_class, matched_prior_candidate_pk,"
        "  short_reason)"
        " VALUES ((SELECT assessment_pk FROM discovery_circuit_novelty_assessments"
        "          WHERE assessment_id = :a),"
        "         (SELECT candidate_pk FROM discovery_candidates"
        "           WHERE candidate_id = :c AND candidate_type = 'region'),"
        "         'ALIAS', NULL, 'x')"
    )
    region_pk = (await h.rows(
        "SELECT candidate_id FROM discovery_candidates"
        " WHERE discovery_run_pk = :p AND candidate_type = 'region' LIMIT 1",
        p=target_pk))[0]["candidate_id"]

    with pytest.raises(Exception) as exc:
        await h.db.execute(bad, {"a": written.assessment_id, "c": region_pk})
    assert "ck_dcnv_match_rule" in str(exc.value)


@case
async def test_U_the_database_refuses_a_NEW_that_claims_a_match(h, novelty):
    """The mirror of T: novelty must not name a match."""
    from sqlalchemy import text

    target_id, target_pk, _ = await _completed_run(h, circuit_names=["One", "Two"])
    first, second = await _circuit_ids(h, target_pk)
    written, _ = await _run(novelty, h, target_id, _verdicts(
        (first, "NEW", None), (second, "NEW", None)))
    region_pk = (await h.rows(
        "SELECT candidate_id FROM discovery_candidates"
        " WHERE discovery_run_pk = :p AND candidate_type = 'region' LIMIT 1",
        p=target_pk))[0]["candidate_id"]

    bad = text(
        "INSERT INTO discovery_circuit_novelty_verdicts"
        " (assessment_pk, candidate_pk, novelty_class, matched_prior_candidate_pk,"
        "  short_reason)"
        " VALUES ((SELECT assessment_pk FROM discovery_circuit_novelty_assessments"
        "          WHERE assessment_id = :a),"
        "         (SELECT candidate_pk FROM discovery_candidates"
        "           WHERE candidate_id = :c AND candidate_type = 'region'),"
        "         'NEW', (SELECT candidate_pk FROM discovery_candidates"
        "                 WHERE candidate_id = :c2 AND candidate_type = 'region'), 'x')"
    )
    region_ids = [r["candidate_id"] for r in await h.rows(
        "SELECT candidate_id FROM discovery_candidates"
        " WHERE discovery_run_pk = :p AND candidate_type = 'region'",
        p=target_pk)]
    with pytest.raises(Exception) as exc:
        await h.db.execute(bad, {"a": written.assessment_id,
                                 "c": region_ids[0], "c2": region_ids[0]})
    assert "ck_dcnv_match_rule" in str(exc.value)
