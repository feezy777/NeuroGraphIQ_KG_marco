"""Phase 2B — Discovery Run lifecycle state machine.

No live database: ``get_db`` is overridden with an in-memory fake that models
just enough of the table (rows, the active-run uniqueness rule, the column
invariants) for the state machine and the HTTP error contract to be exercised
for real. The authority table is never written to (§22).

The fake deliberately enforces the SAME invariants as the gate7b_012
constraints, so a transition that would violate them fails here too.
"""
from __future__ import annotations

import ast
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.main import app
from app.schemas.knowledge_production import (
    ACTIVE_DISCOVERY_RUN_STATUSES,
    COMPLETION_OUTCOMES_BY_TYPE,
    TERMINAL_DISCOVERY_RUN_STATUSES,
)
from app.services import knowledge_discovery_run_lifecycle_service as lifecycle
from app.services import knowledge_discovery_run_service as read_svc

BASE = "/api/knowledge-production"
SEED_ENTITY = "NGIQ-BR-00000001"
UNKNOWN_ENTITY = "NGIQ-BR-99999999"
SERVICE_PATH = Path(lifecycle.__file__)

_RUN_COLUMNS = (
    "run_id", "discovery_type", "status", "outcome", "provider", "model_name",
    "prompt_key", "prompt_version", "query_strategy_version", "created_by",
    "created_at", "started_at", "finished_at", "error_code", "error_message",
)


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None, scalar: Any = None):
        self._rows = list(rows or [])
        self._scalar = scalar

    def scalar_one(self) -> Any:
        return self._scalar

    def scalar_one_or_none(self) -> Any:
        return self._scalar

    def mappings(self) -> "_FakeResult":
        return self

    def one(self) -> dict[str, Any]:
        return self._rows[0]

    def one_or_none(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class _FakeDiscoveryDb:
    """In-memory knowledge_discovery_runs + brain_regions, with DB invariants."""

    def __init__(self, seeds: dict[str, int] | None = None) -> None:
        self.seeds = seeds if seeds is not None else {SEED_ENTITY: 3}
        self.runs: list[dict[str, Any]] = []
        self._t = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
        self.insert_attempts = 0

    def tick(self) -> datetime:
        self._t = self._t + timedelta(minutes=1)
        return self._t

    # -- helpers used by tests to arrange state -----------------------------
    def seed_run(
        self,
        *,
        entity_id: str = SEED_ENTITY,
        discovery_type: str = "LLM_DISCOVERY",
        status: str = "QUEUED",
        outcome: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> str:
        run_id = str(uuid.uuid4())
        self.runs.append(
            {
                "run_id": run_id,
                "seed_entity_id": entity_id,
                "seed_region_pk": self.seeds[entity_id],
                "discovery_type": discovery_type,
                "status": status,
                "outcome": outcome,
                "provider": None,
                "model_name": None,
                "prompt_key": None,
                "prompt_version": None,
                "query_strategy_version": None,
                "created_by": None,
                "created_at": self.tick(),
                "started_at": started_at,
                "finished_at": finished_at,
                "error_code": error_code,
                "error_message": error_message,
            }
        )
        return run_id

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

        # 1. seed identity resolution (read service)
        if sql.startswith("SELECT b.entity_pk FROM brain_regions"):
            return _FakeResult(scalar=self.db.seeds.get(p.get("entity_id")))

        # 2. create
        if sql.startswith("INSERT INTO knowledge_discovery_runs"):
            self.db.insert_attempts += 1
            dup = self.db.active_duplicate(p["seed_region_pk"], p["discovery_type"])
            if dup is not None:
                # Mirrors uq_kdr_active_per_seed_type firing.
                raise IntegrityError(
                    "INSERT", p, Exception("duplicate key value violates unique constraint")
                )
            row = {
                "run_id": str(uuid.uuid4()),
                "seed_entity_id": next(
                    k for k, v in self.db.seeds.items() if v == p["seed_region_pk"]
                ),
                "seed_region_pk": p["seed_region_pk"],
                "discovery_type": p["discovery_type"],
                "status": "QUEUED",
                "outcome": None,
                "provider": None,
                "model_name": None,
                "prompt_key": None,
                "prompt_version": None,
                "query_strategy_version": None,
                "created_by": None,
                "created_at": self.db.tick(),
                "started_at": None,
                "finished_at": None,
                "error_code": None,
                "error_message": None,
            }
            self.db.runs.append(row)
            return _FakeResult(rows=[row])

        # 3. lock the run row (lifecycle) / plain read of one run (read service)
        if "knowledge_discovery_runs r" in sql and "r.run_id = :run_id" in sql:
            found = [r for r in self.db.runs if r["run_id"] == p.get("run_id")]
            return _FakeResult(rows=found)

        # 4. find an existing active run (409 detail)
        if "status = ANY(" in sql:
            dup = self.db.active_duplicate(p["seed_region_pk"], p["discovery_type"])
            return _FakeResult(scalar=dup["run_id"] if dup else None)

        # 5. transition UPDATE ... RETURNING
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
            else:  # pragma: no cover - guards against an unhandled SET clause
                raise AssertionError(f"unhandled SET clause: {sql}")
            self._check_invariants(row)
            return _FakeResult(rows=[row])

        raise AssertionError(f"unhandled SQL: {sql}")  # pragma: no cover

    @staticmethod
    def _check_invariants(row: dict[str, Any]) -> None:
        """The gate7b_012 constraints, so tests cannot accept an illegal row."""
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


@pytest.fixture()
def db() -> _FakeDiscoveryDb:
    return _FakeDiscoveryDb()


@pytest.fixture()
def session(db: _FakeDiscoveryDb) -> _FakeSession:
    return _FakeSession(db)


@pytest.fixture()
def client(session: _FakeSession):
    async def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def create(client, discovery_type: str = "LLM_DISCOVERY", entity: str = SEED_ENTITY):
    return client.post(
        f"{BASE}/brain-regions/{entity}/discovery-runs", json={"discovery_type": discovery_type}
    )


# ===========================================================================
# CREATE
# ===========================================================================
def test_create_llm_run_is_queued(client, session):
    res = create(client)
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "QUEUED"
    assert body["discovery_type"] == "LLM_DISCOVERY"
    assert body["seed_entity_id"] == SEED_ENTITY
    # creation produces NO execution facts
    for field in ("outcome", "started_at", "finished_at", "provider", "model_name",
                  "prompt_key", "prompt_version", "query_strategy_version", "created_by"):
        assert body[field] is None, field


def test_create_literature_run_is_queued(client, session):
    res = create(client, "LITERATURE_DISCOVERY")
    assert res.status_code == 201
    assert res.json()["discovery_type"] == "LITERATURE_DISCOVERY"
    assert res.json()["status"] == "QUEUED"


def test_create_for_unknown_brain_region_is_404(client, session):
    res = create(client, entity=UNKNOWN_ENTITY)
    assert res.status_code == 404
    assert res.json()["detail"]["code"] == "NOT_FOUND"
    assert session.db.insert_attempts == 0, "unknown seed must not attempt an insert"


def test_duplicate_active_run_is_409(client, session):
    first = create(client)
    assert first.status_code == 201
    res = create(client)
    assert res.status_code == 409
    detail = res.json()["detail"]
    assert detail["code"] == "ACTIVE_RUN_EXISTS"
    # the conflicting run is identified by its PUBLIC run_id
    assert detail["active_run_id"] == first.json()["run_id"]
    assert "seed_region_pk" not in res.text
    assert len(session.db.runs) == 1, "no second row may be created"


def test_different_discovery_types_may_coexist(client, session):
    assert create(client, "LLM_DISCOVERY").status_code == 201
    assert create(client, "LITERATURE_DISCOVERY").status_code == 201
    assert len(session.db.runs) == 2


def test_terminal_history_does_not_block_a_new_run(client, session, db):
    old = db.seed_run(status="COMPLETED", outcome="CANDIDATES_FOUND",
                      started_at=db.tick(), finished_at=db.tick())
    res = create(client)
    assert res.status_code == 201
    assert res.json()["run_id"] != old
    assert len(db.runs) == 2


def test_create_rejects_client_supplied_execution_provenance(client, session):
    res = client.post(
        f"{BASE}/brain-regions/{SEED_ENTITY}/discovery-runs",
        json={"discovery_type": "LLM_DISCOVERY", "provider": "deepseek"},
    )
    assert res.status_code == 422
    assert session.db.insert_attempts == 0, "an invalid body must not reach the service"


def test_create_rejects_unknown_discovery_type(client, session):
    res = client.post(
        f"{BASE}/brain-regions/{SEED_ENTITY}/discovery-runs", json={"discovery_type": "NOPE"}
    )
    assert res.status_code == 422
    assert session.db.insert_attempts == 0


# ===========================================================================
# START
# ===========================================================================
def test_start_queued_to_running(client, session, db):
    run_id = db.seed_run()
    res = client.post(f"{BASE}/discovery-runs/{run_id}/start")
    assert res.status_code == 200
    assert res.json()["status"] == "RUNNING"
    assert res.json()["started_at"] is not None
    assert res.json()["finished_at"] is None
    assert res.json()["outcome"] is None


def test_start_while_running_is_idempotent(client, session, db):
    run_id = db.seed_run(status="RUNNING", started_at=db.tick())
    before = db.runs[0]["started_at"]
    res = client.post(f"{BASE}/discovery-runs/{run_id}/start")
    assert res.status_code == 200
    assert res.json()["status"] == "RUNNING"
    assert db.runs[0]["started_at"] == before, "no mutation on idempotent start"
    assert session.commits == 0


@pytest.mark.parametrize("status", ["COMPLETED", "FAILED", "CANCELLED"])
def test_start_from_terminal_is_409(client, session, db, status):
    run_id = db.seed_run(
        status=status,
        outcome="CANDIDATES_FOUND" if status == "COMPLETED" else None,
        started_at=db.tick(),
        finished_at=db.tick(),
    )
    res = client.post(f"{BASE}/discovery-runs/{run_id}/start")
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "RUN_ALREADY_TERMINAL"
    assert db.runs[0]["status"] == status, "terminal state must be untouched"


def test_start_unknown_run_is_404(client, session):
    res = client.post(f"{BASE}/discovery-runs/{uuid.uuid4()}/start")
    assert res.status_code == 404


def test_start_malformed_run_id_is_404_not_500(client, session):
    res = client.post(f"{BASE}/discovery-runs/not-a-uuid/start")
    assert res.status_code == 404
    assert session.statements == [], "a malformed id must not reach the database"


# ===========================================================================
# COMPLETE
# ===========================================================================
def test_complete_running_to_completed(client, session, db):
    run_id = db.seed_run(status="RUNNING", started_at=db.tick())
    res = client.post(
        f"{BASE}/discovery-runs/{run_id}/complete", json={"outcome": "CANDIDATES_FOUND"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "COMPLETED"
    assert body["outcome"] == "CANDIDATES_FOUND"
    assert body["finished_at"] is not None
    assert body["started_at"] is not None


def test_llm_may_not_complete_with_no_evidence_found(client, session, db):
    run_id = db.seed_run(status="RUNNING", started_at=db.tick())
    res = client.post(
        f"{BASE}/discovery-runs/{run_id}/complete", json={"outcome": "NO_EVIDENCE_FOUND"}
    )
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["code"] == "OUTCOME_NOT_ALLOWED"
    assert detail["discovery_type"] == "LLM_DISCOVERY"
    assert "NO_EVIDENCE_FOUND" not in detail["allowed_outcomes"]
    assert db.runs[0]["status"] == "RUNNING", "no mutation on rejection"


def test_literature_may_complete_with_no_evidence_found(client, session, db):
    run_id = db.seed_run(
        discovery_type="LITERATURE_DISCOVERY", status="RUNNING", started_at=db.tick()
    )
    res = client.post(
        f"{BASE}/discovery-runs/{run_id}/complete", json={"outcome": "NO_EVIDENCE_FOUND"}
    )
    assert res.status_code == 200
    assert res.json()["outcome"] == "NO_EVIDENCE_FOUND"
    # status != outcome: finished, and "no evidence" is a real scientific answer
    assert res.json()["status"] == "COMPLETED"


def test_complete_from_queued_is_409(client, session, db):
    run_id = db.seed_run()  # QUEUED
    res = client.post(
        f"{BASE}/discovery-runs/{run_id}/complete", json={"outcome": "CANDIDATES_FOUND"}
    )
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "RUN_NOT_STARTED"
    assert db.runs[0]["status"] == "QUEUED"


def test_complete_requires_an_outcome(client, session, db):
    run_id = db.seed_run(status="RUNNING", started_at=db.tick())
    res = client.post(f"{BASE}/discovery-runs/{run_id}/complete", json={})
    assert res.status_code == 422


def test_repeat_same_complete_is_idempotent(client, session, db):
    run_id = db.seed_run(
        status="COMPLETED", outcome="NO_CANDIDATES_FOUND",
        started_at=db.tick(), finished_at=db.tick(),
    )
    res = client.post(
        f"{BASE}/discovery-runs/{run_id}/complete", json={"outcome": "NO_CANDIDATES_FOUND"}
    )
    assert res.status_code == 200
    assert res.json()["outcome"] == "NO_CANDIDATES_FOUND"
    assert session.commits == 0, "idempotent repeat must not write"


def test_repeat_complete_with_different_outcome_is_409(client, session, db):
    run_id = db.seed_run(
        status="COMPLETED", outcome="CANDIDATES_FOUND",
        started_at=db.tick(), finished_at=db.tick(),
    )
    res = client.post(
        f"{BASE}/discovery-runs/{run_id}/complete", json={"outcome": "NO_CANDIDATES_FOUND"}
    )
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "OUTCOME_ALREADY_RECORDED"
    assert db.runs[0]["outcome"] == "CANDIDATES_FOUND"


@pytest.mark.parametrize("status", ["FAILED", "CANCELLED"])
def test_complete_from_other_terminal_is_409(client, session, db, status):
    run_id = db.seed_run(status=status, started_at=db.tick(), finished_at=db.tick())
    res = client.post(
        f"{BASE}/discovery-runs/{run_id}/complete", json={"outcome": "CANDIDATES_FOUND"}
    )
    assert res.status_code == 409


# ===========================================================================
# FAIL
# ===========================================================================
def test_fail_queued_to_failed_without_faking_started_at(client, session, db):
    run_id = db.seed_run()  # QUEUED
    res = client.post(
        f"{BASE}/discovery-runs/{run_id}/fail",
        json={"error_code": "PROVIDER_TIMEOUT", "error_message": "upstream timeout"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "FAILED"
    assert body["error_code"] == "PROVIDER_TIMEOUT"
    assert body["error_message"] == "upstream timeout"
    assert body["started_at"] is None, "a QUEUED failure must not invent started_at"
    assert body["finished_at"] is not None
    assert body["outcome"] is None, "failure is not a scientific outcome"


def test_fail_running_to_failed_keeps_started_at(client, session, db):
    run_id = db.seed_run(status="RUNNING", started_at=db.tick())
    res = client.post(
        f"{BASE}/discovery-runs/{run_id}/fail", json={"error_message": "boom"}
    )
    assert res.status_code == 200
    assert res.json()["started_at"] is not None
    assert res.json()["finished_at"] is not None
    assert res.json()["error_code"] is None


@pytest.mark.parametrize("payload", [{}, {"error_message": ""}, {"error_message": None}])
def test_fail_requires_a_non_empty_message(client, session, db, payload):
    run_id = db.seed_run(status="RUNNING", started_at=db.tick())
    res = client.post(f"{BASE}/discovery-runs/{run_id}/fail", json=payload)
    assert res.status_code == 422
    assert db.runs[0]["status"] == "RUNNING"


def test_fail_rejects_an_over_long_error_code(client, session, db):
    """error_code is VARCHAR(64): reject, never silently truncate."""
    run_id = db.seed_run(status="RUNNING", started_at=db.tick())
    res = client.post(
        f"{BASE}/discovery-runs/{run_id}/fail",
        json={"error_code": "X" * 65, "error_message": "boom"},
    )
    assert res.status_code == 422


def test_repeat_identical_fail_is_idempotent(client, session, db):
    run_id = db.seed_run(
        status="FAILED", error_code="E1", error_message="boom",
        started_at=db.tick(), finished_at=db.tick(),
    )
    res = client.post(
        f"{BASE}/discovery-runs/{run_id}/fail",
        json={"error_code": "E1", "error_message": "boom"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "FAILED"
    assert session.commits == 0


def test_repeat_different_fail_is_409(client, session, db):
    run_id = db.seed_run(
        status="FAILED", error_code="E1", error_message="boom",
        started_at=db.tick(), finished_at=db.tick(),
    )
    res = client.post(
        f"{BASE}/discovery-runs/{run_id}/fail",
        json={"error_code": "E2", "error_message": "different"},
    )
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "FAILURE_ALREADY_RECORDED"
    assert db.runs[0]["error_code"] == "E1"


@pytest.mark.parametrize("status", ["COMPLETED", "CANCELLED"])
def test_fail_from_completed_or_cancelled_is_409(client, session, db, status):
    run_id = db.seed_run(
        status=status,
        outcome="CANDIDATES_FOUND" if status == "COMPLETED" else None,
        started_at=db.tick(), finished_at=db.tick(),
    )
    res = client.post(
        f"{BASE}/discovery-runs/{run_id}/fail", json={"error_message": "boom"}
    )
    assert res.status_code == 409


# ===========================================================================
# CANCEL
# ===========================================================================
@pytest.mark.parametrize("status", ["QUEUED", "RUNNING"])
def test_cancel_from_active_states(client, session, db, status):
    run_id = db.seed_run(status=status, started_at=db.tick() if status == "RUNNING" else None)
    res = client.post(f"{BASE}/discovery-runs/{run_id}/cancel")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "CANCELLED"
    assert body["finished_at"] is not None
    assert body["outcome"] is None, "cancellation is not a scientific result"
    assert body["error_code"] is None, "cancellation must not invent an error"


def test_repeat_cancel_is_idempotent(client, session, db):
    run_id = db.seed_run(status="CANCELLED", started_at=db.tick(), finished_at=db.tick())
    res = client.post(f"{BASE}/discovery-runs/{run_id}/cancel")
    assert res.status_code == 200
    assert res.json()["status"] == "CANCELLED"
    assert session.commits == 0


@pytest.mark.parametrize("status", ["COMPLETED", "FAILED"])
def test_cancel_from_completed_or_failed_is_409(client, session, db, status):
    run_id = db.seed_run(
        status=status,
        outcome="CANDIDATES_FOUND" if status == "COMPLETED" else None,
        started_at=db.tick(), finished_at=db.tick(),
    )
    res = client.post(f"{BASE}/discovery-runs/{run_id}/cancel")
    assert res.status_code == 409
    assert db.runs[0]["status"] == status


# ===========================================================================
# GENERAL — immutability, contract, isolation
# ===========================================================================
def test_terminal_states_cannot_reopen(client, session, db):
    """A terminal state has exactly one legal call: its OWN idempotent repeat.

    Every other action — including a *different* repeat of the same action —
    is refused with 409, and nothing is written.
    """
    # (terminal status, the one action that is its own repeat, all other actions)
    cases = {
        "COMPLETED": (
            ("complete", {"outcome": "CANDIDATES_FOUND"}),
            [
                ("start", None),
                ("complete", {"outcome": "NO_CANDIDATES_FOUND"}),
                ("fail", {"error_message": "x"}),
                ("cancel", None),
            ],
        ),
        "FAILED": (
            ("fail", {"error_code": "E1", "error_message": "boom"}),
            [
                ("start", None),
                ("complete", {"outcome": "CANDIDATES_FOUND"}),
                ("fail", {"error_message": "boom"}),
                ("cancel", None),
            ],
        ),
        "CANCELLED": (
            ("cancel", None),
            [
                ("start", None),
                ("complete", {"outcome": "CANDIDATES_FOUND"}),
                ("fail", {"error_message": "x"}),
                ("cancel", None),  # repeated cancel IS the repeat; see below
            ],
        ),
    }

    for status, (repeat_action, others) in cases.items():
        extra: dict[str, Any] = {}
        if status == "COMPLETED":
            extra = {"outcome": "CANDIDATES_FOUND"}
        elif status == "FAILED":
            extra = {"error_code": "E1", "error_message": "boom"}
        run_id = db.seed_run(status=status, started_at=db.tick(), finished_at=db.tick(), **extra)
        row_before = dict(db.runs[-1])

        # the idempotent repeat is allowed and does not mutate
        action, body = repeat_action
        repeat = client.post(
            f"{BASE}/discovery-runs/{run_id}/{action}", json=body if body is not None else None
        )
        assert repeat.status_code == 200, f"{status} own repeat must be idempotent"
        assert db.runs[-1] == row_before, "an idempotent repeat must not mutate the row"

        # everything else is a conflict
        for action, body in others:
            if action == repeat_action[0] and body == repeat_action[1]:
                continue  # the repeat itself, already asserted
            if status == "CANCELLED" and action == "cancel":
                continue  # repeated cancel is CANCELLED's own repeat
            res = client.post(
                f"{BASE}/discovery-runs/{run_id}/{action}",
                json=body if body is not None else None,
            )
            assert res.status_code == 409, f"{status} -> {action} must be 409"
            assert db.runs[-1] == row_before, "no refused transition may have written anything"


def test_non_completed_status_never_stores_an_outcome(client, session, db):
    run_id = db.seed_run()
    client.post(f"{BASE}/discovery-runs/{run_id}/start")
    client.post(f"{BASE}/discovery-runs/{run_id}/cancel")
    assert db.runs[0]["status"] == "CANCELLED"
    assert db.runs[0]["outcome"] is None

    other = db.seed_run(discovery_type="LITERATURE_DISCOVERY")
    client.post(f"{BASE}/discovery-runs/{other}/fail", json={"error_message": "x"})
    failed = next(r for r in db.runs if r["run_id"] == other)
    assert failed["outcome"] is None


def test_public_dto_exposes_run_id_not_run_pk(client, db):
    run_id = db.seed_run()
    body = client.get(f"{BASE}/discovery-runs/{run_id}").json()
    assert body["run_id"] == run_id
    assert "run_pk" not in body
    assert "seed_region_pk" not in body


def test_no_entity_pk_in_any_lifecycle_route(client, db):
    """The public surface is entity_id / run_id based only — success AND error bodies."""
    created = create(client)
    assert created.status_code == 201
    run_id = created.json()["run_id"]
    responses = [
        ("create", created, 201),
        # still active, so this is the duplicate-active conflict body
        ("create-duplicate", create(client), 409),
        ("get", client.get(f"{BASE}/discovery-runs/{run_id}"), 200),
        ("start", client.post(f"{BASE}/discovery-runs/{run_id}/start"), 200),
        ("cancel", client.post(f"{BASE}/discovery-runs/{run_id}/cancel"), 200),
        # terminal now: this refused transition is a second kind of error body
        ("start-after-terminal", client.post(f"{BASE}/discovery-runs/{run_id}/start"), 409),
    ]
    assert [(n, r.status_code) for n, r, _ in responses] == [
        (n, s) for n, _, s in responses
    ]
    for name, res, expected in responses:
        assert res.status_code == expected, name
        assert "entity_pk" not in res.text, name
        assert "run_pk" not in res.text, name
        assert "seed_region_pk" not in res.text, name


def test_outcome_vocabularies_are_disjoint_from_status():
    """status != outcome, as a property of the vocabularies themselves."""
    assert set(ACTIVE_DISCOVERY_RUN_STATUSES) & set(TERMINAL_DISCOVERY_RUN_STATUSES) == set()
    for allowed in COMPLETION_OUTCOMES_BY_TYPE.values():
        assert set(allowed) & set(TERMINAL_DISCOVERY_RUN_STATUSES) == set()


def test_llm_route_cannot_claim_no_evidence_as_a_completion_outcome():
    assert "NO_EVIDENCE_FOUND" not in COMPLETION_OUTCOMES_BY_TYPE["LLM_DISCOVERY"]
    assert "NO_EVIDENCE_FOUND" in COMPLETION_OUTCOMES_BY_TYPE["LITERATURE_DISCOVERY"]


def test_lifecycle_service_exposes_exactly_five_public_functions():
    tree = ast.parse(SERVICE_PATH.read_text(encoding="utf-8"))
    public = {
        n.name
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("_")
    }
    assert public == {
        "create_discovery_run",
        "start_discovery_run",
        "complete_discovery_run",
        "fail_discovery_run",
        "cancel_discovery_run",
    }, public


def test_read_service_is_still_read_only():
    """Phase 2B must not turn the read service into a mixed read/write service."""
    tree = ast.parse(Path(read_svc.__file__).read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            n.value = ""
    code = ast.unparse(tree).upper()
    for verb in ("INSERT", "UPDATE", "DELETE", "COMMIT", "ROLLBACK"):
        assert verb not in code, f"the read service must not contain {verb}"


def test_lifecycle_service_never_touches_discovery_execution():
    src = SERVICE_PATH.read_text(encoding="utf-8").lower()
    for forbidden in (
        "llm_provider", "deepseek", "kimi", "openai", "httpx",
        "pubmed", "europepmc", "openalex", "semanticscholar",
        "paper_search", "paper_evidence",
    ):
        assert forbidden not in src, f"lifecycle must not reference {forbidden!r}"


def test_lifecycle_service_has_no_legacy_pipeline_dependency():
    tree = ast.parse(SERVICE_PATH.read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            n.value = ""
    code = ast.unparse(tree).lower()
    for term in ("candidate_", "mirror_", "final_", "ranking_id", "task_type"):
        assert term not in code, f"lifecycle must not reference {term!r}"


# ===========================================================================
# Concurrency / database invariants (§24)
# ===========================================================================
def test_integrity_error_becomes_409_not_500(client, session, db):
    """The partial unique index is the authority; its violation is a 409."""
    db.seed_run()  # an active run already exists
    res = create(client)
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "ACTIVE_RUN_EXISTS"
    assert session.rollbacks == 1, "the failed transaction must be rolled back"


def test_race_between_two_creates_leaves_exactly_one_row(client, session, db):
    """Two creates that both saw 'no active run': the database settles it.

    The first insert lands; the second hits uq_kdr_active_per_seed_type and is
    reported as 409 rather than creating a duplicate.
    """
    first = create(client)
    second = create(client)
    assert (first.status_code, second.status_code) == (201, 409)
    assert len(db.runs) == 1


def test_migration_declares_the_partial_unique_active_index():
    """The invariant is protected by PostgreSQL, not only by application checks."""
    sql = (
        Path(__file__).resolve().parent.parent
        / "migrations"
        / "gate7b_012_discovery_run_lifecycle_integrity.sql"
    ).read_text(encoding="utf-8")
    upper = sql.upper()
    assert "CREATE UNIQUE INDEX IF NOT EXISTS UQ_KDR_ACTIVE_PER_SEED_TYPE" in upper
    assert "ON KNOWLEDGE_DISCOVERY_RUNS (SEED_REGION_PK, DISCOVERY_TYPE)" in upper
    assert "WHERE STATUS IN ('QUEUED', 'RUNNING')" in upper


def test_migration_declares_the_three_lifecycle_checks():
    sql = (
        Path(__file__).resolve().parent.parent
        / "migrations"
        / "gate7b_012_discovery_run_lifecycle_integrity.sql"
    ).read_text(encoding="utf-8")
    for name in (
        "ck_kdr_outcome_matches_status",
        "ck_kdr_finished_at_by_status",
        "ck_kdr_started_at_required_after_start",
    ):
        assert name in sql
    # the state machine is NOT expressed in SQL
    assert "RUNNING' THEN 'COMPLETED" not in sql.upper()
