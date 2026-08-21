"""Circuit mapping service (CI1.2-A: frozen mirror circuit → canonical circuit rules).

Pure mapping functions plus a read-only planning pass used before batch
generation (CI1.2-B). No writes to ``canonical_circuits`` / member tables,
no modification of any mirror table, no LLM guessing, no name-match
fabrication, no auto-creation of regions or function terms. Anything outside
the frozen rule tables raises ``CircuitMappingError`` — silent
misclassification is forbidden.

Frozen rules (validated against the real mirror value space on 2026-08-20):

* circuit_type: the mirror classification is FUNCTIONAL (e.g.
  sensory_circuit = a sensory functional network) while the canonical
  circuit_type is STRUCTURAL (network/pathway/reflex/functional_loop). A
  functional circuit is canonically typed ``network`` (distributed
  functional network); the original functional label is preserved in
  provenance. uncertain_circuit/unknown -> ``uncertain``. Canonical-space
  values pass through unchanged. Anything else raises.

* region role: participant -> core_region; source -> input; target ->
  output; intermediate -> intermediate. hub/relay/modulator are non-terminal
  topology roles and map to ``intermediate`` (original role preserved in
  provenance). ``unknown`` raises — it cannot be mapped without fabricating
  a topology position.

* connection role (projection membership): feedforward/feedback/supporting
  pass through; ``unknown`` -> ``supporting`` (the neutral role that asserts
  no direction; original preserved in provenance).

* grounding: a region member enters a canonical circuit ONLY when its
  ``region_candidate_id`` resolves to a ``candidate_brain_regions`` row with
  a non-NULL ``canonical_region_id``. A connection member enters ONLY when
  its projection resolves to a canonical_connections row via provenance
  (original_connection_ids). Function members resolve through the existing
  function_term_service ladder (term_id anchor or exact text match) — terms
  are NEVER created here; unresolved terms are recorded.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical_connection import CanonicalConnection
from app.services.function_term_service import (
    FunctionTermResolution,
    STATE_AMBIGUOUS,
    STATE_UNRESOLVED,
    VALID_ANCHOR_STATES,
    _load_term_index,
    resolve_canonical_function_term,
    zh_term_key,
)
from app.services.ontology_service import normalize_term_key

_MIRROR_TO_CANONICAL_CIRCUIT_TYPE: dict[str, str] = {
    # mirror functional classification -> canonical structural classification
    "cognitive_control_circuit": "network",
    "sensory_circuit": "network",
    "motor_circuit": "network",
    "limbic_circuit": "network",
    "language_related": "network",
    "memory_related": "network",
    "default_mode_related": "network",
    "attention_related": "network",
    "reward_related": "network",
    "salience_related": "network",
    "uncertain_circuit": "uncertain",
    "unknown": "uncertain",
    # canonical-space passthrough (raw values already in canonical space)
    "network": "network",
    "pathway": "pathway",
    "reflex": "reflex",
    "functional_loop": "functional_loop",
}

_MIRROR_TO_CANONICAL_REGION_ROLE: dict[str, str] = {
    "participant": "core_region",
    "source": "input",
    "target": "output",
    "intermediate": "intermediate",  # passthrough (not in mirror CHECK; future-proof)
    # non-terminal topology roles -> intermediate (original preserved in provenance)
    "hub": "intermediate",
    "relay": "intermediate",
    "modulator": "intermediate",
}

_MIRROR_TO_CANONICAL_CONNECTION_ROLE: dict[str, str] = {
    "feedforward": "feedforward",
    "feedback": "feedback",
    "supporting": "supporting",
    # 'unknown' asserts no direction -> neutral 'supporting' role
    "unknown": "supporting",
}

_CANONICAL_CIRCUIT_TYPES = {"network", "pathway", "reflex", "functional_loop", "uncertain"}
_CANONICAL_REGION_ROLES = {"core_region", "input", "output", "intermediate"}
_CANONICAL_CONNECTION_ROLES = {"feedforward", "feedback", "supporting"}

DEFAULT_MAPPING_VERSION = "macro96_canonical_circuit_v1"

_CANONICAL_SPECIES = "human"   # mirror circuits carry no species; all source atlases are human
_CANONICAL_GRANULARITY = "clinical"  # macro mirror granularity -> clinical canonical granularity

# Canonical relation_type default for circuit function members (mirror
# circuit_functions has no relation_type column; the original function_role /
# effect_type are preserved in member provenance).
DEFAULT_FUNCTION_RELATION_TYPE = "associated_with"


class CircuitMappingError(ValueError):
    """Domain error for circuit mapping rules."""


def map_circuit_type(raw_type: str | None) -> str:
    """Map a mirror circuit_type to the canonical enum.

    Frozen rule: mirror functional classifications are distributed functional
    networks -> ``network`` (original label preserved in provenance);
    uncertain_circuit/unknown -> ``uncertain``; canonical-space values pass
    through. ``None``/empty is treated as ``unknown``. Unmapped values raise
    ``CircuitMappingError`` — silent classification is forbidden.
    """
    if raw_type is None or raw_type == "":
        raw_type = "unknown"
    mapped = _MIRROR_TO_CANONICAL_CIRCUIT_TYPE.get(raw_type)
    if mapped is None:
        raise CircuitMappingError(f"unmapped mirror circuit_type: {raw_type!r}")
    return mapped


def map_circuit_region_role(raw_role: str | None) -> str:
    """Map a mirror circuit region role to the canonical member role.

    participant -> core_region; source -> input; target -> output;
    intermediate -> intermediate; hub/relay/modulator -> intermediate
    (non-terminal topology roles). ``unknown`` and ``None``/empty raise —
    there is no canonical role that represents an unknown topology position.
    """
    if raw_role is None or raw_role == "":
        raise CircuitMappingError("region role is empty — cannot map without fabricating a topology position")
    mapped = _MIRROR_TO_CANONICAL_REGION_ROLE.get(raw_role)
    if mapped is None:
        raise CircuitMappingError(f"unmapped mirror circuit region role: {raw_role!r}")
    return mapped


def map_circuit_connection_role(raw_role: str | None) -> str:
    """Map a mirror projection membership role to the canonical connection role.

    feedforward/feedback/supporting pass through; ``unknown``/``None`` ->
    ``supporting`` (neutral role, asserts no direction).
    """
    if raw_role is None or raw_role == "":
        raw_role = "unknown"
    mapped = _MIRROR_TO_CANONICAL_CONNECTION_ROLE.get(raw_role)
    if mapped is None:
        raise CircuitMappingError(f"unmapped mirror projection role_in_circuit: {raw_role!r}")
    return mapped


def build_circuit_provenance(
    source_mirror_circuit_id: uuid.UUID | str,
    source_region_ids: list[uuid.UUID | str],
    source_connection_ids: list[uuid.UUID | str],
    source_function_ids: list[uuid.UUID | str],
    *,
    mapping_version: str = DEFAULT_MAPPING_VERSION,
    mapping_confidence: float | None = None,
) -> dict[str, Any]:
    """Provenance block for a canonical circuit built from mirror rows.

    Preserves full traceability to the mirror circuit and every source member
    row (which are never modified). Id lists are stringified; mapping_confidence
    is the resolved-member ratio of the plan (0-1) or None.
    """
    if not source_mirror_circuit_id:
        raise CircuitMappingError("source_mirror_circuit_id must not be empty")
    if not mapping_version:
        raise CircuitMappingError("mapping_version must not be empty")
    if mapping_confidence is not None and not (0.0 <= float(mapping_confidence) <= 1.0):
        raise CircuitMappingError("mapping_confidence must be within [0, 1]")
    return {
        "source_mirror_circuit_id": str(source_mirror_circuit_id),
        "source_region_ids": [str(i) for i in source_region_ids],
        "source_connection_ids": [str(i) for i in source_connection_ids],
        "source_function_ids": [str(i) for i in source_function_ids],
        "mapping_version": mapping_version,
        "mapping_confidence": (
            float(mapping_confidence) if mapping_confidence is not None else None
        ),
    }


# --------------------------------------------------------------------------- #
# Function term resolution (lookup only — never creates terms)
# --------------------------------------------------------------------------- #


async def resolve_circuit_function(
    session: AsyncSession,
    *,
    term_id: uuid.UUID | None = None,
    term_en: str | None = None,
    term_cn: str | None = None,
    index: Any | None = None,
) -> FunctionTermResolution:
    """Resolve a mirror circuit function to a canonical ontology term.

    Reuses the existing function_term_service ladder WITHOUT auto-propose:
    1. existing ``term_id`` anchor -> canonical resolution (merged redirects,
       deprecated / wrong-type guards);
    2. exact normalized match against active canonical names;
    3. active synonym exact match;
    4. proposed canonical exact match;
    5. merged canonical exact match -> canonical resolution.
    Anything unresolved is reported as ``unresolved`` (path records the
    attempt) — no new function term is ever created here.
    """
    if term_id is not None:
        return await resolve_canonical_function_term(session, term_id)

    text_value = (term_en or term_cn or "").strip()
    if not text_value:
        return FunctionTermResolution(state=STATE_UNRESOLVED, path=["empty_text"])

    idx = index if index is not None else await _load_term_index(session)
    key = normalize_term_key(text_value)
    if key:
        if key in idx.ambiguous_keys:
            return FunctionTermResolution(state=STATE_AMBIGUOUS, path=["ambiguous_synonym"])
        term_id_found = idx.active_canon.get(key)
        if term_id_found is not None:
            return await resolve_canonical_function_term(session, term_id_found)
        term_id_found = idx.active_synonym.get(key)
        if term_id_found is not None:
            return await resolve_canonical_function_term(session, term_id_found)
        term_id_found = idx.proposed_canon.get(key)
        if term_id_found is not None:
            return await resolve_canonical_function_term(session, term_id_found)
        term_id_found = idx.merged_canon.get(key)
        if term_id_found is not None:
            res = await resolve_canonical_function_term(session, term_id_found)
            res.path = ["merged_canonical_exact", *res.path]
            return res
    zkey = zh_term_key(text_value)
    if zkey:
        term_id_found = idx.zh_canon.get(zkey)
        if term_id_found is not None:
            res = await resolve_canonical_function_term(session, term_id_found)
            res.path = ["zh_canonical_exact", *res.path]
            return res
    return FunctionTermResolution(state=STATE_UNRESOLVED, path=["no_match_no_propose"])


# --------------------------------------------------------------------------- #
# Canonical connection resolution
# --------------------------------------------------------------------------- #


async def resolve_canonical_connection(
    session: AsyncSession, mirror_connection_id: uuid.UUID | str
) -> CanonicalConnection | None:
    """Resolve a mirror connection id to its canonical_connections row.

    The linkage is the CN1.2-2B provenance: a canonical connection lists its
    original mirror row ids in provenance_json.original_connection_ids. A
    mirror row belongs to exactly one canonical group, so this returns at most
    one canonical connection. ``None`` means the mirror connection was never
    canonicalized (recorded as unresolved by the plan).
    """
    row = (
        await session.execute(
            text(
                "SELECT cc.id FROM canonical_connections cc "
                "WHERE cc.provenance_json->'original_connection_ids' @> to_jsonb(CAST(:mid AS text))"
            ),
            {"mid": str(mirror_connection_id)},
        )
    ).first()
    if row is None:
        return None
    return await session.get(CanonicalConnection, row[0])


# --------------------------------------------------------------------------- #
# Fetch (read-only)
# --------------------------------------------------------------------------- #


async def _fetch_macro_circuits(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                "SELECT id, circuit_name, circuit_type, confidence, source_atlas, name_cn "
                "FROM mirror_region_circuits WHERE granularity_level='macro' "
                "ORDER BY circuit_name"
            )
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def _fetch_macro_members(session: AsyncSession) -> dict[str, dict[str, Any]]:
    """Region / function / projection members of macro circuits, grouped by circuit."""
    region_rows = (
        await session.execute(
            text(
                "SELECT mcr.circuit_id, mcr.id, mcr.role, mcr.sort_order, "
                "mcr.region_candidate_id, c.canonical_region_id "
                "FROM mirror_circuit_regions mcr "
                "JOIN mirror_region_circuits mrc ON mrc.id = mcr.circuit_id "
                "LEFT JOIN candidate_brain_regions c ON c.id = mcr.region_candidate_id "
                "WHERE mrc.granularity_level='macro'"
            )
        )
    ).mappings().all()
    function_rows = (
        await session.execute(
            text(
                "SELECT mcf.circuit_id, mcf.id, mcf.function_term_en, mcf.function_term_cn, "
                "mcf.term_id, mcf.function_role, mcf.effect_type, mcf.confidence_score, mcf.confidence "
                "FROM mirror_circuit_functions mcf "
                "JOIN mirror_region_circuits mrc ON mrc.id = mcf.circuit_id "
                "WHERE mrc.granularity_level='macro'"
            )
        )
    ).mappings().all()
    projection_rows = (
        await session.execute(
            text(
                "SELECT mcp.circuit_id, mcp.id, mcp.projection_id, mcp.role_in_circuit, mcp.confidence "
                "FROM mirror_circuit_projection_memberships mcp "
                "JOIN mirror_region_circuits mrc ON mrc.id = mcp.circuit_id "
                "WHERE mrc.granularity_level='macro'"
            )
        )
    ).mappings().all()
    members: dict[str, dict[str, Any]] = {}
    for r in region_rows:
        members.setdefault(str(r["circuit_id"]), {"regions": [], "functions": [], "projections": []})
        members[str(r["circuit_id"])]["regions"].append(dict(r))
    for r in function_rows:
        members.setdefault(str(r["circuit_id"]), {"regions": [], "functions": [], "projections": []})
        members[str(r["circuit_id"])]["functions"].append(dict(r))
    for r in projection_rows:
        members.setdefault(str(r["circuit_id"]), {"regions": [], "functions": [], "projections": []})
        members[str(r["circuit_id"])]["projections"].append(dict(r))
    return members


# --------------------------------------------------------------------------- #
# Plan (dry-run only — never writes)
# --------------------------------------------------------------------------- #


def _empty_bucket() -> dict[str, list[dict[str, Any]]]:
    return {"regions": [], "functions": [], "projections": []}


async def plan_macro_circuit_canonicalization(session: AsyncSession) -> dict[str, Any]:
    """Build a read-only canonicalization plan for macro mirror circuits.

    Classifies every macro circuit (granularity_level='macro') as:
    * rejected  — unmappable circuit_type, or no region members (a canonical
      circuit must have at least one region anchor);
    * unresolved — at least one member fails: region not grounded / region
      role unmappable / function term unresolved (deprecated, invalid or no
      match) / projection without a canonical connection;
    * aligned   — circuit type mappable, >=1 region member, every member
      resolves.

    Writes NOTHING. Returns plan items for aligned circuits (with mapped
    members and full provenance) plus per-circuit failure reasons for the
    unresolved/rejected ones. ``mapping_confidence`` = resolved-member ratio.
    """
    circuits = await _fetch_macro_circuits(session)
    members_by_circuit = await _fetch_macro_members(session)
    term_index = await _load_term_index(session)

    plans: list[dict[str, Any]] = []
    unresolved_circuits: list[dict[str, Any]] = []
    rejected_circuits: list[dict[str, Any]] = []
    region_member_stats = {"aligned": 0, "unresolved": 0}
    function_member_stats = {"aligned": 0, "unresolved": 0}
    projection_member_stats = {"aligned": 0, "unresolved": 0}

    for circuit in circuits:
        cid = str(circuit["id"])
        bucket = members_by_circuit.get(cid, _empty_bucket())
        try:
            mapped_type = map_circuit_type(circuit["circuit_type"])
        except CircuitMappingError as exc:
            rejected_circuits.append({
                "mirror_circuit_id": cid,
                "circuit_name": circuit["circuit_name"],
                "reason": f"unmappable_circuit_type: {exc}",
            })
            continue
        if not bucket["regions"]:
            rejected_circuits.append({
                "mirror_circuit_id": cid,
                "circuit_name": circuit["circuit_name"],
                "reason": "no_region_members",
            })
            continue

        region_members: list[dict[str, Any]] = []
        failures: list[str] = []
        for r in bucket["regions"]:
            try:
                role = map_circuit_region_role(r["role"])
            except CircuitMappingError as exc:
                failures.append(f"region {r['id']}: {exc}")
                region_member_stats["unresolved"] += 1
                continue
            if r["canonical_region_id"] is None:
                failures.append(f"region {r['id']}: region_candidate not grounded to canonical")
                region_member_stats["unresolved"] += 1
                continue
            region_member_stats["aligned"] += 1
            region_members.append({
                "canonical_region_id": str(r["canonical_region_id"]),
                "role": role,
                "order_index": r["sort_order"] or 0,
                "confidence": None,
                "provenance_json": {
                    "original_mirror_region_id": str(r["id"]),
                    "original_role": r["role"],
                },
            })

        function_members: list[dict[str, Any]] = []
        for f in bucket["functions"]:
            res = await resolve_circuit_function(
                session,
                term_id=f["term_id"],
                term_en=f["function_term_en"],
                term_cn=f["function_term_cn"],
                index=term_index,
            )
            if res.state not in VALID_ANCHOR_STATES:
                failures.append(
                    f"function {f['id']}: unresolved ({res.state}, path={res.path})"
                )
                function_member_stats["unresolved"] += 1
                continue
            function_member_stats["aligned"] += 1
            confidence = f["confidence_score"] if f["confidence_score"] is not None else f["confidence"]
            function_members.append({
                "function_term_id": str(res.term_id),
                "relation_type": DEFAULT_FUNCTION_RELATION_TYPE,
                "confidence": float(confidence) if confidence is not None else None,
                "provenance_json": {
                    "original_mirror_function_id": str(f["id"]),
                    "original_function_role": f["function_role"],
                    "original_effect_type": f["effect_type"],
                    "resolution_path": res.path,
                },
            })

        connection_members: list[dict[str, Any]] = []
        for p in bucket["projections"]:
            canonical = await resolve_canonical_connection(session, p["projection_id"])
            if canonical is None:
                failures.append(
                    f"projection {p['id']}: mirror connection {p['projection_id']} "
                    "has no canonical_connections row"
                )
                projection_member_stats["unresolved"] += 1
                continue
            projection_member_stats["aligned"] += 1
            connection_members.append({
                "canonical_connection_id": str(canonical.id),
                "role": map_circuit_connection_role(p["role_in_circuit"]),
                "confidence": float(p["confidence"]) if p["confidence"] is not None else None,
                "provenance_json": {
                    "original_mirror_membership_id": str(p["id"]),
                    "original_projection_id": str(p["projection_id"]),
                    "original_role_in_circuit": p["role_in_circuit"],
                },
            })

        if failures:
            unresolved_circuits.append({
                "mirror_circuit_id": cid,
                "circuit_name": circuit["circuit_name"],
                "source_atlas": circuit["source_atlas"],
                "failures": failures,
            })
            continue

        total_members = (
            len(region_members) + len(function_members) + len(connection_members)
        )
        confidence = circuit["confidence"]
        plans.append({
            "mirror_circuit_id": cid,
            "source_atlas": circuit["source_atlas"],
            "canonical_name_en": circuit["circuit_name"],
            "canonical_name_cn": circuit["name_cn"] or None,
            "circuit_type": mapped_type,
            "original_circuit_type": circuit["circuit_type"],
            "species": _CANONICAL_SPECIES,
            "granularity_level": _CANONICAL_GRANULARITY,
            "status": "proposed",
            "description": None,
            "confidence": float(confidence) if confidence is not None else None,
            "source_summary": {
                "source_atlas": circuit["source_atlas"] or None,
                "mirror_circuit_type": circuit["circuit_type"],
                "region_members": len(region_members),
                "function_members": len(function_members),
                "connection_members": len(connection_members),
            },
            "provenance_json": build_circuit_provenance(
                source_mirror_circuit_id=cid,
                source_region_ids=[m["provenance_json"]["original_mirror_region_id"] for m in region_members],
                source_connection_ids=[
                    m["provenance_json"]["original_mirror_membership_id"] for m in connection_members
                ],
                source_function_ids=[
                    m["provenance_json"]["original_mirror_function_id"] for m in function_members
                ],
                mapping_confidence=(
                    1.0 if total_members > 0 else None
                ),
            ),
            "region_members": region_members,
            "connection_members": connection_members,
            "function_members": function_members,
        })

    return {
        "dry_run": True,
        "stats": {
            "candidate_count": len(circuits),
            "aligned_count": len(plans),
            "unresolved_count": len(unresolved_circuits),
            "rejected_count": len(rejected_circuits),
            "region_members_aligned": region_member_stats["aligned"],
            "region_members_unresolved": region_member_stats["unresolved"],
            "function_members_aligned": function_member_stats["aligned"],
            "function_members_unresolved": function_member_stats["unresolved"],
            "projection_members_aligned": projection_member_stats["aligned"],
            "projection_members_unresolved": projection_member_stats["unresolved"],
        },
        "plans": plans,
        "unresolved_circuits": unresolved_circuits,
        "rejected_circuits": rejected_circuits,
    }
