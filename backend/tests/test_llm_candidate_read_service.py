"""Phase P0-2A — LLM Discovery candidate READ service.

These exercise the REAL read service against the REAL isolated test database,
because what is under test is the interaction between the queries and the
constraints P0-1 persists under. Candidates are written through the REAL P0-1
persistence service, so a read is always reading something the writer genuinely
produced.

Isolation
---------
Each test runs inside an outer transaction that is always ROLLED BACK. The
session joins that transaction with ``join_transaction_mode="create_savepoint"``,
so the writer's own ``session.commit()`` releases a SAVEPOINT rather than
committing for real. The whole test body runs in ONE event loop.

If the isolated database or the migration is missing, the tests SKIP loudly.
"""
from __future__ import annotations

import asyncio
import ast
import json
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

import pytest

if sys.platform == "win32":  # psycopg async cannot use the Proactor loop
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

BACKEND = Path(__file__).resolve().parents[1]
E2E_DB = os.environ.get("TEST_E2E_DB", "neurographiq_human_brain_v1_e2e")

FALLBACK_SEED = "NGIQ-BR-00001169"          # Left Hippocampus


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
    database is loaded from a different dump, so the same region carries a
    different numeric suffix there."""
    try:
        import psycopg

        with psycopg.connect(_dsn(async_=False)) as conn:
            row = conn.execute(
                "SELECT entity_id FROM kg_entities"
                " WHERE entity_type = 'brain_region' AND name_en = 'Left Hippocampus'"
                " ORDER BY entity_id LIMIT 1").fetchone()
        return row[0] if row else FALLBACK_SEED
    except Exception:  # pragma: no cover - the tests skip later anyway
        return FALLBACK_SEED


SEED = _resolve_seed()
UNKNOWN_SEED = "NGIQ-BR-99999999"


@dataclass
class Session:
    """The async session, plus the small read helpers the tests need."""

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
    """Run an async test in one event loop, inside a rolled-back transaction.

    The name is copied over by hand rather than with ``functools.wraps``:
    ``wraps`` sets ``__wrapped__``, which makes pytest follow it back to the
    async signature and demand the harness as a fixture.
    """

    def wrapper() -> None:
        asyncio.run(_drive(fn))

    wrapper.__name__ = fn.__name__
    wrapper.__qualname__ = fn.__qualname__
    wrapper.__doc__ = fn.__doc__
    return wrapper


def _service():
    from app.services import llm_candidate_read_service

    return llm_candidate_read_service


async def _drive(fn: Callable[[Session, Any], Awaitable[None]]) -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(_dsn(), poolclass=NullPool)
    try:
        connection = await engine.connect()
    except Exception as exc:  # pragma: no cover - environment dependent
        await engine.dispose()
        pytest.skip(f"isolated test database unavailable: {type(exc).__name__}")

    transaction = await connection.begin()
    db = AsyncSession(bind=connection, join_transaction_mode="create_savepoint")
    try:
        if (
            await connection.execute(
                text("SELECT to_regclass('public.discovery_candidates')")
            )
        ).scalar_one() is None:
            pytest.skip("gate7b_016 not applied to the isolated test database")

        await fn(Session(db), _service())
    finally:
        await db.close()
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


# ===========================================================================
# fixtures
# ===========================================================================
def _one_of_each(seed_entity_id: str) -> dict[str, Any]:
    """Exactly one candidate of each type, shaped to survive the real parser."""
    return {
        "schema_version": "1.0",
        "seed_entity_id": seed_entity_id,
        "summary": "One candidate of each kind.",
        "regions": [
            {
                "local_id": "region_1",
                "confidence": 0.72,
                "name": "CA1 field of the hippocampus",
                "name_en": "CA1",
                "hemisphere": "LEFT",
                "species_taxon_id": "9606",
                "relation_to_seed": "AFFERENT",
                "rationale": "Receives the seed's principal output.",
            }
        ],
        "connections": [
            {
                "local_id": "connection_1",
                "confidence": 0.55,
                "species_context": {"scope": "NON_HUMAN", "taxon_ids": [10116]},
                "source_ref": "region_1",
                "target_ref": "SEED",
                "connection_type": "PROJECTION",
                "directionality": "DIRECTED",
                "rationale": "Reported in rodent work.",
            }
        ],
        "circuits": [
            {
                "local_id": "circuit_1",
                "confidence": 0.61,
                "species_context": {"scope": "UNKNOWN", "taxon_ids": []},
                "name": "Trisynaptic circuit",
                "description": "A candidate multi-region pathway.",
                "region_refs": ["region_1", "SEED"],
                "connection_refs": ["connection_1"],
                "function_refs": ["function_1"],
                "topology_hint": "FEEDFORWARD",
                "rationale": "One plausible ordering of the proposed edges.",
            }
        ],
        "functions": [
            {
                "local_id": "function_1",
                "confidence": 0.48,
                "species_context": {"scope": "UNKNOWN", "taxon_ids": []},
                "label": "episodic memory encoding",
                "description": "A function the seed may serve.",
                "related_region_refs": ["region_1"],
                "related_circuit_refs": ["circuit_1"],
                "rationale": "Suggested by the proposed pathway.",
            }
        ],
        "source_hints": [{"title": "A remembered review", "pmid": "30000001"}],
        "warnings": [],
    }


def _two_of_each(seed_entity_id: str) -> dict[str, Any]:
    """Two candidates per type, every reference resolvable.

    ``region_10`` sits beside ``region_2`` on purpose: TEXT ordering puts
    ``region_10`` FIRST, a numeric ordering would put it last. Without a pair
    like this the ordering under test is unobservable — and note that
    ``ORDER BY local_id`` alone is provably identical to ordering by
    ``candidate_type, local_id``, because LOCAL_ID_PATTERN makes the prefix
    encode the type and the four prefixes sort in the same order as the four
    type values. The local_id key is what this fixture actually exercises.
    """
    return {
        "schema_version": "1.0",
        "seed_entity_id": seed_entity_id,
        "summary": "Two candidates of each kind.",
        "regions": [
            {"local_id": "region_2", "confidence": 0.7, "name": "CA1",
             "relation_to_seed": "AFFERENT"},
            {"local_id": "region_10", "confidence": 0.6, "name": "CA3",
             "relation_to_seed": "EFFERENT"},
        ],
        "connections": [
            {"local_id": "connection_1", "confidence": 0.5,
             "species_context": {"scope": "UNKNOWN", "taxon_ids": []},
             "source_ref": "region_2", "target_ref": "SEED",
             "connection_type": "PROJECTION", "directionality": "DIRECTED"},
            {"local_id": "connection_2", "confidence": 0.4,
             "species_context": {"scope": "UNKNOWN", "taxon_ids": []},
             "source_ref": "SEED", "target_ref": "region_10",
             "connection_type": "FUNCTIONAL", "directionality": "UNKNOWN"},
        ],
        "circuits": [
            {"local_id": "circuit_1", "confidence": 0.6,
             "species_context": {"scope": "UNKNOWN", "taxon_ids": []},
             "name": "Pathway one", "region_refs": ["region_2", "SEED"],
             "connection_refs": ["connection_1"], "function_refs": ["function_1"],
             "topology_hint": "FEEDFORWARD"},
            {"local_id": "circuit_2", "confidence": 0.5,
             "species_context": {"scope": "UNKNOWN", "taxon_ids": []},
             "name": "Pathway two", "region_refs": ["region_10", "SEED"],
             "connection_refs": ["connection_2"], "function_refs": ["function_2"],
             "topology_hint": "LOOP"},
        ],
        "functions": [
            {"local_id": "function_1", "confidence": 0.5,
             "species_context": {"scope": "UNKNOWN", "taxon_ids": []},
             "label": "encoding", "related_region_refs": ["region_2"],
             "related_circuit_refs": ["circuit_1"]},
            {"local_id": "function_2", "confidence": 0.4,
             "species_context": {"scope": "UNKNOWN", "taxon_ids": []},
             "label": "recall", "related_region_refs": ["region_10"],
             "related_circuit_refs": ["circuit_2"]},
        ],
        "source_hints": [],
        "warnings": [],
    }


def _parsed(raw: dict[str, Any]):
    """Through the REAL parser: nothing is written or read that it rejected."""
    from app.services.llm_discovery_parser import parse_llm_discovery_response

    parsed = parse_llm_discovery_response(raw, seed_entity_id=raw["seed_entity_id"])
    assert parsed.ok, f"fixture must be parser-valid: {parsed.error}"
    return parsed.data


async def _new_run(h: Session, *, entity_id: str = SEED, discovery_type: str = "LLM_DISCOVERY"):
    """A real, committed run of the given route. Returns (run_id, run_pk, seed_pk)."""
    from app.services import knowledge_discovery_run_lifecycle_service as lifecycle

    run = await lifecycle.create_discovery_run(
        h.db, entity_id=entity_id, discovery_type=discovery_type
    )
    run = await lifecycle.start_discovery_run(h.db, run.run_id)
    keys = await h.rows(
        "SELECT run_pk, seed_region_pk FROM knowledge_discovery_runs WHERE run_id = :r",
        r=run.run_id,
    )
    return run.run_id, int(keys[0]["run_pk"]), int(keys[0]["seed_region_pk"])


async def _finish(h: Session, run_id: str) -> None:
    """Terminal, so a second run for the same seed + route may be created."""
    from app.services import knowledge_discovery_run_lifecycle_service as lifecycle

    await lifecycle.complete_discovery_run(h.db, run_id, "CANDIDATES_FOUND")


async def _persist(h: Session, run_pk: int, seed_pk: int, raw: dict[str, Any]) -> int:
    """Write through the REAL P0-1 persistence service."""
    from app.services import llm_candidate_persistence_service as writer

    summary = await writer.persist_discovery_candidates(
        h.db, discovery_run_pk=run_pk, seed_region_pk=seed_pk, data=_parsed(raw)
    )
    return summary.created


async def _seed_with(h: Session, raw: dict[str, Any], *, finish: bool = True):
    """Create one LLM run and persist `raw` into it. Returns (run_id, rows)."""
    run_id, run_pk, seed_pk = await _new_run(h)
    created = await _persist(h, run_pk, seed_pk, raw)
    if finish:
        await _finish(h, run_id)
    return run_id, created


async def _insert_row(
    h: Session, *, run_pk: int, seed_pk: int, candidate_type: str, local_id: str
) -> None:
    """A raw candidate row, bypassing the writer.

    Used only to build states the writer would never produce (a candidate under
    a LITERATURE run), so the read service is tested against the hostile case.
    """
    from sqlalchemy import text

    await h.db.execute(
        text(
            "INSERT INTO discovery_candidates"
            " (discovery_run_pk, seed_region_pk, candidate_type, local_id, name, payload_json)"
            " VALUES (:r, :s, :t, :l, :n, '{}'::jsonb)"
        ),
        {"r": run_pk, "s": seed_pk, "t": candidate_type, "l": local_id, "n": local_id},
    )


class _RecordingSession:
    """Wraps the real session and records every statement it is asked to run."""

    def __init__(self, db: Any) -> None:
        self._db = db
        self.statements: list[str] = []

    async def execute(self, stmt: Any, params: Any = None) -> Any:
        self.statements.append(" ".join(str(stmt).split()))
        return await self._db.execute(stmt, params)


# ===========================================================================
# A / B — run-scoped read, and payload fidelity
# ===========================================================================
@case
async def test_A_run_scoped_read_returns_all_four_candidate_types(h, svc):
    run_id, created = await _seed_with(h, _one_of_each(SEED))
    assert created == 4

    items = await svc.list_candidates_for_run(h.db, run_id=run_id)
    assert len(items) == 4
    assert {i.candidate_type for i in items} == {
        "region", "connection", "circuit", "function"
    }

    for item in items:
        assert item.candidate_id.startswith("NGIQ-DC-")
        assert item.run_id == run_id
        assert item.seed_entity_id == SEED
        assert item.status == "proposed"
        assert item.local_id.startswith(f"{item.candidate_type}_")
        assert isinstance(item.payload, dict) and item.payload
        assert isinstance(item.confidence, float) and 0.0 <= item.confidence <= 1.0
        assert isinstance(item.created_at, datetime)
        assert isinstance(item.updated_at, datetime)

    by_type = {i.candidate_type: i for i in items}
    assert by_type["region"].name == "CA1 field of the hippocampus"
    assert by_type["circuit"].name == "Trisynaptic circuit"
    assert by_type["function"].name == "episodic memory encoding"
    assert by_type["connection"].name == "region_1 -> SEED [PROJECTION]"


@case
async def test_B_payload_round_trips_exactly_as_persisted(h, svc):
    """§8 — the payload is the persisted typed candidate, not a reconstruction."""
    run_id, _ = await _seed_with(h, _one_of_each(SEED))
    items = await svc.list_candidates_for_run(h.db, run_id=run_id)
    payloads = {i.candidate_type: i.payload for i in items}

    connection = payloads["connection"]
    assert connection["source_ref"] == "region_1"
    assert connection["target_ref"] == "SEED"
    assert connection["connection_type"] == "PROJECTION"
    assert connection["directionality"] == "DIRECTED"
    assert connection["species_context"] == {"scope": "NON_HUMAN", "taxon_ids": [10116]}

    circuit = payloads["circuit"]
    assert circuit["region_refs"] == ["region_1", "SEED"]
    assert circuit["connection_refs"] == ["connection_1"]
    assert circuit["function_refs"] == ["function_1"]
    assert circuit["topology_hint"] == "FEEDFORWARD"
    assert circuit["species_context"] == {"scope": "UNKNOWN", "taxon_ids": []}

    function = payloads["function"]
    assert function["related_region_refs"] == ["region_1"]
    assert function["related_circuit_refs"] == ["circuit_1"]

    assert payloads["region"]["relation_to_seed"] == "AFFERENT"

    # ...and they equal the typed candidate the parser produced, field for field.
    data = _parsed(_one_of_each(SEED))
    for kind, candidate in (
        ("region", data.regions[0]), ("connection", data.connections[0]),
        ("circuit", data.circuits[0]), ("function", data.functions[0]),
    ):
        assert payloads[kind] == candidate.model_dump(mode="json"), kind


# ===========================================================================
# C — deterministic run-scoped ordering
# ===========================================================================
@case
async def test_C_run_scoped_order_is_deterministic(h, svc):
    """Ordered by candidate_type then local_id — both keys exercised."""
    run_id, created = await _seed_with(h, _two_of_each(SEED))
    assert created == 8

    items = await svc.list_candidates_for_run(h.db, run_id=run_id)
    assert [(i.candidate_type, i.local_id) for i in items] == [
        ("circuit", "circuit_1"), ("circuit", "circuit_2"),
        ("connection", "connection_1"), ("connection", "connection_2"),
        ("function", "function_1"), ("function", "function_2"),
        ("region", "region_10"), ("region", "region_2"),
    ]

    # Reading twice yields the identical order: nothing depends on plan order.
    again = await svc.list_candidates_for_run(h.db, run_id=run_id)
    assert [i.candidate_id for i in again] == [i.candidate_id for i in items]


# ===========================================================================
# D / E — seed-scoped read, across runs and in run chronology
# ===========================================================================
@case
async def test_D_seed_scoped_read_spans_every_llm_run_of_that_seed(h, svc):
    run_a, _ = await _seed_with(h, _one_of_each(SEED))
    run_b, _ = await _seed_with(h, _two_of_each(SEED))

    items = await svc.list_candidates_for_seed(h.db, entity_id=SEED)
    assert len(items) == 12, "4 from the first run + 8 from the second"
    assert {i.run_id for i in items} == {run_a, run_b}
    assert {i.seed_entity_id for i in items} == {SEED}


@case
async def test_E_seed_scoped_read_shows_the_newest_run_first(h, svc):
    """Run chronology is explicit, so ordering cannot pass by accident."""
    from sqlalchemy import text

    older, _ = await _seed_with(h, _one_of_each(SEED))
    newer, _ = await _seed_with(h, _one_of_each(SEED))

    # now() is the TRANSACTION timestamp, so two runs in one test share it.
    # History is therefore set explicitly rather than hoped for.
    base = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
    for run_id, stamp in ((older, base), (newer, base + timedelta(hours=1))):
        await h.db.execute(
            text("UPDATE knowledge_discovery_runs SET created_at = :ts WHERE run_id = :r"),
            {"ts": stamp, "r": run_id},
        )

    items = await svc.list_candidates_for_seed(h.db, entity_id=SEED)
    assert len(items) == 8
    assert [i.run_id for i in items] == [newer] * 4 + [older] * 4

    # Within a run the order is still candidate_type then local_id.
    assert [i.candidate_type for i in items[:4]] == [
        "circuit", "connection", "function", "region"
    ]


# ===========================================================================
# F / G — empty versus absent, for a run
# ===========================================================================
@case
async def test_F_a_known_llm_run_with_no_candidates_is_empty_not_missing(h, svc):
    run_id, created = await _seed_with(h, _one_of_each(SEED))
    empty_run, _, _ = await _new_run(h)
    assert created == 4

    assert await svc.list_candidates_for_run(h.db, run_id=empty_run) == []
    # ...and the populated run is unaffected.
    assert len(await svc.list_candidates_for_run(h.db, run_id=run_id)) == 4


@case
async def test_G_an_unknown_or_malformed_run_id_raises_not_found(h, svc):
    with pytest.raises(svc.DiscoveryCandidateRunNotFound):
        await svc.list_candidates_for_run(h.db, run_id=str(uuid.uuid4()))

    # A malformed id cannot identify any run, so it is "not found" — and it must
    # never reach the uuid column comparison, which would be a 500.
    with pytest.raises(svc.DiscoveryCandidateRunNotFound):
        await svc.list_candidates_for_run(h.db, run_id="not-a-uuid")


# ===========================================================================
# H / K — the two discovery channels stay independent
# ===========================================================================
@case
async def test_H_a_non_llm_run_is_rejected_even_when_it_holds_candidate_rows(h, svc):
    """§4 — explicit rejection, never a silent empty page."""
    lit_run, lit_pk, seed_pk = await _new_run(h, discovery_type="LITERATURE_DISCOVERY")
    # A row the writer would never create: a candidate under a literature run.
    await _insert_row(h, run_pk=lit_pk, seed_pk=seed_pk,
                      candidate_type="region", local_id="region_1")

    assert await h.count(
        "SELECT count(*) FROM discovery_candidates WHERE discovery_run_pk = :p",
        p=lit_pk,
    ) == 1, "the hostile row must really be there, or this test proves nothing"

    with pytest.raises(svc.DiscoveryCandidateRunNotLlm) as excinfo:
        await svc.list_candidates_for_run(h.db, run_id=lit_run)
    assert excinfo.value.discovery_type == "LITERATURE_DISCOVERY"


@case
async def test_K_seed_scoped_read_excludes_non_llm_runs(h, svc):
    llm_run, _ = await _seed_with(h, _one_of_each(SEED))
    lit_run, lit_pk, seed_pk = await _new_run(h, discovery_type="LITERATURE_DISCOVERY")
    await _insert_row(h, run_pk=lit_pk, seed_pk=seed_pk,
                      candidate_type="circuit", local_id="circuit_9")

    items = await svc.list_candidates_for_seed(h.db, entity_id=SEED)
    assert len(items) == 4, "only the LLM run's candidates may appear"
    assert {i.run_id for i in items} == {llm_run}
    assert lit_run not in {i.run_id for i in items}


# ===========================================================================
# I / J — empty versus absent, for a seed
# ===========================================================================
@case
async def test_I_a_known_brain_region_with_no_llm_candidates_is_empty(h, svc):
    assert await svc.list_candidates_for_seed(h.db, entity_id=SEED) == []


@case
async def test_J_an_unknown_brain_region_raises_not_found(h, svc):
    with pytest.raises(svc.DiscoveryCandidateSeedNotFound):
        await svc.list_candidates_for_seed(h.db, entity_id=UNKNOWN_SEED)


# ===========================================================================
# L / M / N — architecture guards
# ===========================================================================
def _read_service_source() -> str:
    return Path(_service().__file__).read_text(encoding="utf-8")


def _code_without_prose() -> str:
    """The module's code with docstrings and comments removed.

    The prose in this module talks ABOUT writes ("SELECT only, never a write"),
    so scanning the raw file would match its own documentation.
    """
    src = _read_service_source()
    doc_lines: set[int] = set()
    for node in ast.walk(ast.parse(src)):
        if (isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            doc_lines.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    kept = []
    for i, line in enumerate(src.splitlines(), start=1):
        if i in doc_lines or line.strip().startswith("#"):
            continue
        kept.append(line.split("#", 1)[0])
    return "\n".join(kept)


@case
async def test_L_the_read_service_is_select_only(h, svc):
    """Static: no write verb exists in the code. Dynamic: none is ever issued."""
    code = _code_without_prose()
    for forbidden in ("INSERT INTO", "UPDATE ", "DELETE FROM", "commit(",
                      "session.commit", "add(", "flush("):
        assert forbidden not in code, forbidden

    run_id, _ = await _seed_with(h, _one_of_each(SEED))
    recorder = _RecordingSession(h.db)
    await svc.list_candidates_for_run(recorder, run_id=run_id)
    await svc.list_candidates_for_seed(recorder, entity_id=SEED)

    assert recorder.statements, "the reads must actually issue SQL"
    for sql in recorder.statements:
        assert sql.split(" ", 1)[0].upper() == "SELECT", sql


@case
async def test_M_the_query_count_does_not_grow_with_the_candidate_count(h, svc):
    """§9 — no N+1: two statements either way, for one row or for eight."""
    small_run, small_created = await _seed_with(h, _one_of_each(SEED))
    big_run, big_created = await _seed_with(h, _two_of_each(SEED))
    assert (small_created, big_created) == (4, 8)

    small = _RecordingSession(h.db)
    await svc.list_candidates_for_run(small, run_id=small_run)
    big = _RecordingSession(h.db)
    await svc.list_candidates_for_run(big, run_id=big_run)
    assert len(small.statements) == len(big.statements) == 2

    seed_recorder = _RecordingSession(h.db)
    items = await svc.list_candidates_for_seed(seed_recorder, entity_id=SEED)
    assert len(items) == 12
    assert len(seed_recorder.statements) == 2, "twelve rows, still two statements"


@case
async def test_N_no_internal_primary_key_is_exposed_on_the_dto(h, svc):
    """§5 — storage keys stay in storage."""
    run_id, _ = await _seed_with(h, _one_of_each(SEED))
    items = await svc.list_candidates_for_run(h.db, run_id=run_id)

    fields = set(svc.DiscoveryCandidateReadItem.model_fields)
    assert fields == {
        "candidate_id", "run_id", "seed_entity_id", "candidate_type", "local_id",
        "name", "payload", "confidence", "status", "created_at", "updated_at",
    }
    for internal in ("candidate_pk", "discovery_run_pk", "seed_region_pk"):
        assert internal not in fields, internal

    # And the values really are public identities, not numeric keys.
    for item in items:
        assert isinstance(item.candidate_id, str) and item.candidate_id.startswith("NGIQ-DC-")
        assert str(uuid.UUID(item.run_id)) == item.run_id
        assert item.seed_entity_id.startswith("NGIQ-BR-")
        assert not hasattr(item, "candidate_pk")


# ===========================================================================
# boundary guards (no database needed)
# ===========================================================================
def test_the_seed_query_filters_on_the_llm_route_in_sql_not_in_python():
    """§4 — the channel separation is enforced by the query, so it holds even
    for rows the caller never inspects."""
    svc = _service()
    assert svc.LLM_DISCOVERY == "LLM_DISCOVERY"

    sql = " ".join(str(svc._FOR_SEED_SQL).split())
    assert "r.discovery_type = :discovery_type" in sql
    assert "JOIN knowledge_discovery_runs r" in sql


def test_the_read_service_touches_no_legacy_candidate_or_mirror_table():
    """The only candidate storage this module may name is discovery_candidates."""
    code = _code_without_prose()
    assert "discovery_candidates" in code
    for forbidden in ("candidate_generation_runs", "candidate_brain_regions",
                      "candidate_pools", "mirror_", "final_", "provenance_json",
                      "kg_entities AS", "evidence"):
        assert forbidden not in code, forbidden


def test_the_domain_errors_never_carry_sql_or_database_internals():
    svc = _service()
    for exc in (svc.DiscoveryCandidateRunNotFound("r"),
                svc.DiscoveryCandidateSeedNotFound("e"),
                svc.DiscoveryCandidateRunNotLlm("r", "LITERATURE_DISCOVERY")):
        message = str(exc)
        for forbidden in ("SELECT", "FROM", "WHERE", "discovery_candidates",
                          "run_pk", "seed_region_pk", "psycopg", "Traceback"):
            assert forbidden not in message, (type(exc).__name__, forbidden)
        assert isinstance(exc, svc.DiscoveryCandidateReadError)
