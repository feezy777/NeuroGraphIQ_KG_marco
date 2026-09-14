"""Phase 3A — versioned prompt for LLM Discovery (contract only, no execution).

This module BUILDS a prompt. It never sends one: there is no provider call and
no network access anywhere on this path (Phase 3B connects execution).

The output schema description is DERIVED from the typed contract in
``app.schemas.llm_discovery`` rather than hand-written, so the prompt cannot
drift away from what the parser actually accepts.
"""
from __future__ import annotations

import json
from typing import Any

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
PROMPT_KEY = "knowledge_production.llm_discovery"
PROMPT_VERSION = "1.0.0"

_JSON_TYPES = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def _field_type(annotation: Any) -> str:
    """Compact, human-readable type label for one annotated field."""
    text = str(annotation)
    text = text.replace("typing.", "").replace("<class '", "").replace("'>", "")
    text = text.replace("NoneType", "null")
    return text


def compact_output_schema(model: type) -> dict[str, str]:
    """Field -> type map derived from a Pydantic model (single source of truth)."""
    return {name: _field_type(f.annotation) for name, f in model.model_fields.items()}


def build_output_schema_description() -> dict[str, Any]:
    """The machine-readable shape of the expected JSON object."""
    return {
        "schema_version": SCHEMA_VERSION,
        "top_level": compact_output_schema(LlmDiscoveryResponse),
        "RegionCandidate": compact_output_schema(RegionCandidate),
        "ConnectionCandidate": compact_output_schema(ConnectionCandidate),
        "FunctionCandidate": compact_output_schema(FunctionCandidate),
        "CircuitCandidate": compact_output_schema(CircuitCandidate),
        "SourceHint": compact_output_schema(SourceHint),
        # Required by connection/function/circuit, so the model must be told
        # its shape rather than left to guess.
        "SpeciesContext": compact_output_schema(SpeciesContext),
    }


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
            "Vocabulary (use these exact values):",
            f"- connection_type: {', '.join(CONNECTION_TYPES)}",
            f"- directionality: {', '.join(CONNECTION_DIRECTIONALITIES)}",
            f"- relation_to_seed: {', '.join(REGION_RELATIONS_TO_SEED)}",
            f"- topology_hint: {', '.join(CIRCUIT_TOPOLOGY_HINTS)}",
            f"- species_context.scope: {', '.join(SPECIES_SCOPES)}",
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
            f"Output exactly one JSON object with schema_version {SCHEMA_VERSION!r}:",
            "",
            "```json",
            json.dumps(build_output_schema_description(), ensure_ascii=False, indent=2),
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
