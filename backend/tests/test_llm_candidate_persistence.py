"""LLM Discovery P0-1 — candidate persistence.

These exercise the REAL service against the REAL isolated test database,
because what is under test is the interaction between service logic and database
constraints. A fake would prove only the fake: idempotency, the run-local
local_id guard and "no canonical row was written" are all properties of the
database, not of the Python.

Isolation
---------
Each test runs inside an outer transaction that is always ROLLED BACK. The
session joins that transaction with ``join_transaction_mode="create_savepoint"``,
so the service's own ``session.commit()`` releases a SAVEPOINT rather than
committing for real. The whole test body runs in ONE event loop, so the async
connection never crosses a loop boundary.

If the isolated database or the migration is missing, the tests SKIP loudly --
they never silently pass.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable
from unittest.mock import patch

import pytest

if sys.platform == "win32":  # psycopg async cannot use the Proactor loop
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

BACKEND = Path(__file__).resolve().parents[1]
E2E_DB = os.environ.get("TEST_E2E_DB", "neurographiq_human_brain_v1_e2e")

FALLBACK_SEED = "NGIQ-BR-00001169"          # Left Hippocampus

#: Tables a candidate must never write to. Canonical knowledge, Mirror-era
#: staging and the evidence layer are all on this list on purpose: a proposal
#: that reaches any of them has stopped being a proposal.
CANONICAL_TABLES = (
    "kg_entities",
    "brain_regions",
    "connections",
    "circuits",
    "functions",
    "evidence",
    "knowledge_assertions",
)


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
    """Left Hippocampus, looked up rather than hard-coded.

    The isolated test database is loaded from a different dump than the
    authority database, so the same region carries a different numeric suffix
    there. Hard-coding production's id makes every run-dependent test fail for
    a reason that has nothing to do with what it is testing.
    """
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
    from app.services import llm_candidate_persistence_service

    return llm_candidate_persistence_service


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

    # The transaction is opened BEFORE any statement: engine.connect() would
    # autobegin on the first execute, and a later connection.begin() then fails.
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
# fixtures used by the tests
# ===========================================================================
def _response_json(seed_entity_id: str) -> dict[str, Any]:
    """One valid Phase 3A response: exactly one candidate of each type.

    Shaped to survive the REAL parser, not to look plausible: the circuit cites
    two distinct regions and resolves every one of its refs, because the parser
    rejects a response that does not.
    """
    return {
        "schema_version": "1.0",
        "seed_entity_id": seed_entity_id,
        "summary": "A high-recall sketch of the seed's neighbourhood.",
        "regions": [
            {
                "local_id": "region_1",
                "confidence": 0.72,
                "name": "CA1 field of the hippocampus",
                "name_en": "CA1",
                "hemisphere": "LEFT",
                "species_taxon_id": "9606",
                "relation_to_seed": "AFFERENT",
                "rationale": "CA1 receives the seed's principal output.",
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
                "rationale": "A projection reported in rodent work.",
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
        # Deliberately present, and deliberately ignored: a hint is a literature
        # lead, not a Region/Connection/Circuit/Function candidate.
        "source_hints": [
            {"title": "A remembered review", "authors": ["A. Author"], "year": 2019,
             "pmid": "30000001"},
            {"title": "A remembered study", "doi": "10.1000/remembered"},
        ],
        "warnings": [],
    }


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


def _parsed(seed_entity_id: str = SEED):
    from app.schemas.llm_discovery import LlmDiscoveryResponse

    return LlmDiscoveryResponse.model_validate(_response_json(seed_entity_id))


async def _candidates(h: Session, run_pk: int) -> list[Any]:
    return await h.rows(
        "SELECT * FROM discovery_candidates WHERE discovery_run_pk = :p"
        " ORDER BY candidate_type, local_id",
        p=run_pk,
    )


# ===========================================================================
# A / B — the four types persist, and their typed fields survive
# ===========================================================================
@case
async def test_A_the_four_candidate_types_persist(h, p):
    run_id, run_pk, seed_pk = await _new_run(h)
    summary = await p.persist_discovery_candidates(
        h.db, discovery_run_pk=run_pk, seed_region_pk=seed_pk, data=_parsed()
    )

    assert (summary.created, summary.existing, summary.total) == (4, 0, 4)
    assert summary.by_type == {
        "region": 1, "connection": 1, "circuit": 1, "function": 1
    }

    rows = await _candidates(h, run_pk)
    assert len(rows) == 4
    assert {r["candidate_type"] for r in rows} == {
        "region", "connection", "circuit", "function"
    }
    assert {r["local_id"] for r in rows} == {
        "region_1", "connection_1", "circuit_1", "function_1"
    }
    for row in rows:
        assert row["status"] == "proposed"
        assert row["discovery_run_pk"] == run_pk
        assert row["seed_region_pk"] == seed_pk
        assert row["candidate_id"].startswith("NGIQ-DC-")
        assert row["payload_json"], "a candidate row must carry its typed payload"


@case
async def test_A2_the_recorded_seed_is_the_runs_own_seed(h, p):
    """seed_region_pk comes from the run row, so the two cannot disagree."""
    _, run_pk, seed_pk = await _new_run(h)
    await p.persist_discovery_candidates(
        h.db, discovery_run_pk=run_pk, seed_region_pk=seed_pk, data=_parsed()
    )
    mismatched = await h.count(
        "SELECT count(*) FROM discovery_candidates dc"
        " JOIN knowledge_discovery_runs r ON r.run_pk = dc.discovery_run_pk"
        " WHERE dc.seed_region_pk IS DISTINCT FROM r.seed_region_pk"
    )
    assert mismatched == 0


@case
async def test_B_every_typed_field_survives_json_persistence(h, p):
    """§16.B — the payload is the candidate, not a summary of it."""
    _, run_pk, seed_pk = await _new_run(h)
    await p.persist_discovery_candidates(
        h.db, discovery_run_pk=run_pk, seed_region_pk=seed_pk, data=_parsed()
    )
    payloads = {
        r["candidate_type"]: r["payload_json"] for r in await _candidates(h, run_pk)
    }

    region = payloads["region"]
    assert region["relation_to_seed"] == "AFFERENT"
    assert region["name"] == "CA1 field of the hippocampus"
    assert region["hemisphere"] == "LEFT"

    connection = payloads["connection"]
    assert connection["source_ref"] == "region_1"
    assert connection["target_ref"] == "SEED"
    assert connection["directionality"] == "DIRECTED"
    assert connection["species_context"] == {
        "scope": "NON_HUMAN", "taxon_ids": [10116]
    }

    circuit = payloads["circuit"]
    assert circuit["region_refs"] == ["region_1", "SEED"]
    assert circuit["connection_refs"] == ["connection_1"]
    assert circuit["function_refs"] == ["function_1"]
    assert circuit["topology_hint"] == "FEEDFORWARD"
    assert circuit["species_context"] == {"scope": "UNKNOWN", "taxon_ids": []}

    function = payloads["function"]
    assert function["related_region_refs"] == ["region_1"]
    assert function["related_circuit_refs"] == ["circuit_1"]
    assert function["species_context"] == {"scope": "UNKNOWN", "taxon_ids": []}


@case
async def test_B2_confidence_is_stored_as_parsed(h, p):
    """§9 — stored exactly as parsed. Never recomputed, never 'corrected'."""
    _, run_pk, seed_pk = await _new_run(h)
    data = _parsed()
    await p.persist_discovery_candidates(
        h.db, discovery_run_pk=run_pk, seed_region_pk=seed_pk, data=data
    )
    stored = {
        r["candidate_type"]: float(r["confidence"])
        for r in await _candidates(h, run_pk)
    }
    assert stored == {
        "region": data.regions[0].confidence,
        "connection": data.connections[0].confidence,
        "circuit": data.circuits[0].confidence,
        "function": data.functions[0].confidence,
    }


# ===========================================================================
# C — run-local references stay payload; nothing canonical is created
# ===========================================================================
@case
async def test_C_run_local_refs_are_data_not_foreign_keys(h, p):
    """The only FKs on the table are the run and the seed."""
    _, run_pk, seed_pk = await _new_run(h)
    await p.persist_discovery_candidates(
        h.db, discovery_run_pk=run_pk, seed_region_pk=seed_pk, data=_parsed()
    )

    fk_columns = {
        r["column_name"]
        for r in await h.rows(
            "SELECT kcu.column_name FROM information_schema.table_constraints tc"
            " JOIN information_schema.key_column_usage kcu"
            "   ON kcu.constraint_name = tc.constraint_name"
            "  AND kcu.table_schema = tc.table_schema"
            " WHERE tc.table_name = 'discovery_candidates'"
            "   AND tc.constraint_type = 'FOREIGN KEY'"
        )
    }
    assert fk_columns == {"discovery_run_pk", "seed_region_pk"}

    # The refs are still there — as values inside the payload.
    payloads = {
        r["candidate_type"]: r["payload_json"] for r in await _candidates(h, run_pk)
    }
    assert payloads["circuit"]["region_refs"] == ["region_1", "SEED"]
    assert payloads["circuit"]["connection_refs"] == ["connection_1"]
    assert payloads["connection"]["source_ref"] == "region_1"


@case
async def test_C2_no_candidate_can_hold_a_canonical_shaped_local_id(h, p):
    """§5 at the DATABASE level: a canonical id in local_id is a hard error.

    The service would never produce one -- this proves the column cannot hold
    one even if a future writer tried, which is the difference between a
    convention and a guarantee.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    _, run_pk, seed_pk = await _new_run(h)
    await h.db.execute(text("SAVEPOINT canonical_id_probe"))
    with pytest.raises(IntegrityError):
        await h.db.execute(
            text(
                "INSERT INTO discovery_candidates"
                " (discovery_run_pk, seed_region_pk, candidate_type, local_id, name, payload_json)"
                " VALUES (:r, :s, 'region', 'NGIQ-BR-00000252', 'invented', '{}'::jsonb)"
            ),
            {"r": run_pk, "s": seed_pk},
        )
    await h.db.execute(text("ROLLBACK TO SAVEPOINT canonical_id_probe"))


# ===========================================================================
# D / E / L — idempotency and its exact scope
# ===========================================================================
@case
async def test_D_re_persisting_the_same_response_creates_nothing(h, p):
    _, run_pk, seed_pk = await _new_run(h)
    first = await p.persist_discovery_candidates(
        h.db, discovery_run_pk=run_pk, seed_region_pk=seed_pk, data=_parsed()
    )
    second = await p.persist_discovery_candidates(
        h.db, discovery_run_pk=run_pk, seed_region_pk=seed_pk, data=_parsed()
    )

    assert first.created == 4 and first.existing == 0
    assert second.created == 0 and second.existing == 4
    assert second.by_type == first.by_type
    assert await h.count(
        "SELECT count(*) FROM discovery_candidates WHERE discovery_run_pk = :p", p=run_pk
    ) == 4


@case
async def test_E_the_same_local_id_in_two_runs_is_two_proposals(h, p):
    """Run-local means run-local: `circuit_1` in a second run is a different idea."""
    data = _parsed()
    _, run_a, seed_a = await _new_run(h)
    _, run_b, seed_b = await _new_run(h, discovery_type="LITERATURE_DISCOVERY")

    await p.persist_discovery_candidates(
        h.db, discovery_run_pk=run_a, seed_region_pk=seed_a, data=data
    )
    summary_b = await p.persist_discovery_candidates(
        h.db, discovery_run_pk=run_b, seed_region_pk=seed_b, data=data
    )

    assert summary_b.created == 4, "a second run's identical labels are new proposals"
    circuit_rows = await h.rows(
        "SELECT discovery_run_pk FROM discovery_candidates"
        " WHERE candidate_type = 'circuit' AND local_id = 'circuit_1'"
        " ORDER BY discovery_run_pk"
    )
    assert len(circuit_rows) == 2
    assert {int(r["discovery_run_pk"]) for r in circuit_rows} == {run_a, run_b}


@case
async def test_L_the_unique_constraint_really_rejects_a_duplicate(h, p):
    """Proven by bypassing the service: the guard is the index, not the code."""
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    _, run_pk, seed_pk = await _new_run(h)
    insert = (
        "INSERT INTO discovery_candidates"
        " (discovery_run_pk, seed_region_pk, candidate_type, local_id, name, payload_json)"
        " VALUES (:r, :s, 'circuit', 'circuit_1', 'x', '{}'::jsonb)"
    )
    count = (
        "SELECT count(*) FROM discovery_candidates WHERE discovery_run_pk = :p"
    )

    await h.db.execute(text(insert), {"r": run_pk, "s": seed_pk})
    assert await h.count(count, p=run_pk) == 1

    # The duplicate is isolated in its own savepoint: the rejection must undo
    # the rejected row and nothing else.
    await h.db.execute(text("SAVEPOINT duplicate_probe"))
    with pytest.raises(IntegrityError):
        await h.db.execute(text(insert), {"r": run_pk, "s": seed_pk})
    await h.db.execute(text("ROLLBACK TO SAVEPOINT duplicate_probe"))

    assert await h.count(count, p=run_pk) == 1, "the first row must survive"


# ===========================================================================
# F / G — the two things that must NOT become rows
# ===========================================================================
@case
async def test_F_a_zero_candidate_response_persists_nothing_and_is_not_an_error(h, p):
    from app.schemas.llm_discovery import LlmDiscoveryResponse

    _, run_pk, seed_pk = await _new_run(h)
    empty = LlmDiscoveryResponse.model_validate(
        {"schema_version": "1.0", "seed_entity_id": SEED, "summary": "nothing found",
         "regions": [], "connections": [], "circuits": [], "functions": [],
         "source_hints": [], "warnings": []}
    )
    summary = await p.persist_discovery_candidates(
        h.db, discovery_run_pk=run_pk, seed_region_pk=seed_pk, data=empty
    )

    assert (summary.created, summary.existing, summary.total) == (0, 0, 0)
    assert summary.by_type == {"region": 0, "connection": 0, "circuit": 0, "function": 0}
    assert await h.count(
        "SELECT count(*) FROM discovery_candidates WHERE discovery_run_pk = :p", p=run_pk
    ) == 0

    from app.services.llm_discovery_execution_service import resolve_outcome

    assert resolve_outcome(empty) == "NO_CANDIDATES_FOUND"


@case
async def test_G_source_hints_never_become_candidate_rows(h, p):
    data = _parsed()
    assert len(data.source_hints) == 2, "the fixture must actually carry hints"

    _, run_pk, seed_pk = await _new_run(h)
    await p.persist_discovery_candidates(
        h.db, discovery_run_pk=run_pk, seed_region_pk=seed_pk, data=data
    )

    rows = await _candidates(h, run_pk)
    assert len(rows) == 4, "four candidates, not four candidates plus two hints"
    blob = json.dumps([r["payload_json"] for r in rows])
    assert "remembered" not in blob.lower()


# ===========================================================================
# H / I — integration with the LLM discovery execution
# ===========================================================================
def _stub_provider(raw_text: str, model: str):
    """A provider that returns a canned answer. No network, no credentials."""
    from app.services.llm_providers.base import LlmProviderResponse, LlmProviderUsage

    class _Stub:
        name = "deepseek"

        async def complete_json(self, **_: Any) -> LlmProviderResponse:
            return LlmProviderResponse(
                provider="deepseek",
                model=model,
                raw_text=raw_text,
                parsed_json=json.loads(raw_text),
                usage=LlmProviderUsage(prompt_tokens=10, completion_tokens=20,
                                       total_tokens=30),
                finish_reason="stop",
                request_payload_redacted={},
                response_payload={},
                latency_ms=5,
            )

    return _Stub()


@case
async def test_H_candidates_are_persisted_BEFORE_the_run_is_completed(h, p):
    """§11 — the ordering is the guarantee, so it is asserted at the transition."""
    from app.services import knowledge_discovery_run_lifecycle_service as lifecycle
    from app.services import llm_discovery_execution_service as execution

    observed: dict[str, Any] = {}
    original = lifecycle.complete_discovery_run

    async def _spy(session, run_id, outcome, **kwargs):
        observed["status"] = await h.scalar(
            "SELECT status FROM knowledge_discovery_runs WHERE run_id = :r", r=run_id
        )
        observed["candidates"] = await h.count(
            "SELECT count(*) FROM discovery_candidates dc"
            " JOIN knowledge_discovery_runs r ON r.run_pk = dc.discovery_run_pk"
            " WHERE r.run_id = :r",
            r=run_id,
        )
        return await original(session, run_id, outcome, **kwargs)

    raw = json.dumps(_response_json(SEED))
    with patch.object(lifecycle, "complete_discovery_run", _spy), patch.object(
        execution, "get_llm_provider", lambda name: _stub_provider(raw, execution.effective_deepseek_model(None))
    ):
        result = await execution.execute_llm_discovery(h.db, entity_id=SEED)

    assert observed["status"] == "RUNNING", "the run must still be RUNNING here"
    assert observed["candidates"] == 4, "all four rows must already be stored"
    assert result.run.status == "COMPLETED"
    assert result.run.outcome == "CANDIDATES_FOUND"

    # And they are still readable after the run finished.
    rows = await h.rows(
        "SELECT candidate_type FROM discovery_candidates dc"
        " JOIN knowledge_discovery_runs r ON r.run_pk = dc.discovery_run_pk"
        " WHERE r.run_id = :r",
        r=result.run.run_id,
    )
    assert len(rows) == 4


@case
async def test_I_a_persistence_failure_fails_the_run_and_leaves_no_partial_rows(h, p):
    """§11 / §12 — and the failure is on the LAST candidate, so atomicity is real.

    The four rows are written by one statement in the order region, connection,
    circuit, function. Making the FUNCTION row violate a database rule therefore
    proves the three that came before it were rolled back with it: if
    persistence were row-by-row, they would still be there.

    The injected defect is a projection returning no value at all, which the
    database rejects on `name NOT NULL`. It deliberately does NOT lean on a
    content rule: the table has none for `name`, because the parser is the only
    structural authority for candidate content.
    """
    from app.services import llm_discovery_execution_service as execution

    original_name = p.candidate_name

    def _valueless_function_label(candidate_type, candidate):
        if candidate_type == p.TYPE_FUNCTION:
            return None           # `name` is NOT NULL
        return original_name(candidate_type, candidate)

    raw = json.dumps(_response_json(SEED))
    with patch.object(p, "candidate_name", _valueless_function_label), patch.object(
        execution, "get_llm_provider", lambda name: _stub_provider(raw, execution.effective_deepseek_model(None))
    ):
        with pytest.raises(execution.LlmDiscoveryExecutionError) as excinfo:
            await execution.execute_llm_discovery(h.db, entity_id=SEED)

    assert excinfo.value.code == "LLM_CANDIDATE_PERSISTENCE_FAILED"
    assert excinfo.value.run_id is not None

    row = (await h.rows(
        "SELECT status, outcome, error_code, error_message"
        " FROM knowledge_discovery_runs WHERE run_id = :r", r=excinfo.value.run_id))[0]
    assert row["status"] == "FAILED"
    assert row["outcome"] is None, "a failure is an execution fact, not a result"
    assert row["error_code"] == "LLM_CANDIDATE_PERSISTENCE_FAILED"
    # Bounded: the message must not carry SQL, a constraint name or a traceback.
    assert "INSERT" not in row["error_message"]
    assert "ck_dc" not in row["error_message"]

    assert await h.count(
        "SELECT count(*) FROM discovery_candidates dc"
        " JOIN knowledge_discovery_runs r ON r.run_pk = dc.discovery_run_pk"
        " WHERE r.run_id = :r",
        r=excinfo.value.run_id,
    ) == 0, "no partial set may survive a failed persistence"


# ===========================================================================
# J / K — nothing canonical, nothing raw
# ===========================================================================
@case
async def test_J_no_canonical_knowledge_table_is_written(h, p):
    before = {t: await h.count(f"SELECT count(*) FROM {t}") for t in CANONICAL_TABLES}

    _, run_pk, seed_pk = await _new_run(h)
    await p.persist_discovery_candidates(
        h.db, discovery_run_pk=run_pk, seed_region_pk=seed_pk, data=_parsed()
    )

    after = {t: await h.count(f"SELECT count(*) FROM {t}") for t in CANONICAL_TABLES}
    assert after == before, "a proposal must not create canonical knowledge"


@case
async def test_K_the_payload_carries_no_raw_response_and_no_prompt(h, p):
    from app.schemas.llm_discovery import CircuitCandidate, FunctionCandidate

    _, run_pk, seed_pk = await _new_run(h)
    await p.persist_discovery_candidates(
        h.db, discovery_run_pk=run_pk, seed_region_pk=seed_pk, data=_parsed()
    )

    for row in await _candidates(h, run_pk):
        payload = row["payload_json"]
        # Exactly the typed candidate's own fields -- an extra key would mean
        # something (a provider payload, a prompt echo) leaked into the row.
        model = {
            "region": p.RegionCandidate,
            "connection": p.ConnectionCandidate,
            "circuit": CircuitCandidate,
            "function": FunctionCandidate,
        }[row["candidate_type"]]
        assert set(payload) == set(model.model_fields), row["candidate_type"]

        serialized = json.dumps(payload).lower()
        for forbidden in ("system_prompt", "user_prompt", "reasoning", "api_key",
                          "raw_text", "chain-of-thought"):
            assert forbidden not in serialized, (row["candidate_type"], forbidden)


# ===========================================================================
# M / N / O — DB ⇄ parser contract alignment
# ===========================================================================
# The Phase 3A parser is the ONLY structural authority for candidate content.
# Each test below takes a candidate the REAL parser accepts and proves the
# DATABASE does not reject it, so persistence can never be stricter than the
# contract it stores.
@case
async def test_M_a_blank_name_the_parser_accepts_is_not_rejected_by_the_database(h, p):
    """`RegionCandidate.name` / `FunctionCandidate.label` are plain `str` with no
    min_length, so the frozen contract accepts "". A nonblank CHECK would make
    the table reject a candidate the parser approved — a second authority."""
    from app.services.llm_discovery_parser import parse_llm_discovery_response

    raw = _response_json(SEED)
    raw["regions"][0]["name"] = ""
    raw["functions"][0]["label"] = ""
    parsed = parse_llm_discovery_response(raw, seed_entity_id=SEED)
    assert parsed.ok, f"the frozen parser must accept this: {parsed.error}"

    _, run_pk, seed_pk = await _new_run(h)
    summary = await p.persist_discovery_candidates(
        h.db, discovery_run_pk=run_pk, seed_region_pk=seed_pk, data=parsed.data
    )
    assert summary.created == 4, "a contract-valid blank name must persist"

    names = {r["candidate_type"]: r["name"] for r in await _candidates(h, run_pk)}
    assert names["region"] == "" and names["function"] == ""

    # ...and the constraint that used to make this impossible is really gone.
    constraints = {
        r["conname"] for r in await h.rows(
            "SELECT conname FROM pg_constraint"
            " WHERE conrelid = 'discovery_candidates'::regclass")
    }
    assert "ck_dc_name_not_blank" not in constraints


@case
async def test_N_a_parser_valid_local_id_longer_than_64_characters_persists(h, p):
    """LOCAL_ID_PATTERN caps local_id by SHAPE, not by length. A VARCHAR(64)
    column would reject a contract-valid label with a truncation error."""
    from app.services.llm_discovery_parser import parse_llm_discovery_response

    long_id = "region_" + "1" * 70
    assert len(long_id) > 64

    raw = _response_json(SEED)
    raw["regions"][0]["local_id"] = long_id
    # Every reference must follow, or the parser rejects a dangling ref.
    raw["connections"][0]["source_ref"] = long_id
    raw["circuits"][0]["region_refs"] = [long_id, "SEED"]
    raw["functions"][0]["related_region_refs"] = [long_id]
    parsed = parse_llm_discovery_response(raw, seed_entity_id=SEED)
    assert parsed.ok, f"the frozen parser must accept this: {parsed.error}"

    _, run_pk, seed_pk = await _new_run(h)
    summary = await p.persist_discovery_candidates(
        h.db, discovery_run_pk=run_pk, seed_region_pk=seed_pk, data=parsed.data
    )
    assert summary.created == 4

    stored = await h.scalar(
        "SELECT local_id FROM discovery_candidates"
        " WHERE discovery_run_pk = :p AND candidate_type = 'region'",
        p=run_pk,
    )
    assert stored == long_id, "no truncation and no rejection"

    assert await h.scalar(
        "SELECT data_type FROM information_schema.columns"
        " WHERE table_name = 'discovery_candidates' AND column_name = 'local_id'"
    ) == "text"


@case
async def test_O_confidence_round_trips_without_quantization(h, p):
    """§9 — the parsed value is stored as-is. NUMERIC(4,3) silently returned
    0.123 for 0.123456789, i.e. it recalculated what must not be recalculated."""
    from app.services.llm_discovery_parser import parse_llm_discovery_response

    precise = 0.123456789
    raw = _response_json(SEED)
    for group in ("regions", "connections", "circuits", "functions"):
        raw[group][0]["confidence"] = precise
    parsed = parse_llm_discovery_response(raw, seed_entity_id=SEED)
    assert parsed.ok, parsed.error

    _, run_pk, seed_pk = await _new_run(h)
    await p.persist_discovery_candidates(
        h.db, discovery_run_pk=run_pk, seed_region_pk=seed_pk, data=parsed.data
    )

    rows = await _candidates(h, run_pk)
    assert len(rows) == 4
    for row in rows:
        stored = float(row["confidence"])
        assert stored == precise, (row["candidate_type"], stored)
        assert stored != 0.123, "the value must not be quantized to three decimals"

    # The type itself is asserted, so a future regression to NUMERIC fails here
    # rather than silently truncating in production.
    assert await h.scalar(
        "SELECT data_type FROM information_schema.columns"
        " WHERE table_name = 'discovery_candidates' AND column_name = 'confidence'"
    ) == "double precision"


# ===========================================================================
# vocabulary guards (no database needed, but kept beside their table)
# ===========================================================================
def test_the_candidate_type_vocabulary_matches_the_database_check():
    """gate7b_016 constrains candidate_type to four values. A fifth type added
    on one side only would produce an insert that the database rejects at
    runtime, or a stored row the API cannot represent."""
    from app.services import llm_candidate_persistence_service as p

    sql = (
        BACKEND / "migrations" / "gate7b_016_discovery_candidates.sql"
    ).read_text(encoding="utf-8")
    assert "candidate_type IN ('region', 'connection', 'circuit', 'function')" in sql
    assert set(p.CANDIDATE_TYPES) == {"region", "connection", "circuit", "function"}
    assert p.STATUS_PROPOSED == "proposed"


def test_the_connection_label_is_deterministic_and_resolves_nothing():
    """§8 — no canonical name lookup happens here."""
    from app.schemas.llm_discovery import ConnectionCandidate
    from app.services import llm_candidate_persistence_service as p

    candidate = ConnectionCandidate.model_validate(
        {"local_id": "connection_1", "confidence": 0.5,
         "species_context": {"scope": "UNKNOWN", "taxon_ids": []},
         "source_ref": "region_1", "target_ref": "SEED",
         "connection_type": "PROJECTION", "directionality": "DIRECTED"}
    )
    assert p.candidate_name(p.TYPE_CONNECTION, candidate) == "region_1 -> SEED [PROJECTION]"


def test_an_unknown_candidate_type_fails_closed():
    from app.services import llm_candidate_persistence_service as p

    with pytest.raises(ValueError):
        p.candidate_name("literature", object())


def test_the_summary_never_carries_a_payload_or_an_internal_key():
    """A summary is counts. Returning the rows (or a pk) would defeat the point."""
    from app.services import llm_candidate_persistence_service as p

    fields = set(p.CandidatePersistenceSummary.__dataclass_fields__)
    assert fields == {"created", "existing", "total", "by_type"}
