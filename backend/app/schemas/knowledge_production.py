"""Phase 1 Knowledge Production API DTOs (read-only).

These DTOs describe only fields that actually exist in the Gate7B formal
knowledge tables of ``neurographiq_human_brain_v1``:

    kg_entities  (identity / names / lifecycle)
    brain_regions (subtype row: granularity / hemisphere / category)
    region_mappings + external_regions + atlases (atlas provenance)

No candidate_* / mirror_* / final_* entity is represented here.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

# The frozen Gate7B granularity vocabulary. This is the ONLY granularity
# vocabulary used by the Knowledge Production module.
GranularityLevel = Literal[
    "G1_MACRO",
    "G2_MESO_ANATOMICAL",
    "G3_MESO_FINE",
    "G4_MICROSTRUCTURAL_FINE",
]

GATE7B_GRANULARITY_LEVELS: tuple[str, ...] = (
    "G1_MACRO",
    "G2_MESO_ANATOMICAL",
    "G3_MESO_FINE",
    "G4_MICROSTRUCTURAL_FINE",
)


class BrainRegionSeedItem(BaseModel):
    """One canonical BrainRegion usable as a discovery seed. Read-only."""

    entity_pk: int
    entity_id: str
    name_en: str | None = None
    name_zh: str | None = None
    abbreviation: str | None = None
    granularity_level: str | None = None
    region_category: str | None = None
    hemisphere: str | None = None
    species_taxon_id: str | None = None
    record_status: str | None = None
    review_status: str | None = None
    atlas_names: list[str] = Field(default_factory=list)


class BrainRegionSeedListResponse(BaseModel):
    items: list[BrainRegionSeedItem]
    total: int


class BrainRegionSummary(BaseModel):
    """Read-only BrainRegion counts for the Production Index summary row.

    One aggregate query instead of one list request per granularity.
    Contains ONLY fields that exist in the Gate7B authority tables.
    """

    total: int
    by_granularity: dict[str, int]


class BrainRegionSeedDetail(BrainRegionSeedItem):
    """Detail view. Adds only fields that exist on brain_regions / kg_entities."""

    definition_en: str | None = None
    parent_region_pk: int | None = None
    hierarchy_depth: int | None = None
    external_region_ids: list[str] = Field(default_factory=list)
    mapping_types: list[str] = Field(default_factory=list)
    mapping_review_statuses: list[str] = Field(default_factory=list)


# ===========================================================================
# Phase 2A — Discovery Run (workflow / provenance, NOT knowledge)
# ===========================================================================
# Frozen vocabulary, mirrored by the CHECK constraints on
# knowledge_discovery_runs (migration gate7b_011). These are EXECUTION
# lifecycle + scientific-outcome vocabularies, deliberately separate from any
# future CandidateStatus / ValidationStatus / PromotionStatus.

DiscoveryType = Literal[
    "LLM_DISCOVERY",
    "LITERATURE_DISCOVERY",
    # gate7b_013 widened the database CHECK to these two; this vocabulary must
    # match it or a stored run type becomes unrepresentable in the API.
    "EVIDENCE_SEARCH",
    "CITATION_CHAINING",
]

DiscoveryRunStatus = Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"]

DiscoveryRunOutcome = Literal[
    "CANDIDATES_FOUND",
    "NO_CANDIDATES_FOUND",
    "NO_EVIDENCE_FOUND",
]

#: DERIVED from ``DiscoveryType``, never hand-written. ``DiscoveryType`` is the
#: single canonical authority for this vocabulary, mirrored by the database
#: CHECK ``ck_kdr_discovery_type``. A second hand-written list is what went
#: stale here before: gate7b_013 widened the CHECK to four values and this
#: constant kept only two, silently, because nothing compared them.
DISCOVERY_TYPES: tuple[str, ...] = get_args(DiscoveryType)
DISCOVERY_RUN_STATUSES: tuple[str, ...] = (
    "QUEUED",
    "RUNNING",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
)
DISCOVERY_RUN_OUTCOMES: tuple[str, ...] = (
    "CANDIDATES_FOUND",
    "NO_CANDIDATES_FOUND",
    "NO_EVIDENCE_FOUND",
)


class DiscoveryRunItem(BaseModel):
    """One Discovery Run, read-only.

    Exposes the run's identity, seed, lifecycle and route provenance.

    Deliberately NOT exposed here:
      * ``parameters_json`` / ``provenance_json`` — internal run config, not a
        list-row concern (and never raw candidate entities).
      * ``seed_region_pk`` — the public API is entity_id based; the internal
        shared PK never leaves the backend.
      * any credential — the table has no secret column and none may be added.
    """

    run_id: str
    seed_entity_id: str

    discovery_type: DiscoveryType
    status: DiscoveryRunStatus
    outcome: DiscoveryRunOutcome | None = None

    provider: str | None = None
    model_name: str | None = None
    prompt_key: str | None = None
    prompt_version: str | None = None
    query_strategy_version: str | None = None

    created_by: str | None = None

    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    error_code: str | None = None
    error_message: str | None = None


class DiscoveryRunListResponse(BaseModel):
    items: list[DiscoveryRunItem]
    total: int


# ===========================================================================
# Phase 2B — Discovery Run lifecycle request DTOs
# ===========================================================================
# A run is ACTIVE while it is QUEUED or RUNNING. At most one active run may
# exist per (seed_region_pk, discovery_type) — enforced by the partial unique
# index uq_kdr_active_per_seed_type (migration gate7b_012).
ACTIVE_DISCOVERY_RUN_STATUSES: tuple[str, ...] = ("QUEUED", "RUNNING")

TERMINAL_DISCOVERY_RUN_STATUSES: tuple[str, ...] = ("COMPLETED", "FAILED", "CANCELLED")

# Which outcome may a finished run report, per route?
#
# LLM_DISCOVERY is NOT an evidence-search route: it proposes candidate
# knowledge, so it may report that it found candidates or found none, but it
# has no standing to assert NO_EVIDENCE_FOUND — that is a literature-search
# conclusion. Enforced in the lifecycle service (it depends on discovery_type,
# so it is not expressible as a column CHECK).
COMPLETION_OUTCOMES_BY_TYPE: dict[str, tuple[str, ...]] = {
    "LLM_DISCOVERY": ("CANDIDATES_FOUND", "NO_CANDIDATES_FOUND"),
    "LITERATURE_DISCOVERY": (
        "CANDIDATES_FOUND",
        "NO_CANDIDATES_FOUND",
        "NO_EVIDENCE_FOUND",
    ),
    # gate7b_013 added these two run types to the database CHECK; the mapping
    # must cover them too, or completing such a run raises KeyError instead of
    # returning a verdict. Both are literature/evidence SEARCH routes, so a
    # completed search may legitimately report that it found no evidence --
    # unlike LLM_DISCOVERY, which proposes candidates and has no standing to.
    "EVIDENCE_SEARCH": (
        "CANDIDATES_FOUND",
        "NO_CANDIDATES_FOUND",
        "NO_EVIDENCE_FOUND",
    ),
    "CITATION_CHAINING": (
        "CANDIDATES_FOUND",
        "NO_CANDIDATES_FOUND",
        "NO_EVIDENCE_FOUND",
    ),
}


class DiscoveryRunCreateRequest(BaseModel):
    """POST body for creating a run. ONLY the route may be supplied.

    ``extra="forbid"`` is deliberate: the client must not be able to fabricate
    execution provenance (provider / model_name / prompt_key / prompt_version /
    query_strategy_version), run config (parameters_json / provenance_json),
    audit identity (created_by) or knowledge payloads (candidates / evidence).
    Those are written by the execution layers that actually produce them.
    """

    model_config = ConfigDict(extra="forbid")

    discovery_type: DiscoveryType


class DiscoveryRunCompleteRequest(BaseModel):
    """POST body for completing a run. A scientific outcome is required.

    A completed run must state its result, so ``outcome`` has no default.
    """

    model_config = ConfigDict(extra="forbid")

    outcome: DiscoveryRunOutcome


class DiscoveryRunFailRequest(BaseModel):
    """POST body for failing a run. The explanation is mandatory.

    Lengths mirror the columns: ``error_message`` is TEXT (uncapped),
    ``error_code`` is VARCHAR(64) — validated here rather than silently
    truncated by the database.
    """

    model_config = ConfigDict(extra="forbid")

    error_code: str | None = Field(default=None, max_length=64)
    error_message: str = Field(min_length=1)


# ===========================================================================
# Phase 3E.2B — Literature production READ views
# ===========================================================================
# The read side of the literature production model:
#
#     BrainRegion -> Literature Discovery Runs
#                 -> PublicationDiscoveryHits -> Publications
#
# Two semantics are frozen here and must not drift:
#
#   * A PublicationDiscoveryHit means "THIS QUERY FOUND THIS PUBLICATION".
#     It is retrieval provenance. It is NOT "this publication supports a claim".
#     There is deliberately no supports / contradicts / evidence_strength field:
#     those belong to the Evidence layer, which this module never touches.
#   * Diagnostics are a BOUNDED projection of ``provenance_json``. The whole
#     blob is internal run config and is never returned.

#: Discovery routes that do NOT search literature. LLM_DISCOVERY proposes
#: candidate knowledge instead, so it has no publications to read and must not
#: appear under a literature endpoint.
_NON_LITERATURE_DISCOVERY_TYPES: frozenset[str] = frozenset({"LLM_DISCOVERY"})

#: The literature/evidence SEARCH routes, DERIVED as the complement of the
#: exclusions above. Written as a derivation rather than a second literal tuple
#: so it cannot drift away from the canonical vocabulary: widening
#: ``DiscoveryType`` widens this automatically, and the only thing a maintainer
#: must decide is whether the NEW route searches literature.
LITERATURE_DISCOVERY_TYPES: tuple[str, ...] = tuple(
    t for t in DISCOVERY_TYPES if t not in _NON_LITERATURE_DISCOVERY_TYPES
)

#: The ONLY provenance_json keys the read API may surface.
LITERATURE_DIAGNOSTIC_KEYS: tuple[str, ...] = (
    "provider_failures",
    "partial",
    "all_providers_failed",
    "papers_found",
)


class ProviderFailureItem(BaseModel):
    """ONE provider's failure, bounded to the fields the search layer emits.

    Audited: ``paper_search_multi.multi_search`` is the ONLY writer of
    ``provider_failures`` in the codebase, and both of its construction sites
    (``LiteratureSearchError.as_diagnostic`` and the generic-exception fallback)
    emit exactly these five keys, all scalars. The schema is therefore stable
    enough to type.

    Typing it TIGHTENS what a reader can see. ``provenance_json`` is an
    unconstrained jsonb column and every field here is optional, so a failure
    entry carrying anything else -- a nested provider payload, an internal
    field added later -- is dropped by the read layer rather than forwarded.
    """

    provider: str | None = None
    status_code: int | None = None
    retryable: bool | None = None
    message: str | None = None
    query_strategy: str | None = None


class LiteratureRunDiagnostics(BaseModel):
    """Bounded view of a literature run's ``provenance_json``.

    Carrying the whole blob would leak internal run configuration and re-couple
    the read API to whatever the execution layer happens to write. These four
    keys are the ones a reader can act on: which providers failed, whether the
    result was partial, whether every provider failed, and how many papers came
    back. ``all_providers_failed`` is what distinguishes a provider OUTAGE from
    a genuine zero-result search -- a distinction Phase 3E.1 froze.
    """

    provider_failures: list[ProviderFailureItem] = Field(default_factory=list)
    partial: bool = False
    all_providers_failed: bool = False
    papers_found: int | None = None


class LiteratureRunItem(BaseModel):
    """One literature discovery run for a BrainRegion seed. Read-only.

    Deliberately narrower than ``DiscoveryRunItem``: no model / prompt /
    query-strategy provenance, because a literature search uses no LLM and those
    columns are NULL for these routes. ``diagnostics`` replaces the raw
    ``provenance_json`` that ``DiscoveryRunItem`` withholds.
    """

    run_id: str
    seed_entity_id: str

    discovery_type: DiscoveryType
    status: DiscoveryRunStatus
    outcome: DiscoveryRunOutcome | None = None

    provider: str | None = None

    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    error_code: str | None = None
    error_message: str | None = None

    diagnostics: LiteratureRunDiagnostics = Field(default_factory=LiteratureRunDiagnostics)


class LiteratureRunListResponse(BaseModel):
    items: list[LiteratureRunItem]
    total: int


class PublicationHitItem(BaseModel):
    """One retrieval fact: this query found this publication, this way.

    ``run_id`` is carried because the publication detail view spans runs; the
    same publication may have been reached by several runs, and without it the
    hits could not be told apart. It is ``None`` for a hit recorded without a
    run (the column is nullable by design).
    """

    query_text: str
    query_family: str | None = None
    query_level: str | None = None
    source: str | None = None
    result_rank: int | None = None
    retrieved_at: datetime
    run_id: str | None = None


class LiteraturePublicationItem(BaseModel):
    """One Publication reached by literature search, with its retrieval hits.

    Identity is the publication's Gate7B ``entity_id``. Bibliographic fields are
    the canonical stored values; no provider-specific identifier appears here
    (OpenAlex / Semantic Scholar ids live in entity_xrefs).
    """

    entity_id: str
    original_title: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    doi: str | None = None
    publication_year: int | None = None
    source_database: str | None = None
    hits: list[PublicationHitItem] = Field(default_factory=list)


class LiteraturePublicationListResponse(BaseModel):
    """Publications reached by ONE discovery run.

    ``distinct_publications`` and ``hits_total`` are reported separately and on
    purpose: one publication found by three different queries is ONE publication
    and THREE retrieval facts. Collapsing them would hide exactly the provenance
    that hit idempotency (gate7b_014) exists to protect.
    """

    run_id: str
    items: list[LiteraturePublicationItem]
    distinct_publications: int
    hits_total: int


class PublicationDetailResponse(LiteraturePublicationItem):
    """One Publication with ALL of its retrieval provenance, across every run."""

    hits_total: int
