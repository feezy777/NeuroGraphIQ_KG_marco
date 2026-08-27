"""Macro96 database safety guard.

Single source of truth for the database names the Macro96 runtime may use:

- main development database: ``neurographiq_macro96_v1``
- isolated test database(s):  ``neurographiq_macro96_v1_e2e``
  (extendable via the ``TEST_DB_SUFFIXES`` env var, same convention as tests/conftest.py)

Legacy NeuroGraphIQ V3 database names (``neurographiq_kg_v3*``, ``NeuroGraphIQ_KG*``,
``NeuroGraphIQ_Workbench``) are never allowed — not as defaults, not as fallbacks,
not via runtime switching.
"""

from __future__ import annotations

import os

MAIN_DATABASE = "neurographiq_macro96_v1"
E2E_DATABASE = "neurographiq_macro96_v1_e2e"

# Legacy V3 family that must never be touched by the Macro96 runtime.
FORBIDDEN_DB_PREFIXES = ("neurographiq_kg_v3", "NeuroGraphIQ_KG", "NeuroGraphIQ_Workbench")


class DatabaseGuardError(Exception):
    """Raised when a database name is not allowed by the Macro96 guard."""


def test_database_suffixes() -> tuple[str, ...]:
    """Test-database suffixes: TEST_DB_SUFFIXES env (comma-separated) or ``_e2e``."""
    raw = os.environ.get("TEST_DB_SUFFIXES", "").strip()
    suffixes = tuple(s.strip() for s in raw.split(",") if s.strip()) if raw else ()
    return suffixes or ("_e2e",)


def is_forbidden_legacy_database(name: str) -> bool:
    return name.startswith(FORBIDDEN_DB_PREFIXES)


def is_allowed_main_database(name: str) -> bool:
    return name == MAIN_DATABASE and not is_forbidden_legacy_database(name)


def is_allowed_test_database(name: str) -> bool:
    if is_forbidden_legacy_database(name):
        return False
    return name == E2E_DATABASE or name.endswith(test_database_suffixes())


def is_allowed_database(name: str) -> bool:
    """Any database name the Macro96 runtime may connect to (main or isolated test)."""
    return is_allowed_main_database(name) or is_allowed_test_database(name)


def assert_allowed_database(name: str) -> None:
    """Raise DatabaseGuardError unless ``name`` is an allowed Macro96 database."""
    if is_allowed_database(name):
        return
    if is_forbidden_legacy_database(name):
        raise DatabaseGuardError(
            f"database '{name}' is a legacy NeuroGraphIQ V3 database; the Macro96 runtime "
            f"only allows '{MAIN_DATABASE}' (main) or '{E2E_DATABASE}' (test)."
        )
    raise DatabaseGuardError(
        f"database '{name}' is not an allowed Macro96 database "
        f"(allowed: '{MAIN_DATABASE}', '{E2E_DATABASE}')."
    )
