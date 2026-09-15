"""Phase 3E.2B — Literature production READ API.

Exercises the real read service and the real route handlers against the
isolated test database, because what is under test is the queries themselves:
their joins, their empty-result semantics and their provenance grouping. A fake
session would prove only the fake.

Isolation: each test runs inside an outer transaction that is always ROLLED
BACK, and the session joins it with ``join_transaction_mode="create_savepoint"``
so any internal ``commit()`` releases a SAVEPOINT instead of committing. Fixture
data is written through the REAL Phase 3E.1B services, so the read layer is
tested against the shapes the write layer actually produces -- not against
hand-rolled rows that might agree with my assumptions instead of the schema.

HTTP transport is NOT exercised: the route coroutines are called directly and
their ``HTTPException`` is inspected. That checks the exact status-code contract
without binding an async session to a second event loop.
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

import pytest
from fastapi import HTTPException

BACKEND = Path(__file__).resolve().parents[1]
E2E_DB = os.environ.get("TEST_E2E_DB", "neurographiq_human_brain_v1_e2e")
SERVICE_PATH = BACKEND / "app" / "services" / "knowledge_production_literature_service.py"


def _dsn() -> str:
    cfg: dict[str, str] = {}
    env = BACKEND / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    return "postgresql+psycopg://%s:%s@%s:%s/%s" % (
        cfg.get("POSTGRES_USER"), cfg.get("POSTGRES_PASSWORD"),
        cfg.get("POSTGRES_HOST", "127.0.0.1"), cfg.get("POSTGRES_PORT", "5432"), E2E_DB)


@dataclass
class Session:
    db: Any

    async def scalar(self, sql: str, **params: Any) -> Any:
        from sqlalchemy import text

        return (await self.db.execute(text(sql), params)).scalar_one_or_none()

    async def count(self, sql: str, **params: Any) -> int:
        return int(await self.scalar(sql, **params))


def case(fn: Callable[[Session], Awaitable[None]]):
    """Run an async test in one event loop, inside a rolled-back transaction.

    The name is copied by hand rather than with ``functools.wraps``: ``wraps``
    sets ``__wrapped__``, which makes pytest follow it to the async signature.
    """

    def wrapper() -> None:
        asyncio.run(_drive(fn))

    wrapper.__name__ = fn.__name__
    wrapper.__qualname__ = fn.__qualname__
    wrapper.__doc__ = fn.__doc__
    return wrapper


async def _drive(fn: Callable[[Session], Awaitable[None]]) -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(_dsn(), poolclass=NullPool)
    try:
        connection = await engine.connect()
    except Exception as exc:  # pragma: no cover - environment dependent
        await engine.dispose()
        pytest.skip(f"isolated test database unavailable: {type(exc).__name__}")

    transaction = await connection.begin()
    db = AsyncSession(bind=connection, join_transaction_mode="create_savepoint")
    try:
        if (
            await connection.execute(
                text("SELECT to_regclass('public.publication_discovery_hits')")
            )
        ).scalar_one() is None:
            pytest.skip("gate7b_013 not applied to the isolated test database")
        # Supply exactly the fixtures the test declares, so a test can ask for
        # just the session, or the session plus the services it drives.
        lit_mod, persistence_mod = _modules()
        available = (Session(db), lit_mod, persistence_mod)
        await fn(*available[:len(inspect.signature(fn).parameters)])
    finally:
        await db.close()
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


def _modules():
    from app.services import knowledge_production_literature_service as lit
    from app.services import publication_persistence_service as persistence

    return lit, persistence


@pytest.fixture(scope="module")
def lit():
    return pytest.importorskip("app.services.knowledge_production_literature_service")


@pytest.fixture(scope="module")
def persistence():
    return pytest.importorskip("app.services.publication_persistence_service")


async def _seed_entity_id(h: Session) -> str:
    """The E2E database's Left Hippocampus, resolved by NAME.

    Never hard-coded: the isolated database is loaded from a different dump, so
    the same anatomical region carries a different entity_id there.
    """
    entity_id = await h.scalar(
        "SELECT entity_id FROM kg_entities WHERE entity_type='brain_region'"
        " AND name_en = 'Left Hippocampus' ORDER BY entity_id LIMIT 1")
    if entity_id is None:  # pragma: no cover - environment dependent
        pytest.skip("Left Hippocampus not present in the isolated test database")
    return entity_id


async def _source_pk(h: Session, name: str = "Europe PMC") -> int:
    pk = await h.scalar("SELECT source_pk FROM sources WHERE name_en = :n LIMIT 1", n=name)
    if pk is None:  # pragma: no cover - environment dependent
        pytest.skip(f"source '{name}' not registered in the isolated test database")
    return int(pk)


def _paper(pmid: str, title: str) -> dict[str, Any]:
    return {"title": title, "pmid": pmid, "doi": f"10.7000/paper-{pmid}",
            "journal": "J Read", "year": 2022, "source": "europepmc"}


async def _one_run_with_papers(h: Session, persistence, *, papers, queries, provenance=None,
                               complete=True, entity_id=None):
    """Build a realistic literature run through the REAL Phase 3E.1B services."""
    seed = entity_id or await _seed_entity_id(h)
    source = await _source_pk(h)
    run = await persistence.create_literature_run(
        h.db, seed_entity_id=seed, discovery_type="EVIDENCE_SEARCH", provider="europepmc",
        provenance={"phase": "3E.2B-test"})
    for query, subset in zip(queries, papers):
        await persistence.persist_search_results(
            h.db, papers=subset, discovery_run_pk=run["run_pk"], source_pk=source,
            query_text=query, query_family="A_general", query_level="NAME")
    if complete:
        await persistence.complete_literature_run(
            h.db, run["run_id"], outcome="CANDIDATES_FOUND", provenance=provenance or {})
    return run


# ===========================================================================
# §5.1-2 — empty vs missing
# ===========================================================================
@case
async def test_1_a_known_region_with_no_literature_data_is_empty_not_missing(h, lit):
    seed = await _seed_entity_id(h)
    result = await lit.list_literature_runs_for_region(h.db, entity_id=seed)
    assert result is not None, "an existing region must NOT be reported as missing"
    assert result.items == [] and result.total == 0


@case
async def test_2_an_unknown_region_is_not_found(h, lit):
    assert await lit.list_literature_runs_for_region(
        h.db, entity_id="NGIQ-BR-99999999") is None


# ===========================================================================
# §5.3-5 — run fields and the bounded diagnostics projection
# ===========================================================================
@case
async def test_3_a_literature_run_is_returned_with_status_outcome_provider(h, lit, persistence):
    run = await _one_run_with_papers(
        h, persistence, papers=[[_paper("71000001", "One")]], queries=["q1"])
    result = await lit.list_literature_runs_for_region(
        h.db, entity_id=await _seed_entity_id(h))
    item = next(i for i in result.items if i.run_id == str(run["run_id"]))
    assert item.status == "COMPLETED"
    assert item.outcome == "CANDIDATES_FOUND"
    assert item.provider == "europepmc"
    assert item.finished_at is not None


@case
async def test_4_bounded_diagnostics_are_returned(h, lit, persistence):
    # The exact shape the search layer emits: all five keys, scalars only.
    failures = [{"provider": "europepmc", "status_code": 429, "retryable": True,
                 "message": "HTTP 429", "query_strategy": "A_general"}]
    run = await _one_run_with_papers(
        h, persistence, papers=[[]], queries=["q1"],
        provenance={"provider_failures": failures, "partial": True,
                    "all_providers_failed": False, "papers_found": 0})
    result = await lit.list_literature_runs_for_region(
        h.db, entity_id=await _seed_entity_id(h))
    d = next(i for i in result.items if i.run_id == str(run["run_id"])).diagnostics
    assert [f.model_dump() for f in d.provider_failures] == failures
    assert d.partial is True
    assert d.all_providers_failed is False
    assert d.papers_found == 0


@case
async def test_4c_a_malformed_failure_entry_cannot_break_the_run(h, lit, persistence):
    """COERCION, not just bounding.

    Bounding is guaranteed by the DTO (Pydantic ignores unknown keys). What is
    NOT free is tolerance: a wrong-typed field would otherwise fail validation
    and make the whole run unreadable -- one bad entry written by another layer
    taking down the endpoint. Wrong types degrade to None; an entry with no
    provider is not a diagnostic and is dropped.
    """
    run = await _one_run_with_papers(
        h, persistence, papers=[[]], queries=["q1"],
        provenance={"provider_failures": [
            {"provider": "pubmed", "status_code": {"nested": 1}, "retryable": "yes",
             "message": ["not", "a", "string"], "query_strategy": 7},
            {"status_code": 500},          # no provider: not a diagnostic
            "not-a-mapping-at-all"], "papers_found": 0})
    result = await lit.list_literature_runs_for_region(
        h.db, entity_id=await _seed_entity_id(h))
    d = next(i for i in result.items if i.run_id == str(run["run_id"])).diagnostics
    assert len(d.provider_failures) == 1, "only the well-formed entry survives"
    failure = d.provider_failures[0]
    assert failure.provider == "pubmed"
    assert (failure.status_code, failure.retryable, failure.message,
            failure.query_strategy) == (None, None, None, None)


@case
async def test_4b_a_failure_entry_carrying_extra_fields_is_bounded(h, lit, persistence):
    """Anything beyond the five known fields is dropped, not forwarded.

    provenance_json is an unconstrained jsonb column, so the read layer is the
    only place this bound can hold."""
    run = await _one_run_with_papers(
        h, persistence, papers=[[]], queries=["q1"],
        provenance={"provider_failures": [
            {"provider": "pubmed", "status_code": 503, "retryable": True,
             "message": "upstream", "query_strategy": "loose",
             "internal_payload": {"api_key": "must-not-leak"},
             "raw_response": "must-not-leak-either"}], "papers_found": 0})
    result = await lit.list_literature_runs_for_region(
        h.db, entity_id=await _seed_entity_id(h))
    item = next(i for i in result.items if i.run_id == str(run["run_id"]))
    failure = item.diagnostics.provider_failures[0]
    assert failure.provider == "pubmed" and failure.query_strategy == "loose"
    assert set(failure.model_dump()) == {
        "provider", "status_code", "retryable", "message", "query_strategy"}
    blob = json.dumps(item.model_dump(mode="json"))
    assert "must-not-leak" not in blob


@case
async def test_5_the_full_provenance_blob_is_never_exposed(h, lit, persistence):
    """Only the four whitelisted keys may cross the boundary."""
    run = await _one_run_with_papers(
        h, persistence, papers=[[]], queries=["q1"],
        provenance={"provider_failures": [], "papers_found": 0,
                    "INTERNAL_SENTINEL": "must-not-leak",
                    "query_strategy_version": "internal"})
    result = await lit.list_literature_runs_for_region(
        h.db, entity_id=await _seed_entity_id(h))
    item = next(i for i in result.items if i.run_id == str(run["run_id"]))
    blob = json.dumps(item.model_dump(mode="json"))
    assert "must-not-leak" not in blob
    assert "INTERNAL_SENTINEL" not in blob
    assert "query_strategy_version" not in blob


def test_5b_the_projection_keys_match_the_declared_contract(lit):
    """The DTO's fields and the frozen whitelist must not drift apart."""
    from app.schemas.knowledge_production import (
        LITERATURE_DIAGNOSTIC_KEYS,
        LiteratureRunDiagnostics,
    )

    assert set(LiteratureRunDiagnostics.model_fields) == set(LITERATURE_DIAGNOSTIC_KEYS)


# ===========================================================================
# §5.6-8 — publications and hit provenance
# ===========================================================================
@case
async def test_6_one_publication_found_by_three_queries_keeps_three_hits(h, lit, persistence):
    """distinct_publications == 1 but hits_total == 3. Collapsing these would
    destroy the retrieval provenance that hit idempotency exists to protect."""
    paper = _paper("72000001", "Found three ways")
    run = await _one_run_with_papers(
        h, persistence, papers=[[paper], [paper], [paper]],
        queries=["query alpha", "query beta", "query gamma"])
    result = await lit.list_publications_for_run(h.db, run_id=str(run["run_id"]))
    assert result is not None
    assert result.distinct_publications == 1
    assert result.hits_total == 3
    assert len(result.items) == 1
    assert len(result.items[0].hits) == 3
    assert {x.query_text for x in result.items[0].hits} == {
        "query alpha", "query beta", "query gamma"}


@case
async def test_7_hit_provenance_preserves_every_field(h, lit, persistence):
    run = await _one_run_with_papers(
        h, persistence, papers=[[_paper("73000001", "Provenance")]], queries=["the query"])
    result = await lit.list_publications_for_run(h.db, run_id=str(run["run_id"]))
    hit = result.items[0].hits[0]
    assert hit.query_text == "the query"
    assert hit.query_family == "A_general"
    assert hit.query_level == "NAME"
    assert hit.source == "Europe PMC"
    assert hit.result_rank == 1
    assert hit.retrieved_at is not None
    assert hit.run_id == str(run["run_id"])


@case
async def test_8_two_publications_in_one_run_are_both_returned(h, lit, persistence):
    run = await _one_run_with_papers(
        h, persistence,
        papers=[[_paper("74000001", "First"), _paper("74000002", "Second")]],
        queries=["q1"])
    result = await lit.list_publications_for_run(h.db, run_id=str(run["run_id"]))
    assert result.distinct_publications == 2
    assert result.hits_total == 2
    assert {item.pmid for item in result.items} == {"74000001", "74000002"}
    assert {item.original_title for item in result.items} == {"First", "Second"}


@case
async def test_8b_an_unknown_run_is_not_found(h, lit):
    assert await lit.list_publications_for_run(
        h.db, run_id="00000000-0000-0000-0000-000000000000") is None


@case
async def test_8c_a_run_that_reached_nothing_is_empty_not_missing(h, lit, persistence):
    run = await _one_run_with_papers(h, persistence, papers=[[]], queries=["empty query"])
    result = await lit.list_publications_for_run(h.db, run_id=str(run["run_id"]))
    assert result is not None, "an existing run must NOT be reported as missing"
    assert result.items == [] and result.hits_total == 0


# ===========================================================================
# §5.9 — publication detail spans runs
# ===========================================================================
@case
async def test_9_publication_detail_returns_hits_across_runs(h, lit, persistence):
    seed = await _seed_entity_id(h)
    paper = _paper("75000001", "Across runs")
    first = await _one_run_with_papers(
        h, persistence, papers=[[paper]], queries=["run one query"], entity_id=seed)
    await persistence.complete_literature_run(
        h.db, first["run_id"], outcome="CANDIDATES_FOUND")
    second = await _one_run_with_papers(
        h, persistence, papers=[[paper]], queries=["run two query"], entity_id=seed)

    entity_id = (await lit.list_publications_for_run(h.db, run_id=str(first["run_id"]))
                 ).items[0].entity_id
    detail = await lit.get_publication(h.db, entity_id=entity_id)
    assert detail is not None
    assert detail.pmid == "75000001"
    assert detail.hits_total == 2
    assert {x.run_id for x in detail.hits} == {str(first["run_id"]), str(second["run_id"])}
    assert {x.query_text for x in detail.hits} == {"run one query", "run two query"}


@case
async def test_8d_an_llm_discovery_run_is_not_a_literature_resource(h, lit, persistence):
    """Blocker 1.

    An LLM_DISCOVERY run never searches literature. Reading it through the
    literature endpoint and getting "200 + no publications" would assert that a
    search ran and found nothing -- a false scientific statement, since no
    search happened at all. It must be 404: not a literature resource.
    """
    from sqlalchemy import text

    seed = await _seed_entity_id(h)
    run_id = (
        await h.db.execute(
            text("INSERT INTO knowledge_discovery_runs"
                 " (seed_region_pk, discovery_type, status, outcome,"
                 "  started_at, finished_at)"
                 " SELECT entity_pk, 'LLM_DISCOVERY', 'COMPLETED',"
                 "        'NO_CANDIDATES_FOUND', now(), now()"
                 " FROM brain_regions WHERE entity_pk ="
                 "   (SELECT entity_pk FROM kg_entities WHERE entity_id = :e)"
                 " RETURNING run_id"),
            {"e": seed},
        )
    ).scalar_one()

    assert await lit.resolve_literature_run_pk(h.db, str(run_id)) is None
    assert await lit.list_publications_for_run(h.db, run_id=str(run_id)) is None

    from app.routers import knowledge_production as routes

    with pytest.raises(HTTPException) as exc:
        await routes.list_run_publications(run_id=str(run_id), db=h.db)
    assert exc.value.status_code == 404


@case
async def test_9b_an_unknown_publication_is_not_found(h, lit):
    assert await lit.get_publication(h.db, entity_id="NGIQ-PUB-99999999") is None


@case
async def test_9c_a_brain_region_entity_id_is_not_a_publication(h, lit):
    """A reader can paste the wrong kind of id; it must not resolve to a paper.

    This holds because the lookup joins ``publications``, which a BrainRegion
    has no row in -- not because of the entity_type scope (see test_9d).
    """
    seed = await _seed_entity_id(h)
    assert await lit.get_publication(h.db, entity_id=seed) is None


@case
async def test_9d_both_read_paths_obey_the_same_entity_authority(h, lit, persistence):
    """Blocker 2. The entity_type scope is load-bearing, not decoration.

    ``publications`` is guarded by a BEFORE INSERT trigger
    (``trg_publications_entity_type``) and ``kg_entities`` carries NO trigger at
    all, so an existing publications row survives a later change to its
    entity's type. BOTH read paths must then refuse it -- if only one did, the
    two endpoints would disagree about what a publication is.
    """
    from sqlalchemy import text

    run = await _one_run_with_papers(
        h, persistence, papers=[[_paper("78000001", "Type drift")]], queries=["q1"])
    listing = await lit.list_publications_for_run(h.db, run_id=str(run["run_id"]))
    entity_id = listing.items[0].entity_id
    assert listing.distinct_publications == 1
    assert await lit.get_publication(h.db, entity_id=entity_id) is not None

    await h.db.execute(
        text("UPDATE kg_entities SET entity_type = 'brain_region' WHERE entity_id = :e"),
        {"e": entity_id})

    assert await lit.get_publication(h.db, entity_id=entity_id) is None, \
        "publication detail must refuse a publications row that is no longer a publication"
    drifted = await lit.list_publications_for_run(h.db, run_id=str(run["run_id"]))
    assert drifted.items == [] and drifted.distinct_publications == 0, \
        "the run listing must refuse it too -- 404 and 200 must not disagree"


# ===========================================================================
# §5.10-11 — no knowledge is created or required; reads change nothing
# ===========================================================================
@case
async def test_10_no_evidence_or_assertion_is_created_or_required(h, lit, persistence):
    before_ev = await h.count("SELECT count(*) FROM evidence")
    before_as = await h.count("SELECT count(*) FROM knowledge_assertions")
    run = await _one_run_with_papers(
        h, persistence, papers=[[_paper("76000001", "No knowledge")]], queries=["q1"])
    await lit.list_literature_runs_for_region(h.db, entity_id=await _seed_entity_id(h))
    await lit.list_publications_for_run(h.db, run_id=str(run["run_id"]))
    assert await h.count("SELECT count(*) FROM evidence") == before_ev
    assert await h.count("SELECT count(*) FROM knowledge_assertions") == before_as
    # and the publication DTO exposes no evidence semantics at all
    from app.schemas.knowledge_production import PublicationHitItem

    for forbidden in ("supports", "contradicts", "evidence_strength", "e1", "e2"):
        assert forbidden not in PublicationHitItem.model_fields


@case
async def test_11_the_reads_change_no_table_counts(h, lit, persistence):
    run = await _one_run_with_papers(
        h, persistence, papers=[[_paper("77000001", "Counts")]], queries=["q1"])
    tables = ("knowledge_discovery_runs", "publications", "publication_discovery_hits",
              "evidence", "knowledge_assertions", "connections", "circuits", "functions")
    before = {t: await h.count(f"SELECT count(*) FROM {t}") for t in tables}
    for _ in range(2):  # repeat: a read must be idempotent, not merely quiet once
        await lit.list_literature_runs_for_region(h.db, entity_id=await _seed_entity_id(h))
        await lit.list_publications_for_run(h.db, run_id=str(run["run_id"]))
        await lit.get_publication(
            h.db, entity_id=(await lit.list_publications_for_run(
                h.db, run_id=str(run["run_id"]))).items[0].entity_id)
    for table, n in before.items():
        assert await h.count(f"SELECT count(*) FROM {table}") == n, table


# ===========================================================================
# §3 — route-level status contract (handlers called directly)
# ===========================================================================
@case
async def test_13_route_contract_404_vs_200_empty(h):
    # The handlers are called directly, so FastAPI's Query(...) defaults are NOT
    # resolved for us -- limit/offset must be supplied explicitly.
    from app.routers import knowledge_production as routes

    seed = await _seed_entity_id(h)
    ok = await routes.list_brain_region_literature_runs(
        entity_id=seed, limit=50, offset=0, db=h.db)
    assert ok.items == [] and ok.total == 0

    with pytest.raises(HTTPException) as region:
        await routes.list_brain_region_literature_runs(
            entity_id="NGIQ-BR-99999999", limit=50, offset=0, db=h.db)
    assert region.value.status_code == 404

    with pytest.raises(HTTPException) as run:
        await routes.list_run_publications(
            run_id="00000000-0000-0000-0000-000000000000", db=h.db)
    assert run.value.status_code == 404

    with pytest.raises(HTTPException) as pub:
        await routes.get_publication(entity_id="NGIQ-PUB-99999999", db=h.db)
    assert pub.value.status_code == 404


@case
async def test_13b_a_malformed_run_id_is_404_not_500(h):
    from app.routers import knowledge_production as routes

    with pytest.raises(HTTPException) as exc:
        await routes.list_run_publications(run_id="not-a-uuid", db=h.db)
    assert exc.value.status_code == 404


@case
async def test_13c_a_route_error_body_carries_no_sql_or_internals(h):
    from app.routers import knowledge_production as routes

    with pytest.raises(HTTPException) as exc:
        await routes.get_publication(entity_id="NGIQ-PUB-99999999", db=h.db)
    body = json.dumps(exc.value.detail)
    for forbidden in ("SELECT", "FROM", "publication_discovery_hits", "psycopg"):
        assert forbidden not in body, forbidden


# ===========================================================================
# §5.12 — static architecture boundary (no DB required)
# ===========================================================================
def _code_only_without_literals(path: Path) -> str:
    """Executable code with every string constant blanked out and comments gone.

    The boundary check must inspect what the module DOES. Its docstring
    legitimately names the providers it forbids, so prose must not be scanned.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            node.value = ""
    return ast.unparse(tree)


def _docstrings(tree: ast.AST) -> set[str]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None:
                found.add(doc)
    return found


def _string_literals(path: Path) -> list[str]:
    """Every string constant in the module, EXCLUDING docstrings.

    Docstrings are prose: this module's own docstring says it "issues SELECT
    statements only", which would otherwise be scanned as if it were SQL.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs = _docstrings(tree)
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and n.value not in docs]


def test_12_the_read_service_reaches_no_provider_or_search_client():
    code = _code_only_without_literals(SERVICE_PATH)
    for forbidden in ("paper_search", "llm_providers", "deepseek", "openai", "kimi",
                      "europepmc", "pubmed", "openalex", "semanticscholar", "httpx",
                      "requests"):
        assert forbidden not in code.lower(), f"read service must not reference {forbidden}"


def test_12b_the_read_service_imports_only_read_dependencies():
    tree = ast.parse(SERVICE_PATH.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    allowed_prefixes = ("__future__", "typing", "uuid", "sqlalchemy", "app.schemas",
                        "app.services.knowledge_discovery_run_service")
    for module in imported:
        assert module.startswith(allowed_prefixes), f"unexpected import: {module}"


def test_12c_the_read_service_issues_no_write_statement():
    literals = _string_literals(SERVICE_PATH)
    # Non-vacuous: the scan must actually be looking at this module's SQL.
    assert any("SELECT" in s.upper() for s in literals), \
        "the SQL scan found no statement at all -- it is not testing anything"
    for literal in literals:
        upper = literal.upper()
        for keyword in ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ", "TRUNCATE "):
            assert keyword not in upper, f"write statement found: {keyword.strip()}"


def test_12d_no_transaction_or_session_mutation_is_used():
    """No commit/rollback/flush: a read service has nothing to make durable."""
    code = _code_only_without_literals(SERVICE_PATH)
    for call in (".commit(", ".rollback(", ".flush(", ".add(", ".delete(", ".execute("):
        if call == ".execute(":
            continue  # reading requires execute
        assert call not in code, f"read service must not call {call}"


# ===========================================================================
# §6 — vocabulary convergence: the cross-layer guard
# ===========================================================================
@case
async def test_14_the_app_vocabulary_matches_the_database_check(h):
    """The guard that went missing: gate7b_013 widened ck_kdr_discovery_type to
    four values while the app constant kept two, and nothing compared the two
    layers. Comparing the constant to its own source Literal would be a
    tautology (it is derived from it), so this reaches across to the database."""
    from app.schemas.knowledge_production import (
        DISCOVERY_TYPES,
        LITERATURE_DISCOVERY_TYPES,
    )

    definition = await h.scalar(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
        " WHERE conname = 'ck_kdr_discovery_type'")
    assert definition is not None, "ck_kdr_discovery_type must exist"
    allowed = set(re.findall(r"'([A-Z_]+)'", definition))
    assert allowed == set(DISCOVERY_TYPES), "app vocabulary drifted from the DB check"
    assert set(LITERATURE_DISCOVERY_TYPES) == allowed - {"LLM_DISCOVERY"}
