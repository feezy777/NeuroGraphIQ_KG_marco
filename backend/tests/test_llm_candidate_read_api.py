"""Phase P0-2B — LLM Discovery candidate READ API.

These exercise the REAL router against the REAL read service against the REAL
isolated test database. Candidates are written through the REAL P0-1 writer, so
every assertion is about a payload the system genuinely produced.

Isolation
---------
The app is driven through ``httpx.ASGITransport`` in the SAME event loop as the
test, and ``get_db`` is overridden to hand the endpoints the test's own session.
That is what makes a rolled-back real-database API test possible at all: a
psycopg async connection cannot cross event loops, so ``TestClient`` (which runs
the app in another thread) is not an option here.

Each test runs inside an outer transaction that is ALWAYS rolled back. The
whole test body runs in ONE event loop.

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
from pathlib import Path
from typing import Any, Awaitable, Callable

import pytest

if sys.platform == "win32":  # psycopg async cannot use the Proactor loop
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

BACKEND = Path(__file__).resolve().parents[1]
E2E_DB = os.environ.get("TEST_E2E_DB", "neurographiq_human_brain_v1_e2e")
FALLBACK_SEED = "NGIQ-BR-00001169"          # Left Hippocampus
UNKNOWN_SEED = "NGIQ-BR-99999999"

RUN_URL = "/api/knowledge-production/discovery-runs/{run_id}/llm-candidates"
SEED_URL = "/api/knowledge-production/brain-regions/{entity_id}/llm-candidates"

#: Never reachable through this API. Checked against the raw JSON body, so a
#: field added to the wrong layer would be caught even if unnamed here.
FORBIDDEN_BODY_TOKENS = (
    "candidate_pk", "run_pk", "seed_region_pk", "discovery_run_pk",
    "raw_text", "reasoning", "system_prompt", "user_prompt", "api_key",
    "provider_payload", "request_payload", "chain-of-thought",
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


class _RecordingSession:
    """Wraps the real session so the tests can count and inspect every statement."""

    def __init__(self, db: Any) -> None:
        self._db = db
        self.statements: list[str] = []

    async def execute(self, stmt: Any, params: Any = None) -> Any:
        self.statements.append(" ".join(str(stmt).split()))
        return await self._db.execute(stmt, params)


@dataclass
class Api:
    """What a test needs to talk to the app and to see what it ran."""

    client: Any
    recorder: _RecordingSession

    async def get(self, url: str) -> Any:
        self.recorder.statements.clear()
        return await self.client.get(url)


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


def api_case(fn: Callable[[Session, Api], Awaitable[None]]):
    """Run an async API test in one event loop, inside a rolled-back transaction."""

    def wrapper() -> None:
        asyncio.run(_drive(fn))

    wrapper.__name__ = fn.__name__
    wrapper.__qualname__ = fn.__qualname__
    wrapper.__doc__ = fn.__doc__
    return wrapper


async def _drive(fn: Callable[[Session, Api], Awaitable[None]]) -> None:
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.database import get_db
    from app.main import app

    engine = create_async_engine(_dsn(), poolclass=NullPool)
    try:
        connection = await engine.connect()
    except Exception as exc:  # pragma: no cover - environment dependent
        await engine.dispose()
        pytest.skip(f"isolated test database unavailable: {type(exc).__name__}")

    transaction = await connection.begin()
    db = AsyncSession(bind=connection, join_transaction_mode="create_savepoint")
    recorder = _RecordingSession(db)

    async def _override():
        # The SAME session for every request, so nothing the app does escapes
        # the outer transaction, and every statement is visible to the recorder.
        yield recorder

    app.dependency_overrides[get_db] = _override
    try:
        if (
            await connection.execute(
                text("SELECT to_regclass('public.discovery_candidates')")
            )
        ).scalar_one() is None:
            pytest.skip("gate7b_016 not applied to the isolated test database")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            await fn(Session(db), Api(client=client, recorder=recorder))
    finally:
        app.dependency_overrides.pop(get_db, None)
        await db.close()
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


# ===========================================================================
# fixtures (written through the REAL P0-1 writer)
# ===========================================================================
def _one_of_each(seed_entity_id: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "seed_entity_id": seed_entity_id,
        "summary": "One candidate of each kind.",
        "regions": [
            {"local_id": "region_1", "confidence": 0.72, "name": "CA1 field",
             "relation_to_seed": "AFFERENT"}
        ],
        "connections": [
            {"local_id": "connection_1", "confidence": 0.55,
             "species_context": {"scope": "NON_HUMAN", "taxon_ids": [10116]},
             "source_ref": "region_1", "target_ref": "SEED",
             "connection_type": "PROJECTION", "directionality": "DIRECTED"}
        ],
        "circuits": [
            {"local_id": "circuit_1", "confidence": 0.61,
             "species_context": {"scope": "UNKNOWN", "taxon_ids": []},
             "name": "Trisynaptic circuit",
             "region_refs": ["region_1", "SEED"],
             "connection_refs": ["connection_1"], "function_refs": ["function_1"],
             "topology_hint": "FEEDFORWARD"}
        ],
        "functions": [
            {"local_id": "function_1", "confidence": 0.48,
             "species_context": {"scope": "UNKNOWN", "taxon_ids": []},
             "label": "episodic memory encoding",
             "related_region_refs": ["region_1"], "related_circuit_refs": ["circuit_1"]}
        ],
        "source_hints": [{"title": "A remembered review", "pmid": "30000001"}],
        "warnings": [],
    }


def _two_regions(seed_entity_id: str) -> dict[str, Any]:
    """Two candidates, so ordering and count are non-trivial."""
    raw = _one_of_each(seed_entity_id)
    raw["regions"].append(
        {"local_id": "region_2", "confidence": 0.6, "name": "CA3 field",
         "relation_to_seed": "EFFERENT"}
    )
    raw["connections"].append(
        {"local_id": "connection_2", "confidence": 0.4,
         "species_context": {"scope": "UNKNOWN", "taxon_ids": []},
         "source_ref": "SEED", "target_ref": "region_2",
         "connection_type": "FUNCTIONAL", "directionality": "UNKNOWN"}
    )
    return raw


def _parsed(raw: dict[str, Any]):
    from app.services.llm_discovery_parser import parse_llm_discovery_response

    parsed = parse_llm_discovery_response(raw, seed_entity_id=raw["seed_entity_id"])
    assert parsed.ok, f"fixture must be parser-valid: {parsed.error}"
    return parsed.data


async def _new_run(h: Session, *, entity_id: str = SEED, discovery_type: str = "LLM_DISCOVERY"):
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


async def _persist(h: Session, run_pk: int, seed_pk: int, raw: dict[str, Any]) -> int:
    from app.services import llm_candidate_persistence_service as writer

    summary = await writer.persist_discovery_candidates(
        h.db, discovery_run_pk=run_pk, seed_region_pk=seed_pk, data=_parsed(raw)
    )
    return summary.created


async def _seeded_run(h: Session, raw: dict[str, Any], *, finish: bool = True):
    """One LLM run carrying `raw`. Returns (run_id, created_count)."""
    from app.services import knowledge_discovery_run_lifecycle_service as lifecycle

    run_id, run_pk, seed_pk = await _new_run(h)
    created = await _persist(h, run_pk, seed_pk, raw)
    if finish:
        await lifecycle.complete_discovery_run(h.db, run_id, "CANDIDATES_FOUND")
    return run_id, created


async def _hostile_row(h: Session, *, run_pk: int, seed_pk: int, local_id: str) -> None:
    """A candidate under a run the writer would never produce one for."""
    from sqlalchemy import text

    await h.db.execute(
        text(
            "INSERT INTO discovery_candidates"
            " (discovery_run_pk, seed_region_pk, candidate_type, local_id, name, payload_json)"
            " VALUES (:r, :s, 'region', :l, :l, '{}'::jsonb)"
        ),
        {"r": run_pk, "s": seed_pk, "l": local_id},
    )


# ===========================================================================
# A / B — the two endpoints return real candidates
# ===========================================================================
@api_case
async def test_A_the_run_endpoint_returns_all_four_candidate_types(h, api):
    run_id, created = await _seeded_run(h, _one_of_each(SEED))
    assert created == 4

    response = await api.get(RUN_URL.format(run_id=run_id))
    assert response.status_code == 200
    body = response.json()

    assert set(body) == {"items", "total"}
    assert body["total"] == 4
    assert {i["candidate_type"] for i in body["items"]} == {
        "region", "connection", "circuit", "function"
    }
    for item in body["items"]:
        assert item["candidate_id"].startswith("NGIQ-DC-")
        assert item["run_id"] == run_id
        assert item["seed_entity_id"] == SEED
        assert item["status"] == "proposed"
        assert isinstance(item["payload"], dict) and item["payload"]
        assert isinstance(item["confidence"], float)


@api_case
async def test_B_the_seed_endpoint_returns_candidates_across_runs(h, api):
    run_a, _ = await _seeded_run(h, _one_of_each(SEED))
    run_b, _ = await _seeded_run(h, _two_regions(SEED))

    response = await api.get(SEED_URL.format(entity_id=SEED))
    assert response.status_code == 200
    body = response.json()
    # 4 from the first run + 6 from the second: the endpoint spans runs.
    assert body["total"] == 10
    assert len(body["items"]) == body["total"]
    assert {i["run_id"] for i in body["items"]} == {run_a, run_b}
    assert {i["seed_entity_id"] for i in body["items"]} == {SEED}


# ===========================================================================
# C / D / E — error semantics
# ===========================================================================
@api_case
async def test_C_an_unknown_run_is_404_with_a_structured_code(h, api):
    response = await api.get(RUN_URL.format(run_id=str(uuid.uuid4())))
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "RUN_NOT_FOUND"

    # A malformed id cannot identify any run, so it is also 404 — never a 500.
    malformed = await api.get(RUN_URL.format(run_id="not-a-uuid"))
    assert malformed.status_code == 404
    assert malformed.json()["detail"]["code"] == "RUN_NOT_FOUND"


@api_case
async def test_D_a_non_llm_run_is_409_not_404_and_not_an_empty_200(h, api):
    """The run exists. Saying "not found" would be a false statement about it."""
    lit_run, lit_pk, seed_pk = await _new_run(h, discovery_type="LITERATURE_DISCOVERY")
    await _hostile_row(h, run_pk=lit_pk, seed_pk=seed_pk, local_id="region_1")
    assert await h.count(
        "SELECT count(*) FROM discovery_candidates WHERE discovery_run_pk = :p",
        p=lit_pk,
    ) == 1, "the hostile row must really exist, or this test proves nothing"

    response = await api.get(RUN_URL.format(run_id=lit_run))
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "NOT_AN_LLM_RUN"
    assert detail["discovery_type"] == "LITERATURE_DISCOVERY"


@api_case
async def test_E_an_unknown_brain_region_is_404_with_a_structured_code(h, api):
    response = await api.get(SEED_URL.format(entity_id=UNKNOWN_SEED))
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "BRAIN_REGION_NOT_FOUND"


# ===========================================================================
# F / G — "exists but empty" is a SUCCESS, never a 404
# ===========================================================================
@api_case
async def test_F_a_known_run_with_no_candidates_is_200_and_empty(h, api):
    run_id, _, _ = await _new_run(h)
    response = await api.get(RUN_URL.format(run_id=run_id))
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}


@api_case
async def test_G_a_known_seed_with_no_candidates_is_200_and_empty(h, api):
    response = await api.get(SEED_URL.format(entity_id=SEED))
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}


@api_case
async def test_G2_a_literature_run_under_the_same_seed_contributes_nothing(h, api):
    llm_run, _ = await _seeded_run(h, _one_of_each(SEED))
    _, lit_pk, seed_pk = await _new_run(h, discovery_type="LITERATURE_DISCOVERY")
    await _hostile_row(h, run_pk=lit_pk, seed_pk=seed_pk, local_id="circuit_9")

    body = (await api.get(SEED_URL.format(entity_id=SEED))).json()
    assert body["total"] == 4
    assert {i["run_id"] for i in body["items"]} == {llm_run}


# ===========================================================================
# H / L — what may not leave through this API
# ===========================================================================
@api_case
async def test_H_no_internal_primary_key_appears_in_the_response(h, api):
    run_id, _ = await _seeded_run(h, _one_of_each(SEED))
    for url in (RUN_URL.format(run_id=run_id), SEED_URL.format(entity_id=SEED)):
        body = (await api.get(url)).json()
        item_fields = {k for i in body["items"] for k in i}
        assert item_fields == {
            "candidate_id", "run_id", "seed_entity_id", "candidate_type", "local_id",
            "name", "payload", "confidence", "status", "created_at", "updated_at",
        }
        assert set(body) == {"items", "total"}
        assert "candidate_pk" not in json.dumps(body)


@api_case
async def test_L_no_raw_model_output_or_prompt_reaches_the_response(h, api):
    run_id, _ = await _seeded_run(h, _one_of_each(SEED))
    blob = (await api.get(RUN_URL.format(run_id=run_id))).text

    for token in FORBIDDEN_BODY_TOKENS:
        assert token not in blob, token
    # The response carries the PARSED candidate, not the model's answer text.
    assert "One candidate of each kind." not in blob, "the summary leaked"
    assert "A remembered review" not in blob, "a source_hint leaked"


# ===========================================================================
# I — the API inherits the service's order and invents nothing
# ===========================================================================
@api_case
async def test_I_ordering_is_exactly_the_services_ordering(h, api):
    from app.services import llm_candidate_read_service as svc

    run_id, _ = await _seeded_run(h, _two_regions(SEED))
    await _seeded_run(h, _two_regions(SEED))

    api_ids = [i["candidate_id"] for i in
               (await api.get(RUN_URL.format(run_id=run_id))).json()["items"]]
    service_ids = [i.candidate_id for i in
                   await svc.list_candidates_for_run(h.db, run_id=run_id)]
    assert api_ids == service_ids

    seed_api_ids = [i["candidate_id"] for i in
                    (await api.get(SEED_URL.format(entity_id=SEED))).json()["items"]]
    seed_service_ids = [i.candidate_id for i in
                        await svc.list_candidates_for_seed(h.db, entity_id=SEED)]
    assert seed_api_ids == seed_service_ids, "no second sort authority"


# ===========================================================================
# J / K — read-only, and no candidate-level N+1
# ===========================================================================
@api_case
async def test_J_a_GET_writes_nothing(h, api):
    run_id, _ = await _seeded_run(h, _one_of_each(SEED))
    tables = ("discovery_candidates", "knowledge_discovery_runs")
    before = {t: await h.count(f"SELECT count(*) FROM {t}") for t in tables}

    assert (await api.get(RUN_URL.format(run_id=run_id))).status_code == 200
    assert (await api.get(SEED_URL.format(entity_id=SEED))).status_code == 200

    after = {t: await h.count(f"SELECT count(*) FROM {t}") for t in tables}
    assert after == before

    # ...and every statement the API caused was a SELECT.
    assert api.recorder.statements
    for sql in api.recorder.statements:
        assert sql.split(" ", 1)[0].upper() == "SELECT", sql


@api_case
async def test_J2_statement_count_does_not_grow_with_the_candidate_count(h, api):
    """§8 — no candidate-level N+1 behind the response."""
    small_run, small_n = await _seeded_run(h, _one_of_each(SEED))
    big_run, big_n = await _seeded_run(h, _two_regions(SEED))

    await api.get(RUN_URL.format(run_id=small_run))
    small = len(api.recorder.statements)
    await api.get(RUN_URL.format(run_id=big_run))
    big = len(api.recorder.statements)

    assert (small_n, big_n) == (4, 6), "the fixtures must differ in size"
    assert small == big == 2, (small, big)

    await api.get(SEED_URL.format(entity_id=SEED))
    assert len(api.recorder.statements) == 2, "ten rows across two runs, two statements"


def _router_source() -> str:
    from app.routers import llm_discovery_candidates

    return Path(llm_discovery_candidates.__file__).read_text(encoding="utf-8")


def _router_code_only() -> str:
    """The router's code with docstrings and comments removed.

    Its prose explains the very boundaries being checked ("issues no SQL at
    all"), so scanning the raw file would match the documentation.
    """
    src = _router_source()
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


def test_K_the_router_contains_no_sql_and_no_database_table_name():
    code = _router_code_only()
    for forbidden in ("SELECT", "INSERT", "UPDATE ", "DELETE", "discovery_candidates",
                      "knowledge_discovery_runs", "brain_regions", "kg_entities",
                      "text(", "session.execute", "commit("):
        assert forbidden not in code, forbidden

    # And it really does go through the P0-2A service, not around it.
    assert "llm_candidate_read_service" in code
    assert "list_candidates_for_run" in code
    assert "list_candidates_for_seed" in code


def test_the_router_declares_exactly_its_three_endpoints():
    """Two reads (P0-2B) and one review action (P0-3C1).

    Asserted as an EXACT set, so a route added or removed is visible rather than
    absorbed. P0-3C1 added the third; this is the one place that pins the
    surface, so the review-API tests do not assert it again.
    """
    from app.routers import llm_discovery_candidates

    routes = sorted(
        (sorted(r.methods), r.path)
        for r in llm_discovery_candidates.router.routes
    )
    assert routes == [
        (["GET"], "/api/knowledge-production/brain-regions/{entity_id}/llm-candidates"),
        (["GET"], "/api/knowledge-production/discovery-runs/{run_id}/llm-candidates"),
        (["POST"], "/api/knowledge-production/candidates/{candidate_id}/review"),
    ]


def test_the_router_does_not_re_sort_or_filter_what_the_service_returned():
    """A second ordering authority is exactly what §7 forbids."""
    code = _router_code_only()
    for forbidden in ("sorted(", ".sort(", "reverse(", "filter("):
        assert forbidden not in code, forbidden
