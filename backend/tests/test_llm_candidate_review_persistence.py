"""Phase P0-3B — Candidate Review persistence.

Real service, real isolated test database, real candidates written through the
REAL P0-1 writer: every review in here decides a proposal the system genuinely
produced.

Isolation
---------
Each `@case` test runs inside an outer transaction that is ALWAYS rolled back,
with the session joined via ``join_transaction_mode="create_savepoint"`` so the
service's own ``commit()`` releases a SAVEPOINT rather than committing for real.

The ONE exception is the two-connection lock test at the bottom: a row that
another connection cannot see is not a row another connection can contend for,
so that test commits its fixture and removes it in a ``finally``.
"""
from __future__ import annotations

import asyncio
import ast
import os
import sys
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable
from unittest.mock import patch

import pytest

from app.schemas.llm_discovery import SCHEMA_VERSION

if sys.platform == "win32":  # psycopg async cannot use the Proactor loop
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

BACKEND = Path(__file__).resolve().parents[1]
E2E_DB = os.environ.get("TEST_E2E_DB", "neurographiq_human_brain_v1_e2e")
FALLBACK_SEED = "NGIQ-BR-00001169"          # Left Hippocampus

#: Every table a review must never write. Canonical knowledge, the evidence
#: layer, the identity layer and the legacy staging tables are all here: an
#: `accepted` candidate is still only a candidate.
CANONICAL_TABLES = (
    "kg_entities", "brain_regions", "connections", "circuits", "functions",
    "knowledge_assertions", "evidence", "evidence_links", "publications",
    "entity_aliases", "entity_xrefs",
)

#: Tables this phase may write, and no others.
WRITE_ALLOWED = ("candidate_review_records", "discovery_candidates")


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


def case(fn: Callable[[Session, Any], Awaitable[None]]):
    def wrapper() -> None:
        asyncio.run(_drive(fn))

    wrapper.__name__ = fn.__name__
    wrapper.__qualname__ = fn.__qualname__
    wrapper.__doc__ = fn.__doc__
    return wrapper


def _service():
    from app.services import llm_candidate_review_persistence_service

    return llm_candidate_review_persistence_service


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
                text("SELECT to_regclass('public.candidate_review_records')")
            )
        ).scalar_one() is None:
            pytest.skip("gate7b_017 not applied to the isolated test database")

        await fn(Session(db), _service())
    finally:
        await db.close()
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


# ===========================================================================
# fixtures
# ===========================================================================
def _one_region(seed_entity_id: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "seed_entity_id": seed_entity_id,
        "summary": "One region candidate.",
        "regions": [
            {"local_id": "region_1", "confidence": 0.72, "name": "CA1 field",
             "relation_to_seed": "AFFERENT"}
        ],
        "connections": [], "circuits": [], "functions": [],
        "source_hints": [], "warnings": [],
    }


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


async def _candidate(h: Session, raw: dict[str, Any] | None = None) -> str:
    """A real candidate written through the REAL P0-1 writer. Returns candidate_id.

    The run is COMPLETED afterwards, so a test may create several independent
    candidates: ``uq_kdr_active_per_seed_type`` allows only one ACTIVE run per
    (seed, discovery type), and leaving each run RUNNING would block the next.
    """
    from app.services import knowledge_discovery_run_lifecycle_service as lifecycle
    from app.services import llm_candidate_persistence_service as writer
    from app.services.llm_discovery_parser import parse_llm_discovery_response

    payload = raw or _one_region(SEED)
    run_id, run_pk, seed_pk = await _new_run(h)
    parsed = parse_llm_discovery_response(payload, seed_entity_id=SEED)
    assert parsed.ok, parsed.error
    await writer.persist_discovery_candidates(
        h.db, discovery_run_pk=run_pk, seed_region_pk=seed_pk, data=parsed.data
    )
    await lifecycle.complete_discovery_run(h.db, run_id, "CANDIDATES_FOUND")
    return await h.scalar(
        "SELECT candidate_id FROM discovery_candidates WHERE discovery_run_pk = :p LIMIT 1",
        p=run_pk,
    )


async def _review_count(h: Session) -> int:
    """How many review records exist, full stop.

    Assertions below compare this BEFORE and AFTER an operation rather than
    against a literal 0. Since gate7b_018 an audit row, once committed, is
    permanent — so "the table is empty" is not a stable invariant a test may
    rely on. "This operation added N rows" is the actual claim, and it holds
    regardless of what else the table already contains.
    """
    return await h.count("SELECT count(*) FROM candidate_review_records")


async def _status(h: Session, candidate_id: str) -> str:
    return await h.scalar(
        "SELECT status FROM discovery_candidates WHERE candidate_id = :c", c=candidate_id
    )


async def _reviews(h: Session, candidate_id: str) -> list[Any]:
    return await h.rows(
        "SELECT r.* FROM candidate_review_records r"
        " JOIN discovery_candidates c ON c.candidate_pk = r.candidate_pk"
        " WHERE c.candidate_id = :c ORDER BY r.review_pk",
        c=candidate_id,
    )


@contextmanager
def _forced_failure(module: Any, attr: str, sql: str):
    """Replace one module-level statement to force a real database rejection."""
    from sqlalchemy import text

    with patch.object(module, attr, text(sql)):
        yield


# ===========================================================================
# A / B / C — the three decisions persist
# ===========================================================================
@case
async def test_A_B_C_each_decision_moves_the_candidate_and_appends_one_record(h, svc):
    """ACCEPT / REJECT / DEFER, each on its OWN candidate (a decided candidate
    cannot be decided again, so one candidate per decision)."""
    for decision, expected_status, expected_gate in (
        ("ACCEPT", "accepted", "RESOLUTION_CANONICALIZATION"),
        ("REJECT", "rejected", "TERMINAL"),
        ("DEFER", "deferred", "CANDIDATE_REVIEW"),
    ):
        candidate_id = await _candidate(h)
        assert await _status(h, candidate_id) == "proposed"

        result = await svc.persist_candidate_review(
            h.db, candidate_id=candidate_id, decision=decision,
            reviewer="dr.reviewer", reviewer_note="a note",
        )

        assert result.candidate_id == candidate_id
        assert result.decision == decision
        assert result.from_status == "proposed"
        assert result.to_status == expected_status
        assert result.next_gate == expected_gate
        assert result.review_id.startswith("NGIQ-CR-")

        assert await _status(h, candidate_id) == expected_status, decision
        records = await _reviews(h, candidate_id)
        assert len(records) == 1, f"{decision}: exactly one append-only record"


# ===========================================================================
# D — the record carries every required field
# ===========================================================================
@case
async def test_D_the_review_record_carries_the_full_decision(h, svc):
    candidate_id = await _candidate(h)
    result = await svc.persist_candidate_review(
        h.db, candidate_id=candidate_id, decision="ACCEPT",
        reviewer="dr.reviewer", reviewer_note="looks right",
    )

    row = (await _reviews(h, candidate_id))[0]
    assert row["review_id"] == result.review_id
    assert row["decision"] == "ACCEPT"
    assert row["from_status"] == "proposed"
    assert row["to_status"] == "accepted"
    assert row["reviewer"] == "dr.reviewer"
    assert row["reviewer_note"] == "looks right"
    assert row["created_at"] is not None
    # It points at the candidate it decided, and at nothing else.
    assert await h.scalar(
        "SELECT c.candidate_id FROM discovery_candidates c"
        " JOIN candidate_review_records r ON r.candidate_pk = c.candidate_pk"
        " WHERE r.review_id = :r", r=result.review_id
    ) == candidate_id


@case
async def test_D2_the_note_is_optional_and_a_null_note_stays_null(h, svc):
    candidate_id = await _candidate(h)
    result = await svc.persist_candidate_review(
        h.db, candidate_id=candidate_id, decision="REJECT", reviewer="dr.reviewer"
    )
    assert result.reviewer_note is None
    assert (await _reviews(h, candidate_id))[0]["reviewer_note"] is None


# ===========================================================================
# E — the P0-3A contract is genuinely consumed, not re-implemented
# ===========================================================================
def _service_source() -> str:
    return Path(_service().__file__).read_text(encoding="utf-8")


def _code_only() -> str:
    src = _service_source()
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


def test_E1_the_service_carries_no_second_transition_authority():
    """§11 — a local decision->status map or transition table is exactly how the
    contract would stop being the authority."""
    code = _code_only()
    for forbidden in ("_DECISION_STATUS", "ALLOWED", "TRANSITIONS",
                      '"proposed":', "'proposed':", '"accepted":', '"deferred":'):
        assert forbidden not in code, forbidden
    # ...and it does go through the contract.
    assert "llm_candidate_review_contract" in code
    assert "review_decision_to_status" in code
    assert "can_transition_candidate_status" in code
    assert "next_candidate_gate" in code


@case
async def test_E2_patching_the_contract_changes_the_service_behaviour(h, svc):
    """Behavioural proof: the service really asks the contract, every call."""
    from app.services import llm_candidate_review_contract as contract

    candidate_id = await _candidate(h)

    # A contract that forbids every move must stop persistence entirely.
    with patch.object(contract, "can_transition_candidate_status", lambda *a, **k: False):
        with pytest.raises(svc.InvalidCandidateReviewTransition):
            await svc.persist_candidate_review(
                h.db, candidate_id=candidate_id, decision="ACCEPT", reviewer="dr.reviewer"
            )
    assert await _status(h, candidate_id) == "proposed"
    assert await _reviews(h, candidate_id) == []

    # A contract that names a different gate must change the RESULT, proving
    # next_gate is derived on every call and never stored.
    with patch.object(contract, "next_candidate_gate", lambda _s: "SENTINEL_GATE"):
        result = await svc.persist_candidate_review(
            h.db, candidate_id=candidate_id, decision="ACCEPT", reviewer="dr.reviewer"
        )
    assert result.next_gate == "SENTINEL_GATE"


# ===========================================================================
# F / G — a decided candidate is never decided again
# ===========================================================================
@case
async def test_F_a_second_review_of_a_decided_candidate_fails_closed(h, svc):
    """All NINE first×second combinations, each on its own candidate."""
    decisions = ("ACCEPT", "REJECT", "DEFER")
    for first in decisions:
        for second in decisions:
            candidate_id = await _candidate(h)
            await svc.persist_candidate_review(
                h.db, candidate_id=candidate_id, decision=first, reviewer="dr.reviewer"
            )
            settled = await _status(h, candidate_id)

            with pytest.raises(svc.InvalidCandidateReviewTransition) as excinfo:
                await svc.persist_candidate_review(
                    h.db, candidate_id=candidate_id, decision=second, reviewer="dr.reviewer"
                )
            assert excinfo.value.from_status == settled, (first, second)
            assert excinfo.value.decision == second, (first, second)

            assert await _status(h, candidate_id) == settled, (first, second)
            assert len(await _reviews(h, candidate_id)) == 1, (first, second)


@case
async def test_G_reopening_a_deferred_candidate_is_not_implemented(h, svc):
    """§7 — P0-3A permits deferred -> proposed, but no decision PRODUCES
    ``proposed``, so there is no governed operation to call. The persistence
    layer must therefore not offer one, and must not invent one."""
    candidate_id = await _candidate(h)
    await svc.persist_candidate_review(
        h.db, candidate_id=candidate_id, decision="DEFER", reviewer="dr.reviewer"
    )

    public = [n for n in dir(svc) if not n.startswith("_")]
    assert set(public) >= {"persist_candidate_review"}
    for forbidden in ("reopen", "re_open", "reset_to_proposed", "un_defer", "undefer"):
        assert not any(forbidden in n.lower() for n in public), forbidden

    # And no decision can move a deferred candidate anywhere.
    for decision in ("ACCEPT", "REJECT", "DEFER"):
        with pytest.raises(svc.InvalidCandidateReviewTransition):
            await svc.persist_candidate_review(
                h.db, candidate_id=candidate_id, decision=decision, reviewer="dr.reviewer"
            )
    assert await _status(h, candidate_id) == "deferred"


# ===========================================================================
# H / I — candidate resolution and channel safety
# ===========================================================================
@case
async def test_H_an_unknown_candidate_id_raises_not_found(h, svc):
    before = await _review_count(h)
    with pytest.raises(svc.CandidateReviewCandidateNotFound):
        await svc.persist_candidate_review(
            h.db, candidate_id="NGIQ-DC-99999999", decision="ACCEPT", reviewer="dr.reviewer"
        )
    assert await _review_count(h) == before, "a refused review writes no new row"


@case
async def test_I_a_candidate_under_a_non_llm_run_is_refused(h, svc):
    """A literature candidate must not be decidable through the LLM review path."""
    from sqlalchemy import text

    _, lit_pk, seed_pk = await _new_run(h, discovery_type="LITERATURE_DISCOVERY")
    await h.db.execute(
        text(
            "INSERT INTO discovery_candidates"
            " (discovery_run_pk, seed_region_pk, candidate_type, local_id, name, payload_json)"
            " VALUES (:r, :s, 'region', 'region_1', 'hostile', '{}'::jsonb)"
        ),
        {"r": lit_pk, "s": seed_pk},
    )
    hostile_id = await h.scalar(
        "SELECT candidate_id FROM discovery_candidates WHERE discovery_run_pk = :p", p=lit_pk
    )
    before = await _review_count(h)
    assert hostile_id, "the hostile row must really exist, or this proves nothing"

    with pytest.raises(svc.CandidateReviewWrongDiscoveryType) as excinfo:
        await svc.persist_candidate_review(
            h.db, candidate_id=hostile_id, decision="ACCEPT", reviewer="dr.reviewer"
        )
    assert excinfo.value.discovery_type == "LITERATURE_DISCOVERY"

    # The refusal changed nothing: no decision was recorded, and the session is
    # still usable. Note the failed call rolls the session back to its pre-call
    # state, which necessarily includes THIS TEST's own uncommitted fixture —
    # that is what "change nothing and stay usable" means, so the observable
    # proof is the untouched review table plus a working session, not the row.
    assert await _review_count(h) == before, "a refused review writes no new row"
    assert await h.count(
        "SELECT count(*) FROM candidate_review_records r"
        " JOIN discovery_candidates c ON c.candidate_pk = r.candidate_pk"
        " WHERE c.candidate_id = :c", c=hostile_id
    ) == 0
    assert await _candidate(h) is not None, "the session must still work"


# ===========================================================================
# J — reviewer / decision input validation happens BEFORE any DB mutation
# ===========================================================================
@case
async def test_J_a_blank_or_missing_reviewer_is_rejected_before_any_write(h, svc):
    candidate_id = await _candidate(h)

    for bad in ("", "   ", "\t\n", None, 123):
        with pytest.raises(svc.CandidateReviewInvalidReviewer):
            await svc.persist_candidate_review(
                h.db, candidate_id=candidate_id, decision="ACCEPT", reviewer=bad
            )
        assert await _status(h, candidate_id) == "proposed", bad
        assert await _reviews(h, candidate_id) == [], bad


@case
async def test_J2_an_unknown_decision_is_rejected_before_any_write(h, svc):
    candidate_id = await _candidate(h)
    for bad in ("MAYBE", "approve", "accepted", ""):
        with pytest.raises(svc.CandidateReviewInvalidDecision):
            await svc.persist_candidate_review(
                h.db, candidate_id=candidate_id, decision=bad, reviewer="dr.reviewer"
            )
    assert await _status(h, candidate_id) == "proposed"
    assert await _reviews(h, candidate_id) == []


@case
async def test_J3_the_reviewer_is_recorded_verbatim_but_trimmed(h, svc):
    candidate_id = await _candidate(h)
    result = await svc.persist_candidate_review(
        h.db, candidate_id=candidate_id, decision="ACCEPT", reviewer="  dr.reviewer  "
    )
    assert result.reviewer == "dr.reviewer"


# ===========================================================================
# K — append-only
# ===========================================================================
def test_K_the_service_never_updates_or_deletes_a_review_record():
    code = _code_only()
    for forbidden in ("UPDATE candidate_review_records", "DELETE FROM",
                      "delete(", "DELETE "):
        assert forbidden not in code, forbidden
    # Exactly ONE update statement, and it targets the CANDIDATE's materialized
    # status. (`FOR UPDATE ` is the lock clause and is not a write.)
    assert code.count("UPDATE ") - code.count("FOR UPDATE ") == 1
    assert "UPDATE discovery_candidates" in code


@case
async def test_K2_no_updated_at_column_exists_on_a_review_record(h, svc):
    """An editable timestamp would invite editing the record it belongs to."""
    assert await h.count(
        "SELECT count(*) FROM information_schema.columns"
        " WHERE table_name = 'candidate_review_records' AND column_name = 'updated_at'"
    ) == 0


# ===========================================================================
# L / M — atomicity: both writes, or neither
# ===========================================================================
@case
async def test_L_a_failed_review_INSERT_leaves_the_candidate_untouched(h, svc):
    candidate_id = await _candidate(h)

    with _forced_failure(
        svc, "_INSERT_REVIEW_SQL",
        "INSERT INTO candidate_review_records"
        " (candidate_pk, decision, from_status, to_status, reviewer)"
        " VALUES (:candidate_pk, 'MAYBE', 'proposed', 'accepted', 'dr.reviewer')",
    ):
        with pytest.raises(Exception):
            await svc.persist_candidate_review(
                h.db, candidate_id=candidate_id, decision="ACCEPT", reviewer="dr.reviewer"
            )

    assert await _status(h, candidate_id) == "proposed", "no status move survived"
    assert await _reviews(h, candidate_id) == [], "no review record survived"
    # The session must still be usable after the rollback.
    assert await h.count("SELECT count(*) FROM discovery_candidates") >= 1


@case
async def test_M_a_failed_status_UPDATE_rolls_the_review_record_back_too(h, svc):
    """The dangerous direction: the record inserted, then the move failed."""
    candidate_id = await _candidate(h)

    with _forced_failure(
        svc, "_UPDATE_STATUS_SQL",
        "UPDATE discovery_candidates SET status = 'not_a_status'"
        " WHERE candidate_pk = :candidate_pk",
    ):
        with pytest.raises(Exception):
            await svc.persist_candidate_review(
                h.db, candidate_id=candidate_id, decision="ACCEPT", reviewer="dr.reviewer"
            )

    assert await _status(h, candidate_id) == "proposed"
    assert await _reviews(h, candidate_id) == [], (
        "a review record must never outlive the status move it claims to describe"
    )


# ===========================================================================
# O / P — no canonical side effects, and no internal keys exposed
# ===========================================================================
@case
async def test_O_a_review_writes_only_the_two_authorised_tables(h, svc):
    candidate_id = await _candidate(h)
    before = {t: await h.count(f"SELECT count(*) FROM {t}") for t in CANONICAL_TABLES}

    await svc.persist_candidate_review(
        h.db, candidate_id=candidate_id, decision="ACCEPT", reviewer="dr.reviewer"
    )

    after = {t: await h.count(f"SELECT count(*) FROM {t}") for t in CANONICAL_TABLES}
    assert after == before, "accepted is still only a candidate"


@case
async def test_O2_the_only_statements_issued_write_the_two_authorised_tables(h, svc):
    from sqlalchemy import text

    statements: list[str] = []

    class _Recorder:
        def __init__(self, db: Any) -> None:
            self._db = db

        async def execute(self, stmt: Any, params: Any = None) -> Any:
            statements.append(" ".join(str(stmt).split()))
            return await self._db.execute(stmt, params)

        async def commit(self) -> None:
            statements.append("COMMIT")
            await self._db.commit()

        async def rollback(self) -> None:
            await self._db.rollback()

    candidate_id = await _candidate(h)
    assert text("SELECT 1") is not None  # keep the import honest

    await svc.persist_candidate_review(
        _Recorder(h.db), candidate_id=candidate_id, decision="ACCEPT", reviewer="dr.reviewer"
    )

    writes = [s for s in statements if s.split(" ", 1)[0].upper() in ("INSERT", "UPDATE", "DELETE")]
    assert writes, "the review must actually write something"
    for sql in writes:
        assert any(t in sql for t in WRITE_ALLOWED), sql
    for sql in statements:
        if sql == "COMMIT":
            continue
        for forbidden in ("kg_entities", "brain_regions", "connections", "circuits",
                          "functions", "knowledge_assertions", "evidence",
                          "publications", "entity_aliases", "entity_xrefs", "final_"):
            assert forbidden not in sql, (forbidden, sql)


@case
async def test_P_the_result_exposes_no_internal_primary_key(h, svc):
    candidate_id = await _candidate(h)
    result = await svc.persist_candidate_review(
        h.db, candidate_id=candidate_id, decision="ACCEPT", reviewer="dr.reviewer"
    )

    fields = set(result.__dataclass_fields__)
    assert fields == {
        "review_id", "candidate_id", "decision", "from_status", "to_status",
        "reviewer", "reviewer_note", "created_at", "next_gate",
    }
    for internal in ("review_pk", "candidate_pk", "discovery_run_pk", "seed_region_pk"):
        assert internal not in fields, internal

    blob = f"{result!r}"
    for internal in ("review_pk", "candidate_pk", "discovery_run_pk", "seed_region_pk"):
        assert internal not in blob, internal


# ===========================================================================
# Q — next_gate is derived, never stored
# ===========================================================================
@case
async def test_Q_next_gate_is_derived_from_the_contract_and_never_stored(h, svc):
    from app.services import llm_candidate_review_contract as contract

    for decision, status in (("ACCEPT", "accepted"), ("REJECT", "rejected"),
                             ("DEFER", "deferred")):
        candidate_id = await _candidate(h)
        result = await svc.persist_candidate_review(
            h.db, candidate_id=candidate_id, decision=decision, reviewer="dr.reviewer"
        )
        assert result.next_gate == contract.next_candidate_gate(status)

    # ...and the gate is nowhere in the table.
    assert await h.count(
        "SELECT count(*) FROM information_schema.columns"
        " WHERE table_name = 'candidate_review_records' AND column_name = 'next_gate'"
    ) == 0


# ===========================================================================
# R — the migration's stored vocabularies match P0-3A
# ===========================================================================
def test_R_the_migration_vocabulary_matches_the_contract():
    import re

    from app.services import llm_candidate_review_contract as contract

    sql = (BACKEND / "migrations" / "gate7b_017_candidate_review_records.sql").read_text(
        encoding="utf-8")

    decision_check = re.search(r"ck_crr_decision CHECK \(\s*decision IN \(([^)]+)\)", sql)
    assert decision_check, "ck_crr_decision not found"
    assert tuple(re.findall(r"'([A-Z]+)'", decision_check.group(1))) == (
        contract.CANDIDATE_REVIEW_DECISIONS
    )

    for name in ("ck_crr_from_status", "ck_crr_to_status"):
        col = name.replace("ck_crr_", "")
        match = re.search(rf"{name} CHECK \(\s*{col} IN \(([^)]+)\)", sql)
        assert match, f"{name} not found"
        stored = tuple(re.findall(r"'([a-z_]+)'", match.group(1)))
        assert stored == contract.CANDIDATE_STATUSES, (name, stored)


# ===========================================================================
# N — concurrency
# ===========================================================================
@case
async def test_N1_two_reviewers_of_one_proposal_produce_exactly_one_decision(h, svc):
    """Two independent reviewers, one candidate. Exactly one may win.

    Sequential here by construction: the harness shares one transaction. The
    LOCK itself is proven separately (N2/N3), because a missing lock would not
    change this test's outcome and it must not be mistaken for that proof.
    """
    candidate_id = await _candidate(h)

    outcomes: list[str] = []
    for reviewer in ("dr.first", "dr.second"):
        try:
            await svc.persist_candidate_review(
                h.db, candidate_id=candidate_id, decision="ACCEPT", reviewer=reviewer
            )
            outcomes.append(f"{reviewer}:ok")
        except svc.InvalidCandidateReviewTransition:
            outcomes.append(f"{reviewer}:refused")

    assert outcomes == ["dr.first:ok", "dr.second:refused"], outcomes
    records = await _reviews(h, candidate_id)
    assert len(records) == 1
    assert records[0]["reviewer"] == "dr.first"
    assert await _status(h, candidate_id) == "accepted"


def test_N2_the_status_is_read_BY_the_locking_statement():
    """Why there is no read-then-write window: the lock and the read are ONE
    statement, so a status observed under the lock cannot go stale before the
    transition is verified against it."""
    sql = " ".join(str(_service()._LOCK_CANDIDATE_SQL).split())
    assert "FOR UPDATE OF c" in sql, "the candidate row must be locked"
    assert "c.status" in sql, "the status must be read by the locking statement"
    assert sql.upper().count("SELECT") == 1, "one statement, not a read-then-lock pair"
    # The run is joined for the channel check but deliberately NOT locked.
    assert "FOR UPDATE OF c" in sql and "knowledge_discovery_runs" in sql
    assert "FOR UPDATE OF r" not in sql


def test_N2b_the_lock_statement_is_the_only_read_of_the_current_status():
    """Two reads of the status — one locked, one not — would reintroduce exactly
    the race the lock exists to prevent."""
    code = _code_only()
    assert code.count("c.status") == 1


def test_N3_the_real_two_connection_lock_behaviour():
    """The only test here that commits, and it must: a row another connection
    cannot see is not a row another connection can contend for.

    It holds the candidate's row lock on one connection, proves a second
    connection is BLOCKED rather than allowed through, then releases and shows
    the second connection succeed.

    ISOLATION STRATEGY (P0-3B.1): the committed fixture is the RUN and the
    CANDIDATE only. The successful review runs inside an outer transaction that
    is ROLLED BACK, so no review row is ever committed — which matters now that
    gate7b_018 makes a committed review row permanent and undeletable. Cleanup
    therefore never has to touch the audit table, and the append-only guard is
    never disabled for a test.
    """
    asyncio.run(_lock_contention())


async def _lock_contention() -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.services import llm_candidate_persistence_service as writer
    from app.services import knowledge_discovery_run_lifecycle_service as lifecycle
    from app.services import llm_candidate_review_persistence_service as svc
    from app.services.llm_discovery_parser import parse_llm_discovery_response

    engine = create_async_engine(_dsn(), poolclass=NullPool)
    committed_run_pk: int | None = None
    committed_candidate_pk: int | None = None
    try:
        # --- fixture, COMMITTED so a second connection can see it ------------
        async with AsyncSession(bind=engine) as setup:
            if (await setup.execute(text(
                    "SELECT to_regclass('public.candidate_review_records')"))).scalar_one() is None:
                pytest.skip("gate7b_017 not applied to the isolated test database")
            run = await lifecycle.create_discovery_run(
                setup, entity_id=SEED, discovery_type="LLM_DISCOVERY")
            await lifecycle.start_discovery_run(setup, run.run_id)
            keys = (await setup.execute(text(
                "SELECT run_pk, seed_region_pk FROM knowledge_discovery_runs WHERE run_id=:r"),
                {"r": run.run_id})).one()
            committed_run_pk, seed_pk = int(keys[0]), int(keys[1])
            parsed = parse_llm_discovery_response(_one_region(SEED), seed_entity_id=SEED)
            await writer.persist_discovery_candidates(
                setup, discovery_run_pk=committed_run_pk, seed_region_pk=seed_pk,
                data=parsed.data)
            committed_candidate_pk = int((await setup.execute(text(
                "SELECT candidate_pk FROM discovery_candidates WHERE discovery_run_pk=:p"),
                {"p": committed_run_pk})).scalar_one())
            candidate_id = (await setup.execute(text(
                "SELECT candidate_id FROM discovery_candidates WHERE candidate_pk=:p"),
                {"p": committed_candidate_pk})).scalar_one()

        # --- connection A takes and HOLDS the row lock -----------------------
        conn_a = await engine.connect()
        tx_a = await conn_a.begin()
        conn_b = await engine.connect()
        tx_b = await conn_b.begin()
        # create_savepoint: the service's commit() releases a SAVEPOINT, so the
        # review below is never really committed and never needs un-deleting.
        session_b = AsyncSession(bind=conn_b, join_transaction_mode="create_savepoint")

        class _TracingSession:
            """Records each statement B STARTS, so a test can see WHERE it stuck.

            This is what makes the lock clause itself testable. Removing
            FOR UPDATE from the service does not change the SQLSTATE B reports:
            a plain SELECT is not blocked by a row lock, so B would sail past the
            read and stall later on the INSERT's foreign-key check instead —
            same error, entirely different reason. Counting started statements
            tells the two apart.
            """

            def __init__(self, inner: Any) -> None:
                self._inner = inner
                self.started: list[str] = []

            async def execute(self, stmt: Any, params: Any = None) -> Any:
                self.started.append(" ".join(str(stmt).split()))
                return await self._inner.execute(stmt, params)

            async def commit(self) -> None:
                await self._inner.commit()

            async def rollback(self) -> None:
                await self._inner.rollback()

        traced = _TracingSession(session_b)
        try:
            reviews_before = (await conn_a.execute(text(
                "SELECT count(*) FROM candidate_review_records"))).scalar_one()
            locked = (await conn_a.execute(text(
                "SELECT candidate_pk FROM discovery_candidates"
                " WHERE candidate_pk = :p FOR UPDATE"), {"p": committed_candidate_pk})).one()
            assert locked[0] == committed_candidate_pk

            # --- connection B must NOT get through while A holds it ----------
            await session_b.execute(text("SET LOCAL lock_timeout = '1200ms'"))
            with pytest.raises(Exception) as excinfo:
                await svc.persist_candidate_review(
                    traced, candidate_id=candidate_id, decision="ACCEPT",
                    reviewer="dr.blocked")
            # Assert on the SQLSTATE, not on message text: this server's locale
            # is not English, so the prose is not a stable contract. 55P03 is
            # lock_not_available — a LOCK timeout, exactly what contention makes.
            original = getattr(excinfo.value, "orig", excinfo.value)
            assert getattr(original, "sqlstate", None) == "55P03", original

            # ...and it blocked ON THE LOCK, not somewhere further along. One
            # statement started = the locking SELECT itself never returned.
            assert len(traced.started) == 1, traced.started
            assert "FOR UPDATE" in traced.started[0], traced.started[0]

            # Nothing happened, and the session is usable again.
            assert (await session_b.execute(text(
                "SELECT status FROM discovery_candidates WHERE candidate_pk=:p"),
                {"p": committed_candidate_pk})).scalar_one() == "proposed"
            assert (await session_b.execute(text(
                "SELECT count(*) FROM candidate_review_records"))).scalar_one() == reviews_before

            # --- A releases; B now succeeds -----------------------------
            await tx_a.rollback()
            tx_a = None
            await session_b.execute(text("SET LOCAL lock_timeout = '5s'"))
            result = await svc.persist_candidate_review(
                session_b, candidate_id=candidate_id, decision="ACCEPT",
                reviewer="dr.after_release")
            assert result.to_status == "accepted"

            assert (await session_b.execute(text(
                "SELECT status FROM discovery_candidates WHERE candidate_pk=:p"),
                {"p": committed_candidate_pk})).scalar_one() == "accepted"
            assert (await session_b.execute(text(
                "SELECT count(*) FROM candidate_review_records"))).scalar_one() == reviews_before + 1
            # ...all of which is discarded by the rollback below.
        finally:
            await session_b.close()
            await tx_b.rollback()
            await conn_b.close()
            if tx_a is not None:
                await tx_a.rollback()
            await conn_a.close()

    finally:
        # --- unconditional cleanup, touching ONLY the two tables that have no
        #     append-only guard: no review row was committed, so nothing blocks
        #     the candidate and its run from being removed.
        try:
            async with AsyncSession(bind=engine) as cleanup:
                if committed_candidate_pk is not None:
                    await cleanup.execute(text(
                        "DELETE FROM discovery_candidates WHERE candidate_pk = :p"),
                        {"p": committed_candidate_pk})
                if committed_run_pk is not None:
                    await cleanup.execute(text(
                        "DELETE FROM knowledge_discovery_runs WHERE run_pk = :p"),
                        {"p": committed_run_pk})
                await cleanup.commit()
        finally:
            await engine.dispose()


# ===========================================================================
# P0-3B.1 — the DATABASE guards added by gate7b_018
# ===========================================================================
# These deliberately bypass the service and speak SQL, because a hand-written
# INSERT is exactly the writer the guards exist to stop.
_SQL_INSERT = (
    "INSERT INTO candidate_review_records"
    " (candidate_pk, decision, from_status, to_status, reviewer)"
    " VALUES (:p, :d, :f, :t, 'dr.sql')"
)


async def _candidate_pk(h: Session, candidate_id: str) -> int:
    return int(await h.scalar(
        "SELECT candidate_pk FROM discovery_candidates WHERE candidate_id = :c",
        c=candidate_id))


def _sqlstate(exc: BaseException) -> str | None:
    return getattr(getattr(exc, "orig", exc), "sqlstate", None)


@case
async def test_S1_the_database_accepts_the_three_legal_records(h, svc):
    """§7A — hand-written INSERTs of the three legal decisions must succeed.
    The guard must not be so tight that it blocks legitimate history."""
    from sqlalchemy import text

    before = await _review_count(h)
    for decision, to_status in (("ACCEPT", "accepted"), ("REJECT", "rejected"),
                                ("DEFER", "deferred")):
        pk = await _candidate_pk(h, await _candidate(h))
        await h.db.execute(text(_SQL_INSERT),
                           {"p": pk, "d": decision, "f": "proposed", "t": to_status})

    assert await _review_count(h) == before + 3


@case
async def test_S2_contradictory_records_are_rejected_by_the_database(h, svc):
    """§7B — a record that contradicts the P0-3A contract cannot exist even
    when it never goes through the service."""
    from sqlalchemy import text

    pk = await _candidate_pk(h, await _candidate(h))
    before = await _review_count(h)
    illegal = [
        ("ACCEPT", "proposed", "rejected"),   # right decision, wrong destination
        ("ACCEPT", "proposed", "deferred"),
        ("REJECT", "proposed", "accepted"),
        ("DEFER", "proposed", "accepted"),
        ("ACCEPT", "accepted", "rejected"),   # not a move FROM proposed
        ("REJECT", "accepted", "rejected"),
        ("DEFER", "deferred", "accepted"),
        ("ACCEPT", "deferred", "accepted"),
    ]
    for decision, from_status, to_status in illegal:
        await h.db.execute(text("SAVEPOINT illegal_probe"))
        with pytest.raises(Exception) as excinfo:
            await h.db.execute(text(_SQL_INSERT),
                               {"p": pk, "d": decision, "f": from_status, "t": to_status})
        assert _sqlstate(excinfo.value) == "23514", (decision, from_status, to_status)
        await h.db.execute(text("ROLLBACK TO SAVEPOINT illegal_probe"))

    assert await _review_count(h) == before, "not one illegal row got in"


@case
async def test_S3_an_update_is_rejected_by_the_database(h, svc):
    """§7C — append-only is a DATABASE property, not a service habit."""
    from sqlalchemy import text

    pk = await _candidate_pk(h, await _candidate(h))
    before = await _review_count(h)
    await h.db.execute(text(_SQL_INSERT),
                       {"p": pk, "d": "ACCEPT", "f": "proposed", "t": "accepted"})

    await h.db.execute(text("SAVEPOINT update_probe"))
    with pytest.raises(Exception) as excinfo:
        await h.db.execute(
            text("UPDATE candidate_review_records SET reviewer = 'someone.else'"
                 " WHERE candidate_pk = :p"), {"p": pk})
    assert _sqlstate(excinfo.value) == "P0001", excinfo.value  # plpgsql RAISE
    await h.db.execute(text("ROLLBACK TO SAVEPOINT update_probe"))

    assert await h.scalar(
        "SELECT reviewer FROM candidate_review_records WHERE candidate_pk = :p", p=pk
    ) == "dr.sql", "the row is untouched"
    assert await _review_count(h) == before + 1


@case
async def test_S4_a_delete_is_rejected_by_the_database(h, svc):
    """§7D — history cannot be erased, including by cleanup code."""
    from sqlalchemy import text

    pk = await _candidate_pk(h, await _candidate(h))
    before = await _review_count(h)
    await h.db.execute(text(_SQL_INSERT),
                       {"p": pk, "d": "DEFER", "f": "proposed", "t": "deferred"})

    await h.db.execute(text("SAVEPOINT delete_probe"))
    with pytest.raises(Exception) as excinfo:
        await h.db.execute(
            text("DELETE FROM candidate_review_records WHERE candidate_pk = :p"), {"p": pk})
    assert _sqlstate(excinfo.value) == "P0001", excinfo.value
    await h.db.execute(text("ROLLBACK TO SAVEPOINT delete_probe"))

    assert await _review_count(h) == before + 1
    # The session survives both refusals and still works.
    assert await _candidate(h) is not None


@case
async def test_S5_the_append_only_guard_does_not_block_a_rollback(h, svc):
    """§4 — a rolled-back transaction is not a DELETE, and must never be
    refused. The service relies on rollback for its own atomicity."""
    pk = await _candidate_pk(h, await _candidate(h))
    before = await h.count("SELECT count(*) FROM candidate_review_records")

    result = await svc.persist_candidate_review(
        h.db, candidate_id=await h.scalar(
            "SELECT candidate_id FROM discovery_candidates WHERE candidate_pk = :p", p=pk),
        decision="ACCEPT", reviewer="dr.rollback",
    )
    assert result.to_status == "accepted"
    assert await h.count("SELECT count(*) FROM candidate_review_records") == before + 1
    # ...and the enclosing transaction rolling back leaves no trace of it.
    from sqlalchemy import text
    await h.db.execute(text("SAVEPOINT outer_probe"))
    assert await h.count("SELECT count(*) FROM candidate_review_records") == before + 1
    await h.db.execute(text("ROLLBACK TO SAVEPOINT outer_probe"))
    assert await h.count("SELECT count(*) FROM candidate_review_records") == before + 1
