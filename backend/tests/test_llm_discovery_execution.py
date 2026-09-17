"""Phase 3B — LLM Discovery execution.

No network and no live database. The provider is a stub, and ``get_db`` is
overridden with an in-memory fake that models ``knowledge_discovery_runs``
closely enough to prove the run really moves QUEUED -> RUNNING -> COMPLETED /
FAILED (the authority table is never touched).

The fake enforces the SAME invariants as the gate7b_012 constraints, so a
failure path that forgot to terminate its run fails here too.
"""
from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.schemas.llm_discovery import SCHEMA_VERSION
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError, OperationalError

from app.database import get_db
from app.llm_discovery_views import (
    InvalidDiscoveryView,
    strategy_identifier,
    view_provenance,
)
from app.llm_model_policy import effective_deepseek_model
from app.main import app
from app.prompts.llm_discovery_prompt import PROMPT_KEY, PROMPT_VERSION
from app.schemas.knowledge_production import (
    ACTIVE_DISCOVERY_RUN_STATUSES,
    TERMINAL_DISCOVERY_RUN_STATUSES,
)
from app.schemas.llm_discovery import LlmDiscoveryInput
from app.services import knowledge_discovery_run_lifecycle_service as lifecycle
from app.services import llm_discovery_execution_service as execution
from app.services import llm_discovery_readiness_service as readiness
from app.services import llm_discovery_seed_service as seed_svc
from app.services.llm_providers.base import (
    LlmProviderResponse,
    LlmProviderUsage,
    ProviderNotConfiguredError,
)

BASE = "/api/knowledge-production"
SEED_ENTITY = "NGIQ-BR-00000247"
UNKNOWN_ENTITY = "NGIQ-BR-99999999"
SEED_PK = 740
EXEC_PATH = Path(execution.__file__)
SEED_PATH = Path(seed_svc.__file__)


# ===========================================================================
# In-memory authority stand-in
# ===========================================================================
def _prov(row: dict[str, Any]) -> dict[str, Any]:
    """A run row's provenance object, however the fake happens to hold it."""
    value = row.get("provenance_json")
    if not value:
        return {}
    return json.loads(value) if isinstance(value, str) else value


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None, scalar: Any = None):
        self._rows = list(rows or [])
        self._scalar = scalar

    def scalar_one(self) -> Any:
        return self._scalar

    def scalar_one_or_none(self) -> Any:
        return self._scalar

    def scalars(self) -> "_FakeResult":
        return self

    def mappings(self) -> "_FakeResult":
        return self

    def one(self) -> dict[str, Any]:
        return self._rows[0]

    def one_or_none(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def all(self) -> list[Any]:
        return self._rows


class _FakeDiscoveryDb:
    """knowledge_discovery_runs + discovery_candidates + brain_regions, with the
    DB invariants.

    ``discovery_candidates`` is modelled too, because the execution path now
    persists the proposals it parsed and the test must be able to see them. It
    models the gate7b_016 UNIQUE (run, type, local_id) key so a replayed
    response is observable as "existing" rather than as a new row.
    """

    def __init__(self, seeds: dict[str, int] | None = None) -> None:
        self.seeds = seeds if seeds is not None else {SEED_ENTITY: SEED_PK}
        self.runs: list[dict[str, Any]] = []
        self.candidates: list[dict[str, Any]] = []
        self.candidate_keys: set[tuple[Any, str, str]] = set()
        self.other_writes: list[str] = []
        # P0-4C.1 — the readiness shape. Defaults are the E2E database: both
        # tables and gate7b_016 applied. A test flips one flag to present an
        # unready database.
        self.has_runs_table = True
        self.has_candidates_table = True
        self.has_migration_ledger = True
        self.migration_applied = True
        self._t = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
        self._run_pk = 0
        #: P0-1: make the run-key read itself fail, to exercise the
        #: persistence-PREPARATION failure path. The run still exists and the
        #: lifecycle transition can still be attempted.
        self.fail_run_keys_read = False
        #: ...and make the session die only AFTER the run has started, so even
        #: the failure transition cannot run. `start_discovery_run` must still
        #: succeed, or the test would never reach the step it is about.
        self.run_lock_fails_after_start = False

    def tick(self) -> datetime:
        self._t = self._t + timedelta(minutes=1)
        return self._t

    def next_run_pk(self) -> int:
        self._run_pk += 1
        return self._run_pk

    def seed_run(self, *, entity_id: str = SEED_ENTITY, status: str = "RUNNING") -> str:
        run_id = str(uuid.uuid4())
        self.runs.append(
            {
                "run_pk": self.next_run_pk(),
                "run_id": run_id,
                "seed_entity_id": entity_id,
                "seed_region_pk": self.seeds[entity_id],
                "discovery_type": "LLM_DISCOVERY",
                "status": status,
                "outcome": None,
                "provider": None,
                "model_name": None,
                "prompt_key": None,
                "prompt_version": None,
                "query_strategy_version": None,
                "created_by": None,
                "created_at": self.tick(),
                "started_at": self.tick() if status != "QUEUED" else None,
                "finished_at": None,
                "error_code": None,
                "error_message": None,
            }
        )
        return run_id

    def _chain(self, p: dict[str, Any]) -> list[dict[str, Any]]:
        """The completed runs of one seed+view — the WHOLE chain, not one run."""
        return [
            r for r in self.runs
            if r["seed_entity_id"] == p["entity_id"]
            and r["discovery_type"] == p["discovery_type"]
            and r["status"] == p["status"]
            and r["query_strategy_version"] == p["strategy"]
        ]

    def active_duplicate(self, seed_region_pk: int, discovery_type: str) -> dict | None:
        for r in self.runs:
            if (
                r["seed_region_pk"] == seed_region_pk
                and r["discovery_type"] == discovery_type
                and r["status"] in ACTIVE_DISCOVERY_RUN_STATUSES
            ):
                return r
        return None


class _FakeSession:
    def __init__(self, db: _FakeDiscoveryDb) -> None:
        self.db = db
        self.commits = 0
        self.rollbacks = 0
        self.statements: list[str] = []

    async def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> _FakeResult:
        sql = " ".join(str(stmt).split())
        p = dict(params or {})
        self.statements.append(sql)

        # P0-4C.1 — the readiness guard runs BEFORE anything else in
        # `execute_llm_discovery`, so the fake must answer its catalogue probes.
        # Defaults describe a READY database (the E2E shape), which is the state
        # every test below assumes; the flags let a test present the unready one.
        if sql.startswith("SELECT to_regclass("):
            return _FakeResult(
                rows=[
                    {
                        # Keyed by the TABLE'S OWN NAME, matching the SQL aliases.
                        "knowledge_discovery_runs": (
                            "knowledge_discovery_runs" if self.db.has_runs_table else None
                        ),
                        "discovery_candidates": (
                            "discovery_candidates" if self.db.has_candidates_table else None
                        ),
                        "schema_migrations": (
                            "schema_migrations" if self.db.has_migration_ledger else None
                        ),
                    }
                ]
            )

        if sql.startswith("SELECT filename FROM infra.schema_migrations"):
            return _FakeResult(
                rows=[{"filename": p.get("filename")}] if self.db.migration_applied else []
            )

        # Discovery View continuation — the scope of the run being continued,
        # the chain of completed runs of this seed+view, and the circuits they
        # produced. Placed BEFORE the generic run lookup: this scope query also
        # matches `r.run_id = :run_id`, and it needs a different row shape.
        if "AS continuation_round" in sql and "r.run_id = :run_id" in sql:
            row = next((r for r in self.db.runs if r["run_id"] == p.get("run_id")), None)
            if row is None:
                return _FakeResult(rows=[])
            return _FakeResult(rows=[{
                "run_id": row["run_id"],
                "status": row["status"],
                "discovery_type": row["discovery_type"],
                "query_strategy_version": row["query_strategy_version"],
                "continuation_round": _prov(row).get("continuation_round"),
                "seed_entity_id": row["seed_entity_id"],
            }])

        if "ORDER BY r.created_at, r.run_id" in sql:
            return _FakeResult(rows=[
                {"run_id": r["run_id"], "continuation_round": _prov(r).get("continuation_round")}
                for r in self.db._chain(p)
            ])

        if "dc.candidate_type = 'circuit'" in sql:
            pks = {r["run_pk"] for r in self.db._chain(p)}
            return _FakeResult(rows=[
                {"name": c["name"], "local_id": c["local_id"]}
                for c in self.db.candidates
                if c["candidate_type"] == "circuit" and c["discovery_run_pk"] in pks
            ])

        if sql.startswith("SELECT b.entity_pk FROM brain_regions"):
            return _FakeResult(scalar=self.db.seeds.get(p.get("entity_id")))

        if sql.startswith("INSERT INTO knowledge_discovery_runs"):
            dup = self.db.active_duplicate(p["seed_region_pk"], p["discovery_type"])
            if dup is not None:
                raise IntegrityError(
                    "INSERT", p, Exception("duplicate key value violates unique constraint")
                )
            row = {
                "run_pk": self.db.next_run_pk(),
                "run_id": str(uuid.uuid4()),
                "seed_entity_id": next(
                    k for k, v in self.db.seeds.items() if v == p["seed_region_pk"]
                ),
                "seed_region_pk": p["seed_region_pk"],
                "discovery_type": p["discovery_type"],
                "status": "QUEUED",
                "outcome": None,
                "provider": p.get("provider"),
                "model_name": p.get("model_name"),
                "prompt_key": p.get("prompt_key"),
                "prompt_version": p.get("prompt_version"),
                # Recorded from the statement's own parameters, not hardcoded:
                # a fake that always answered None could not tell a legacy run
                # from a view run, which is exactly what the view contract adds.
                "query_strategy_version": p.get("query_strategy_version"),
                "provenance_json": p.get("provenance_json"),
                "created_by": None,
                "created_at": self.db.tick(),
                "started_at": None,
                "finished_at": None,
                "error_code": None,
                "error_message": None,
            }
            self.db.runs.append(row)
            return _FakeResult(rows=[row])

        if "knowledge_discovery_runs r" in sql and "r.run_id = :run_id" in sql:
            current = next(
                (r for r in self.db.runs if r["run_id"] == p.get("run_id")), None
            )
            if (
                self.db.run_lock_fails_after_start
                and current is not None
                and current["status"] != "QUEUED"
            ):
                raise OperationalError("SELECT ... FOR UPDATE", p, Exception("no connection"))
            return _FakeResult(rows=[current] if current is not None else [])

        if sql.startswith("SELECT run_pk, seed_region_pk FROM knowledge_discovery_runs"):
            if self.db.fail_run_keys_read:
                raise OperationalError("SELECT run keys", p, Exception("connection reset"))
            return _FakeResult(
                rows=[
                    {"run_pk": r["run_pk"], "seed_region_pk": r["seed_region_pk"]}
                    for r in self.db.runs
                    if r["run_id"] == p.get("run_id")
                ]
            )

        if sql.startswith("INSERT INTO discovery_candidates"):
            indexes = sorted(int(k.split("_", 1)[1]) for k in p if k.startswith("type_"))
            created: list[str] = []
            for i in indexes:
                key = (p["run_pk"], p[f"type_{i}"], p[f"local_id_{i}"])
                if key in self.db.candidate_keys:
                    continue  # ON CONFLICT (...) DO NOTHING
                self.db.candidate_keys.add(key)
                self.db.candidates.append(
                    {
                        "discovery_run_pk": p["run_pk"],
                        "seed_region_pk": p["seed_pk"],
                        "candidate_type": p[f"type_{i}"],
                        "local_id": p[f"local_id_{i}"],
                        "name": p[f"name_{i}"],
                        "payload_json": p[f"payload_{i}"],
                        "confidence": p[f"confidence_{i}"],
                        "status": p["status"],
                    }
                )
                created.append(p[f"type_{i}"])
            return _FakeResult(rows=created)

        if "status = ANY(" in sql:
            dup = self.db.active_duplicate(p["seed_region_pk"], p["discovery_type"])
            return _FakeResult(scalar=dup["run_id"] if dup else None)

        if sql.startswith("UPDATE knowledge_discovery_runs SET"):
            row = next(r for r in self.db.runs if r["run_id"] == p["run_id"])
            if "status = 'RUNNING'" in sql:
                row["status"] = "RUNNING"
                row["started_at"] = self.db.tick()
            elif "status = 'COMPLETED'" in sql:
                row["status"] = "COMPLETED"
                row["outcome"] = p["outcome"]
                row["finished_at"] = self.db.tick()
            elif "status = 'FAILED'" in sql:
                row["status"] = "FAILED"
                row["finished_at"] = self.db.tick()
                row["error_code"] = p["error_code"]
                row["error_message"] = p["error_message"]
            elif "status = 'CANCELLED'" in sql:
                row["status"] = "CANCELLED"
                row["finished_at"] = self.db.tick()
            else:  # pragma: no cover
                raise AssertionError(f"unhandled SET clause: {sql}")
            self._check_invariants(row)
            return _FakeResult(rows=[row])

        # Anything else is a write/read this phase must not perform.
        self.db.other_writes.append(sql)
        raise AssertionError(f"unexpected SQL: {sql}")

    @staticmethod
    def _check_invariants(row: dict[str, Any]) -> None:
        status = row["status"]
        if status == "COMPLETED":
            assert row["outcome"] is not None and row["started_at"] and row["finished_at"]
        else:
            assert row["outcome"] is None, "non-COMPLETED must not carry an outcome"
        if status in ("QUEUED", "RUNNING"):
            assert row["finished_at"] is None
        else:
            assert row["finished_at"] is not None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


# ===========================================================================
# Provider stub
# ===========================================================================
class _StubProvider:
    """Records the call and returns (or raises) whatever the test arranged."""

    def __init__(self, *, response=None, raises: BaseException | None = None) -> None:
        self.response = response
        self.raises = raises
        self.calls: list[dict[str, Any]] = []

    async def complete_json(self, **kwargs: Any) -> LlmProviderResponse:
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        assert self.response is not None, "no response arranged"
        return self.response


def _payload(**overrides: Any) -> dict[str, Any]:
    """A structurally valid Phase 3A discovery response."""
    data: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "seed_entity_id": SEED_ENTITY,
        "summary": "hypothesis sketch",
        "regions": [
            {
                "local_id": "region_1",
                "name": "Medial dorsal nucleus",
                "relation_to_seed": "RECIPROCAL",
                "confidence": 0.6,
            }
        ],
        "connections": [
            {
                "local_id": "connection_1",
                "source_ref": "SEED",
                "target_ref": "region_1",
                "connection_type": "PROJECTION",
                "directionality": "DIRECTED",
                "confidence": 0.5,
                "species_context": {"scope": "NON_HUMAN", "taxon_ids": [10090]},
            }
        ],
        "functions": [],
        "circuits": [],
        "source_hints": [],
        "warnings": [],
    }
    data.update(overrides)
    return data


def _response(**overrides: Any) -> LlmProviderResponse:
    base: dict[str, Any] = {
        "provider": "deepseek",
        "model": "deepseek-flash",
        "raw_text": json.dumps(_payload()),
        "parsed_json": None,
        "usage": LlmProviderUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        "finish_reason": "stop",
        "request_payload_redacted": {"model": "deepseek-flash"},
        "response_payload": {"model": "deepseek-flash"},
        "latency_ms": 1234,
        "error_message": None,
        "transport_ok": True,
        "response_format": "json_object",
    }
    base.update(overrides)
    return LlmProviderResponse(**base)


def _seed_input(**overrides: Any) -> LlmDiscoveryInput:
    base = dict(
        seed_entity_id=SEED_ENTITY,
        seed_name_en="Left Thalamus",
        seed_name_zh="左侧丘脑",
        seed_granularity_level="G1_MACRO",
        seed_hemisphere="left",
        species_taxon_id="9606",
        source_atlas_names=["AAL3"],
    )
    base.update(overrides)
    return LlmDiscoveryInput(**base)


@pytest.fixture()
def env(monkeypatch):
    """A wired execution environment: fake DB + stub provider + fixed settings."""
    db = _FakeDiscoveryDb()
    session = _FakeSession(db)
    provider = _StubProvider(response=_response())
    config = type(
        "Cfg",
        (),
        {
            "temperature": 0.2,
            "max_tokens": 65536,
            "timeout_seconds": 300,
            "default_model": "x",
            "thinking_enabled": True,
            "reasoning_effort": "high",
        },
    )()

    async def fake_seed_input(_session, _entity_id):
        return _seed_input()

    monkeypatch.setattr(execution, "build_discovery_input", fake_seed_input)
    monkeypatch.setattr(execution, "get_llm_provider", lambda name: provider)
    monkeypatch.setattr(execution, "get_deepseek_runtime_config", lambda: config)

    def run(coro):
        return asyncio.run(coro)

    return type(
        "Env",
        (),
        {
            "db": db,
            "session": session,
            "provider": provider,
            "config": config,
            "execute": lambda self=None: run(execution.execute_llm_discovery(session, entity_id=SEED_ENTITY)),
        },
    )()


def _execute(env, entity_id: str = SEED_ENTITY):
    return asyncio.run(execution.execute_llm_discovery(env.session, entity_id=entity_id))


def _terminal(env) -> None:
    """Every run this phase touched must be TERMINAL — never stuck RUNNING."""
    for row in env.db.runs:
        assert row["status"] in TERMINAL_DISCOVERY_RUN_STATUSES, row["status"]


# ===========================================================================
# §26 — success path
# ===========================================================================
def test_26_1_a_valid_response_completes_the_run_with_typed_candidates(env):
    result = _execute(env)
    assert result.run.status == "COMPLETED"
    assert result.run.outcome == "CANDIDATES_FOUND"
    assert result.run.discovery_type == "LLM_DISCOVERY"
    assert [r.local_id for r in result.result.regions] == ["region_1"]


def test_26_2_the_run_is_queued_then_running_before_the_provider_is_called(env):
    calls: list[str] = []
    original_create = lifecycle.create_discovery_run
    original_start = lifecycle.start_discovery_run

    async def spy_create(session, **kwargs):
        item = await original_create(session, **kwargs)
        calls.append(f"create:{item.status}")
        return item

    async def spy_start(session, run_id):
        item = await original_start(session, run_id)
        calls.append(f"start:{item.status}")
        return item

    execution.lifecycle.create_discovery_run = spy_create
    execution.lifecycle.start_discovery_run = spy_start
    try:
        _execute(env)
    finally:
        execution.lifecycle.create_discovery_run = original_create
        execution.lifecycle.start_discovery_run = original_start

    assert calls == ["create:QUEUED", "start:RUNNING"]
    assert len(env.provider.calls) == 1, "the provider is called exactly once"


def test_26_3_the_provider_receives_the_frozen_phase_3a_prompt(env):
    from app.prompts.llm_discovery_prompt import build_llm_discovery_prompt

    _execute(env)
    call = env.provider.calls[0]
    expected = build_llm_discovery_prompt(_seed_input())
    assert call["system_prompt"] == expected["system_prompt"]
    assert call["user_prompt"] == expected["user_prompt"]


def test_26_4_the_prompt_carries_the_seed_facts(env):
    _execute(env)
    user_prompt = " ".join(env.provider.calls[0]["user_prompt"].split())
    assert SEED_ENTITY in user_prompt
    assert "Left Thalamus" in user_prompt
    assert "G1_MACRO" in user_prompt


def test_26_5_no_response_schema_is_passed_to_the_provider(env):
    """No provider-side enforcement is claimed (§20): the parser is the authority."""
    _execute(env)
    assert "response_schema" not in env.provider.calls[0]


def test_26_6_the_provider_is_asked_for_the_policy_model(env):
    _execute(env)
    assert env.provider.calls[0]["model"] == effective_deepseek_model(None)


def test_26_7_generation_settings_come_from_the_runtime_config(env):
    _execute(env)
    call = env.provider.calls[0]
    assert call["temperature"] == env.config.temperature
    assert call["max_tokens"] == env.config.max_tokens
    assert call["timeout_seconds"] == env.config.timeout_seconds


def test_26_8_validation_warnings_are_returned_not_swallowed(env):
    """The stub declares NON_HUMAN scope, which the parser flags."""
    result = _execute(env)
    codes = {w.code for w in result.validation_warnings}
    assert "CROSS_SPECIES_UNCERTAINTY" in codes
    assert result.metrics.warning_count == len(result.validation_warnings)


def test_26_9_only_the_four_candidate_arrays_decide_the_outcome(env):
    """source_hints alone are NOT candidates (§12)."""
    env.provider.response = _response(
        raw_text=json.dumps(
            _payload(
                regions=[],
                connections=[],
                functions=[],
                circuits=[],
                source_hints=[{"title": "a remembered paper", "year": 1999}],
            )
        )
    )
    result = _execute(env)
    assert result.run.outcome == "NO_CANDIDATES_FOUND"
    assert result.result.source_hints, "the hint is still returned to the caller"


def test_26_10_llm_discovery_never_reports_no_evidence_found(env):
    env.provider.response = _response(
        raw_text=json.dumps(
            _payload(regions=[], connections=[], functions=[], circuits=[])
        )
    )
    result = _execute(env)
    assert result.run.outcome == "NO_CANDIDATES_FOUND"
    assert result.run.outcome != "NO_EVIDENCE_FOUND"


def test_26_11_metrics_report_provenance_without_content(env):
    result = _execute(env)
    metrics = result.metrics
    assert metrics.provider == "deepseek"
    assert metrics.effective_model == "deepseek-flash"
    assert metrics.prompt_key == PROMPT_KEY
    assert metrics.prompt_version == PROMPT_VERSION
    assert metrics.max_tokens == env.config.max_tokens
    assert metrics.finish_reason == "stop"
    assert metrics.latency_ms == 1234
    assert metrics.total_tokens == 30
    assert metrics.candidate_counts == {
        "regions": 1,
        "connections": 1,
        "functions": 0,
        "circuits": 0,
        "source_hints": 0,
    }
    assert len(metrics.response_sha256) == 64
    assert len(metrics.prompt_sha256) == 64


def test_26_12_the_hashes_digest_what_was_actually_sent_and_received(env):
    from app.prompts.llm_discovery_prompt import build_llm_discovery_prompt

    result = _execute(env)
    prompt = build_llm_discovery_prompt(_seed_input())
    expected_prompt = hashlib.sha256(
        (prompt["system_prompt"] + "\n" + prompt["user_prompt"]).encode("utf-8")
    ).hexdigest()
    expected_response = hashlib.sha256(env.provider.response.raw_text.encode("utf-8")).hexdigest()
    assert result.metrics.prompt_sha256 == expected_prompt
    assert result.metrics.response_sha256 == expected_response


# ===========================================================================
# §3 / §4 / §5 — the QUALITY-FIRST output budget (Phase 3B.1)
# ===========================================================================
def test_qf_1_the_deepseek_default_budget_is_the_thinking_mode_default():
    """§4: 64K is the thinking-mode default; the old 8K cap was ours, not the model's."""
    from app.schemas.settings import DeepSeekRuntimeSettings

    assert DeepSeekRuntimeSettings().max_tokens == 65536
    assert DeepSeekRuntimeSettings().timeout_seconds == 300


def test_qf_1b_the_schema_accepts_far_more_than_the_old_8k_cap():
    """§7: 8192 was a project-imposed limit that no longer matches the API."""
    from pydantic import ValidationError

    from app.schemas.settings import DeepSeekRuntimeSettings

    assert DeepSeekRuntimeSettings(max_tokens=131072).max_tokens == 131072
    # the diagnostic headroom is bounded on purpose: 384K is NOT opened here
    with pytest.raises(ValidationError):
        DeepSeekRuntimeSettings(max_tokens=131073)
    with pytest.raises(ValidationError):
        DeepSeekRuntimeSettings(max_tokens=393216)


def test_qf_1c_timeout_can_be_raised_but_stays_bounded():
    from pydantic import ValidationError

    from app.schemas.settings import DeepSeekRuntimeSettings, DeepSeekRuntimeSettingsPatch

    assert DeepSeekRuntimeSettings(timeout_seconds=600).timeout_seconds == 600
    with pytest.raises(ValidationError):
        DeepSeekRuntimeSettings(timeout_seconds=601)
    # the PATCH schema must be able to express the same value, or Settings
    # could not persist what the runtime is allowed to hold
    assert DeepSeekRuntimeSettingsPatch(timeout_seconds=300).timeout_seconds == 300
    assert DeepSeekRuntimeSettingsPatch(max_tokens=131072).max_tokens == 131072


def test_qf_1d_the_default_reasoning_profile_is_explicit_and_quality_first():
    """§4 / §5: thinking ON at high effort — stated, not inherited."""
    from app.schemas.settings import DeepSeekRuntimeSettings

    settings = DeepSeekRuntimeSettings()
    assert settings.thinking_enabled is True
    assert settings.reasoning_effort == "high"


def test_qf_2_kimi_keeps_its_own_budget():
    """§6: the DeepSeek policy change must not leak into another provider."""
    from app.schemas.settings import KimiRuntimeSettings

    assert KimiRuntimeSettings().max_tokens == 2000


def test_qf_3_a_clean_install_resolves_to_the_full_budget(tmp_path, monkeypatch):
    """No runtime file exists -> the request carries the quality-first default."""
    from app.services import settings_service

    monkeypatch.setattr(
        settings_service, "RUNTIME_SETTINGS_PATH", tmp_path / "absent.json"
    )
    assert settings_service.get_deepseek_runtime_config().max_tokens == 65536


def test_qf_3b_a_clean_install_resolves_to_the_discovery_temperature(tmp_path, monkeypatch):
    """§6: Discovery generates at a LOW temperature, and that is a decision.

    Same shape as the budget pin above, for the same reason — temperature is a
    SHARED runtime setting (every DeepSeek flow reads it), so its value is a
    choice that must not drift silently. Precision and stability are what this
    path wants: a continuation round that merely re-words a circuit the View
    already found is not a discovery, it is noise the assessor then has to
    re-classify.
    """
    from app.services import settings_service

    monkeypatch.setattr(
        settings_service, "RUNTIME_SETTINGS_PATH", tmp_path / "absent.json"
    )
    config = settings_service.get_deepseek_runtime_config()
    assert config.temperature == 0.2
    # ...and the rest of the frozen Discovery target is unchanged by this pin.
    assert config.max_tokens == 65536
    assert config.reasoning_effort == "high"
    assert config.thinking_enabled is True


def test_qf_4_the_execution_path_forwards_the_budget_unclamped(env):
    """The value that reaches the provider is the configured one, untouched."""
    _execute(env)
    assert env.provider.calls[0]["max_tokens"] == 65536


def test_qf_4b_the_execution_path_states_the_reasoning_profile(env):
    """§5: the profile is sent, not left to the server's default."""
    _execute(env)
    call = env.provider.calls[0]
    assert call["thinking_enabled"] is True
    assert call["reasoning_effort"] == "high"
    assert call["timeout_seconds"] == 300


def test_qf_5_no_business_layer_hardcodes_a_deepseek_token_budget():
    """§5: the budget is a runtime setting, never a literal at a call site.

    Scans the CODE, not the prose: the log format legitimately names the field,
    but no numeric budget may appear anywhere in this module.
    """
    tree = ast.parse(_exec_source())

    # No numeric literal may be passed as max_tokens ...
    literals = [
        kw.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for kw in node.keywords
        if kw.arg == "max_tokens" and isinstance(kw.value, ast.Constant)
    ]
    assert literals == [], literals

    # ... and none of the old downgrade values may exist at all.
    numbers = {
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, int)
    }
    assert not (numbers & {2000, 2048, 4096, 8192}), numbers

    # The single authority is consulted, not bypassed.
    source = _exec_source()
    assert "config.max_tokens" in source
    assert "get_deepseek_runtime_config()" in source


def test_qf_6_the_budget_is_reported_so_truncation_is_diagnosable(env):
    """§12: without max_tokens + finish_reason, 'length' is invisible."""
    env.provider.response = _response(raw_text=json.dumps(_payload()), finish_reason="length")
    result = _execute(env)
    assert result.metrics.max_tokens == 65536
    assert result.metrics.finish_reason == "length"


def test_qf_7_a_provider_failure_is_never_retried_with_a_smaller_budget(env):
    """§1: quality-first means no automatic downgrade on failure either."""
    env.provider.raises = ProviderNotConfiguredError("no key")
    with pytest.raises(execution.LlmDiscoveryExecutionError) as exc:
        _execute(env)
    assert exc.value.code == execution.ERR_PROVIDER_AUTH
    assert len(env.provider.calls) == 1, "one attempt, no retry loop"
    assert env.provider.calls[0]["max_tokens"] == 65536, "the budget is not renegotiated"


def test_qf_8_the_real_http_payload_carries_the_quality_first_budget(monkeypatch):
    """§3: prove the REQUEST that would leave the process — not a settings view.

    The provider is stubbed only at the HTTP boundary, so the payload asserted
    here is produced by the real DeepSeekProvider from the real schema defaults.
    """
    from app.schemas.settings import DeepSeekRuntimeSettings
    from app.services.llm_providers import deepseek as deepseek_mod
    from app.services.llm_providers.factory import get_llm_provider

    sent: dict[str, Any] = {}

    class _Response:
        status_code = 200
        text = json.dumps({"choices": [{"message": {"content": "{}"}}], "usage": {}})

        def json(self) -> dict[str, Any]:
            return json.loads(self.text)

    class _Client:
        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *exc: object) -> bool:
            return False

        async def post(self, url: str, *, json: dict[str, Any], headers: dict) -> Any:
            sent["url"] = url
            sent["body"] = json
            sent["headers"] = sorted(headers)  # names only, never values
            return _Response()

    monkeypatch.setattr(deepseek_mod.httpx, "AsyncClient", lambda **kw: _Client())
    defaults = DeepSeekRuntimeSettings()
    cfg = type(
        "Cfg",
        (),
        {
            "enabled": defaults.enabled,
            "api_key": "test-key-not-a-secret",
            "base_url": defaults.base_url,
            "default_model": defaults.default_model,
            "timeout_seconds": defaults.timeout_seconds,
            "max_tokens": defaults.max_tokens,
        },
    )()
    monkeypatch.setattr(deepseek_mod, "get_deepseek_runtime_config", lambda: cfg)

    asyncio.run(
        get_llm_provider("deepseek").complete_json(
            model=execution.effective_deepseek_model(None),
            system_prompt="s",
            user_prompt="u",
            temperature=defaults.temperature,
            max_tokens=cfg.max_tokens,
        )
    )

    assert sent["body"]["model"] == "deepseek-flash"
    assert sent["body"]["max_tokens"] == 65536
    assert sent["body"]["response_format"] == {"type": "json_object"}
    assert sent["url"].endswith("/chat/completions")
    # headers are asserted by NAME only — a value would be a secret
    assert sent["headers"] == ["Authorization", "Content-Type"]


# ===========================================================================
# §5 / §6 / §14 — the knowledge-production REASONING profile, at the wire
# ===========================================================================
def _capture_payload(monkeypatch, *, thinking, effort, max_tokens=65536, timeout=300,
                     temperature=0.2):
    """Run the REAL provider against a stubbed HTTP boundary; return the body."""
    from app.services.llm_providers import deepseek as deepseek_mod
    from app.services.llm_providers.factory import get_llm_provider

    sent: dict[str, Any] = {}

    class _Response:
        status_code = 200
        text = json.dumps(
            {
                "choices": [{"message": {"content": "{}"}}],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "total_tokens": 30,
                    "completion_tokens_details": {"reasoning_tokens": 7},
                },
            }
        )

        def json(self) -> dict[str, Any]:
            return json.loads(self.text)

    class _Client:
        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *exc: object) -> bool:
            return False

        async def post(self, url: str, *, json: dict[str, Any], headers: dict) -> Any:
            sent["body"] = json
            return _Response()

    monkeypatch.setattr(deepseek_mod.httpx, "AsyncClient", lambda **kw: _Client())
    cfg = type(
        "Cfg",
        (),
        {
            "enabled": True,
            "api_key": "test-key-not-a-secret",
            "base_url": "https://api.deepseek.com/v1",
            "default_model": "deepseek-flash",
            "timeout_seconds": timeout,
            "max_tokens": max_tokens,
            "thinking_enabled": thinking,
            "reasoning_effort": effort,
        },
    )()
    monkeypatch.setattr(deepseek_mod, "get_deepseek_runtime_config", lambda: cfg)

    response = asyncio.run(
        get_llm_provider("deepseek").complete_json(
            model=effective_deepseek_model(None),
            system_prompt="s",
            user_prompt="u",
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_seconds=timeout,
            thinking_enabled=thinking,
            reasoning_effort=effort,
        )
    )
    return sent["body"], response


def test_rp_1_the_wire_payload_enables_thinking(monkeypatch):
    body, _ = _capture_payload(monkeypatch, thinking=True, effort="high")
    assert body["thinking"] == {"type": "enabled"}


def test_rp_2_the_wire_payload_states_high_reasoning_effort(monkeypatch):
    body, _ = _capture_payload(monkeypatch, thinking=True, effort="high")
    assert body["reasoning_effort"] == "high"


def test_rp_3_the_wire_payload_carries_the_64k_budget(monkeypatch):
    body, _ = _capture_payload(monkeypatch, thinking=True, effort="high")
    assert body["max_tokens"] == 65536
    assert body["model"] == "deepseek-flash"
    assert body["response_format"] == {"type": "json_object"}


def test_rp_3b_the_wire_payload_carries_the_generation_temperature(monkeypatch):
    """The frozen Discovery target, at the wire: 0.2 — not the server default."""
    body, _ = _capture_payload(monkeypatch, thinking=True, effort="high",
                               temperature=0.2)
    assert body["temperature"] == 0.2
    # stated together, because they are one decision about how this path runs
    assert body["reasoning_effort"] == "high"
    assert body["thinking"] == {"type": "enabled"}
    assert body["max_tokens"] == 65536
    assert body["model"] == "deepseek-flash"


def test_rp_4_no_retired_model_name_reaches_the_wire(monkeypatch):
    from app.llm_model_policy import LEGACY_DEEPSEEK_MODELS

    body, _ = _capture_payload(monkeypatch, thinking=True, effort="high")
    for legacy in LEGACY_DEEPSEEK_MODELS:
        assert legacy not in json.dumps(body)


def test_rp_5_low_effort_is_expressible_for_the_diagnostic(monkeypatch):
    """§19/§20: the control exists without becoming the production default."""
    body, _ = _capture_payload(monkeypatch, thinking=True, effort="low")
    assert body["reasoning_effort"] == "low"
    assert body["thinking"] == {"type": "enabled"}
    assert body["max_tokens"] == 65536


def test_rp_6_a_caller_that_states_no_profile_sends_none(monkeypatch):
    """§6: legacy DeepSeek workloads must be untouched by this profile."""
    body, _ = _capture_payload(monkeypatch, thinking=None, effort=None, max_tokens=2000, timeout=120)
    assert "thinking" not in body
    assert "reasoning_effort" not in body


def test_rp_7_reasoning_tokens_are_recorded_as_a_count_only(monkeypatch):
    """§11: a number if the provider reports one; never the reasoning text."""
    _, response = _capture_payload(monkeypatch, thinking=True, effort="high")
    assert response.usage.reasoning_tokens == 7
    assert response.raw_text == "{}", "content is still the only answer"


def test_rp_8_metrics_report_the_profile_so_truncation_can_be_read(env):
    """§12: `length` is only interpretable WITH the effort that consumed it."""
    env.provider.response = _response(
        raw_text=json.dumps(_payload()), finish_reason="length"
    )
    result = _execute(env)
    assert result.metrics.thinking_enabled is True
    assert result.metrics.reasoning_effort == "high"
    assert result.metrics.max_tokens == 65536
    assert result.metrics.finish_reason == "length"


def test_rp_9_run_provenance_names_the_hardened_prompt_version(env):
    """§25.9: the persisted run must identify the prompt text that produced it.

    The assertion is against the module's own constant, because what this test
    proves is the PLUMBING — that the version reaches the persisted run. WHICH
    version is current is pinned once, in test_llm_discovery_contract; a literal
    here would go stale at every prompt revision and prove nothing extra.
    """
    _execute(env)
    assert env.db.runs[0]["prompt_version"] == PROMPT_VERSION
    assert env.db.runs[0]["prompt_key"] == "knowledge_production.llm_discovery"


# ===========================================================================
# §27 — failure paths (each one must also terminate the run)
# ===========================================================================
def test_27_1_a_provider_timeout_fails_the_run_with_the_timeout_code(env):
    env.provider.raises = httpx.ReadTimeout("slow")
    with pytest.raises(execution.LlmDiscoveryExecutionError) as exc:
        _execute(env)
    assert exc.value.code == execution.ERR_PROVIDER_TIMEOUT
    assert env.db.runs[0]["error_code"] == execution.ERR_PROVIDER_TIMEOUT
    _terminal(env)


def test_27_2_a_generic_provider_exception_fails_the_run_as_a_provider_error(env):
    env.provider.raises = RuntimeError("connection reset at https://api.deepseek.com/v1")
    with pytest.raises(execution.LlmDiscoveryExecutionError) as exc:
        _execute(env)
    assert exc.value.code == execution.ERR_PROVIDER_ERROR
    # the exception text never reaches the run: it can carry a URL or worse
    assert "api.deepseek.com" not in env.db.runs[0]["error_message"]
    _terminal(env)


def test_27_3_an_unconfigured_provider_is_an_auth_error(env):
    env.provider.raises = ProviderNotConfiguredError("DeepSeek API key is not configured")
    with pytest.raises(execution.LlmDiscoveryExecutionError) as exc:
        _execute(env)
    assert exc.value.code == execution.ERR_PROVIDER_AUTH
    _terminal(env)


@pytest.mark.parametrize(
    "status,expected",
    [
        (401, execution.ERR_PROVIDER_AUTH),
        (403, execution.ERR_PROVIDER_AUTH),
        (408, execution.ERR_PROVIDER_TIMEOUT),
        (504, execution.ERR_PROVIDER_TIMEOUT),
        (400, execution.ERR_PROVIDER_ERROR),
        (500, execution.ERR_PROVIDER_ERROR),
        (503, execution.ERR_PROVIDER_ERROR),
    ],
)
def test_27_4_a_transport_failure_maps_by_structured_status_code(env, status, expected):
    env.provider.response = _response(
        raw_text="",
        transport_ok=False,
        error_message=f"DeepSeek returned HTTP {status}",
        response_payload={"status_code": status},
        usage=LlmProviderUsage(),
    )
    with pytest.raises(execution.LlmDiscoveryExecutionError) as exc:
        _execute(env)
    assert exc.value.code == expected
    _terminal(env)


def test_27_5_a_transport_timeout_without_a_status_code_is_still_a_timeout(env):
    env.provider.response = _response(
        raw_text="",
        transport_ok=False,
        error_message="DeepSeek request failed: timed out",
        response_payload={},
        usage=LlmProviderUsage(),
    )
    with pytest.raises(execution.LlmDiscoveryExecutionError) as exc:
        _execute(env)
    assert exc.value.code == execution.ERR_PROVIDER_TIMEOUT
    _terminal(env)


def test_27_6_no_content_is_an_empty_response_and_is_never_parsed(env):
    env.provider.response = _response(raw_text="", parsed_json=None)
    with pytest.raises(execution.LlmDiscoveryExecutionError) as exc:
        _execute(env)
    assert exc.value.code == execution.ERR_EMPTY_RESPONSE
    _terminal(env)


def test_27_7_a_salvaged_raw_body_is_treated_as_empty_not_as_an_answer(env):
    """reasoning-only responses come back as a body dump; that is a failure."""
    env.provider.response = _response(
        raw_text='{"choices": [{"message": {"reasoning_content": "let me think..."}}]}',
        response_payload={"model": "deepseek-flash", "fallback_raw_response_used": True},
    )
    with pytest.raises(execution.LlmDiscoveryExecutionError) as exc:
        _execute(env)
    assert exc.value.code == execution.ERR_EMPTY_RESPONSE
    _terminal(env)


def test_27_7c_the_parser_is_not_called_at_all_when_content_is_empty(env, monkeypatch):
    """§11: the raw envelope is transport diagnostics, never parser input."""
    calls: list[object] = []
    original = execution.parse_llm_discovery_response

    def spy(raw, **kwargs):
        calls.append(raw)
        return original(raw, **kwargs)

    monkeypatch.setattr(execution, "parse_llm_discovery_response", spy)
    env.provider.response = _response(
        # The envelope is non-empty JSON that LOOKS parseable; it must still
        # never reach the parser, because it is not the model's answer.
        raw_text=json.dumps({"choices": [{"message": {"content": ""}}]}),
        response_payload={"model": "deepseek-flash", "fallback_raw_response_used": True},
    )
    with pytest.raises(execution.LlmDiscoveryExecutionError) as exc:
        _execute(env)
    assert exc.value.code == execution.ERR_EMPTY_RESPONSE
    assert calls == [], "the raw response envelope must never be parsed"


def test_27_7b_a_truncated_answer_says_so_without_leaving_the_vocabulary(env):
    env.provider.response = _response(
        raw_text="",
        finish_reason="length",
        response_payload={"model": "deepseek-flash", "fallback_raw_response_used": True},
    )
    with pytest.raises(execution.LlmDiscoveryExecutionError) as exc:
        _execute(env)
    assert exc.value.code == execution.ERR_EMPTY_RESPONSE
    assert "token budget" in exc.value.message
    assert env.db.runs[0]["error_code"] == execution.ERR_EMPTY_RESPONSE
    _terminal(env)


@pytest.mark.parametrize(
    "raw,label",
    [
        ("not json at all", "invalid json"),
        (json.dumps(_payload(schema_version="2.0")), "wrong schema version"),
        (json.dumps(_payload(seed_entity_id="NGIQ-BR-00000001")), "seed mismatch"),
        (json.dumps(_payload(unexpected_field=True)), "undefined field"),
        (
            json.dumps(_payload(connections=[{"local_id": "c1", "source_ref": "SEED", "target_ref": "SEED", "confidence": 0.1, "species_context": {"scope": "UNKNOWN", "taxon_ids": []}}])),
            "canonical-looking local id",
        ),
        (
            json.dumps(_payload(connections=[{"local_id": "connection_1", "source_ref": "SEED", "target_ref": "region_404", "confidence": 0.1, "species_context": {"scope": "UNKNOWN", "taxon_ids": []}}])),
            "dangling region reference",
        ),
        (
            json.dumps(
                _payload(
                    connections=[
                        {
                            "local_id": "connection_1",
                            "source_ref": "SEED",
                            "target_ref": "SEED",
                            "confidence": 0.1,
                        }
                    ]
                )
            ),
            "missing species_context",
        ),
    ],
)
def test_27_8_an_unusable_response_fails_the_run_as_a_parse_failure(env, raw, label):
    env.provider.response = _response(raw_text=raw)
    with pytest.raises(execution.LlmDiscoveryExecutionError) as exc:
        _execute(env)
    assert exc.value.code == execution.ERR_PARSE_FAILED, label
    assert env.db.runs[0]["error_code"] == execution.ERR_PARSE_FAILED
    _terminal(env)


def test_27_9_a_parse_failure_records_a_summary_not_the_response(env):
    raw = json.dumps(_payload(summary="x" * 4000, unexpected_field="y" * 4000))
    env.provider.response = _response(raw_text=raw)
    with pytest.raises(execution.LlmDiscoveryExecutionError):
        _execute(env)
    message = env.db.runs[0]["error_message"]
    assert len(message) <= execution._ERROR_MESSAGE_MAX
    assert "x" * 100 not in message, "the response body must not be copied in"


def test_27_10_a_model_that_ignores_the_policy_fails_the_run(env):
    env.provider.response = _response(model="deepseek-v4-pro")
    with pytest.raises(execution.LlmDiscoveryExecutionError) as exc:
        _execute(env)
    assert exc.value.code == execution.ERR_PROVIDER_ERROR
    assert "deepseek-flash" in exc.value.message
    _terminal(env)


def test_27_11_no_failure_path_leaves_a_run_running(env):
    """The whole §27 matrix, re-run as a single 'never stuck' sweep."""
    scenarios = [
        _response(raw_text="", transport_ok=False, response_payload={"status_code": 500}),
        _response(raw_text=""),
        _response(raw_text="{}"),
        _response(model="deepseek-reasoner"),
    ]
    for scenario in scenarios:
        db = _FakeDiscoveryDb()
        session = _FakeSession(db)
        env.db.runs = db.runs
        env.session.db = db
        env.session.statements = []
        env.provider.response = scenario
        env.provider.raises = None
        try:
            asyncio.run(execution.execute_llm_discovery(session, entity_id=SEED_ENTITY))
            raise AssertionError("expected a failure")
        except execution.LlmDiscoveryExecutionError:
            pass
        assert [r["status"] for r in db.runs] == ["FAILED"]


def test_27_12_every_failed_run_records_both_an_error_code_and_a_message(env):
    env.provider.raises = httpx.ConnectError("refused")
    with pytest.raises(execution.LlmDiscoveryExecutionError):
        _execute(env)
    row = env.db.runs[0]
    assert row["error_code"] and row["error_message"]
    assert row["outcome"] is None, "a failure is not a scientific result"


# ===========================================================================
# §28 — provenance
# ===========================================================================
def test_28_1_the_execution_service_writes_the_provenance(env):
    _execute(env)
    row = env.db.runs[0]
    assert row["provider"] == "deepseek"
    assert row["model_name"] == effective_deepseek_model(None)
    assert row["prompt_key"] == PROMPT_KEY
    assert row["prompt_version"] == PROMPT_VERSION


def test_28_2_the_model_name_is_not_a_literal_in_this_phase(env):
    """§7: the value must come from the policy, never be re-typed here."""
    strings = {
        n.value
        for n in ast.walk(ast.parse(EXEC_PATH.read_text(encoding="utf-8-sig")))
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }
    assert "deepseek-flash" not in strings
    assert "effective_deepseek_model(" in EXEC_PATH.read_text(encoding="utf-8")


def test_28_3_the_run_records_the_model_the_provider_reported(env):
    _execute(env)
    assert env.provider.response.model == env.db.runs[0]["model_name"]


def test_28_4_no_raw_response_reaches_a_run_column(env):
    _execute(env)
    row = env.db.runs[0]
    blob = json.dumps(row, default=str)
    assert "Medial dorsal nucleus" not in blob, "candidate content leaked into the run"
    assert "hypothesis sketch" not in blob, "the summary leaked into the run"
    assert "reasoning" not in blob.lower()


def test_28_5_the_client_cannot_supply_provenance_through_the_generic_api():
    """§8: the public create endpoint still takes the route and nothing else."""
    payload = {
        "discovery_type": "LLM_DISCOVERY",
        "provider": "kimi",
        "model_name": "moonshot-v1-auto",
        "prompt_key": "evil",
        "prompt_version": "9.9.9",
    }
    client = TestClient(app)
    response = client.post(f"{BASE}/brain-regions/{SEED_ENTITY}/discovery-runs", json=payload)
    assert response.status_code == 422, "extra fields must be rejected before any DB work"


# ===========================================================================
# §29 — isolation
# ===========================================================================
def _exec_source() -> str:
    return EXEC_PATH.read_text(encoding="utf-8")


def test_29_1_the_execution_service_never_writes_a_run_with_raw_sql(env):
    """Widened from "issues no SQL at all" when P0-1 made this path persist
    candidates. The property that actually matters is unchanged and is now
    stated precisely: the run row is READ (to learn its own internal keys) and
    is never written except through the lifecycle service."""
    source = _exec_source()
    for forbidden in ("INSERT INTO knowledge_discovery_runs",
                      "UPDATE knowledge_discovery_runs",
                      "DELETE FROM",
                      "FOR UPDATE"):
        assert forbidden not in source, forbidden


def test_29_2_the_execution_path_writes_only_the_run_and_the_candidate_staging_table(env):
    _execute(env)
    writes = [
        s for s in env.session.statements
        if s.split(" ", 1)[0] in ("INSERT", "UPDATE", "DELETE")
    ]
    assert writes, "the lifecycle transitions must actually be executed"
    for sql in writes:
        assert (
            "knowledge_discovery_runs" in sql or "discovery_candidates" in sql
        ), sql
        for other in ("brain_regions", "kg_entities", "entity_aliases"):
            assert other not in sql, sql


def test_29_3_no_canonical_knowledge_table_is_ever_touched(env):
    """A candidate is a PROPOSAL: the only candidate table this path may touch
    is the Knowledge Production staging table, never a legacy `candidate_*` or
    Mirror table, and never a canonical entity table."""
    _execute(env)
    # Never mentioned by ANY statement, read or write: none of these layers is
    # a legitimate participant in an LLM discovery execution.
    never = ("mirror", "final_", "evidence", "knowledge_assertions")
    # Never WRITTEN. Reading them is how the seed is built, and that is the
    # whole point of a BrainRegion-anchored run.
    never_written = (
        "kg_entities",
        "brain_regions",
        "connections",
        "circuits",
        "functions",
    )
    for sql in env.session.statements:
        lowered = sql.lower()
        for name in never:
            assert name not in lowered, f"{name} in {sql}"
        if "candidate" in lowered:
            assert "discovery_candidates" in lowered, sql
        if sql.split(" ", 1)[0] in ("INSERT", "UPDATE", "DELETE"):
            for name in never_written:
                assert name not in lowered, f"{name} in {sql}"
    assert env.db.other_writes == []


def test_29_4_the_execution_layer_does_not_import_a_knowledge_writer():
    tree = ast.parse(_exec_source())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    for module in imported:
        assert "mirror" not in module, module
        assert "candidate" not in module, module
        assert "final" not in module, module
        assert "promotion" not in module, module


def _identifiers(path: Path) -> set[str]:
    """Every NAME and attribute the module actually uses (prose excluded)."""
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    names |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    names |= {
        n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
    }
    return names


def test_29_5_nothing_is_deferred_to_a_background_executor():
    used = _identifiers(EXEC_PATH)
    for forbidden in (
        "BackgroundTasks",
        "celery",
        "Celery",
        "redis",
        "threading",
        "multiprocessing",
        "create_task",
        "APScheduler",
        "Task",
    ):
        assert forbidden not in used, forbidden


def test_29_6_reasoning_content_is_never_fed_to_the_parser(env):
    """A reasoning-only payload cannot become a candidate."""
    env.provider.response = _response(
        raw_text=json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "reasoning_content": json.dumps(_payload()),
                        }
                    }
                ]
            }
        ),
        response_payload={"fallback_raw_response_used": True},
    )
    with pytest.raises(execution.LlmDiscoveryExecutionError) as exc:
        _execute(env)
    assert exc.value.code == execution.ERR_EMPTY_RESPONSE
    assert env.db.runs[0]["status"] == "FAILED"


def test_29_7_no_secret_or_header_can_appear_in_the_result(env):
    result = _execute(env)
    blob = result.model_dump_json()
    for forbidden in ("Authorization", "Bearer", "api_key", "sk-", "reasoning_content"):
        assert forbidden not in blob, forbidden


def test_29_8_the_seed_loader_reads_only_declared_gate7b_values():
    """§5: no alias is invented, no parent guessed, no legacy table consulted."""
    source = SEED_PATH.read_text(encoding="utf-8")
    # The ONLY tables it may name are the Gate7B authority tables.
    for legacy in (
        "canonical_region_aliases",
        "coarse_brain_region_aliases",
        "candidate_",
        "mirror_",
        "final_",
    ):
        assert legacy not in source, legacy
    for authority in ("brain_regions", "kg_entities", "entity_aliases"):
        assert authority in source, authority
    # No inference helper: nothing here resolves a parent or an alias by name.
    used = _identifiers(SEED_PATH)
    for forbidden in ("difflib", "SequenceMatcher", "fuzzy", "guess", "infer"):
        assert forbidden not in used, forbidden


# ===========================================================================
# §5 — the seed loader itself
# ===========================================================================
class _FakeSeedSession:
    """Answers the two deterministic seed queries, and nothing else."""

    def __init__(self, *, parent_name: str | None, depth: int | None, aliases: list[str]):
        self.parent_name = parent_name
        self.depth = depth
        self.aliases = aliases
        self.statements: list[str] = []

    async def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> _FakeResult:
        sql = " ".join(str(stmt).split())
        self.statements.append(sql)
        if sql.startswith("SELECT b.hierarchy_depth"):
            return _FakeResult(
                rows=[{"hierarchy_depth": self.depth, "parent_name_en": self.parent_name}]
            )
        if sql.startswith("SELECT a.alias_text"):
            return _FakeResult(rows=list(self.aliases))
        raise AssertionError(f"unexpected SQL: {sql}")  # pragma: no cover


@pytest.fixture()
def seed_env(monkeypatch):
    from app.schemas.knowledge_production import BrainRegionSeedDetail

    session = _FakeSeedSession(parent_name=None, depth=None, aliases=[])
    detail = BrainRegionSeedDetail(
        entity_pk=SEED_PK,
        entity_id=SEED_ENTITY,
        name_en="Left Thalamus",
        name_zh="左侧丘脑",
        granularity_level="G1_MACRO",
        hemisphere="left",
        species_taxon_id="9606",
        atlas_names=["AAL3", "Brainnetome"],
    )

    async def fake_get_seed_region(_session, identifier):
        return detail if identifier == SEED_ENTITY else None

    monkeypatch.setattr(seed_svc, "get_seed_region", fake_get_seed_region)
    return session


def _load(seed_env, entity_id: str = SEED_ENTITY):
    return asyncio.run(seed_svc.build_discovery_input(seed_env, entity_id))


def test_5_1_a_declared_seed_maps_straight_through(seed_env):
    seed_env.parent_name = "Right Thalamus"
    seed_env.depth = 2
    seed_env.aliases = ["Thalamus (left)", "TH-left"]
    seed = _load(seed_env)
    assert seed.seed_entity_id == SEED_ENTITY
    assert seed.seed_name_en == "Left Thalamus"
    assert seed.seed_name_zh == "左侧丘脑"
    assert seed.seed_granularity_level == "G1_MACRO"
    assert seed.seed_hemisphere == "left"
    assert seed.species_taxon_id == "9606"
    assert seed.source_atlas_names == ["AAL3", "Brainnetome"]
    assert seed.parent_region_name == "Right Thalamus"
    assert seed.known_aliases == ["Thalamus (left)", "TH-left"]


def test_5_2_an_unknown_brain_region_loads_nothing(seed_env):
    assert _load(seed_env, UNKNOWN_ENTITY) is None


def test_5_3_an_absent_parent_stays_absent(seed_env):
    seed = _load(seed_env)
    assert seed.parent_region_name is None, "a missing parent must never be guessed"


def test_5_4_an_absent_depth_is_not_rendered_as_zero(seed_env):
    seed_env.parent_name = "Right Thalamus"
    seed_env.depth = None
    assert _load(seed_env).hierarchy_context == "granularity_level=G1_MACRO; hemisphere=left"


def test_5_5_the_hierarchy_context_restates_only_declared_values(seed_env):
    seed_env.depth = 3
    assert (
        _load(seed_env).hierarchy_context
        == "granularity_level=G1_MACRO; hemisphere=left; hierarchy_depth=3"
    )


def test_5_6_no_aliases_yields_an_empty_list_not_a_substitute(seed_env):
    assert _load(seed_env).known_aliases == []


def test_5_7_alias_rows_are_deduplicated_against_the_declared_names(seed_env):
    """The exclusion lives in SQL, so a name is never repeated as an 'alias'."""
    _load(seed_env)
    alias_sql = next(s for s in seed_env.statements if s.startswith("SELECT a.alias_text"))
    assert "e.name_en" in alias_sql and "e.name_zh" in alias_sql
    assert "ORDER BY a.is_preferred DESC, a.alias_pk" in alias_sql
    assert "LIMIT :limit" in alias_sql


def test_5_8_a_seed_with_no_name_is_rejected_before_anything_runs(monkeypatch):
    from app.schemas.knowledge_production import BrainRegionSeedDetail

    nameless = BrainRegionSeedDetail(entity_pk=1, entity_id="NGIQ-BR-00000009")
    session = _FakeSeedSession(parent_name=None, depth=None, aliases=[])

    async def fake_get_seed_region(_session, identifier):
        return nameless

    monkeypatch.setattr(seed_svc, "get_seed_region", fake_get_seed_region)
    with pytest.raises(Exception) as exc:
        _load(session, "NGIQ-BR-00000009")
    assert "seed_name_en or seed_name_zh is required" in str(exc.value)


# ===========================================================================
# §30 — endpoint
# ===========================================================================
@pytest.fixture()
def client(env, monkeypatch):
    app.dependency_overrides[get_db] = lambda: env.session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_30_1_execution_returns_200_with_run_result_and_warnings(client, env):
    response = client.post(f"{BASE}/brain-regions/{SEED_ENTITY}/llm-discovery/execute")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"run", "result", "validation_warnings", "metrics"}
    assert body["run"]["status"] == "COMPLETED"
    assert body["run"]["outcome"] == "CANDIDATES_FOUND"
    assert body["result"]["regions"][0]["local_id"] == "region_1"
    assert body["metrics"]["effective_model"] == "deepseek-flash"


def test_30_2_an_unknown_brain_region_is_404(client, env, monkeypatch):
    async def missing(_session, _entity_id):
        return None

    monkeypatch.setattr(execution, "build_discovery_input", missing)
    response = client.post(f"{BASE}/brain-regions/{UNKNOWN_ENTITY}/llm-discovery/execute")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "NOT_FOUND"
    assert env.db.runs == [], "no run may be created for a missing seed"


def test_30_3_an_active_run_makes_execution_409(client, env):
    env.db.seed_run(status="QUEUED")
    response = client.post(f"{BASE}/brain-regions/{SEED_ENTITY}/llm-discovery/execute")
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "ACTIVE_RUN_EXISTS"
    assert "active_run_id" in detail
    assert len(env.db.runs) == 1, "the conflicting run is not duplicated"


def test_30_4_a_parse_failure_is_502_and_names_the_failure(client, env):
    env.provider.response = _response(raw_text="definitely not json")
    response = client.post(f"{BASE}/brain-regions/{SEED_ENTITY}/llm-discovery/execute")
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["code"] == execution.ERR_PARSE_FAILED
    assert detail["run_id"] == env.db.runs[0]["run_id"]
    assert "definitely not json" not in json.dumps(detail)


def test_30_5_a_provider_failure_is_502_and_names_the_failure(client, env):
    env.provider.raises = httpx.ReadTimeout("slow")
    response = client.post(f"{BASE}/brain-regions/{SEED_ENTITY}/llm-discovery/execute")
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == execution.ERR_PROVIDER_TIMEOUT


def test_30_6_the_endpoint_takes_no_body(client, env):
    response = client.post(f"{BASE}/brain-regions/{SEED_ENTITY}/llm-discovery/execute")
    assert response.status_code == 200
    assert len(env.provider.calls) == 1


def test_30_7_a_client_supplied_body_cannot_change_the_execution(client, env):
    """The body may name a VIEW and nothing else, and a stray field is REJECTED.

    Before the view contract the body was ignored by the signature. It is now
    refused outright, which is the stronger promise: a silently dropped `model`
    leaves the caller believing it took effect, and the run's provenance would
    then name a model the server never used.
    """
    response = client.post(
        f"{BASE}/brain-regions/{SEED_ENTITY}/llm-discovery/execute",
        json={"provider": "kimi", "model_name": "moonshot-v1-auto"},
    )
    assert response.status_code == 422
    # Rejected before anything ran, so nothing was steered and nothing was spent.
    assert env.db.runs == []
    assert env.provider.calls == []


def test_30_7b_a_view_may_be_named_but_a_model_still_may_not(client, env):
    """The one permitted field steers the QUESTION. The provider stays the server's."""
    response = client.post(
        f"{BASE}/brain-regions/{SEED_ENTITY}/llm-discovery/execute",
        json={"discovery_view": "AFFERENT_CIRCUITS", "model_name": "moonshot-v1-auto"},
    )
    assert response.status_code == 422
    assert env.db.runs == []
    assert env.provider.calls == []


def test_30_8_the_endpoint_is_registered_once_on_its_own_path():
    paths = [r.path for r in app.routes if "llm-discovery" in getattr(r, "path", "")]
    assert paths == [f"{BASE}/brain-regions/{{entity_id}}/llm-discovery/execute"]


# ===========================================================================
# §31 — P0-1: reading the run's own keys is part of candidate persistence
# ===========================================================================
# Persisting candidates needs the run's internal keys, so that read is the FIRST
# step of persistence, not a separate concern. If it fails, the run must end the
# same way any other persistence failure ends it — under the one existing code,
# never a new one.
def test_31_1_a_failed_run_key_read_ends_the_run_as_a_persistence_failure(env):
    env.db.fail_run_keys_read = True

    with pytest.raises(execution.LlmDiscoveryExecutionError) as excinfo:
        _execute(env)

    assert excinfo.value.code == execution.ERR_CANDIDATE_PERSISTENCE_FAILED
    assert excinfo.value.run_id is not None

    run = env.db.runs[0]
    assert run["status"] == "FAILED", "the run must not remain successful or RUNNING"
    assert run["error_code"] == "LLM_CANDIDATE_PERSISTENCE_FAILED"
    assert run["outcome"] is None, "a failure is an execution fact, not a result"

    # The message stays an operational summary: no SQL, no constraint, no stack.
    for forbidden in ("SELECT", "run_pk", "seed_region_pk", "OperationalError",
                      "connection reset", "Traceback"):
        assert forbidden not in run["error_message"], forbidden

    assert env.db.candidates == [], "nothing may be persisted"
    assert env.session.rollbacks >= 1, "the aborted transaction must be rolled back"


def test_31_2_when_the_run_cannot_even_be_failed_the_error_still_surfaces(env):
    """The honest negative: a session too broken to run the failure transition.

    `_abort` cannot repair this, and it must not pretend otherwise. What is
    asserted is exactly what it promises: the error still reaches the caller,
    and the failure is recorded loudly rather than swallowed.
    """
    env.db.fail_run_keys_read = True
    env.db.run_lock_fails_after_start = True

    with pytest.raises(execution.LlmDiscoveryExecutionError) as excinfo:
        _execute(env)

    assert excinfo.value.code == execution.ERR_CANDIDATE_PERSISTENCE_FAILED
    # No invented success: the run could not be transitioned, and that is the
    # truth this test records rather than papering over.
    assert env.db.runs[0]["status"] == "RUNNING"
    assert env.db.candidates == []


# ===========================================================================
# §32 — G4 Discovery View contract: one view is one run, and the run says which
# ===========================================================================
# The four views are named HERE as literals rather than imported, so this file
# fails if the frozen vocabulary changes: a test that imported the tuple would
# agree with any tuple it was given.
VIEW_A = "NAMED_CLASSIC_CIRCUITS"
VIEW_B = "LOCAL_INTRINSIC_CIRCUITS"
VIEW_C = "AFFERENT_CIRCUITS"
VIEW_D = "EFFERENT_CIRCUITS"
ALL_VIEWS = (VIEW_A, VIEW_B, VIEW_C, VIEW_D)


def _execute_view(env, view: str | None):
    return asyncio.run(
        execution.execute_llm_discovery(
            env.session, entity_id=SEED_ENTITY, discovery_view=view
        )
    )


def test_32_1_one_view_is_exactly_one_run(env):
    _execute_view(env, VIEW_C)

    assert len(env.db.runs) == 1, "a view must not fan out into several runs"
    assert len(env.provider.calls) == 1, "and must not spend more than one call"


def test_32_2_four_views_are_four_runs_each_carrying_its_own_view(env):
    for view in ALL_VIEWS:
        _execute_view(env, view)

    assert len(env.db.runs) == 4, "four views, four runs — never one merged run"
    assert [r["query_strategy_version"] for r in env.db.runs] == [
        f"G4HR1/{v}" for v in ALL_VIEWS
    ]
    # Same seed throughout: the views differ in what they ASKED, not in what
    # they were pointed at.
    assert {r["seed_entity_id"] for r in env.db.runs} == {SEED_ENTITY}


def test_32_3_the_view_is_readable_from_the_run_record(env):
    import json

    for view in ALL_VIEWS:
        _execute_view(env, view)

    for view, row in zip(ALL_VIEWS, env.db.runs):
        # The single readable identifier the run DTO already exposes...
        assert row["query_strategy_version"] == f"G4HR1/{view}"
        # ...and the structured fact for readers that want the parts.
        assert json.loads(row["provenance_json"]) == {
            "discovery_view": view,
            "strategy_family": "G4_HIGH_RECALL_V1",
            "strategy_version": "G4HR1",
        }
        # Provenance stays truthful about what actually ran.
        assert row["provider"] == "deepseek"
        assert row["prompt_key"] == "knowledge_production.llm_discovery"


def test_32_4_every_view_is_asked_a_different_question(env, monkeypatch):
    """The prompt actually sent must differ per view — otherwise the record lies."""
    sent: list[str] = []
    real = execution.build_view_prompt

    def _capture(seed, view, already=None):
        prompt = real(seed, view, already)
        sent.append(prompt["system_prompt"])
        return prompt

    monkeypatch.setattr(execution, "build_view_prompt", _capture)
    for view in ALL_VIEWS:
        _execute_view(env, view)

    assert len(set(sent)) == 4, "four views must send four different instructions"
    for view, text in zip(ALL_VIEWS, sent):
        assert view in text


def test_32_5_the_same_candidate_in_two_views_is_two_rows_never_merged(env):
    """RECALL layer: an unresolved duplicate is cheap, a destroyed one is not."""
    _execute_view(env, VIEW_A)
    _execute_view(env, VIEW_B)

    per_run: dict[Any, list[dict[str, Any]]] = {}
    for c in env.db.candidates:
        per_run.setdefault(c["discovery_run_pk"], []).append(c)

    assert len(per_run) == 2, "each view's candidates live under its own run"
    sizes = [len(v) for v in per_run.values()]
    assert sizes[0] == sizes[1] and sizes[0] > 0, sizes

    # Identical stub payloads in both runs: the SAME names must survive twice.
    names_a = sorted(c["name"] for c in per_run[env.db.runs[0]["run_pk"]])
    names_b = sorted(c["name"] for c in per_run[env.db.runs[1]["run_pk"]])
    assert names_a == names_b, "the same concept is returned by both views"
    assert len(env.db.candidates) == sizes[0] + sizes[1], "nothing was deduplicated"


def test_32_6_candidates_stay_scoped_to_the_run_that_produced_them(env):
    _execute_view(env, VIEW_A)
    _execute_view(env, VIEW_D)

    run_pks = {r["run_pk"] for r in env.db.runs}
    assert len(run_pks) == 2
    for c in env.db.candidates:
        assert c["discovery_run_pk"] in run_pks
    # No candidate escaped its run, and no run claimed another's rows.
    assert {c["discovery_run_pk"] for c in env.db.candidates} == run_pks


def test_32_7_an_unready_database_blocks_a_view_run_before_any_side_effect(env):
    env.db.has_candidates_table = False

    with pytest.raises(readiness.LlmDiscoveryDatabaseNotReady):
        _execute_view(env, VIEW_A)

    assert env.db.runs == [], "no run may exist after a readiness refusal"
    assert env.provider.calls == [], "and no provider call may have been made"


def test_32_8_an_invalid_view_is_refused_before_readiness_is_even_asked(env):
    """A request fault costs nothing: it is answered before the database is read."""
    env.db.has_candidates_table = False  # the database is ALSO unready
    asked: list[str] = []
    real_check = readiness.require_llm_discovery_database_readiness

    async def _spy(session):
        asked.append("read")
        return await real_check(session)

    import app.services.llm_discovery_execution_service as _ex

    original = _ex.readiness.require_llm_discovery_database_readiness
    _ex.readiness.require_llm_discovery_database_readiness = _spy
    try:
        with pytest.raises(InvalidDiscoveryView):
            _execute_view(env, "NOT_A_VIEW")
    finally:
        _ex.readiness.require_llm_discovery_database_readiness = original

    assert asked == [], "an invalid view must not reach the readiness check"
    assert env.db.runs == [] and env.provider.calls == []


def test_32_9_the_legacy_run_records_no_view_at_all(env):
    """§8 — the old entry point stays semantically distinguishable.

    The assertion is on the CLAIM, not on the encoding. A legacy run currently
    stores `{}` rather than SQL NULL (the lifecycle writes `_json(provenance or
    {})` on every create), which is an empty object and not a view. What must
    never happen is a view appearing where none was asked for.
    """
    _execute_view(env, None)

    row = env.db.runs[0]
    assert row["query_strategy_version"] is None, "a legacy run names no strategy"
    provenance = json.loads(row["provenance_json"] or "{}")
    assert provenance == {}, "no empty object may carry a view"
    assert "discovery_view" not in provenance
    # ...and it is still a normal, complete run.
    assert row["status"] == "COMPLETED"


def test_32_10_every_view_still_runs_on_the_policy_model(env):
    """§17 — a view selects a question; it never selects a model."""
    for view in ALL_VIEWS:
        _execute_view(env, view)

    for call in env.provider.calls:
        assert call["model"] == effective_deepseek_model(None)
        assert call["model"] == "deepseek-flash"
    for row in env.db.runs:
        assert row["provider"] == "deepseek"
        assert row["model_name"] == "deepseek-flash"


# ===========================================================================
# §33 — Discovery View continuation: a second pass over the SAME question
# ===========================================================================
def _seed_completed_view_run(env, *, view=None, round_no=None, circuits=("Papez circuit",)):
    """A COMPLETED run of a view that a continuation can honestly be built on."""
    view = view or VIEW_A
    db = env.db
    run_id = str(uuid.uuid4())
    db.runs.append({
        "run_pk": db.next_run_pk(),
        "run_id": run_id,
        "seed_entity_id": SEED_ENTITY,
        "seed_region_pk": SEED_PK,
        "discovery_type": "LLM_DISCOVERY",
        "status": "COMPLETED",
        "outcome": "CANDIDATES_FOUND",
        "provider": "deepseek",
        "model_name": "deepseek-flash",
        "prompt_key": PROMPT_KEY,
        "prompt_version": PROMPT_VERSION,
        "query_strategy_version": strategy_identifier(view),
        "created_by": None,
        "created_at": db.tick(),
        "started_at": db.tick(),
        "finished_at": db.tick(),
        "error_code": None,
        "error_message": None,
        "provenance_json": json.dumps(view_provenance(
            view,
            continuation={"continuation_round": round_no} if round_no else None,
        )),
    })
    run_pk = db.runs[-1]["run_pk"]
    for i, name in enumerate(circuits, 1):
        db.candidates.append({
            "discovery_run_pk": run_pk,
            "seed_region_pk": SEED_PK,
            "candidate_type": "circuit",
            "local_id": "circuit_%d" % i,
            "name": name,
        })
    return run_id


def _execute_continuation(env, from_run_id, *, view=None):
    return asyncio.run(execution.execute_llm_discovery(
        env.session,
        entity_id=SEED_ENTITY,
        discovery_view=view or VIEW_A,
        continuation_from_run_id=from_run_id,
    ))


def test_33_1_a_first_pass_with_no_continuation_is_unchanged(env):
    """§16.1 — naming a view but not a continuation is the ordinary run."""
    run = _execute_view(env, VIEW_A)
    provenance = _prov(env.db.runs[0])
    assert provenance["discovery_view"] == VIEW_A
    assert "continuation_round" not in provenance, "a first pass is not round 2"
    assert run.run.query_strategy_version == strategy_identifier(VIEW_A)


def test_33_2_a_continuation_creates_a_NEW_run(env):
    """§16.2 — round 2 is a second, independent run; the parent is not rewritten."""
    parent = _seed_completed_view_run(env)
    before = len(env.db.runs)

    _execute_continuation(env, parent)

    assert len(env.db.runs) == before + 1, "one continuation, one new run"
    kept = next(r for r in env.db.runs if r["run_id"] == parent)
    assert kept["status"] == "COMPLETED", "the parent run still holds its own result"


def test_33_3_33_4_the_continuation_keeps_the_same_seed_and_view(env):
    parent = _seed_completed_view_run(env)
    _execute_continuation(env, parent)

    child = env.db.runs[-1]
    assert child["seed_entity_id"] == SEED_ENTITY
    assert child["seed_region_pk"] == SEED_PK
    # §16.16 — the strategy identifier does NOT fork per round: "which question"
    # and "how many times we asked it" are different dimensions.
    assert child["query_strategy_version"] == "G4HR1/NAMED_CLASSIC_CIRCUITS"


def test_33_5_the_round_is_derived_and_recorded_as_two(env):
    """§16.14 — round 1 exists with no recorded round, so this one is round 2."""
    parent = _seed_completed_view_run(env)
    _execute_continuation(env, parent)

    provenance = _prov(env.db.runs[-1])
    assert provenance["continuation_round"] == 2
    assert provenance["continuation_from_run_id"] == parent
    assert provenance["already_discovered_circuit_count"] == 1
    assert provenance["discovery_view"] == VIEW_A
    assert provenance["strategy_version"] == "G4HR1"


def test_33_15_a_further_continuation_derives_round_three(env):
    """§16.15 — the round comes from the persisted chain, not from the caller."""
    parent = _seed_completed_view_run(env)
    _execute_continuation(env, parent)
    second = env.db.runs[-1]["run_id"]

    _execute_continuation(env, second)

    assert _prov(env.db.runs[-1])["continuation_round"] == 3


def test_33_9_the_exclusion_context_is_derived_server_side(env, monkeypatch):
    """§16.9 — names come from the CANDIDATE ROWS, never from the request."""
    parent = _seed_completed_view_run(
        env, circuits=("Papez circuit", "Entorhinal-hippocampal loop")
    )
    seen = []
    real = execution.build_view_prompt

    def _capture(seed, view, already=None):
        seen.append(already)
        return real(seed, view, already)

    monkeypatch.setattr(execution, "build_view_prompt", _capture)
    _execute_continuation(env, parent)

    assert seen == [("Papez circuit", "Entorhinal-hippocampal loop")]
    # ...and the block really reaches the prompt the model would receive.
    prompt = real(_seed_input(), VIEW_A, seen[0])
    assert "CONTINUATION PASS" in prompt["system_prompt"]
    for name in seen[0]:
        assert name in prompt["system_prompt"]


def test_33_11_every_completed_run_of_the_view_is_included(env, monkeypatch):
    """§16.11 — a round-3 continuation sees rounds 1 AND 2, not only its parent."""
    first = _seed_completed_view_run(env, circuits=("From round 1",))
    second = _seed_completed_view_run(env, round_no=2, circuits=("From round 2",))

    seen = []
    real = execution.build_view_prompt

    def _capture(seed, view, already=None):
        seen.append(already)
        return real(seed, view, already)

    monkeypatch.setattr(execution, "build_view_prompt", _capture)
    _execute_continuation(env, second)

    assert seen and set(seen[0]) == {"From round 1", "From round 2"}
    assert first, "round 1 still contributes after round 2 exists"


def test_33_13_the_continuation_never_merges_or_deletes_candidates(env):
    """§16.13 — the exclusion list is a PROMPT construct; storage is untouched."""
    parent = _seed_completed_view_run(env, circuits=("Papez circuit",))
    before = [dict(c) for c in env.db.candidates]

    _execute_continuation(env, parent)

    for original in before:
        assert original in env.db.candidates, "no parent candidate was removed"
    child_pk = env.db.runs[-1]["run_pk"]
    assert all(c["discovery_run_pk"] != child_pk for c in before)


def test_33_10_a_client_cannot_supply_its_own_exclusion_list(client, env):
    """§16.10 — forbidden by the schema, so it cannot even be silently ignored."""
    parent = _seed_completed_view_run(env)
    response = client.post(
        BASE + "/brain-regions/" + SEED_ENTITY + "/llm-discovery/execute",
        json={
            "discovery_view": VIEW_A,
            "continuation_from_run_id": parent,
            "already_discovered": ["I choose what to exclude"],
        },
    )
    assert response.status_code == 422
    assert len(env.db.runs) == 1, "no run was created"
    assert env.provider.calls == [], "and no model was called"


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        ("cross-seed", lambda r: r.update(seed_entity_id=UNKNOWN_ENTITY)),
        ("cross-view", lambda r: r.update(query_strategy_version=strategy_identifier(VIEW_B))),
        ("not-completed", lambda r: r.update(status="RUNNING")),
        ("not-llm", lambda r: r.update(discovery_type="LITERATURE_DISCOVERY")),
    ],
)
def test_33_rejections_leave_no_trace(env, label, mutate):
    """§16.6/7/8 — a refused continuation creates no run and calls no model."""
    parent = _seed_completed_view_run(env)
    mutate(next(r for r in env.db.runs if r["run_id"] == parent))
    before = len(env.db.runs)

    with pytest.raises(execution.continuation.ContinuationError):
        _execute_continuation(env, parent)

    assert len(env.db.runs) == before, label + ": no run may be created"
    assert env.provider.calls == [], label + ": no model may be called"


def test_33_a_missing_parent_run_is_refused(env):
    with pytest.raises(execution.continuation.ContinuationRunNotFound):
        _execute_continuation(env, str(uuid.uuid4()))
    assert env.db.runs == []
    assert env.provider.calls == []


def test_33_18_readiness_blocks_a_continuation_before_any_side_effect(env):
    """§16.18 — and before the candidate read, which would otherwise 503."""
    parent = _seed_completed_view_run(env)
    env.db.has_candidates_table = False
    before = len(env.db.runs)

    with pytest.raises(readiness.LlmDiscoveryDatabaseNotReady):
        _execute_continuation(env, parent)

    assert len(env.db.runs) == before
    assert env.provider.calls == []


def test_33_17_a_continuation_still_runs_on_the_policy_model(env):
    """§16.17 — continuation selects a question, never a model."""
    parent = _seed_completed_view_run(env)
    _execute_continuation(env, parent)

    assert env.provider.calls[0]["model"] == effective_deepseek_model(None)
    assert env.provider.calls[0]["model"] == "deepseek-flash"
    child = env.db.runs[-1]
    assert child["provider"] == "deepseek"
    assert child["model_name"] == "deepseek-flash"


def test_33_19_legacy_no_body_discovery_is_still_unchanged(client, env):
    response = client.post(BASE + "/brain-regions/" + SEED_ENTITY + "/llm-discovery/execute")
    assert response.status_code == 200
    assert env.db.runs[0]["query_strategy_version"] is None
    assert _prov(env.db.runs[0]) == {}
