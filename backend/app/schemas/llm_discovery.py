"""Phase 3A — LLM Discovery structured contract (pure, no execution).

LLM Discovery is HIGH-RECALL HYPOTHESIS GENERATION. It is NOT evidence
verification, NOT canonicalization, and NOT formal knowledge creation.
Everything defined here is a CANDIDATE: a proposal that a later, governed
phase must review. Nothing in this module is persisted.

Three semantic defaults are frozen here for the FUTURE candidate layer. They
are constants, deliberately NOT written to any table by Phase 3A:

    source_type      = LLM_GENERATED
    evidence_status  = UNVERIFIED
    knowledge_status = CANDIDATE

Frozen boundaries:
  * local ephemeral ids only. The model must never invent `NGIQ-*` ids or a
    database key; the ONLY canonical id it ever receives is `seed_entity_id`.
  * `summary` is descriptive prose. Machine logic reads the structured arrays,
    never the summary.
  * a SourceHint is NOT Evidence (see §13 of the phase brief).
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# ===========================================================================
# Frozen contract version
# ===========================================================================
SCHEMA_VERSION = "1.0"

# The reserved reference for the known seed BrainRegion. Connections/circuits
# point at it directly instead of inventing a fake RegionCandidate for it.
SEED_REF = "SEED"

# Semantic defaults for the future candidate layer. NOT persisted in Phase 3A.
CANDIDATE_SOURCE_TYPE = "LLM_GENERATED"
CANDIDATE_EVIDENCE_STATUS = "UNVERIFIED"
CANDIDATE_KNOWLEDGE_STATUS = "CANDIDATE"

# Local ids are ephemeral and response-scoped. The pattern deliberately
# EXCLUDES anything that could look canonical (`NGIQ-BR-...` has uppercase
# letters and hyphens), which makes "the model invented a canonical id" a
# deterministic rejection rather than a judgement call.
LOCAL_ID_PATTERN = re.compile(r"^(region|connection|function|circuit)_[0-9]+$")


def is_local_candidate_id(value: str) -> bool:
    """True when `value` is a well-formed ephemeral local candidate id."""
    return bool(LOCAL_ID_PATTERN.match(value))


# ===========================================================================
# Vocabularies
# ===========================================================================
# connection_type maps 1:1 onto the frozen Gate7B
# `connections.connection_class` CHECK (structural_connection / projection /
# functional_connectivity / effective_connectivity) plus UNKNOWN, which is a
# DISCOVERY-ONLY marker: "the source did not say". UNKNOWN has no formal
# equivalent and must never be silently coerced into one.
ConnectionType = Literal[
    "STRUCTURAL",
    "PROJECTION",
    "FUNCTIONAL",
    "EFFECTIVE",
    "UNKNOWN",
]

# Mirrors `connections.directionality` (directed / non_directional /
# direction_unknown).
ConnectionDirectionality = Literal["DIRECTED", "NON_DIRECTIONAL", "UNKNOWN"]

RegionRelationToSeed = Literal[
    "AFFERENT",
    "EFFERENT",
    "RECIPROCAL",
    "CIRCUIT_MEMBER",
    "FUNCTIONALLY_RELATED",
    "UNKNOWN",
]

# A neural circuit is NOT required to be a closed loop. `LOOP` is one shape
# among many; Gate7B models closed-ness as the boolean property
# `circuits.is_closed_loop`, never as a requirement.
CircuitTopologyHint = Literal[
    "FEEDFORWARD",
    "FEEDBACK",
    "RECIPROCAL",
    "LOOP",
    "PARALLEL",
    "CONVERGENT",
    "DIVERGENT",
    "NETWORK",
    "UNKNOWN",
]

DiscoveryWarningCode = Literal[
    "POSSIBLE_HALLUCINATED_SOURCE",
    "UNCERTAIN_REGION_NAME",
    "AMBIGUOUS_DIRECTION",
    "CIRCUIT_WITHOUT_CONNECTION",
    "DUPLICATE_LOCAL_CANDIDATE",
    "CROSS_SPECIES_UNCERTAINTY",
    "OTHER",
]

CONNECTION_TYPES: tuple[str, ...] = (
    "STRUCTURAL",
    "PROJECTION",
    "FUNCTIONAL",
    "EFFECTIVE",
    "UNKNOWN",
)
CONNECTION_DIRECTIONALITIES: tuple[str, ...] = ("DIRECTED", "NON_DIRECTIONAL", "UNKNOWN")
REGION_RELATIONS_TO_SEED: tuple[str, ...] = (
    "AFFERENT",
    "EFFERENT",
    "RECIPROCAL",
    "CIRCUIT_MEMBER",
    "FUNCTIONALLY_RELATED",
    "UNKNOWN",
)
CIRCUIT_TOPOLOGY_HINTS: tuple[str, ...] = (
    "FEEDFORWARD",
    "FEEDBACK",
    "RECIPROCAL",
    "LOOP",
    "PARALLEL",
    "CONVERGENT",
    "DIVERGENT",
    "NETWORK",
    "UNKNOWN",
)
DISCOVERY_WARNING_CODES: tuple[str, ...] = (
    "POSSIBLE_HALLUCINATED_SOURCE",
    "UNCERTAIN_REGION_NAME",
    "AMBIGUOUS_DIRECTION",
    "CIRCUIT_WITHOUT_CONNECTION",
    "DUPLICATE_LOCAL_CANDIDATE",
    "CROSS_SPECIES_UNCERTAINTY",
    "OTHER",
)

# A circuit needs at least two region references to describe a relation at all.
MIN_CIRCUIT_REGION_REFS = 2


class _LocalIdMixin(BaseModel):
    """A candidate carrying an ephemeral, response-scoped local id."""

    local_id: str = Field(
        description="Ephemeral id, e.g. 'region_1'. Never a canonical NGIQ id."
    )

    @field_validator("local_id")
    @classmethod
    def _validate_local_id(cls, value: str) -> str:
        if not is_local_candidate_id(value):
            raise ValueError(
                f"'{value}' is not a local candidate id "
                f"(expected e.g. 'region_1'); canonical ids must never be invented"
            )
        return value


class _ConfidenceMixin(BaseModel):
    """Model self-assessed DISCOVERY confidence.

    This is the model's own belief that the hypothesis is worth reviewing. It
    is NOT evidence quality, NOT canonicalization confidence and NOT validation
    confidence. Those are separate, later judgements made by other layers.
    """

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Discovery confidence in [0.0, 1.0]. Not evidence quality.",
    )


# ===========================================================================
# Input contract — one BrainRegion seed
# ===========================================================================
class LlmDiscoveryInput(BaseModel):
    """The ONLY thing sent to the model that describes the world.

    Every field is deterministically sourceable from the Gate7B authority.
    Deliberately absent: candidate ids, mirror/final ids, database primary
    keys, credentials, and any whole-database dump.
    """

    seed_entity_id: str = Field(description="Canonical Gate7B id, e.g. NGIQ-BR-00000247")
    seed_name_en: str | None = None
    seed_name_zh: str | None = None
    seed_granularity_level: str | None = None
    seed_hemisphere: str | None = None
    species_taxon_id: str | None = None
    source_atlas_names: list[str] = Field(default_factory=list)

    # Optional deterministic context.
    parent_region_name: str | None = None
    hierarchy_context: str | None = None
    known_aliases: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_a_usable_name(self) -> "LlmDiscoveryInput":
        # The model needs something to reason about; a seed with no name at all
        # is not a discovery input.
        if not (self.seed_name_en or "").strip() and not (self.seed_name_zh or "").strip():
            raise ValueError("seed_name_en or seed_name_zh is required")
        return self


# ===========================================================================
# Candidate types — RAW DISCOVERY PROPOSALS, not canonical entities
# ===========================================================================
class RegionCandidate(_LocalIdMixin, _ConfidenceMixin):
    """A region the model proposes as relevant. NOT canonicalized.

    Phase 3A never maps this onto a Gate7B BrainRegion: name resolution is a
    later, governed step. `name` stays exactly as discovered.
    """

    name: str
    name_en: str | None = None
    name_zh: str | None = None
    hemisphere: str | None = None
    species_taxon_id: str | None = None
    relation_to_seed: RegionRelationToSeed = "UNKNOWN"
    rationale: str | None = None


class ConnectionCandidate(_LocalIdMixin, _ConfidenceMixin):
    """A connection the model proposes between two regions.

    `source_ref` / `target_ref` are either `SEED` or a declared
    RegionCandidate.local_id. For DIRECTED connections the order is semantic.
    """

    source_ref: str
    target_ref: str
    connection_type: ConnectionType = "UNKNOWN"
    directionality: ConnectionDirectionality = "UNKNOWN"
    rationale: str | None = None


class FunctionCandidate(_LocalIdMixin, _ConfidenceMixin):
    """A function the model proposes. NOT mapped to a formal Function term."""

    label: str
    description: str | None = None
    related_region_refs: list[str] = Field(default_factory=list)
    related_circuit_refs: list[str] = Field(default_factory=list)
    rationale: str | None = None


class CircuitCandidate(_LocalIdMixin, _ConfidenceMixin):
    """The PRIMARY discovery object: an organized multi-region pathway.

    A circuit does NOT have to be a closed loop — `LOOP` is one topology hint
    among many, and a functionally coherent pathway qualifies without one.
    """

    name: str
    description: str | None = None
    region_refs: list[str] = Field(default_factory=list)
    connection_refs: list[str] = Field(default_factory=list)
    function_refs: list[str] = Field(default_factory=list)
    topology_hint: CircuitTopologyHint = "UNKNOWN"
    rationale: str | None = None


class SourceHint(BaseModel):
    """A source the model *remembers*. UNVERIFIED — source_hint != Evidence.

    A model-produced PMID/DOI/title is a lead, never proof. It must not reach
    Gate7B `publications` / `evidence` / `evidence_links` without later
    deterministic literature verification.
    """

    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    journal: str | None = None
    pmid: str | None = None
    doi: str | None = None
    url: str | None = None
    note: str | None = None


class DiscoveryWarning(BaseModel):
    """Informative only: a warning never creates formal knowledge."""

    code: DiscoveryWarningCode
    message: str
    local_id: str | None = None


class LlmDiscoveryResponse(BaseModel):
    """Top-level model output contract.

    Raw discovery candidates — NOT canonical Gate7B entities.
    """

    schema_version: str = SCHEMA_VERSION
    seed_entity_id: str
    summary: str | None = None

    regions: list[RegionCandidate] = Field(default_factory=list)
    connections: list[ConnectionCandidate] = Field(default_factory=list)
    functions: list[FunctionCandidate] = Field(default_factory=list)
    circuits: list[CircuitCandidate] = Field(default_factory=list)

    source_hints: list[SourceHint] = Field(default_factory=list)
    warnings: list[DiscoveryWarning] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_schema_version(self) -> "LlmDiscoveryResponse":
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported schema_version '{self.schema_version}' "
                f"(this contract is {SCHEMA_VERSION})"
            )
        return self

    # -- convenience for the cross-reference pass ---------------------------
    def region_local_ids(self) -> set[str]:
        return {r.local_id for r in self.regions}

    def all_local_ids(self) -> list[str]:
        """Every declared local id, across ALL types (used for duplicate checks)."""
        return [
            *(r.local_id for r in self.regions),
            *(c.local_id for c in self.connections),
            *(f.local_id for f in self.functions),
            *(c.local_id for c in self.circuits),
        ]


class LlmDiscoveryParseResult(BaseModel):
    """Outcome of one parse attempt.

    `data` is present only when the response is structurally valid.
    `validation_warnings` are STRUCTURAL discovery-contract warnings — not
    knowledge validation, which is a different (and much later) layer.

    `error` is a machine-readable rejection reason when `data` is None.
    """

    data: LlmDiscoveryResponse | None = None
    error: str | None = None
    validation_warnings: list[DiscoveryWarning] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.data is not None
