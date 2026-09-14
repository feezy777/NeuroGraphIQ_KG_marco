"""Phase 3A — parse and structurally validate one raw LLM discovery response.

Responsibilities, and nothing else:

    parse raw model text -> normalize superficial JSON formatting
    -> validate against LlmDiscoveryResponse -> cross-reference validation
    -> structured result or typed rejection

It does NOT canonicalize regions, touch a database, write candidates, call a
provider or search literature. No DB session is accepted anywhere in this
module: it is a pure function over (text, seed id).

Repair policy (deliberate and narrow):
  * ALLOWED, because it changes formatting only: BOM / control-char cleanup,
    markdown code-fence removal, whitespace, and extracting the single
    unambiguous top-level JSON object from surrounding prose.
  * FORBIDDEN, because it would manufacture scientific content: inventing a
    missing connection (the legacy `no_connections` injection), inferring
    direction, creating region candidates, replacing missing circuit members,
    fabricating source hints, guessing canonical ids, or rewriting an enum.

A structurally invalid response FAILS. It is never patched into validity.
"""
from __future__ import annotations

from app.schemas.llm_discovery import (
    MIN_CIRCUIT_REGION_REFS,
    SEED_REF,
    DiscoveryWarning,
    DiscoveryWarningCode,
    LlmDiscoveryParseResult,
    LlmDiscoveryResponse,
)
from app.services.llm_json_utils import extract_json_object_from_text

# Rejection reasons (machine-readable, stable).
ERR_INVALID_JSON = "INVALID_JSON"
ERR_SCHEMA_INVALID = "SCHEMA_INVALID"
ERR_SEED_MISMATCH = "SEED_MISMATCH"
ERR_DUPLICATE_LOCAL_ID = "DUPLICATE_LOCAL_ID"
ERR_DANGLING_REGION_REF = "DANGLING_REGION_REF"
ERR_DANGLING_CONNECTION_REF = "DANGLING_CONNECTION_REF"
ERR_DANGLING_FUNCTION_REF = "DANGLING_FUNCTION_REF"
ERR_DANGLING_CIRCUIT_REF = "DANGLING_CIRCUIT_REF"
ERR_CIRCUIT_TOO_FEW_REGIONS = "CIRCUIT_TOO_FEW_REGIONS"


def _warn(
    code: DiscoveryWarningCode, message: str, local_id: str | None = None
) -> DiscoveryWarning:
    return DiscoveryWarning(code=code, message=message, local_id=local_id)


def _duplicate_local_ids(response: LlmDiscoveryResponse) -> list[str]:
    """Locally unique ids, across ALL candidate types (cross-type reuse is also
    rejected: a bare `region_1` in a `connection_refs` list would be ambiguous)."""
    seen: set[str] = set()
    dupes: list[str] = []
    for local_id in response.all_local_ids():
        if local_id in seen and local_id not in dupes:
            dupes.append(local_id)
        seen.add(local_id)
    return dupes


def validate_cross_references(
    response: LlmDiscoveryResponse,
) -> tuple[list[str], list[DiscoveryWarning]]:
    """Resolve every reference inside one response.

    Returns ``(errors, warnings)``. Errors mean the response is structurally
    broken (reject); warnings mean it is acceptable but noteworthy.
    """
    errors: list[str] = []
    warnings: list[DiscoveryWarning] = []

    dupes = _duplicate_local_ids(response)
    if dupes:
        errors.append(f"{ERR_DUPLICATE_LOCAL_ID}: {', '.join(sorted(dupes))}")

    region_ids = response.region_local_ids()
    connection_ids = {c.local_id for c in response.connections}
    function_ids = {f.local_id for f in response.functions}

    def region_targets_ok(refs: list[str]) -> list[str]:
        return [r for r in refs if r != SEED_REF and r not in region_ids]

    # 1 / 4. Connection endpoints must resolve to SEED or a declared region.
    for conn in response.connections:
        bad = region_targets_ok([conn.source_ref, conn.target_ref])
        if bad:
            errors.append(f"{ERR_DANGLING_REGION_REF}: {conn.local_id} -> {', '.join(bad)}")
        if conn.directionality == "UNKNOWN":
            warnings.append(
                _warn(
                    "AMBIGUOUS_DIRECTION",
                    f"connection {conn.local_id} has unknown directionality",
                    conn.local_id,
                )
            )

    # 2. Function references.
    for func in response.functions:
        bad_r = region_targets_ok(func.related_region_refs)
        if bad_r:
            errors.append(f"{ERR_DANGLING_REGION_REF}: {func.local_id} -> {', '.join(bad_r)}")
        bad_c = [c for c in func.related_circuit_refs if c not in {
            x.local_id for x in response.circuits
        }]
        if bad_c:
            errors.append(
                f"{ERR_DANGLING_CIRCUIT_REF}: {func.local_id} -> {', '.join(bad_c)}"
            )

    # 3 / 5 / 6. Circuit integrity.
    for circuit in response.circuits:
        bad_r = region_targets_ok(circuit.region_refs)
        if bad_r:
            errors.append(f"{ERR_DANGLING_REGION_REF}: {circuit.local_id} -> {', '.join(bad_r)}")
        bad_c = [c for c in circuit.connection_refs if c not in connection_ids]
        if bad_c:
            errors.append(
                f"{ERR_DANGLING_CONNECTION_REF}: {circuit.local_id} -> {', '.join(bad_c)}"
            )
        bad_f = [f for f in circuit.function_refs if f not in function_ids]
        if bad_f:
            errors.append(
                f"{ERR_DANGLING_FUNCTION_REF}: {circuit.local_id} -> {', '.join(bad_f)}"
            )

        distinct_regions = {r for r in circuit.region_refs}
        if len(distinct_regions) < MIN_CIRCUIT_REGION_REFS:
            errors.append(
                f"{ERR_CIRCUIT_TOO_FEW_REGIONS}: {circuit.local_id} "
                f"({len(distinct_regions)} < {MIN_CIRCUIT_REGION_REFS})"
            )
        if not circuit.connection_refs:
            # Preserved, NOT patched: we never fabricate the missing connection.
            warnings.append(
                _warn(
                    "CIRCUIT_WITHOUT_CONNECTION",
                    f"circuit {circuit.local_id} declares no connection reference",
                    circuit.local_id,
                )
            )

    # Cross-species representation: the seed is human (9606). Anything else is
    # preserved explicitly and flagged — never silently treated as human fact.
    for region in response.regions:
        taxon = (region.species_taxon_id or "").strip()
        if taxon and taxon != "9606":
            warnings.append(
                _warn(
                    "CROSS_SPECIES_UNCERTAINTY",
                    f"region {region.local_id} carries non-human taxon {taxon}",
                    region.local_id,
                )
            )

    return errors, warnings


def parse_llm_discovery_response(
    raw: str | dict | list, *, seed_entity_id: str
) -> LlmDiscoveryParseResult:
    """Parse one raw model response into the structured discovery contract.

    `seed_entity_id` is the id that was REQUESTED. A response echoing a
    different seed is rejected rather than silently corrected: that mismatch is
    exactly the prompt/model drift this contract exists to catch.
    """
    if isinstance(raw, (dict, list)):
        parsed: object = raw
    else:
        parsed, err = extract_json_object_from_text(raw)
        if parsed is None:
            return LlmDiscoveryParseResult(error=f"{ERR_INVALID_JSON}: {err}")

    try:
        response = LlmDiscoveryResponse.model_validate(parsed)
    except Exception as exc:  # pydantic ValidationError (schema-shape failure)
        return LlmDiscoveryParseResult(error=f"{ERR_SCHEMA_INVALID}: {exc}")

    if response.seed_entity_id != seed_entity_id:
        return LlmDiscoveryParseResult(
            error=(
                f"{ERR_SEED_MISMATCH}: response declares '{response.seed_entity_id}' "
                f"but '{seed_entity_id}' was requested"
            )
        )

    errors, warnings = validate_cross_references(response)
    if errors:
        return LlmDiscoveryParseResult(
            error=f"{ERR_SCHEMA_INVALID}: " + "; ".join(errors),
        )

    return LlmDiscoveryParseResult(
        data=response,
        validation_warnings=[*response.warnings, *warnings],
    )
