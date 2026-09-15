"""Phase 3E.1B — publication discovery RUNTIME persistence.

These exercise the REAL service against the REAL isolated test database,
because what is under test is the interaction between service logic and database
constraints. A fake would prove only the fake.

Isolation
---------
Each test runs inside an outer transaction that is always ROLLED BACK. The
session joins that transaction with ``join_transaction_mode="create_savepoint"``,
so the service's own ``session.commit()`` releases a SAVEPOINT rather than
committing for real. The whole test body runs in ONE event loop, so the async
connection never crosses a loop boundary.

If the isolated database or the migration is missing, the tests SKIP loudly --
they never silently pass.
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

import pytest

BACKEND = Path(__file__).resolve().parents[1]
E2E_DB = os.environ.get("TEST_E2E_DB", "neurographiq_human_brain_v1_e2e")

FALLBACK_SEED = "NGIQ-BR-00001169"          # Left Hippocampus


def _dsn(async_: bool = True) -> str:
    cfg: dict[str, str] = {}
    env = BACKEND / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    driver = "postgresql+psycopg://" if async_ else "postgresql://"
    return "%s%s:%s@%s:%s/%s" % (
        driver, cfg.get("POSTGRES_USER"), cfg.get("POSTGRES_PASSWORD"),
        cfg.get("POSTGRES_HOST", "127.0.0.1"), cfg.get("POSTGRES_PORT", "5432"), E2E_DB)


def _resolve_seed() -> str:
    """Left Hippocampus, looked up rather than hard-coded.

    The isolated test database is loaded from a different dump than the
    authority database, so the same region carries a different numeric
    suffix there. Hard-coding production's id makes every run-dependent test
    fail for a reason that has nothing to do with what it is testing.
    """
    try:
        import psycopg

        with psycopg.connect(_dsn(async_=False)) as conn:
            row = conn.execute(
                "SELECT entity_id FROM kg_entities"
                " WHERE entity_type = 'brain_region' AND name_en = 'Left Hippocampus'"
                " ORDER BY entity_id LIMIT 1").fetchone()
        return row[0] if row else FALLBACK_SEED
    except Exception:  # pragma: no cover - the tests skip later anyway
        return FALLBACK_SEED


SEED = _resolve_seed()


@dataclass
class Session:
    """The async session, plus the small read helpers the tests need."""

    db: Any

    async def scalar(self, sql: str, **params: Any) -> Any:
        from sqlalchemy import text

        return (await self.db.execute(text(sql), params)).scalar_one_or_none()

    async def row(self, sql: str, **params: Any) -> Any:
        from sqlalchemy import text

        return (await self.db.execute(text(sql), params)).mappings().one()

    async def count(self, sql: str, **params: Any) -> int:
        return int(await self.scalar(sql, **params))


def case(fn: Callable[[Session], Awaitable[None]]):
    """Run an async test in one event loop, inside a rolled-back transaction.

    The name is copied over by hand rather than with ``functools.wraps``:
    ``wraps`` sets ``__wrapped__``, which makes pytest follow it back to the
    async signature and demand the harness as a fixture.
    """

    def wrapper() -> None:
        asyncio.run(_drive(fn))

    wrapper.__name__ = fn.__name__
    wrapper.__qualname__ = fn.__qualname__
    wrapper.__doc__ = fn.__doc__
    return wrapper


async def _drive(fn: Callable[[Session], Awaitable[None]]) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    from sqlalchemy import text

    engine = create_async_engine(_dsn(), poolclass=NullPool)
    try:
        connection = await engine.connect()
    except Exception as exc:  # pragma: no cover - environment dependent
        await engine.dispose()
        pytest.skip(f"isolated test database unavailable: {type(exc).__name__}")

    # The transaction is opened BEFORE any statement: engine.connect() would
    # autobegin on the first execute, and a later connection.begin() then fails.
    transaction = await connection.begin()
    db = AsyncSession(bind=connection, join_transaction_mode="create_savepoint")
    try:
        if (
            await connection.execute(
                text("SELECT to_regclass('public.publication_discovery_hits')")
            )
        ).scalar_one() is None:
            pytest.skip("gate7b_013 not applied to the isolated test database")
        if not (
            await connection.execute(
                text("SELECT 1 FROM sources WHERE name_en = 'Europe PMC'")
            )
        ).scalar_one_or_none():
            pytest.skip("gate7b_014 not applied to the isolated test database")

        await fn(Session(db), _service())
    finally:
        await db.close()
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


def _service():
    """The module under test. Imported once; the tests take it as an argument so
    they can also be read as `svc.` calls at the top level."""
    from app.services import publication_persistence_service

    return publication_persistence_service


@pytest.fixture(scope="module", name="svc")
def svc_fixture():
    return _service()


async def _source_pk(h: Session, name: str) -> int | None:
    return await h.scalar("SELECT source_pk FROM sources WHERE name_en = :n LIMIT 1", n=name)


def _paper(**over: Any) -> dict[str, Any]:
    base = {
        "title": "A hippocampal circuit paper",
        "pmid": "40000001",
        "journal": "J Test",
        "year": 2020,
        "abstract": "abstract text",
        "source": "europepmc",
    }
    base.update(over)
    # Derived from the PMID unless one is given explicitly, so two papers that
    # differ only by PMID do not silently share a DOI and resolve to one row --
    # which is correct service behaviour but a trap for the test author.
    base.setdefault("doi", f"10.1000/paper-{base['pmid']}")
    return base


# ===========================================================================
# §22.1-3 — discovery runs
# ===========================================================================
@case
async def test_1_create_a_literature_discovery_run(h, svc):
    created = await svc.create_literature_run(
        h.db, seed_entity_id=SEED, discovery_type="EVIDENCE_SEARCH", provider="europepmc")
    assert created["status"] == "RUNNING" and created["run_id"]
    assert created["started_at"] is not None


@case
async def test_1b_a_literature_run_carries_no_fake_model_provenance(h, svc):
    """No LLM is involved, so model/prompt provenance must stay NULL."""
    created = await svc.create_literature_run(h.db, seed_entity_id=SEED)
    row = await h.row(
        "SELECT model_name, prompt_key, prompt_version FROM knowledge_discovery_runs"
        " WHERE run_pk = :p", p=created["run_pk"])
    assert row["model_name"] is None
    assert row["prompt_key"] is None and row["prompt_version"] is None


@case
async def test_1c_an_unknown_seed_is_rejected(h, svc):
    with pytest.raises(ValueError):
        await svc.create_literature_run(h.db, seed_entity_id="NGIQ-BR-99999999")


@case
async def test_1d_two_active_runs_for_one_seed_and_type_are_rejected(h, svc):
    """gate7b_012: at most one active run per (seed, discovery_type)."""
    await svc.create_literature_run(h.db, seed_entity_id=SEED,
                                    discovery_type="EVIDENCE_SEARCH")
    with pytest.raises(Exception):
        await svc.create_literature_run(h.db, seed_entity_id=SEED,
                                        discovery_type="EVIDENCE_SEARCH")


@case
async def test_2_complete_a_run(h, svc):
    created = await svc.create_literature_run(h.db, seed_entity_id=SEED)
    done = await svc.complete_literature_run(
        h.db, created["run_id"], outcome="NO_EVIDENCE_FOUND",
        provenance={"provider_failures": [], "papers_found": 0})
    assert done["status"] == "COMPLETED" and done["outcome"] == "NO_EVIDENCE_FOUND"
    assert await h.scalar(
        "SELECT finished_at FROM knowledge_discovery_runs WHERE run_pk = :p",
        p=created["run_pk"]) is not None


def test_2b_the_outcome_vocabulary_covers_every_run_type_the_database_allows():
    """gate7b_013 widened the DB CHECK; the app mapping must cover it too, or
    completing such a run raises KeyError instead of returning a verdict."""
    from app.schemas.knowledge_production import COMPLETION_OUTCOMES_BY_TYPE

    for run_type in ("LLM_DISCOVERY", "LITERATURE_DISCOVERY",
                     "EVIDENCE_SEARCH", "CITATION_CHAINING"):
        assert run_type in COMPLETION_OUTCOMES_BY_TYPE, run_type


@case
async def test_3_fail_a_run_keeps_provider_diagnostics(h, svc):
    created = await svc.create_literature_run(h.db, seed_entity_id=SEED)
    failed = await svc.fail_literature_run(
        h.db, created["run_id"], error_code="SEARCH_PROVIDER_ERROR",
        error_message="provider rate limited",
        provenance={"provider_failures": [{"provider": "europepmc", "status_code": 429}],
                    "all_providers_failed": True})
    assert failed["status"] == "FAILED"
    stored = await h.scalar(
        "SELECT provenance_json FROM knowledge_discovery_runs WHERE run_pk = :p",
        p=created["run_pk"])
    assert stored["all_providers_failed"] is True
    assert stored["provider_failures"][0]["status_code"] == 429


@case
async def test_3b_failing_an_unknown_run_is_rejected(h, svc):
    import uuid

    with pytest.raises(ValueError):
        await svc.fail_literature_run(h.db, str(uuid.uuid4()), error_code="X",
                                      error_message="y")


# ===========================================================================
# §22.4-7 — identity resolution
# ===========================================================================
@case
async def test_4_same_pmid_resolves_to_one_publication(h, svc):
    a = await svc.resolve_or_create_publication(h.db, title="X", pmid="41000001")
    b = await svc.resolve_or_create_publication(h.db, title="Different title",
                                                pmid="41000001")
    assert a.publication_pk == b.publication_pk
    assert a.created and not b.created and b.matched_on == "pmid"


@case
async def test_5_same_doi_different_case_and_spacing_resolves_to_one(h, svc):
    a = await svc.resolve_or_create_publication(h.db, title="Y", doi="10.1000/ABC")
    b = await svc.resolve_or_create_publication(h.db, title="Y2", doi="  10.1000/abc  ")
    assert a.publication_pk == b.publication_pk


@case
async def test_5b_a_doi_url_prefix_is_stripped(h, svc):
    a = await svc.resolve_or_create_publication(h.db, title="Z", doi="10.2000/xyz")
    b = await svc.resolve_or_create_publication(
        h.db, title="Z2", doi="https://doi.org/10.2000/XYZ")
    assert a.publication_pk == b.publication_pk


@case
async def test_6_same_pmcid_resolves_to_one_publication(h, svc):
    a = await svc.resolve_or_create_publication(h.db, title="P", pmcid="PMC9990001")
    b = await svc.resolve_or_create_publication(h.db, title="P2", pmcid="pmc9990001")
    assert a.publication_pk == b.publication_pk


@case
async def test_7_pmid_identity_wins_over_the_title_fallback(h, svc):
    """Ordering is only observable when the two keys point at DIFFERENT rows:
    a record whose PMID matches Alpha and whose title matches Beta must land on
    Alpha. Reverse the frozen order and this test fails."""
    alpha = await svc.resolve_or_create_publication(h.db, title="Alpha",
                                                    pmid="42000001")
    beta = await svc.resolve_or_create_publication(h.db, title="Beta")
    assert beta.publication_pk != alpha.publication_pk
    resolved = await svc.resolve_or_create_publication(h.db, title="Beta",
                                                       pmid="42000001")
    assert resolved.publication_pk == alpha.publication_pk
    assert resolved.matched_on == "pmid", "PMID must be resolved before the title"


@case
async def test_7b_the_title_fallback_still_resolves_without_identifiers(h, svc):
    a = await svc.resolve_or_create_publication(h.db, title="No Identifiers Here")
    b = await svc.resolve_or_create_publication(h.db, title="no   identifiers here")
    assert a.publication_pk == b.publication_pk and b.matched_on == "title"


# ===========================================================================
# §22.8-10 — enrichment and conflicts
# ===========================================================================
@case
async def test_8_an_existing_publication_can_gain_a_doi_and_pmcid(h, svc):
    first = await svc.resolve_or_create_publication(h.db, title="Enrich Me",
                                                    pmid="43000001")
    again = await svc.resolve_or_create_publication(
        h.db, title="Enrich Me", pmid="43000001",
        doi="10.3000/enrich", pmcid="PMC7770001")
    assert again.publication_pk == first.publication_pk
    assert set(again.enriched_fields) >= {"doi", "pmcid"}
    assert await h.scalar("SELECT doi FROM publications WHERE entity_pk = :p",
                          p=first.publication_pk) == "10.3000/enrich"


@case
async def test_8b_every_writable_column_round_trips(h, svc):
    """The jsonb columns take a CAST while the scalars do not, so a mis-mapped
    parameter would otherwise be invisible until a real paper carried authors."""
    authors = [{"name": "A. Author", "affiliation": "Inst"}]
    mesh = [{"term": "Hippocampus"}]
    pub = await svc.resolve_or_create_publication(
        h.db, title="Roundtrip", pmid="43500001", doi="10.3500/roundtrip",
        journal_name="J Roundtrip", journal_abbreviation="JR", publication_year=2021,
        abstract_en="abstract", publication_type="journal-article",
        authors_json=authors, keywords_json=["kw1"], mesh_terms_json=mesh,
        affiliations_json=[{"name": "Inst"}], is_open_access=True, citation_count=7,
        full_text_url="https://example.org/x", source_database="europepmc")
    row = await h.row(
        "SELECT original_title, journal_name, journal_abbreviation, publication_year,"
        " abstract_en, publication_type, citation_count, is_open_access, full_text_url,"
        " source_database, pmid, doi, authors_json, keywords_json, mesh_terms_json,"
        " affiliations_json FROM publications WHERE entity_pk = :p",
        p=pub.publication_pk)
    assert dict(row) == {
        "original_title": "Roundtrip", "journal_name": "J Roundtrip",
        "journal_abbreviation": "JR", "publication_year": 2021,
        "abstract_en": "abstract", "publication_type": "journal-article",
        "citation_count": 7, "is_open_access": True,
        "full_text_url": "https://example.org/x", "source_database": "europepmc",
        "pmid": "43500001", "doi": "10.3500/roundtrip", "authors_json": authors,
        "keywords_json": ["kw1"], "mesh_terms_json": mesh,
        "affiliations_json": [{"name": "Inst"}]}


@case
async def test_9_null_never_overwrites_existing_metadata(h, svc):
    first = await svc.resolve_or_create_publication(
        h.db, title="Keep My Journal", pmid="44000001", journal_name="Real Journal")
    again = await svc.resolve_or_create_publication(
        h.db, title="Keep My Journal", pmid="44000001", journal_name=None)
    assert await h.scalar("SELECT journal_name FROM publications WHERE entity_pk = :p",
                          p=first.publication_pk) == "Real Journal"
    # A field the second record simply does not carry is ABSENT, not
    # DISAGREEING: reporting it as a conflict would flood the run with noise
    # and make a genuine disagreement impossible to spot.
    assert [c for c in again.metadata_conflicts if c["field"] == "journal_name"] == []
    assert again.enriched_fields == []


@case
async def test_9b_empty_values_never_overwrite_existing_metadata(h, svc):
    first = await svc.resolve_or_create_publication(
        h.db, title="Keep My Year", pmid="45000001", publication_year=1999)
    await svc.resolve_or_create_publication(
        h.db, title="Keep My Year", pmid="45000001", publication_year=None,
        journal_name="")
    assert await h.scalar("SELECT publication_year FROM publications WHERE entity_pk = :p",
                          p=first.publication_pk) == 1999


@case
async def test_10_a_metadata_conflict_is_recorded_not_silently_applied(h, svc):
    first = await svc.resolve_or_create_publication(
        h.db, title="Conflicted", pmid="46000001", publication_year=2001)
    again = await svc.resolve_or_create_publication(
        h.db, title="Conflicted", pmid="46000001", publication_year=2024)
    assert again.metadata_conflicts, "the disagreement must be recorded"
    conflict = next(c for c in again.metadata_conflicts if c["field"] == "publication_year")
    assert conflict["kept"] == "2001"
    assert conflict["ignored_from_newer_record"] == "2024"
    assert await h.scalar("SELECT publication_year FROM publications WHERE entity_pk = :p",
                          p=first.publication_pk) == 2001, "canonical value must survive"
    assert again.enriched_fields == [], "a conflict must not become an update"


# ===========================================================================
# §22.11-14 — hits
# ===========================================================================
@case
async def test_11_one_publication_can_have_many_hits(h, svc):
    pub = await svc.resolve_or_create_publication(h.db, title="Multi", pmid="47000001")
    run = await svc.create_literature_run(h.db, seed_entity_id=SEED)
    for i in range(3):
        _pk, created = await svc.record_publication_discovery_hit(
            h.db, publication_pk=pub.publication_pk, discovery_run_pk=run["run_pk"],
            query_text=f"query {i}", result_rank=1)
        assert created
    assert await h.count(
        "SELECT count(*) FROM publication_discovery_hits WHERE publication_pk = :p",
        p=pub.publication_pk) == 3


@case
async def test_12_different_queries_produce_different_hits(h, svc):
    pub = await svc.resolve_or_create_publication(h.db, title="Q", pmid="48000001")
    run = await svc.create_literature_run(h.db, seed_entity_id=SEED)
    await svc.record_publication_discovery_hit(
        h.db, publication_pk=pub.publication_pk, discovery_run_pk=run["run_pk"],
        query_text="hippocampus Papez circuit", query_family="A_general")
    await svc.record_publication_discovery_hit(
        h.db, publication_pk=pub.publication_pk, discovery_run_pk=run["run_pk"],
        query_text="hippocampus memory consolidation", query_family="D_functional")
    assert await h.count(
        "SELECT count(DISTINCT query_family) FROM publication_discovery_hits"
        " WHERE publication_pk = :p", p=pub.publication_pk) == 2


@case
async def test_13_different_sources_produce_different_hits(h, svc):
    pub = await svc.resolve_or_create_publication(h.db, title="S", pmid="49000001")
    run = await svc.create_literature_run(h.db, seed_entity_id=SEED)
    epmc = await _source_pk(h, "Europe PMC")
    pubmed = await _source_pk(h, "PubMed")
    assert epmc and pubmed, "both provider sources must be registered"
    for src in (epmc, pubmed):
        _pk, created = await svc.record_publication_discovery_hit(
            h.db, publication_pk=pub.publication_pk, discovery_run_pk=run["run_pk"],
            source_pk=src, query_text="same query text", result_rank=1)
        assert created
    assert await h.count(
        "SELECT count(*) FROM publication_discovery_hits WHERE publication_pk = :p",
        p=pub.publication_pk) == 2, "one query through two providers is two facts"


@case
async def test_14_an_identical_hit_is_idempotent(h, svc):
    pub = await svc.resolve_or_create_publication(h.db, title="I", pmid="50000001")
    run = await svc.create_literature_run(h.db, seed_entity_id=SEED)
    kwargs = dict(publication_pk=pub.publication_pk, discovery_run_pk=run["run_pk"],
                  query_text="repeatable query", result_rank=1)
    _pk1, first = await svc.record_publication_discovery_hit(h.db, **kwargs)
    _pk2, second = await svc.record_publication_discovery_hit(h.db, **kwargs)
    assert first is True and second is False, "a retry must not inflate provenance"
    assert await h.count(
        "SELECT count(*) FROM publication_discovery_hits WHERE publication_pk = :p",
        p=pub.publication_pk) == 1


@case
async def test_14b_a_different_rank_is_a_different_hit(h, svc):
    pub = await svc.resolve_or_create_publication(h.db, title="R", pmid="51000001")
    run = await svc.create_literature_run(h.db, seed_entity_id=SEED)
    for rank in (1, 2):
        _pk, created = await svc.record_publication_discovery_hit(
            h.db, publication_pk=pub.publication_pk, discovery_run_pk=run["run_pk"],
            query_text="ranked query", result_rank=rank)
        assert created


@case
async def test_14c_a_hit_without_a_run_or_source_can_still_be_recorded(h, svc):
    """Retrieval provenance without a recorded run is still worth keeping."""
    pub = await svc.resolve_or_create_publication(h.db, title="Orphan", pmid="51500001")
    _pk, created = await svc.record_publication_discovery_hit(
        h.db, publication_pk=pub.publication_pk, query_text="orphan query")
    assert created


# ===========================================================================
# §22.15-17 — provider failure vs a real empty result
# ===========================================================================
@case
async def test_15_16_a_provider_failure_creates_neither_publication_nor_hit(h, svc):
    """A failed search yields no papers, so there is nothing to persist -- and
    the failure is recorded on the RUN, never as a phantom publication."""
    run = await svc.create_literature_run(h.db, seed_entity_id=SEED)
    before = await h.count("SELECT count(*) FROM publications")
    summary = await svc.persist_search_results(
        h.db, papers=[], discovery_run_pk=run["run_pk"],
        query_text="rate-limited query", query_family="A_general")
    assert summary.publications_created == 0 and summary.hits_recorded == 0
    assert await h.count("SELECT count(*) FROM publications") == before
    assert await h.count(
        "SELECT count(*) FROM publication_discovery_hits WHERE discovery_run_pk = :p",
        p=run["run_pk"]) == 0
    failed = await svc.fail_literature_run(
        h.db, run["run_id"], error_code="SEARCH_PROVIDER_ERROR", error_message="rate limited",
        provenance={"provider_failures": [{"provider": "europepmc", "status_code": 429}]})
    assert failed["status"] == "FAILED"


@case
async def test_17_a_valid_zero_result_search_is_distinguishable_from_failure(h, svc):
    ok = await svc.create_literature_run(h.db, seed_entity_id=SEED)
    await svc.persist_search_results(h.db, papers=[], discovery_run_pk=ok["run_pk"],
                                     query_text="genuinely empty query")
    done = await svc.complete_literature_run(
        h.db, ok["run_id"], outcome="NO_EVIDENCE_FOUND",
        provenance={"provider_failures": [], "partial": False,
                    "all_providers_failed": False, "papers_found": 0})
    assert done["status"] == "COMPLETED" and done["outcome"] == "NO_EVIDENCE_FOUND"
    prov = await h.scalar(
        "SELECT provenance_json FROM knowledge_discovery_runs WHERE run_pk = :p",
        p=ok["run_pk"])
    assert prov["provider_failures"] == [] and prov["papers_found"] == 0


# ===========================================================================
# §22.18-21 — external ids and forbidden writes
# ===========================================================================
@case
async def test_18_openalex_and_semantic_scholar_go_to_entity_xrefs(h, svc):
    pub = await svc.resolve_or_create_publication(
        h.db, title="Xrefs", pmid="52000001",
        external_ids={"OpenAlex": "W123456789", "SemanticScholar": "abc123"})
    assert await h.count("SELECT count(*) FROM entity_xrefs WHERE entity_pk = :p",
                         p=pub.publication_pk) == 2
    assert await h.count(
        "SELECT count(*) FROM information_schema.columns"
        " WHERE table_name='publications' AND column_name IN"
        " ('openalex_id','semantic_scholar_id')") == 0, \
        "provider ids must not become publications columns"


@case
async def test_18b_recording_the_same_external_id_twice_is_idempotent(h, svc):
    kwargs = dict(title="Xref Idem", pmid="53000001", external_ids={"OpenAlex": "W999"})
    first = await svc.resolve_or_create_publication(h.db, **kwargs)
    again = await svc.resolve_or_create_publication(h.db, **kwargs)
    assert first.publication_pk == again.publication_pk
    assert again.external_ids_added == []
    assert await h.count("SELECT count(*) FROM entity_xrefs WHERE entity_pk = :p",
                         p=first.publication_pk) == 1


@case
async def test_18c_an_external_id_owned_by_another_entity_is_not_re_pointed(h, svc):
    """uq_entity_xrefs_resolved_external is UNIQUE table-wide, so a second
    claim on the same provider id must be reported, not crash the run."""
    first = await svc.resolve_or_create_publication(
        h.db, title="Owner", pmid="53500001", external_ids={"OpenAlex": "W777"})
    second = await svc.resolve_or_create_publication(
        h.db, title="Claimant", pmid="53500002", external_ids={"OpenAlex": "W777"})
    assert second.external_ids_added == []
    assert await h.count("SELECT count(*) FROM entity_xrefs WHERE entity_pk = :p",
                         p=first.publication_pk) == 1
    assert await h.count("SELECT count(*) FROM entity_xrefs WHERE entity_pk = :p",
                         p=second.publication_pk) == 0


@case
async def test_19_no_evidence_row_is_created(h, svc):
    pub = await svc.resolve_or_create_publication(
        h.db, title="Evidence Free", pmid="54000001", abstract_en="lots of text")
    run = await svc.create_literature_run(h.db, seed_entity_id=SEED)
    await svc.record_publication_discovery_hit(
        h.db, publication_pk=pub.publication_pk, discovery_run_pk=run["run_pk"],
        query_text="q")
    assert await h.count("SELECT count(*) FROM evidence WHERE publication_pk = :p",
                         p=pub.publication_pk) == 0, \
        "publication metadata is not an Evidence Passage"


@case
async def test_20_no_knowledge_assertion_is_created(h, svc):
    before = await h.count("SELECT count(*) FROM knowledge_assertions")
    await svc.resolve_or_create_publication(h.db, title="No Assertion", pmid="55000001")
    assert await h.count("SELECT count(*) FROM knowledge_assertions") == before


@case
async def test_21_no_connection_circuit_function_or_region_is_created(h, svc):
    before = {t: await h.count(f"SELECT count(*) FROM {t}")
              for t in ("connections", "circuits", "functions", "brain_regions")}
    await svc.resolve_or_create_publication(h.db, title="No KG", pmid="56000001")
    for table, n in before.items():
        assert await h.count(f"SELECT count(*) FROM {table}") == n, table


@case
async def test_21b_a_new_publication_entity_is_proposed_not_active(h, svc):
    pub = await svc.resolve_or_create_publication(h.db, title="Unreviewed",
                                                  pmid="57000001")
    assert await h.scalar("SELECT record_status FROM kg_entities WHERE entity_pk = :p",
                          p=pub.publication_pk) == "proposed", \
        "retrieval is not review"


# ===========================================================================
# §22.22 — transaction boundary
# ===========================================================================
@case
async def test_22_one_failing_paper_does_not_lose_the_others(h, svc):
    run = await svc.create_literature_run(h.db, seed_entity_id=SEED)
    papers = [
        _paper(pmid="58000001", title="Good one"),
        _paper(pmid="58000002", title="Bad year", year="not-a-year"),
        _paper(pmid="58000003", title="Good two"),
    ]
    summary = await svc.persist_search_results(
        h.db, papers=papers, discovery_run_pk=run["run_pk"], query_text="mixed quality")
    assert summary.publications_created == 2, summary.as_dict()
    assert summary.hits_recorded == 2
    assert summary.errors, "the bad row must be reported, not swallowed"
    assert await h.count(
        "SELECT count(*) FROM publications WHERE pmid = :p", p="58000002") == 0


@case
async def test_22b_a_failed_paper_leaves_no_half_written_entity(h, svc):
    """The kg_entities row created for a failing paper must roll back with it."""
    run = await svc.create_literature_run(h.db, seed_entity_id=SEED)
    await svc.persist_search_results(
        h.db, papers=[_paper(pmid="58500001", title="Doomed", year="not-a-year")],
        discovery_run_pk=run["run_pk"], query_text="doomed query")
    assert await h.count(
        "SELECT count(*) FROM kg_entities WHERE name_en = :n", n="Doomed") == 0, \
        "an orphan entity must not survive a failed paper"
    assert await h.count(
        "SELECT count(*) FROM publications WHERE pmid = :p", p="58500001") == 0


@case
async def test_22c_persist_records_hits_with_full_query_provenance(h, svc):
    run = await svc.create_literature_run(h.db, seed_entity_id=SEED)
    epmc = await _source_pk(h, "Europe PMC")
    summary = await svc.persist_search_results(
        h.db, papers=[_paper(pmid="59000001", title="Provenance")],
        discovery_run_pk=run["run_pk"], source_pk=epmc,
        query_text="hippocampus AND nucleus reuniens",
        query_family="C_aff_eff", query_level="MEMBER_COMBINATION")
    assert summary.hits_recorded == 1
    row = await h.row(
        "SELECT query_text, query_family, query_level, result_rank, retrieved_at"
        " FROM publication_discovery_hits WHERE discovery_run_pk = :p",
        p=run["run_pk"])
    assert row["query_text"] == "hippocampus AND nucleus reuniens"
    assert (row["query_family"], row["query_level"], row["result_rank"]) == (
        "C_aff_eff", "MEMBER_COMBINATION", 1)
    assert row["retrieved_at"] is not None


@case
async def test_22d_re_running_the_same_search_deduplicates(h, svc):
    run = await svc.create_literature_run(h.db, seed_entity_id=SEED)
    papers = [_paper(pmid="59500001", title="Repeat"),
              _paper(pmid="59500002", title="Repeat 2")]
    first = await svc.persist_search_results(h.db, papers=papers,
                                             discovery_run_pk=run["run_pk"],
                                             query_text="same query")
    second = await svc.persist_search_results(h.db, papers=papers,
                                              discovery_run_pk=run["run_pk"],
                                              query_text="same query")
    assert first.publications_created == 2 and first.hits_recorded == 2
    assert second.publications_created == 0 and second.publications_matched == 2
    assert second.hits_recorded == 0 and second.hits_deduplicated == 2


# ===========================================================================
# §6 — identifier normalization
# ===========================================================================
@pytest.mark.parametrize("junk", ["", "   ", "n/a", "N/A", "unknown", "none", "null", "-"])
def test_normalization_treats_sentinel_values_as_absent(svc, junk):
    assert svc.normalize_pmid(junk) is None
    assert svc.normalize_doi(junk) is None
    assert svc.normalize_pmcid(junk) is None


def test_normalization_folds_doi_case_and_uppercases_pmcid(svc):
    assert svc.normalize_doi("  10.1000/ABC  ") == "10.1000/abc"
    assert svc.normalize_doi("doi:10.1000/ABC") == "10.1000/abc"
    assert svc.normalize_pmcid(" pmc1234567 ") == "PMC1234567"
    assert svc.normalize_pmid(" 40000001 ") == "40000001"


@case
async def test_a_junk_identifier_never_becomes_a_real_identity(h, svc):
    """Two papers both reporting pmid='n/a' must not collide on it."""
    a = await svc.resolve_or_create_publication(h.db, title="Junk A", pmid="n/a")
    b = await svc.resolve_or_create_publication(h.db, title="Junk B", pmid="N/A")
    assert a.publication_pk != b.publication_pk
    assert await h.scalar("SELECT pmid FROM publications WHERE entity_pk = :p",
                          p=a.publication_pk) is None


# ===========================================================================
# Phase 3E.2D-2A — explicit retrieval ranks
# ===========================================================================
# The rank of a hit is the rank the PROVIDER gave the paper for that query. A
# caller that filtered or reordered papers before persisting must be able to
# keep it; otherwise a paper the provider ranked 2nd is recorded as rank 1 and
# the retrieval provenance is simply wrong.
async def _stored_ranks(h, run_pk: int) -> list[int]:
    from sqlalchemy import text

    rows = (
        await h.db.execute(
            text("SELECT result_rank FROM publication_discovery_hits"
                 " WHERE discovery_run_pk = :p ORDER BY hit_pk"),
            {"p": run_pk},
        )
    ).scalars().all()
    return [int(r) for r in rows]


@case
async def test_23_without_explicit_ranks_the_1_to_n_behaviour_is_unchanged(h, svc):
    run = await svc.create_literature_run(h.db, seed_entity_id=SEED)
    summary = await svc.persist_search_results(
        h.db,
        papers=[_paper(pmid="63000001", title="First"), _paper(pmid="63000002", title="Second")],
        discovery_run_pk=run["run_pk"], query_text="ordered by provider",
    )
    assert summary.hits_recorded == 2
    assert await _stored_ranks(h, run["run_pk"]) == [1, 2]


@case
async def test_23b_explicit_ranks_are_recorded_verbatim(h, svc):
    run = await svc.create_literature_run(h.db, seed_entity_id=SEED)
    summary = await svc.persist_search_results(
        h.db,
        papers=[_paper(pmid="63100001", title="Rank 2"), _paper(pmid="63100002", title="Rank 7")],
        discovery_run_pk=run["run_pk"], query_text="filtered subset",
        result_ranks=[2, 7],
    )
    assert summary.hits_recorded == 2
    assert await _stored_ranks(h, run["run_pk"]) == [2, 7]


@case
async def test_23c_invalid_ranks_are_rejected_before_any_write(h, svc):
    """Validation is up-front: a half-persisted run is the exact partial state
    the per-publication transaction exists to prevent."""
    run = await svc.create_literature_run(h.db, seed_entity_id=SEED)
    papers = [_paper(pmid="63200001", title="A"), _paper(pmid="63200002", title="B")]
    before = await h.count("SELECT count(*) FROM publications")

    for bad in ([1], [1, 2, 3], [0, 1], [-1, 2], [True, 2], [1, "2"], [1.5, 2], []):
        with pytest.raises(ValueError):
            await svc.persist_search_results(
                h.db, papers=papers, discovery_run_pk=run["run_pk"],
                query_text="q", result_ranks=bad,
            )

    assert await h.count("SELECT count(*) FROM publications") == before, \
        "a rejected rank list must not leave publications behind"
    assert await h.count(
        "SELECT count(*) FROM publication_discovery_hits WHERE discovery_run_pk = :p",
        p=run["run_pk"]) == 0


@case
async def test_23d_idempotency_still_holds_with_explicit_ranks(h, svc):
    run = await svc.create_literature_run(h.db, seed_entity_id=SEED)
    papers = [_paper(pmid="63300001", title="Idem")]
    kwargs = dict(papers=papers, discovery_run_pk=run["run_pk"],
                  query_text="same query", result_ranks=[3])

    first = await svc.persist_search_results(h.db, **kwargs)
    second = await svc.persist_search_results(h.db, **kwargs)

    assert first.hits_recorded == 1
    assert second.hits_recorded == 0 and second.hits_deduplicated == 1
    assert await _stored_ranks(h, run["run_pk"]) == [3], "the retry must not add a hit"


@case
async def test_23e_one_publication_may_have_many_explicitly_ranked_hits(h, svc):
    pub = await svc.resolve_or_create_publication(h.db, title="Multi ranked", pmid="63400001")
    run = await svc.create_literature_run(h.db, seed_entity_id=SEED)
    for rank in (1, 5, 9):
        _pk, created = await svc.record_publication_discovery_hit(
            h.db, publication_pk=pub.publication_pk, discovery_run_pk=run["run_pk"],
            query_text=f"query at rank {rank}", result_rank=rank)
        assert created
    assert sorted(await _stored_ranks(h, run["run_pk"])) == [1, 5, 9]
