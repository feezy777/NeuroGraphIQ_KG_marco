"""Phase 2A — Discovery Run read-only API + service boundary tests.

These tests need no live database: the FastAPI dependency ``get_db`` is
overridden with a recording stub session, so the router, query-parameter
validation and the DTO contract are exercised for real while SQL execution is
simulated.

Phase 2A is a PERSISTENCE / READ foundation. Two boundaries are asserted here
and must keep holding in later phases:

  * the run service is READ-ONLY (no INSERT / UPDATE / DELETE), because run
    lifecycle transitions belong to Phase 2B in a separate governed module;
  * nothing on this path touches the legacy Candidate / Mirror / Final
    pipelines, and nothing executes discovery (no LLM, no literature search).
"""
from __future__ import annotations

import ast
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.schemas.knowledge_production import (
    DISCOVERY_RUN_OUTCOMES,
    DISCOVERY_RUN_STATUSES,
    DISCOVERY_TYPES,
    LITERATURE_DISCOVERY_TYPES,
    DiscoveryRunItem,
)
from app.services import knowledge_discovery_run_service as run_svc

RUNS_ENDPOINT = "/api/knowledge-production/brain-regions/NGIQ-BR-00000001/discovery-runs"
RUN_ENDPOINT = "/api/knowledge-production/discovery-runs"
SERVICE_PATH = Path(run_svc.__file__)

# Internal shared PK that the public entity_id must resolve to. The public API
# must never expose this value.
SEED_REGION_PK = 3


def _run_row(**over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "run_id": "11111111-2222-3333-4444-555555555555",
        "seed_entity_id": "NGIQ-BR-00000001",
        "discovery_type": "LLM_DISCOVERY",
        "status": "QUEUED",
        "outcome": None,
        "provider": None,
        "model_name": None,
        "prompt_key": None,
        "prompt_version": None,
        "query_strategy_version": None,
        "created_by": None,
        "created_at": datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc),
        "started_at": None,
        "finished_at": None,
        "error_code": None,
        "error_message": None,
    }
    row.update(over)
    return row


def _code_only(path: Path) -> str:
    """Source with comments and string literals removed.

    Terminology/boundary checks must inspect executable code and SQL, not the
    prose in docstrings (which legitimately names the things it forbids).
    """
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            node.value = ""
    return ast.unparse(tree)


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None, scalar: Any = None):
        self._rows = rows or []
        self._scalar = scalar

    def scalar_one(self) -> Any:
        return self._scalar

    def scalar_one_or_none(self) -> Any:
        return self._scalar

    def mappings(self) -> "_FakeResult":
        return self

    def all(self) -> list[dict[str, Any]]:
        return self._rows

    def one_or_none(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class _RecordingSession:
    """Records every statement; answers the three query shapes by SQL shape."""

    def __init__(
        self,
        *,
        region_pk: int | None = SEED_REGION_PK,
        total: int = 0,
        rows: list[dict[str, Any]] | None = None,
        detail_row: dict[str, Any] | None = None,
    ) -> None:
        self.region_pk = region_pk
        self.total = total
        self.rows = rows if rows is not None else []
        self.detail_row = detail_row
        self.statements: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> _FakeResult:
        sql = " ".join(str(stmt).split())
        self.statements.append((sql, dict(params or {})))
        if "knowledge_discovery_runs" in sql:
            if sql.upper().startswith("SELECT COUNT(*)"):
                return _FakeResult(rows=[], scalar=self.total)
            if "WHERE r.run_id" in sql:
                return _FakeResult(rows=[self.detail_row] if self.detail_row else [])
            return _FakeResult(rows=self.rows)
        # BrainRegion identity resolution (kg_entities / brain_regions)
        return _FakeResult(scalar=self.region_pk)

    @property
    def sql_text(self) -> str:
        return " ".join(s for s, _ in self.statements)


@pytest.fixture()
def session() -> _RecordingSession:
    return _RecordingSession()


@pytest.fixture()
def client(session: _RecordingSession):
    async def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# 1 / 2 — list shape, empty table
# ---------------------------------------------------------------------------
def test_list_returns_items_and_total(client, session):
    session.total = 1
    session.rows = [_run_row()]
    res = client.get(RUNS_ENDPOINT)
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"items", "total"}
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["run_id"] == "11111111-2222-3333-4444-555555555555"
    assert body["items"][0]["seed_entity_id"] == "NGIQ-BR-00000001"
    assert body["items"][0]["discovery_type"] == "LLM_DISCOVERY"
    assert body["items"][0]["status"] == "QUEUED"
    assert body["items"][0]["outcome"] is None


def test_empty_table_returns_empty_page(client, session):
    """Accepted Phase 2A expectation: {"items": [], "total": 0}."""
    res = client.get(RUNS_ENDPOINT)
    assert res.status_code == 200
    assert res.json() == {"items": [], "total": 0}


# ---------------------------------------------------------------------------
# 3 — public identity resolution
# ---------------------------------------------------------------------------
def test_entity_id_resolves_to_internal_seed_region_pk(client, session):
    client.get(RUNS_ENDPOINT)
    # resolution goes public entity_id -> kg_entities/brain_regions -> internal PK
    resolvers = [s for s, _ in session.statements if "knowledge_discovery_runs" not in s]
    assert resolvers, "the BrainRegion identity must be resolved"
    assert any("entity_id = :entity_id" in s for s in resolvers)
    # the run queries are scoped by public identity, never by internal PK
    run_sql = [s for s, _ in session.statements if "knowledge_discovery_runs" in s]
    assert run_sql and all("e.entity_id = :entity_id" in s for s in run_sql)
    assert all("seed_region_pk =" not in s for s in run_sql)
    assert all(
        p.get("entity_id") == "NGIQ-BR-00000001"
        for s, p in session.statements
        if "knowledge_discovery_runs" in s
    )


def test_internal_pk_is_never_exposed(client, session):
    """The public API is entity_id based; the internal shared PK stays internal."""
    session.total = 1
    session.rows = [_run_row()]
    item = client.get(RUNS_ENDPOINT).json()["items"][0]
    assert "seed_region_pk" not in item
    assert SEED_REGION_PK not in item.values()
    # the seed is addressed by its public identity, not its PK
    assert item["seed_entity_id"] == "NGIQ-BR-00000001"


def test_unknown_brain_region_is_404_not_an_empty_page(client, session):
    """'no such region' and 'no runs for this region' are different facts."""
    session.region_pk = None
    res = client.get("/api/knowledge-production/brain-regions/NGIQ-BR-99999999/discovery-runs")
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# 4 / 5 / 6 — filters and pagination
# ---------------------------------------------------------------------------
def test_discovery_type_filter_is_applied(client, session):
    res = client.get(RUNS_ENDPOINT, params={"discovery_type": "LITERATURE_DISCOVERY"})
    assert res.status_code == 200
    run_sql = [s for s, _ in session.statements if "knowledge_discovery_runs" in s]
    assert all("r.discovery_type = :discovery_type" in s for s in run_sql)
    assert all(
        p["discovery_type"] == "LITERATURE_DISCOVERY"
        for s, p in session.statements
        if "knowledge_discovery_runs" in s
    )


def test_status_filter_is_applied(client, session):
    res = client.get(RUNS_ENDPOINT, params={"status": "COMPLETED"})
    assert res.status_code == 200
    run_sql = [s for s, _ in session.statements if "knowledge_discovery_runs" in s]
    assert all("r.status = :status" in s for s in run_sql)
    assert all(
        p["status"] == "COMPLETED"
        for s, p in session.statements
        if "knowledge_discovery_runs" in s
    )


def test_filters_combine_and_hit_both_count_and_page(client, session):
    client.get(RUNS_ENDPOINT, params={"discovery_type": "LLM_DISCOVERY", "status": "FAILED"})
    run_sql = [s for s, _ in session.statements if "knowledge_discovery_runs" in s]
    assert len(run_sql) == 2, "one COUNT + one page query"
    for s in run_sql:
        assert "r.discovery_type = :discovery_type" in s
        assert "r.status = :status" in s


def test_limit_and_offset_are_passed_through(client, session):
    client.get(RUNS_ENDPOINT, params={"limit": 5, "offset": 10})
    page = [p for s, p in session.statements if "knowledge_discovery_runs" in s and "LIMIT" in s]
    assert page and page[0]["limit"] == 5 and page[0]["offset"] == 10


def test_runs_are_ordered_newest_first(client, session):
    client.get(RUNS_ENDPOINT)
    page = [s for s in session.sql_text.split(";") if "ORDER BY" in s]
    assert page and "r.created_at DESC" in page[0]


# ---------------------------------------------------------------------------
# 7 / 8 — parameter validation
# ---------------------------------------------------------------------------
def test_invalid_discovery_type_is_422(client, session):
    res = client.get(RUNS_ENDPOINT, params={"discovery_type": "BOGUS"})
    assert res.status_code == 422
    assert session.statements == [], "invalid input must not reach the database"


def test_invalid_status_is_422(client, session):
    res = client.get(RUNS_ENDPOINT, params={"status": "NOPE"})
    assert res.status_code == 422
    assert session.statements == []


def test_every_frozen_vocabulary_value_is_accepted_by_validation(client, session):
    """The frozen contract exactly (no extra value silently allowed)."""
    for t in DISCOVERY_TYPES:
        assert client.get(RUNS_ENDPOINT, params={"discovery_type": t}).status_code == 200
    for s in DISCOVERY_RUN_STATUSES:
        assert client.get(RUNS_ENDPOINT, params={"status": s}).status_code == 200


def test_the_discovery_type_vocabulary_is_frozen_and_complete():
    """COMPLETENESS, not just validity.

    The test above passes even if this constant holds HALF the vocabulary --
    which is how it went stale (gate7b_013 widened the DB CHECK to four values,
    the constant kept two, nothing compared them). Comparing against a literal
    is the point: it cannot silently follow the vocabulary, and it still works
    where no database is reachable.
    """
    assert set(DISCOVERY_TYPES) == {
        "LLM_DISCOVERY", "LITERATURE_DISCOVERY", "EVIDENCE_SEARCH", "CITATION_CHAINING"}
    assert set(LITERATURE_DISCOVERY_TYPES) == {
        "LITERATURE_DISCOVERY", "EVIDENCE_SEARCH", "CITATION_CHAINING"}


# ---------------------------------------------------------------------------
# 9 — run detail
# ---------------------------------------------------------------------------
def test_unknown_run_id_is_404(client, session):
    res = client.get(f"{RUN_ENDPOINT}/00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404


def test_malformed_run_id_is_404_not_500(client, session):
    """A malformed UUID must not reach the uuid column comparison."""
    res = client.get(f"{RUN_ENDPOINT}/not-a-uuid")
    assert res.status_code == 404
    assert session.statements == [], "a malformed id must not reach the database"


def test_run_detail_returns_the_dto(client, session):
    session.detail_row = _run_row(status="COMPLETED", outcome="NO_EVIDENCE_FOUND")
    res = client.get(f"{RUN_ENDPOINT}/11111111-2222-3333-4444-555555555555")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "COMPLETED"
    assert body["outcome"] == "NO_EVIDENCE_FOUND"
    # status != outcome: a finished run with no evidence is its own answer
    assert body["status"] != body["outcome"]
    assert set(body) == set(DiscoveryRunItem.model_fields)


def test_run_dto_never_exposes_json_blobs_or_secrets(client, session):
    session.rows = [_run_row()]
    res = client.get(RUNS_ENDPOINT)
    item = res.json()["items"][0]
    for forbidden in ("parameters_json", "provenance_json", "api_key", "token", "secret"):
        assert forbidden not in item


# ---------------------------------------------------------------------------
# Phase 2A boundary: read-only, no lifecycle, no discovery execution
# ---------------------------------------------------------------------------
def test_read_surface_accepts_no_mutation(client, session):
    """Reads stay reads.

    Phase 2A asserted that no writer existed at all. Phase 2B intentionally
    added the five lifecycle POSTs (create/start/complete/fail/cancel), so that
    assertion now lives in the lifecycle suite. What must remain true here is
    that the READ surface itself accepts no mutation: the run-detail path is
    GET-only, and there is no collection-level POST (a run is always created
    against a BrainRegion, never standalone).
    """
    run_id = "11111111-2222-3333-4444-555555555555"
    assert client.patch(f"{RUN_ENDPOINT}/{run_id}", json={}).status_code == 405
    assert client.delete(f"{RUN_ENDPOINT}/{run_id}").status_code == 405
    assert client.put(f"{RUN_ENDPOINT}/{run_id}", json={}).status_code == 405
    assert client.post(RUN_ENDPOINT, json={}).status_code == 404


# 10 — the service layer contains no INSERT / UPDATE / DELETE
def test_service_is_read_only():
    code = _code_only(SERVICE_PATH).upper()
    for verb in ("INSERT", "UPDATE", "DELETE", "UPSERT", "TRUNCATE"):
        assert verb not in code, f"Phase 2A run service must not contain {verb}"


def test_service_declares_only_the_two_read_functions():
    """Phase 2B lifecycle writers must not appear ahead of time."""
    tree = ast.parse(SERVICE_PATH.read_text(encoding="utf-8"))
    public = {
        n.name
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("_")
    }
    assert public == {
        "list_discovery_runs_for_region",
        "get_discovery_run",
        "resolve_seed_region_pk",
        "build_run_filters",
        "normalize_limit",
        "normalize_offset",
        "row_to_item",
    }, public
    for lifecycle in ("create", "start", "complete", "fail", "cancel", "retry", "resume"):
        assert not any(lifecycle in name for name in public), lifecycle


# 11 — no legacy Candidate / Mirror / Final dependency
def test_new_modules_have_no_legacy_pipeline_dependency():
    legacy = ("candidate_", "mirror_", "final_", "ranking_id", "task_type")
    for path in (
        SERVICE_PATH,
        Path(__file__).resolve().parent.parent / "app" / "routers" / "knowledge_production.py",
        Path(__file__).resolve().parent.parent / "app" / "schemas" / "knowledge_production.py",
    ):
        code = _code_only(path).lower()
        for term in legacy:
            assert term not in code, f"{path.name} must not reference {term!r}"


def test_new_modules_do_not_import_discovery_execution():
    """The READ path still executes nothing: no LLM provider, no literature client.

    Phase 3B added an execution layer, and it did that WITHOUT moving execution
    into the read path. The read service still only issues SELECTs and must not
    even name a provider. The router is now allowed to route TO execution — so
    its prose may describe DeepSeek — but its code must still reach no provider,
    and its one execution dependency must be the execution service itself.
    """
    forbidden = (
        "llm_provider",
        "deepseek",
        "kimi",
        "paper_search",
        "pubmed",
        "europepmc",
        "openalex",
        "semanticscholar",
        "paper_evidence",
    )
    src = SERVICE_PATH.read_text(encoding="utf-8").lower()
    for term in forbidden:
        assert term not in src, f"{SERVICE_PATH.name} must not reference {term!r}"

    router_path = (
        Path(__file__).resolve().parent.parent / "app" / "routers" / "knowledge_production.py"
    )
    router_code = _code_only(router_path).lower()
    for term in forbidden:
        assert term not in router_code, f"router code must not reach {term!r}"
    # The router delegates execution; it does not implement any.
    assert "llm_discovery_execution_service" in router_code


# ---------------------------------------------------------------------------
# pure helpers
# ---------------------------------------------------------------------------
def test_build_run_filters_is_pure_and_parameterised():
    where, params = run_svc.build_run_filters()
    assert where == "" and params == {}
    where, params = run_svc.build_run_filters(discovery_type="LLM_DISCOVERY")
    assert where == " WHERE r.discovery_type = :discovery_type"
    assert params == {"discovery_type": "LLM_DISCOVERY"}
    where, params = run_svc.build_run_filters(status="FAILED")
    assert where == " WHERE r.status = :status"
    assert params == {"status": "FAILED"}


def test_normalize_limit_and_offset_clamp():
    assert run_svc.normalize_limit(None) == 50
    assert run_svc.normalize_limit(0) == 50
    assert run_svc.normalize_limit(10_000) == 200
    assert run_svc.normalize_offset(None) == 0
    assert run_svc.normalize_offset(-5) == 0


def test_row_to_item_maps_uuid_to_str_and_keeps_nulls():
    import uuid

    row = _run_row(run_id=uuid.UUID("11111111-2222-3333-4444-555555555555"), provider="deepseek")
    item = run_svc.row_to_item(row)
    assert isinstance(item.run_id, str)
    assert item.run_id == "11111111-2222-3333-4444-555555555555"
    assert item.provider == "deepseek"
    assert item.model_name is None


def test_outcome_is_independent_of_status():
    """status != outcome is the frozen contract, not an implementation detail."""
    assert set(DISCOVERY_RUN_STATUSES) & set(DISCOVERY_RUN_OUTCOMES) == set()
    completed = _run_row(status="COMPLETED", outcome="NO_EVIDENCE_FOUND")
    item = run_svc.row_to_item(completed)
    assert item.status == "COMPLETED"
    assert item.outcome == "NO_EVIDENCE_FOUND"
