"""Phase P0-4C.1 — the LLM Discovery database readiness guard.

Three layers, each proving something the others cannot:

  A. the CHECKER, against a scripted session: which schema states are ready and
     which are not, including the state the E2E database is in and the state the
     authority database is in. No database, no writes.
  B. the ORDERING, against the REAL isolated E2E database: a not-ready database
     must fail BEFORE any side effect — no run created, no provider request, no
     parse, no storage attempt, and no new row.
  C. the HTTP MAPPING: 409 + DISCOVERY_DATABASE_NOT_READY, registered on the app.

The guard exists because the chain writes candidates LAST: without it, a database
that cannot store them still pays for a model call and leaves a FAILED run behind
(three such runs exist on the authority database today).
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

if sys.platform == "win32":  # psycopg async cannot use the Proactor loop
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

BACKEND = Path(__file__).resolve().parents[1]
E2E_DB = os.environ.get("TEST_E2E_DB", "neurographiq_human_brain_v1_e2e")
AUTHORITY_DB = "neurographiq_human_brain_v1"
SEED = "NGIQ-BR-00001169"  # Left Hippocampus, as it exists in the E2E database

from app.services import llm_discovery_readiness_service as readiness  # noqa: E402


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


# ===========================================================================
# A. the checker — a scripted catalogue, so every schema state is reachable
# ===========================================================================
class _Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> "_Result":
        return self

    def one(self) -> dict[str, Any]:
        return self._rows[0]

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class _Catalogue:
    """Answers the two readiness probes from an explicit schema description.

    This is how the states a real database cannot be put into are tested: the
    authority shape (no candidate table, migration unapplied), the E2E shape, and
    the intermediate shapes in between.
    """

    def __init__(
        self,
        *,
        runs: bool = True,
        candidates: bool = True,
        ledger: bool = True,
        applied: tuple[str, ...] = (readiness.REQUIRED_MIGRATION,),
    ) -> None:
        self.runs, self.candidates, self.ledger = runs, candidates, ledger
        self.applied = set(applied)
        self.statements: list[str] = []

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _Result:
        sql = " ".join(str(statement).split())
        self.statements.append(sql)
        if sql.startswith("SELECT to_regclass("):
            return _Result([{
                "knowledge_discovery_runs": "knowledge_discovery_runs" if self.runs else None,
                "discovery_candidates": "discovery_candidates" if self.candidates else None,
                "schema_migrations": "schema_migrations" if self.ledger else None,
            }])
        if sql.startswith("SELECT filename FROM infra.schema_migrations"):
            name = (params or {}).get("filename")
            return _Result([{"filename": name}] if name in self.applied else [])
        raise AssertionError(f"unexpected SQL: {sql}")


def _check(catalogue: _Catalogue) -> readiness.DiscoveryDatabaseReadiness:
    return asyncio.run(readiness.check_llm_discovery_database_readiness(catalogue))


def test_1_the_e2e_shape_is_ready():
    result = _check(_Catalogue())
    assert result.ready is True
    assert result.missing_tables == () and result.missing_migrations == ()


def test_1b_the_authority_shape_is_NOT_ready():
    """The live failure this phase exists to prevent: no candidate table, no 016."""
    result = _check(
        _Catalogue(candidates=False, applied=())
    )
    assert result.ready is False
    assert result.missing_tables == ("discovery_candidates",)
    assert result.missing_migrations == (readiness.REQUIRED_MIGRATION,)


def test_2_a_missing_candidate_table_alone_is_NOT_ready():
    result = _check(_Catalogue(candidates=False))
    assert result.ready is False
    assert result.missing_tables == ("discovery_candidates",)
    assert result.missing_migrations == ()


def test_2b_an_unapplied_migration_alone_is_NOT_ready():
    result = _check(_Catalogue(applied=()))
    assert result.ready is False
    assert result.missing_tables == ()
    assert result.missing_migrations == (readiness.REQUIRED_MIGRATION,)


def test_2c_a_missing_run_table_is_NOT_ready():
    result = _check(_Catalogue(runs=False))
    assert result.ready is False
    assert result.missing_tables == ("knowledge_discovery_runs",)


def test_2d_no_migration_ledger_at_all_means_nothing_is_applied():
    result = _check(_Catalogue(ledger=False))
    assert result.ready is False
    assert result.missing_migrations == (readiness.REQUIRED_MIGRATION,)


def _code_only(path: Path) -> str:
    """The module's CODE, with docstrings and comments removed.

    Required because this module's docstring NAMES the migrations it deliberately
    does not require — a substring scan over the raw text would flag the very
    sentence that states the rule.
    """
    import ast

    src = path.read_text(encoding="utf-8")
    lines = src.splitlines()
    drop: set[int] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                drop.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return "\n".join(
        line.split("#", 1)[0] for i, line in enumerate(lines, start=1) if i not in drop
    )


def test_8_review_migrations_are_NOT_required():
    """The decoupling proof: 016 + both tables is enough, with 017/018 absent.

    Readiness depends on exactly ONE migration. The scripted catalogue has no
    gate7b_017 / gate7b_018 anywhere and is still ready — and a static check below
    confirms the module never even names them in code.
    """
    result = _check(_Catalogue(applied=(readiness.REQUIRED_MIGRATION,)))
    assert result.ready is True

    code = _code_only(Path(readiness.__file__))
    for forbidden in ("gate7b_017", "gate7b_018", "candidate_review_records"):
        assert forbidden not in code, f"readiness must not depend on {forbidden}"
    assert "gate7b_016_discovery_candidates.sql" in code


def test_9_the_checker_performs_no_write():
    """Read-only, structurally: every statement it issues is a SELECT.

    A readiness check that wrote would be a migration in disguise.
    """
    catalogue = _Catalogue()
    _check(catalogue)
    assert catalogue.statements, "the checker must actually query something"
    for sql in catalogue.statements:
        assert sql.upper().lstrip().startswith("SELECT"), sql


def test_10_the_error_carries_no_credential():
    err = readiness.LlmDiscoveryDatabaseNotReady(("discovery_candidates",), ("gate7b_016.sql",))
    assert err.code == "DISCOVERY_DATABASE_NOT_READY"
    assert err.missing_tables == ("discovery_candidates",)
    assert err.missing_migrations == ("gate7b_016.sql",)
    blob = f"{err} {err.message} {err.missing_tables} {err.missing_migrations}".lower()
    for secret in ("password", "postgres", "postgresql://", "api_key", "token", "traceback"):
        assert secret not in blob, secret


# ===========================================================================
# B. ordering — a not-ready database costs NOTHING (real isolated E2E session)
# ===========================================================================
class _Spy:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *a: Any, **k: Any) -> Any:
        self.calls += 1
        raise AssertionError("must not be called on a not-ready database")


def _run_not_ready(monkeypatch) -> dict[str, Any]:
    """Drive the real execution service against the real E2E DB, guard NOT ready."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.services import knowledge_discovery_run_lifecycle_service as lifecycle
    from app.services import llm_discovery_execution_service as execution

    outcome: dict[str, Any] = {}

    async def _drive() -> None:
        engine = create_async_engine(_dsn(), poolclass=NullPool)
        connection = await engine.connect()
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, join_transaction_mode="create_savepoint")
        try:
            before = (
                await connection.execute(text("SELECT count(*) FROM knowledge_discovery_runs"))
            ).scalar_one()

            spies = {
                "create_run": _Spy(),
                "start_run": _Spy(),
                "seed_input": _Spy(),
                "provider": _Spy(),
                "parser": _Spy(),
                "persistence": _Spy(),
            }
            # The guard itself reports the authority shape.
            async def not_ready(_session):
                return readiness.DiscoveryDatabaseReadiness(
                    ready=False,
                    missing_tables=("discovery_candidates",),
                    missing_migrations=(readiness.REQUIRED_MIGRATION,),
                )

            monkeypatch.setattr(readiness, "check_llm_discovery_database_readiness", not_ready)
            monkeypatch.setattr(lifecycle, "create_discovery_run", spies["create_run"])
            monkeypatch.setattr(lifecycle, "start_discovery_run", spies["start_run"])
            monkeypatch.setattr(execution, "build_discovery_input", spies["seed_input"])
            monkeypatch.setattr(execution, "get_llm_provider", spies["provider"])
            monkeypatch.setattr(execution, "parse_llm_discovery_response", spies["parser"])
            monkeypatch.setattr(
                execution.candidate_persistence,
                "persist_discovery_candidates",
                spies["persistence"],
            )

            try:
                await execution.execute_llm_discovery(session, entity_id=SEED)
                outcome["raised"] = None
            except readiness.LlmDiscoveryDatabaseNotReady as exc:
                outcome["raised"] = exc

            after = (
                await connection.execute(text("SELECT count(*) FROM knowledge_discovery_runs"))
            ).scalar_one()
            outcome["before"], outcome["after"] = before, after
            outcome["spies"] = {k: v.calls for k, v in spies.items()}
        finally:
            await session.close()
            await transaction.rollback()
            await connection.close()
            await engine.dispose()

    asyncio.run(_drive())
    return outcome


@pytest.fixture()
def not_ready(monkeypatch):
    try:
        import psycopg

        with psycopg.connect(_dsn(async_=False)) as conn:
            conn.execute("SELECT 1")
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"isolated test database unavailable: {type(exc).__name__}")
    return _run_not_ready(monkeypatch)


def test_3_4_5_6_a_not_ready_database_fails_before_every_side_effect(not_ready):
    err = not_ready["raised"]
    assert err is not None, "a not-ready database must raise, not proceed"
    assert err.code == "DISCOVERY_DATABASE_NOT_READY"
    assert err.missing_tables == ("discovery_candidates",)

    # Nothing was created, called or attempted — every spy is at zero.
    assert not_ready["spies"] == {
        "create_run": 0,
        "start_run": 0,
        "seed_input": 0,
        "provider": 0,
        "parser": 0,
        "persistence": 0,
    }, not_ready["spies"]


def test_3b_the_run_count_is_unchanged(not_ready):
    assert not_ready["after"] == not_ready["before"], (
        "a not-ready database must leave the run table exactly as it found it"
    )


# ===========================================================================
# C. the E2E database really is ready, and the guard lets execution through
# ===========================================================================
def test_7_the_real_e2e_database_is_ready_read_only():
    """The positive case, against the real isolated database. SELECT only."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    async def _check_real() -> readiness.DiscoveryDatabaseReadiness:
        engine = create_async_engine(_dsn(), poolclass=NullPool)
        connection = await engine.connect()
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, join_transaction_mode="create_savepoint")
        try:
            assert (
                await connection.execute(text("SELECT current_database()"))
            ).scalar_one() == E2E_DB
            return await readiness.check_llm_discovery_database_readiness(session)
        finally:
            await session.close()
            await transaction.rollback()
            await connection.close()
            await engine.dispose()

    result = asyncio.run(_check_real())
    assert result.ready is True, result
    assert result.missing_tables == () and result.missing_migrations == ()


def test_7b_the_guard_passes_on_the_e2e_database():
    """`require_...` is silent when ready — the execution chain is unblocked."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    async def _require_real() -> None:
        engine = create_async_engine(_dsn(), poolclass=NullPool)
        connection = await engine.connect()
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, join_transaction_mode="create_savepoint")
        try:
            await readiness.require_llm_discovery_database_readiness(session)
        finally:
            await session.close()
            await transaction.rollback()
            await connection.close()
            await engine.dispose()

    asyncio.run(_require_real())  # must not raise


def test_11_the_authority_database_is_not_ready_read_only():
    """The negative case against the LIVE authority database. SELECT only.

    The REAL checker is run against the REAL authority database: this is the exact
    call the running service makes, and it must answer NOT READY. Nothing is
    written — the checker only reads the catalogue, no migration is applied and no
    run is created — so running it there is safe.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    async def _check_authority() -> tuple[str, readiness.DiscoveryDatabaseReadiness]:
        engine = create_async_engine(_dsn(db=AUTHORITY_DB), poolclass=NullPool)
        connection = await engine.connect()
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, join_transaction_mode="create_savepoint")
        try:
            name = (
                await connection.execute(text("SELECT current_database()"))
            ).scalar_one()
            return name, await readiness.check_llm_discovery_database_readiness(session)
        finally:
            await session.close()
            await transaction.rollback()
            await connection.close()
            await engine.dispose()

    try:
        name, result = asyncio.run(_check_authority())
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"authority database unavailable: {type(exc).__name__}")

    assert name == AUTHORITY_DB, "this test must only ever look at the authority DB"
    assert result.ready is False, (
        "the authority database has no candidate table — the guard MUST refuse"
    )
    assert "discovery_candidates" in result.missing_tables
    assert readiness.REQUIRED_MIGRATION in result.missing_migrations


# ===========================================================================
# D. the HTTP mapping
# ===========================================================================
def test_12_the_app_maps_the_error_to_409_with_its_own_code():
    from app.main import app

    # Registered on the app — not inside a router, and not as a provider or
    # persistence failure.
    assert readiness.LlmDiscoveryDatabaseNotReady in app.exception_handlers

    handler = app.exception_handlers[readiness.LlmDiscoveryDatabaseNotReady]
    response = asyncio.run(
        handler(
            None,
            readiness.LlmDiscoveryDatabaseNotReady(
                ("discovery_candidates",), ("gate7b_016_discovery_candidates.sql",)
            ),
        )
    )
    assert response.status_code == 409
    import json

    detail = json.loads(response.body)["detail"]
    assert detail["code"] == "DISCOVERY_DATABASE_NOT_READY"
    assert detail["message"] == readiness.NOT_READY_MESSAGE
    assert detail["missing_tables"] == ["discovery_candidates"]
    assert detail["missing_migrations"] == ["gate7b_016_discovery_candidates.sql"]

    # Bounded: schema object names only.
    body = response.body.decode("utf-8").lower()
    for secret in ("password", "postgresql://", "api_key", "traceback", "file \""):
        assert secret not in body, secret
