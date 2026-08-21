"""Canonical Circuit service (CI1.1: Circuit Entity + members + integrity).

Responsibilities:
- CRUD for canonical_circuits (concept-neutral circuit layer)
- member binding: regions -> canonical_brain_regions, connections ->
  canonical_connections, functions -> ontology_terms (each dedup by
  circuit + member identity, never silent overwrite)
- merge support: ``replaced_by_circuit_id`` redirect (deprecated circuit
  keeps its row and members; readers follow the replacement)
- integrity checker for the canonical circuit layer

Hard boundaries (CI1.1): never writes ``mirror_region_circuits`` /
``mirror_circuit_*``, never modifies triples, never modifies promotion,
never infers or auto-generates real circuits. This module only establishes
the canonical circuit entity + membership infrastructure.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical_circuit import (
    CanonicalCircuit,
    CanonicalCircuitConnection,
    CanonicalCircuitFunction,
    CanonicalCircuitRegion,
)
from app.models.canonical_connection import CanonicalConnection
from app.models.canonical_region import CanonicalBrainRegion
from app.models.ontology import OntologyTerm
from app.schemas.canonical_circuit import (
    CanonicalCircuitConnectionCreate,
    CanonicalCircuitCreate,
    CanonicalCircuitFunctionCreate,
    CanonicalCircuitRegionCreate,
)

_VALID_CIRCUIT_TYPES = {"network", "pathway", "reflex", "functional_loop", "uncertain"}
_VALID_REGION_ROLES = {"core_region", "input", "output", "intermediate"}
_VALID_CONNECTION_ROLES = {"feedforward", "feedback", "supporting"}
_VALID_RELATION_TYPES = {
    "involved_in",
    "associated_with",
    "necessary_for",
    "modulates",
    "participates_in",
    "uncertain_association",
    "unknown",
}
_VALID_SPECIES = {"human", "mouse", "unknown"}
_VALID_STATUSES = {"proposed", "active", "deprecated"}
_VALID_GRANULARITY_LEVELS = {"whole_brain", "macro", "clinical", "research", "fine", "ultra_fine"}
_CIRCUIT_CODE_PREFIX = "ng:ci:"
_MAX_CODE_RETRIES = 1000


class CanonicalCircuitError(ValueError):
    """Domain error for canonical circuit operations."""


def _species_conflict(a: str, b: str) -> bool:
    """True when two concrete species conflict ('unknown' is compatible with anything)."""
    return a != "unknown" and b != "unknown" and a != b


def _slugify(name: str) -> str:
    """Lowercase, keep [a-z0-9_], collapse separators."""
    slug = re.sub(r"[^a-z0-9_]", "_", name.strip().lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "circuit"


async def _generate_circuit_code(session: AsyncSession, name_en: str) -> str:
    """Auto-generate ``ng:ci:<slug>`` with a numeric suffix on collision."""
    base = f"{_CIRCUIT_CODE_PREFIX}{_slugify(name_en)}"
    taken = {
        code
        for (code,) in (
            await session.execute(select(CanonicalCircuit.circuit_code))
        ).all()
    }
    candidate = base
    for i in range(2, _MAX_CODE_RETRIES + 2):
        if candidate not in taken:
            return candidate
        candidate = f"{base}_{i}"
    raise CanonicalCircuitError("could not generate a unique circuit_code")


async def get_canonical_circuit(
    session: AsyncSession, circuit_id: uuid.UUID
) -> CanonicalCircuit | None:
    return await session.get(CanonicalCircuit, circuit_id)


async def get_canonical_circuit_by_code(
    session: AsyncSession, circuit_code: str
) -> CanonicalCircuit | None:
    return (
        await session.execute(
            select(CanonicalCircuit).where(CanonicalCircuit.circuit_code == circuit_code)
        )
    ).scalar_one_or_none()


async def create_canonical_circuit(
    session: AsyncSession, payload: CanonicalCircuitCreate
) -> CanonicalCircuit:
    """Create one canonical circuit.

    ``circuit_code`` is auto-generated (``ng:ci:<slug>`` from
    canonical_name_en) when not supplied; an explicit code must follow the
    ``ng:ci:*`` pattern and must not already exist. Status starts at
    'proposed' — proposed circuits never enter the Final KG.
    """
    if payload.circuit_code:
        if not payload.circuit_code.startswith(_CIRCUIT_CODE_PREFIX):
            raise CanonicalCircuitError(
                f"circuit_code must follow the {_CIRCUIT_CODE_PREFIX}* pattern"
            )
        if await get_canonical_circuit_by_code(session, payload.circuit_code) is not None:
            raise CanonicalCircuitError(f"circuit_code already exists: {payload.circuit_code}")
        code = payload.circuit_code
    else:
        code = await _generate_circuit_code(session, payload.canonical_name_en)
    circuit = CanonicalCircuit(**payload.model_dump(exclude={"circuit_code"}), circuit_code=code)
    session.add(circuit)
    await session.flush()
    return circuit


async def list_canonical_circuits(
    session: AsyncSession,
    *,
    circuit_type: str | None = None,
    status: str | None = None,
    species: str | None = None,
) -> list[CanonicalCircuit]:
    stmt = select(CanonicalCircuit).order_by(CanonicalCircuit.circuit_code)
    if circuit_type:
        stmt = stmt.where(CanonicalCircuit.circuit_type == circuit_type)
    if status:
        stmt = stmt.where(CanonicalCircuit.status == status)
    if species:
        stmt = stmt.where(CanonicalCircuit.species == species)
    return list((await session.execute(stmt)).scalars().all())


async def _load_circuit(session: AsyncSession, circuit_id: uuid.UUID) -> CanonicalCircuit:
    circuit = await session.get(CanonicalCircuit, circuit_id)
    if circuit is None:
        raise CanonicalCircuitError(f"canonical circuit not found: {circuit_id}")
    return circuit


async def _validate_circuit_species(
    circuit: CanonicalCircuit, member_species: str, member_name: str
) -> None:
    if _species_conflict(circuit.species, member_species):
        raise CanonicalCircuitError(
            f"species mismatch: circuit '{circuit.circuit_code}' species "
            f"'{circuit.species}' vs {member_name} species '{member_species}'"
        )


# --------------------------------------------------------------------------- #
# Region members
# --------------------------------------------------------------------------- #


async def add_circuit_region(
    session: AsyncSession, circuit_id: uuid.UUID, payload: CanonicalCircuitRegionCreate
) -> CanonicalCircuitRegion:
    """Bind a canonical region to a circuit (role core_region/input/output/intermediate)."""
    circuit = await _load_circuit(session, circuit_id)
    region = await session.get(CanonicalBrainRegion, payload.region_id)
    if region is None:
        raise CanonicalCircuitError(f"canonical region not found: {payload.region_id}")
    await _validate_circuit_species(circuit, region.species, f"region '{region.region_code}'")
    dup = (
        await session.execute(
            select(CanonicalCircuitRegion).where(
                CanonicalCircuitRegion.circuit_id == circuit_id,
                CanonicalCircuitRegion.region_id == payload.region_id,
            )
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise CanonicalCircuitError(
            f"duplicate member: region '{region.region_code}' is already bound "
            f"to circuit '{circuit.circuit_code}'"
        )
    member = CanonicalCircuitRegion(circuit_id=circuit_id, **payload.model_dump())
    session.add(member)
    await session.flush()
    return member


async def list_circuit_regions(
    session: AsyncSession, circuit_id: uuid.UUID
) -> list[CanonicalCircuitRegion]:
    await _load_circuit(session, circuit_id)
    return list(
        (
            await session.execute(
                select(CanonicalCircuitRegion)
                .where(CanonicalCircuitRegion.circuit_id == circuit_id)
                .order_by(CanonicalCircuitRegion.order_index, CanonicalCircuitRegion.created_at)
            )
        ).scalars().all()
    )


# --------------------------------------------------------------------------- #
# Connection members
# --------------------------------------------------------------------------- #


async def add_circuit_connection(
    session: AsyncSession, circuit_id: uuid.UUID, payload: CanonicalCircuitConnectionCreate
) -> CanonicalCircuitConnection:
    """Bind a canonical connection to a circuit (role feedforward/feedback/supporting)."""
    circuit = await _load_circuit(session, circuit_id)
    connection = await session.get(CanonicalConnection, payload.connection_id)
    if connection is None:
        raise CanonicalCircuitError(f"canonical connection not found: {payload.connection_id}")
    await _validate_circuit_species(
        circuit, connection.species, f"connection '{connection.connection_code}'"
    )
    dup = (
        await session.execute(
            select(CanonicalCircuitConnection).where(
                CanonicalCircuitConnection.circuit_id == circuit_id,
                CanonicalCircuitConnection.connection_id == payload.connection_id,
            )
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise CanonicalCircuitError(
            f"duplicate member: connection '{connection.connection_code}' is already bound "
            f"to circuit '{circuit.circuit_code}'"
        )
    member = CanonicalCircuitConnection(circuit_id=circuit_id, **payload.model_dump())
    session.add(member)
    await session.flush()
    return member


async def list_circuit_connections(
    session: AsyncSession, circuit_id: uuid.UUID
) -> list[CanonicalCircuitConnection]:
    await _load_circuit(session, circuit_id)
    return list(
        (
            await session.execute(
                select(CanonicalCircuitConnection)
                .where(CanonicalCircuitConnection.circuit_id == circuit_id)
                .order_by(CanonicalCircuitConnection.created_at)
            )
        ).scalars().all()
    )


# --------------------------------------------------------------------------- #
# Function members
# --------------------------------------------------------------------------- #


async def add_circuit_function(
    session: AsyncSession, circuit_id: uuid.UUID, payload: CanonicalCircuitFunctionCreate
) -> CanonicalCircuitFunction:
    """Bind an ontology function term to a circuit (relation_type from vocab)."""
    circuit = await _load_circuit(session, circuit_id)
    term = await session.get(OntologyTerm, payload.function_term_id)
    if term is None:
        raise CanonicalCircuitError(f"ontology term not found: {payload.function_term_id}")
    dup = (
        await session.execute(
            select(CanonicalCircuitFunction).where(
                CanonicalCircuitFunction.circuit_id == circuit_id,
                CanonicalCircuitFunction.function_term_id == payload.function_term_id,
            )
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise CanonicalCircuitError(
            f"duplicate member: function term '{payload.function_term_id}' is already bound "
            f"to circuit '{circuit.circuit_code}'"
        )
    member = CanonicalCircuitFunction(circuit_id=circuit_id, **payload.model_dump())
    session.add(member)
    await session.flush()
    return member


async def list_circuit_functions(
    session: AsyncSession, circuit_id: uuid.UUID
) -> list[CanonicalCircuitFunction]:
    await _load_circuit(session, circuit_id)
    return list(
        (
            await session.execute(
                select(CanonicalCircuitFunction)
                .where(CanonicalCircuitFunction.circuit_id == circuit_id)
                .order_by(CanonicalCircuitFunction.created_at)
            )
        ).scalars().all()
    )


# --------------------------------------------------------------------------- #
# Merge (lifecycle: proposed -> active -> deprecated)
# --------------------------------------------------------------------------- #


async def merge_circuits(
    session: AsyncSession, *, deprecated_circuit_id: uuid.UUID, active_circuit_id: uuid.UUID
) -> CanonicalCircuit:
    """Redirect a deprecated circuit onto its replacement (merge).

    The deprecated circuit keeps its row and its members (provenance is
    never rewritten); its status becomes 'deprecated' and
    ``replaced_by_circuit_id`` points at the active circuit. Readers follow
    the redirect. A circuit that is itself deprecated can never be the
    merge target.
    """
    deprecated = await _load_circuit(session, deprecated_circuit_id)
    active = await _load_circuit(session, active_circuit_id)
    if deprecated.id == active.id:
        raise CanonicalCircuitError("merge requires two distinct circuits")
    if deprecated.replaced_by_circuit_id is not None:
        raise CanonicalCircuitError(
            f"circuit '{deprecated.circuit_code}' was already merged "
            f"(replaced_by {deprecated.replaced_by_circuit_id})"
        )
    if active.status == "deprecated":
        raise CanonicalCircuitError(
            f"merge target '{active.circuit_code}' is itself deprecated"
        )
    deprecated.status = "deprecated"
    deprecated.replaced_by_circuit_id = active.id
    await session.flush()
    return deprecated


# --------------------------------------------------------------------------- #
# Integrity checker
# --------------------------------------------------------------------------- #


def _issue(issues: list[dict[str, str]], severity: str, code: str, message: str) -> None:
    issues.append({"severity": severity, "code": code, "message": message})


async def check_canonical_circuit_integrity(session: AsyncSession) -> dict[str, Any]:
    """Audit the canonical circuit layer without modifying anything.

    Checks: orphan region/connection/function member references, duplicate
    members, circuit with no members, invalid type/status/granularity/roles,
    species mismatch (circuit vs members), deprecated references (dangling
    or self replacement, deprecated circuit without replacement,
    non-deprecated circuit with replacement, member pointing at a deprecated
    region/connection). DB-level CHECK/UNIQUE/FK constraints already prevent
    most of these — the checker is a defensive second opinion, plus reports
    the untouched mirror_region_circuits row count.
    """
    issues: list[dict[str, str]] = []
    counts: dict[str, int] = {}

    circuits = (
        await session.execute(
            select(CanonicalCircuit).order_by(CanonicalCircuit.circuit_code)
        )
    ).scalars().all()
    counts["total_circuits"] = len(circuits)

    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    memberless = 0
    circuit_ids = [c.id for c in circuits]

    for c in circuits:
        by_status[c.status] = by_status.get(c.status, 0) + 1
        by_type[c.circuit_type] = by_type.get(c.circuit_type, 0) + 1
        if c.circuit_type not in _VALID_CIRCUIT_TYPES:
            _issue(issues, "high", "INVALID_TYPE",
                   f"circuit {c.circuit_code} has invalid circuit_type '{c.circuit_type}'")
        if c.status not in _VALID_STATUSES:
            _issue(issues, "medium", "INVALID_STATUS",
                   f"circuit {c.circuit_code} has invalid status '{c.status}'")
        if c.granularity_level not in _VALID_GRANULARITY_LEVELS:
            _issue(issues, "medium", "INVALID_GRANULARITY",
                   f"circuit {c.circuit_code} has invalid granularity_level '{c.granularity_level}'")
        if c.replaced_by_circuit_id is not None:
            if c.replaced_by_circuit_id == c.id:
                _issue(issues, "critical", "REPLACEMENT_SELF",
                       f"circuit {c.circuit_code} is replaced by itself")
            elif c.replaced_by_circuit_id not in set(circuit_ids):
                _issue(issues, "critical", "REPLACEMENT_MISSING",
                       f"circuit {c.circuit_code} references a missing replacement circuit")
            elif c.status != "deprecated":
                _issue(issues, "medium", "NON_DEPRECATED_WITH_REPLACEMENT",
                       f"circuit {c.circuit_code} (status '{c.status}') has a replacement set")
        elif c.status == "deprecated":
            _issue(issues, "medium", "DEPRECATED_WITHOUT_REPLACEMENT",
                   f"circuit {c.circuit_code} is deprecated but has no replaced_by_circuit_id")

    # --- region members ---
    region_rows = (
        await session.execute(
            text(
                "SELECT m.circuit_id, m.region_id, m.role, "
                "rr.species AS region_species, rr.status AS region_status, rr.region_code "
                "FROM canonical_circuit_regions m "
                "LEFT JOIN canonical_brain_regions rr ON rr.id = m.region_id"
            )
        )
    ).mappings().all()
    counts["region_members"] = len(region_rows)
    for r in region_rows:
        if r["region_species"] is None:
            _issue(issues, "critical", "ORPHAN_REGION_MEMBER",
                   f"region member of circuit {r['circuit_id']} references a missing canonical region")
            continue
        if r["role"] not in _VALID_REGION_ROLES:
            _issue(issues, "high", "INVALID_REGION_ROLE",
                   f"region member {r['region_code']} has invalid role '{r['role']}'")
        if r["region_status"] == "deprecated":
            _issue(issues, "medium", "DEPRECATED_REGION_REFERENCE",
                   f"region member references deprecated region '{r['region_code']}'")

    # --- connection members ---
    connection_rows = (
        await session.execute(
            text(
                "SELECT m.circuit_id, m.connection_id, m.role, "
                "cc.species AS connection_species, cc.status AS connection_status, "
                "cc.connection_code "
                "FROM canonical_circuit_connections m "
                "LEFT JOIN canonical_connections cc ON cc.id = m.connection_id"
            )
        )
    ).mappings().all()
    counts["connection_members"] = len(connection_rows)
    for r in connection_rows:
        if r["connection_species"] is None:
            _issue(issues, "critical", "ORPHAN_CONNECTION_MEMBER",
                   f"connection member of circuit {r['circuit_id']} references a missing canonical connection")
            continue
        if r["role"] not in _VALID_CONNECTION_ROLES:
            _issue(issues, "high", "INVALID_CONNECTION_ROLE",
                   f"connection member {r['connection_code']} has invalid role '{r['role']}'")
        if r["connection_status"] == "deprecated":
            _issue(issues, "medium", "DEPRECATED_CONNECTION_REFERENCE",
                   f"connection member references deprecated connection '{r['connection_code']}'")

    # --- function members ---
    function_rows = (
        await session.execute(
            text(
                "SELECT m.circuit_id, m.function_term_id, m.relation_type, "
                "ot.id AS term_row_id "
                "FROM canonical_circuit_functions m "
                "LEFT JOIN ontology_terms ot ON ot.id = m.function_term_id"
            )
        )
    ).mappings().all()
    counts["function_members"] = len(function_rows)
    for r in function_rows:
        if r["term_row_id"] is None:
            _issue(issues, "critical", "ORPHAN_FUNCTION_MEMBER",
                   f"function member of circuit {r['circuit_id']} references a missing ontology term")
            continue
        if r["relation_type"] not in _VALID_RELATION_TYPES:
            _issue(issues, "high", "INVALID_RELATION_TYPE",
                   f"function member {r['function_term_id']} has invalid relation_type '{r['relation_type']}'")

    # --- species consistency: circuit vs members (per member row) ---
    circuit_species = {c.id: c.species for c in circuits}
    for r in region_rows:
        cs = circuit_species.get(r["circuit_id"])
        if cs is not None and r["region_species"] is not None and _species_conflict(cs, r["region_species"]):
            _issue(issues, "high", "SPECIES_MISMATCH",
                   f"circuit {r['circuit_id']} species '{cs}' conflicts with region member "
                   f"'{r['region_code']}' species '{r['region_species']}'")
    for r in connection_rows:
        cs = circuit_species.get(r["circuit_id"])
        if cs is not None and r["connection_species"] is not None and _species_conflict(cs, r["connection_species"]):
            _issue(issues, "high", "SPECIES_MISMATCH",
                   f"circuit {r['circuit_id']} species '{cs}' conflicts with connection member "
                   f"'{r['connection_code']}' species '{r['connection_species']}'")

    # --- duplicate members (defensive; UNIQUE constraints prevent these) ---
    dup_regions = int((await session.execute(text(
        "SELECT count(*) FROM (SELECT circuit_id, region_id FROM canonical_circuit_regions "
        "GROUP BY 1,2 HAVING count(*)>1) d"
    ))).scalar_one())
    if dup_regions:
        counts["duplicate_region_members"] = dup_regions
        _issue(issues, "critical", "DUPLICATE_REGION_MEMBER",
               f"{dup_regions} duplicate (circuit,region) member groups")
    dup_connections = int((await session.execute(text(
        "SELECT count(*) FROM (SELECT circuit_id, connection_id FROM canonical_circuit_connections "
        "GROUP BY 1,2 HAVING count(*)>1) d"
    ))).scalar_one())
    if dup_connections:
        counts["duplicate_connection_members"] = dup_connections
        _issue(issues, "critical", "DUPLICATE_CONNECTION_MEMBER",
               f"{dup_connections} duplicate (circuit,connection) member groups")
    dup_functions = int((await session.execute(text(
        "SELECT count(*) FROM (SELECT circuit_id, function_term_id FROM canonical_circuit_functions "
        "GROUP BY 1,2 HAVING count(*)>1) d"
    ))).scalar_one())
    if dup_functions:
        counts["duplicate_function_members"] = dup_functions
        _issue(issues, "critical", "DUPLICATE_FUNCTION_MEMBER",
               f"{dup_functions} duplicate (circuit,function) member groups")

    # --- circuits without members (not deprecated — historical circuits are exempt) ---
    memberless = int((await session.execute(text(
        "SELECT count(*) FROM canonical_circuits c "
        "WHERE c.status <> 'deprecated' "
        "AND NOT EXISTS (SELECT 1 FROM canonical_circuit_regions m WHERE m.circuit_id = c.id) "
        "AND NOT EXISTS (SELECT 1 FROM canonical_circuit_connections m WHERE m.circuit_id = c.id) "
        "AND NOT EXISTS (SELECT 1 FROM canonical_circuit_functions m WHERE m.circuit_id = c.id)"
    ))).scalar_one())
    counts["memberless_circuit_count"] = memberless
    if memberless:
        _issue(issues, "medium", "CIRCUIT_NO_MEMBERS",
               f"{memberless} non-deprecated circuit(s) have no members")

    mirror_count = int((await session.execute(
        text("SELECT count(*) FROM mirror_region_circuits")
    )).scalar_one())
    counts["mirror_circuits_untouched"] = mirror_count

    counts.update({f"status_{k}": v for k, v in by_status.items()})
    counts.update({f"type_{k}": v for k, v in by_type.items()})

    return {
        "ok": not any(i["severity"] in ("critical", "high") for i in issues),
        "counts": counts,
        "issues": issues,
    }


async def check_circuit_graph_integrity(session: AsyncSession) -> dict[str, Any]:
    """Circuit-Connection-Region closure checker (CI1.3-3).

    Cross-layer audit of the canonical circuit graph (read-only):

    1. topology closure — every connection member's source/target region must
       both be bound as region members of the SAME circuit;
    2. orphan connection member — member references a missing
       canonical_connections row;
    3. missing endpoint — the referenced connection exists but its
       source/target region row is missing;
    4. orphan region/function members — member references a missing
       canonical_brain_regions / ontology_terms row;
    5. duplicate members — (circuit, member) rows in all three member tables;
    6. deprecated references — members referencing deprecated entities
       (region / connection / function term / connection endpoint regions).

    DB-level FK/UNIQUE constraints already prevent most of these — the checker
    is a defensive second opinion, plus the topology closure statistics.
    """
    issues: list[dict[str, str]] = []
    counts: dict[str, int] = {}

    # --- per-circuit region member sets (for topology closure) ---
    region_rows = (
        await session.execute(
            text(
                "SELECT m.circuit_id, m.region_id, "
                "rr.id AS region_row_id, rr.status AS region_status, rr.region_code "
                "FROM canonical_circuit_regions m "
                "LEFT JOIN canonical_brain_regions rr ON rr.id = m.region_id"
            )
        )
    ).mappings().all()
    counts["region_members"] = len(region_rows)
    circuit_region_sets: dict[str, set[str]] = {}
    orphan_region_members = 0
    deprecated_region_refs = 0
    for r in region_rows:
        cid = str(r["circuit_id"])
        if r["region_row_id"] is None:
            orphan_region_members += 1
            _issue(issues, "critical", "ORPHAN_REGION_MEMBER",
                   f"region member of circuit {cid} references a missing canonical region")
            continue
        circuit_region_sets.setdefault(cid, set()).add(str(r["region_id"]))
        if r["region_status"] == "deprecated":
            deprecated_region_refs += 1
            _issue(issues, "medium", "DEPRECATED_REGION_REFERENCE",
                   f"region member references deprecated region '{r['region_code']}' "
                   f"of circuit {cid}")
    counts["orphan_region_member_count"] = orphan_region_members

    # --- connection members joined with their canonical connections ---
    connection_rows = (
        await session.execute(
            text(
                "SELECT m.circuit_id, m.connection_id, "
                "cc.source_region_id, cc.target_region_id, "
                "cc.status AS connection_status, cc.connection_code, "
                "src.id AS src_row_id, tgt.id AS tgt_row_id, "
                "src.status AS src_status, tgt.status AS tgt_status "
                "FROM canonical_circuit_connections m "
                "LEFT JOIN canonical_connections cc ON cc.id = m.connection_id "
                "LEFT JOIN canonical_brain_regions src ON src.id = cc.source_region_id "
                "LEFT JOIN canonical_brain_regions tgt ON tgt.id = cc.target_region_id"
            )
        )
    ).mappings().all()
    counts["connection_members"] = len(connection_rows)
    circuits_with_connections: set[str] = set()
    orphan_connection_members = 0
    missing_endpoint_regions = 0
    topology_open = 0
    deprecated_connection_refs = 0
    for r in connection_rows:
        cid = str(r["circuit_id"])
        circuits_with_connections.add(cid)
        if r["connection_code"] is None:
            orphan_connection_members += 1
            _issue(issues, "critical", "ORPHAN_CONNECTION_MEMBER",
                   f"connection member of circuit {cid} references a missing "
                   "canonical connection")
            continue
        if r["src_row_id"] is None or r["tgt_row_id"] is None:
            missing_endpoint_regions += 1
            _issue(issues, "critical", "MISSING_ENDPOINT_REGION",
                   f"connection '{r['connection_code']}' of circuit {cid} has a "
                   "missing source/target canonical region")
            continue
        if r["connection_status"] == "deprecated":
            deprecated_connection_refs += 1
            _issue(issues, "medium", "DEPRECATED_CONNECTION_REFERENCE",
                   f"connection member references deprecated connection "
                   f"'{r['connection_code']}' of circuit {cid}")
        member_regions = circuit_region_sets.get(cid, set())
        if (
            str(r["source_region_id"]) not in member_regions
            or str(r["target_region_id"]) not in member_regions
        ):
            topology_open += 1
            _issue(issues, "high", "TOPOLOGY_ENDPOINT_NOT_MEMBER",
                   f"connection '{r['connection_code']}' of circuit {cid} has an "
                   "endpoint region that is not a member of the circuit")
        if r["src_status"] == "deprecated" or r["tgt_status"] == "deprecated":
            deprecated_connection_refs += 1
            _issue(issues, "medium", "DEPRECATED_ENDPOINT_REGION",
                   f"connection '{r['connection_code']}' of circuit {cid} "
                   "references a deprecated endpoint region")

    counts["circuits_with_connections"] = len(circuits_with_connections)
    counts["topology_closed_connections"] = (
        counts["connection_members"] - orphan_connection_members
        - missing_endpoint_regions - topology_open
    )
    counts["topology_open_connections"] = topology_open
    counts["orphan_connection_member_count"] = orphan_connection_members
    counts["missing_endpoint_region_count"] = missing_endpoint_regions

    # --- function members ---
    function_rows = (
        await session.execute(
            text(
                "SELECT m.circuit_id, m.function_term_id, "
                "ot.id AS term_row_id, ot.status AS term_status "
                "FROM canonical_circuit_functions m "
                "LEFT JOIN ontology_terms ot ON ot.id = m.function_term_id"
            )
        )
    ).mappings().all()
    counts["function_members"] = len(function_rows)
    orphan_function_members = 0
    deprecated_function_refs = 0
    for r in function_rows:
        cid = str(r["circuit_id"])
        if r["term_row_id"] is None:
            orphan_function_members += 1
            _issue(issues, "critical", "ORPHAN_FUNCTION_MEMBER",
                   f"function member of circuit {cid} references a missing ontology term")
            continue
        if r["term_status"] == "deprecated":
            deprecated_function_refs += 1
            _issue(issues, "medium", "DEPRECATED_FUNCTION_REFERENCE",
                   f"function member references deprecated term "
                   f"'{r['function_term_id']}' of circuit {cid}")
    counts["orphan_function_member_count"] = orphan_function_members

    # --- duplicate members (defensive; UNIQUE constraints prevent these) ---
    duplicate_groups = 0
    for table, id_col, kind in (
        ("canonical_circuit_regions", "region_id", "region"),
        ("canonical_circuit_connections", "connection_id", "connection"),
        ("canonical_circuit_functions", "function_term_id", "function"),
    ):
        dup = int((await session.execute(text(
            f"SELECT count(*) FROM (SELECT circuit_id, {id_col} FROM {table} "
            f"GROUP BY 1,2 HAVING count(*)>1) d"
        ))).scalar_one())
        counts[f"duplicate_{kind}_member_groups"] = dup
        if dup:
            duplicate_groups += dup
            _issue(issues, "critical", "DUPLICATE_MEMBER",
                   f"{dup} duplicate (circuit,{kind}) member groups in {table}")
    counts["duplicate_member_groups"] = duplicate_groups

    counts["deprecated_reference_count"] = (
        deprecated_region_refs + deprecated_connection_refs + deprecated_function_refs
    )

    return {
        "ok": not any(i["severity"] in ("critical", "high") for i in issues),
        "counts": counts,
        "issues": issues,
    }
