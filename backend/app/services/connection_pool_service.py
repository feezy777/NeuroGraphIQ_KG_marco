"""Connection pool CRUD — cross-source connection accumulation for LLM extraction."""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import func, select, delete, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.connection_pool import ConnectionPool, ConnectionPoolMembership
from app.models.mirror_kg import MirrorRegionConnection


def _chunked(seq: list, size: int = 1000):
    """Yield fixed-size chunks to stay under the 65535 bind-parameter limit."""
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _scope_lock_pair(*parts: str) -> tuple[int, int]:
    raw = "|".join(str(p or "") for p in parts)
    digest = hashlib.md5(raw.encode("utf-8")).digest()
    k1 = int.from_bytes(digest[:8], "big") & 0x7FFFFFFF
    k2 = int.from_bytes(digest[8:16], "big") & 0x7FFFFFFF
    return k1, k2


async def _lock_pool_scope(
    session: AsyncSession,
    *,
    scope_atlas: str,
    scope_granularity: str,
) -> None:
    """Serialize pool mutations for a scope to prevent deadlocks/duplicate races."""
    k1, k2 = _scope_lock_pair("conn_pool", scope_atlas, scope_granularity)
    await session.execute(text("SELECT pg_advisory_xact_lock(:k1, :k2)"), {"k1": k1, "k2": k2})


async def _lock_pool_by_id(session: AsyncSession, pool_id: uuid.UUID) -> None:
    """Serialize mutations of a single pool (used by add/remove members)."""
    k1, k2 = _scope_lock_pair("conn_pool_pool", str(pool_id))
    await session.execute(text("SELECT pg_advisory_xact_lock(:k1, :k2)"), {"k1": k1, "k2": k2})


async def create_pool(
    session: AsyncSession,
    *,
    name: str | None,
    connection_ids: list[uuid.UUID],
    scope_atlas: str,
    scope_granularity: str,
    source: str = "manual",
    resource_id: uuid.UUID | None = None,
    batch_id: uuid.UUID | None = None,
) -> ConnectionPool:
    """Create a connection pool with initial members."""
    await _lock_pool_scope(session, scope_atlas=scope_atlas, scope_granularity=scope_granularity)
    deduped_ids = list(dict.fromkeys(connection_ids))
    q = select(MirrorRegionConnection).where(MirrorRegionConnection.id.in_(deduped_ids))
    result = await session.execute(q)
    connections = list(result.scalars().all())
    if not connections:
        raise ValueError("At least 1 valid connection ID is required")
    valid_ids = [c.id for c in connections]

    pool = ConnectionPool(
        name=name,
        scope_atlas=scope_atlas,
        scope_granularity=scope_granularity,
        source=source,
        resource_id=resource_id,
        batch_id=batch_id,
        connection_count=len(valid_ids),
    )
    session.add(pool)
    await session.flush()

    for cid in valid_ids:
        session.add(ConnectionPoolMembership(
            pool_id=pool.id,
            connection_id=cid,
            added_source=source,
        ))

    await session.flush()
    # Refresh server-generated columns (created_at/updated_at) together with
    # memberships; a memberships-only refresh leaves onupdate columns expired
    # and Pydantic validation raises MissingGreenlet.
    await session.refresh(pool, ["memberships", "created_at", "updated_at"])
    return pool


async def get_pool(
    session: AsyncSession,
    pool_id: uuid.UUID,
    *,
    include_memberships: bool = True,
) -> ConnectionPool | None:
    from sqlalchemy.orm import selectinload

    q = select(ConnectionPool).where(ConnectionPool.id == pool_id)
    if include_memberships:
        q = q.options(selectinload(ConnectionPool.memberships))
    result = await session.execute(q)
    return result.scalar_one_or_none()


async def list_pools(
    session: AsyncSession,
    *,
    scope_atlas: str | None = None,
    scope_granularity: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ConnectionPool], int]:
    from sqlalchemy.orm import selectinload

    base = select(ConnectionPool)
    if scope_atlas:
        base = base.where(ConnectionPool.scope_atlas == scope_atlas)
    if scope_granularity:
        base = base.where(ConnectionPool.scope_granularity == scope_granularity)

    count_q = select(func.count()).select_from(base.subquery())
    total = int((await session.execute(count_q)).scalar_one() or 0)

    q = (
        base.order_by(ConnectionPool.created_at.desc())
        .options(selectinload(ConnectionPool.memberships))
        .limit(limit)
        .offset(offset)
    )
    pools = list((await session.execute(q)).scalars().all())
    return pools, total


async def add_members(
    session: AsyncSession,
    pool_id: uuid.UUID,
    connection_ids: list[uuid.UUID],
) -> ConnectionPool:
    await _lock_pool_by_id(session, pool_id)
    pool = await get_pool(session, pool_id)
    if pool is None:
        raise KeyError(f"Pool {pool_id} not found")

    existing = {m.connection_id for m in pool.memberships}
    new_ids = [cid for cid in dict.fromkeys(connection_ids) if cid not in existing]
    if new_ids:
        # Idempotent, chunked insert: concurrent duplicate submissions must not
        # fail with UniqueViolation, and huge batches must stay under the
        # 65535 bind-parameter limit (4 params per row -> ~16k rows max).
        for chunk in _chunked(new_ids):
            stmt = pg_insert(ConnectionPoolMembership).values(
                [
                    {
                        "id": uuid.uuid4(),
                        "pool_id": pool_id,
                        "connection_id": cid,
                        "added_source": "manual",
                    }
                    for cid in chunk
                ]
            ).on_conflict_do_nothing(index_elements=["pool_id", "connection_id"])
            await session.execute(stmt)

    count_q = (
        select(func.count())
        .select_from(ConnectionPoolMembership)
        .where(ConnectionPoolMembership.pool_id == pool_id)
    )
    pool.connection_count = int((await session.execute(count_q)).scalar_one())
    await session.flush()
    await session.refresh(pool, ["memberships", "created_at", "updated_at"])
    return pool


async def remove_members(
    session: AsyncSession,
    pool_id: uuid.UUID,
    connection_ids: list[uuid.UUID],
) -> ConnectionPool:
    await _lock_pool_by_id(session, pool_id)
    pool = await get_pool(session, pool_id)
    if pool is None:
        raise KeyError(f"Pool {pool_id} not found")

    for chunk in _chunked(list(dict.fromkeys(connection_ids)), 5000):
        await session.execute(
            delete(ConnectionPoolMembership).where(
                ConnectionPoolMembership.pool_id == pool_id,
                ConnectionPoolMembership.connection_id.in_(chunk),
            )
        )
    remaining = {m.connection_id for m in pool.memberships} - set(connection_ids)
    pool.connection_count = len(remaining)
    await session.flush()
    await session.refresh(pool, ["memberships", "created_at", "updated_at"])
    return pool


async def replace_pool_for_scope(
    session: AsyncSession,
    *,
    name: str | None,
    connection_ids: list[uuid.UUID],
    scope_atlas: str,
    scope_granularity: str,
    source: str = "manual",
    resource_id: uuid.UUID | None = None,
    batch_id: uuid.UUID | None = None,
) -> ConnectionPool:
    """Idempotent: one active pool per scope with exactly the given members."""
    await _lock_pool_scope(session, scope_atlas=scope_atlas, scope_granularity=scope_granularity)
    deduped_ids = list(dict.fromkeys(connection_ids))
    q = select(MirrorRegionConnection).where(MirrorRegionConnection.id.in_(deduped_ids))
    result = await session.execute(q)
    connections = list(result.scalars().all())
    if not connections:
        raise ValueError("At least 1 valid connection ID is required")

    pools, _ = await list_pools(
        session,
        scope_atlas=scope_atlas,
        scope_granularity=scope_granularity,
        limit=100,
    )
    primary = pools[0] if pools else None
    for extra in pools[1:]:
        await delete_pool(session, extra.id)

    if primary is None:
        pool = ConnectionPool(
            name=name,
            scope_atlas=scope_atlas,
            scope_granularity=scope_granularity,
            source=source,
            resource_id=resource_id,
            batch_id=batch_id,
            connection_count=len(deduped_ids),
        )
        session.add(pool)
        await session.flush()
    else:
        pool = primary
        await session.execute(
            delete(ConnectionPoolMembership).where(
                ConnectionPoolMembership.pool_id == pool.id,
            )
        )
        pool.name = name or pool.name
        pool.resource_id = resource_id
        pool.batch_id = batch_id
        pool.source = source
        pool.connection_count = len(deduped_ids)

    for chunk in _chunked(deduped_ids):
        stmt = pg_insert(ConnectionPoolMembership).values(
            [
                {
                    "id": uuid.uuid4(),
                    "pool_id": pool.id,
                    "connection_id": cid,
                    "added_source": source,
                }
                for cid in chunk
            ]
        ).on_conflict_do_nothing(index_elements=["pool_id", "connection_id"])
        await session.execute(stmt)

    count_q = (
        select(func.count())
        .select_from(ConnectionPoolMembership)
        .where(ConnectionPoolMembership.pool_id == pool.id)
    )
    pool.connection_count = int((await session.execute(count_q)).scalar_one())

    await session.refresh(pool, ["memberships", "created_at", "updated_at"])
    return pool


async def delete_pool(session: AsyncSession, pool_id: uuid.UUID) -> bool:
    pool = await session.get(ConnectionPool, pool_id)
    if pool is None:
        return False
    await session.delete(pool)
    await session.flush()
    return True


async def resolve_pool_connection_ids(
    session: AsyncSession,
    pool_id: uuid.UUID,
) -> list[uuid.UUID]:
    """Resolve all connection IDs in a pool for extraction use."""
    q = select(ConnectionPoolMembership.connection_id).where(
        ConnectionPoolMembership.pool_id == pool_id
    )
    result = await session.execute(q)
    return [row[0] for row in result.all()]
