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
  * ALLOWED, and the one exception that is not formatting: an UNKNOWN key on a
    region whose value is null is dropped before validation. The rule is
    Region-only and null-only — see ``_strip_null_region_extras`` — and the
    drop is reported as a warning, never made silently.
  * FORBIDDEN, because it would manufacture scientific content: inventing a
    missing connection (the legacy `no_connections` injection), inferring
    direction, creating region candidates, replacing missing circuit members,
    fabricating source hints, guessing canonical ids, or rewriting an enum.

A structurally invalid response FAILS. It is never patched into validity. What
the second bullet permits is the removal of a key that says nothing; every key
that says anything at all is still the model's to get right, and still fails.
"""
from __future__ import annotations

from app.schemas.llm_discovery import (
    HUMAN_TAXON_ID,
    MIN_CIRCUIT_REGION_REFS,
    SEED_REF,
    DiscoveryWarning,
    DiscoveryWarningCode,
    LlmDiscoveryParseResult,
    LlmDiscoveryResponse,
    RegionCandidate,
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


#: The keys a RegionCandidate declares. Read FROM the contract rather than
#: restated, so the schema stays the single authority for what a region may
#: carry; this set is used only to decide which keys are UNKNOWN.
_REGION_FIELDS: frozenset[str] = frozenset(RegionCandidate.model_fields)


def _strip_null_region_extras(
    parsed: object,
) -> tuple[object, list[DiscoveryWarning]]:
    """Drop UNKNOWN, null-valued keys from ``regions[]`` — and nothing else.

    Why this exists
    ---------------
    Under RECALL FIRST a region is mostly a SUPPORTING REFERENCE: circuits and
    connections point at regions by local_id, so regions exist to make that
    topology expressible. A live Round-4 continuation pass was thrown away in
    full — an otherwise valid response with ~15 circuits — because ONE region
    carried one unknown key set to null. An empty auxiliary key is not worth a
    whole round.

    Why it is this narrow
    ---------------------
    A key is dropped only when BOTH hold: it is not a RegionCandidate field,
    AND its value is None. An unknown key holding any content — a string, 0,
    false, a list — is left exactly where the model put it and still fails
    ``extra="forbid"``, because it carries meaning this contract does not
    understand and silently discarding meaning is precisely what the FORBIDDEN
    list above rules out. Connections, functions and circuits are not touched
    at all: only Region was relaxed, and only for null.

    The drop is reported, not silent. Strictness exists to surface drift, so
    trading a loud failure for a quiet deletion would be a bad deal; the caller
    gets a warning naming the region and the field.
    """
    if not isinstance(parsed, dict):
        return parsed, []
    regions = parsed.get("regions")
    if not isinstance(regions, list):
        return parsed, []

    warnings: list[DiscoveryWarning] = []
    cleaned: list[object] = []
    changed = False
    for region in regions:
        if not isinstance(region, dict):
            cleaned.append(region)
            continue
        dropped = [k for k, v in region.items() if k not in _REGION_FIELDS and v is None]
        if not dropped:
            cleaned.append(region)
            continue
        cleaned.append({k: v for k, v in region.items() if k not in dropped})
        changed = True
        raw_id = region.get("local_id")
        local_id = raw_id if isinstance(raw_id, str) else None
        for key in dropped:
            # `OTHER` because DiscoveryWarningCode is the MODEL's vocabulary and
            # is rendered into the prompt: a parser-only code would extend a
            # frozen vocabulary and teach the model to emit it. The stable token
            # lives in the message instead.
            warnings.append(
                _warn(
                    "OTHER",
                    f"REGION_NULL_EXTRA_IGNORED: region dropped unknown "
                    f"null-valued field '{key}'",
                    local_id,
                )
            )

    if not changed:
        return parsed, []
    return {**parsed, "regions": cleaned}, warnings


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
        if taxon and taxon != str(HUMAN_TAXON_ID):
            warnings.append(
                _warn(
                    "CROSS_SPECIES_UNCERTAINTY",
                    f"region {region.local_id} carries non-human taxon {taxon}",
                    region.local_id,
                )
            )

    # Candidate species BASIS: a human seed does not make a discovered claim
    # human-established. Anything that does not positively declare HUMAN support
    # is flagged — UNKNOWN included, because an unstated basis must stay visible
    # instead of being read as human. These are structural discovery warnings,
    # not knowledge validation.
    candidates = (
        *((c, "connection") for c in response.connections),
        *((f, "function") for f in response.functions),
        *((c, "circuit") for c in response.circuits),
    )
    for candidate, kind in candidates:
        scope = candidate.species_context.scope
        if scope != "HUMAN":
            warnings.append(
                _warn(
                    "CROSS_SPECIES_UNCERTAINTY",
                    f"{kind} {candidate.local_id} species scope is {scope}",
                    candidate.local_id,
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

    # Narrow pre-validation normalization: unknown NULL extras on regions only.
    # Non-null unknowns survive this and are still rejected by the strict
    # schema below, which remains the authority.
    parsed, null_extra_warnings = _strip_null_region_extras(parsed)

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
        validation_warnings=[*response.warnings, *null_extra_warnings, *warnings],
    )
