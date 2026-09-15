"""Phase 3E.2B - read-only Literature Production access.

The read side of the model Phase 3E.1B made writable:

    BrainRegion
      -> Literature Discovery Runs      (knowledge_discovery_runs)
      -> PublicationDiscoveryHits       (publication_discovery_hits)
      -> Publications                   (publications)

Tables read (SELECT only):

    knowledge_discovery_runs       the runs
    publication_discovery_hits     retrieval provenance
    publications                   bibliographic metadata
    kg_entities                    public identity (entity_id) for both
    brain_regions                  seed identity
    sources                        provider display name for a hit

This module is STRICTLY READ-ONLY. It issues SELECT statements only. It never
creates, mutates or deletes a row, and it must never be extended into one:
writing belongs to ``publication_persistence_service`` (Phase 3E.1B) and to the
Phase 2B lifecycle service. Do not add a write statement here.

It must not import or reach any LLM provider, paper-search client or HTTP client:
this layer READS what a search already produced and never performs one. Provider
names appear here only as stored data (``sources.name_en``), never as a call.

Scientific boundary, frozen: a PublicationDiscoveryHit means "THIS QUERY FOUND
THIS PUBLICATION". It is retrieval provenance, not a claim about what the paper
proves. Nothing here joins into ``evidence``, ``evidence_links`` or
``knowledge_assertions``, and nothing here creates them.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.knowledge_production import (
    LITERATURE_DISCOVERY_TYPES,
    LiteraturePublicationItem,
    LiteraturePublicationListResponse,
    LiteratureRunDiagnostics,
    LiteratureRunItem,
    LiteratureRunListResponse,
    ProviderFailureItem,
    PublicationDetailResponse,
    PublicationHitItem,
)
from app.services.knowledge_discovery_run_service import (
    normalize_limit,
    normalize_offset,
    resolve_seed_region_pk,
)

_RUN_COLUMNS = """
    r.run_id,
    e.entity_id AS seed_entity_id,
    r.discovery_type,
    r.status,
    r.outcome,
    r.provider,
    r.created_at,
    r.started_at,
    r.finished_at,
    r.error_code,
    r.error_message,
    r.provenance_json
"""

_RUN_FROM = """
    FROM knowledge_discovery_runs r
    JOIN brain_regions b ON b.entity_pk = r.seed_region_pk
    JOIN kg_entities e ON e.entity_pk = b.entity_pk
"""

# Scope every run query to the literature routes. LLM_DISCOVERY is excluded by
# construction rather than by a caller-supplied filter: an LLM run has no
# publications, so listing one here would offer a reader an empty result that
# looks like a failed search.
_LITERATURE_SCOPE = " r.discovery_type = ANY(:literature_types)"

_HIT_COLUMNS = """
    h.publication_pk,
    h.query_text,
    h.query_family,
    h.query_level,
    h.result_rank,
    h.retrieved_at,
    s.name_en AS source_name,
    r.run_id AS hit_run_id
"""

# LEFT JOINs on purpose: source_pk and discovery_run_pk are both nullable by
# design (a hit may be recorded without them), and an INNER JOIN would silently
# drop exactly the provenance rows a reader most needs to see.
_HIT_FROM = """
    FROM publication_discovery_hits h
    LEFT JOIN sources s ON s.source_pk = h.source_pk
    LEFT JOIN knowledge_discovery_runs r ON r.run_pk = h.discovery_run_pk
"""

_PUBLICATION_COLUMNS = """
    pub.entity_pk AS publication_pk,
    pe.entity_id AS publication_entity_id,
    pub.original_title,
    pub.pmid,
    pub.pmcid,
    pub.doi,
    pub.publication_year,
    pub.source_database
"""


def _failure_item(raw: Mapping[str, Any]) -> ProviderFailureItem | None:
    """One failure entry, whitelisted field by field.

    Every field is coerced rather than trusted: this reads data another layer
    wrote into an unconstrained jsonb column, so a wrong-typed or nested value
    must degrade to ``None`` instead of raising and making the whole run
    unreadable. An entry with no usable provider is not a diagnostic at all.
    """
    provider = raw.get("provider")
    if not isinstance(provider, str):
        return None
    status = raw.get("status_code")
    retryable = raw.get("retryable")
    message = raw.get("message")
    strategy = raw.get("query_strategy")
    return ProviderFailureItem(
        provider=provider,
        # bool is a subclass of int; a boolean status code is not one.
        status_code=status if isinstance(status, int) and not isinstance(status, bool) else None,
        retryable=retryable if isinstance(retryable, bool) else None,
        message=message if isinstance(message, str) else None,
        query_strategy=strategy if isinstance(strategy, str) else None,
    )


def extract_diagnostics(provenance: Any) -> LiteratureRunDiagnostics:
    """Project ``provenance_json`` down to its bounded, reader-facing keys.

    Only the keys named in ``LITERATURE_DIAGNOSTIC_KEYS`` survive, and each
    provider failure keeps only the five fields the search layer emits.
    Everything else the execution layer may have written is internal run
    configuration and is dropped here rather than filtered at the edge, so the
    blob can never reach a response by accident.

    Tolerant by design: this reads data written by another layer, so a missing
    key, a NULL column or a non-dict jsonb must degrade to "nothing to report"
    rather than raise. A malformed provenance must not make a run unreadable.
    """
    src = provenance if isinstance(provenance, Mapping) else {}
    failures = src.get("provider_failures")
    papers_found = src.get("papers_found")
    entries = (
        [_failure_item(f) for f in failures if isinstance(f, Mapping)]
        if isinstance(failures, Sequence) and not isinstance(failures, (str, bytes))
        else []
    )
    return LiteratureRunDiagnostics(
        provider_failures=[e for e in entries if e is not None],
        partial=bool(src.get("partial", False)),
        all_providers_failed=bool(src.get("all_providers_failed", False)),
        papers_found=papers_found if isinstance(papers_found, int) else None,
    )


def row_to_literature_run(row: Mapping[str, Any]) -> LiteratureRunItem:
    """Map one run row to the DTO. Pure function (unit-testable)."""
    return LiteratureRunItem(
        run_id=str(row["run_id"]),
        seed_entity_id=row["seed_entity_id"],
        discovery_type=row["discovery_type"],
        status=row["status"],
        outcome=row["outcome"],
        provider=row["provider"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        error_code=row["error_code"],
        error_message=row["error_message"],
        diagnostics=extract_diagnostics(row["provenance_json"]),
    )


def row_to_hit(row: Mapping[str, Any]) -> PublicationHitItem:
    """Map one hit row to the DTO. Pure function (unit-testable)."""
    hit_run_id = row.get("hit_run_id")
    return PublicationHitItem(
        query_text=row["query_text"],
        query_family=row["query_family"],
        query_level=row["query_level"],
        source=row.get("source_name"),
        result_rank=row["result_rank"],
        retrieved_at=row["retrieved_at"],
        run_id=str(hit_run_id) if hit_run_id is not None else None,
    )


async def list_literature_runs_for_region(
    session: AsyncSession,
    *,
    entity_id: str,
    limit: int | None = None,
    offset: int | None = None,
) -> LiteratureRunListResponse | None:
    """Literature Discovery Runs for one BrainRegion, newest first. SELECT only.

    Returns None when the BrainRegion does not exist, so the caller can answer
    404. A region that exists but has no literature runs returns an empty page:
    "no such region" and "this region has no literature runs yet" are different
    facts and must not be conflated.
    """
    if await resolve_seed_region_pk(session, entity_id) is None:
        return None

    scope = " WHERE e.entity_id = :entity_id AND" + _LITERATURE_SCOPE
    params = {"entity_id": entity_id, "literature_types": list(LITERATURE_DISCOVERY_TYPES)}

    total = int(
        (
            await session.execute(
                text("SELECT COUNT(*)" + _RUN_FROM + scope), params
            )
        ).scalar_one()
    )
    rows = (
        await session.execute(
            text(
                "SELECT " + _RUN_COLUMNS + _RUN_FROM + scope
                + " ORDER BY r.created_at DESC, r.run_id LIMIT :limit OFFSET :offset"
            ),
            {**params, "limit": normalize_limit(limit), "offset": normalize_offset(offset)},
        )
    ).mappings().all()
    return LiteratureRunListResponse(
        items=[row_to_literature_run(r) for r in rows], total=total
    )


async def resolve_literature_run_pk(session: AsyncSession, run_id: str) -> int | None:
    """Internal PK for a public run_id, IF that run is a literature route.

    Literature-scoped on purpose. Resolving ANY run here would let an
    LLM_DISCOVERY run -- which never searches literature -- be read through the
    literature endpoint and come back as "this search found no papers". That is
    a false scientific statement, not an empty result: the run searched nothing.

    Returns None for an unknown run AND for a non-literature run, so the caller
    answers 404 in both cases: neither is a literature resource.
    """
    return (
        await session.execute(
            text(
                "SELECT r.run_pk FROM knowledge_discovery_runs r"
                " WHERE r.run_id = :run_id AND" + _LITERATURE_SCOPE
            ),
            {"run_id": run_id, "literature_types": list(LITERATURE_DISCOVERY_TYPES)},
        )
    ).scalar_one_or_none()


async def list_publications_for_run(
    session: AsyncSession, *, run_id: str
) -> LiteraturePublicationListResponse | None:
    """Publications reached by ONE run, each with ALL of its retrieval hits.

    None when the run does not exist (the caller maps that to 404). A run that
    reached nothing returns an empty list, not an error.

    ONE batched query, grouped in Python: a per-publication follow-up query
    would be N+1 on a run that may have hundreds of papers.

    ``distinct_publications`` and ``hits_total`` are reported separately. One
    publication found by three different queries is ONE publication and THREE
    retrieval facts -- collapsing the hits would destroy the provenance that
    hit idempotency exists to protect.
    """
    run_pk = await resolve_literature_run_pk(session, run_id)
    if run_pk is None:
        return None

    rows = (
        await session.execute(
            text(
                "SELECT " + _PUBLICATION_COLUMNS + "," + _HIT_COLUMNS + _HIT_FROM
                + " JOIN publications pub ON pub.entity_pk = h.publication_pk"
                + " JOIN kg_entities pe ON pe.entity_pk = h.publication_pk"
                # Same entity authority as get_publication: `publications` is
                # guarded only by a BEFORE INSERT trigger and kg_entities has no
                # trigger at all, so a publications row can outlive its entity's
                # type. Both read paths must refuse such a row, or they disagree
                # about what a publication is.
                + " WHERE h.discovery_run_pk = :run_pk"
                + "   AND pe.entity_type = 'publication'"
                + " ORDER BY h.hit_pk"
            ),
            {"run_pk": run_pk},
        )
    ).mappings().all()

    items: list[LiteraturePublicationItem] = []
    by_publication: dict[int, LiteraturePublicationItem] = {}
    for row in rows:  # rows arrive in retrieval order, so items keep it too
        pk = int(row["publication_pk"])
        item = by_publication.get(pk)
        if item is None:
            item = LiteraturePublicationItem(
                entity_id=row["publication_entity_id"],
                original_title=row["original_title"],
                pmid=row["pmid"],
                pmcid=row["pmcid"],
                doi=row["doi"],
                publication_year=row["publication_year"],
                source_database=row["source_database"],
            )
            by_publication[pk] = item
            items.append(item)
        item.hits.append(row_to_hit(row))

    return LiteraturePublicationListResponse(
        run_id=run_id,
        items=items,
        distinct_publications=len(items),
        hits_total=len(rows),
    )


async def get_publication(
    session: AsyncSession, *, entity_id: str
) -> PublicationDetailResponse | None:
    """One Publication with ALL of its retrieval provenance, across every run.

    None when no such publication exists. Retrieval provenance only: this never
    joins into Evidence or KnowledgeAssertion, and returns none of their fields.

    Two queries regardless of hit count: the publication row, then its hits.
    """
    pub = (
        await session.execute(
            text(
                "SELECT" + _PUBLICATION_COLUMNS
                + " FROM publications pub"
                + " JOIN kg_entities pe ON pe.entity_pk = pub.entity_pk"
                + " WHERE pe.entity_id = :entity_id"
                + "   AND pe.entity_type = 'publication'"
            ),
            {"entity_id": entity_id},
        )
    ).mappings().one_or_none()
    if pub is None:
        return None

    rows = (
        await session.execute(
            text(
                "SELECT " + _HIT_COLUMNS + _HIT_FROM
                + " WHERE h.publication_pk = :publication_pk ORDER BY h.hit_pk"
            ),
            {"publication_pk": pub["publication_pk"]},
        )
    ).mappings().all()

    return PublicationDetailResponse(
        entity_id=pub["publication_entity_id"],
        original_title=pub["original_title"],
        pmid=pub["pmid"],
        pmcid=pub["pmcid"],
        doi=pub["doi"],
        publication_year=pub["publication_year"],
        source_database=pub["source_database"],
        hits=[row_to_hit(r) for r in rows],
        hits_total=len(rows),
    )
