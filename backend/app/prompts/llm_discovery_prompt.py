"""Phase 3A — versioned prompt for LLM Discovery (contract only, no execution).

This module BUILDS a prompt. It never sends one: there is no provider call and
no network access anywhere on this path (Phase 3B connects execution).

The output schema description is DERIVED from the typed contract in
``app.schemas.llm_discovery`` rather than hand-written, so the prompt cannot
drift away from what the parser actually accepts.
"""
from __future__ import annotations

import json
import types as _types
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel

from app.schemas.llm_discovery import (
    CIRCUIT_TOPOLOGY_HINTS,
    CONNECTION_DIRECTIONALITIES,
    CONNECTION_TYPES,
    HUMAN_TAXON_ID,
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
)

# Frozen prompt identity. Bump PROMPT_VERSION whenever the instructions or the
# expected output shape change: the version is persisted on the Discovery Run
# so a stored result can always be traced back to the contract that produced it.
#
#   1.0.0 — Phase 3A. The schema description was embedded AS a JSON object with
#           a `top_level` wrapper, which a real model returned as its answer.
#   1.1.0 — Phase 3B.2. The response root is stated explicitly and the schema
#           description is split into a root skeleton plus a plain-text field
#           reference. Two different prompt TEXTS must never share a version,
#           or a stored run's provenance stops identifying what produced it.
#
# The contract's own `schema_version` (1.0) is a SEPARATE thing: the science did
# not change, only how it is described to the model.
PROMPT_KEY = "knowledge_production.llm_discovery"
PROMPT_VERSION = "1.1.0"

_SCALARS = {str: "string", int: "integer", float: "number", bool: "boolean"}


def _json_type_label(annotation: Any) -> str:
    """Render a Python annotation as a JSON-facing type label.

    Python reprs leak module paths (`list[app.schemas...RegionCandidate]`) that a
    model can neither act on nor cheaply tokenise. These labels say the same
    thing in the language the model actually has to emit.
    """
    if annotation is type(None):
        return "null"
    origin = get_origin(annotation)
    if origin in (Union, _types.UnionType):
        parts = [_json_type_label(a) for a in get_args(annotation)]
        return "|".join(p for p in parts if p != "null") + ("|null" if "null" in parts else "")
    if origin is Literal:
        return "enum(" + "|".join(str(a) for a in get_args(annotation)) + ")"
    if origin is list:
        args = get_args(annotation)
        return "array<" + (_json_type_label(args[0]) if args else "any") + ">"
    if isinstance(annotation, type):
        if annotation in _SCALARS:
            return _SCALARS[annotation]
        if issubclass(annotation, BaseModel):
            return annotation.__name__
    return str(annotation).replace("typing.", "")


def compact_output_schema(model: type[BaseModel]) -> dict[str, str]:
    """Field -> JSON type label, derived from a Pydantic model (single authority)."""
    return {
        name: _json_type_label(field.annotation)
        for name, field in model.model_fields.items()
    }


#: The ONE object the model must return. Every key comes from the typed
#: contract, so a new top-level field appears here automatically.
def build_response_root_skeleton() -> dict[str, Any]:
    """Literal shape of the response root: the contract's own top-level fields."""
    skeleton: dict[str, Any] = {}
    for name, field in LlmDiscoveryResponse.model_fields.items():
        default = field.default
        if isinstance(default, (str, int, float, bool)):
            # A declared constant (schema_version) is shown as its real value.
            skeleton[name] = default
        elif get_origin(field.annotation) is list:
            skeleton[name] = []
        else:
            skeleton[name] = f"<{name}>"
    return skeleton


#: Model -> how the model is reached from the response root. Ordered so the
#: arrays are described before the shared sub-object they depend on.
_FIELD_DEFINITION_MODELS: tuple[tuple[type[BaseModel], str], ...] = (
    (RegionCandidate, 'items of "regions"'),
    (ConnectionCandidate, 'items of "connections"'),
    (FunctionCandidate, 'items of "functions"'),
    (CircuitCandidate, 'items of "circuits"'),
    (SourceHint, 'items of "source_hints"'),
    (
        SpeciesContext,
        'the "species_context" object of every connection, function and circuit',
    ),
    (DiscoveryWarning, 'items of "warnings"'),
)


def build_field_definitions() -> str:
    """Plain-text field reference, rendered from the typed contract.

    Deliberately NOT a JSON object: a JSON envelope here is indistinguishable
    from an example answer, and the model will return it as one.
    """
    blocks: list[str] = []
    for model, used_by in _FIELD_DEFINITION_MODELS:
        lines = [f"{model.__name__}  ({used_by})"]
        for name, field in model.model_fields.items():
            label = _json_type_label(field.annotation)
            default = field.default
            suffix = (
                f"  default={default}"
                if not field.is_required() and isinstance(default, (str, int, float))
                else ""
            )
            lines.append(f"  {name}: {label}{suffix}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


SYSTEM_PROMPT = """\
You are a neuroscience knowledge DISCOVERY assistant.

Your job is HIGH-RECALL HYPOTHESIS GENERATION about one BrainRegion: propose
what may be connected to it, which circuits it takes part in, and what
functions it may serve.

Every candidate you produce is a HYPOTHESIS awaiting human review, never a
fact. You are not verifying evidence and you are not creating knowledge.

Rules you must obey:

1. IDENTIFIERS. Use ONLY ephemeral local ids of the form <type>_<number>
   (region_1, connection_2, function_1, circuit_3). NEVER invent a canonical
   id such as NGIQ-BR-..., NGIQ-CONN-..., NGIQ-CIRCUIT-..., and never output a
   database key. The only canonical id in this task is the seed id given to
   you; reference the seed with the reserved token SEED.

2. DISTINGUISH THE TYPES. A region is a structure. A connection is a relation
   between two regions. A PROJECTION is a specific kind of connection
   (a directed fibre pathway) - do NOT label every connection a PROJECTION,
   and do not silently downgrade a projection to a generic connection. A
   circuit is an organized multi-region pathway with functional coherence. A
   function is a role or process.

3. CIRCUITS ARE NOT REQUIRED TO BE CLOSED LOOPS. A circuit may be
   feedforward, convergent, divergent, parallel or a network. Use the topology
   hint that actually fits; use UNKNOWN when the shape is unclear.

4. CONNECTION TYPE. Use exactly one of the allowed vocabulary values. Use
   UNKNOWN when the information does not say - never guess a type.

5. CONFIDENCE. Give a numeric confidence in [0.0, 1.0] for each candidate.
   It is YOUR OWN assessment that the hypothesis is worth reviewing. It is not
   evidence quality and not a probability of truth.

6. SOURCES. `source_hints` are things you REMEMBER. They are unverified leads,
   never evidence. Do not present them as proof. Do not provide quotations,
   page numbers or excerpts: you are not reading any document in this task.

7. SPECIES BASIS. Every connection, circuit and function MUST carry a
   `species_context` with two parts: `scope` (exactly one of HUMAN, NON_HUMAN,
   MIXED, UNKNOWN) and `taxon_ids` (NCBI taxonomy ids, e.g. 9606 human,
   10090 mouse, 10116 rat).

   A HUMAN BrainRegion seed does NOT imply that every discovered connection,
   circuit or function is established in humans. Much of what you recall may
   come from rodent or primate work, and saying so is correct, not a defect.

   Use scope HUMAN only when the knowledge itself is human-established.
   Use NON_HUMAN or MIXED when animal work is part of the basis.
   Use UNKNOWN when the species basis is unclear. Never silently convert
   animal knowledge into HUMAN, and never guess a taxon id.

8. NO EVIDENCE CLAIMS. Do not claim that something is proven, and do not
   fabricate evidence, quotations or citations.

9. ONLY THE FIELDS IN THE SCHEMA. Return exactly the fields defined below and
   nothing else. Do NOT add quotations, evidence passages, page numbers,
   offsets, citation blocks, confidence explanations, or any other field of
   your own invention. An undefined field is treated as an error, not ignored.

10. OUTPUT JSON ONLY. Return exactly one JSON object and nothing else: no
   markdown, no code fences, no commentary before or after it.

11. RESPONSE ROOT. The answer is ONE JSON object whose first-level keys are
   exactly: schema_version, seed_entity_id, summary, regions, connections,
   functions, circuits, source_hints, warnings.

   The root is an OBJECT. Never return a JSON array at the root.
   There is no "top_level" key and no envelope around the answer: do not wrap
   the candidates in an outer object, and do not return a schema description,
   a field reference, or JSON Schema metadata instead of the answer. A field
   reference describes the ITEMS INSIDE the arrays; it is not the response.
"""


def build_user_prompt(seed: LlmDiscoveryInput) -> str:
    """The seed-specific half of the prompt."""
    seed_block = {
        "seed_entity_id": seed.seed_entity_id,
        "name_en": seed.seed_name_en,
        "name_zh": seed.seed_name_zh,
        "granularity_level": seed.seed_granularity_level,
        "hemisphere": seed.seed_hemisphere,
        "species_taxon_id": seed.species_taxon_id,
        "source_atlases": seed.source_atlas_names,
        "parent_region_name": seed.parent_region_name,
        "hierarchy_context": seed.hierarchy_context,
        "known_aliases": seed.known_aliases,
    }
    return "\n".join(
        [
            "Discover candidate knowledge for this BrainRegion seed:",
            "",
            "```json",
            json.dumps(seed_block, ensure_ascii=False, indent=2),
            "```",
            "",
            "Every connection, circuit and function must state its species_context.",
            f"Taxon ids use NCBI taxonomy ({HUMAN_TAXON_ID} = human, 10090 = mouse, "
            "10116 = rat). A human seed does not prove that a candidate is "
            "human-established: use UNKNOWN when the species basis is unclear "
            "rather than assuming HUMAN.",
            "",
            f"Reference the seed with the reserved ref {SEED_REF!r}; reference any "
            "other region by the local_id you declared for it.",
            "A circuit must reference at least two regions. Include at least one "
            "connection reference for it; if you cannot, still return the circuit "
            "and say so in a warning.",
            "",
            "=" * 68,
            "A. EXPECTED RESPONSE ROOT — the ONLY acceptable output",
            "=" * 68,
            "",
            "Return exactly ONE JSON object. It is the WHOLE answer.",
            "",
            "```json",
            json.dumps(build_response_root_skeleton(), ensure_ascii=False, indent=2),
            "```",
            "",
            "- The root MUST be an object. NEVER return a JSON array at the root.",
            "- The first-level keys MUST be exactly those above, and nothing else.",
            '- There is NO "top_level" key and NO wrapper or envelope.',
            "- Do NOT output a schema, a schema description, or JSON Schema "
            "keywords ($schema, properties, type, required, $defs).",
            "- Do NOT copy section B back. Section B is a reference, not the answer.",
            "",
            "=" * 68,
            "B. FIELD DEFINITIONS — the shape of the ITEMS inside those arrays",
            "=" * 68,
            "",
            "These describe the objects that go INSIDE the arrays of section A. "
            "They are not the response and must not be returned on their own.",
            "",
            build_field_definitions(),
        ]
    )


def build_llm_discovery_prompt(seed: LlmDiscoveryInput) -> dict[str, str]:
    """Return the ready-to-send prompt parts. Sending them is Phase 3B's job."""
    return {
        "prompt_key": PROMPT_KEY,
        "prompt_version": PROMPT_VERSION,
        "system_prompt": SYSTEM_PROMPT,
        "user_prompt": build_user_prompt(seed),
    }
