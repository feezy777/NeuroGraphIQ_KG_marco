"""Gate 7B Phase 0 tests — migration runner + bootstrap guard (no live DB required).

Covers the pure logic of the two Phase 0 scripts (filename regex, integer
ordering, duplicate-NNN rejection, checksum stability, DB-name constants, and
password redaction) plus the guard/config freeze to ``neurographiq_human_brain_v1``.
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
SCRIPTS = BACKEND / "scripts"


def _load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


gate7b = _load_script("gate7b_migrate", "gate7b_migrate.py")
bootstrap = _load_script("bootstrap_human_brain_v1", "bootstrap_human_brain_v1.py")


# --- filename regex ---------------------------------------------------------


def test_filename_re_accepts_gate7b_three_digit():
    m = gate7b.FILENAME_RE.match("gate7b_001_phase0_bootstrap.sql")
    assert m is not None
    assert m.group(1) == "001"


def test_filename_re_rejects_legacy_prefix():
    assert gate7b.FILENAME_RE.match("001_legacy.sql") is None
    assert gate7b.FILENAME_RE.match("20260520_coarse_grain_schema.sql") is None


def test_filename_re_rejects_non_numeric_or_short_nnn():
    assert gate7b.FILENAME_RE.match("gate7b_00a_x.sql") is None
    assert gate7b.FILENAME_RE.match("gate7b_1_x.sql") is None
    assert gate7b.FILENAME_RE.match("gate7b_0001_x.sql") is None


# --- discovery --------------------------------------------------------------


def test_discover_orders_by_integer_ignoring_legacy(tmp_path, monkeypatch):
    monkeypatch.setattr(gate7b, "MIGRATIONS_DIR", tmp_path)
    (tmp_path / "gate7b_010_b.sql").write_text("-- b", encoding="utf-8")
    (tmp_path / "gate7b_002_a.sql").write_text("-- a", encoding="utf-8")
    (tmp_path / "001_legacy.sql").write_text("-- legacy", encoding="utf-8")
    found = gate7b._discover()
    assert [nnn for nnn, _ in found] == [2, 10]


def test_discover_rejects_duplicate_nnn(tmp_path, monkeypatch):
    monkeypatch.setattr(gate7b, "MIGRATIONS_DIR", tmp_path)
    (tmp_path / "gate7b_001_a.sql").write_text("-- a", encoding="utf-8")
    (tmp_path / "gate7b_001_b.sql").write_text("-- b", encoding="utf-8")
    with pytest.raises(SystemExit):
        gate7b._discover()


def test_discover_empty_dir_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(gate7b, "MIGRATIONS_DIR", tmp_path)
    assert gate7b._discover() == []


# --- checksum ---------------------------------------------------------------


def test_sha256_normalizes_line_endings(tmp_path):
    f = tmp_path / "x.sql"
    f.write_bytes(b"SELECT 1;\r\n")
    # Checksum reflects SQL content, not platform line-ending style.
    assert gate7b._sha256(f) == hashlib.sha256(b"SELECT 1;\n").hexdigest()


# --- bootstrap constants + redaction ---------------------------------------


def test_bootstrap_target_constants_frozen():
    assert bootstrap.MAIN_DATABASE == "neurographiq_human_brain_v1"
    assert bootstrap.E2E_DATABASE == "neurographiq_human_brain_v1_e2e"
    assert bootstrap.LEGACY_DATABASE == "neurographiq_kg_v3_wb"


def test_redact_never_leaks_password():
    assert bootstrap._redact("postgres") == "<REDACTED>"
    assert bootstrap._redact("") == "<EMPTY>"
    assert bootstrap._redact(None) == "<EMPTY>"


# --- guard / config freeze --------------------------------------------------


def test_guard_freezes_human_brain_names():
    from app.database_guard import (
        E2E_DATABASE,
        MAIN_DATABASE,
        is_allowed_main_database,
        is_allowed_test_database,
    )

    assert MAIN_DATABASE == "neurographiq_human_brain_v1"
    assert E2E_DATABASE == "neurographiq_human_brain_v1_e2e"
    assert is_allowed_main_database(MAIN_DATABASE)
    assert is_allowed_test_database(E2E_DATABASE)


def test_guard_rejects_old_macro96_name():
    from app.database_guard import is_allowed_database, is_allowed_main_database

    # Old main name is no longer the main DB and lacks a test suffix.
    assert not is_allowed_main_database("neurographiq_macro96_v1")
    assert not is_allowed_database("neurographiq_macro96_v1")


def test_config_defaults_freeze_human_brain_name():
    from app.config import Settings

    settings = Settings(_env_file=None)
    assert settings.postgres_db == "neurographiq_human_brain_v1"
    assert "neurographiq_human_brain_v1" in settings.database_url
