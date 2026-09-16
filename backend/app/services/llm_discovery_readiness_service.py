"""Can THIS database store — and serve — LLM Discovery candidates?

Why this module exists
----------------------
The execution chain creates a run, calls the model, parses the answer and only
THEN writes the candidates (P0-1). On a database without the candidate staging
table that last step fails — after a run row has been written and after the
provider has been paid for. That already happened three times on the authority
database, each attempt leaving a FAILED `LLM_DISCOVERY` run behind. The chain is
correct; what was missing is a check BEFORE it starts.

The same absence has a second face, found later: READING candidates. A
`SELECT ... FROM discovery_candidates` on such a database raises
`UndefinedTable`, which the app-wide SQLAlchemy handler reports as HTTP 503
`DATABASE_UNAVAILABLE` — "check PostgreSQL is running and DATABASE_URL is
correct", about a server that is running fine and a URL that is correct. The
read endpoints guard with this same module, so the answer to "is this database
enabled for discovery" has ONE authority and cannot differ between writing a
candidate and reading one back.

What it checks, and deliberately does NOT check
-----------------------------------------------
    knowledge_discovery_runs   the run record
    discovery_candidates       where the proposals are staged
    gate7b_016 applied         the migration that creates the second one

`gate7b_017` / `gate7b_018` and `candidate_review_records` are NOT required: they
belong to Candidate Review, which is a separate phase with its own contract. A
database that can run a discovery but cannot yet record a review is a legitimate
state, and demanding more would couple two independent phases.

This module only READS. It never writes, never migrates and never repairs — a
readiness check that changed the database would be a migration in disguise.

No caching: a migration may be applied between two requests, so the answer is
re-read every time. Both statements are catalogue lookups, which is cheap enough
that a cache would cost more (in staleness) than it saves.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

#: The one migration this chain depends on. Named after the migration FILE, which
#: is the identity the ledger records and the runner checksums.
REQUIRED_MIGRATION = "gate7b_016_discovery_candidates.sql"

#: The two tables the execution chain writes, in dependency order.
REQUIRED_TABLES: tuple[str, ...] = ("knowledge_discovery_runs", "discovery_candidates")

#: One catalogue round trip answers "does this database have the shape at all".
#: `to_regclass` is the precise "does this relation exist" primitive: it returns
#: NULL instead of raising, which is exactly the question being asked.
#:
#: Each column is aliased to the TABLE'S OWN NAME, so `REQUIRED_TABLES` can be
#: used as the key directly — no second name→alias map to keep in step.
_EXISTENCE_SQL = text(
    """
    SELECT to_regclass('public.knowledge_discovery_runs')::text AS knowledge_discovery_runs,
           to_regclass('public.discovery_candidates')::text     AS discovery_candidates,
           to_regclass('infra.schema_migrations')::text         AS schema_migrations
    """
)

#: The ledger's own name, as the key of the third probe.
_LEDGER_KEY = "schema_migrations"

#: The second statement is issued only when the ledger exists — a database with no
#: ledger is a database where nothing has been applied, and querying a missing
#: table would raise instead of answering.
_APPLIED_SQL = text(
    """
    SELECT filename FROM infra.schema_migrations
    WHERE filename = :filename AND status = 'APPLIED'
    """
)

#: The message is a fixed sentence, never a database error: it is shown to an
#: operator and must carry no credential, host, URL or stack fragment.
#:
#: It says STORAGE, not "persistence" or "read": the condition is one condition,
#: and a caller that is refused while reading must be told the same thing as a
#: caller that is refused while writing. Two sentences for one state would invite
#: an operator to treat them as two problems.
NOT_READY_MESSAGE = (
    "LLM Discovery candidate storage is not enabled for the current database."
)


@dataclass(frozen=True)
class DiscoveryDatabaseReadiness:
    """The answer, with the bounded diagnostics a caller may report.

    Both tuples name SCHEMA OBJECTS only. Nothing here can leak a credential:
    a table name and a migration filename are public facts about a deployment.
    """

    ready: bool
    missing_tables: tuple[str, ...]
    missing_migrations: tuple[str, ...]


class LlmDiscoveryDatabaseNotReady(Exception):
    """This database is not enabled for LLM Discovery candidates.

    Raised both when a run would be started and when candidates would be read:
    without the staging table there is nothing to write AND nothing to read, and
    the two callers must not have to interpret two different failures.

    An ENVIRONMENT precondition, not a runtime failure: nothing was attempted, no
    run exists, no model was called and no candidate row was queried. It is
    deliberately not a provider error and not a persistence error — a caller must
    be able to tell "this database is not set up for discovery" apart from "the
    model or the storage failed".
    """

    def __init__(
        self,
        missing_tables: tuple[str, ...] = (),
        missing_migrations: tuple[str, ...] = (),
    ) -> None:
        super().__init__(NOT_READY_MESSAGE)
        self.code = "DISCOVERY_DATABASE_NOT_READY"
        self.message = NOT_READY_MESSAGE
        self.missing_tables = tuple(missing_tables)
        self.missing_migrations = tuple(missing_migrations)


async def check_llm_discovery_database_readiness(
    session: AsyncSession,
) -> DiscoveryDatabaseReadiness:
    """Read-only: is this database ready for an LLM Discovery run? SELECT only."""
    row = (await session.execute(_EXISTENCE_SQL)).mappings().one()

    missing_tables = tuple(name for name in REQUIRED_TABLES if row[name] is None)

    # No ledger means nothing was ever recorded as applied, so the required
    # migration is missing rather than unknown.
    applied = (
        (await session.execute(_APPLIED_SQL, {"filename": REQUIRED_MIGRATION})).first()
        if row[_LEDGER_KEY] is not None
        else None
    )
    missing_migrations = () if applied is not None else (REQUIRED_MIGRATION,)

    return DiscoveryDatabaseReadiness(
        ready=not missing_tables and not missing_migrations,
        missing_tables=missing_tables,
        missing_migrations=missing_migrations,
    )


async def require_llm_discovery_database_readiness(session: AsyncSession) -> None:
    """The guard: raise unless this database can hold discovery candidates.

    Called BEFORE anything is created and before any model is called, so a
    not-ready database costs nothing at all — no run row, no provider request, no
    parser invocation and no storage attempt.

    Also called before any candidate SELECT, where "costs nothing" means the
    candidate table is never named in a statement that would raise
    `UndefinedTable`. The caller is expected to place this call before it touches
    `discovery_candidates`, and to map the raised error as an environment
    precondition (HTTP 409) rather than a database outage (HTTP 503).
    """
    readiness = await check_llm_discovery_database_readiness(session)
    if not readiness.ready:
        raise LlmDiscoveryDatabaseNotReady(
            readiness.missing_tables, readiness.missing_migrations
        )
