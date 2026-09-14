"""Phase 3B.6 — project a canonical Pydantic JSON Schema into the STRICT subset
DeepSeek's Responses API accepts.

Why this exists: DeepSeek strict mode rejects any object whose ``required`` does
not enumerate every one of its ``properties`` ("Required properties must match
all properties in the object"). Pydantic expresses an optional field by simply
omitting it from ``required``, so a canonical schema is systematically rejected
even though it is perfectly valid JSON Schema.

The projection changes ONE thing: which fields are listed as required.

    OMITTABLE IS NOT NULLABLE.

That distinction is the whole design. The obvious-looking move — rewrite every
optional field as ``type: [<original>, "null"]`` — is WRONG here, because it
would let the provider accept an answer the canonical contract rejects:

    "regions": null      provider: satisfies the schema
                         Pydantic: ValidationError (regions is list[...], not
                         Optional[list[...]])

So a field that was omittable only because it had a default keeps its canonical
type and simply becomes required. A field the contract itself allows to be null
already carries ``anyOf: [..., {"type": "null"}]`` and is left exactly as is.

The invariant this buys:

    anything the provider accepts is also canonical-Pydantic-valid

Pure function. No database, no HTTP, no domain logic, no mutation of the input.
The canonical schema stays the single authority: no constraint is ever added,
removed or rewritten here.
"""
from __future__ import annotations

import copy
from typing import Any

#: Keys whose value is a list of sub-schemas.
_SUBSCHEMA_LISTS = ("anyOf", "oneOf", "allOf", "prefixItems")
#: Keys whose value is a single sub-schema.
_SUBSCHEMA_SINGLE = ("items", "additionalProperties", "not", "contains")
#: Keys whose value is a MAP of name -> sub-schema. Missing `$defs` here was a
#: real bug: Pydantic puts every nested model in `$defs`, so without this the
#: traversal never reached a single candidate definition and the projection
#: silently left the schema still-rejected.
_SUBSCHEMA_MAPS = ("$defs", "definitions", "patternProperties", "dependentSchemas")


def _map_children(value: Any, fn) -> Any:
    if not isinstance(value, dict):
        return fn(value)
    return {name: fn(sub) for name, sub in value.items()}


def project_for_deepseek_strict(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a projected, strict-compatible COPY of ``schema``.

    Deterministic: the same input always yields the same output. The input is
    never mutated.
    """
    return _project(copy.deepcopy(schema))


def _project(node: Any) -> Any:
    if isinstance(node, list):
        return [_project(item) for item in node]
    if not isinstance(node, dict):
        return node

    projected: dict[str, Any] = {}
    for key, value in node.items():
        if key in _SUBSCHEMA_LISTS and isinstance(value, list):
            projected[key] = [_project(item) for item in value]
        elif key in _SUBSCHEMA_MAPS:
            projected[key] = _map_children(value, _project)
        elif key in _SUBSCHEMA_SINGLE:
            projected[key] = _project(value)
        else:
            projected[key] = value

    properties = projected.get("properties")
    if isinstance(properties, dict):
        # Union, never replace: if the canonical schema marked something required
        # that is not in `properties` (an invalid schema), dropping it here would
        # be this module silently changing the contract.
        merged = list(properties.keys())
        for name in node.get("required") or []:
            if name not in merged:
                merged.append(name)
        projected["required"] = merged
        projected["additionalProperties"] = False
    return projected


def iter_objects(schema: Any) -> list[dict[str, Any]]:
    """Every object definition in a schema, depth-first (read-only)."""
    found: list[dict[str, Any]] = []
    if isinstance(schema, list):
        for item in schema:
            found.extend(iter_objects(item))
    elif isinstance(schema, dict):
        if isinstance(schema.get("properties"), dict):
            found.append(schema)
        for key, value in schema.items():
            if key in _SUBSCHEMA_LISTS or key in _SUBSCHEMA_SINGLE:
                found.extend(iter_objects(value))
            elif key in _SUBSCHEMA_MAPS and isinstance(value, dict):
                for sub in value.values():
                    found.extend(iter_objects(sub))
    return found


def audit_strict_compatibility(schema: dict[str, Any]) -> dict[str, Any]:
    """Count objects that would still be rejected by strict mode (read-only)."""
    objects = iter_objects(schema)
    mismatches = [
        {
            "properties": sorted(obj["properties"]),
            "required": sorted(obj.get("required") or []),
            "missing": sorted(set(obj["properties"]) - set(obj.get("required") or [])),
        }
        for obj in objects
        if set(obj.get("required") or []) != set(obj["properties"])
    ]
    not_closed = [
        sorted(obj["properties"])
        for obj in objects
        if obj.get("additionalProperties") is not False
    ]
    return {
        "object_count": len(objects),
        "required_mismatch_count": len(mismatches),
        "required_mismatches": mismatches,
        "additional_properties_open_count": len(not_closed),
        "additional_properties_open": not_closed,
    }


def strict_enforcement_coverage(schema: dict[str, Any]) -> dict[str, bool]:
    """What the PROJECTED schema actually constrains, read from the schema.

    Deliberately computed rather than asserted: whether a constraint is
    enforceable is a property of the generated schema, not of our intentions.
    """
    objects = iter_objects(schema)
    candidates = [
        obj
        for obj in objects
        if "local_id" in obj.get("properties", {})
        and "confidence" in obj.get("properties", {})
    ]
    return {
        "required_fields": all(
            set(obj.get("required") or []) == set(obj["properties"]) for obj in objects
        ),
        "extra_fields_closed": all(
            obj.get("additionalProperties") is False for obj in objects
        ),
        "confidence_bounds": bool(candidates)
        and all(
            "minimum" in obj["properties"]["confidence"]
            and "maximum" in obj["properties"]["confidence"]
            for obj in candidates
        ),
        "enum_constraints": any("enum" in obj.get("properties", {}).get("scope", {}) for obj in objects),
        # NOT enforceable: the canonical schema carries no `pattern`, because
        # local-ID validation is a @field_validator and Pydantic cannot project
        # a validator into JSON Schema.
        "local_id_pattern": all(
            "pattern" in obj["properties"]["local_id"] for obj in candidates
        )
        if candidates
        else False,
    }
