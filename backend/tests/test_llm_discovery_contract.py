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
    REGION_RELATIONS_TO_SEED,
    SCHEMA_VERSION,
    SEED_REF,
    SPECIES_SCOPES,
    CircuitCandidate,
    ConnectionCandidate,
    FunctionCandidate,
    LlmDiscoveryInput,
    RegionCandidate,
    SourceHint,
    SpeciesContext,
    is_local_candidate_id,
)
from app.services import llm_discovery_parser as parser

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
    body = json.dumps(payload(regions=[{"local_id": "region_1", "name": "X"}]))  # no confidence
    result = parse_text(f"Note: confidence was unclear.\n{body}")
    assert not result.ok, "a prose hint must not substitute for a required field"


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
    assert prompt_mod.PROMPT_VERSION == "1.0.0"


def test_prompt_parts_and_seed_context():
    built = prompt_mod.build_llm_discovery_prompt(seed())
    assert set(built) == {"prompt_key", "prompt_version", "system_prompt", "user_prompt"}
    assert built["prompt_version"] == "1.0.0"

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
    """Derived, not hand-written: adding a field cannot silently desync them."""
    described = prompt_mod.build_output_schema_description()
    assert described["top_level"] == prompt_mod.compact_output_schema(
        __import__("app.schemas.llm_discovery", fromlist=["LlmDiscoveryResponse"]).LlmDiscoveryResponse
    )
    for model, key in (
        (RegionCandidate, "RegionCandidate"),
        (ConnectionCandidate, "ConnectionCandidate"),
        (FunctionCandidate, "FunctionCandidate"),
        (CircuitCandidate, "CircuitCandidate"),
        (SourceHint, "SourceHint"),
    ):
        assert described[key] == prompt_mod.compact_output_schema(model)
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
    described = prompt_mod.build_output_schema_description()
    for key in ("ConnectionCandidate", "FunctionCandidate", "CircuitCandidate"):
        assert "species_context" in described[key], key
    # the referenced type is described too, so the model can produce it
    assert described["SpeciesContext"] == prompt_mod.compact_output_schema(SpeciesContext)
    assert "scope" in described["SpeciesContext"]
    assert "taxon_ids" in described["SpeciesContext"]
    assert "SpeciesContext" in prompt_mod.build_user_prompt(seed())
    user = prompt_mod.build_user_prompt(seed())
    for scope in SPECIES_SCOPES:
        assert scope in user, scope
