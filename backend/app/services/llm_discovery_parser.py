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
  * ALLOWED, and the one exception that is not formatting: an UNKNOWN key whose
    value is structurally EMPTY — null, [], {} — is dropped before validation,
    judged against the field set of the object's OWN type. See
    ``_sanitize_benign_empty_extras``. Region-only and null-only was the previous
    form of this rule; the generic form subsumes it exactly (a region with an
    unknown null key is the special case), so the region-specific repair was
    removed rather than kept beside it. Every removal is logged.
  * ALLOWED, and the second exception: a warning `code` that is an explicitly
    approved LEXICAL ALIAS of a canonical warning code is renamed to the
    canonical one — see ``WARNING_CODE_ALIASES``. The map is closed and exact;
    there is no matching of any kind, so a code nobody approved still fails.
  * FORBIDDEN, because it would manufacture scientific content: inventing a
    missing connection (the legacy `no_connections` injection), inferring
    direction, creating region candidates, replacing missing circuit members,
    fabricating source hints, guessing canonical ids, or rewriting an enum.

A structurally invalid response FAILS. It is never patched into validity. What
the second bullet permits is the removal of a key that says nothing; every key
that says anything at all is still the model's to get right, and still fails.
"""
from __future__ import annotations

import logging

from app.schemas.llm_discovery import (
    HUMAN_TAXON_ID,
    MIN_CIRCUIT_REGION_REFS,
    SEED_REF,
    DiscoveryWarning,
    DiscoveryWarningCode,
    LlmDiscoveryParseResult,
    LlmDiscoveryResponse,
    CircuitCandidate,
    ConnectionCandidate,
    FunctionCandidate,
    RegionCandidate,
)
from app.services.llm_json_utils import extract_json_object_from_text

logger = logging.getLogger(__name__)

#: Explicit LEXICAL ALIASES of canonical warning codes, and nothing else.
#:
#: Each entry is a near-miss a model has actually produced for a code that
#: already exists. They are the same warning about the same thing, spelled
#: differently — a spelling difference is not a scientific concept, so the
#: canonical vocabulary stays exactly as it is and the alias is mapped onto it
#: rather than added beside it.
#:
#: This is a FIXED MAP, deliberately not a matcher. No prefix, substring,
#: case-insensitive, edit-distance or semantic matching exists or may be added:
#: every one of those would eventually accept a code nobody approved, and the
#: strict schema would stop meaning anything. An unlisted code — including a
#: plausible neighbour of a listed one — still fails validation.
WARNING_CODE_ALIASES: dict[str, str] = {
    "AMBIGUOUS_DIRECTIONALITY": "AMBIGUOUS_DIRECTION",
}


def _normalize_warning_code_aliases(parsed: object) -> tuple[object, int]:
    """Rename approved warning-code aliases to their canonical spelling.

    Returns ``(parsed, renamed_count)``. Only the ``code`` value is touched: a
    warning's message, local_id and position are the model's words and are left
    exactly as written. If nothing matched, the ORIGINAL object is returned, so
    an untouched response is never copied or reshaped by passing through here.
    """
    if not isinstance(parsed, dict):
        return parsed, 0
    warnings = parsed.get("warnings")
    if not isinstance(warnings, list):
        return parsed, 0

    renamed = 0
    out: list[object] = []
    for warning in warnings:
        if isinstance(warning, dict):
            code = warning.get("code")
            if isinstance(code, str) and code in WARNING_CODE_ALIASES:
                warning = {**warning, "code": WARNING_CODE_ALIASES[code]}
                renamed += 1
        out.append(warning)

    if not renamed:
        return parsed, 0
    return {**parsed, "warnings": out}, renamed


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


#: The four typed arrays of the response, each mapped to the type that
#: DECLARES its fields. The field sets are read FROM the contract rather than
#: restated, so a field added to a candidate is automatically protected here.
#:
#: Named for the ARRAYS, not the layer: the parser must not reference the
#: Candidate/Mirror/Final database layers, and a constant called
#: `_CANDIDATE_...` would collide with the structural guard that enforces it.
_ARRAY_SCHEMAS: dict[str, type] = {
    "regions": RegionCandidate,
    "connections": ConnectionCandidate,
    "functions": FunctionCandidate,
    "circuits": CircuitCandidate,
}


def _is_benign_empty(value: object) -> bool:
    """True only for values that carry NO content.

    ``null``, ``[]`` and ``{}`` say nothing, so removing one removes nothing.
    Everything else is content, and stays where the model put it:

      * ``""`` is excluded because an empty STRING is a stated value that happens
        to be blank, and V1 of this policy deliberately does not decide which of
        those are meaningless;
      * ``0`` and ``false`` are excluded because they are Python-falsy but are
        real values — a truthiness test here would silently swallow them.

    That is why this is an explicit identity/emptiness check and not ``not value``.
    """
    if value is None:
        return True
    return isinstance(value, (list, dict)) and not value


def _sanitize_benign_empty_extras(parsed: object) -> tuple[object, list[tuple[str, str | None, tuple[str, ...]]]]:
    """Drop UNKNOWN fields whose value is structurally EMPTY, per object type.

    Why this exists
    ---------------
    A live Round-12 pass was discarded in full — every circuit in it — because a
    CONNECTION carried `connection_refs: []` and `connection_refs_placeholder:
    null`. Both are unknown on a Connection (the first is a Circuit field, which
    is exactly why it looked plausible), and both are empty. Under RECALL FIRST,
    an empty auxiliary key must not cost a round.

    Why it is this narrow
    ---------------------
    A field is dropped only when it is BOTH unknown to the object's own type AND
    structurally empty. An unknown field holding any content — a string, a
    number, a boolean, a non-empty array or object — is left exactly where the
    model put it and still fails ``extra="forbid"``, because it carries meaning
    this contract does not understand. The schema is still the authority; this
    only removes the cases where there is nothing for it to be authoritative
    about.

    The collision that motivates the rule is real and tested: `connection_refs`
    is DECLARED on CircuitCandidate and UNKNOWN on ConnectionCandidate. On a
    Circuit it is preserved untouched, empty or not. On a Connection, an empty
    one is dropped and a populated one fails — the same key, judged by the type
    that actually declares it.
    """
    if not isinstance(parsed, dict):
        return parsed, []

    dropped: list[tuple[str, str | None, tuple[str, ...]]] = []
    out = dict(parsed)
    changed = False

    for array_name, model in _ARRAY_SCHEMAS.items():
        items = out.get(array_name)
        if not isinstance(items, list):
            continue
        declared = frozenset(model.model_fields)
        cleaned: list[object] = []
        for item in items:
            if not isinstance(item, dict):
                cleaned.append(item)
                continue
            unknown_empty = [
                key for key, value in item.items()
                if key not in declared and _is_benign_empty(value)
            ]
            if not unknown_empty:
                cleaned.append(item)
                continue
            cleaned.append(
                {k: v for k, v in item.items() if k not in unknown_empty}
            )
            changed = True
            raw_id = item.get("local_id")
            dropped.append(
                (array_name, raw_id if isinstance(raw_id, str) else None,
                 tuple(unknown_empty))
            )
        out[array_name] = cleaned

    if not changed:
        return parsed, []
    return out, dropped


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

    # Narrow pre-validation normalization: UNKNOWN, structurally EMPTY extras,
    # per object type. Anything with content survives this and is still rejected
    # by the strict schema below, which remains the authority.
    parsed, benign_extras = _sanitize_benign_empty_extras(parsed)
    for array_name, local_id, fields in benign_extras:
        logger.info(
            "[discovery-parser][benign-extra-drop] object_type=%s local_id=%s"
            " fields=%s",
            array_name.rstrip("s"), local_id, ",".join(fields),
        )
    if benign_extras:
        logger.info(
            "[discovery-parser][benign-extra-drop] total_objects=%s total_fields=%s",
            len(benign_extras), sum(len(f) for _, _, f in benign_extras),
        )

    # Approved warning-code aliases -> canonical spelling. Runs BEFORE the strict
    # validation for the same reason: the schema stays the authority, and an
    # unapproved code still fails there.
    parsed, aliases_renamed = _normalize_warning_code_aliases(parsed)
    if aliases_renamed:
        # Logged, not turned into a warning: adding one would alter the model's
        # own warning list, and a rename inside its vocabulary is not a new
        # observation about the science.
        logger.info(
            "[discovery-parser] normalized %s warning-code alias(es)", aliases_renamed
        )

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
