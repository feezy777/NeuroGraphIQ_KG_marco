"""Canonical Circuit API (CI1.1: Circuit Entity + members + integrity)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.canonical_circuit import (
    CanonicalCircuitConnectionCreate,
    CanonicalCircuitConnectionRead,
    CanonicalCircuitCreate,
    CanonicalCircuitFunctionCreate,
    CanonicalCircuitFunctionRead,
    CanonicalCircuitMergeRequest,
    CanonicalCircuitRead,
    CanonicalCircuitRegionCreate,
    CanonicalCircuitRegionRead,
)
from app.services import canonical_circuit_service as ccs

router = APIRouter()


def _http(exc: ccs.CanonicalCircuitError) -> HTTPException:
    return HTTPException(
        status_code=400, detail={"code": "CANONICAL_CIRCUIT_ERROR", "message": str(exc)}
    )


@router.post("", response_model=CanonicalCircuitRead)
async def create_canonical_circuit(
    body: CanonicalCircuitCreate,
    session: AsyncSession = Depends(get_db),
):
    try:
        circuit = await ccs.create_canonical_circuit(session, body)
    except ccs.CanonicalCircuitError as exc:
        raise _http(exc)
    await session.commit()
    await session.refresh(circuit)
    return circuit


@router.get("", response_model=list[CanonicalCircuitRead])
async def list_canonical_circuits(
    circuit_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    species: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    return await ccs.list_canonical_circuits(
        session, circuit_type=circuit_type, status=status, species=species
    )


@router.get("/integrity")
async def canonical_circuit_integrity(session: AsyncSession = Depends(get_db)):
    return await ccs.check_canonical_circuit_integrity(session)


@router.get("/graph-integrity")
async def canonical_circuit_graph_integrity(session: AsyncSession = Depends(get_db)):
    """Circuit-Connection-Region closure check (CI1.3-3)."""
    return await ccs.check_circuit_graph_integrity(session)


@router.post("/merge", response_model=CanonicalCircuitRead)
async def merge_canonical_circuits(
    body: CanonicalCircuitMergeRequest,
    session: AsyncSession = Depends(get_db),
):
    try:
        circuit = await ccs.merge_circuits(
            session,
            deprecated_circuit_id=body.deprecated_circuit_id,
            active_circuit_id=body.active_circuit_id,
        )
    except ccs.CanonicalCircuitError as exc:
        raise _http(exc)
    await session.commit()
    await session.refresh(circuit)
    return circuit


@router.get("/{circuit_id}", response_model=CanonicalCircuitRead)
async def get_canonical_circuit(circuit_id: uuid.UUID, session: AsyncSession = Depends(get_db)):
    circuit = await ccs.get_canonical_circuit(session, circuit_id)
    if circuit is None:
        raise HTTPException(status_code=404, detail="canonical circuit not found")
    return circuit


@router.post("/{circuit_id}/regions", response_model=CanonicalCircuitRegionRead)
async def add_circuit_region_member(
    circuit_id: uuid.UUID,
    body: CanonicalCircuitRegionCreate,
    session: AsyncSession = Depends(get_db),
):
    try:
        member = await ccs.add_circuit_region(session, circuit_id, body)
    except ccs.CanonicalCircuitError as exc:
        raise _http(exc)
    await session.commit()
    await session.refresh(member)
    return member


@router.get("/{circuit_id}/regions", response_model=list[CanonicalCircuitRegionRead])
async def list_circuit_region_members(
    circuit_id: uuid.UUID, session: AsyncSession = Depends(get_db)
):
    try:
        return await ccs.list_circuit_regions(session, circuit_id)
    except ccs.CanonicalCircuitError as exc:
        raise _http(exc)


@router.post("/{circuit_id}/connections", response_model=CanonicalCircuitConnectionRead)
async def add_circuit_connection_member(
    circuit_id: uuid.UUID,
    body: CanonicalCircuitConnectionCreate,
    session: AsyncSession = Depends(get_db),
):
    try:
        member = await ccs.add_circuit_connection(session, circuit_id, body)
    except ccs.CanonicalCircuitError as exc:
        raise _http(exc)
    await session.commit()
    await session.refresh(member)
    return member


@router.get("/{circuit_id}/connections", response_model=list[CanonicalCircuitConnectionRead])
async def list_circuit_connection_members(
    circuit_id: uuid.UUID, session: AsyncSession = Depends(get_db)
):
    try:
        return await ccs.list_circuit_connections(session, circuit_id)
    except ccs.CanonicalCircuitError as exc:
        raise _http(exc)


@router.post("/{circuit_id}/functions", response_model=CanonicalCircuitFunctionRead)
async def add_circuit_function_member(
    circuit_id: uuid.UUID,
    body: CanonicalCircuitFunctionCreate,
    session: AsyncSession = Depends(get_db),
):
    try:
        member = await ccs.add_circuit_function(session, circuit_id, body)
    except ccs.CanonicalCircuitError as exc:
        raise _http(exc)
    await session.commit()
    await session.refresh(member)
    return member


@router.get("/{circuit_id}/functions", response_model=list[CanonicalCircuitFunctionRead])
async def list_circuit_function_members(
    circuit_id: uuid.UUID, session: AsyncSession = Depends(get_db)
):
    try:
        return await ccs.list_circuit_functions(session, circuit_id)
    except ccs.CanonicalCircuitError as exc:
        raise _http(exc)
