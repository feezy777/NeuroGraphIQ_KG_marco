"""Phase 3B.6 — strict JSON Schema projection. Pure functions, no network, no DB.

The projection exists to satisfy one provider rule (strict mode wants `required`
to enumerate every property) without ever weakening the scientific contract.
The tests below are mostly about what the projection must NOT do.
"""
from __future__ import annotations

import copy
import json

import pytest

from app.schemas.llm_discovery import LlmDiscoveryResponse
from app.services.deepseek_schema_projection import (
    audit_strict_compatibility,
    iter_objects,
    project_for_deepseek_strict,
    strict_enforcement_coverage,
)

CANDIDATE_DEFS = ("RegionCandidate", "ConnectionCandidate", "FunctionCandidate", "CircuitCandidate")


@pytest.fixture()
def canonical() -> dict:
    return LlmDiscoveryResponse.model_json_schema()


@pytest.fixture()
def projected(canonical) -> dict:
    return project_for_deepseek_strict(canonical)


def _properties_by_path(schema: dict) -> dict[str, dict]:
    """{(owner, field): property schema} across the whole document."""
    out: dict[str, dict] = {}
    for obj in iter_objects(schema):
        for name, prop in obj["properties"].items():
            out[f"{obj.get('title', '?')}.{name}"] = prop
    return out


# ===========================================================================
# §10.1 / §10.13 — the canonical schema is never touched
# ===========================================================================
def test_1_the_canonical_schema_is_not_mutated(canonical):
    snapshot = copy.deepcopy(canonical)
    project_for_deepseek_strict(canonical)
    assert canonical == snapshot


def test_13_canonical_before_equals_canonical_after(canonical):
    before = json.dumps(canonical, sort_keys=True)
    project_for_deepseek_strict(canonical)
    assert json.dumps(LlmDiscoveryResponse.model_json_schema(), sort_keys=True) == before


def test_2_the_projection_is_deterministic(canonical):
    first = json.dumps(project_for_deepseek_strict(canonical), sort_keys=True)
    second = json.dumps(project_for_deepseek_strict(canonical), sort_keys=True)
    assert first == second


# ===========================================================================
# §9 / §10.3-5 — strict compatibility
# ===========================================================================
def test_3_the_root_requires_all_of_its_properties(projected):
    assert set(projected["required"]) == set(projected["properties"])


def test_4_every_definition_requires_all_of_its_properties(projected):
    for obj in iter_objects(projected):
        assert set(obj.get("required") or []) == set(obj["properties"]), obj.get("title")


def test_5_every_object_closes_additional_properties(projected):
    for obj in iter_objects(projected):
        assert obj.get("additionalProperties") is False, obj.get("title")


def test_the_audit_reports_zero_mismatches_after_projection(projected):
    audit = audit_strict_compatibility(projected)
    assert audit["required_mismatch_count"] == 0
    assert audit["required_mismatches"] == []
    assert audit["additional_properties_open_count"] == 0


def test_the_audit_finds_every_mismatch_before_projection(canonical):
    """The control: the canonical schema is rejected for all 8 objects."""
    audit = audit_strict_compatibility(canonical)
    assert audit["object_count"] == 8
    assert audit["required_mismatch_count"] == 8


def test_the_traversal_reaches_nested_definitions(projected):
    """A regression guard: `$defs` is a name->schema MAP, not a sub-schema."""
    titles = {obj.get("title") for obj in iter_objects(projected)}
    assert "LlmDiscoveryResponse" in titles
    for name in CANDIDATE_DEFS + ("SourceHint", "SpeciesContext", "DiscoveryWarning"):
        assert name in titles, name


# ===========================================================================
# §3 / §10.6-7 — OMITTABLE IS NOT NULLABLE
# ===========================================================================
def test_6_a_canonically_nullable_field_keeps_its_null(canonical, projected):
    for name in CANDIDATE_DEFS:
        for field in ("rationale", "name_en", "hemisphere", "description"):
            canon = canonical["$defs"][name]["properties"].get(field)
            if canon is None:
                continue
            proj = projected["$defs"][name]["properties"][field]
            assert canon == proj, (name, field)
            assert {"type": "null"} in proj.get("anyOf", []), (name, field)


def test_7_no_field_gains_a_null_it_did_not_have(canonical, projected):
    """The whole point: a stricter `required` must not become a wider type."""
    for path, canon_prop in _properties_by_path(canonical).items():
        proj_prop = _properties_by_path(projected)[path]
        assert canon_prop == proj_prop, path
        if "anyOf" in canon_prop:
            assert sorted(canon_prop["anyOf"], key=json.dumps) == sorted(
                proj_prop["anyOf"], key=json.dumps
            ), path


def test_7b_a_defaulted_list_stays_a_list_and_is_simply_required(canonical, projected):
    """`warnings: list[...] = []` must become required-array, never nullable."""
    for container, field in (
        (projected, "warnings"),
        (projected, "regions"),
        (projected, "source_hints"),
    ):
        prop = container["properties"][field]
        assert prop["type"] == "array", field
        assert "anyOf" not in prop, field
        assert field in container["required"], field
    # and the canonical definition of the same field is untouched
    assert canonical["properties"]["warnings"] == projected["properties"]["warnings"]


def test_7c_a_defaulted_scalar_keeps_its_type_and_enum(canonical, projected):
    """`scope: ... = "UNKNOWN"` stays a plain enum string, not nullable."""
    proj = projected["$defs"]["SpeciesContext"]["properties"]["scope"]
    assert proj["type"] == "string"
    assert "anyOf" not in proj
    assert "scope" in projected["$defs"]["SpeciesContext"]["required"]
    assert proj == canonical["$defs"]["SpeciesContext"]["properties"]["scope"]


# ===========================================================================
# §6 / §10.8-11 — no scientific constraint is added, removed or rewritten
# ===========================================================================
def test_8_confidence_bounds_survive(canonical, projected):
    for name in CANDIDATE_DEFS:
        canon = canonical["$defs"][name]["properties"]["confidence"]
        proj = projected["$defs"][name]["properties"]["confidence"]
        assert proj["minimum"] == 0.0 and proj["maximum"] == 1.0, name
        assert canon == proj, name
        assert "confidence" in projected["$defs"][name]["required"], name


def test_9_enums_are_byte_identical(canonical, projected):
    for path, canon_prop in _properties_by_path(canonical).items():
        if "enum" not in canon_prop:
            continue
        assert _properties_by_path(projected)[path]["enum"] == canon_prop["enum"], path


def test_10_property_names_are_identical(canonical, projected):
    assert set(canonical["properties"]) == set(projected["properties"])
    assert set(canonical["$defs"]) == set(projected["$defs"]), "definitions must not move"
    for name in canonical["$defs"]:
        assert set(canonical["$defs"][name]["properties"]) == set(
            projected["$defs"][name]["properties"]
        ), name


def test_11_every_ref_target_still_exists(canonical, projected):
    def refs(schema) -> list[str]:
        found: list[str] = []
        for obj in iter_objects(schema):
            for prop in obj["properties"].values():
                text = json.dumps(prop)
                found += [t.split("/")[-1] for t in json.loads(text).get("$ref", "").split() if "$ref" in text]
        return found

    canonical_refs = refs(canonical)
    assert canonical_refs, "the schema must actually use $ref"
    for target in refs(projected):
        assert target in projected["$defs"], target


def test_12_species_context_is_present_and_required(projected):
    for name in ("ConnectionCandidate", "FunctionCandidate", "CircuitCandidate"):
        definition = projected["$defs"][name]
        assert "species_context" in definition["properties"], name
        assert "species_context" in definition["required"], name
    assert projected["$defs"]["SpeciesContext"]["required"] == ["scope", "taxon_ids"]


# ===========================================================================
# §7 / §8 / §16 — what this route still CANNOT enforce
# ===========================================================================
def test_13_the_local_id_pattern_is_still_not_enforceable(projected):
    """KNOWN GAP, unchanged by this phase and NOT papered over.

    The local-ID rule lives in a `@field_validator`, which Pydantic cannot
    project into JSON Schema. Injecting the regex here by hand would create a
    second authority, so it is deliberately left out: Prompt 1.2.0 and the
    Phase 3A parser remain its only gates.
    """
    coverage = strict_enforcement_coverage(projected)
    assert coverage["local_id_pattern"] is False
    for name in CANDIDATE_DEFS:
        assert "pattern" not in projected["$defs"][name]["properties"]["local_id"]


def test_14_the_projection_claims_only_what_the_schema_shows(projected):
    coverage = strict_enforcement_coverage(projected)
    assert coverage["required_fields"] is True
    assert coverage["extra_fields_closed"] is True
    assert coverage["confidence_bounds"] is True
    assert coverage["enum_constraints"] is True
    # cross-reference integrity and duplicate-id detection are parser-only and
    # must never be reported as provider-enforced
    assert "cross_reference" not in coverage
    assert "duplicate" not in coverage


def test_15_nothing_was_imported_that_would_make_this_impure():
    """No DB, no HTTP, no domain logic: it is a schema function."""
    import ast
    from pathlib import Path

    from app.services import deepseek_schema_projection as mod

    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8-sig"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert imported == {"__future__", "copy", "typing"}, imported
