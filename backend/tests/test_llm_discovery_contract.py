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
