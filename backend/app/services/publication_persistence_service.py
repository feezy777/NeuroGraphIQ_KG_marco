"""Phase 3E.1B — Publication discovery RUNTIME persistence.

The write chain this module implements, and nothing beyond it:

    BrainRegion seed -> Knowledge Discovery Run -> Literature Search
      -> Publication resolve/upsert -> Publication Discovery Hit

Scope boundaries, frozen:

  * It does NOT search. The caller supplies already-retrieved papers.
  * It does NOT read full text, extract evidence passages, classify support,
    canonicalize, or promote. Nothing here writes `evidence`,
    `evidence_links` or `knowledge_assertions`.
  * A discovery hit records WHY a paper was FOUND. It is retrieval provenance,
    not a claim about what the paper proves. There is deliberately no E1/E2,
    no `supports`, no `contradicts`, no evidence_strength column.
  * Publication metadata is NOT evidence: an abstract is bibliographic
    metadata, and abstract != Evidence Passage.
  * No candidate links, and no Phase 3C local ids (`circuit_1`) may be stored.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: Values a provider may put in an identifier slot that are NOT identifiers.
#: Storing "n/a" as a PMID would make it a resolvable-looking identity and let
#: two unrelated papers collide on it.
_NULL_IDENTIFIERS = {"", "n/a", "na", "n.a.", "unknown", "none", "null", "-", "--"}

#: The four jsonb columns -- the only values needing a CAST on the way in.
_JSONB_FIELDS = ("authors_json", "affiliations_json", "mesh_terms_json", "keywords_json")

#: Publication fields eligible for later enrichment. The upsert only ever FILLS
#: a currently-empty field from these; it never overwrites a non-empty value.
_ENRICHABLE = (
    "original_title", "journal_name", "journal_abbreviation", "publication_year",
    "publication_date", "publication_type", "abstract_en", "authors_text",
    "authors_json", "affiliations_json", "mesh_terms_json", "keywords_json",
    "is_open_access", "full_text_url", "citation_count", "pmcid", "doi", "pmid",
    "source_database",
)

_RETURN_PUB = (
    "entity_pk, pmid, pmcid, doi, original_title, journal_name, publication_year,"
    " publication_type, abstract_en, authors_text, authors_json, affiliations_json,"
    " mesh_terms_json, keywords_json, is_open_access, full_text_url, citation_count,"
    " source_database"
)


# ---------------------------------------------------------------------------
# identifier normalization (§6)
# ---------------------------------------------------------------------------
def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    if text_value.lower() in _NULL_IDENTIFIERS:
        return None
    return text_value


def normalize_pmid(value: Any) -> str | None:
    return _clean(value)


def normalize_pmcid(value: Any) -> str | None:
    """PMC ids are stored upper-case with the PMC prefix (project convention)."""
    cleaned = _clean(value)
    if cleaned is None:
        return None
    return cleaned.upper()


def normalize_doi(value: Any) -> str | None:
    """DOIs are case-insensitive, so identity comparison folds case."""
    cleaned = _clean(value)
    if cleaned is None:
        return None
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
    return cleaned.lower() or None


def normalize_title(value: Any) -> str | None:
    """Fallback resolver only. Never a hard identity (see gate7b_013)."""
    cleaned = _clean(value)
    if cleaned is None:
        return None
    return " ".join(cleaned.lower().split())


# ---------------------------------------------------------------------------
# results
# ---------------------------------------------------------------------------
@dataclass
class PublicationResolution:
    """What resolve_or_create_publication did, and why."""

    publication_pk: int
    created: bool
    matched_on: str | None = None
    enriched_fields: list[str] = field(default_factory=list)
    metadata_conflicts: list[dict[str, Any]] = field(default_factory=list)
    external_ids_added: list[str] = field(default_factory=list)


@dataclass
class PersistSummary:
    publications_created: int = 0
    publications_matched: int = 0
    publications_enriched: int = 0
    hits_recorded: int = 0
    hits_deduplicated: int = 0
    metadata_conflicts: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Plain-dict view, for logging and run provenance."""
        return asdict(self)


# ---------------------------------------------------------------------------
# discovery run persistence (§3/§4)
# ---------------------------------------------------------------------------
async def create_literature_run(
    session: AsyncSession,
    *,
    seed_entity_id: str,
    discovery_type: str = "EVIDENCE_SEARCH",
    provider: str | None = None,
    provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Open a literature-search run for one BrainRegion seed.

    A literature search uses no LLM, so model_name / prompt_key / prompt_version
    stay NULL. Faking them would make the run's provenance a lie.
    """
    seed_pk = (await session.execute(
        text("SELECT b.entity_pk FROM brain_regions b"
             " JOIN kg_entities e ON e.entity_pk = b.entity_pk"
             " WHERE e.entity_id = :entity_id"),
        {"entity_id": seed_entity_id})).scalar_one_or_none()
    if seed_pk is None:
        raise ValueError(f"BrainRegion '{seed_entity_id}' not found")

    row = (
        await session.execute(
            text(
                "INSERT INTO knowledge_discovery_runs"
                " (seed_region_pk, discovery_type, status, provider,"
                "  provenance_json, started_at)"
                " VALUES (:seed_region_pk, :discovery_type, 'RUNNING', :provider,"
                "  CAST(:provenance AS jsonb), now())"
                " RETURNING run_pk, run_id, discovery_type, status, started_at"
            ),
            {
                "seed_region_pk": seed_pk,
                "discovery_type": discovery_type,
                "provider": provider,
                "provenance": _json(provenance or {}),
            },
        )
    ).mappings().one()
    await session.commit()
    return dict(row)


async def complete_literature_run(
    session: AsyncSession,
    run_id: str,
    *,
    outcome: str,
    provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Close a run. Provider failures and counts live in provenance_json --
    there is no second failure table (§16)."""
    row = (
        await session.execute(
            text(
                "UPDATE knowledge_discovery_runs"
                " SET status = 'COMPLETED', outcome = :outcome, finished_at = now(),"
                "     updated_at = now(),"
                "     provenance_json = provenance_json || CAST(:provenance AS jsonb)"
                " WHERE run_id = :run_id RETURNING run_pk, run_id, status, outcome"
            ),
            {"run_id": run_id, "outcome": outcome, "provenance": _json(provenance or {})},
        )
    ).mappings().one_or_none()
    if row is None:
        raise ValueError(f"Discovery Run '{run_id}' not found")
    await session.commit()
    return dict(row)


async def fail_literature_run(
    session: AsyncSession,
    run_id: str,
    *,
    error_code: str,
    error_message: str,
    provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    row = (
        await session.execute(
            text(
                "UPDATE knowledge_discovery_runs"
                " SET status = 'FAILED', finished_at = now(), updated_at = now(),"
                "     error_code = :error_code, error_message = :error_message,"
                "     provenance_json = provenance_json || CAST(:provenance AS jsonb)"
                " WHERE run_id = :run_id RETURNING run_pk, run_id, status, error_code"
            ),
            {
                "run_id": run_id,
                "error_code": error_code[:64],
                "error_message": error_message[:2000],
                "provenance": _json(provenance or {}),
            },
        )
    ).mappings().one_or_none()
    if row is None:
        raise ValueError(f"Discovery Run '{run_id}' not found")
    await session.commit()
    return dict(row)


# ---------------------------------------------------------------------------
# publication resolution (§5/§7/§8/§9)
# ---------------------------------------------------------------------------
async def resolve_or_create_publication(
    session: AsyncSession,
    *,
    title: str | None = None,
    pmid: Any = None,
    pmcid: Any = None,
    doi: Any = None,
    external_ids: Mapping[str, str] | None = None,
    **metadata: Any,
) -> PublicationResolution:
    """Find the publication this record refers to, or create it.

    Identity order is frozen: PMID > normalized DOI > PMCID > normalized title.
    Provider-specific ids (OpenAlex work id, S2 paper id) are NEVER identity --
    they go to entity_xrefs.

    A newly retrieved paper is `proposed` / unreviewed. It is NOT auto-approved:
    retrieval is not review.
    """
    ident = {
        "pmid": normalize_pmid(pmid),
        "pmcid": normalize_pmcid(pmcid),
        "doi": normalize_doi(doi),
    }
    existing, matched_on = await _find_existing(session, ident, title)
    if existing is not None:
        return await _enrich_existing(session, existing, ident, metadata,
                                      external_ids, matched_on)

    entity_pk = await _create_publication_entity(session, title, metadata)
    clean = {k: v for k, v in metadata.items() if v not in (None, "")}
    # Derived from _ENRICHABLE rather than hand-written, so the column list and
    # the parameter mapping cannot drift apart.
    scalar = [f for f in _ENRICHABLE
              if f not in _JSONB_FIELDS + ("pmid", "pmcid", "doi", "original_title")]
    cols = ("entity_pk", "original_title", "pmid", "pmcid", "doi", *scalar, *_JSONB_FIELDS)
    await session.execute(
        text("INSERT INTO publications ({}) VALUES ({})".format(
            ", ".join(cols),
            ", ".join(f"CAST(:{c} AS jsonb)" if c in _JSONB_FIELDS else f":{c}"
                      for c in cols))),
        {
            "entity_pk": entity_pk,
            "original_title": _clean(title),
            **ident,
            **{k: clean.get(k) for k in scalar},
            **{k: _jsonb(clean.get(k)) for k in _JSONB_FIELDS},
        },
    )
    added = await _upsert_external_ids(session, entity_pk, external_ids)
    await session.commit()
    return PublicationResolution(
        publication_pk=entity_pk, created=True, matched_on=None,
        external_ids_added=added,
    )


#: The frozen identity order (§5), as data. Provider-specific ids (OpenAlex
#: work id, S2 paper id) are deliberately absent: they are never identity.
_IDENTITY_STEPS = (
    ("pmid", "pmid = :v"),
    ("doi", "lower(btrim(doi)) = :v"),
    ("pmcid", "pmcid = :v"),
)


async def _find_existing(
    session: AsyncSession, ident: Mapping[str, str | None], title: str | None
) -> tuple[Mapping[str, Any] | None, str | None]:
    """Frozen resolution order. Each step is an exact identity match."""
    for field_name, predicate in _IDENTITY_STEPS:
        if not ident[field_name]:
            continue
        row = (await session.execute(
            text(f"SELECT {_RETURN_PUB} FROM publications WHERE {predicate} LIMIT 1"),
            {"v": ident[field_name]})).mappings().one_or_none()
        if row:
            return row, field_name
    normalized = normalize_title(title)
    if normalized:
        row = (await session.execute(
            text(f"SELECT {_RETURN_PUB} FROM publications"
                 " WHERE lower(btrim(original_title)) = :v LIMIT 1"),
            {"v": normalized})).mappings().one_or_none()
        if row:
            return row, "title"
    return None, None


async def _enrich_existing(
    session: AsyncSession,
    existing: Mapping[str, Any],
    ident: Mapping[str, str | None],
    metadata: Mapping[str, Any],
    external_ids: Mapping[str, str] | None,
    matched_on: str | None,
) -> PublicationResolution:
    """Fill only EMPTY fields. Never overwrite, never blank out.

    A value that disagrees is recorded as a conflict instead of being applied:
    choosing between two providers' years is a scientific judgement, and this
    layer is not entitled to make it.
    """
    updates: dict[str, Any] = {}
    conflicts: list[dict[str, Any]] = []

    for field_name in _ENRICHABLE:
        incoming = ident.get(field_name) if field_name in ident else metadata.get(field_name)
        if incoming in (None, ""):
            continue
        current = existing.get(field_name)
        if current in (None, ""):
            updates[field_name] = incoming
        elif str(current).strip() != str(incoming).strip():
            conflicts.append({
                "field": field_name,
                "kept": str(current)[:300],
                "ignored_from_newer_record": str(incoming)[:300],
                "resolution": "existing canonical value kept",
            })

    added = await _upsert_external_ids(session, int(existing["entity_pk"]), external_ids)
    if updates or added or conflicts:
        if updates:
            assignments = ", ".join(f"{k} = :{k}" for k in updates)
            await session.execute(
                text(
                    f"UPDATE publications SET {assignments} WHERE entity_pk = :entity_pk"
                ),
                {**updates, "entity_pk": existing["entity_pk"]},
            )
        await session.commit()
    return PublicationResolution(
        publication_pk=int(existing["entity_pk"]),
        created=False,
        matched_on=matched_on,
        enriched_fields=sorted(updates),
        metadata_conflicts=conflicts,
        external_ids_added=added,
    )


async def _create_publication_entity(
    session: AsyncSession, title: str | None, metadata: Mapping[str, Any]
) -> int:
    """Create the kg_entities identity a publication requires.

    `proposed` + an explicit source: retrieval is not review, so a retrieved
    paper must never enter as `active`/`approved`. This also satisfies
    ck_kg_entities_proposed_source and ck_kg_entities_proposed_has_name.
    """
    entity_id = (await session.execute(
        text("SELECT infra.next_ngiq_id('publication')"))).scalar_one()
    name_en = _clean(title) or "Untitled publication"
    return int((await session.execute(
        text("INSERT INTO kg_entities"
             " (entity_id, entity_type, name_en, source_name_original, record_status)"
             " VALUES (:entity_id, 'publication', :name_en, :source, 'proposed')"
             " RETURNING entity_pk"),
        {"entity_id": entity_id, "name_en": name_en[:2000],
         "source": _clean(metadata.get("source_database")) or "literature_search"},
    )).scalar_one())


async def _upsert_external_ids(
    session: AsyncSession, entity_pk: int, external_ids: Mapping[str, str] | None
) -> list[str]:
    """OpenAlex / Semantic Scholar go here, never onto publications columns."""
    added: list[str] = []
    for source_db, external_id in (external_ids or {}).items():
        cleaned = _clean(external_id)
        if cleaned is None:
            continue
        # The lookup is deliberately NOT scoped to entity_pk: the database
        # constraint that will actually reject a duplicate is
        # uq_entity_xrefs_resolved_external, which is UNIQUE on
        # (source_database, external_id) across the WHOLE table -- a provider id
        # names one work, globally. Checking per entity would miss the row and
        # then fail on INSERT instead of reporting "already recorded".
        existing = (
            await session.execute(
                text(
                    "SELECT entity_pk FROM entity_xrefs"
                    " WHERE lower(btrim(source_database)) = :db AND btrim(external_id) = :ext"
                ),
                {"db": source_db.strip().lower(), "ext": cleaned},
            )
        ).scalar_one_or_none()
        if existing is not None:
            if int(existing) != entity_pk:
                logger.warning(
                    "[publication-persistence] %s:%s already belongs to entity_pk=%s;"
                    " not re-pointing it at entity_pk=%s",
                    source_db, cleaned, existing, entity_pk)
            continue                      # idempotent: already recorded
        await session.execute(
            text(
                "INSERT INTO entity_xrefs (xref_id, entity_pk, source_database,"
                " external_id, external_uri, match_type, is_primary)"
                " VALUES ('NGIQ-XRF-' || lpad(nextval('infra.ngiq_xrf_seq')::text, 8, '0'),"
                " :entity_pk, :db, :ext, :uri, 'exact', false)"
            ),
            {
                "entity_pk": entity_pk,
                "db": source_db.strip(),
                "ext": cleaned,
                "uri": cleaned if cleaned.startswith("http") else None,
            },
        )
        added.append(f"{source_db}:{cleaned}")
    return added


# ---------------------------------------------------------------------------
# discovery hit (§11/§12/§13/§14)
# ---------------------------------------------------------------------------
async def record_publication_discovery_hit(
    session: AsyncSession,
    *,
    publication_pk: int,
    query_text: str,
    discovery_run_pk: int | None = None,
    source_pk: int | None = None,
    seed_brain_region_pk: int | None = None,
    query_family: str | None = None,
    query_level: str | None = None,
    result_rank: int | None = None,
    metadata: Mapping[str, Any] | None = None,
    remark: str | None = None,
) -> tuple[int | None, bool]:
    """Record that this publication was FOUND this way. Returns (hit_pk, created).

    Idempotent on (run, publication, source, query_text, result_rank): a retry
    of the same search must not inflate retrieval provenance.
    """
    row = (
        await session.execute(
            text(
                "INSERT INTO publication_discovery_hits"
                " (publication_pk, discovery_run_pk, source_pk, seed_brain_region_pk,"
                "  query_family, query_level, query_text, result_rank, metadata_json, remark)"
                " VALUES (:publication_pk, :discovery_run_pk, :source_pk,"
                "  :seed_brain_region_pk, :query_family, :query_level, :query_text,"
                "  :result_rank, CAST(:metadata AS jsonb), :remark)"
                " ON CONFLICT (discovery_run_pk, publication_pk, source_pk, query_text,"
                "  result_rank) DO NOTHING"
                " RETURNING hit_pk"
            ),
            {
                "publication_pk": publication_pk,
                "discovery_run_pk": discovery_run_pk,
                "source_pk": source_pk,
                "seed_brain_region_pk": seed_brain_region_pk,
                "query_family": query_family,
                "query_level": query_level,
                "query_text": query_text,
                "result_rank": result_rank,
                "metadata": _json(metadata or {}),
                "remark": remark,
            },
        )
    ).scalar_one_or_none()
    return (int(row), True) if row is not None else (None, False)


# ---------------------------------------------------------------------------
# orchestration (§18)
# ---------------------------------------------------------------------------
async def persist_search_results(
    session: AsyncSession,
    *,
    papers: Sequence[Mapping[str, Any]],
    discovery_run_pk: int | None,
    query_text: str,
    source_pk: int | None = None,
    seed_brain_region_pk: int | None = None,
    query_family: str | None = None,
    query_level: str | None = None,
) -> PersistSummary:
    """Persist one query's results, ONE TRANSACTION PER PUBLICATION.

    Per-publication (not one giant transaction for the whole run) so a failure
    cannot leave "publication written, hit lost" as an unexplained partial
    state, and so a 1000-paper run does not hold a single enormous transaction.
    """
    summary = PersistSummary()
    for rank, paper in enumerate(papers, start=1):
        try:
            resolved = await resolve_or_create_publication(
                session,
                title=paper.get("title"),
                pmid=paper.get("pmid"),
                pmcid=paper.get("pmcid"),
                doi=paper.get("doi"),
                external_ids=_external_ids_of(paper),
                journal_name=paper.get("journal"),
                publication_year=paper.get("year"),
                abstract_en=paper.get("abstract"),
                authors_json=paper.get("authors"),
                is_open_access=paper.get("is_oa"),
                full_text_url=paper.get("full_text_url"),
                citation_count=paper.get("citation_count"),
                source_database=paper.get("source"),
            )
            if resolved.created:
                summary.publications_created += 1
            else:
                summary.publications_matched += 1
                if resolved.enriched_fields:
                    summary.publications_enriched += 1
            summary.metadata_conflicts += len(resolved.metadata_conflicts)

            _hit_pk, created = await record_publication_discovery_hit(
                session,
                publication_pk=resolved.publication_pk,
                discovery_run_pk=discovery_run_pk,
                source_pk=source_pk,
                seed_brain_region_pk=seed_brain_region_pk,
                query_family=query_family,
                query_level=query_level,
                query_text=query_text,
                result_rank=rank,
                metadata={"provider": paper.get("source"),
                          "title": (paper.get("title") or "")[:300],
                          "matched_on": resolved.matched_on,
                          **({"metadata_conflicts": resolved.metadata_conflicts}
                             if resolved.metadata_conflicts else {})},
            )
            await session.commit()
            if created:
                summary.hits_recorded += 1
            else:
                summary.hits_deduplicated += 1
        except Exception as exc:  # noqa: BLE001 - one bad paper must not lose the rest
            await session.rollback()
            summary.errors.append(f"rank {rank}: {type(exc).__name__}")
            logger.warning("[publication-persistence] paper %s failed: %s",
                           rank, type(exc).__name__)
    return summary


def _external_ids_of(paper: Mapping[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, db in (("openalex_id", "OpenAlex"), ("semanticscholar_id", "SemanticScholar"),
                    ("corpus_id", "SemanticScholar")):
        value = _clean(paper.get(key))
        if value:
            out[db] = value
    return out


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _jsonb(value: Any) -> str | None:
    """Serialize a jsonb column value, or None for an absent one.

    An empty list/dict is a real value (a paper with no MeSH terms is not the
    same as one whose MeSH terms were never retrieved), so only None maps to
    SQL NULL.
    """
    return None if value is None else _json(value)
