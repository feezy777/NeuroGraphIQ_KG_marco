"""Phase 2B — Discovery Run lifecycle (the ONLY writer of discovery runs).

Frozen state graph (docs/KNOWLEDGE_PRODUCTION_ARCHITECTURE.md §14):

    CREATE → QUEUED ──start──→ RUNNING ──complete──→ COMPLETED
                      │              ├──fail────→ FAILED
                      │              └──cancel──→ CANCELLED
                      ├──fail────→ FAILED
                      └──cancel──→ CANCELLED

COMPLETED / FAILED / CANCELLED are TERMINAL and immutable: no transition leaves
them. Retry is deliberately absent — a future retry creates a NEW run.

This module is the write counterpart to the READ-ONLY
``knowledge_discovery_run_service``. The read service is not touched: reads stay
reads, and every mutation lives here.

Boundaries:
  * NO execution. Nothing here calls an LLM, a literature API or a provider:
    ``create`` produces a QUEUED run that a later execution layer advances.
  * NO knowledge. A run is workflow/provenance; it never becomes a circuit,
    connection, function, evidence or assertion.
  * NO candidate/evidence writes, no history/event table.

Concurrency: every transition runs in ONE transaction that first locks the run
row with ``SELECT ... FOR UPDATE``. A "read the status, then UPDATE" without the
lock would let two concurrent requests both observe QUEUED and both start the
run. Creation is protected by the partial unique index
``uq_kdr_active_per_seed_type`` (gate7b_012), which the database enforces even
if two requests race past an application-level pre-check.
"""
from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.discovery_forensics import (
    FORENSIC_COLUMN_NAMES,
    DiscoveryResponseForensics,
)
from app.schemas.knowledge_production import (
    ACTIVE_DISCOVERY_RUN_STATUSES,
    COMPLETION_OUTCOMES_BY_TYPE,
    TERMINAL_DISCOVERY_RUN_STATUSES,
    DiscoveryRunItem,
)
from app.services.knowledge_discovery_run_service import (
    resolve_seed_region_pk,
    row_to_item,
)


# ---------------------------------------------------------------------------
# Domain errors — the router maps these to HTTP status codes. No SQL or DB
# internals ever appear in their messages (§19).
# ---------------------------------------------------------------------------
class DiscoveryRunNotFound(Exception):
    """The run (or the BrainRegion seed) does not exist -> 404."""

    def __init__(self, identifier: str, *, what: str = "Discovery Run") -> None:
        super().__init__(f"{what} '{identifier}' not found")
        self.identifier = identifier
        self.what = what


class DiscoveryRunConflict(Exception):
    """The requested transition is illegal for the current state -> 409."""

    def __init__(self, code: str, message: str, *, active_run_id: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.active_run_id = active_run_id


class DiscoveryRunOutcomeNotAllowed(Exception):
    """The outcome is not scientifically valid for this route -> 422."""

    def __init__(self, discovery_type: str, outcome: str, allowed: tuple[str, ...]) -> None:
        super().__init__(
            f"outcome '{outcome}' is not valid for {discovery_type};"
            f" allowed: {', '.join(allowed)}"
        )
        self.discovery_type = discovery_type
        self.outcome = outcome
        self.allowed = allowed


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------
_RETURN_COLUMNS = """
    run_id,
    discovery_type,
    status,
    outcome,
    provider,
    model_name,
    prompt_key,
    prompt_version,
    query_strategy_version,
    created_by,
    created_at,
    started_at,
    finished_at,
    error_code,
    error_message
"""

# Locks ONLY the run row (FOR UPDATE OF r), not the joined reference rows.
_LOCK_SQL = text(
    """
    SELECT r.run_id, e.entity_id AS seed_entity_id,
           r.discovery_type, r.status, r.outcome,
           r.provider, r.model_name, r.prompt_key, r.prompt_version,
           r.query_strategy_version, r.created_by,
           r.created_at, r.started_at, r.finished_at,
           r.error_code, r.error_message
    FROM knowledge_discovery_runs r
    JOIN brain_regions b ON b.entity_pk = r.seed_region_pk
    JOIN kg_entities e ON e.entity_pk = b.entity_pk
    WHERE r.run_id = :run_id
    FOR UPDATE OF r
    """
)

_FIND_ACTIVE_SQL = text(
    """
    SELECT run_id FROM knowledge_discovery_runs
    WHERE seed_region_pk = :seed_region_pk
      AND discovery_type = :discovery_type
      AND status = ANY(:active_statuses)
    ORDER BY created_at
    LIMIT 1
    """
)

# SET clauses are module constants — never built from request input.
_SET_START = "status = 'RUNNING', started_at = now(), updated_at = now()"
_SET_COMPLETE = (
    "status = 'COMPLETED', outcome = :outcome, finished_at = now(), updated_at = now()"
)
_SET_FAIL = (
    "status = 'FAILED', finished_at = now(), updated_at = now(),"
    " error_code = :error_code, error_message = :error_message"
)
_SET_CANCEL = "status = 'CANCELLED', finished_at = now(), updated_at = now()"


def _with_forensics(
    set_sql: str, forensics: DiscoveryResponseForensics | None
) -> tuple[str, dict[str, Any]]:
    """Extend a terminal SET clause with the provider-response forensics.

    The columns are appended to the COMPLETING statement rather than written by
    a second UPDATE, so a run can never be found FAILED with its forensic
    evidence missing when that evidence was already in memory (§7). Column names
    come from the record's own tuple — never from request input — so this cannot
    name a column the migration did not create.

    ``None`` leaves the statement byte-for-byte as it was: a caller with nothing
    to record does not silently NULL columns written by an earlier transition.
    """
    if forensics is None:
        return set_sql, {}
    params = {name: getattr(forensics, name) for name in FORENSIC_COLUMN_NAMES}
    assignments = ", ".join(f"{name} = :{name}" for name in FORENSIC_COLUMN_NAMES)
    return f"{set_sql}, {assignments}", params


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
async def _lock_run_or_404(session: AsyncSession, run_id: str) -> Mapping[str, Any]:
    """Lock the run row for the duration of the transaction, or raise 404."""
    row = (await session.execute(_LOCK_SQL, {"run_id": run_id})).mappings().one_or_none()
    if row is None:
        raise DiscoveryRunNotFound(run_id)
    return row


def _json(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, default=str)


async def _apply(
    session: AsyncSession,
    locked: Mapping[str, Any],
    set_sql: str,
    params: Mapping[str, Any],
    provenance: Mapping[str, Any] | None = None,
) -> DiscoveryRunItem:
    """Apply one SET clause to the already-locked row and commit the transaction.

    ``provenance`` is MERGED into ``provenance_json`` rather than replacing it,
    so a run accumulates what each stage learned about it. Passing nothing
    leaves the column exactly as it was — the previous behaviour.
    """
    if provenance:
        set_sql += (
            ", provenance_json = COALESCE(provenance_json, '{}'::jsonb)"
            " || CAST(:provenance_json AS jsonb)"
        )
        params = {**params, "provenance_json": _json(provenance)}
    updated = (
        await session.execute(
            text(
                "UPDATE knowledge_discovery_runs SET " + set_sql
                + " WHERE run_id = :run_id RETURNING " + _RETURN_COLUMNS
            ),
            {**params, "run_id": locked["run_id"]},
        )
    ).mappings().one()
    await session.commit()
    # seed_entity_id comes from the locked read; the UPDATE cannot join.
    return row_to_item({**locked, **updated})


def _terminal_conflict(row: Mapping[str, Any], action: str) -> DiscoveryRunConflict:
    return DiscoveryRunConflict(
        "RUN_ALREADY_TERMINAL",
        f"cannot {action} a run in terminal state {row['status']}",
    )


# ---------------------------------------------------------------------------
# PUBLIC LIFECYCLE — create / start / complete / fail / cancel. Nothing else.
# ---------------------------------------------------------------------------
async def create_discovery_run(
    session: AsyncSession,
    *,
    entity_id: str,
    discovery_type: str,
    provider: str | None = None,
    model_name: str | None = None,
    prompt_key: str | None = None,
    prompt_version: str | None = None,
    query_strategy_version: str | None = None,
    provenance: Mapping[str, Any] | None = None,
) -> DiscoveryRunItem:
    """Create a QUEUED run for one BrainRegion seed.

    The PUBLIC API supplies only ``entity_id`` + ``discovery_type``: the HTTP
    layer never forwards client-provided provider / model / prompt, so a
    browser cannot fabricate execution provenance.

    The provenance kwargs exist for the TRUSTED INTERNAL caller (the LLM
    discovery execution service), which knows what it is about to run. They
    default to None, which is exactly the public behaviour — a run created
    without them keeps those columns empty.

    Raises DiscoveryRunNotFound (unknown BrainRegion) or DiscoveryRunConflict
    (an active run already exists for this seed + route).
    """
    seed_region_pk = await resolve_seed_region_pk(session, entity_id)
    if seed_region_pk is None:
        raise DiscoveryRunNotFound(entity_id, what="BrainRegion")

    try:
        row = (
            await session.execute(
                text(
                    "INSERT INTO knowledge_discovery_runs"
                    " (seed_region_pk, discovery_type, status, outcome, started_at,"
                    "  finished_at, provider, model_name, prompt_key, prompt_version,"
                    "  query_strategy_version, provenance_json)"
                    " VALUES (:seed_region_pk, :discovery_type, 'QUEUED', NULL, NULL, NULL,"
                    "  :provider, :model_name, :prompt_key, :prompt_version,"
                    "  :query_strategy_version, CAST(:provenance_json AS jsonb))"
                    " RETURNING " + _RETURN_COLUMNS
                ),
                {
                    "seed_region_pk": seed_region_pk,
                    "discovery_type": discovery_type,
                    "provider": provider,
                    "model_name": model_name,
                    "prompt_key": prompt_key,
                    "prompt_version": prompt_version,
                    "query_strategy_version": query_strategy_version,
                    "provenance_json": _json(provenance or {}),
                },
            )
        ).mappings().one()
    except IntegrityError:
        # uq_kdr_active_per_seed_type fired: a concurrent or earlier create won
        # the race. The database is the final authority; report 409, not 500.
        await session.rollback()
        existing = (
            await session.execute(
                _FIND_ACTIVE_SQL,
                {
                    "seed_region_pk": seed_region_pk,
                    "discovery_type": discovery_type,
                    "active_statuses": list(ACTIVE_DISCOVERY_RUN_STATUSES),
                },
            )
        ).scalar_one_or_none()
        raise DiscoveryRunConflict(
            "ACTIVE_RUN_EXISTS",
            f"an active {discovery_type} run already exists for this BrainRegion",
            active_run_id=str(existing) if existing is not None else None,
        ) from None

    await session.commit()
    return row_to_item({**row, "seed_entity_id": entity_id})


async def start_discovery_run(session: AsyncSession, run_id: str) -> DiscoveryRunItem:
    """QUEUED -> RUNNING. Starting an already-RUNNING run is a no-op (200)."""
    row = await _lock_run_or_404(session, run_id)
    if row["status"] == "RUNNING":
        return row_to_item(row)  # idempotent: no mutation
    if row["status"] != "QUEUED":
        raise _terminal_conflict(row, "start")
    return await _apply(session, row, _SET_START, {})


async def complete_discovery_run(
    session: AsyncSession, run_id: str, outcome: str, *,
    provenance: Mapping[str, Any] | None = None,
    forensics: DiscoveryResponseForensics | None = None,
) -> DiscoveryRunItem:
    """RUNNING -> COMPLETED with a scientific outcome.

    The outcome must be valid for the run's route: LLM_DISCOVERY may not claim
    NO_EVIDENCE_FOUND, because it is not an evidence-search route.
    """
    row = await _lock_run_or_404(session, run_id)

    # Request validity first: an outcome the route can never report is 422,
    # regardless of the run's current state.
    allowed = COMPLETION_OUTCOMES_BY_TYPE[row["discovery_type"]]
    if outcome not in allowed:
        raise DiscoveryRunOutcomeNotAllowed(row["discovery_type"], outcome, allowed)

    if row["status"] == "COMPLETED":
        if row["outcome"] == outcome:
            return row_to_item(row)  # idempotent repeat
        raise DiscoveryRunConflict(
            "OUTCOME_ALREADY_RECORDED",
            f"run is already COMPLETED with outcome {row['outcome']}",
        )
    if row["status"] in TERMINAL_DISCOVERY_RUN_STATUSES:
        raise _terminal_conflict(row, "complete")
    if row["status"] == "QUEUED":
        raise DiscoveryRunConflict("RUN_NOT_STARTED", "a run must be started before it can complete")
    set_sql, forensic_params = _with_forensics(_SET_COMPLETE, forensics)
    return await _apply(session, row, set_sql,
                        {"outcome": outcome, **forensic_params},
                        provenance=provenance)


async def fail_discovery_run(
    session: AsyncSession, run_id: str, *, error_code: str | None, error_message: str,
    provenance: Mapping[str, Any] | None = None,
    forensics: DiscoveryResponseForensics | None = None,
) -> DiscoveryRunItem:
    """QUEUED | RUNNING -> FAILED with an explanation.

    outcome stays NULL: a failure is an execution fact, not a scientific
    result. started_at is NOT fabricated when the failure happened while QUEUED.
    """
    row = await _lock_run_or_404(session, run_id)
    if row["status"] == "FAILED":
        if row["error_code"] == error_code and row["error_message"] == error_message:
            return row_to_item(row)  # idempotent repeat
        raise DiscoveryRunConflict(
            "FAILURE_ALREADY_RECORDED", "run is already FAILED with a different error"
        )
    if row["status"] in TERMINAL_DISCOVERY_RUN_STATUSES:
        raise _terminal_conflict(row, "fail")
    set_sql, forensic_params = _with_forensics(_SET_FAIL, forensics)
    return await _apply(
        session,
        row,
        set_sql,
        {"error_code": error_code, "error_message": error_message, **forensic_params},
        provenance=provenance,
    )


async def cancel_discovery_run(session: AsyncSession, run_id: str) -> DiscoveryRunItem:
    """QUEUED | RUNNING -> CANCELLED.

    outcome stays NULL and no error is invented: cancelling is neither a
    scientific result nor a failure.
    """
    row = await _lock_run_or_404(session, run_id)
    if row["status"] == "CANCELLED":
        return row_to_item(row)  # idempotent
    if row["status"] in TERMINAL_DISCOVERY_RUN_STATUSES:
        raise _terminal_conflict(row, "cancel")
    return await _apply(session, row, _SET_CANCEL, {})
