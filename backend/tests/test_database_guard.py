"""Human-brain database boundary tests (no live PostgreSQL connection required)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.database_guard import (
    E2E_DATABASE,
    MAIN_DATABASE,
    DatabaseGuardError,
    assert_allowed_database,
    is_allowed_database,
    is_allowed_main_database,
    is_allowed_test_database,
)

LEGACY_V3_NAMES = [
    "neurographiq_kg_v3_mvp1_e2e",
    "neurographiq_kg_v3_candidate",
    "neurographiq_kg_v3_wb",
    "NeuroGraphIQ_KG_V3",
    "NeuroGraphIQ_KG_Candidate",
    "NeuroGraphIQ_Workbench",
]


def test_config_defaults_freeze_human_brain_names():
    settings = Settings(_env_file=None)
    assert settings.postgres_db == MAIN_DATABASE
    assert MAIN_DATABASE in settings.database_url


def test_guard_allows_human_brain_names():
    assert is_allowed_main_database(MAIN_DATABASE)
    assert is_allowed_test_database(E2E_DATABASE)
    assert is_allowed_database(MAIN_DATABASE)
    assert is_allowed_database(E2E_DATABASE)


def test_guard_rejects_all_legacy_v3_names():
    for name in LEGACY_V3_NAMES:
        assert not is_allowed_database(name), name
        with pytest.raises(DatabaseGuardError):
            assert_allowed_database(name)


def test_guard_rejects_unknown_names():
    with pytest.raises(DatabaseGuardError):
        assert_allowed_database("postgres")
    with pytest.raises(DatabaseGuardError):
        assert_allowed_database("some_random_db")


def test_guard_test_suffixes_env_extension(monkeypatch):
    monkeypatch.setenv("TEST_DB_SUFFIXES", "_e2e,_test")
    assert is_allowed_test_database("neurographiq_human_brain_v1_test")
    # Legacy names stay forbidden even when they match an allowed suffix.
    assert not is_allowed_test_database("neurographiq_kg_v3_mvp1_e2e")


def test_engine_bound_to_datbase_url_database():
    """The engine bootstraps from DATABASE_URL only (guard-enforced)."""
    import app.database as db_module
    from app.config import get_settings
    from app.services.database_admin_service import parse_database_name

    settings = get_settings()
    expected = parse_database_name(settings.database_url) or settings.postgres_db
    assert db_module._engine is not None
    assert db_module._engine.url.database == expected


def test_switch_disabled_even_for_allowed_database():
    import asyncio

    from app.services import database_admin_service

    with pytest.raises(database_admin_service.DatabaseSwitchDisabledError):
        asyncio.run(database_admin_service.switch_database(MAIN_DATABASE))


def test_switch_endpoint_returns_disabled_error():
    from app.routers import database_admin as router_module

    app = FastAPI()
    app.include_router(router_module.router)
    client = TestClient(app)

    resp = client.post("/switch", json={"database": "neurographiq_kg_v3_wb"})
    assert resp.status_code == 403
    detail = resp.json()["detail"]
    assert detail["code"] == "DATABASE_SWITCH_DISABLED"
    assert detail["database"] == "neurographiq_kg_v3_wb"


def test_switch_endpoint_invalid_name_returns_409():
    from app.routers import database_admin as router_module

    app = FastAPI()
    app.include_router(router_module.router)
    client = TestClient(app)

    resp = client.post("/switch", json={"database": "bad-name!"})
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["code"] == "DATABASE_SWITCH_NOT_ALLOWED"
