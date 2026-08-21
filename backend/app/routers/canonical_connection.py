"""Canonical Connection API (CN1.2-1: schema/model/service foundation)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.canonical_connection import CanonicalConnectionCreate, CanonicalConnectionRead
from app.services import canonical_connection_service as ccs

router = APIRouter()


def _http(exc: ccs.CanonicalConnectionError) -> HTTPException:
    return HTTPException(
        status_code=400, detail={"code": "CANONICAL_CONNECTION_ERROR", "message": str(exc)}
    )


@router.post("", response_model=CanonicalConnectionRead)
async def create_canonical_connection(
    body: CanonicalConnectionCreate,
    session: AsyncSession = Depends(get_db),
):
    try:
        connection = await ccs.create_canonical_connection(session, body)
    except ccs.CanonicalConnectionError as exc:
        raise _http(exc)
    await session.commit()
    await session.refresh(connection)
    return connection


@router.get("", response_model=list[CanonicalConnectionRead])
async def list_canonical_connections(
    connection_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    species: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    return await ccs.list_canonical_connections(
        session, connection_type=connection_type, status=status, species=species
    )


@router.get("/integrity")
async def canonical_connection_integrity(session: AsyncSession = Depends(get_db)):
    return await ccs.check_canonical_connection_integrity(session)


@router.get("/{connection_id}", response_model=CanonicalConnectionRead)
async def get_canonical_connection(connection_id: uuid.UUID, session: AsyncSession = Depends(get_db)):
    connection = await ccs.get_canonical_connection(session, connection_id)
    if connection is None:
        raise HTTPException(status_code=404, detail="canonical connection not found")
    return connection
