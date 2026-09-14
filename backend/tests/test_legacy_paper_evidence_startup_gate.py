"""Phase 2A.1 — legacy Gen-1 startup recovery is schema-gated.

The authoritative database (``neurographiq_human_brain_v1``) legitimately has no
Gen-1 ``paper_evidence_*`` tables. Startup must therefore skip the legacy
recovery cleanly, once, with an explicit reason and no UndefinedTable traceback —
while still running recovery verbatim wherever that schema does exist.

No real legacy table is required: the availability query is served by a stub
session and the recovery functions are replaced by spies.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest

from app import database as app_database
from app import database_guard
from app import main as app_main
from app.services import legacy_paper_evidence_compat as compat
from app.services import paper_evidence_extraction_run_service as extraction_run_svc
from app.services import paper_evidence_service as pes

SKIP_MARKER = "legacy paper evidence recovery skipped"


class _StubResult:
    def __init__(self, rows: list[tuple[str, ...]] | None = None) -> None:
        self._rows = rows or []

    def all(self) -> list[tuple[str, ...]]:
        return self._rows

    def scalars(self) -> "_StubResult":
        return self

    def rowcount(self) -> int:
        return 0


class _StubSession:
    """Serves the pg_catalog availability query; records every statement.

    Any other query returns no rows, so a recovery function that somehow ran
    would see an empty result instead of a missing table.
    """

    def __init__(self, present: tuple[str, ...] = ()) -> None:
        self.present = present
        self.statements: list[str] = []

    async def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> _StubResult:
        sql = " ".join(str(stmt).split())
        self.statements.append(sql)
        if "pg_catalog.pg_class" in sql:
            return _StubResult([(name,) for name in self.present])
        return _StubResult([])

    async def __aenter__(self) -> "_StubSession":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    @property
    def has_write(self) -> bool:
        joined = " ".join(self.statements).upper()
        return any(v in joined for v in ("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP"))


@pytest.fixture()
def session_factory(monkeypatch):
    """Install a stub AsyncSessionLocal and return the created stub sessions."""

    created: list[_StubSession] = []

    def _install(present: tuple[str, ...] = ()) -> _StubSession:
        stub = _StubSession(present)
        created.append(stub)
        monkeypatch.setattr(app_database, "AsyncSessionLocal", lambda: stub)
        return stub

    return _install


@pytest.fixture()
def recovery_spies(monkeypatch):
    """Replace both legacy recovery entry points with call-recording spies."""
    calls: dict[str, list[Any]] = {"batch": [], "runs": []}

    async def _batch(session: Any) -> int:
        calls["batch"].append(session)
        return 0

    async def _runs(session: Any) -> list[Any]:
        calls["runs"].append(session)
        return []

    monkeypatch.setattr(pes, "recover_interrupted_batch_tasks", _batch)
    monkeypatch.setattr(extraction_run_svc, "recover_interrupted_runs", _runs)
    return calls


def _run_startup() -> None:
    asyncio.run(app_main.log_startup_version())


# ---------------------------------------------------------------------------
# 1 / 2 / 3 — availability gate
# ---------------------------------------------------------------------------
def test_all_required_tables_present_gate_is_true(session_factory):
    session = session_factory(compat.REQUIRED_TABLES)
    availability = asyncio.run(compat.legacy_paper_evidence_recovery_available(session))
    assert availability.available is True
    assert availability.missing_tables == ()
    assert availability.describe() == "all required Gen-1 tables present"


def test_one_required_table_absent_gate_is_false(session_factory):
    absent = compat.REQUIRED_TABLES[0]
    session = session_factory(tuple(t for t in compat.REQUIRED_TABLES if t != absent))
    availability = asyncio.run(compat.legacy_paper_evidence_recovery_available(session))
    assert availability.available is False
    assert availability.missing_tables == (absent,)
    assert absent in availability.describe()


def test_all_required_tables_absent_gate_is_false(session_factory):
    session = session_factory(())
    availability = asyncio.run(compat.legacy_paper_evidence_recovery_available(session))
    assert availability.available is False
    assert availability.missing_tables == compat.REQUIRED_TABLES


def test_gate_covers_exactly_the_tables_the_startup_hooks_need():
    """A specific compatibility gate, not a generic missing-table system."""
    assert compat.REQUIRED_TABLES == (
        "paper_evidence_tasks",
        "paper_evidence_task_items",
        "paper_evidence_extraction_runs",
        "paper_evidence_extraction_items",
    )


# ---------------------------------------------------------------------------
# 4 / 5 — startup behaviour
# ---------------------------------------------------------------------------
def test_missing_tables_skip_recovery_and_log_once_without_traceback(
    session_factory, recovery_spies, caplog
):
    session_factory(())  # authoritative DB: no Gen-1 tables at all
    with caplog.at_level(logging.INFO):
        _run_startup()

    assert recovery_spies["batch"] == [], "legacy batch recovery must not run"
    assert recovery_spies["runs"] == [], "legacy run recovery must not run"

    skips = [r for r in caplog.records if SKIP_MARKER in r.getMessage()]
    assert len(skips) == 1, "exactly one summarized skip message, not one per table"
    message = skips[0].getMessage()
    assert "missing tables=" in message
    for table in compat.REQUIRED_TABLES:
        assert table in message
    assert skips[0].levelno == logging.INFO

    # no UndefinedTable traceback: nothing at ERROR/CRITICAL, no exc_info
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []
    assert all(r.exc_info is None for r in caplog.records)


def test_present_tables_preserve_recovery_invocation(session_factory, recovery_spies, caplog):
    session_factory(compat.REQUIRED_TABLES)  # a genuinely legacy environment
    with caplog.at_level(logging.INFO):
        _run_startup()

    assert len(recovery_spies["batch"]) == 1, "batch recovery must still run"
    assert len(recovery_spies["runs"]) == 1, "run recovery must still run"
    assert not [r for r in caplog.records if SKIP_MARKER in r.getMessage()]


def test_partially_present_schema_still_skips(session_factory, recovery_spies, caplog):
    """One missing table is enough: recovery would raise UndefinedTable."""
    session_factory(tuple(t for t in compat.REQUIRED_TABLES if t != "paper_evidence_task_items"))
    with caplog.at_level(logging.INFO):
        _run_startup()
    assert recovery_spies["batch"] == []
    assert recovery_spies["runs"] == []
    assert len([r for r in caplog.records if SKIP_MARKER in r.getMessage()]) == 1


def test_no_database_session_skips_without_touching_recovery(monkeypatch, recovery_spies, caplog):
    monkeypatch.setattr(app_database, "AsyncSessionLocal", None)
    with caplog.at_level(logging.INFO):
        _run_startup()
    assert recovery_spies["batch"] == []
    assert recovery_spies["runs"] == []
    skips = [r for r in caplog.records if SKIP_MARKER in r.getMessage()]
    assert len(skips) == 1
    assert "no database session" in skips[0].getMessage()


# ---------------------------------------------------------------------------
# 6 / 8 — read-only, creates nothing
# ---------------------------------------------------------------------------
def test_availability_check_issues_one_read_only_statement(session_factory):
    session = session_factory(())
    asyncio.run(compat.legacy_paper_evidence_recovery_available(session))
    assert len(session.statements) == 1, "one catalogue query, not one per table"
    assert session.statements[0].upper().startswith("SELECT")
    assert session.has_write is False


def test_compat_module_contains_no_ddl_or_dml():
    source = compat.__file__
    with open(source, encoding="utf-8") as fh:
        code = fh.read()
    for verb in ("CREATE TABLE", "ALTER TABLE", "DROP TABLE", "INSERT INTO", "DELETE FROM"):
        assert verb not in code.upper(), f"the gate must not contain {verb!r}"


def test_compat_module_never_selects_row_data():
    """The gate inspects the catalogue only — it must not read legacy rows."""
    session = _StubSession(())
    asyncio.run(compat.legacy_paper_evidence_recovery_available(session))
    sql = session.statements[0]
    assert "pg_catalog.pg_class" in sql
    assert "paper_evidence_tasks " not in sql  # no table scan


# ---------------------------------------------------------------------------
# 7 — database_guard is untouched
# ---------------------------------------------------------------------------
def test_database_guard_still_permits_only_the_authoritative_databases():
    assert database_guard.MAIN_DATABASE == "neurographiq_human_brain_v1"
    assert database_guard.is_allowed_main_database("neurographiq_human_brain_v1")
    assert not database_guard.is_allowed_main_database("neurographiq_human_brain_v1_e2e")


def test_database_guard_still_rejects_every_legacy_database():
    for name in database_guard.FORBIDDEN_DB_PREFIXES:
        assert database_guard.is_forbidden_legacy_database(f"{name}_anything")
        with pytest.raises(database_guard.DatabaseGuardError):
            database_guard.assert_allowed_database(f"{name}_anything")


def test_gate_does_not_touch_database_switching():
    """The fix adapts startup to the authoritative schema; it never re-points it."""
    with open(compat.__file__, encoding="utf-8") as fh:
        code = fh.read()
    for forbidden in ("reload_database_engine", "database_admin_service", "create_engine"):
        assert forbidden not in code, f"the gate must not reference {forbidden!r}"
