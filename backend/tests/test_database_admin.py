"""Database admin tests (no PostgreSQL required for pure helpers)."""

from __future__ import annotations

import json

import pytest

from app.schemas.database_admin import DatabaseSchemaStatus
from app.services import database_admin_service


def test_parse_database_name_from_async_url():
    url = "postgresql+psycopg_async://postgres:secret@127.0.0.1:5432/neurographiq_human_brain_v1_e2e"
    assert database_admin_service.parse_database_name(url) == "neurographiq_human_brain_v1_e2e"


def test_resolve_active_database_ignores_runtime_override(tmp_path, monkeypatch):
    from app.database_guard import MAIN_DATABASE, E2E_DATABASE

    runtime_path = tmp_path / "database.local.json"
    runtime_path.write_text(
        json.dumps({"postgres_db": "neurographiq_kg_v3_mvp1_e2e"}), encoding="utf-8"
    )
    monkeypatch.setattr(database_admin_service, "RUNTIME_DATABASE_PATH", runtime_path)

    name = database_admin_service.resolve_active_database_name()
    # Runtime override file must NOT control the main connection.
    assert name != "neurographiq_kg_v3_mvp1_e2e"
    assert name in (MAIN_DATABASE, E2E_DATABASE)
    # The stale override is still surfaced for diagnostics.
    assert database_admin_service.get_ignored_runtime_override() == "neurographiq_kg_v3_mvp1_e2e"


def test_validate_rejects_invalid_database_name():
    import asyncio

    result = asyncio.run(database_admin_service.validate_database_schema("bad-name!"))
    assert result["schema_status"] == DatabaseSchemaStatus.unreachable
    assert "invalid database name" in result["notes"][0]


def test_mvp1_required_tables_include_core_tables():
    tables = database_admin_service.MVP1_REQUIRED_TABLES
    assert "atlas_resources" in tables
    assert "final_brain_regions" in tables
    assert "candidate_brain_regions" in tables


def test_switch_is_disabled_for_legacy_database():
    import asyncio

    with pytest.raises(database_admin_service.DatabaseSwitchDisabledError) as exc:
        asyncio.run(database_admin_service.switch_database("neurographiq_kg_v3_wb"))

    assert exc.value.database == "neurographiq_kg_v3_wb"
    assert "disabled" in str(exc.value)


def test_switch_rejects_invalid_database_name():
    import asyncio

    with pytest.raises(database_admin_service.DatabaseSwitchNotAllowedError):
        asyncio.run(database_admin_service.switch_database("bad-name!"))


def test_database_switch_not_allowed_error_fields():
    err = database_admin_service.DatabaseSwitchNotAllowedError(
        "db_x", DatabaseSchemaStatus.partial, "not ready"
    )
    assert err.database == "db_x"
    assert "not ready" in str(err)
