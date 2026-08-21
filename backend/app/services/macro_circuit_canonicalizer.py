"""Macro Circuit Canonicalizer (CI1.2-B).

Batch conversion of aligned macro mirror circuits (CI1.2-A frozen mapping
rules) into canonical_circuits entities — status ``proposed``, full member
binding (regions / connections / functions), full provenance.

Hard boundaries: never modifies mirror_region_circuits, mirror_circuit_*,
triples, or promotion tables. Only the aligned circuits from the CI1.2-A plan
are written; unresolved and rejected circuits are skipped and reported.

Idempotency: a mirror circuit is written exactly once — identity is
``provenance_json.source_mirror_circuit_id``; a second run inserts 0 rows.

Connection members: only projections that already resolve to a
canonical_connections row are bound. A member that fails at write time is
recorded in ``unresolved_connections`` and never fails the whole circuit.

Member folding (laterality collapse): the canonical layer is concept-neutral,
so two mirror members of one circuit can ground to the same canonical region
(left/right homologues), or resolve to the same canonical connection / term.
Member tables are UNIQUE(circuit_id, member_id) — write() folds such
duplicates onto the first member (regions ordered by order_index, others by
mirror id) and records the folded mirror ids in the kept member's provenance
(``merged_mirror_region_ids`` / ``merged_mirror_connection_ids`` /
``merged_mirror_function_ids``). Circuit provenance still lists every source
mirror id. Folded counts are reported as ``folded_*`` in the write result.

Pipeline: fetch_candidates (read-only) -> build_plan (aligned subset) ->
dry_run (predicts without writing) -> write (idempotent insert, caller
commits) -> integrity_check (check_canonical_circuit_integrity; the caller
commits only when it passes).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.canonical_circuit import (
    CanonicalCircuitConnectionCreate,
    CanonicalCircuitCreate,
    CanonicalCircuitFunctionCreate,
    CanonicalCircuitRegionCreate,
)
from app.services import canonical_circuit_service as cis
from app.services import circuit_mapping_service as cms

_PROVENANCE_KEYS = {
    "source_mirror_circuit_id",
    "source_region_ids",
    "source_connection_ids",
    "source_function_ids",
    "mapping_version",
    "mapping_confidence",
}

_CREATED_BY = "macro96_canonical_circuit_v1"


class MacroCircuitCanonicalizerError(ValueError):
    """Domain error for Macro circuit canonicalization."""


# --------------------------------------------------------------------------- #
# Fetch (read-only)
# --------------------------------------------------------------------------- #


async def fetch_candidates(session: AsyncSession) -> dict[str, Any]:
    """Run the CI1.2-A read-only plan over macro mirror circuits.

    Returns the full classification: ``plans`` (aligned), ``unresolved_circuits``,
    ``rejected_circuits``, plus member-level stats. Writes nothing.
    """
    return await cms.plan_macro_circuit_canonicalization(session)


# --------------------------------------------------------------------------- #
# Plan / dry-run
# --------------------------------------------------------------------------- #


async def build_plan(session: AsyncSession) -> dict[str, Any]:
    """Classify macro mirror circuits and return the aligned write plan.

    Only ``plans`` items are write targets; unresolved and rejected circuits
    are skipped and reported (with reasons) — never written.
    """
    plan = await fetch_candidates(session)
    return {
        "stats": plan["stats"],
        "plans": plan["plans"],
        "unresolved_circuits": plan["unresolved_circuits"],
        "rejected_circuits": plan["rejected_circuits"],
    }


async def dry_run(session: AsyncSession) -> dict[str, Any]:
    """Predict the batch without writing anything (deterministic)."""
    plan = await build_plan(session)
    return {"dry_run": True, **plan}


# --------------------------------------------------------------------------- #
# Write
# --------------------------------------------------------------------------- #


async def _load_existing_mirror_ids(session: AsyncSession) -> set[str]:
    rows = (
        await session.execute(
            text(
                "SELECT provenance_json->>'source_mirror_circuit_id' "
                "FROM canonical_circuits "
                "WHERE provenance_json->>'source_mirror_circuit_id' IS NOT NULL"
            )
        )
    ).scalars().all()
    return set(rows)


def _fold_members(
    members: list[dict[str, Any]],
    *,
    key: str,
    sort_key,
    mirror_id_key: str,
    merged_key: str,
) -> tuple[list[dict[str, Any]], int]:
    """Fold members sharing the same canonical target onto the first one.

    Deterministic: members are sorted by ``sort_key`` before folding, so the
    kept member is always the same across runs. Folded members' mirror ids
    are appended to the kept member's provenance under ``merged_key``.
    Returns (kept_members, folded_count).
    """
    ordered = sorted(members, key=sort_key)
    by_key: dict[str, list[dict[str, Any]]] = {}
    for m in ordered:
        by_key.setdefault(m[key], []).append(m)
    kept: list[dict[str, Any]] = []
    folded = 0
    for group in by_key.values():
        first, *rest = group
        if rest:
            first = {
                **first,
                "provenance_json": {
                    **first["provenance_json"],
                    merged_key: [m["provenance_json"][mirror_id_key] for m in rest],
                },
            }
            folded += len(rest)
        kept.append(first)
    return kept, folded


async def write(
    session: AsyncSession, plans: list[dict[str, Any]]
) -> dict[str, Any]:
    """Create canonical circuits (+ members) for planned aligned circuits.

    Idempotent: a plan whose ``source_mirror_circuit_id`` already exists in
    canonical_circuits provenance is skipped (second run inserts 0). Region
    and function bind failures raise (a canonical circuit must keep its
    topology and function anchors); connection bind failures are recorded in
    ``unresolved_connections`` and never fail the whole circuit.
    """
    existing = await _load_existing_mirror_ids(session)
    created = 0
    skipped_existing = 0
    region_written = 0
    connection_written = 0
    function_written = 0
    region_folded = 0
    connection_folded = 0
    function_folded = 0
    unresolved_connections: list[dict[str, Any]] = []

    for plan in plans:
        mid = plan["provenance_json"]["source_mirror_circuit_id"]
        if mid in existing:
            skipped_existing += 1
            continue

        circuit = await cis.create_canonical_circuit(
            session,
            CanonicalCircuitCreate(
                canonical_name_en=plan["canonical_name_en"],
                canonical_name_cn=plan["canonical_name_cn"],
                circuit_type=plan["circuit_type"],
                species=plan["species"],
                granularity_level=plan["granularity_level"],
                status=plan["status"],
                description=plan["description"],
                confidence=plan["confidence"],
                source_summary=plan["source_summary"],
                provenance_json=plan["provenance_json"],
                created_by=_CREATED_BY,
            ),
        )
        missing = _PROVENANCE_KEYS - set(circuit.provenance_json)
        if missing:
            raise MacroCircuitCanonicalizerError(
                f"provenance incomplete on {circuit.circuit_code}: "
                f"missing {sorted(missing)}"
            )

        regions, n_folded = _fold_members(
            plan["region_members"],
            key="canonical_region_id",
            sort_key=lambda m: (
                m["order_index"],
                m["provenance_json"]["original_mirror_region_id"],
            ),
            mirror_id_key="original_mirror_region_id",
            merged_key="merged_mirror_region_ids",
        )
        region_folded += n_folded
        functions, n_folded = _fold_members(
            plan["function_members"],
            key="function_term_id",
            sort_key=lambda m: m["provenance_json"]["original_mirror_function_id"],
            mirror_id_key="original_mirror_function_id",
            merged_key="merged_mirror_function_ids",
        )
        function_folded += n_folded
        connections, n_folded = _fold_members(
            plan["connection_members"],
            key="canonical_connection_id",
            sort_key=lambda m: m["provenance_json"]["original_mirror_membership_id"],
            mirror_id_key="original_mirror_membership_id",
            merged_key="merged_mirror_membership_ids",
        )
        connection_folded += n_folded

        for m in regions:
            await cis.add_circuit_region(
                session,
                circuit.id,
                CanonicalCircuitRegionCreate(
                    region_id=uuid.UUID(m["canonical_region_id"]),
                    role=m["role"],
                    order_index=m["order_index"],
                    confidence=m["confidence"],
                    provenance_json=m["provenance_json"],
                ),
            )
            region_written += 1

        for m in functions:
            await cis.add_circuit_function(
                session,
                circuit.id,
                CanonicalCircuitFunctionCreate(
                    function_term_id=uuid.UUID(m["function_term_id"]),
                    relation_type=m["relation_type"],
                    confidence=m["confidence"],
                    provenance_json=m["provenance_json"],
                ),
            )
            function_written += 1

        for m in connections:
            try:
                await cis.add_circuit_connection(
                    session,
                    circuit.id,
                    CanonicalCircuitConnectionCreate(
                        connection_id=uuid.UUID(m["canonical_connection_id"]),
                        role=m["role"],
                        confidence=m["confidence"],
                        provenance_json=m["provenance_json"],
                    ),
                )
                connection_written += 1
            except cis.CanonicalCircuitError as exc:
                # unresolved connection member — record, do not fail the circuit
                unresolved_connections.append(
                    {
                        "mirror_circuit_id": mid,
                        "canonical_connection_id": m["canonical_connection_id"],
                        "error": str(exc),
                    }
                )
        created += 1

    return {
        "created": created,
        "skipped_existing": skipped_existing,
        "region_members_written": region_written,
        "connection_members_written": connection_written,
        "function_members_written": function_written,
        "folded_region_members": region_folded,
        "folded_connection_members": connection_folded,
        "folded_function_members": function_folded,
        "unresolved_connections": unresolved_connections,
    }


# --------------------------------------------------------------------------- #
# Integrity
# --------------------------------------------------------------------------- #


async def integrity_check(session: AsyncSession) -> dict[str, Any]:
    """Run the CI1.1 canonical circuit integrity checker over the whole layer."""
    return await cis.check_canonical_circuit_integrity(session)
