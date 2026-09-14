"""Startup compatibility gate for legacy Gen-1 paper-evidence recovery.

The authoritative database (``neurographiq_human_brain_v1``) is the Gate7B
schema. It does NOT contain the Gen-1 paper-evidence tables, because the
Gen-1 evidence subsystem lives in the retired workbench databases. Their
absence is expected architectural absence, not damage.

The startup hook in ``app.main`` still performs Gen-1 recovery work. When it
runs against the authoritative schema it raises ``UndefinedTable`` and logs a
full traceback for each missing table — noise that obscures real startup
problems.

This module answers exactly one question, read-only:

    "Are the tables that legacy recovery needs actually present?"

It contains NO recovery logic, NO table creation, and NO generic
"ignore missing tables" behaviour: the table list is fixed and specific to the
startup hooks it guards. Recovery itself is untouched and still runs verbatim
where the legacy schema genuinely exists.

This gate does NOT widen database access: it reads whatever database the
runtime is already connected to, and ``database_guard`` still decides which
databases those may be.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Tables the two startup recovery hooks require. Kept deliberately explicit:
# this is a compatibility gate for KNOWN hooks, not a discovery mechanism.
#
#   main.log_startup_version -> paper_evidence_service.recover_interrupted_batch_tasks
#       paper_evidence_tasks, paper_evidence_task_items
#   main.log_startup_version -> paper_evidence_extraction_run_service.recover_interrupted_runs
#       paper_evidence_extraction_runs, paper_evidence_extraction_items
REQUIRED_TABLES: tuple[str, ...] = (
    "paper_evidence_tasks",
    "paper_evidence_task_items",
    "paper_evidence_extraction_runs",
    "paper_evidence_extraction_items",
)

# One parameterised, read-only catalogue query for all required tables.
# `relkind IN ('r','p')` = ordinary / partitioned tables; a view or index with
# a matching name does not satisfy a recovery that writes rows.
_NAME_PARAMS = {f"t{i}": name for i, name in enumerate(REQUIRED_TABLES)}
_PRESENT_SQL = text(
    "SELECT c.relname"
    " FROM pg_catalog.pg_class c"
    " JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace"
    " WHERE n.nspname = 'public'"
    "   AND c.relkind IN ('r', 'p')"
    "   AND c.relname IN ("
    + ", ".join(f":{p}" for p in _NAME_PARAMS)
    + ")"
)


@dataclass(frozen=True)
class LegacyRecoveryAvailability:
    """Whether the legacy recovery hooks can run in the current database."""

    available: bool
    missing_tables: tuple[str, ...]

    def describe(self) -> str:
        """One-line reason, suitable for a single startup log message."""
        if self.available:
            return "all required Gen-1 tables present"
        return "missing tables=" + ",".join(self.missing_tables)


async def legacy_paper_evidence_recovery_available(
    session: AsyncSession,
) -> LegacyRecoveryAvailability:
    """Report whether the Gen-1 paper-evidence tables exist. READ ONLY.

    Issues exactly one SELECT against pg_catalog. It performs no INSERT,
    UPDATE, DELETE or DDL, and creates nothing.
    """
    rows = (await session.execute(_PRESENT_SQL, dict(_NAME_PARAMS))).all()
    present = {row[0] for row in rows}
    missing = tuple(name for name in REQUIRED_TABLES if name not in present)
    return LegacyRecoveryAvailability(available=not missing, missing_tables=missing)
