"""Shared pytest fixtures (test-environment compatibility for the ontology cache)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.services import function_term_service as fts
from app.services import llm_function_extraction_service as fes
from app.services import llm_projection_function_extraction_service as pfes
from app.services import mirror_macro_clinical_service as mmcs
from app.services import ontology_vocab_cache as vc


def pytest_configure(config):
    """Register custom markers (no pytest.ini in this repo)."""
    config.addinivalue_line(
        "markers",
        "function_term_real: exercise the real P1.3 function-term resolver/anchoring "
        "(skips the autouse AsyncMock of function_term_service paths)",
    )

# 数据库写测试硬门禁(S7B 安全门禁 + S8 修订 + human-brain 修订):
# - 真实连接后执行 SELECT current_database(),只允许 human-brain 隔离测试库
#   (默认 neurographiq_human_brain_v1_e2e,可用 TEST_DB_SUFFIXES 环境变量以逗号分隔扩展后缀,
#   如 "_e2e,_test");旧 V3 库名(neurographiq_kg_v3* 等)一律拒绝;
# - 连接成功但库名不满足时立即终止整个测试会话(returncode 非 0),不能仅 warning;
# - 连接失败(无数据库环境)时仅警告放行:纯单元测试不依赖真实数据库,任何 DB 写测试会自然失败;
# - 不能只依赖 .env 字符串判断。


@pytest.fixture(scope="session", autouse=True)
def _guard_e2e_test_database():
    from sqlalchemy import text

    from app.database import AsyncSessionLocal
    from app.database_guard import (
        E2E_DATABASE,
        FORBIDDEN_DB_PREFIXES,
        is_allowed_test_database,
    )

    async def _check() -> None:
        async with AsyncSessionLocal() as s:
            name = str((await s.execute(text("SELECT current_database()"))).scalar_one())
            if not is_allowed_test_database(name):
                if name.startswith(FORBIDDEN_DB_PREFIXES):
                    reason = (
                        f"connected database '{name}' is a legacy NeuroGraphIQ V3 database; "
                        "the human-brain test guard refuses to touch it"
                    )
                else:
                    reason = (
                        f"connected database '{name}' is not an isolated human-brain test "
                        f"database (must be '{E2E_DATABASE}' or end with a TEST_DB_SUFFIXES "
                        "suffix); refusing to run tests"
                    )
                pytest.exit(f"DB write guard: {reason}.", returncode=3)

    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_check())
        finally:
            loop.close()
    except Exception as exc:  # 连接失败:无数据库环境 → 单元测试放行,写测试自然失败
        import warnings

        warnings.warn(
            f"DB write guard: cannot verify test database isolation "
            f"({type(exc).__name__}: {exc}); database-dependent tests will fail on their own.",
            RuntimeWarning,
            stacklevel=2,
        )
    yield


@pytest.fixture(autouse=True)
def _seed_ontology_vocab_cache(monkeypatch, request):
    """Seed the in-process vocabulary cache from legacy defaults for tests.

    Production extraction paths refresh the cache from the registry at run
    start; this fixture only keeps deterministic unit tests green without a
    database.

    P1.3: extraction/create paths now anchor via the unified
    function_term_service. Unit tests that exercise those paths without a DB
    get AsyncMocks; tests marked ``function_term_real`` use the real resolver
    and anchoring (DB-backed P1.3 tests).
    """
    vc.seed_vocab_cache("category", fes.DEFAULT_ALLOWED_FUNCTION_CATEGORIES)
    vc.seed_vocab_cache("relation_type", fes.DEFAULT_ALLOWED_RELATION_TYPES)
    # Unit tests run without a live DB; extraction services refresh the cache
    # from the registry at run start in production.
    monkeypatch.setattr(fes, "refresh_vocab_cache", AsyncMock())
    monkeypatch.setattr(pfes, "refresh_vocab_cache", AsyncMock())
    if request.node.get_closest_marker("function_term_real") is None:
        unresolved = fts.FunctionTermResolution(
            term_id=None, state=fts.STATE_UNRESOLVED, path=["mocked"], is_function_term=True
        )
        for mod in (fts, mmcs):
            monkeypatch.setattr(mod, "resolve_or_propose_function_term", AsyncMock(return_value=unresolved))
            monkeypatch.setattr(mod, "anchor_function_relation", AsyncMock())
        # P1.6: create paths also trigger incremental projection — stub it for
        # unit tests without a DB (function_term_real tests use the real one).
        import app.services.function_triple_projection_service as ftps

        monkeypatch.setattr(ftps, "reconcile_function_subject", AsyncMock())
        monkeypatch.setattr(ftps, "project_changed_function_relations", AsyncMock(return_value=[]))
        monkeypatch.setattr(ftps, "refresh_function_term_projection", AsyncMock(return_value=[]))
    yield
    vc.invalidate_vocab_cache()
