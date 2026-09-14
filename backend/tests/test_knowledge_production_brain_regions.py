"""Phase 1 Knowledge Production — BrainRegion seed read-only API tests.

These tests do not require a live database: the FastAPI dependency
``get_db`` is overridden with a recording stub session, so the router,
validation and DTO contract are exercised for real while SQL execution is
simulated. Query *construction* is additionally unit-tested as a pure
function.

A live-database smoke test is included but skipped unless
``KP_LIVE_DB_TEST=1``, so the suite never touches the production authority
database by default.
"""
from __future__ import annotations

import os
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.schemas.knowledge_production import GATE7B_GRANULARITY_LEVELS
from app.services import knowledge_production_brain_region_service as svc

ENDPOINT = "/api/knowledge-production/brain-regions"

_ROW_KEYS = (
    "entity_pk",
    "entity_id",
    "name_en",
    "name_zh",
    "abbreviation",
    "granularity_level",
    "region_category",
    "hemisphere",
    "species_taxon_id",
    "record_status",
    "review_status",
    "atlas_names",
)


def _row(n: int, granularity: str = "G3_MESO_FINE") -> dict[str, Any]:
    return {
        "entity_pk": n,
        "entity_id": f"NGIQ-BR-{n:08d}",
        "name_en": f"Region {n}",
        "name_zh": f"区域 {n}",
        "abbreviation": None,
        "granularity_level": granularity,
        "region_category": "cortical_region",
        "hemisphere": "left",
        "species_taxon_id": "9606",
        "record_status": "active",
        "review_status": "approved",
        "atlas_names": ["Human Brainnetome Atlas"],
    }


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]], scalar: int):
        self._rows = rows
        self._scalar = scalar

    def scalar_one(self) -> int:
        return self._scalar

    def mappings(self) -> "_FakeResult":
        return self

    def all(self) -> list[dict[str, Any]]:
        return self._rows

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class _RecordingSession:
    """Records every statement; returns COUNT for count queries, rows otherwise."""

    def __init__(self, total: int = 770, rows: list[dict[str, Any]] | None = None):
        self.total = total
        self.rows = rows if rows is not None else [_row(1), _row(2)]
        self.mapping_rows: list[dict[str, Any]] = [
            {
                "external_region_id": "NGIQ-XREG-00000001",
                "mapping_type": "exact",
                "review_status": "approved",
            }
        ]
        self.summary_rows: list[dict[str, Any]] = [
            {"granularity_level": "G1_MACRO", "n": 84},
            {"granularity_level": "G3_MESO_FINE", "n": 246},
            {"granularity_level": "G4_MICROSTRUCTURAL_FINE", "n": 440},
        ]
        self.statements: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> _FakeResult:
        sql = str(stmt)
        self.statements.append((sql, dict(params or {})))
        if "GROUP BY" in sql:
            return _FakeResult(self.summary_rows, 0)
        if "COUNT(*)" in sql:
            return _FakeResult([], self.total)
        if "mapping_type" in sql:
            return _FakeResult(self.mapping_rows, self.total)
        return _FakeResult(self.rows, self.total)

    @property
    def sql_text(self) -> str:
        return " ".join(s for s, _ in self.statements).upper()


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


# ---- 1. list returns items + total ----
def test_list_returns_items_and_total(client, session):
    res = client.get(ENDPOINT)
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"items", "total"}
    assert body["total"] == 770
    assert len(body["items"]) == 2
    item = body["items"][0]
    assert item["entity_id"] == "NGIQ-BR-00000001"
    assert item["granularity_level"] == "G3_MESO_FINE"
    assert item["atlas_names"] == ["Human Brainnetome Atlas"]
    # only real Gate7B fields are exposed
    assert set(item) == set(_ROW_KEYS)


# ---- 2. granularity filter works for all four Gate7B levels ----
@pytest.mark.parametrize("level", GATE7B_GRANULARITY_LEVELS)
def test_granularity_filter(client, session, level):
    res = client.get(ENDPOINT, params={"granularity_level": level})
    assert res.status_code == 200
    assert any(p.get("granularity_level") == level for _, p in session.statements)
    assert "B.GRANULARITY_LEVEL = :GRANULARITY_LEVEL" in session.sql_text


# ---- 3. search works ----
def test_search(client, session):
    res = client.get(ENDPOINT, params={"search": "Thalamus"})
    assert res.status_code == 200
    assert any(p.get("search_like") == "%Thalamus%" for _, p in session.statements)
    assert "ILIKE :SEARCH_LIKE" in session.sql_text


def test_atlas_filter(client, session):
    res = client.get(ENDPOINT, params={"source_atlas": "Julich"})
    assert res.status_code == 200
    assert any(p.get("atlas_like") == "%Julich%" for _, p in session.statements)


# ---- 4. pagination works ----
def test_pagination_passes_limit_and_offset(client, session):
    res = client.get(ENDPOINT, params={"limit": 25, "offset": 50})
    assert res.status_code == 200
    assert any(p.get("limit") == 25 and p.get("offset") == 50 for _, p in session.statements)
    assert "LIMIT :LIMIT OFFSET :OFFSET" in session.sql_text


def test_pagination_limit_is_clamped():
    assert svc.normalize_limit(None) == svc._DEFAULT_LIMIT
    assert svc.normalize_limit(0) == svc._DEFAULT_LIMIT
    assert svc.normalize_limit(10_000) == svc._MAX_LIMIT
    assert svc.normalize_offset(-5) == 0
    assert svc.normalize_offset(None) == 0


def test_limit_above_max_rejected_by_validation(client):
    res = client.get(ENDPOINT, params={"limit": svc._MAX_LIMIT + 1})
    assert res.status_code == 422


# ---- 5. endpoint performs no writes ----
def test_no_write_statements_issued(client, session):
    client.get(ENDPOINT)
    client.get(ENDPOINT, params={"search": "x", "granularity_level": "G1_MACRO"})
    for sql, _ in session.statements:
        head = sql.lstrip().upper()
        assert head.startswith("SELECT"), f"non-SELECT statement issued: {sql[:80]}"
        for verb in ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ", "TRUNCATE"):
            assert verb not in sql.upper(), f"{verb.strip()} found in: {sql[:80]}"


def test_module_source_contains_no_write_sql():
    import inspect

    src = inspect.getsource(svc)
    for verb in ("INSERT INTO", "UPDATE ", "DELETE FROM", "DROP ", "ALTER "):
        assert verb not in src.upper().replace("_", " ").replace("INSERT INTO", "INSERT INTO"), (
            f"{verb} found in service source"
        )


def test_no_legacy_table_references():
    import inspect

    src = inspect.getsource(svc) + inspect.getsource(__import__(
        "app.routers.knowledge_production", fromlist=["x"]
    ))
    for legacy in ("candidate_brain_regions", "mirror_region", "final_brain_regions", "mirror_kg_triples"):
        assert legacy not in src, f"legacy table referenced: {legacy}"


# ---- 6. invalid granularity is rejected cleanly ----
def test_invalid_granularity_rejected(client, session):
    res = client.get(ENDPOINT, params={"granularity_level": "macro"})
    assert res.status_code == 422
    assert session.statements == [], "invalid input must not reach the database"


# ---- summary endpoint (Phase 1B Production Index) ----
def test_summary_returns_total_and_all_granularities(client, session):
    res = client.get(f"{ENDPOINT}/summary")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"total", "by_granularity"}
    assert body["total"] == 84 + 246 + 440
    # every Gate7B level is present, missing ones reported as 0 (never omitted)
    assert set(body["by_granularity"]) == set(GATE7B_GRANULARITY_LEVELS)
    assert body["by_granularity"]["G2_MESO_ANATOMICAL"] == 0
    assert body["by_granularity"]["G4_MICROSTRUCTURAL_FINE"] == 440
    # one aggregate query, not one request per granularity
    assert len(session.statements) == 1


def test_summary_route_is_not_swallowed_by_identifier(client, session):
    """/brain-regions/summary must resolve to the summary route."""
    res = client.get(f"{ENDPOINT}/summary")
    assert res.status_code == 200
    assert "total" in res.json()


# ---- detail endpoint ----
def test_detail_returns_entity(client, session):
    session.rows = [
        {
            **_row(1),
            "definition_en": None,
            "parent_region_pk": None,
            "hierarchy_depth": 0,
        }
    ]
    res = client.get(f"{ENDPOINT}/NGIQ-BR-00000001")
    assert res.status_code == 200
    body = res.json()
    assert body["entity_id"] == "NGIQ-BR-00000001"
    assert body["mapping_types"] == ["exact"]
    assert body["external_region_ids"] == ["NGIQ-XREG-00000001"]


def test_detail_404_when_absent(client, session):
    session.rows = []
    res = client.get(f"{ENDPOINT}/NGIQ-BR-99999999")
    assert res.status_code == 404


# ---- pure helper ----
def test_build_filters_is_pure_and_composable():
    where, params = svc.build_filters()
    assert where == "" and params == {}

    where, params = svc.build_filters(granularity_level="G4_MICROSTRUCTURAL_FINE")
    assert "granularity_level = :granularity_level" in where
    assert params == {"granularity_level": "G4_MICROSTRUCTURAL_FINE"}

    where, params = svc.build_filters(search="  Insula  ", source_atlas="Brainnetome")
    assert params["search_like"] == "%Insula%"  # trimmed
    assert params["atlas_like"] == "%Brainnetome%"
    assert where.startswith(" WHERE ")
    assert "b.granularity_level" not in where, "unused filter must not leak into the clause"


def test_row_to_item_maps_only_real_fields():
    item = svc.row_to_item({**_row(7), "atlas_names": None})
    assert item.entity_id == "NGIQ-BR-00000007"
    assert item.atlas_names == []


# ---- optional live smoke test (never runs against production by default) ----
@pytest.mark.skipif(
    os.environ.get("KP_LIVE_DB_TEST") != "1",
    reason="live Gate7B smoke test disabled (set KP_LIVE_DB_TEST=1 to enable)",
)
def test_live_database_smoke():
    import asyncio

    from app.database import AsyncSessionLocal

    async def _run():
        async with AsyncSessionLocal() as s:
            resp = await svc.list_seed_regions(s, limit=1)
            assert resp.total > 0
            assert resp.items[0].entity_id.startswith("NGIQ-BR-")

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(_run())
