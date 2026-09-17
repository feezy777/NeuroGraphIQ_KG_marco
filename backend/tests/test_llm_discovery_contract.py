"""Phase 3A — LLM Discovery structured contract, prompt and parser.

Pure functions only: no database, no provider, no network, no lifecycle. The
whole suite runs in-memory, which is itself part of the contract being tested.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from app.prompts import llm_discovery_prompt as prompt_mod
from app.schemas.llm_discovery import (
    CIRCUIT_TOPOLOGY_HINTS,
    CONNECTION_DIRECTIONALITIES,
    CONNECTION_TYPES,
    CANDIDATE_EVIDENCE_STATUS,
    CANDIDATE_KNOWLEDGE_STATUS,
    CANDIDATE_SOURCE_TYPE,
    DISCOVERY_WARNING_CODES,
    LOCAL_ID_PATTERN,
    REGION_RELATIONS_TO_SEED,
    SCHEMA_VERSION,
    SEED_REF,
    SPECIES_SCOPES,
    CircuitCandidate,
    ConnectionCandidate,
    DiscoveryWarning,
    FunctionCandidate,
    LlmDiscoveryInput,
    LlmDiscoveryResponse,
    RegionCandidate,
    SourceHint,
    SpeciesContext,
    is_local_candidate_id,
)
from app.services import llm_discovery_parser as parser
from app.services.llm_json_utils import extract_json_object_from_text

SEED_ID = "NGIQ-BR-00000247"
PARSER_PATH = Path(parser.__file__)
SCHEMA_PATH = Path(prompt_mod.__file__).parent.parent / "schemas" / "llm_discovery.py"


def seed() -> LlmDiscoveryInput:
    return LlmDiscoveryInput(
        seed_entity_id=SEED_ID,
        seed_name_en="Left Thalamus",
        seed_name_zh="左丘脑",
        seed_granularity_level="G1_MACRO",
        seed_hemisphere="left",
        species_taxon_id="9606",
        source_atlas_names=["Human Brainnetome Atlas"],
    )


def payload(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "seed_entity_id": SEED_ID,
        "summary": "candidate hypotheses",
        "regions": [],
        "connections": [],
        "functions": [],
        "circuits": [],
        "source_hints": [],
        "warnings": [],
    }
    base.update(over)
    return base


def parse(data: dict[str, Any], *, seed_id: str = SEED_ID) -> parser.LlmDiscoveryParseResult:
    return parser.parse_llm_discovery_response(data, seed_entity_id=seed_id)


def parse_text(text: str, *, seed_id: str = SEED_ID) -> parser.LlmDiscoveryParseResult:
    return parser.parse_llm_discovery_response(text, seed_entity_id=seed_id)


def species(scope: str = "HUMAN", taxon_ids: list[int] | None = None) -> dict[str, Any]:
    """A species_context block. Defaults to an explicit HUMAN declaration."""
    return {"scope": scope, "taxon_ids": [9606] if taxon_ids is None else taxon_ids}


def region(local_id: str = "region_1", **over: Any) -> dict[str, Any]:
    base = {"local_id": local_id, "name": "Medial dorsal nucleus", "confidence": 0.6}
    base.update(over)
    return base


def connection(local_id: str = "connection_1", **over: Any) -> dict[str, Any]:
    base = {
        "local_id": local_id,
        "source_ref": SEED_REF,
        "target_ref": "region_1",
        "connection_type": "PROJECTION",
        "directionality": "DIRECTED",
        "confidence": 0.5,
        "species_context": species(),
    }
    base.update(over)
    return base


def function(local_id: str = "function_1", **over: Any) -> dict[str, Any]:
    base = {
        "local_id": local_id,
        "label": "Thalamic gating",
        "confidence": 0.4,
        "species_context": species(),
    }
    base.update(over)
    return base


def circuit(local_id: str = "circuit_1", **over: Any) -> dict[str, Any]:
    base = {
        "local_id": local_id,
        "name": "Thalamo-cortical pathway",
        "confidence": 0.5,
        "species_context": species(),
    }
    base.update(over)
    return base


# ===========================================================================
# §30 — VALID RESPONSES
# ===========================================================================
def test_1_minimal_valid_response():
    result = parse(payload(summary="nothing found"))
    assert result.ok, result.error
    assert result.data is not None
    assert result.data.seed_entity_id == SEED_ID
    assert result.data.schema_version == SCHEMA_VERSION


def test_2_valid_empty_discovery_response():
    """No candidates is a VALID structured result, not a parse failure."""
    result = parse(payload())
    assert result.ok, result.error
    assert result.validation_warnings == []
    data = result.data
    assert (data.regions, data.connections, data.functions, data.circuits) == ([], [], [], [])


def test_3_seed_to_region_projection():
    result = parse(
        payload(
            regions=[region("region_1")],
            connections=[connection("connection_1", connection_type="PROJECTION")],
        )
    )
    assert result.ok, result.error
    conn = result.data.connections[0]
    assert conn.source_ref == SEED_REF
    assert conn.target_ref == "region_1"
    assert conn.connection_type == "PROJECTION"


def test_4_multi_region_circuit_with_multiple_connections():
    result = parse(
        payload(
            regions=[region("region_1"), region("region_2"), region("region_3")],
            connections=[
                connection("connection_1", source_ref=SEED_REF, target_ref="region_1"),
                connection("connection_2", source_ref="region_1", target_ref="region_2"),
                connection("connection_3", source_ref="region_2", target_ref="region_3"),
            ],
            circuits=[
                {
                    "local_id": "circuit_1",
                    "name": "Thalamo-cortical loop",
                    "region_refs": [SEED_REF, "region_1", "region_2", "region_3"],
                    "connection_refs": ["connection_1", "connection_2", "connection_3"],
                    "topology_hint": "FEEDFORWARD",
                    "confidence": 0.55,
                    "species_context": species(),
                }
            ],
        )
    )
    assert result.ok, result.error
    circuit = result.data.circuits[0]
    assert circuit.topology_hint == "FEEDFORWARD"
    assert circuit.region_refs[0] == SEED_REF
    assert len(circuit.connection_refs) == 3
    # a feedforward circuit is a circuit: no closed loop was required
    assert circuit.topology_hint != "LOOP"


def test_5_reciprocal_pair():
    result = parse(
        payload(
            regions=[region("region_1"), region("region_2")],
            connections=[
                connection(
                    "connection_1",
                    source_ref="region_1",
                    target_ref="region_2",
                    directionality="DIRECTED",
                ),
                connection(
                    "connection_2",
                    source_ref="region_2",
                    target_ref="region_1",
                    directionality="DIRECTED",
                ),
            ],
            circuits=[
                {
                    "local_id": "circuit_1",
                    "name": "Reciprocal pair",
                    "region_refs": ["region_1", "region_2"],
                    "connection_refs": ["connection_1", "connection_2"],
                    "topology_hint": "RECIPROCAL",
                    "confidence": 0.4,
                    "species_context": species(),
                }
            ],
        )
    )
    assert result.ok, result.error
    assert result.data.circuits[0].topology_hint == "RECIPROCAL"


def test_6_circuit_with_functions():
    result = parse(
        payload(
            regions=[region("region_1"), region("region_2")],
            connections=[connection("connection_1", target_ref="region_1")],
            functions=[
                {
                    "local_id": "function_1",
                    "label": "Thalamic gating of cortical arousal",
                    "related_region_refs": ["region_1", "region_2"],
                    "related_circuit_refs": ["circuit_1"],
                    "confidence": 0.35,
                    "species_context": species(),
                }
            ],
            circuits=[
                {
                    "local_id": "circuit_1",
                    "name": "Arousal pathway",
                    "region_refs": [SEED_REF, "region_1"],
                    "connection_refs": ["connection_1"],
                    "function_refs": ["function_1"],
                    "topology_hint": "NETWORK",
                    "confidence": 0.45,
                    "species_context": species(),
                }
            ],
        )
    )
    assert result.ok, result.error
    assert result.data.circuits[0].function_refs == ["function_1"]
    assert result.data.functions[0].related_circuit_refs == ["circuit_1"]


def test_7_source_hints_are_preserved_as_unverified_metadata():
    result = parse(
        payload(
            source_hints=[
                {
                    "title": "Some remembered paper",
                    "authors": ["A. Author"],
                    "year": 2019,
                    "journal": "J. Neuro",
                    "pmid": "12345678",
                    "doi": "10.0/xyz",
                }
            ]
        )
    )
    assert result.ok, result.error
    hint = result.data.source_hints[0]
    assert hint.pmid == "12345678"
    # it is metadata, NOT evidence: nothing in the contract promotes a hint
    assert not hasattr(hint, "evidence_status")
    assert CANDIDATE_EVIDENCE_STATUS == "UNVERIFIED"


def test_8_non_human_species_is_preserved_and_flagged():
    result = parse(
        payload(
            regions=[region("region_1", species_taxon_id="10090", name="Mouse region")],
            connections=[connection("connection_1")],
        )
    )
    assert result.ok, result.error
    # preserved explicitly, not converted into a human fact
    assert result.data.regions[0].species_taxon_id == "10090"
    codes = [w.code for w in result.validation_warnings]
    assert "CROSS_SPECIES_UNCERTAINTY" in codes


def test_9_confidence_accepts_both_bounds():
    for value in (0.0, 1.0):
        result = parse(payload(regions=[region("region_1", confidence=value)]))
        assert result.ok, (value, result.error)
        assert result.data.regions[0].confidence == value


# ===========================================================================
# §31 — INVALID RESPONSES
# ===========================================================================
def test_10_invalid_json_rejected():
    result = parse_text("this is not json at all")
    assert not result.ok
    assert result.error.startswith(parser.ERR_INVALID_JSON)


def test_11_wrong_schema_version_rejected():
    result = parse(payload(schema_version="2.0"))
    assert not result.ok
    assert parser.ERR_SCHEMA_INVALID in result.error


def test_12_seed_entity_id_mismatch_rejected():
    result = parse(payload(seed_entity_id="NGIQ-BR-99999999"))
    assert not result.ok
    assert result.error.startswith(parser.ERR_SEED_MISMATCH)
    # not silently overwritten with the requested seed
    assert "NGIQ-BR-99999999" in result.error


def test_13_duplicate_local_id_rejected():
    result = parse(
        payload(
            regions=[region("region_1"), region("region_1")],
        )
    )
    assert not result.ok
    assert parser.ERR_DUPLICATE_LOCAL_ID in result.error


def test_13b_cross_type_local_id_reuse_is_also_rejected():
    result = parse(
        payload(
            regions=[region("connection_1")],
            connections=[connection("connection_1", target_ref="connection_1")],
        )
    )
    assert not result.ok
    assert parser.ERR_DUPLICATE_LOCAL_ID in result.error


def test_14_dangling_region_ref_rejected():
    result = parse(payload(connections=[connection("connection_1", target_ref="region_9")]))
    assert not result.ok
    assert parser.ERR_DANGLING_REGION_REF in result.error


def test_15_dangling_connection_ref_rejected():
    result = parse(
        payload(
            regions=[region("region_1"), region("region_2")],
            circuits=[
                {
                    "local_id": "circuit_1",
                    "name": "Broken",
                    "region_refs": ["region_1", "region_2"],
                    "connection_refs": ["connection_7"],
                    "confidence": 0.5,
                    "species_context": species(),
                }
            ],
        )
    )
    assert not result.ok
    assert parser.ERR_DANGLING_CONNECTION_REF in result.error


def test_16_dangling_function_ref_rejected():
    result = parse(
        payload(
            regions=[region("region_1"), region("region_2")],
            connections=[connection("connection_1")],
            circuits=[
                {
                    "local_id": "circuit_1",
                    "name": "Broken",
                    "region_refs": ["region_1", "region_2"],
                    "connection_refs": ["connection_1"],
                    "function_refs": ["function_9"],
                    "confidence": 0.5,
                    "species_context": species(),
                }
            ],
        )
    )
    assert not result.ok
    assert parser.ERR_DANGLING_FUNCTION_REF in result.error


def test_17_invalid_connection_type_rejected():
    result = parse(
        payload(
            regions=[region("region_1")],
            connections=[connection("connection_1", connection_type="SYNAPTIC")],
        )
    )
    assert not result.ok
    assert parser.ERR_SCHEMA_INVALID in result.error


def test_18_invalid_directionality_rejected():
    result = parse(
        payload(
            regions=[region("region_1")],
            connections=[connection("connection_1", directionality="BIDIRECTIONAL")],
        )
    )
    assert not result.ok
    assert parser.ERR_SCHEMA_INVALID in result.error


@pytest.mark.parametrize("value", [-0.01, -1.0, 1.01, 2])
def test_19_20_confidence_outside_unit_interval_rejected(value):
    result = parse(payload(regions=[region("region_1", confidence=value)]))
    assert not result.ok, value
    assert parser.ERR_SCHEMA_INVALID in result.error


@pytest.mark.parametrize(
    "invented",
    ["NGIQ-BR-00000002", "NGIQ-CONN-00000001", "NGIQ-CIRCUIT-00000001", "entity_pk_7"],
)
def test_21_invented_canonical_id_as_local_id_rejected(invented):
    result = parse(payload(regions=[region(invented)]))
    assert not result.ok, invented
    assert parser.ERR_SCHEMA_INVALID in result.error
    # and the guard itself is explicit
    assert not is_local_candidate_id(invented)
    assert is_local_candidate_id("region_1")


def test_22_circuit_structure_rules():
    """Frozen rule: <2 regions is an ERROR; 0 connections is a WARNING."""
    too_few = parse(
        payload(
            regions=[region("region_1")],
            circuits=[
                {
                    "local_id": "circuit_1",
                    "name": "One region is not a circuit",
                    "region_refs": ["region_1"],
                    "confidence": 0.5,
                    "species_context": species(),
                }
            ],
        )
    )
    assert not too_few.ok
    assert parser.ERR_CIRCUIT_TOO_FEW_REGIONS in too_few.error

    no_connection = parse(
        payload(
            regions=[region("region_1"), region("region_2")],
            circuits=[
                {
                    "local_id": "circuit_1",
                    "name": "Pathway without a declared connection",
                    "region_refs": [SEED_REF, "region_1", "region_2"],
                    "confidence": 0.5,
                    "species_context": species(),
                }
            ],
        )
    )
    assert no_connection.ok, no_connection.error
    codes = [w.code for w in no_connection.validation_warnings]
    assert "CIRCUIT_WITHOUT_CONNECTION" in codes
    # preserved, NOT patched
    assert no_connection.data.circuits[0].connection_refs == []


# ===========================================================================
# §32 — PARSER SAFETY
# ===========================================================================
def test_23_markdown_json_fence_is_stripped():
    body = json.dumps(payload(regions=[region("region_1")]))
    result = parse_text(f"```json\n{body}\n```")
    assert result.ok, result.error
    assert result.data.regions[0].local_id == "region_1"


def test_23b_utf8_bom_and_whitespace_are_stripped():
    body = json.dumps(payload())
    result = parse_text(f"﻿\n\n  {body}  \n")
    assert result.ok, result.error


def test_24_prose_around_one_clear_json_object_is_tolerated():
    """Only because the reused generic extractor picks the balanced object."""
    body = json.dumps(payload(regions=[region("region_1")]))
    result = parse_text(f"Sure! Here is the JSON you asked for:\n\n{body}\n\nHope that helps.")
    assert result.ok, result.error
    assert result.data.regions[0].local_id == "region_1"


def test_24b_prose_does_not_let_the_parser_recover_a_missing_field():
    """A prose hint never substitutes for a field the contract REQUIRES.

    This used `confidence` as the missing field. Region confidence is now
    optional (a live pass returned ten regions without it), so the field under
    test moved to one that is still required — the guarantee is unchanged, but
    it no longer rests on the field this phase deliberately made absent-able.
    """
    body = json.dumps(payload(regions=[{"local_id": "region_1", "confidence": 0.5}]))  # no name
    result = parse_text(f"Note: the region name was unclear.\n{body}")
    assert not result.ok, "a prose hint must not substitute for a required field"

    # ...and the same prose still cannot rescue a missing confidence on a type
    # where confidence IS required.
    body2 = json.dumps(payload(circuits=[{"local_id": "circuit_1", "name": "X"}]))
    assert not parse_text(f"Note: confidence was unclear.\n{body2}").ok


def test_25_parser_invents_no_missing_scientific_fields():
    """A circuit with no connections stays empty; nothing is fabricated."""
    result = parse(
        payload(
            regions=[region("region_1"), region("region_2")],
            circuits=[
                {
                    "local_id": "circuit_1",
                    "name": "No connections declared",
                    "region_refs": [SEED_REF, "region_1", "region_2"],
                    "confidence": 0.5,
                    "species_context": species(),
                }
            ],
        )
    )
    assert result.ok, result.error
    circuit = result.data.circuits[0]
    assert circuit.connection_refs == []
    assert len(result.data.connections) == 0
    # no direction, no region, no hint invented either
    assert circuit.topology_hint == "UNKNOWN"
    assert len(result.data.regions) == 2


def _code_only(path: Path) -> str:
    """Executable code and SQL only — docstrings legitimately name the boundaries."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            node.value = ""
    return ast.unparse(tree)


def test_26_parser_does_not_access_a_database():
    code = _code_only(PARSER_PATH).lower()
    for forbidden in (
        "session",
        "sqlalchemy",
        "get_db",
        "asyncsession",
        "select(",
        "insert",
        "update",
        "delete",
    ):
        assert forbidden not in code, f"parser must not reference {forbidden!r}"


def test_27_parser_does_not_call_a_provider_or_the_network():
    code = _code_only(PARSER_PATH).lower()
    src = PARSER_PATH.read_text(encoding="utf-8").lower()
    for forbidden in (
        "httpx",
        "requests",
        "complete_json",
        "complete_text",
        "get_llm_provider",
        "deepseek",
        "kimi",
        "openai",
        "socket",
        "aiohttp",
    ):
        assert forbidden not in code, f"parser must not reference {forbidden!r}"
        assert forbidden not in src, f"parser must not mention {forbidden!r}"


def test_28_parser_has_no_candidate_mirror_final_dependency():
    code = _code_only(PARSER_PATH).lower()
    for term in ("candidate_", "mirror_", "final_", "ranking_id", "task_type"):
        assert term not in code, f"parser must not reference {term!r}"
    # the parser does not even import the prompt builder
    assert "llm_discovery_prompt" not in code


def test_parser_module_is_a_pure_function_surface():
    """No DB session parameter and no I/O helper: input is (text|dict, seed id)."""
    tree = ast.parse(PARSER_PATH.read_text(encoding="utf-8"))
    public = {
        n.name: [a.arg for a in (*n.args.args, *n.args.kwonlyargs)]
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("_")
    }
    assert set(public) == {
        "parse_llm_discovery_response",
        "validate_cross_references",
    }, public
    # keyword-only: the seed id can never be passed positionally by accident
    assert public["parse_llm_discovery_response"] == ["raw", "seed_entity_id"]
    assert public["validate_cross_references"] == ["response"]


# ===========================================================================
# §33 — PROMPT CONTRACT
# ===========================================================================
def test_prompt_identity_is_frozen():
    assert prompt_mod.PROMPT_KEY == "knowledge_production.llm_discovery"
    # 1.1.0 — Phase 3B.2 root-shape hardened text. 1.0.0 identified the OLD
    # prompt that embedded the `top_level` schema description.
    assert prompt_mod.PROMPT_VERSION != "1.0.0"
    assert prompt_mod.PROMPT_VERSION == "1.2.0"


def test_prompt_parts_and_seed_context():
    built = prompt_mod.build_llm_discovery_prompt(seed())
    assert set(built) == {"prompt_key", "prompt_version", "system_prompt", "user_prompt"}
    # the version comes from the single authority, never re-typed at a call site
    assert built["prompt_version"] == prompt_mod.PROMPT_VERSION

    # seed context the model needs
    for fragment in (SEED_ID, "Left Thalamus", "左丘脑", "G1_MACRO", "9606"):
        assert fragment in built["user_prompt"], fragment
    assert SCHEMA_VERSION in built["user_prompt"]


def test_prompt_states_every_frozen_semantic_rule():
    # collapse the prompt's line wrapping so phrases can be matched reliably
    system = " ".join(prompt_mod.SYSTEM_PROMPT.lower().split())
    required = {
        "role/discovery": "discovery assistant",
        "hypothesis not fact": "hypothesis",
        "local-id instruction": "<type>_<number>",
        "no canonical id invention": "never invent a canonical id",
        "seed reference token": "seed",
        "projection distinction": "projection",
        "circuit not a closed loop": "not required to be closed loops",
        "confidence semantics": "[0.0, 1.0]",
        "unverified sources": "unverified",
        "no quotations": "do not provide quotations",
        "species qualification": "never silently convert animal knowledge into human",
        "no evidence claims": "do not fabricate evidence",
        "json only": "json only",
        "no markdown": "no markdown",
    }
    for label, needle in required.items():
        assert needle in system, f"prompt must state: {label}"


def test_prompt_vocabularies_match_the_typed_contract():
    user = prompt_mod.build_user_prompt(seed())
    for value in CONNECTION_TYPES + CONNECTION_DIRECTIONALITIES + CIRCUIT_TOPOLOGY_HINTS:
        assert value in user, value
    for value in REGION_RELATIONS_TO_SEED:
        assert value in user, value
    assert SEED_REF in user


def test_prompt_schema_description_is_derived_from_the_models():
    """Derived, not hand-written: adding a field cannot silently desync them.

    Phase 3B.2 changed the REPRESENTATION (a separate root skeleton plus a
    plain-text field reference) but not the invariant: both halves are rendered
    from the typed contract.
    """
    root = prompt_mod.build_response_root_skeleton()
    assert list(root) == list(LlmDiscoveryResponse.model_fields)

    definitions = prompt_mod.build_field_definitions()
    for model in (
        RegionCandidate,
        ConnectionCandidate,
        FunctionCandidate,
        CircuitCandidate,
        SourceHint,
        SpeciesContext,
        DiscoveryWarning,
    ):
        assert model.__name__ in definitions, model.__name__
        for name, label in prompt_mod.compact_output_schema(model).items():
            assert f"  {name}: {label}" in definitions, (model.__name__, name)
    # and the prompt actually carries it
    assert "RegionCandidate" in prompt_mod.build_user_prompt(seed())


def test_prompt_module_does_not_call_a_provider():
    code = _code_only(Path(prompt_mod.__file__)).lower()
    for forbidden in ("httpx", "complete_json", "complete_text", "get_llm_provider", "async def"):
        assert forbidden not in code, f"prompt builder must not contain {forbidden!r}"


# ===========================================================================
# Contract defaults (semantic separation for the FUTURE candidate layer)
# ===========================================================================
def test_candidate_defaults_are_frozen_and_persist_nothing():
    assert CANDIDATE_SOURCE_TYPE == "LLM_GENERATED"
    assert CANDIDATE_EVIDENCE_STATUS == "UNVERIFIED"
    assert CANDIDATE_KNOWLEDGE_STATUS == "CANDIDATE"
    # vocabulary is closed and small
    assert len(CONNECTION_TYPES) == 5 and len(CONNECTION_DIRECTIONALITIES) == 3
    assert len(DISCOVERY_WARNING_CODES) == 7


def test_summary_is_not_authority():
    """Machine logic reads the arrays; the summary is descriptive prose."""
    result = parse(
        payload(
            summary="I found 3 regions and a big circuit",
            regions=[],
            circuits=[],
        )
    )
    assert result.ok, result.error
    assert result.data.regions == []
    assert result.data.circuits == []


# ===========================================================================
# Phase 3A.1 — Candidate species context
# ===========================================================================
def test_a1_human_species_context_is_valid():
    result = parse(
        payload(
            regions=[region("region_1")],
            connections=[connection("connection_1", species_context=species("HUMAN", [9606]))],
        )
    )
    assert result.ok, result.error
    ctx = result.data.connections[0].species_context
    assert ctx.scope == "HUMAN" and ctx.taxon_ids == [9606]


def test_a2_non_human_mouse_species_context_is_valid():
    result = parse(
        payload(
            regions=[region("region_1")],
            connections=[connection("connection_1", species_context=species("NON_HUMAN", [10090]))],
        )
    )
    assert result.ok, result.error
    assert result.data.connections[0].species_context.taxon_ids == [10090]


def test_a3_mixed_species_context_is_valid():
    result = parse(
        payload(
            regions=[region("region_1")],
            circuits=[
                circuit(
                    region_refs=[SEED_REF, "region_1"],
                    species_context=species("MIXED", [9606, 10090]),
                )
            ],
        )
    )
    assert result.ok, result.error
    assert result.data.circuits[0].species_context.scope == "MIXED"


def test_a4_unknown_species_context_with_empty_taxa_is_valid():
    result = parse(
        payload(
            regions=[region("region_1")],
            functions=[function("function_1", species_context=species("UNKNOWN", []))],
        )
    )
    assert result.ok, result.error
    ctx = result.data.functions[0].species_context
    assert ctx.scope == "UNKNOWN" and ctx.taxon_ids == []


def test_a5_human_scope_with_only_non_human_taxon_is_rejected():
    result = parse(
        payload(
            regions=[region("region_1")],
            connections=[connection("connection_1", species_context=species("HUMAN", [10090]))],
        )
    )
    assert not result.ok
    assert parser.ERR_SCHEMA_INVALID in result.error
    assert "9606" in result.error


def test_a6_non_human_scope_with_only_human_taxon_is_rejected():
    result = parse(
        payload(
            regions=[region("region_1")],
            connections=[connection("connection_1", species_context=species("NON_HUMAN", [9606]))],
        )
    )
    assert not result.ok
    assert parser.ERR_SCHEMA_INVALID in result.error
    assert "NON_HUMAN" in result.error


def test_a6b_unknown_is_never_silently_promoted_to_human():
    """The default is UNKNOWN, and it survives parsing as UNKNOWN."""
    result = parse(
        payload(
            regions=[region("region_1")],
            connections=[
                connection("connection_1", species_context={"scope": "UNKNOWN", "taxon_ids": []})
            ],
        )
    )
    assert result.ok, result.error
    assert result.data.connections[0].species_context.scope == "UNKNOWN"
    # and a bare SpeciesContext() defaults to UNKNOWN, never HUMAN
    assert SpeciesContext().scope == "UNKNOWN"
    assert SpeciesContext().taxon_ids == []


def test_a7_non_human_connection_warns_cross_species():
    result = parse(
        payload(
            regions=[region("region_1")],
            connections=[connection("connection_1", species_context=species("NON_HUMAN", [10090]))],
        )
    )
    assert result.ok, result.error
    warns = [w for w in result.validation_warnings if w.code == "CROSS_SPECIES_UNCERTAINTY"]
    assert len(warns) == 1
    assert warns[0].local_id == "connection_1"
    assert "NON_HUMAN" in warns[0].message


def test_a8_unknown_circuit_species_warns_cross_species():
    result = parse(
        payload(
            regions=[region("region_1"), region("region_2")],
            circuits=[
                circuit(
                    region_refs=[SEED_REF, "region_1", "region_2"],
                    species_context=species("UNKNOWN", []),
                )
            ],
        )
    )
    assert result.ok, result.error
    warns = [w for w in result.validation_warnings if w.code == "CROSS_SPECIES_UNCERTAINTY"]
    assert [w.local_id for w in warns] == ["circuit_1"]
    assert "UNKNOWN" in warns[0].message


def test_a8b_human_candidates_do_not_warn():
    """A positive HUMAN declaration is the only case that stays quiet."""
    result = parse(
        payload(
            regions=[region("region_1"), region("region_2")],
            connections=[connection("connection_1")],
            functions=[function("function_1")],
            circuits=[
                circuit(region_refs=[SEED_REF, "region_1"], connection_refs=["connection_1"])
            ],
        )
    )
    assert result.ok, result.error
    assert [w for w in result.validation_warnings if w.code == "CROSS_SPECIES_UNCERTAINTY"] == []


# ---------------------------------------------------------------------------
# Phase 3A.1 — strict unknown-field policy
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "field, value",
    [("quotation", "the exact words"), ("evidence_text", "passage"), ("page", 12)],
)
def test_a11_quotation_like_candidate_fields_fail_explicitly(field, value):
    """Not silently dropped: an undefined field is a schema error."""
    body = region("region_1")
    body[field] = value
    result = parse(payload(regions=[body]))
    assert not result.ok, f"{field} must not be silently ignored"
    assert parser.ERR_SCHEMA_INVALID in result.error
    assert field in result.error


def test_a9_candidate_extra_field_is_rejected():
    result = parse(payload(connections=[connection("connection_1", strength="strong")]))
    assert not result.ok
    assert parser.ERR_SCHEMA_INVALID in result.error
    assert "strength" in result.error


def test_a10_top_level_extra_field_is_rejected():
    result = parse(payload(reasoning="a long chain of thought"))
    assert not result.ok
    assert parser.ERR_SCHEMA_INVALID in result.error
    assert "reasoning" in result.error


def test_a10b_extra_field_in_source_hint_and_warning_is_rejected():
    assert not parse(payload(source_hints=[{"title": "t", "offset": 3}])).ok
    assert not parse(
        payload(warnings=[{"code": "OTHER", "message": "m", "severity": "high"}])
    ).ok


def test_a10c_extra_species_context_field_is_rejected():
    result = parse(
        payload(
            regions=[region("region_1")],
            connections=[
                connection(
                    "connection_1",
                    species_context={
                        "scope": "HUMAN",
                        "taxon_ids": [9606],
                        "strain": "C57BL/6",
                    },
                )
            ],
        )
    )
    assert not result.ok
    assert "strain" in result.error


def test_a15_a_valid_response_must_state_species_context_explicitly():
    """Omitting it is an error — the model must state its basis, even as UNKNOWN."""
    body = connection("connection_1")
    del body["species_context"]
    result = parse(payload(regions=[region("region_1")], connections=[body]))
    assert not result.ok
    assert "species_context" in result.error


# ---------------------------------------------------------------------------
# Phase 3A.1 — prompt synchronisation
# ---------------------------------------------------------------------------
def test_a12_prompt_explains_species_context():
    system = " ".join(prompt_mod.SYSTEM_PROMPT.split())
    assert "species_context" in system
    for scope in SPECIES_SCOPES:
        assert scope in system, scope
    for taxon in ("9606", "10090"):
        assert taxon in system


def test_a13_prompt_states_that_a_human_seed_is_not_human_established_knowledge():
    system = " ".join(prompt_mod.SYSTEM_PROMPT.split())
    assert "seed does NOT imply that every discovered connection" in system
    assert "Never silently convert animal knowledge into HUMAN" in system


def test_a13b_prompt_requires_schema_only_fields():
    system = " ".join(prompt_mod.SYSTEM_PROMPT.split())
    assert "ONLY THE FIELDS IN THE SCHEMA" in system
    assert "Do NOT add quotations" in system
    assert "undefined field is treated as an error, not ignored" in system


def test_a14_compact_schema_automatically_includes_species_context():
    for model in (ConnectionCandidate, FunctionCandidate, CircuitCandidate):
        assert "species_context" in prompt_mod.compact_output_schema(model), model.__name__
    # the referenced type is described too, so the model can produce it
    species = prompt_mod.compact_output_schema(SpeciesContext)
    assert "scope" in species
    assert "taxon_ids" in species
    definitions = prompt_mod.build_field_definitions()
    assert "SpeciesContext" in definitions
    assert "species_context" in definitions
    user = prompt_mod.build_user_prompt(seed())
    assert "SpeciesContext" in user
    for scope in SPECIES_SCOPES:
        assert scope in user, scope


# ---------------------------------------------------------------------------
# Phase 3B.2 — response-Root shape hardening
# ---------------------------------------------------------------------------
# A real deepseek-flash smoke (Phase 3B.1) returned `top_level` and a top-level
# JSON array, because the prompt showed the schema description AS a JSON object
# that looked exactly like an answer. These tests freeze the fix: one explicit
# root, an explicitly forbidden envelope, and no ambiguity about which half of
# the prompt is the answer.
def _user_prompt() -> str:
    return prompt_mod.build_user_prompt(seed())


def _collapsed() -> str:
    return " ".join(_user_prompt().split())


def test_b1_prompt_requires_the_root_to_be_a_json_object():
    text = _collapsed()
    assert "Return exactly ONE JSON object" in text
    assert "The root MUST be an object" in text


def test_b2_prompt_forbids_a_json_array_at_the_root():
    assert "NEVER return a JSON array at the root" in _collapsed()


def test_b3_prompt_forbids_the_top_level_wrapper():
    """`top_level` was invented by the old schema description, not the contract."""
    text = _collapsed()
    assert 'NO "top_level" key' in text
    assert "NO wrapper or envelope" in text


def _json_blocks(text: str) -> list[Any]:
    """Every fenced ```json block in the prompt, parsed."""
    return [
        json.loads(part.split("```", 1)[0])
        for part in text.split("```json")[1:]
    ]


def test_b4_no_json_block_in_the_prompt_carries_a_top_level_key():
    """The structural check that matters: no displayed object has `top_level`.

    Prose is allowed to NAME the forbidden key. What must not exist is a JSON
    object in the prompt that actually contains it — that is what the model
    copied in Phase 3B.1.
    """
    text = _user_prompt()
    assert "Do NOT copy section B back" in _collapsed()
    blocks = _json_blocks(text)
    assert blocks, "the prompt must show the expected shape"
    for block in blocks:
        assert not (isinstance(block, dict) and "top_level" in block), block
    # the previous representation is gone from the module entirely
    assert not hasattr(prompt_mod, "build_output_schema_description")
    assert "build_output_schema_description" not in Path(prompt_mod.__file__).read_text("utf-8")


def test_b5_prompt_forbids_json_schema_metadata():
    text = _collapsed()
    assert "Do NOT output a schema, a schema description" in text
    for keyword in ("$schema", "properties", "required", "$defs"):
        assert keyword in text, keyword


def test_b6_the_root_skeleton_is_exactly_the_contract_top_level():
    """Contains those nine keys and nothing else — locked to the typed model."""
    skeleton = prompt_mod.build_response_root_skeleton()
    assert list(skeleton) == [
        "schema_version",
        "seed_entity_id",
        "summary",
        "regions",
        "connections",
        "functions",
        "circuits",
        "source_hints",
        "warnings",
    ]
    assert list(skeleton) == list(LlmDiscoveryResponse.model_fields)
    assert set(skeleton) == set(LlmDiscoveryResponse.model_fields)


def test_b7_the_root_skeleton_tracks_the_contract_automatically():
    """A field added to LlmDiscoveryResponse appears in the prompt by itself."""
    from pydantic import create_model

    extended = create_model(
        "ExtendedResponse",
        __base__=LlmDiscoveryResponse,
        brand_new_field=(str | None, None),
    )
    skeleton = prompt_mod.build_response_root_skeleton.__wrapped__() if hasattr(
        prompt_mod.build_response_root_skeleton, "__wrapped__"
    ) else None
    del skeleton  # the helper reads the contract directly; prove it by identity
    assert list(prompt_mod.build_response_root_skeleton()) == list(
        LlmDiscoveryResponse.model_fields
    ), "the skeleton must be rendered from the contract, never hand-listed"
    # a hand-written list would keep passing after the contract changed:
    assert "brand_new_field" in extended.model_fields


def test_b8_the_root_skeleton_carries_the_real_schema_version():
    skeleton = prompt_mod.build_response_root_skeleton()
    assert skeleton["schema_version"] == SCHEMA_VERSION
    assert skeleton["regions"] == [] and skeleton["warnings"] == []
    assert skeleton["seed_entity_id"] == "<seed_entity_id>"


def test_b9_section_a_and_b_are_separated_and_labelled():
    text = _collapsed()
    assert "A. EXPECTED RESPONSE ROOT" in text
    assert "B. FIELD DEFINITIONS" in text
    assert "It is the WHOLE answer." in text
    assert "They are not the response and must not be returned on their own" in text
    # shape comes first, field reference second
    assert text.index("A. EXPECTED RESPONSE ROOT") < text.index("B. FIELD DEFINITIONS")


def test_b10_the_field_reference_is_not_a_json_object():
    """A JSON envelope here is indistinguishable from an example answer."""
    definitions = prompt_mod.build_field_definitions()
    assert not definitions.lstrip().startswith("{")
    assert "{\n" not in definitions
    with pytest.raises(json.JSONDecodeError):
        json.loads(definitions)


def test_b11_the_field_reference_carries_no_python_module_paths():
    """`list[app.schemas...RegionCandidate]` is noise a model cannot use."""
    text = _user_prompt()
    assert "app.schemas" not in text
    assert "typing." not in text
    assert "<class '" not in text


def test_b12_scientific_guardrails_survive_the_representation_change():
    """The compaction must not have removed any frozen semantic rule."""
    system = " ".join(prompt_mod.SYSTEM_PROMPT.lower().split())
    for needle in (
        "discovery assistant",
        "<type>_<number>",
        "never invent a canonical id",
        "not required to be closed loops",
        "[0.0, 1.0]",
        "unverified",
        "do not provide quotations",
        "never silently convert animal knowledge into human",
        "do not fabricate evidence",
        "json only",
        "no markdown",
        "only the fields in the schema",
    ):
        assert needle in system, needle
    user = _collapsed()
    assert SEED_REF in user
    assert "A circuit must reference at least two regions" in user


def test_b13_every_frozen_vocabulary_value_is_still_present():
    user = _user_prompt()
    for value in (
        CONNECTION_TYPES
        + CONNECTION_DIRECTIONALITIES
        + REGION_RELATIONS_TO_SEED
        + CIRCUIT_TOPOLOGY_HINTS
        + SPECIES_SCOPES
        + DISCOVERY_WARNING_CODES
    ):
        assert value in user, value


def test_b14_the_root_skeleton_is_rendered_not_hand_written():
    """No second schema: every rendered line must come from the typed models."""
    definitions = prompt_mod.build_field_definitions()
    for model in (
        RegionCandidate,
        ConnectionCandidate,
        FunctionCandidate,
        CircuitCandidate,
        SourceHint,
        SpeciesContext,
        DiscoveryWarning,
    ):
        for name, label in prompt_mod.compact_output_schema(model).items():
            assert f"  {name}: {label}" in definitions, (model.__name__, name)

    # A hand-written root skeleton would not track the contract. Scan the
    # skeleton FUNCTION only: the format example legitimately contains empty
    # arrays, because that is part of a complete valid response.
    source = Path(prompt_mod.__file__).read_text(encoding="utf-8")
    fn = next(
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef) and node.name == "build_response_root_skeleton"
    )
    body = ast.get_source_segment(source, fn) or ""
    assert "model_fields" in body, "the skeleton must be rendered from the contract"
    for literal in ('"regions"', '"schema_version": "1.0"', '"source_hints"'):
        assert literal not in body, literal


# ---------------------------------------------------------------------------
# Phase 3B.4 — LOCAL ID compliance hardening
# ---------------------------------------------------------------------------
# A real deepseek-flash run with an ample budget finished normally (`stop`,
# 23K of 64K used) and still returned `conn_1` where the contract requires
# `connection_1`. The contract is NOT relaxed to match: the prompt is made
# unambiguous, and one validated example is added.
def _example() -> dict[str, Any]:
    return prompt_mod.build_format_example(SEED_ID)


def test_c1_prompt_version_is_the_local_id_hardened_text():
    assert prompt_mod.PROMPT_VERSION == "1.2.0"
    built = prompt_mod.build_llm_discovery_prompt(seed())
    assert built["prompt_version"] == "1.2.0"


def test_c2_every_exact_prefix_is_stated_in_the_prompt():
    user = _collapsed()
    for prefix in (
        "region_<integer>",
        "connection_<integer>",
        "function_<integer>",
        "circuit_<integer>",
    ):
        assert prefix in user, prefix


def test_c3_the_abbreviations_a_real_model_produced_are_named_as_forbidden():
    user = _collapsed()
    for bad in ("conn_1", "func_1", "circ_1", "edge_1", "pathway_1", "region1"):
        assert bad in user, bad
    assert "NEVER write" in user


def test_c4_prompt_forbids_abbreviating_local_id_prefixes():
    assert "Do not abbreviate local-ID prefixes." in _collapsed()


def test_c5_references_must_reuse_the_declared_id_exactly():
    user = _collapsed()
    assert "References MUST reuse a declared local_id EXACTLY" in user
    assert 'never "conn_1"' in user


def test_c6_the_seed_is_still_the_only_reserved_reference():
    user = _collapsed()
    assert "SEED is the one reserved reference" in user
    assert "region_seed" in user  # named as forbidden


def test_c7_the_field_reference_states_the_local_id_pattern():
    """The bare `local_id: string` is what a model read while writing `conn_1`."""
    definitions = prompt_mod.build_field_definitions()
    assert "local_id: string - MUST match " in definitions
    # the shape is DERIVED from the contract's own regex, not re-typed
    assert prompt_mod.local_id_shape() == "region_<n>|connection_<n>|function_<n>|circuit_<n>"
    assert prompt_mod.local_id_prefixes() == ("region", "connection", "function", "circuit")
    for prefix in prompt_mod.local_id_prefixes():
        assert prefix in LOCAL_ID_PATTERN.pattern, prefix


def test_c8_the_optional_warning_local_id_is_not_given_the_candidate_rule():
    """DiscoveryWarning.local_id is optional; the MUST rule is for candidates."""
    definitions = prompt_mod.build_field_definitions()
    assert "local_id: string|null" in definitions


def test_c9_the_format_example_is_a_json_object_that_passes_the_contract():
    example = _example()
    assert isinstance(example, dict)
    parsed = LlmDiscoveryResponse.model_validate(example)
    assert parsed.seed_entity_id == SEED_ID


def test_c10_every_example_local_id_is_contract_legal():
    example = _example()
    ids = [
        *(r["local_id"] for r in example["regions"]),
        *(c["local_id"] for c in example["connections"]),
        *(f["local_id"] for f in example["functions"]),
        *(c["local_id"] for c in example["circuits"]),
    ]
    assert len(ids) == len(set(ids)), "example ids must be unique"
    for local_id in ids:
        assert is_local_candidate_id(local_id), local_id
    # all four id kinds actually appear, so the example teaches every prefix
    assert {i.split("_")[0] for i in ids} == {"region", "connection", "function", "circuit"}


def test_c11_every_example_reference_resolves():
    result = prompt_mod.build_format_example(SEED_ID)
    parsed = LlmDiscoveryResponse.model_validate(result)
    errors, _warnings = parser.validate_cross_references(parsed)
    assert errors == [], errors
    # the example is only useful if the PARSER accepts it, not just pydantic
    round_trip = parse_text(json.dumps(result))
    assert round_trip.ok, round_trip.error


def test_c12_the_example_uses_the_seed_id_actually_passed():
    assert (
        prompt_mod.build_format_example("NGIQ-BR-99999999")["seed_entity_id"]
        == "NGIQ-BR-99999999"
    )
    assert SEED_ID in json.dumps(_example())
    # and it demonstrates SEED as a reference, so no fake seed region is invented
    assert SEED_REF in _example()["connections"][0].values()
    assert SEED_REF in _example()["circuits"][0]["region_refs"]


def test_c13_the_example_carries_no_real_brain_region_name():
    """A format example must not inject scientific bias into this seed."""
    blob = json.dumps(_example(), ensure_ascii=False).lower()
    for real in (
        "hippocampus",
        "amygdala",
        "cortex",
        "thalamus",
        "cerebellum",
        "striatum",
        "putamen",
        "insula",
        "brainstem",
        "midbrain",
    ):
        assert real not in blob, real
    assert "example region" in blob and "example circuit" in blob


def test_c14_the_example_declares_no_human_species_basis():
    """A placeholder has no species identity; absence must not read as HUMAN."""
    example = _example()
    assert example["regions"][0]["species_taxon_id"] is None
    for key in ("connections", "functions", "circuits"):
        assert example[key][0]["species_context"] == {"scope": "UNKNOWN", "taxon_ids": []}
    assert "9606" not in json.dumps(example)


def test_c15_the_example_is_labelled_format_only():
    user = _collapsed()
    assert "FORMAT ONLY" in user
    assert "Do not copy its names or its scientific content" in user
    assert "a human seed does not make a candidate human-established" in user


def test_c16_scientific_guardrails_survive_the_hardening():
    system = " ".join(prompt_mod.SYSTEM_PROMPT.lower().split())
    for needle in (
        "discovery assistant",
        "never invent a canonical id",
        "not required to be closed loops",
        "[0.0, 1.0]",
        "unverified",
        "do not provide quotations",
        "never silently convert animal knowledge into human",
        "do not fabricate evidence",
        "json only",
        "no markdown",
    ):
        assert needle in system, needle


def test_c17_the_contract_and_parser_semantics_are_untouched():
    """3B.4 must not have relaxed anything to make the model comply."""
    assert LOCAL_ID_PATTERN.pattern == r"^(region|connection|function|circuit)_[0-9]+$"
    for rejected in ("conn_1", "func_1", "circ_1", "r1", "region1", "connection1", "edge_1"):
        assert not is_local_candidate_id(rejected), rejected
    # no alias normalisation was added anywhere on the parse path
    parser_src = PARSER_PATH.read_text(encoding="utf-8").lower()
    for forbidden in ("conn_1", "func_1", "circ_1", "normalize_local_id", "remap"):
        assert forbidden not in parser_src, forbidden


def test_c18_the_example_reaches_the_rendered_prompt():
    user = prompt_mod.build_user_prompt(seed())
    assert "FORMAT-ONLY EXAMPLE" in user
    blocks = _json_blocks(user)
    identified = [b for b in blocks if isinstance(b, dict) and b.get("regions")]
    assert identified, "the rendered prompt must contain the populated example"
    example = identified[0]
    assert example["seed_entity_id"] == SEED_ID
    assert example["connections"][0]["local_id"] == "connection_1"


# ===========================================================================
# Region confidence is OPTIONAL — and only for Region
# ===========================================================================
# A live continuation pass returned ten otherwise-valid regions with no
# `confidence` at all, and the parser rejected the WHOLE response for it —
# including ten circuits that had nothing wrong with them. These tests pin the
# repair and, just as importantly, pin its narrowness: tolerance for one missing
# component field must not become tolerance for a malformed response.
def region_without_confidence(local_id: str = "region_1", **over: Any) -> dict[str, Any]:
    """A structurally valid region with the confidence key ABSENT (not null)."""
    data = region(local_id, **over)
    del data["confidence"]
    return data


def test_region_confidence_a_absent_is_accepted_as_UNKNOWN():
    """§10.A — and recorded as None. Never 0.0, never a borrowed number."""
    result = parse(payload(regions=[region_without_confidence()]))
    assert result.ok, result.error
    assert result.data.regions[0].confidence is None
    # The region itself survives: dropping it would break every ref pointing here.
    assert result.data.regions[0].name == "Medial dorsal nucleus"


def test_region_confidence_b_explicit_null_is_accepted():
    """§10.B — the model may state "no confidence" rather than omit it."""
    result = parse(payload(regions=[region(confidence=None)]))
    assert result.ok, result.error
    assert result.data.regions[0].confidence is None


def test_region_confidence_c_a_non_numeric_value_is_rejected():
    """§10.C — omission is tolerated; nonsense is not."""
    for bad in ("high", "0.8-ish", {}, []):
        result = parse(payload(regions=[region(confidence=bad)]))
        assert not result.ok, f"{bad!r} must not parse"


def test_region_confidence_numeric_bounds_still_apply():
    for bad in (1.5, -0.1, 2):
        assert not parse(payload(regions=[region(confidence=bad)])).ok, bad
    for good in (0.0, 0.5, 1.0):
        assert parse(payload(regions=[region(confidence=good)])).ok, good


def test_region_confidence_is_NOT_defaulted_to_a_number():
    """The absence must survive as an absence, not become 0.0 or 0.5."""
    result = parse(payload(regions=[region_without_confidence()]))
    assert result.data.regions[0].confidence is None
    assert result.data.regions[0].confidence != 0.0


# --- the OTHER three still require it: no accidental generalisation ---------
@pytest.mark.parametrize("kind", ["circuits", "connections", "functions"])
def test_confidence_is_still_REQUIRED_on_every_other_candidate_type(kind):
    """§8 — the tolerance is a Region fact, not a contract-wide relaxation.

    A circuit, connection or function IS a proposed knowledge claim; a missing
    confidence there is a missing judgement, and it still fails the response.
    """
    base = {
        "circuits": circuit,
        "connections": connection,
        "functions": function,
    }[kind]("x_1")
    del base["confidence"]
    result = parse(payload(**{kind: [base]}))
    assert not result.ok, f"{kind} must still require confidence"


# --- the exact live failure, reproduced ------------------------------------
def test_the_round_2_live_failure_now_parses():
    """§9 — ten regions with confidence omitted, plus circuits that reference them.

    This is the shape the live continuation pass returned. Before the repair the
    whole response was refused; now the regions parse as UNKNOWN and every
    reference is still validated.
    """
    regions = [region_without_confidence(f"region_{i}", name=f"Region {i}")
               for i in range(1, 11)]
    result = parse(payload(
        regions=regions,
        connections=[connection("connection_1", source_ref="region_1",
                                target_ref="region_2")],
        circuits=[circuit("circuit_1", region_refs=["region_1", "region_2"],
                          connection_refs=["connection_1"])],
    ))
    assert result.ok, result.error
    assert len(result.data.regions) == 10
    assert all(r.confidence is None for r in result.data.regions)
    assert len(result.data.circuits) == 1, "the circuits were never the problem"


def test_a_region_without_confidence_can_still_be_REFERENCED():
    """§5 — keeping the region is what keeps its referrers resolvable.

    Two regions, because a circuit must carry at least two components to be a
    circuit at all — the point here is the MISSING CONFIDENCE, not the arity.
    """
    result = parse(payload(
        regions=[region_without_confidence("region_1"),
                 region_without_confidence("region_2")],
        connections=[connection("connection_1", source_ref="region_1",
                                target_ref="region_2")],
        circuits=[circuit("circuit_1", region_refs=["region_1", "region_2"],
                          connection_refs=["connection_1"])],
    ))
    assert result.ok, result.error
    assert result.data.circuits[0].region_refs == ["region_1", "region_2"]
    assert all(r.confidence is None for r in result.data.regions)


def test_removing_the_confidence_key_from_the_fixture_is_what_makes_this_a_test():
    """Guard: the fixture must genuinely OMIT the key, not set it to null."""
    assert "confidence" not in region_without_confidence()


# ===========================================================================
# §10.D-H — structural strictness is UNCHANGED
# ===========================================================================
def test_structural_d_a_region_without_a_name_still_fails():
    data = region_without_confidence()
    del data["name"]
    assert not parse(payload(regions=[data])).ok


def test_structural_e_a_region_without_a_local_id_still_fails():
    data = region_without_confidence()
    del data["local_id"]
    assert not parse(payload(regions=[data])).ok


def test_structural_f_a_dangling_circuit_region_ref_still_fails():
    result = parse(payload(
        regions=[region_without_confidence("region_1")],
        circuits=[circuit("circuit_1", region_refs=["region_1", "region_404"])],
    ))
    assert not result.ok
    assert "region_404" in str(result.error)


def test_structural_g_a_dangling_connection_source_ref_still_fails():
    result = parse(payload(
        regions=[region_without_confidence("region_1")],
        connections=[connection("connection_1", source_ref="region_404")],
    ))
    assert not result.ok
    assert "region_404" in str(result.error)


def test_structural_h_a_malformed_circuit_still_fails():
    for bad in ({"name": ""}, {"region_refs": "region_1"}, {"confidence": "high"}):
        data = circuit("circuit_1", **bad)
        assert not parse(payload(circuits=[data])).ok, bad


def test_structural_the_boundary_rule_is_untouched_by_this_repair():
    """A missing confidence never turns a non-circuit into a circuit."""
    from app.llm_discovery_views import CIRCUIT_BOUNDARY_RULE

    assert "Projection != Connection != Pathway != Circuit" in CIRCUIT_BOUNDARY_RULE


# ===========================================================================
# Region-only tolerance: an UNKNOWN key whose value is null
# ===========================================================================
# A live Round-4 continuation pass was discarded in full — an otherwise valid
# response with ~15 circuits — because ONE region carried one invented key set
# to null (`regions.7.relation_note`, extra_forbidden, input_value=None). Under
# RECALL FIRST that trade is wrong: a region is mostly a supporting reference
# for circuit/connection topology, and an empty auxiliary key says nothing.
#
# These tests pin both halves of that judgement: the tolerance, AND its
# narrowness. Every key that carries ANY content still fails, other candidate
# types are untouched, and nothing was added to the frozen contract.
def _live_round_4_payload() -> dict[str, Any]:
    """Reproduce the exact response the provider returned and the parser refused.

    Eight regions — so the failing one really is index 7 — with the eighth
    carrying the invented `relation_note`, plus the topology that makes the rest
    of the response valid.
    """
    regions = [region(f"region_{i}", name=f"Region {i}") for i in range(1, 9)]
    regions[7]["relation_note"] = None
    return payload(
        summary="round 4 continuation pass",
        regions=regions,
        connections=[
            connection("connection_1", source_ref="region_1", target_ref="region_2")
        ],
        circuits=[
            circuit(
                "circuit_1",
                region_refs=["region_1", "region_2"],
                connection_refs=["connection_1"],
            )
        ],
    )


def _absent(obj: Any, *fields: str) -> bool:
    """True when none of `fields` survived into the typed object.

    The drop used to be reported through a synthetic warning; under the generic
    sanitizer it is reported through a LOG, so the observable fact is the one
    that always mattered — the key is gone from the parsed candidate.
    """
    dumped = obj.model_dump()
    return all(f not in dumped for f in fields)


def test_round_4_live_failure_now_parses():
    """§9 — the live failure, reproduced. Before the repair this whole response
    was refused and ~15 circuits were lost with it."""
    result = parse(_live_round_4_payload())
    assert result.ok, result.error
    assert len(result.data.regions) == 8
    assert result.data.regions[7].local_id == "region_8"
    assert result.data.regions[7].name == "Region 8"
    assert len(result.data.circuits) == 1, "the circuits were never the problem"


def test_the_ignored_key_is_gone_from_the_parsed_region():
    """Dropped means dropped: it must not reappear as a canonical field."""
    result = parse(_live_round_4_payload())
    assert "relation_note" not in result.data.regions[7].model_dump()
    assert not hasattr(result.data.regions[7], "relation_note")
    # ... while the fields it DOES declare survive intact.
    assert result.data.regions[7].confidence == 0.6
    assert result.data.regions[7].relation_to_seed == "UNKNOWN"


def test_the_drop_is_reported_not_silent(caplog):
    """Strictness exists to surface drift; a quiet deletion would trade one
    failure for a worse one. The report is now a structured LOG naming the
    object and the fields, not a warning injected into the model's own list."""
    import logging

    with caplog.at_level(logging.INFO, logger="app.services.llm_discovery_parser"):
        result = parse(_live_round_4_payload())
    assert result.ok, result.error
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "[benign-extra-drop]" in text
    assert "object_type=region" in text
    assert "local_id=region_8" in text
    assert "relation_note" in text
    assert "total_objects=1" in text


def test_the_tolerance_applies_on_the_raw_TEXT_path_too():
    """The live path passes `response.raw_text`, not a dict."""
    result = parse_text(json.dumps(_live_round_4_payload()))
    assert result.ok, result.error
    assert len(result.data.regions) == 8


# --- A / B: the tolerated shape ---------------------------------------------
def test_tolerance_a_region_unknown_field_null_passes():
    data = region("region_1")
    data["relation_note"] = None
    result = parse(payload(regions=[data]))
    assert result.ok, result.error
    assert _absent(result.data.regions[0], "relation_note")


def test_tolerance_b_two_unknown_null_fields_pass():
    data = region("region_1")
    data["relation_note"] = None
    data["another_invented_field"] = None
    result = parse(payload(regions=[data]))
    assert result.ok, result.error
    assert _absent(result.data.regions[0], "relation_note", "another_invented_field")


# --- C / D / E: content is never silently discarded -------------------------
def test_tolerance_c_region_unknown_field_non_null_string_fails():
    data = region("region_1")
    data["relation_note"] = "CA3 receives strong input"
    result = parse(payload(regions=[data]))
    assert not result.ok, "an unknown field carrying meaning must not be dropped"
    assert "extra_forbidden" in result.error


def test_tolerance_d_region_unknown_field_zero_fails():
    """0 is falsy but it is not null — a falsy check would have eaten it."""
    data = region("region_1")
    data["invented_field"] = 0
    result = parse(payload(regions=[data]))
    assert not result.ok
    assert "extra_forbidden" in result.error


def test_tolerance_e_region_unknown_field_false_fails():
    data = region("region_1")
    data["invented_field"] = False
    result = parse(payload(regions=[data]))
    assert not result.ok
    assert "extra_forbidden" in result.error


@pytest.mark.parametrize("value", [123, "", ["x"], {"a": 1}, "CA3", True, 0])
def test_tolerance_no_other_unknown_value_is_dropped(value):
    data = region("region_1")
    data["invented_field"] = value
    assert not parse(payload(regions=[data])).ok, value


# --- F / G / H: the EMPTY tolerance covers every typed array ----------------
# It is no longer Region-only. An unknown NULL/[]/{} extra on any of the four
# types is dropped; anything with content still fails. The old Region-only tests
# asserted the narrower contract and are replaced, not deleted.
def test_tolerance_f_circuit_unknown_null_field_is_dropped():
    data = circuit("circuit_1", region_refs=["region_1", "region_2"])
    data["invented_field"] = None
    result = parse(payload(
        regions=[region("region_1"), region("region_2")], circuits=[data]
    ))
    assert result.ok, result.error
    assert _absent(result.data.circuits[0], "invented_field")


def test_tolerance_g_connection_unknown_null_field_is_dropped():
    data = connection("connection_1")
    data["invented_field"] = None
    result = parse(payload(regions=[region("region_1")], connections=[data]))
    assert result.ok, result.error
    assert _absent(result.data.connections[0], "invented_field")


def test_tolerance_h_function_unknown_null_field_is_dropped():
    data = function("function_1")
    data["invented_field"] = None
    result = parse(payload(functions=[data]))
    assert result.ok, result.error
    assert _absent(result.data.functions[0], "invented_field")


# --- I / J: required region fields are untouched ----------------------------
def test_tolerance_i_region_missing_name_still_fails():
    data = region("region_1")
    del data["name"]
    assert not parse(payload(regions=[data])).ok


def test_tolerance_j_region_missing_local_id_still_fails():
    data = region("region_1")
    del data["local_id"]
    assert not parse(payload(regions=[data])).ok


def test_a_KNOWN_region_field_set_to_null_is_not_dropped():
    """The tolerance covers UNKNOWN keys. `name` is declared, so nulling it is a
    missing value — not an empty extra — and still fails."""
    data = region("region_1")
    data["name"] = None
    assert not parse(payload(regions=[data])).ok


def test_a_region_local_id_of_the_WRONG_TYPE_is_not_dropped():
    """Only null is tolerated. Every other invalid value still reaches the
    schema and is judged there."""
    data = region("region_1")
    data["local_id"] = None
    result = parse(payload(regions=[data]))
    assert not result.ok


# --- K / L: reference integrity is untouched --------------------------------
def test_tolerance_k_dangling_region_ref_still_fails():
    result = parse(payload(
        regions=[region("region_1")],
        circuits=[circuit("circuit_1", region_refs=["region_1", "region_404"])],
    ))
    assert not result.ok
    assert "region_404" in str(result.error)


def test_tolerance_l_dangling_connection_ref_still_fails():
    result = parse(payload(
        regions=[region("region_1"), region("region_2")],
        circuits=[circuit(
            "circuit_1",
            region_refs=["region_1", "region_2"],
            connection_refs=["connection_404"],
        )],
    ))
    assert not result.ok
    assert "connection_404" in str(result.error)


def test_a_dangling_ref_is_still_fatal_EVEN_WITH_a_null_extra_present():
    """The two rules must not interact: dropping an empty key must not soften
    the reference check that runs after it.

    The null extra goes on the REGION (where it is tolerated) and the dangling
    ref on the circuit — otherwise the schema rejection would mask the
    reference error and the test would prove nothing about their interaction.
    """
    tolerated_region = region("region_1")
    tolerated_region["invented_field"] = None
    result = parse(payload(
        regions=[tolerated_region],
        circuits=[circuit("circuit_1", region_refs=["region_1", "region_404"])],
    ))
    assert not result.ok
    assert "region_404" in str(result.error)


# --- the contract was NOT widened -------------------------------------------
def test_relation_note_was_NOT_added_to_the_schema():
    """§6 — the model invented the field. Promoting every invention to a formal
    field is how a frozen contract drifts. Only ONE of them is even reachable
    as a shape the model might repeat, and it is not this one."""
    for name in ("relation_note", "invented_field", "another_invented_field"):
        assert name not in RegionCandidate.model_fields, name


def test_every_discovery_model_is_STILL_strict():
    """§4/§5 — the repair is a pre-validation drop, not a relaxation. Every
    model still forbids extras, so a NON-null unknown still fails everywhere."""
    for model in (
        RegionCandidate,
        CircuitCandidate,
        ConnectionCandidate,
        FunctionCandidate,
        LlmDiscoveryResponse,
    ):
        assert model.model_config["extra"] == "forbid", model.__name__


def test_the_tolerance_did_not_touch_the_warning_vocabulary():
    """The parser reports the drop through the EXISTING channel. It deliberately
    did not mint a new DiscoveryWarningCode: that vocabulary is the MODEL's and
    is rendered into the prompt, so a parser-only code would both extend a frozen
    vocabulary and teach the model to emit it."""
    assert len(DISCOVERY_WARNING_CODES) == 7
    assert "REGION_NULL_EXTRA_IGNORED" not in DISCOVERY_WARNING_CODES


# ===========================================================================
# Circuit topology vocabulary: RECURRENT
# ===========================================================================
# A live Round-5 pass was rejected in full — an otherwise valid response — because
# two circuits carried `topology_hint: "RECURRENT"`. The word was simply absent
# from the frozen vocabulary, and it is the word a model asked about CA3 reaches
# for: CA3's recurrent collaterals are its defining local architecture.
#
# This was a VOCABULARY EXTENSION, not tolerance and not enum rewriting. Nothing
# was mapped onto an existing value: RECURRENT says WHERE activity goes (back
# through connections within one population), which LOOP (the circuit closes),
# RECIPROCAL (two structures point at each other), FEEDBACK (a projection returns)
# and NETWORK (a macro-scale graph) each say differently. Every unknown string is
# still a schema error.
def _valid_circuit_payload(**circuit_over: Any) -> dict[str, Any]:
    """A payload whose only variable is the circuit under test."""
    data = circuit("circuit_1", region_refs=["region_1", "region_2"])
    data.update(circuit_over)
    return payload(
        regions=[region("region_1"), region("region_2")],
        circuits=[data],
    )


# --- A: the newly valid value -----------------------------------------------
def test_topology_a_recurrent_is_now_accepted():
    result = parse(_valid_circuit_payload(topology_hint="RECURRENT"))
    assert result.ok, result.error
    assert result.data.circuits[0].topology_hint == "RECURRENT"


def test_topology_a_the_stored_value_is_RECURRENT_not_a_neighbour():
    """The whole point: it must not be quietly rewritten to a lookalike."""
    result = parse(_valid_circuit_payload(topology_hint="RECURRENT"))
    assert result.data.circuits[0].topology_hint not in (
        "LOOP", "RECIPROCAL", "FEEDBACK", "NETWORK",
    )


# --- B / C / D: the pre-existing values are untouched ------------------------
@pytest.mark.parametrize(
    "value", ["FEEDFORWARD", "RECIPROCAL", "LOOP", "FEEDBACK", "PARALLEL",
              "CONVERGENT", "DIVERGENT", "NETWORK", "UNKNOWN"]
)
def test_topology_bcd_every_previous_value_still_parses(value):
    result = parse(_valid_circuit_payload(topology_hint=value))
    assert result.ok, (value, result.error)
    assert result.data.circuits[0].topology_hint == value


def test_topology_the_default_is_still_UNKNOWN():
    assert parse(_valid_circuit_payload()).data.circuits[0].topology_hint == "UNKNOWN"


# --- E / F: strictness is intact --------------------------------------------
@pytest.mark.parametrize(
    "value",
    ["RECURRENT_LOOP", "recurrent", "Recurrent", "RECURRING", "RECURRENCY",
     "AUTOASSOCIATIVE", "CYCLIC", "RECURRENT ", " RECURRENT", "RECURRENTLY", ""],
)
def test_topology_ef_no_lookalike_or_unknown_string_is_accepted(value):
    """No fuzzy repair, no case normalisation, no prefix matching."""
    result = parse(_valid_circuit_payload(topology_hint=value))
    assert not result.ok, f"{value!r} must not be accepted"


def test_topology_the_rejection_is_a_schema_error_not_a_silent_default():
    """An unknown value must FAIL — never be coerced to UNKNOWN."""
    result = parse(_valid_circuit_payload(topology_hint="RECURRENT_LOOP"))
    assert not result.ok
    assert "literal_error" in result.error


# --- G / H: Circuit strictness is otherwise unchanged -----------------------
def test_topology_g_a_circuit_missing_a_required_field_still_fails():
    data = circuit("circuit_1", region_refs=["region_1", "region_2"])
    del data["name"]
    result = parse(payload(
        regions=[region("region_1"), region("region_2")], circuits=[data]
    ))
    assert not result.ok


def test_topology_h_a_circuit_with_an_unknown_extra_still_fails():
    """A NON-empty unknown extra. The empty case is now tolerated; content is
    not, and this is the test that keeps that line drawn."""
    data = circuit("circuit_1", region_refs=["region_1", "region_2"])
    data["invented_field"] = "carries meaning"
    result = parse(payload(
        regions=[region("region_1"), region("region_2")], circuits=[data]
    ))
    assert not result.ok
    assert "extra_forbidden" in result.error


# --- I / J / K: the neighbouring repairs are undisturbed --------------------
def test_topology_i_the_empty_extra_tolerance_is_no_longer_Region_only():
    """The region case is now the special case of a general rule."""
    tolerated = region("region_1")
    tolerated["relation_note"] = None
    assert parse(payload(regions=[tolerated])).ok
    # ... and the same tolerance now covers a circuit, a connection and a function.
    for kind, builder, extra in (
        ("circuits", lambda: circuit("circuit_1", region_refs=["region_1", "region_2"]),
         [region("region_1"), region("region_2")]),
        ("connections", lambda: connection("connection_1"), [region("region_1")]),
        ("functions", lambda: function("function_1"), []),
    ):
        item = builder()
        item["relation_note"] = None
        result = parse(payload(regions=extra, **{kind: [item]}))
        assert result.ok, (kind, result.error)


def test_topology_j_region_missing_confidence_is_still_None():
    data = region("region_1")
    del data["confidence"]
    result = parse(payload(regions=[data]))
    assert result.ok, result.error
    assert result.data.regions[0].confidence is None


@pytest.mark.parametrize("kind", ["circuits", "connections", "functions"])
def test_topology_k_confidence_is_still_required_on_every_other_type(kind):
    base = {
        "circuits": circuit("circuit_1", region_refs=["region_1", "region_2"]),
        "connections": connection("connection_1"),
        "functions": function("function_1"),
    }[kind]
    del base["confidence"]
    result = parse(payload(
        regions=[region("region_1"), region("region_2")],
        **{kind: [base]},
    ))
    assert not result.ok, f"{kind} must still require confidence"


# --- §8: the frozen vocabulary, explicitly ----------------------------------
def test_recurrent_is_part_of_the_frozen_topology_vocabulary():
    assert "RECURRENT" in CIRCUIT_TOPOLOGY_HINTS
    assert len(CIRCUIT_TOPOLOGY_HINTS) == 10


def test_the_literal_and_the_tuple_are_the_same_vocabulary():
    """Two copies of one vocabulary must never drift apart."""
    from typing import get_args

    from app.schemas.llm_discovery import CircuitTopologyHint

    assert tuple(get_args(CircuitTopologyHint)) == CIRCUIT_TOPOLOGY_HINTS


def test_the_vocabulary_widened_by_exactly_one_value():
    """Guards against a careless bulk edit: the nine old values, unchanged."""
    assert set(CIRCUIT_TOPOLOGY_HINTS) - {"RECURRENT"} == {
        "FEEDFORWARD", "FEEDBACK", "RECIPROCAL", "LOOP", "PARALLEL",
        "CONVERGENT", "DIVERGENT", "NETWORK", "UNKNOWN",
    }


def test_the_prompt_now_offers_RECURRENT_and_nothing_else_new():
    """Rendered from the Literal, so the prompt follows the contract by itself."""
    user = _user_prompt()
    assert "RECURRENT" in user
    assert "RECURRENT_LOOP" not in user
    for value in CIRCUIT_TOPOLOGY_HINTS:
        assert value in user, value


# ===========================================================================
# Warning-code aliases: an approved lexical near-miss, mapped — not added
# ===========================================================================
# A live Round-7 pass was rejected in full because one warning carried
# `code: "AMBIGUOUS_DIRECTIONALITY"` where the frozen vocabulary says
# `AMBIGUOUS_DIRECTION`. Same warning, same meaning, different spelling. Adding
# the long form as a second enum member would make the vocabulary grow every
# time a model misspells something; mapping it keeps the vocabulary exactly as
# it was and confines the tolerance to spellings somebody approved by hand.
def warning(code: str, message: str = "a warning", local_id: str | None = None):
    data: dict[str, Any] = {"code": code, "message": message}
    if local_id is not None:
        data["local_id"] = local_id
    return data


# --- A / B / C --------------------------------------------------------------
def test_warning_alias_a_a_canonical_code_is_left_exactly_as_it_was():
    result = parse(payload(warnings=[warning("AMBIGUOUS_DIRECTION")]))
    assert result.ok, result.error
    assert [w.code for w in result.data.warnings] == ["AMBIGUOUS_DIRECTION"]


def test_warning_alias_b_the_approved_near_miss_normalizes():
    result = parse(payload(warnings=[warning("AMBIGUOUS_DIRECTIONALITY")]))
    assert result.ok, result.error
    assert [w.code for w in result.data.warnings] == ["AMBIGUOUS_DIRECTION"]


def test_warning_alias_c_the_CANONICAL_value_is_what_reaches_the_model_object():
    """The alias must not survive into the typed response."""
    result = parse(payload(warnings=[warning("AMBIGUOUS_DIRECTIONALITY")]))
    assert "AMBIGUOUS_DIRECTIONALITY" not in {
        w.code for w in result.data.warnings
    }


def test_warning_alias_d_the_typed_model_never_carries_the_alias():
    """Warnings are not persisted (the candidate writer excludes them), so the
    validated model is the last place the alias could survive. It does not."""
    result = parse(payload(warnings=[warning("AMBIGUOUS_DIRECTIONALITY")]))
    dumped = result.data.model_dump()
    assert "AMBIGUOUS_DIRECTIONALITY" not in json.dumps(dumped)


# --- E ----------------------------------------------------------------------
@pytest.mark.parametrize("code", [
    "AMBIGUOUS_DIRECTIONALITY_TYPO",   # a neighbour of a LISTED alias
    "AMBIGUOUS_DIRECTIONS",
    "ambiguous_directionality",        # case is not tolerated
    "AMBIGUOUS DIRECTIONALITY",        # whitespace is not tolerated
    "DIRECTIONALITY_AMBIGUOUS",
    "SOME_NEW_UNKNOWN_WARNING",
    "",
])
def test_warning_alias_e_anything_unlisted_still_fails(code):
    """No prefix, substring, case-insensitive or edit-distance matching exists."""
    result = parse(payload(warnings=[warning(code)]))
    assert not result.ok, f"{code!r} must not be accepted"
    assert "literal_error" in result.error


# --- F ----------------------------------------------------------------------
def test_warning_alias_f_a_mixture_keeps_order_messages_and_local_ids():
    result = parse(payload(warnings=[
        warning("UNCERTAIN_REGION_NAME", "first", "region_1"),
        warning("AMBIGUOUS_DIRECTIONALITY", "second", "connection_1"),
        warning("OTHER", "third"),
        warning("AMBIGUOUS_DIRECTION", "fourth", "circuit_1"),
    ]))
    assert result.ok, result.error
    assert [w.code for w in result.data.warnings] == [
        "UNCERTAIN_REGION_NAME", "AMBIGUOUS_DIRECTION", "OTHER",
        "AMBIGUOUS_DIRECTION",
    ]
    assert [w.message for w in result.data.warnings] == [
        "first", "second", "third", "fourth",
    ]
    assert [w.local_id for w in result.data.warnings] == [
        "region_1", "connection_1", None, "circuit_1",
    ]


def test_warning_alias_f_two_aliases_in_one_response_are_both_renamed():
    result = parse(payload(warnings=[
        warning("AMBIGUOUS_DIRECTIONALITY"), warning("AMBIGUOUS_DIRECTIONALITY"),
    ]))
    assert result.ok, result.error
    assert [w.code for w in result.data.warnings] == [
        "AMBIGUOUS_DIRECTION", "AMBIGUOUS_DIRECTION",
    ]


# --- G ----------------------------------------------------------------------
def test_warning_alias_g_nothing_else_in_the_response_is_touched():
    """The repair is a rename of one field. A circuit, a connection, a region,
    a function or a topology hint that changed would be a much larger claim."""
    data = payload(
        regions=[region("region_1", name="Untouched Region"),
                 region("region_2", name="Untouched Region 2")],
        connections=[connection("connection_1", source_ref="region_1",
                                target_ref="region_2")],
        functions=[function("function_1")],
        circuits=[circuit("circuit_1", name="Untouched Circuit",
                          region_refs=["region_1", "region_2"],
                          topology_hint="RECURRENT")],
        warnings=[warning("AMBIGUOUS_DIRECTIONALITY")],
    )
    result = parse(data)
    assert result.ok, result.error
    out = result.data
    assert [r.name for r in out.regions] == ["Untouched Region", "Untouched Region 2"]
    assert [f.label for f in out.functions] == ["Thalamic gating"]
    assert [c.name for c in out.circuits] == ["Untouched Circuit"]
    assert [c.topology_hint for c in out.circuits] == ["RECURRENT"]
    assert out.connections[0].connection_type == "PROJECTION"
    # ... and the input mapping itself was not mutated in place.
    assert data["warnings"][0]["code"] == "AMBIGUOUS_DIRECTIONALITY"


# --- the map is closed and explicit -----------------------------------------
def test_warning_alias_the_map_is_exactly_the_approved_entry():
    assert parser.WARNING_CODE_ALIASES == {"AMBIGUOUS_DIRECTIONALITY": "AMBIGUOUS_DIRECTION"}


def test_warning_alias_targets_are_canonical_members():
    """An alias may only point at a code that actually exists."""
    for alias, canonical in parser.WARNING_CODE_ALIASES.items():
        assert canonical in DISCOVERY_WARNING_CODES, canonical
        assert alias not in DISCOVERY_WARNING_CODES, alias


def test_warning_alias_the_canonical_vocabulary_did_NOT_grow():
    """The whole point: normalize the spelling, do not add a member."""
    assert len(DISCOVERY_WARNING_CODES) == 7
    assert "AMBIGUOUS_DIRECTIONALITY" not in DISCOVERY_WARNING_CODES
    assert "AMBIGUOUS_DIRECTION" in DISCOVERY_WARNING_CODES


# ===========================================================================
# Benign EMPTY extra fields — generic, per object type
# ===========================================================================
# A live Round-12 pass was discarded in full because a CONNECTION carried
# `connection_refs: []` and `connection_refs_placeholder: null`. Both are
# unknown on a Connection — the first is a CIRCUIT field, which is exactly why
# it looked plausible — and both are empty. Under RECALL FIRST an empty
# auxiliary key must not cost a round.
#
# The line this policy draws is between EMPTY and CONTENT, not between known and
# unknown: an unknown field carrying anything still fails.
def _with(kind: str, item: dict, **over) -> dict:
    """One payload containing exactly one object of `kind`, plus whatever
    supporting objects it needs to be otherwise valid."""
    extra: dict = {}
    if kind == "connections":
        extra["regions"] = [region("region_1")]
    if kind == "circuits":
        extra["regions"] = [region("region_1"), region("region_2")]
    return payload(**extra, **{kind: [item]}, **over)


# --- §10 ACCEPTED: unknown + structurally empty ------------------------------
@pytest.mark.parametrize("kind,item,field", [
    ("connections", connection("connection_1"), "unknown_null"),
    ("connections", connection("connection_1"), "connection_refs"),
    ("connections", connection("connection_1"), "connection_refs_placeholder"),
    ("regions", region("region_1"), "relation_note"),
    ("functions", function("function_1"), "some_unknown"),
    ("circuits", circuit("circuit_1", region_refs=["region_1", "region_2"]),
     "some_unknown"),
    ("functions", function("function_1"), "empty_object"),
])
def test_benign_a_unknown_empty_extras_are_removed(kind, item, field):
    """null, [] and {} on ANY of the four types."""
    item[field] = {"unknown_null": None, "connection_refs": [],
                   "connection_refs_placeholder": None, "relation_note": None,
                   "some_unknown": [], "empty_object": {}}[field]
    result = parse(_with(kind, item))
    assert result.ok, (kind, field, result.error)
    assert _absent(getattr(result.data, kind)[0], field)


def test_benign_a_the_exact_live_round_12_failure_now_parses():
    """The recorded failure, reproduced field for field."""
    item = connection("connection_1")
    item["connection_refs"] = []
    item["connection_refs_placeholder"] = None
    result = parse(_with("connections", item))
    assert result.ok, result.error
    assert _absent(result.data.connections[0], "connection_refs",
                   "connection_refs_placeholder")


# --- §4 THE COLLISION: the same key, judged by the declaring type ------------
def test_benign_the_collision_rule_connection_refs_on_a_CIRCUIT_is_legitimate():
    """`connection_refs` is DECLARED on CircuitCandidate. On a Circuit it is
    preserved exactly as written, empty or not."""
    data = circuit("circuit_1", region_refs=["region_1", "region_2"],
                   connection_refs=[])
    result = parse(_with("circuits", data))
    assert result.ok, result.error
    assert result.data.circuits[0].connection_refs == []


def test_benign_the_collision_rule_connection_refs_on_a_CONNECTION_is_unknown():
    """On a Connection the SAME key is unknown: empty is dropped, content fails."""
    empty = connection("connection_1")
    empty["connection_refs"] = []
    assert parse(_with("connections", empty)).ok

    populated = connection("connection_1")
    populated["connection_refs"] = ["connection_1"]
    result = parse(_with("connections", populated))
    assert not result.ok, "a populated wrong-type field is content, not noise"
    assert "extra_forbidden" in result.error


# --- §11 REJECTED: unknown + content -----------------------------------------
@pytest.mark.parametrize("kind,item,field,value", [
    ("connections", connection("connection_1"), "connection_refs", ["connection_1"]),
    ("connections", connection("connection_1"), "relation_note", "something"),
    ("regions", region("region_1"), "relation_note", "semantic content"),
    ("functions", function("function_1"), "unknown", ["x"]),
    ("circuits", circuit("circuit_1", region_refs=["region_1", "region_2"]),
     "unknown", {"x": 1}),
    ("connections", connection("connection_1"), "unknown", False),
    ("connections", connection("connection_1"), "unknown", 0),
    ("connections", connection("connection_1"), "unknown", True),
    ("connections", connection("connection_1"), "unknown", 1),
    ("connections", connection("connection_1"), "unknown", ""),
])
def test_benign_b_unknown_NON_empty_extras_still_fail(kind, item, field, value):
    """Content is never silently discarded — including the falsy values that a
    truthiness test would have swallowed."""
    item[field] = value
    result = parse(_with(kind, item))
    assert not result.ok, (kind, field, value)
    assert "extra_forbidden" in result.error


def test_benign_b_a_region_of_the_same_name_still_carries_content():
    """The old region-only repair would have dropped this ONLY if it were null;
    with content it was always fatal, and still is."""
    data = region("region_1")
    data["relation_note"] = "projects strongly to CA3"
    assert not parse(payload(regions=[data])).ok


# --- §12 a KNOWN empty field is preserved ------------------------------------
def test_benign_c_a_DECLARED_empty_field_survives_untouched():
    """Only UNKNOWN+empty is removed. A declared field that happens to be empty
    is the model's statement and stays."""
    data = circuit("circuit_1", region_refs=["region_1", "region_2"],
                   connection_refs=[], function_refs=[])
    result = parse(_with("circuits", data))
    assert result.ok, result.error
    assert result.data.circuits[0].connection_refs == []
    assert result.data.circuits[0].function_refs == []
    # and a declared field that is empty on a connection survives too
    conn = connection("connection_1")
    conn["rationale"] = ""
    result = parse(_with("connections", conn))
    assert result.ok, result.error
    assert result.data.connections[0].rationale == ""


# --- §13 no other science is touched -----------------------------------------
def test_benign_d_nothing_else_in_the_response_changes():
    data = payload(
        regions=[region("region_1", name="Kept Region"),
                 region("region_2", name="Kept Region 2")],
        connections=[connection("connection_1", source_ref="region_1",
                                target_ref="region_2", confidence=0.42,
                                connection_type="PROJECTION",
                                directionality="DIRECTED")],
        functions=[function("function_1", label="Kept Function")],
        circuits=[circuit("circuit_1", name="Kept Circuit",
                          region_refs=["region_1", "region_2"],
                          connection_refs=["connection_1"],
                          topology_hint="RECURRENT", confidence=0.33,
                          description="kept description",
                          rationale="kept rationale")],
        warnings=[],
    )
    data["connections"][0]["connection_refs"] = []          # benign, dropped
    data["connections"][0]["connection_refs_placeholder"] = None
    before = json.dumps(data, sort_keys=True)

    result = parse(data)
    assert result.ok, result.error
    out = result.data
    assert [r.name for r in out.regions] == ["Kept Region", "Kept Region 2"]
    assert out.connections[0].source_ref == "region_1"
    assert out.connections[0].target_ref == "region_2"
    assert out.connections[0].confidence == 0.42
    assert out.connections[0].connection_type == "PROJECTION"
    assert out.connections[0].directionality == "DIRECTED"
    assert out.functions[0].label == "Kept Function"
    c = out.circuits[0]
    assert (c.name, c.confidence, c.topology_hint) == (
        "Kept Circuit", 0.33, "RECURRENT")
    assert c.description == "kept description"
    assert c.rationale == "kept rationale"
    assert c.region_refs == ["region_1", "region_2"]
    assert c.connection_refs == ["connection_1"]
    # the input mapping itself is not mutated in place
    assert json.dumps(data, sort_keys=True) == before


# --- the policy is per TYPE, from the contract, not a hand-written list ------
def test_benign_the_declared_field_sets_come_from_the_schema():
    assert parser._ARRAY_SCHEMAS == {
        "regions": RegionCandidate, "connections": ConnectionCandidate,
        "functions": FunctionCandidate, "circuits": CircuitCandidate,
    }
    for name, model in parser._ARRAY_SCHEMAS.items():
        assert model.model_config["extra"] == "forbid", name


def test_benign_the_schema_was_NOT_made_permissive():
    """extra='forbid' everywhere. The tolerance is a pre-validation boundary,
    never a schema relaxation."""
    for model in (LlmDiscoveryResponse, RegionCandidate, ConnectionCandidate,
                  FunctionCandidate, CircuitCandidate):
        assert model.model_config["extra"] == "forbid", model.__name__


def test_benign_empty_means_empty_not_falsy():
    """The one function the whole policy rests on."""
    for empty in (None, [], {}):
        assert parser._is_benign_empty(empty), empty
    for content in ("", 0, 1, False, True, "x", [0], {"a": 1}):
        assert not parser._is_benign_empty(content), content


# ===========================================================================
# §33 — DISCOVERY ENVELOPE EXTRACTION
# ===========================================================================
# A Discovery response is a DOCUMENT, and the parser now decides that
# structurally instead of trusting a heuristic score. The cases below are the
# read-only diagnosis, made permanent: A–F are the behaviours that were already
# correct and must stay correct; L1–L4, M1 and M2 are the proven vulnerability.
#
# The last test in the vulnerability group asserts that the GENERIC extractor
# still returns the bare RegionCandidate for the same text. That is deliberate:
# the generic behaviour is unchanged on purpose (connection completion depends on
# it), and the point of this layer is that Discovery no longer believes it.
REGION_DOC = {
    "local_id": "region_1",
    "confidence": 0.9,
    "name": "Dentate gyrus (granule cell layer)",
    "name_en": "Dentate gyrus",
    "name_zh": "齿状回",
    "hemisphere": "left",
    "species_taxon_id": "9606",
    "relation_to_seed": "AFFERENT",
    "rationale": "Primary afferent source of the dentate-CA3 sub-circuits.",
}


def region_doc(**over: Any) -> str:
    data = dict(REGION_DOC)
    data.update(over)
    return json.dumps(data, ensure_ascii=False)


def envelope(**over: Any) -> str:
    return json.dumps(payload(**over), ensure_ascii=False)


# --- A–F: the behaviours that were already correct ---------------------------
def test_envelope_a_a_complete_envelope_parses():
    result = parse_text(envelope(regions=[region("region_1")]))
    assert result.ok, result.error
    assert [r.local_id for r in result.data.regions] == ["region_1"]


def test_envelope_b_prose_around_an_envelope_parses():
    result = parse_text("Here is the analysis:\n" + envelope(regions=[region("region_1")])
                        + "\nDone.")
    assert result.ok, result.error
    assert [r.local_id for r in result.data.regions] == ["region_1"]


def test_envelope_c_a_fenced_envelope_parses():
    result = parse_text(f"```json\n{envelope(regions=[region('region_1')])}\n```")
    assert result.ok, result.error
    assert [r.local_id for r in result.data.regions] == ["region_1"]


def test_envelope_d_a_bare_object_sibling_does_not_beat_the_envelope():
    """The envelope is chosen on IDENTITY, not on which object came first."""
    result = parse_text(region_doc() + "\n" + envelope(regions=[region("region_1")]))
    assert result.ok, result.error
    assert result.data.seed_entity_id == SEED_ID
    assert [r.local_id for r in result.data.regions] == ["region_1"]


def test_envelope_e_a_nested_object_never_becomes_the_document():
    """The envelope contains a region whose keys are all valid region keys."""
    result = parse_text(envelope(regions=[region("region_1", name="Dentate gyrus")]))
    assert result.ok, result.error
    assert result.data.seed_entity_id == SEED_ID
    assert result.data.regions[0].name == "Dentate gyrus"


def test_envelope_f_a_diagnostic_sibling_does_not_beat_the_envelope():
    result = parse_text(json.dumps({"status": "thinking", "step": 1}) + "\n"
                        + envelope(regions=[region("region_1")]))
    assert result.ok, result.error
    assert result.data.seed_entity_id == SEED_ID


# --- G / H: the two new typed refusals --------------------------------------
def test_envelope_g_a_bare_candidate_is_not_a_document():
    result = parse_text(region_doc())
    assert not result.ok
    assert result.error.startswith(parser.ERR_ENVELOPE_MISSING), result.error


def test_envelope_g2_a_bare_candidate_is_never_wrapped():
    """No envelope is invented. Missing collections must not be fabricated."""
    result = parse_text(region_doc())
    assert result.data is None
    for fabricated in ("regions", "connections", "functions", "circuits"):
        assert fabricated in result.error or result.data is None


def test_envelope_h_two_independent_envelopes_are_refused():
    first = envelope(seed_entity_id=SEED_ID, summary="one")
    second = envelope(summary="two")
    result = parse_text(first + "\n" + second)
    assert not result.ok
    assert result.error.startswith(parser.ERR_ENVELOPE_AMBIGUOUS), result.error


def test_envelope_h2_ambiguity_is_not_resolved_by_position():
    """Swapping the two envelopes must not change the outcome."""
    first = envelope(summary="one")
    second = envelope(summary="two")
    assert not parse_text(first + "\n" + second).ok
    assert not parse_text(second + "\n" + first).ok


# --- §13 the proven vulnerability: a malformed envelope must not leak a child --
def test_envelope_l1_a_missing_comma_does_not_leak_the_nested_region():
    text = ('{"schema_version": "1.0", "seed_entity_id": "%s", "regions": [%s]'
            ' "connections": [], "circuits": []}' % (SEED_ID, region_doc()))
    result = parse_text(text)
    assert not result.ok
    assert result.error.startswith(parser.ERR_ENVELOPE_MISSING), result.error


def test_envelope_l2_a_stray_member_does_not_leak_the_nested_region():
    text = ('{"schema_version": "1.0", "seed_entity_id": "%s", "regions": [%s],'
            ' "connections": [], "oops": }' % (SEED_ID, region_doc()))
    assert not parse_text(text).ok


def test_envelope_l3_a_single_quoted_key_does_not_leak_the_nested_region():
    text = ("{'schema_version': '1.0', 'seed_entity_id': '%s', 'regions': [%s],"
            " 'connections': []}" % (SEED_ID, region_doc()))
    assert not parse_text(text).ok


def test_envelope_l4_a_raw_newline_in_a_string_does_not_leak_the_nested_region():
    text = ('{"schema_version": "1.0", "seed_entity_id": "%s",'
            ' "summary": "line one\nline two", "regions": [%s], "connections": []}'
            % (SEED_ID, region_doc()))
    assert not parse_text(text).ok


def test_envelope_m1_a_balanced_invalid_parent_does_not_leak_its_child():
    text = '{"note": "oops" "inner": %s}' % region_doc()
    result = parse_text(text)
    assert not result.ok
    assert result.error.startswith(parser.ERR_ENVELOPE_MISSING), result.error


def test_envelope_m2_a_valid_parent_is_not_outranked_by_its_child():
    """The scoring inversion, made permanent. The parent here is VALID JSON and
    the child is richer in plain keys, which is exactly the case the generic
    score prefers the child."""
    text = '{"note": "ok", "inner": %s}' % region_doc()
    result = parse_text(text)
    assert not result.ok
    assert result.error.startswith(parser.ERR_ENVELOPE_MISSING), result.error


def test_envelope_the_generic_extractor_is_unchanged_and_discovery_no_longer_believes_it():
    """Both halves of the repair, in one place.

    The generic extractor still answers its own question the way it always did —
    that behaviour is load-bearing for connection completion. Discovery simply
    stopped treating that answer as a document.
    """
    text = '{"note": "oops" "inner": %s}' % region_doc()

    generic, err = extract_json_object_from_text(text)
    assert err is None
    assert generic["local_id"] == "region_1", "the generic behaviour is unchanged"

    result = parse_text(text)
    assert not result.ok
    assert result.error.startswith(parser.ERR_ENVELOPE_MISSING)


# --- §14 the protection is not Region-specific -------------------------------
@pytest.mark.parametrize("body", [
    json.dumps(region("region_1")),
    json.dumps(connection("connection_1")),
    json.dumps(function("function_1")),
    json.dumps(circuit("circuit_1")),
])
def test_envelope_every_bare_object_type_is_refused(body):
    result = parse_text(body)
    assert not result.ok, body
    assert result.error.startswith(parser.ERR_ENVELOPE_MISSING), (body, result.error)


def test_envelope_an_unknown_NON_empty_extra_still_fails():
    """The new layer relaxes nothing: an envelope with real extra content is
    still the strict schema's business."""
    body = circuit("circuit_1", invented_field="carries meaning")
    result = parse_text(envelope(circuits=[body]))
    assert not result.ok
    assert parser.ERR_SCHEMA_INVALID in result.error


def test_envelope_the_benign_empty_sanitizer_still_runs():
    body = region("region_1")
    body["relation_note"] = None
    result = parse_text(envelope(regions=[body]))
    assert result.ok, result.error
    assert not hasattr(result.data.regions[0], "relation_note")


def test_envelope_the_warning_alias_still_normalizes():
    result = parse_text(envelope(warnings=[warning("AMBIGUOUS_DIRECTIONALITY")]))
    assert result.ok, result.error
    assert [w.code for w in result.data.warnings] == ["AMBIGUOUS_DIRECTION"]


def test_envelope_a_schema_violation_inside_a_real_envelope_is_SCHEMA_INVALID():
    """The envelope decisions must not swallow the contract's own errors."""
    result = parse_text(envelope(seed_entity_id="NGIQ-BR-00000001"))
    assert not result.ok
    assert parser.ERR_SEED_MISMATCH in result.error


# --- provenance ---------------------------------------------------------------
def test_envelope_modes_are_reported():
    doc, mode, err = parser._extract_discovery_document(envelope())
    assert err is None and mode == parser._ENVELOPE_MODE_WHOLE

    doc, mode, err = parser._extract_discovery_document(f"```json\n{envelope()}\n```")
    assert err is None and mode == parser._ENVELOPE_MODE_FENCED

    doc, mode, err = parser._extract_discovery_document("prose\n" + envelope())
    assert err is None and mode == parser._ENVELOPE_MODE_SPAN


def test_envelope_a_truncated_document_is_repaired_but_only_from_the_outside():
    """A response cut off by its output budget keeps what it emitted.

    The repair closes the OUTER object's own brackets. It is gated by the same
    envelope identity, so it can never promote a nested object.
    """
    whole = envelope(regions=[region("region_1")])
    truncated = whole[: whole.rindex('"warnings"')].rstrip().rstrip(",")
    doc, mode, err = parser._extract_discovery_document(truncated)
    assert err is None, err
    assert doc["seed_entity_id"] == SEED_ID
    assert [r["local_id"] for r in doc["regions"]] == ["region_1"]

    # ...and the SAME repair applied to a bare region is still refused. Nothing
    # decodes and no balanced document exists, so this is not even a document —
    # it is reported as an unfixable JSON failure rather than as an envelope.
    broken = region_doc()[: region_doc().rindex('"rationale"')].rstrip().rstrip(",")
    doc2, _, err2 = parser._extract_discovery_document(broken)
    assert doc2 is None
    assert err2.startswith(parser.ERR_INVALID_JSON), err2


def test_envelope_identity_comes_from_the_contract():
    assert parser._ENVELOPE_REQUIRED == frozenset(
        name for name, spec in LlmDiscoveryResponse.model_fields.items()
        if spec.is_required()
    )
    assert parser._ENVELOPE_REQUIRED == {"seed_entity_id"}
    assert parser._ENVELOPE_COLLECTIONS == frozenset(
        {"regions", "connections", "functions", "circuits"})


def test_envelope_identity_rejects_every_candidate_type():
    for bare in (region("region_1"), connection("connection_1"),
                 function("function_1"), circuit("circuit_1"), [], "text", None):
        assert not parser._looks_like_discovery_envelope(bare), bare
    assert parser._looks_like_discovery_envelope(payload())


def test_envelope_nothing_decodable_is_still_INVALID_JSON():
    """The new code must not reclassify a non-JSON answer."""
    result = parse_text("this is not json at all")
    assert not result.ok
    assert result.error.startswith(parser.ERR_INVALID_JSON)
