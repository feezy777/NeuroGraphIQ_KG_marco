"""Minimal async database access for Resource Registry (MVP 1).

Macro96 boundary: the main database comes ONLY from settings DATABASE_URL
(.env / env vars). The legacy runtime JSON override and runtime switching
are disabled — see app/database_guard.py and database_admin_service.py.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

_engine: AsyncEngine | None = None
AsyncSessionLocal: async_sessionmaker[AsyncSession] | None = None
_engine_lock = asyncio.Lock()


def _create_engine_and_factory(database_url: str) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    settings = get_settings()
    engine = create_async_engine(
        database_url,
        echo=settings.db_echo,
        pool_pre_ping=True,
        pool_size=20,
        max_overflow=10,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return engine, factory


def _bootstrap_engine() -> None:
    global _engine, AsyncSessionLocal
    from app.database_guard import assert_allowed_database
    from app.services.database_admin_service import parse_database_name

    url = get_settings().database_url
    assert_allowed_database(parse_database_name(url))
    _engine, AsyncSessionLocal = _create_engine_and_factory(url)


_bootstrap_engine()


async def reload_database_engine(database: str) -> str:
    """Dispose current engine and bind to a new database (allowed Macro96 names only).

    Not exposed as a runtime switch; kept for tooling that must rebind the
    engine to the isolated test database.
    """
    global _engine, AsyncSessionLocal
    from app.database_guard import assert_allowed_database

    assert_allowed_database(database)
    settings = get_settings()
    new_url = settings.build_database_url(database=database)
    async with _engine_lock:
        if _engine is not None:
            await _engine.dispose()
        _engine, AsyncSessionLocal = _create_engine_and_factory(new_url)
    return new_url


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    if AsyncSessionLocal is None:
        _bootstrap_engine()
    async with AsyncSessionLocal() as session:  # type: ignore[misc]
        yield session
