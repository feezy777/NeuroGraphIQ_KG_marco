"""Phase P0-3C2 — Candidate Review History Read API.

Real HTTP transport (``httpx.ASGITransport``), real router, the real P0-3C2 read
service, the real P0-3B writer, the real isolated test database, real candidates
written through the REAL P0-1 writer. Nothing here calls a handler directly:
every assertion is about a GET request, its status code and its JSON body.

Isolation
---------
The app is driven in the SAME event loop as the test, with ``get_db`` overridden
to hand the endpoint the test's own session — which joins an outer transaction
that is ALWAYS rolled back. Every fixture written here therefore disappears, and
nothing this file does can be observed by another test or another run.

Every statement the endpoint executes is captured through SQLAlchemy's
``before_cursor_execute`` event, so "this GET issued SELECTs and nothing else" is
an observation about the wire, not a claim about the source code.

Multi-record history
--------------------
The current contract allows at most ONE review per candidate, so a runtime
two-record history cannot be constructed truthfully — see
``test_the_reader_returns_every_record_it_is_given`` for the exact reason and for
what is proved instead.
"""
from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

import pytest

if sys.platform == "win32":  # psycopg async cannot use the Proactor loop
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

BACKEND = Path(__file__).resolve().parents[1]
E2E_DB = os.environ.get("TEST_E2E_DB", "neurographiq_human_brain_v1_e2e")
AUTHORITY_DB = "neurographiq_human_brain_v1"
FALLBACK_SEED = "NGIQ-BR-00001169"          # Left Hippocampus

HISTORY_URL = "/api/knowledge-production/candidates/{candidate_id}/reviews"
REVIEW_URL = "/api/knowledge-production/candidates/{candidate_id}/review"

#: The seven public item fields. Anything beyond this set is an internal key.
EXPECTED_ITEM_FIELDS = {
    "review_id", "decision", "from_status", "to_status",
    "reviewer", "reviewer_note", "created_at",
}
EXPECTED_BODY_FIELDS = {"candidate_id", "items", "total"}

#: Never reachable through this API.
FORBIDDEN_BODY_TOKENS = (
    "candidate_pk", "review_pk", "discovery_run_pk", "seed_region_pk",
    "INSERT", "UPDATE", "DELETE", "psycopg", "Traceback",
)

#: Statements that would mean this GET tried to change something.
WRITE_KEYWORDS = ("INSERT", "UPDATE", "DELETE", "COMMIT", "TRUNCATE")


def _dsn(async_: bool = True, db: str = E2E_DB) -> str:
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
        cfg.get("POSTGRES_HOST", "127.0.0.1"), cfg.get("POSTGRES_PORT", "5432"), db)


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


@dataclass
class Session:
    db: Any
    #: Every statement the driver executed, in order, for the whole test.
    statements: list[str] = field(default_factory=list)

    async def scalar(self, sql: str, **params: Any) -> Any:
        from sqlalchemy import text

        return (await self.db.execute(text(sql), params)).scalar_one_or_none()

    async def rows(self, sql: str, **params: Any) -> list[Any]:
        from sqlalchemy import text

        return list((await self.db.execute(text(sql), params)).mappings().all())

    async def count(self, sql: str, **params: Any) -> int:
        return int(await self.scalar(sql, **params))

    def mark(self) -> int:
        """Index into ``statements`` — everything after this was one request."""
        return len(self.statements)

    def since(self, mark: int) -> list[str]:
        return self.statements[mark:]


def api_case(fn: Callable[[Session, Any], Awaitable[None]]):
    def wrapper() -> None:
        asyncio.run(_drive(fn))

    wrapper.__name__ = fn.__name__
    wrapper.__qualname__ = fn.__qualname__
    wrapper.__doc__ = fn.__doc__
    return wrapper


async def _drive(fn: Callable[[Session, Any], Awaitable[None]]) -> None:
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import event, text
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

    statements: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _record)

    async def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    try:
        if (
            await connection.execute(
                text("SELECT to_regclass('public.candidate_review_records')")
            )
        ).scalar_one() is None:
            pytest.skip("gate7b_017/018 not applied to the isolated test database")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            await fn(Session(db, statements), client)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _record)
        app.dependency_overrides.pop(get_db, None)
        await db.close()
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


# ===========================================================================
# fixtures — real candidates through the REAL P0-1 writer, real reviews through
# the REAL P0-3B writer over real HTTP
# ===========================================================================
def _one_region(seed_entity_id: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0", "seed_entity_id": seed_entity_id,
        "summary": "One region candidate.",
        "regions": [{"local_id": "region_1", "confidence": 0.72, "name": "CA1 field",
                     "relation_to_seed": "AFFERENT"}],
        "connections": [], "circuits": [], "functions": [],
        "source_hints": [], "warnings": [],
    }


async def _new_run(h: Session, *, discovery_type: str = "LLM_DISCOVERY"):
    from app.services import knowledge_discovery_run_lifecycle_service as lifecycle

    run = await lifecycle.create_discovery_run(
        h.db, entity_id=SEED, discovery_type=discovery_type)
    run = await lifecycle.start_discovery_run(h.db, run.run_id)
    keys = await h.rows(
        "SELECT run_pk, seed_region_pk FROM knowledge_discovery_runs WHERE run_id = :r",
        r=run.run_id)
    return run.run_id, int(keys[0]["run_pk"]), int(keys[0]["seed_region_pk"])


async def _candidate(h: Session) -> str:
    """A real candidate. Its run is completed so the next fixture is not blocked."""
    from app.services import knowledge_discovery_run_lifecycle_service as lifecycle
    from app.services import llm_candidate_persistence_service as writer
    from app.services.llm_discovery_parser import parse_llm_discovery_response

    run_id, run_pk, seed_pk = await _new_run(h)
    parsed = parse_llm_discovery_response(_one_region(SEED), seed_entity_id=SEED)
    assert parsed.ok, parsed.error
    await writer.persist_discovery_candidates(
        h.db, discovery_run_pk=run_pk, seed_region_pk=seed_pk, data=parsed.data)
    await lifecycle.complete_discovery_run(h.db, run_id, "CANDIDATES_FOUND")
    return await h.scalar(
        "SELECT candidate_id FROM discovery_candidates WHERE discovery_run_pk = :p LIMIT 1",
        p=run_pk)


async def _reviewed(h: Session, client: Any, decision: str) -> tuple[str, Any]:
    """Create a candidate and decide it through the REAL POST review endpoint."""
    candidate_id = await _candidate(h)
    response = await client.post(
        REVIEW_URL.format(candidate_id=candidate_id),
        json={"decision": decision, "reviewer": "dr.reviewer", "reviewer_note": "a note"})
    assert response.status_code == 200, response.text
    return candidate_id, response.json()


async def _get(client: Any, candidate_id: str) -> Any:
    return await client.get(HISTORY_URL.format(candidate_id=candidate_id))


async def _snapshot(h: Session, candidate_id: str) -> dict[str, Any]:
    """Everything a GET must leave exactly as it found it.

    ``ctid`` is here on purpose. Comparing visible columns alone is not enough:
    PostgreSQL's ``now()`` is the TRANSACTION start time, so an
    ``UPDATE ... SET updated_at = now()`` inside this test's single transaction
    leaves ``updated_at`` byte-identical and the write would go unnoticed. Every
    UPDATE creates a new row version, which always moves ``ctid`` — so a changed
    ``ctid`` is a write, even one that changed nothing a reader can see.
    """
    rows = await h.rows(
        "SELECT c.status, c.updated_at, c.ctid::text AS candidate_ctid,"
        "       r.status AS run_status, r.ctid::text AS run_ctid"
        " FROM discovery_candidates c"
        " JOIN knowledge_discovery_runs r ON r.run_pk = c.discovery_run_pk"
        " WHERE c.candidate_id = :c", c=candidate_id)
    assert len(rows) == 1, rows
    return dict(rows[0])


async def _review_count(h: Session) -> int:
    return await h.count("SELECT count(*) FROM candidate_review_records")


# ===========================================================================
# 1 — a candidate that has not been reviewed is NOT a missing candidate
# ===========================================================================
@api_case
async def test_1_an_unreviewed_candidate_is_200_with_an_empty_history(h, client):
    candidate_id = await _candidate(h)

    response = await _get(client, candidate_id)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body == {"candidate_id": candidate_id, "items": [], "total": 0}


# ===========================================================================
# 2 / 3 / 4 / 5 / 13 — one decision, one record, exactly the contract's fields
# ===========================================================================
@api_case
async def test_2_3_4_each_decision_appears_as_its_own_record(h, client):
    for decision, to_status in (
        ("ACCEPT", "accepted"), ("REJECT", "rejected"), ("DEFER", "deferred"),
    ):
        candidate_id, posted = await _reviewed(h, client, decision)

        response = await _get(client, candidate_id)
        assert response.status_code == 200, (decision, response.text)
        body = response.json()

        assert body["candidate_id"] == candidate_id, decision
        assert body["total"] == 1, decision
        assert len(body["items"]) == 1, decision

        item = body["items"][0]
        assert item["review_id"] == posted["review_id"], decision
        assert item["decision"] == decision
        assert item["from_status"] == "proposed"
        assert item["to_status"] == to_status
        assert item["reviewer"] == "dr.reviewer"
        assert item["reviewer_note"] == "a note"
        assert item["created_at"] == posted["created_at"], decision


@api_case
async def test_5_the_item_and_body_have_exactly_the_contract_fields(h, client):
    candidate_id, _ = await _reviewed(h, client, "ACCEPT")
    body = (await _get(client, candidate_id)).json()

    assert set(body) == EXPECTED_BODY_FIELDS
    assert set(body["items"][0]) == EXPECTED_ITEM_FIELDS, (
        "the history item is the seven public review fields — no next_gate, "
        "no pk, nothing else"
    )


@api_case
async def test_5b_a_null_note_is_returned_as_null(h, client):
    candidate_id = await _candidate(h)
    await client.post(REVIEW_URL.format(candidate_id=candidate_id),
                      json={"decision": "REJECT", "reviewer": "dr.reviewer"})

    item = (await _get(client, candidate_id)).json()["items"][0]
    assert item["reviewer_note"] is None


@api_case
async def test_13_total_is_the_length_of_items(h, client):
    empty_id = await _candidate(h)
    reviewed_id, _ = await _reviewed(h, client, "DEFER")

    for candidate_id in (empty_id, reviewed_id):
        body = (await _get(client, candidate_id)).json()
        assert body["total"] == len(body["items"]), candidate_id


# ===========================================================================
# 6 — no internal key escapes
# ===========================================================================
@api_case
async def test_6_no_internal_primary_key_leaks_into_the_body(h, client):
    candidate_id, _ = await _reviewed(h, client, "ACCEPT")
    response = await _get(client, candidate_id)

    for token in ("candidate_pk", "review_pk", "discovery_run_pk", "seed_region_pk"):
        assert token not in response.text, token
    for token in ("INSERT", "UPDATE", "SELECT", "Traceback"):
        assert token not in response.text, token


# ===========================================================================
# 7 / 8 — absent candidate, wrong channel (and no traceback either way)
# ===========================================================================
@api_case
async def test_7_an_unknown_candidate_is_404_not_an_empty_history(h, client):
    response = await _get(client, "NGIQ-DC-99999999")

    assert response.status_code == 404, response.text
    assert response.json()["detail"]["code"] == "CANDIDATE_NOT_FOUND"
    assert "items" not in response.text, (
        "'no such candidate' must never be reported as 'not reviewed yet'"
    )


@api_case
async def test_8_a_non_llm_candidate_is_409_and_its_history_is_not_readable(h, client):
    from sqlalchemy import text

    _, lit_pk, seed_pk = await _new_run(h, discovery_type="LITERATURE_DISCOVERY")
    await h.db.execute(
        text("INSERT INTO discovery_candidates"
             " (discovery_run_pk, seed_region_pk, candidate_type, local_id, name, payload_json)"
             " VALUES (:r, :s, 'region', 'region_1', 'hostile', '{}'::jsonb)"),
        {"r": lit_pk, "s": seed_pk})
    hostile = await h.scalar(
        "SELECT candidate_id FROM discovery_candidates WHERE discovery_run_pk = :p", p=lit_pk)
    assert hostile, "the hostile row must exist, or this proves nothing"

    response = await _get(client, hostile)
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "NOT_AN_LLM_CANDIDATE"
    assert detail["discovery_type"] == "LITERATURE_DISCOVERY"


@api_case
async def test_8b_the_two_review_endpoints_fail_identically(h, client):
    """A reader and a reviewer must not disagree about why a request failed.

    The two endpoints raise the SAME error classes, so the bodies are identical
    by construction rather than by two mappings kept in step by hand.
    """
    candidate_id = "NGIQ-DC-99999999"
    got = await _get(client, candidate_id)
    posted = await client.post(REVIEW_URL.format(candidate_id=candidate_id),
                               json={"decision": "ACCEPT", "reviewer": "dr.reviewer"})

    assert got.status_code == posted.status_code == 404
    assert got.json() == posted.json(), (got.text, posted.text)


# ===========================================================================
# 9 / 10 — ordering: chronological, with a decisive tie-break
# ===========================================================================
def test_9_the_history_query_orders_by_created_at_ascending():
    """Ordering is the DATABASE's clause, so it is asserted on the statement."""
    from app.services import llm_candidate_review_read_service as svc

    sql = " ".join(str(svc._HISTORY_SQL).upper().split())
    assert "ORDER BY CREATED_AT ASC, REVIEW_PK ASC" in sql, sql


def test_10_the_tie_break_is_a_total_order_and_is_never_projected():
    """``review_pk`` is the PK (unique), so the ORDER BY is total — and it is
    deliberately absent from the SELECT list, so a stable order does not depend
    on a column the caller can see."""
    from app.services import llm_candidate_review_read_service as svc

    sql = " ".join(str(svc._HISTORY_SQL).upper().split())
    projected = sql.split("FROM")[0]
    assert "REVIEW_PK" not in projected, projected
    assert "REVIEW_ID" in projected, projected


@api_case
async def test_10b_the_executed_statement_carries_the_chronological_order(h, client):
    """The exact clause the endpoint really sent, captured off the wire."""
    candidate_id, _ = await _reviewed(h, client, "DEFER")

    mark = h.mark()
    await _get(client, candidate_id)
    history = [s for s in h.since(mark) if "candidate_review_records" in s]
    assert len(history) == 1, history
    assert "ORDER BY created_at ASC, review_pk ASC" in history[0], history[0]


# NOTE: "the reader does not re-sort" is proved in
# test_the_reader_returns_every_record_it_is_given below, which hands the real
# service three rows in a deliberately non-sorted order (DEFER, REJECT, ACCEPT)
# and requires them back in exactly that order.


# ===========================================================================
# 11 / 12 / 14 — a GET changes nothing
# ===========================================================================
@api_case
async def test_11_a_history_read_does_not_mutate_the_candidate_or_its_run(h, client):
    candidate_id, _ = await _reviewed(h, client, "ACCEPT")
    before = await _snapshot(h, candidate_id)

    assert (await _get(client, candidate_id)).status_code == 200
    assert (await _get(client, candidate_id)).status_code == 200   # twice: no drift

    assert await _snapshot(h, candidate_id) == before, (
        "status, updated_at and run status must all be untouched by a read"
    )


@api_case
async def test_12_a_history_read_neither_creates_nor_removes_review_rows(h, client):
    candidate_id, _ = await _reviewed(h, client, "ACCEPT")
    before = await _review_count(h)

    assert (await _get(client, candidate_id)).status_code == 200
    assert await _review_count(h) == before

    unreviewed = await _candidate(h)
    assert (await _get(client, unreviewed)).status_code == 200
    assert await _review_count(h) == before, (
        "reading an empty history must not create a placeholder record"
    )


@api_case
async def test_14_the_get_executes_only_selects_and_exactly_two_of_them(h, client):
    """Statement-level proof, captured from the driver, not read from the source.

    Every statement the request caused, by first keyword: two SELECTs and
    nothing else that touches data. ``SAVEPOINT`` is allowed through because it
    is the session's own transaction bookkeeping (the harness runs the test
    inside a savepoint), not something the endpoint asked for — and it is
    named explicitly rather than waved through, so a new kind of statement
    appearing here is a failure, not a surprise.
    """
    candidate_id, _ = await _reviewed(h, client, "ACCEPT")

    mark = h.mark()
    assert (await _get(client, candidate_id)).status_code == 200
    window = h.since(mark)

    assert window, "no statement was observed — the listener is not proving anything"
    keywords = [s.strip().split()[0].upper() for s in window]
    assert all(k in ("SELECT", "SAVEPOINT") for k in keywords), window
    assert not [k for k in keywords if k in WRITE_KEYWORDS], window

    selects = [s for s in window if s.strip().split()[0].upper() == "SELECT"]
    assert len(selects) == 2, window
    assert "discovery_candidates" in selects[0], selects[0]      # the channel check
    assert "candidate_review_records" in selects[1], selects[1]  # then the history
    assert "FOR UPDATE" not in " ".join(selects).upper(), (
        "a read must not take a row lock"
    )


def test_14b_the_router_holds_no_sql_for_the_history_route():
    """The two statements live in the read service; the router only delegates."""
    from app.routers import llm_discovery_candidates as router_mod
    from app.services import llm_candidate_review_read_service as svc

    src = Path(router_mod.__file__).read_text(encoding="utf-8")
    assert "list_reviews_for_candidate" in src
    assert "review_read_service" in src

    service_src = Path(svc.__file__).read_text(encoding="utf-8")
    assert "_SCOPE_SQL" in service_src and "_HISTORY_SQL" in service_src


# ===========================================================================
# 15 — the route is really mounted, over real HTTP
# ===========================================================================
@api_case
async def test_15_the_route_is_really_mounted_on_the_app(h, client):
    """Not a handler call: a real request through the ASGI app.

    The 404 is OURS (structured detail), not Starlette's route-not-found, which
    would mean the path was never registered at all.
    """
    from app.main import app

    path = "/api/knowledge-production/candidates/{candidate_id}/reviews"
    assert path in app.openapi()["paths"]
    assert "get" in app.openapi()["paths"][path]

    response = await _get(client, "NGIQ-DC-00000000")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "CANDIDATE_NOT_FOUND"


# ===========================================================================
# 13 (cont.) — multi-record history: what is proved, and why not more
# ===========================================================================
class _Rows:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> "_Rows":
        return self

    def one_or_none(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def all(self) -> list[dict[str, Any]]:
        return list(self._rows)


class _ScriptedSession:
    """Answers the service's two statements from scripted row sets.

    Not a database double for any other purpose: it exists only so a scenario the
    storage layer cannot currently hold can still be driven through the real
    mapping code.
    """

    def __init__(self, *, scope: list[dict[str, Any]], history: list[dict[str, Any]]) -> None:
        self._scope = scope
        self._history = history

    async def execute(self, statement: Any, params: Any = None) -> "_Rows":
        sql = str(statement)
        return _Rows(self._scope if "discovery_candidates" in sql else self._history)


def test_the_reader_returns_every_record_it_is_given():
    """MULTI_REVIEW_RUNTIME_SCENARIO_DEFERRED_UNTIL_REOPEN — see the module docstring.

    A runtime two-record history for ONE candidate cannot be constructed
    truthfully under the frozen contract:

      * ``ck_crr_decision_matches_transition`` (gate7b_018) requires
        ``from_status = 'proposed'`` in ALL THREE legal branches, so every record
        must claim the candidate was ``proposed`` immediately before it;
      * no P0-3A decision produces ``proposed``, so a candidate reaches
        ``proposed`` exactly once and never returns to it;
      * therefore a SECOND record can only be written by making it claim a
        transition that never happened — a fabricated audit record, which this
        phase must not create to make a test convenient.

    What is proved instead: the read service maps EVERY row it is handed, in the
    order it is handed them. The statement has no LIMIT / DISTINCT / GROUP BY
    and projects no collapsible column, and the mapper uses ``.all()`` — so a
    future governed re-open needs no change here.

    This is a service-level proof: a session is scripted to answer the two
    statements the service issues, and the REAL service function is driven with
    more rows than the current contract can hold.
    """
    from app.services import llm_candidate_review_read_service as svc

    rows = [
        {"review_id": "NGIQ-CR-00000001", "decision": "DEFER",
         "from_status": "proposed", "to_status": "deferred",
         "reviewer": "dr.first", "reviewer_note": None,
         "created_at": "2026-01-01T00:00:00Z"},
        {"review_id": "NGIQ-CR-00000002", "decision": "REJECT",
         "from_status": "proposed", "to_status": "rejected",
         "reviewer": "dr.second", "reviewer_note": "later",
         "created_at": "2026-01-02T00:00:00Z"},
        # Identical created_at to the row before it: only the tie-break separates
        # them, so a reader that collapsed same-timestamp records would lose one.
        {"review_id": "NGIQ-CR-00000003", "decision": "ACCEPT",
         "from_status": "proposed", "to_status": "accepted",
         "reviewer": "dr.third", "reviewer_note": None,
         "created_at": "2026-01-02T00:00:00Z"},
    ]
    session = _ScriptedSession(
        scope=[{"candidate_pk": 1, "discovery_type": "LLM_DISCOVERY"}], history=rows)

    items = asyncio.run(
        svc.list_reviews_for_candidate(session, candidate_id="NGIQ-DC-00000001"))

    assert [i.review_id for i in items] == [
        "NGIQ-CR-00000001", "NGIQ-CR-00000002", "NGIQ-CR-00000003"], (
        "all three records, in order: no truncation, no dedup, no latest-only"
    )
    assert [i.decision for i in items] == ["DEFER", "REJECT", "ACCEPT"]
    assert len(items) == len(rows)


def test_the_history_statement_cannot_collapse_rows():
    """The SQL half of the same property: nothing that reduces a row set."""
    from app.services import llm_candidate_review_read_service as svc

    sql = " ".join(str(svc._HISTORY_SQL).upper().split())
    for forbidden in ("LIMIT", "DISTINCT", "GROUP BY", "FETCH FIRST", "OFFSET"):
        assert forbidden not in sql, (forbidden, sql)


# ===========================================================================
# 16 — the authority database is untouched by all of this
# ===========================================================================
def test_16_the_authority_database_is_untouched():
    """Read-only check against the AUTHORITY database.

    gate7b_016/017/018 have never been applied there, so neither table may exist.
    """
    try:
        import psycopg

        conn = psycopg.connect(_dsn(async_=False, db=AUTHORITY_DB))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"authority database unavailable: {type(exc).__name__}")

    with conn:
        assert conn.execute("SELECT current_database()").fetchone()[0] == AUTHORITY_DB
        assert conn.execute(
            "SELECT to_regclass('public.discovery_candidates')").fetchone()[0] is None
        assert conn.execute(
            "SELECT to_regclass('public.candidate_review_records')").fetchone()[0] is None
        assert conn.execute(
            "SELECT count(*) FROM infra.schema_migrations"
            " WHERE filename LIKE '%016%' OR filename LIKE '%017%' OR filename LIKE '%018%'"
        ).fetchone()[0] == 0
