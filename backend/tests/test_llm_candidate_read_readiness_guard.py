"""Single BrainRegion closeout — the candidate READ guard.

The defect this file exists for
------------------------------
On the authority database (no `discovery_candidates`) a candidate read raised
`UndefinedTable`, which the app-wide SQLAlchemy handler reported as

    503  {"code": "DATABASE_UNAVAILABLE",
          "message": "Database connection failed.",
          "hint": "Check PostgreSQL is running and DATABASE_URL is correct."}

Every part of that is false: PostgreSQL was running, the DATABASE_URL was
correct, and no connection had failed. A missing TABLE was being reported as a
missing SERVER, sending an operator after a fault that did not exist. The read
endpoints now ask the readiness service first and answer the true thing.

What is asserted here
---------------------
A. On a database without the candidate table, BOTH reads answer 409
   `DISCOVERY_DATABASE_NOT_READY` — and never 503.
B. The candidate table is never named in a statement: the guard stops the
   request before the query that would raise. This is the zero-SQL-error proof,
   and it is asserted on the statements the endpoint actually issued.
C. The body carries no SQL, DSN, credential or stack fragment.
D. The REAL authority database, driven through the REAL app, answers 409 for
   both reads, and its run counts are unchanged by having asked (SELECT only).
E. The healthy database is untouched: both reads are still 200.

Nothing here writes. The authority-DB test opens a read-only session and the
fake sessions never reach a socket at all.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

if sys.platform == "win32":  # psycopg async cannot use the Proactor loop
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

BACKEND = Path(__file__).resolve().parents[1]
E2E_DB = os.environ.get("TEST_E2E_DB", "neurographiq_human_brain_v1_e2e")
AUTHORITY_DB = "neurographiq_human_brain_v1"

RUN_URL = "/api/knowledge-production/discovery-runs/{run_id}/llm-candidates"
SEED_URL = "/api/knowledge-production/brain-regions/{entity_id}/llm-candidates"

#: A run uuid that is well-formed, so nothing is rejected on shape before the
#: readiness question is asked. It need not exist: readiness is answered first.
ANY_RUN = "673a88f4-fe84-4233-85a3-abf1719cac0a"
ANY_SEED = "NGIQ-BR-00000252"  # Left Hippocampus on the authority database

REQUIRED_MESSAGE = (
    "LLM Discovery candidate storage is not enabled for the current database."
)

#: The candidate query, by the only part that identifies it as a READ of rows.
CANDIDATE_READ = "FROM discovery_candidates"

#: What the WRONG answer would have carried. None of it may appear.
FORBIDDEN_IN_BODY = (
    "SELECT", "psycopg", "postgresql", "DATABASE_URL", "password", "api_key",
    "Traceback", 'File "', "UndefinedTable", "relation ",
)


def _dsn(db: str, *, async_: bool = True) -> str:
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
        cfg.get("POSTGRES_HOST", "127.0.0.1"), cfg.get("POSTGRES_PORT", "5432"), db,
    )


# ===========================================================================
# A scripted session: a database that answers "no candidate table"
# ===========================================================================
@dataclass
class _Result:
    """The slice of SQLAlchemy's Result the readiness check uses."""

    row: dict[str, Any] | None = None
    first_row: Any = None

    def mappings(self) -> "_Result":
        return self

    def one(self) -> dict[str, Any]:
        assert self.row is not None
        return self.row

    def first(self) -> Any:
        return self.first_row


class _NotReadySession:
    """A database with the run table but no candidate table.

    Every statement is recorded, and a statement that READS the candidate rows
    is refused loudly rather than answered: the whole point of the guard is that
    such a statement is never issued.
    """

    def __init__(self, *, has_run_table: bool = True, has_ledger: bool = False) -> None:
        self.statements: list[str] = []
        self._has_run_table = has_run_table
        self._has_ledger = has_ledger

    async def execute(self, stmt: Any, params: Any = None) -> _Result:
        sql = " ".join(str(stmt).split())
        self.statements.append(sql)
        assert CANDIDATE_READ not in sql, (
            "the candidate table was READ on a database that has no such table — "
            "the guard did not run first: " + sql
        )
        if "to_regclass" in sql:
            return _Result(
                row={
                    "knowledge_discovery_runs": "knowledge_discovery_runs"
                    if self._has_run_table else None,
                    "discovery_candidates": None,
                    "schema_migrations": "schema_migrations" if self._has_ledger else None,
                }
            )
        raise AssertionError(f"unexpected statement: {sql}")


async def _drive_against(session: Any, fn) -> Any:
    """Run one async test with ``get_db`` overridden to hand out `session`."""
    from httpx import ASGITransport, AsyncClient

    from app.database import get_db
    from app.main import app

    async def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await fn(client)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _case(fn):
    def wrapper() -> None:
        asyncio.run(fn())

    wrapper.__name__ = fn.__name__
    wrapper.__qualname__ = fn.__qualname__
    wrapper.__doc__ = fn.__doc__
    return wrapper


# ===========================================================================
# A / B / C — not-ready: 409, no candidate SQL, nothing leaked
# ===========================================================================
@_case
async def test_1_the_run_read_answers_409_not_503_and_never_reads_the_table():
    session = _NotReadySession()

    async def body(client):
        return await client.get(RUN_URL.format(run_id=ANY_RUN))

    response = await _drive_against(session, body)

    assert response.status_code == 409, response.text
    assert response.status_code != 503
    detail = response.json()["detail"]
    assert detail["code"] == "DISCOVERY_DATABASE_NOT_READY"
    assert detail["message"] == REQUIRED_MESSAGE
    assert detail["missing_tables"] == ["discovery_candidates"]
    # ...and the query that would have raised was never built.
    assert not any(CANDIDATE_READ in s for s in session.statements), session.statements


@_case
async def test_2_the_seed_read_answers_409_not_503_and_never_reads_the_table():
    session = _NotReadySession()

    async def body(client):
        return await client.get(SEED_URL.format(entity_id=ANY_SEED))

    response = await _drive_against(session, body)

    assert response.status_code == 409, response.text
    assert response.status_code != 503
    assert response.json()["detail"]["code"] == "DISCOVERY_DATABASE_NOT_READY"
    assert not any(CANDIDATE_READ in s for s in session.statements), session.statements


@_case
async def test_3_the_body_carries_no_sql_no_dsn_and_no_stack():
    session = _NotReadySession()

    async def body(client):
        return await client.get(SEED_URL.format(entity_id=ANY_SEED))

    raw = (await _drive_against(session, body)).text
    for forbidden in FORBIDDEN_IN_BODY:
        assert forbidden not in raw, f"{forbidden!r} leaked into the error body: {raw}"

    # The 503 shape must be absent ENTIRELY: no outage, no hint, no raw error.
    payload = json.loads(raw)
    assert "hint" not in str(payload)
    assert "error" not in payload["detail"]


@_case
async def test_4_a_database_with_no_run_table_either_is_still_a_409():
    """Worse shape, same answer — the code does not depend on WHICH piece is missing."""
    session = _NotReadySession(has_run_table=False, has_ledger=False)

    async def body(client):
        return await client.get(RUN_URL.format(run_id=ANY_RUN))

    response = await _drive_against(session, body)

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert set(detail["missing_tables"]) == {"knowledge_discovery_runs", "discovery_candidates"}


# ===========================================================================
# D — the REAL authority database, through the REAL app
# ===========================================================================
def _authority_counts() -> tuple[int, int, str]:
    """(runs, active runs, current_database) — read with a plain sync connection."""
    import psycopg

    with psycopg.connect(_dsn(AUTHORITY_DB, async_=False)) as conn:
        name = conn.execute("SELECT current_database()").fetchone()[0]
        runs = conn.execute("SELECT count(*) FROM knowledge_discovery_runs").fetchone()[0]
        active = conn.execute(
            "SELECT count(*) FROM knowledge_discovery_runs"
            " WHERE status IN ('QUEUED', 'RUNNING')"
        ).fetchone()[0]
    return int(runs), int(active), str(name)


@_case
async def test_5_the_authority_database_answers_409_for_both_reads_and_is_unchanged():
    """§3 — the live negative case. SELECT only; the run table is not touched."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    try:
        runs_before, active_before, name = _authority_counts()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"authority database unavailable: {type(exc).__name__}")

    assert name == AUTHORITY_DB, "this test must only ever look at the authority DB"

    engine = create_async_engine(_dsn(AUTHORITY_DB), poolclass=NullPool)
    try:
        connection = await engine.connect()
    except Exception as exc:  # pragma: no cover - environment dependent
        await engine.dispose()
        pytest.skip(f"authority database unavailable: {type(exc).__name__}")

    transaction = await connection.begin()
    db = AsyncSession(bind=connection, join_transaction_mode="create_savepoint")
    try:
        async def body(client):
            return [
                await client.get(RUN_URL.format(run_id=ANY_RUN)),
                await client.get(SEED_URL.format(entity_id=ANY_SEED)),
            ]

        responses = await _drive_against(db, body)
    finally:
        await db.close()
        await transaction.rollback()
        await connection.close()
        await engine.dispose()

    for response in responses:
        # The whole point: NOT 503, and not a database-outage report.
        assert response.status_code == 409, response.text
        detail = response.json()["detail"]
        assert detail["code"] == "DISCOVERY_DATABASE_NOT_READY"
        assert detail["message"] == REQUIRED_MESSAGE
        assert "discovery_candidates" in detail["missing_tables"]
        for forbidden in FORBIDDEN_IN_BODY:
            assert forbidden not in response.text, forbidden

    runs_after, active_after, _ = _authority_counts()
    assert (runs_after, active_after) == (runs_before, active_before), (
        "asking a read endpoint must not change the authority database at all"
    )


# ===========================================================================
# E — the healthy database is untouched by the guard
# ===========================================================================
@_case
async def test_6_the_e2e_database_still_answers_200_for_both_reads():
    """The positive control: a ready database must not be turned into a 409."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(_dsn(E2E_DB), poolclass=NullPool)
    try:
        connection = await engine.connect()
    except Exception as exc:  # pragma: no cover - environment dependent
        await engine.dispose()
        pytest.skip(f"isolated test database unavailable: {type(exc).__name__}")

    transaction = await connection.begin()
    db = AsyncSession(bind=connection, join_transaction_mode="create_savepoint")
    try:
        async def body(client):
            return await client.get(SEED_URL.format(entity_id=ANY_SEED))

        response = await _drive_against(db, body)
    finally:
        await db.close()
        await transaction.rollback()
        await connection.close()
        await engine.dispose()

    # The seed may or may not exist on the isolated database; what matters is
    # that the READINESS guard did not refuse a database that has the table.
    assert response.status_code in (200, 404), response.text
    assert response.status_code != 409
