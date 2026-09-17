"""Phase P0-3C1 — Candidate Review Action API.

Real HTTP transport (``httpx.ASGITransport``), real router, real P0-3B service,
real isolated test database, real candidates written through the REAL P0-1
writer. Nothing here calls a handler directly: every assertion is about a POST
request, its status code and its JSON body.

Isolation
---------
The app is driven in the SAME event loop as the test, with ``get_db`` overridden
to hand the endpoints the test's own session — which joins an outer transaction
that is ALWAYS rolled back. The service's own ``commit()`` therefore releases a
SAVEPOINT rather than committing for real.
"""
from __future__ import annotations

import asyncio
import ast
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

import pytest

from app.schemas.llm_discovery import SCHEMA_VERSION

if sys.platform == "win32":  # psycopg async cannot use the Proactor loop
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

BACKEND = Path(__file__).resolve().parents[1]
E2E_DB = os.environ.get("TEST_E2E_DB", "neurographiq_human_brain_v1_e2e")
AUTHORITY_DB = "neurographiq_human_brain_v1"
FALLBACK_SEED = "NGIQ-BR-00001169"          # Left Hippocampus

REVIEW_URL = "/api/knowledge-production/candidates/{candidate_id}/review"

#: The nine public fields. Anything beyond this set is an internal key escaping.
EXPECTED_RESPONSE_FIELDS = {
    "candidate_id", "review_id", "decision", "from_status", "to_status",
    "reviewer", "reviewer_note", "created_at", "next_gate",
}

#: Never reachable through this API.
FORBIDDEN_BODY_TOKENS = (
    "candidate_pk", "review_pk", "discovery_run_pk", "seed_region_pk",
    "INSERT", "UPDATE", "SELECT", "psycopg", "Traceback",
)


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

    async def scalar(self, sql: str, **params: Any) -> Any:
        from sqlalchemy import text

        return (await self.db.execute(text(sql), params)).scalar_one_or_none()

    async def rows(self, sql: str, **params: Any) -> list[Any]:
        from sqlalchemy import text

        return list((await self.db.execute(text(sql), params)).mappings().all())

    async def count(self, sql: str, **params: Any) -> int:
        return int(await self.scalar(sql, **params))


def api_case(fn: Callable[[Session, Any], Awaitable[None]]):
    def wrapper() -> None:
        asyncio.run(_drive(fn))

    wrapper.__name__ = fn.__name__
    wrapper.__qualname__ = fn.__qualname__
    wrapper.__doc__ = fn.__doc__
    return wrapper


async def _drive(fn: Callable[[Session, Any], Awaitable[None]]) -> None:
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
            await fn(Session(db), client)
    finally:
        app.dependency_overrides.pop(get_db, None)
        await db.close()
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


# ===========================================================================
# fixtures — real candidates through the REAL P0-1 writer
# ===========================================================================
def _one_region(seed_entity_id: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION, "seed_entity_id": seed_entity_id,
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


async def _status(h: Session, candidate_id: str) -> str:
    return await h.scalar(
        "SELECT status FROM discovery_candidates WHERE candidate_id = :c", c=candidate_id)


async def _review_count(h: Session) -> int:
    return await h.count("SELECT count(*) FROM candidate_review_records")


async def _post(client: Any, candidate_id: str, **body: Any) -> Any:
    return await client.post(REVIEW_URL.format(candidate_id=candidate_id), json=body)


# ===========================================================================
# 1 / 2 / 3 / 4 / 5 — the three decisions, over real HTTP
# ===========================================================================
@api_case
async def test_1_2_3_each_decision_is_accepted_over_http_with_the_expected_result(h, client):
    for decision, to_status, gate in (
        ("ACCEPT", "accepted", "RESOLUTION_CANONICALIZATION"),
        ("REJECT", "rejected", "TERMINAL"),
        ("DEFER", "deferred", "CANDIDATE_REVIEW"),
    ):
        candidate_id = await _candidate(h)
        before = await _review_count(h)

        response = await _post(client, candidate_id,
                               decision=decision, reviewer="dr.reviewer",
                               reviewer_note="a note")
        assert response.status_code == 200, (decision, response.text)
        body = response.json()

        assert body["candidate_id"] == candidate_id, decision
        assert body["decision"] == decision
        assert body["from_status"] == "proposed"
        assert body["to_status"] == to_status
        assert body["reviewer"] == "dr.reviewer"
        assert body["reviewer_note"] == "a note"
        assert body["next_gate"] == gate, decision
        assert body["review_id"].startswith("NGIQ-CR-")
        assert body["created_at"]

        assert await _status(h, candidate_id) == to_status
        assert await _review_count(h) == before + 1


@api_case
async def test_4_the_response_has_exactly_the_contract_fields(h, client):
    candidate_id = await _candidate(h)
    body = (await _post(client, candidate_id, decision="ACCEPT", reviewer="dr.reviewer")).json()
    assert set(body) == EXPECTED_RESPONSE_FIELDS


@api_case
async def test_4b_a_null_note_is_allowed_and_returned_as_null(h, client):
    candidate_id = await _candidate(h)
    body = (await _post(client, candidate_id, decision="REJECT", reviewer="dr.reviewer")).json()
    assert body["reviewer_note"] is None


@api_case
async def test_5_no_internal_primary_key_leaks_into_the_body(h, client):
    candidate_id = await _candidate(h)
    response = await _post(client, candidate_id, decision="DEFER", reviewer="dr.reviewer")
    for token in ("candidate_pk", "review_pk", "discovery_run_pk", "seed_region_pk"):
        assert token not in response.text, token


# ===========================================================================
# 6 / 7 — unknown candidate, wrong channel
# ===========================================================================
@api_case
async def test_6_an_unknown_candidate_is_404(h, client):
    response = await _post(client, "NGIQ-DC-99999999",
                           decision="ACCEPT", reviewer="dr.reviewer")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "CANDIDATE_NOT_FOUND"


@api_case
async def test_7_a_non_llm_candidate_is_409_not_404_and_not_500(h, client):
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

    response = await _post(client, hostile, decision="ACCEPT", reviewer="dr.reviewer")
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "NOT_AN_LLM_CANDIDATE"
    assert detail["discovery_type"] == "LITERATURE_DISCOVERY"


# ===========================================================================
# 8 / 9 — unusable requests
# ===========================================================================
@api_case
async def test_8_a_blank_reviewer_is_422_and_writes_nothing(h, client):
    candidate_id = await _candidate(h)
    before = await _review_count(h)
    for bad in ("", "   ", "\t"):
        response = await _post(client, candidate_id,
                               decision="ACCEPT", reviewer=bad)
        assert response.status_code == 422, bad
        assert response.json()["detail"]["code"] == "INVALID_REVIEWER"
    assert await _status(h, candidate_id) == "proposed"
    assert await _review_count(h) == before


@api_case
async def test_9_an_invalid_decision_is_422_and_writes_nothing(h, client):
    candidate_id = await _candidate(h)
    before = await _review_count(h)
    for bad in ("MAYBE", "approve", "accepted", "accept"):
        response = await _post(client, candidate_id, decision=bad, reviewer="dr.reviewer")
        assert response.status_code == 422, bad
        assert response.json()["detail"]["code"] == "INVALID_DECISION"
    assert await _status(h, candidate_id) == "proposed"
    assert await _review_count(h) == before


@api_case
async def test_9b_a_missing_reviewer_or_decision_is_rejected_by_the_schema(h, client):
    candidate_id = await _candidate(h)
    assert (await _post(client, candidate_id, decision="ACCEPT")).status_code == 422
    assert (await _post(client, candidate_id, reviewer="dr.reviewer")).status_code == 422


# ===========================================================================
# 10 / 11 / 12 / 13 / 14 — a decided candidate is never decided again
# ===========================================================================
@api_case
async def test_10_11_12_a_second_review_of_any_settled_candidate_is_409(h, client):
    for first in ("ACCEPT", "REJECT", "DEFER"):
        for second in ("ACCEPT", "REJECT", "DEFER"):
            candidate_id = await _candidate(h)
            assert (await _post(client, candidate_id,
                                decision=first, reviewer="dr.first")).status_code == 200
            settled = await _status(h, candidate_id)
            before = await _review_count(h)

            response = await _post(client, candidate_id,
                                   decision=second, reviewer="dr.second")
            assert response.status_code == 409, (first, second, response.text)
            detail = response.json()["detail"]
            assert detail["code"] == "INVALID_REVIEW_TRANSITION"
            assert detail["from_status"] == settled
            assert detail["decision"] == second

            # 13 — no second record.  14 — the state did not move.
            assert await _review_count(h) == before, (first, second)
            assert await _status(h, candidate_id) == settled, (first, second)


@api_case
async def test_13b_the_first_decision_is_the_one_that_stands(h, client):
    candidate_id = await _candidate(h)
    await _post(client, candidate_id, decision="ACCEPT", reviewer="dr.first")
    await _post(client, candidate_id, decision="REJECT", reviewer="dr.second")

    rows = await h.rows(
        "SELECT r.decision, r.reviewer FROM candidate_review_records r"
        " JOIN discovery_candidates c ON c.candidate_pk = r.candidate_pk"
        " WHERE c.candidate_id = :c", c=candidate_id)
    assert len(rows) == 1, "no silent overwrite, no second row"
    assert rows[0]["decision"] == "ACCEPT" and rows[0]["reviewer"] == "dr.first"
    assert await _status(h, candidate_id) == "accepted"


# ===========================================================================
# 15 — next_gate comes from below, not from this layer
# ===========================================================================
@api_case
async def test_15_next_gate_is_the_services_answer_not_a_router_mapping(h, client):
    from unittest.mock import patch

    from app.services import llm_candidate_review_contract as contract

    candidate_id = await _candidate(h)
    with patch.object(contract, "next_candidate_gate", lambda _s: "SENTINEL_GATE"):
        body = (await _post(client, candidate_id,
                            decision="ACCEPT", reviewer="dr.reviewer")).json()
    assert body["next_gate"] == "SENTINEL_GATE", (
        "the router must echo whatever the contract says, not its own table"
    )


# ===========================================================================
# 16 — the router still contains no SQL
# ===========================================================================
def test_16_the_router_contains_no_write_sql():
    from app.routers import llm_discovery_candidates as mod

    src = Path(mod.__file__).read_text(encoding="utf-8")
    doc_lines: set[int] = set()
    for node in ast.walk(ast.parse(src)):
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            doc_lines.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    kept = [line.split("#", 1)[0] for i, line in enumerate(src.splitlines(), start=1)
            if i not in doc_lines and not line.strip().startswith("#")]
    code = "\n".join(kept)

    for forbidden in ("INSERT", "UPDATE", "DELETE", "candidate_review_records",
                      "discovery_candidates", "text(", "session.execute"):
        assert forbidden not in code, forbidden
    # ...and it really does go through the P0-3B service.
    assert "persist_candidate_review" in code
    assert "review_service" in code


# NOTE: the router's exact route surface is asserted in
# test_llm_candidate_read_api.py::test_the_router_declares_exactly_its_three_endpoints
# — one authority for it, not two.


# ===========================================================================
# 17 — the authority database is untouched by all of this
# ===========================================================================
def test_17_the_authority_database_is_untouched():
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
