"""Durable provider-response forensics for a Discovery run.

Closes DISCOVERY_FAILED_RAW_RESPONSE_AUDIT_GAP: a failed run must retain enough
bounded evidence to answer "what did the provider actually return?" long after
the process is gone.

What is REAL here: the run table, the new columns, the CHECK constraints that
bound them, the lifecycle write path and the persistence of zero candidates.
What is STUBBED: the provider call, and only the provider call. No network, no
DeepSeek, and every test rolls its transaction back, so the database is left
exactly as it was found.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from app.schemas.llm_discovery import SCHEMA_VERSION

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

BACKEND = Path(__file__).resolve().parents[1]
E2E_DB = os.environ.get("TEST_E2E_DB", "neurographiq_human_brain_v1_e2e")
AUTHORITY_DB = "neurographiq_human_brain_v1"
FORENSIC_COLUMNS = (
    "response_sha256", "raw_response_preview", "finish_reason",
    "prompt_tokens", "completion_tokens", "total_tokens",
    "provider_latency_ms", "fallback_raw_response_used",
)


def _cfg() -> dict[str, str]:
    cfg: dict[str, str] = {}
    env = BACKEND / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg


def _dsn(db: str = E2E_DB) -> str:
    cfg = _cfg()
    return "postgresql+psycopg://%s:%s@%s:%s/%s" % (
        cfg.get("POSTGRES_USER"), cfg.get("POSTGRES_PASSWORD"),
        cfg.get("POSTGRES_HOST", "127.0.0.1"), cfg.get("POSTGRES_PORT", "5432"), db)


def _resolve_seed() -> str:
    """A region with no discovery history, so each test starts from Round 1."""
    try:
        import psycopg

        with psycopg.connect(_dsn().replace("+psycopg", "")) as conn:
            row = conn.execute(
                "SELECT e.entity_id FROM brain_regions b"
                " JOIN kg_entities e ON e.entity_pk = b.entity_pk"
                " WHERE NOT EXISTS (SELECT 1 FROM knowledge_discovery_runs r"
                "                    WHERE r.seed_region_pk = b.entity_pk)"
                " ORDER BY e.entity_id LIMIT 1").fetchone()
        return row[0] if row else "NGIQ-BR-00001169"
    except Exception:  # pragma: no cover
        return "NGIQ-BR-00001169"


SEED = _resolve_seed()


def case(fn):
    def wrapper() -> None:
        asyncio.run(_drive(fn))

    wrapper.__name__ = fn.__name__
    wrapper.__qualname__ = fn.__qualname__
    wrapper.__doc__ = fn.__doc__
    return wrapper


async def _drive(fn) -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(_dsn(), poolclass=NullPool)
    try:
        connection = await engine.connect()
    except Exception as exc:  # pragma: no cover
        await engine.dispose()
        pytest.skip(f"isolated test database unavailable: {type(exc).__name__}")

    transaction = await connection.begin()
    db = AsyncSession(bind=connection, join_transaction_mode="create_savepoint")
    try:
        present = (await connection.execute(text(
            "SELECT count(*) FROM information_schema.columns"
            " WHERE table_name = 'knowledge_discovery_runs'"
            "   AND column_name = 'response_sha256'"))).scalar_one()
        if not present:
            pytest.skip("gate7b_022 not applied to the isolated test database")
        await fn(db)
    finally:
        await db.close()
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


# ===========================================================================
# the stubbed provider
# ===========================================================================
class _Usage:
    def __init__(self, prompt: int = 11, completion: int = 22, total: int = 33):
        self.prompt_tokens = prompt
        self.completion_tokens = completion
        self.total_tokens = total
        self.reasoning_tokens = 0

    def as_dict(self) -> dict[str, int]:
        return {}


class _Response:
    def __init__(self, text: str, *, finish_reason: str = "stop", latency_ms: int = 1234,
                 fallback: bool = False):
        self.raw_text = text
        self.parsed_json = None
        self.transport_ok = True
        self.provider = "deepseek"
        self.model = "deepseek-flash"
        self.finish_reason = finish_reason
        self.error_message = None
        self.latency_ms = latency_ms
        self.usage = _Usage()
        self.response_payload = {"fallback_raw_response_used": fallback} if fallback else {}
        self.request_payload_redacted = {}
        self.response_format = None
        self.fallback_raw_response_used = fallback


class _Provider:
    def __init__(self, response: _Response):
        self.response = response
        self.calls = 0

    async def complete_json(self, **kwargs):
        self.calls += 1
        return self.response


def _envelope(**over: Any) -> str:
    body = {
        "schema_version": SCHEMA_VERSION, "seed_entity_id": SEED, "summary": "forensics",
        "regions": [], "connections": [], "functions": [], "circuits": [],
        "source_hints": [], "warnings": [],
    }
    body.update(over)
    return json.dumps(body)


def _long_failing_response(summary: str) -> str:
    """A long response that must fail: an unknown NON-EMPTY extra on a circuit.

    Length and failure are independent here, so the preview bound can be tested
    without the response accidentally parsing.
    """
    return _envelope(summary=summary, circuits=[{
        "local_id": "circuit_1", "name": "X", "confidence": 0.5,
        "species_context": {"scope": "HUMAN", "taxon_ids": [9606]},
        "invented_field": "carries meaning",
    }])


BARE_REGION = json.dumps({
    "local_id": "region_1", "confidence": 0.9, "name": "Dentate gyrus (granule cell layer)",
    "name_en": "Dentate gyrus", "name_zh": "齿状回", "hemisphere_context": "LEFT",
    "species_taxon_id": "9606", "relation_to_seed": "AFFERENT",
    "rationale": "Primary afferent source of the dentate-CA3 sub-circuits.",
}, ensure_ascii=False)


async def _run_failing(session, response: _Response):
    """Execute one discovery against the stubbed provider, returning the error."""
    from app.services import llm_discovery_execution_service as execution

    provider = _Provider(response)
    with patch.object(execution, "get_llm_provider", lambda _n: provider):
        try:
            await execution.execute_llm_discovery(session, entity_id=SEED)
        except execution.LlmDiscoveryExecutionError as exc:
            return exc, provider.calls
    raise AssertionError("the execution was expected to fail")


async def _rows(session, sql: str, **p):
    from sqlalchemy import text

    return list((await session.execute(text(sql), p)).mappings().all())


async def _latest(session):
    return (await _rows(
        session,
        "SELECT r.run_id::text, r.status, r.error_code,"
        "       r.response_sha256, r.raw_response_preview, r.finish_reason,"
        "       r.prompt_tokens, r.completion_tokens, r.total_tokens,"
        "       r.provider_latency_ms, r.fallback_raw_response_used,"
        "       (SELECT count(*) FROM discovery_candidates dc"
        "         WHERE dc.discovery_run_pk = r.run_pk) AS candidates"
        "  FROM knowledge_discovery_runs r"
        "  JOIN brain_regions b ON b.entity_pk = r.seed_region_pk"
        "  JOIN kg_entities e ON e.entity_pk = b.entity_pk"
        " WHERE e.entity_id = :s ORDER BY r.run_pk DESC LIMIT 1", s=SEED))[0]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ===========================================================================
# A / H / I / L — the success path keeps working, and now records evidence too
# ===========================================================================
@case
async def test_A_a_successful_run_stores_the_hash_of_the_full_response(session):
    from app.services import llm_discovery_execution_service as execution

    text = _envelope(regions=[{"local_id": "region_1", "name": "R1", "confidence": 0.5}])
    provider = _Provider(_Response(text))
    with patch.object(execution, "get_llm_provider", lambda _n: provider):
        result = await execution.execute_llm_discovery(session, entity_id=SEED)

    row = await _latest(session)
    assert row["run_id"] == str(result.run.run_id)
    assert row["status"] == "COMPLETED"
    assert row["response_sha256"] == _sha(text), "the FULL response was hashed"
    assert row["raw_response_preview"] == text
    assert row["finish_reason"] == "stop"


@case
async def test_H_I_token_and_latency_metadata_are_persisted(session):
    text = _envelope()
    await _run_ok(session, _Response(text, latency_ms=4242))

    row = await _latest(session)
    assert (row["prompt_tokens"], row["completion_tokens"], row["total_tokens"]) == (11, 22, 33)
    assert row["provider_latency_ms"] == 4242


@case
async def test_L_successful_candidate_persistence_is_unchanged(session):
    text = _envelope(regions=[{"local_id": "region_1", "name": "R1", "confidence": 0.5}])
    await _run_ok(session, _Response(text))

    row = await _latest(session)
    assert row["status"] == "COMPLETED"
    assert int(row["candidates"]) == 1, "the proposals are still stored"


async def _run_ok(session, response: _Response):
    from app.services import llm_discovery_execution_service as execution

    provider = _Provider(response)
    with patch.object(execution, "get_llm_provider", lambda _n: provider):
        return await execution.execute_llm_discovery(session, entity_id=SEED)


# ===========================================================================
# B / C — a failed response is now readable after the fact
# ===========================================================================
@case
async def test_B_a_schema_invalid_response_stores_preview_hash_and_finish_reason(session):
    text = _envelope(circuits=[{"local_id": "circuit_1", "name": "X", "confidence": 0.5,
                                "species_context": {"scope": "HUMAN", "taxon_ids": [9606]},
                                "invented_field": "carries meaning"}])
    exc, calls = await _run_failing(session, _Response(text, finish_reason="stop"))

    assert exc.code == "LLM_DISCOVERY_PARSE_FAILED"
    assert calls == 1
    row = await _latest(session)
    assert row["status"] == "FAILED"
    assert row["response_sha256"] == _sha(text)
    assert row["raw_response_preview"].startswith('{"schema_version"')
    assert row["finish_reason"] == "stop"


@case
async def test_C_an_envelope_failure_stores_forensic_metadata(session):
    """The R21 shape: a bare candidate where the document should be."""
    exc, _ = await _run_failing(session, _Response(BARE_REGION))

    assert exc.code == "LLM_DISCOVERY_PARSE_FAILED"
    assert "DISCOVERY_ENVELOPE_MISSING" in exc.message
    row = await _latest(session)
    assert row["status"] == "FAILED"
    assert row["response_sha256"] == _sha(BARE_REGION)
    assert "Dentate gyrus" in row["raw_response_preview"]


# ===========================================================================
# D — an empty response says so, and does NOT pretend to have content
# ===========================================================================
@case
async def test_D_an_empty_response_records_no_content_truthfully(session):
    exc, _ = await _run_failing(session, _Response("", finish_reason="length"))

    assert exc.code == "LLM_EMPTY_RESPONSE"
    row = await _latest(session)
    assert row["status"] == "FAILED"
    assert row["response_sha256"] is None, "no content -> NULL, never sha256('')"
    assert row["raw_response_preview"] is None
    assert row["finish_reason"] == "length", "the stop reason is still evidence"
    assert row["fallback_raw_response_used"] is False


@case
async def test_D2_a_fallback_raw_body_dump_is_flagged_and_retained(session):
    """A salvaged HTTP body is never parsed as a result, but it IS evidence."""
    dump = '{"error": {"message": "upstream unavailable"}, "choices": []}'
    exc, _ = await _run_failing(session, _Response(dump, fallback=True))

    assert exc.code == "LLM_EMPTY_RESPONSE"
    row = await _latest(session)
    assert row["fallback_raw_response_used"] is True
    assert row["response_sha256"] == _sha(dump), "the dump is still hashed"


# ===========================================================================
# E / F / G — the preview is bounded, the hash is not
# ===========================================================================
@case
async def test_E_a_long_response_is_previewed_but_hashed_in_full(session):
    text = _long_failing_response("x" * 6000)
    assert len(text) > 6000
    await _run_failing(session, _Response(text))

    row = await _latest(session)
    assert len(row["raw_response_preview"]) <= 2048, "bounded in code AND by the CHECK"
    assert row["raw_response_preview"].startswith('{"schema_version"')
    assert "truncated" in row["raw_response_preview"], "how much was cut is recorded"
    assert row["response_sha256"] == _sha(text), "the hash covers the WHOLE response"


@case
async def test_F_the_same_response_produces_the_same_hash(session):
    text = _long_failing_response("identical")
    await _run_failing(session, _Response(text, latency_ms=10))
    first = (await _latest(session))["response_sha256"]

    await _run_failing(session, _Response(text, latency_ms=999))
    second = (await _latest(session))["response_sha256"]

    assert first == second == _sha(text)


@case
async def test_G_a_shared_prefix_with_a_different_tail_has_a_different_hash(session):
    """The case a bounded preview alone cannot settle."""
    body = "y" * 3000
    one = _long_failing_response(body + "TAIL-ONE")
    two = _long_failing_response(body + "TAIL-TWO")

    await _run_failing(session, _Response(one))
    await _run_failing(session, _Response(two))
    rows = await _rows(
        session,
        "SELECT r.response_sha256, r.raw_response_preview, r.run_pk"
        "  FROM knowledge_discovery_runs r"
        "  JOIN brain_regions b ON b.entity_pk = r.seed_region_pk"
        "  JOIN kg_entities e ON e.entity_pk = b.entity_pk"
        " WHERE e.entity_id = :s ORDER BY r.run_pk", s=SEED)
    first, second = rows[0], rows[1]

    assert first["raw_response_preview"] == second["raw_response_preview"], (
        "the previews are indistinguishable — that is the point"
    )
    assert first["response_sha256"] != second["response_sha256"], (
        "the hash still separates them, because it covers the full text"
    )


# ===========================================================================
# J / K — a failed run still creates nothing
# ===========================================================================
@case
async def test_J_K_a_failed_run_persists_zero_candidates(session):
    for text in (BARE_REGION, _envelope(circuits=[{"local_id": "circuit_1"}]), ""):
        await _run_failing(session, _Response(text))
    row = await _latest(session)
    assert int(row["candidates"]) == 0

    total = (await _rows(
        session,
        "SELECT count(*) AS n FROM discovery_candidates dc"
        "  JOIN knowledge_discovery_runs r ON r.run_pk = dc.discovery_run_pk"
        "  JOIN brain_regions b ON b.entity_pk = r.seed_region_pk"
        "  JOIN kg_entities e ON e.entity_pk = b.entity_pk"
        " WHERE e.entity_id = :s", s=SEED))[0]["n"]
    assert int(total) == 0, "forensic metadata never becomes a candidate"


# ===========================================================================
# storage-level invariants
# ===========================================================================
@case
async def test_the_database_refuses_a_malformed_hash_or_an_oversized_preview(session):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    # A run of our own: this test rolls back like the others, so it cannot
    # borrow one written by a previous test.
    await _run_failing(session, _Response(BARE_REGION))
    rid = (await _latest(session))["run_id"]

    for sql in (
        "UPDATE knowledge_discovery_runs SET response_sha256 = 'not-a-hash' WHERE run_id = :r",
        "UPDATE knowledge_discovery_runs SET raw_response_preview = repeat('x', 2049)"
        " WHERE run_id = :r",
        "UPDATE knowledge_discovery_runs SET prompt_tokens = -1 WHERE run_id = :r",
        "UPDATE knowledge_discovery_runs SET provider_latency_ms = -5 WHERE run_id = :r",
    ):
        with pytest.raises(IntegrityError):
            await session.execute(text(sql), {"r": rid})
            await session.commit()
        await session.rollback()


@case
async def test_a_run_without_forensics_leaves_the_columns_null(session):
    """Historical rows are NOT back-filled. Absence is truthful audit data."""
    rows = await _rows(
        session,
        "SELECT count(*) AS n FROM knowledge_discovery_runs"
        " WHERE run_id::text LIKE '36f057e1%'"
        "   AND (response_sha256 IS NULL AND raw_response_preview IS NULL"
        "        AND finish_reason IS NULL AND prompt_tokens IS NULL"
        "        AND completion_tokens IS NULL AND total_tokens IS NULL"
        "        AND provider_latency_ms IS NULL"
        "        AND fallback_raw_response_used IS NULL)")
    assert int(rows[0]["n"]) == 1, "R21 keeps NULL: the response no longer exists"


# ===========================================================================
# pure helpers — no database
# ===========================================================================
def test_forensics_null_when_there_is_no_content():
    from app.services.llm_discovery_execution_service import forensics_from_response

    for raw in (None, "", "   ", "\n\t "):
        f = forensics_from_response(_Response(raw or ""))
        assert f.response_sha256 is None, raw
        assert f.raw_response_preview is None, raw


def test_forensics_hashes_the_full_text_not_the_preview():
    from app.services.llm_discovery_execution_service import forensics_from_response

    text = "z" * 9000
    f = forensics_from_response(_Response(text))
    assert f.response_sha256 == _sha(text)
    assert len(f.raw_response_preview) <= 2048
    assert f.raw_response_preview.startswith("z" * 100)


def test_forensics_is_unicode_safe_and_never_raises():
    from app.services.llm_discovery_execution_service import forensics_from_response

    text = "齿状回" * 2000
    f = forensics_from_response(_Response(text))
    assert f.response_sha256 == _sha(text)
    assert len(f.raw_response_preview) <= 2048
    assert "齿状回" in f.raw_response_preview


def test_the_lifecycle_forensic_fragment_is_empty_without_a_record():
    """No record -> the terminal SET clause is byte-for-byte what it was."""
    from app.services.knowledge_discovery_run_lifecycle_service import (
        _SET_FAIL,
        _with_forensics,
    )

    sql, params = _with_forensics(_SET_FAIL, None)
    assert sql == _SET_FAIL and params == {}


def test_the_lifecycle_forensic_fragment_names_every_column():
    from app.schemas.discovery_forensics import (
        FORENSIC_COLUMN_NAMES,
        DiscoveryResponseForensics,
    )
    from app.services.knowledge_discovery_run_lifecycle_service import (
        _SET_FAIL,
        _with_forensics,
    )

    sql, params = _with_forensics(_SET_FAIL, DiscoveryResponseForensics())
    for name in FORENSIC_COLUMN_NAMES:
        assert f"{name} = :{name}" in sql, name
        assert name in params, name
    assert sql.startswith(_SET_FAIL), "the terminal transition is not replaced"


def test_the_dto_and_the_column_list_cannot_drift():
    from dataclasses import fields

    from app.schemas.discovery_forensics import (
        FORENSIC_COLUMN_NAMES,
        DiscoveryResponseForensics,
    )

    assert tuple(f.name for f in fields(DiscoveryResponseForensics)) == FORENSIC_COLUMN_NAMES
