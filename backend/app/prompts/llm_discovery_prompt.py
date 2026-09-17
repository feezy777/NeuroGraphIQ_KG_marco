"""Phase 3A — versioned prompt for LLM Discovery (contract only, no execution).

This module BUILDS a prompt. It never sends one: there is no provider call and
no network access anywhere on this path (Phase 3B connects execution).

The output schema description is DERIVED from the typed contract in
``app.schemas.llm_discovery`` rather than hand-written, so the prompt cannot
drift away from what the parser actually accepts.
"""
from __future__ import annotations

import json
import re
import types as _types
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel

from app.schemas.llm_discovery import (
    CIRCUIT_TOPOLOGY_HINTS,
    CONNECTION_DIRECTIONALITIES,
    CONNECTION_TYPES,
    HUMAN_TAXON_ID,
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
#   1.2.0 — Phase 3B.4. A real model with an ample budget returned `conn_1`
#           where the contract requires `connection_1`: the field reference said
#           only `local_id: string`, and `<type>_<number>` was too abstract to
#           survive contact with a domain that abbreviates constantly. Adds
#           explicit per-type prefixes, a prohibition on abbreviation, and one
#           validated format-only example.
#   1.3.0 — Hemisphere-aware. Regions now carry `hemisphere_context` in a closed
#           vocabulary, so the prompt states the vocabulary, the rule that a
#           side is never inferred from the seed, and — for the first time —
#           tells the model what SEED IS rather than only what it is called.
#           The seed's own hemisphere was already in the seed block; what was
#           missing is that a stated side is a property of the SEED alone.
#
# The contract's own `schema_version` is a SEPARATE thing: it tracks the SHAPE
# a response must have (1.1 for hemisphere-aware), not how that shape is
# described. Prompt text and response shape move together here, so both version
# markers move together; they stay separate fields because a wording change
# alone must never invalidate stored payloads.
PROMPT_KEY = "knowledge_production.llm_discovery"
PROMPT_VERSION = "1.3.0"

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


def local_id_prefixes() -> tuple[str, ...]:
    """The accepted local-id prefixes, READ FROM the contract's own regex.

    Restating them by hand would create a second authority that can silently
    disagree with the validator that actually decides.
    """
    seen: list[str] = []
    for prefix in re.findall(r"[a-z]+", LOCAL_ID_PATTERN.pattern):
        if prefix not in seen:
            seen.append(prefix)
    return tuple(seen)


def local_id_shape() -> str:
    """`region_<n>|connection_<n>|function_<n>|circuit_<n>` for the prompt."""
    return "|".join(f"{prefix}_<n>" for prefix in local_id_prefixes())


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


def build_format_example(seed_entity_id: str) -> dict[str, Any]:
    """A COMPLETE, contract-valid illustration of the response format.

    Two invariants, both enforced below rather than asserted in a comment:

      * it is a VALIDATED ILLUSTRATION, never a second schema — it is built as
        a plain dict and returned only after ``LlmDiscoveryResponse`` accepts
        it, so the typed contract stays the single authority;
      * its content is deliberately NON-SCIENTIFIC. Placeholder names only, so
        the example cannot bias what the model proposes for the real seed. In
        particular it declares no human taxon: a placeholder region has no
        species identity, and the contract is explicit that absent information
        must never be rendered as HUMAN.
    """
    unknown = {"scope": "UNKNOWN", "taxon_ids": []}
    example: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "seed_entity_id": seed_entity_id,
        "summary": "Format example only.",
        "regions": [
            {
                "local_id": "region_1",
                "name": "Example Region",
                "species_taxon_id": None,
                "relation_to_seed": "UNKNOWN",
                "confidence": 0.5,
            }
        ],
        "connections": [
            {
                "local_id": "connection_1",
                "source_ref": SEED_REF,
                "target_ref": "region_1",
                "connection_type": "UNKNOWN",
                "directionality": "UNKNOWN",
                "confidence": 0.5,
                "species_context": dict(unknown),
            }
        ],
        "functions": [
            {
                "local_id": "function_1",
                "label": "Example Function",
                "related_region_refs": ["region_1"],
                "confidence": 0.5,
                "species_context": dict(unknown),
            }
        ],
        "circuits": [
            {
                "local_id": "circuit_1",
                "name": "Example Circuit",
                # SEED appears in a circuit too, so the model never invents a
                # region candidate for the seed it was already given.
                "region_refs": [SEED_REF, "region_1"],
                "connection_refs": ["connection_1"],
                "function_refs": ["function_1"],
                "topology_hint": "UNKNOWN",
                "confidence": 0.5,
                "species_context": dict(unknown),
            }
        ],
        "source_hints": [],
        "warnings": [],
    }
    # Fail loudly here rather than teach the model a shape the parser rejects.
    LlmDiscoveryResponse.model_validate(example)
    return example


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
            if name == "local_id" and field.is_required():
                # The annotation alone renders as a bare `string`, which is
                # what a real model read while writing `conn_1`. State the
                # constraint where the value is actually written.
                label = f"{label} - MUST match {local_id_shape()}"
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

8. LATERALITY. Every region carries a `hemisphere_context` saying what you
   know about THAT structure's side, in exactly one of these values:

     LEFT, RIGHT                 you know the structure's own side
     BILATERAL                   the structure spans both sides
     MIDLINE                     the structure is midline / unpaired
     IPSILATERAL_TO_SEED         the same side as the seed
     CONTRALATERAL_TO_SEED       the opposite side from the seed
     UNSPECIFIED                 you do not know, or a side does not apply

   Prefer a RELATIVE value when the relationship is what you actually know:
   "the contralateral CA3" is CONTRALATERAL_TO_SEED, and it stays correct
   whichever side the seed is on. Do not convert it into LEFT or RIGHT.

   NEVER infer a side from the seed. A seed on the left does NOT make the
   structures you propose left, does not make its partners right, and does not
   make them bilateral. If you do not know a side, write UNSPECIFIED: that is a
   complete answer, not a missing one, and once stored a guessed side is
   indistinguishable from a known one.

   A connection, circuit or function does NOT carry a laterality. Their sides
   follow from the regions they reference, so state the side on the REGION and
   let it follow.

9. NO EVIDENCE CLAIMS. Do not claim that something is proven, and do not
   fabricate evidence, quotations or citations.

10. ONLY THE FIELDS IN THE SCHEMA. Return exactly the fields defined below and
   nothing else. Do NOT add quotations, evidence passages, page numbers,
   offsets, citation blocks, confidence explanations, or any other field of
   your own invention. An undefined field is treated as an error, not ignored.

11. OUTPUT JSON ONLY. Return exactly one JSON object and nothing else: no
   markdown, no code fences, no commentary before or after it.

12. RESPONSE ROOT. The answer is ONE JSON object whose first-level keys are
   exactly: schema_version, seed_entity_id, summary, regions, connections,
   functions, circuits, source_hints, warnings.

   The root is an OBJECT. Never return a JSON array at the root.
   There is no "top_level" key and no envelope around the answer: do not wrap
   the candidates in an outer object, and do not return a schema description,
   a field reference, or JSON Schema metadata instead of the answer. A field
   reference describes the ITEMS INSIDE the arrays; it is not the response.
"""


def build_seed_identity_note(seed: LlmDiscoveryInput) -> str:
    """State what SEED IS, not only what it is called (§6).

    The seed block is DATA. A model can read `seed_entity_id` as a label and
    still reason about a CATEGORY — "the hippocampus" rather than the one
    structure that was asked about — which is how a bilateral claim gets made
    about a region that was named on one side. Naming the identity in words is
    what pins the discovery to THIS region, at THIS granularity, on THIS side.

    The hemisphere sentence is deliberately a CONSTRAINED statement: it says the
    side is a property of the seed alone and is not evidence about anything the
    model proposes. A prompt that states the seed's side without that limit
    invites exactly the inference the contract forbids.
    """
    name = seed.seed_name_en or seed.seed_name_zh or seed.seed_entity_id
    hemisphere = (seed.seed_hemisphere or "").strip()
    granularity = (seed.seed_granularity_level or "").strip()

    lines = [
        f"SEED is exactly this canonical BrainRegion: {seed.seed_entity_id} "
        f"({name}). Everything you return is a hypothesis about THAT structure."
    ]
    if granularity:
        lines.append(
            f"Its granularity is {granularity}: discover that structure at that "
            "granularity, not a coarser or finer structure that resembles it."
        )
    if hemisphere:
        lines.append(
            f"Its hemisphere is {hemisphere}. That side belongs to the SEED "
            "alone (rule 8): it is what makes a relative value resolvable, and "
            "it is NOT evidence about the side of any region you propose."
        )
    else:
        lines.append(
            "Its hemisphere is not stated, so no relative laterality can be "
            "resolved: use LEFT or RIGHT only if you independently know that "
            "structure's side, otherwise UNSPECIFIED."
        )
    return "\n".join(lines)


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
            build_seed_identity_note(seed),
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
            "LOCAL ID RULES — read before writing any candidate",
            "=" * 68,
            "",
            "Every candidate declares a local_id. Its prefix is the FULL type "
            "name, lowercased, then `_`, then an integer starting at 1:",
            "",
            "  regions      local_id MUST be  region_<integer>      e.g. region_1",
            "  connections  local_id MUST be  connection_<integer>  e.g. connection_1",
            "  functions    local_id MUST be  function_<integer>    e.g. function_1",
            "  circuits     local_id MUST be  circuit_<integer>     e.g. circuit_1",
            "",
            "Do not abbreviate local-ID prefixes. NEVER write:",
            "  conn_1  edge_1  projection_1  conn1  (for a connection)",
            "  func_1  fn_1                  function1  (for a function)",
            "  circ_1  pathway_1             circuit1   (for a circuit)",
            "  reg_1   r1  region1                      (for a region)",
            "",
            "References MUST reuse a declared local_id EXACTLY, character for "
            "character: no abbreviation, no case change, no dropped underscore, "
            "and no new prefix. If you declare \"local_id\": \"connection_1\", "
            "then a circuit refers to it as \"connection_1\" — never \"conn_1\".",
            "",
            f"SEED is the one reserved reference. Do NOT invent region_0 or "
            f"region_seed for the seed: it is already known, and connections and "
            f"circuits point at it with {SEED_REF!r} directly.",
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
            "",
            "=" * 68,
            "C. FORMAT-ONLY EXAMPLE — structure and ID rules, NOT knowledge",
            "=" * 68,
            "",
            "This example demonstrates FORMAT ONLY. Do not copy its names or its "
            "scientific content, and do not treat it as a finding: generate "
            "candidates from the actual seed above.",
            "",
            "Its species values are placeholders. Decide the real species basis "
            "for each candidate you find — a human seed does not make a candidate "
            "human-established.",
            "",
            "```json",
            json.dumps(
                build_format_example(seed.seed_entity_id),
                ensure_ascii=False,
                indent=2,
            ),
            "```",
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
