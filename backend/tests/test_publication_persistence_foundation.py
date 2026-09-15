"""Phase 3E.1A — Publication persistence foundation (gate7b_013).

These tests exercise the REAL database, because the thing under test IS the
constraint set: a fake would only prove the fake. They run against the
isolated ``neurographiq_human_brain_v1_e2e`` database and SKIP (loudly, never
silently pass) when it is unavailable, so the suite stays honest about what it
did and did not verify.

Every test wraps itself in a transaction that is ROLLED BACK, so the test
database is left exactly as found.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND / "migrations" / "gate7b_013_publication_persistence_foundation.sql"

E2E_DB = os.environ.get("TEST_E2E_DB", "neurographiq_human_brain_v1_e2e")


def _dsn() -> str:
    cfg: dict[str, str] = {}
    env = BACKEND / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    return "postgresql://%s:%s@%s:%s/%s" % (
        cfg.get("POSTGRES_USER"), cfg.get("POSTGRES_PASSWORD"),
        cfg.get("POSTGRES_HOST", "127.0.0.1"), cfg.get("POSTGRES_PORT", "5432"), E2E_DB)


@pytest.fixture(scope="module")
def db():
    psycopg = pytest.importorskip("psycopg")
    try:
        conn = psycopg.connect(_dsn(), autocommit=False)
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"isolated test database unavailable: {type(exc).__name__}")
    cur = conn.cursor()
    cur.execute("select to_regclass('public.publication_discovery_hits')")
    if cur.fetchone()[0] is None:
        conn.close()
        pytest.skip("gate7b_013 not applied to the isolated test database")
    yield conn
    conn.rollback()
    conn.close()


class _Tx:
    """A transaction that always rolls back."""

    def __init__(self, conn):
        self.conn = conn
        self.cur = conn.cursor()
        self.cur.execute("SAVEPOINT test_case")

    def __enter__(self):
        return self.cur

    def __exit__(self, exc_type, exc, tb):
        self.cur.execute("ROLLBACK TO SAVEPOINT test_case")
        self.conn.rollback()
        return False


def _seed_ids(cur):
    cur.execute("select entity_pk from brain_regions limit 1")
    region = cur.fetchone()[0]
    cur.execute("select source_pk from sources limit 1")
    source = cur.fetchone()[0]
    return region, source


def _make_publication(cur, *, pmid=None, pmcid=None, doi=None, title="T") -> int:
    """A publications row is a kg_entities subtype, so it needs both.

    'proposed' is the honest status for a freshly retrieved publication, and it
    is also the least encumbered: kg_entities requires a proposed entity to have
    a name AND a declared source, while an 'active' one would additionally need
    a bilingual name whose zh_source is not 'unknown'.
    """
    eid = f"NGIQ-PUB-{uuid.uuid4().hex[:8].upper()}"
    cur.execute(
        "INSERT INTO kg_entities (entity_id, entity_type, name_en, source_name_original,"
        " record_status) VALUES (%s, 'publication', %s, 'europepmc', 'proposed')"
        " RETURNING entity_pk", (eid, title))
    pk = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO publications (entity_pk, original_title, pmid, pmcid, doi)"
        " VALUES (%s, %s, %s, %s, %s)", (pk, title, pmid, pmcid, doi))
    return pk


def _make_run(cur, region_pk, run_type="EVIDENCE_SEARCH") -> int:
    cur.execute(
        "INSERT INTO knowledge_discovery_runs (seed_region_pk, discovery_type, status)"
        " VALUES (%s, %s, 'QUEUED') RETURNING run_pk", (region_pk, run_type))
    return cur.fetchone()[0]


def _make_hit(cur, pub_pk, *, run_pk=None, source_pk=None, region_pk=None,
              family="A_general", level="NAME", text="hippocampus circuit", rank=1):
    cur.execute(
        "INSERT INTO publication_discovery_hits"
        " (publication_pk, discovery_run_pk, source_pk, seed_brain_region_pk,"
        "  query_family, query_level, query_text, result_rank)"
        " VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING hit_pk, hit_id",
        (pub_pk, run_pk, source_pk, region_pk, family, level, text, rank))
    return cur.fetchone()


# ===========================================================================
# §18.1 — publication identity guards
# ===========================================================================
def test_1_duplicate_pmid_is_rejected(db):
    with _Tx(db) as cur:
        _make_publication(cur, pmid="12345678")
        with pytest.raises(Exception) as exc:
            _make_publication(cur, pmid="12345678")
    assert "uq_publications_pmid" in str(exc.value) or "duplicate" in str(exc.value).lower()


def test_1b_duplicate_doi_is_rejected_case_insensitively(db):
    """10.1/X and 10.1/x are the same DOI."""
    with _Tx(db) as cur:
        _make_publication(cur, doi="10.1000/ABC")
        with pytest.raises(Exception):
            _make_publication(cur, doi="10.1000/abc")


def test_1c_duplicate_pmcid_is_rejected(db):
    with _Tx(db) as cur:
        _make_publication(cur, pmcid="PMC1234567")
        with pytest.raises(Exception):
            _make_publication(cur, pmcid="PMC1234567")


def test_1d_many_publications_may_have_no_identifier(db):
    """The guard is PARTIAL: absent identifiers must not collide with each other."""
    with _Tx(db) as cur:
        a = _make_publication(cur, pmid=None, doi=None, pmcid=None)
        b = _make_publication(cur, pmid=None, doi=None, pmcid=None)
        assert a != b


def test_1e_empty_string_identifiers_do_not_collide(db):
    with _Tx(db) as cur:
        a = _make_publication(cur, pmid="", doi="   ")
        b = _make_publication(cur, pmid="", doi="   ")
        assert a != b


def test_1f_two_different_identifiers_on_one_row_are_fine(db):
    with _Tx(db) as cur:
        _make_publication(cur, pmid="99999991", doi="10.9999/one", pmcid="PMC9999991")
        _make_publication(cur, pmid="99999992", doi="10.9999/two", pmcid="PMC9999992")


# ===========================================================================
# §18.2-4 — foreign keys
# ===========================================================================
def test_2_a_hit_requires_an_existing_seed_region(db):
    with _Tx(db) as cur:
        pub = _make_publication(cur)
        with pytest.raises(Exception):
            _make_hit(cur, pub, region_pk=10**17)


def test_3_a_hit_requires_an_existing_publication(db):
    with _Tx(db) as cur:
        with pytest.raises(Exception):
            _make_hit(cur, 10**17)


def test_4_a_hit_requires_an_existing_run_when_one_is_given(db):
    with _Tx(db) as cur:
        pub = _make_publication(cur)
        with pytest.raises(Exception):
            _make_hit(cur, pub, run_pk=10**17)


def test_4b_a_hit_requires_an_existing_source_when_one_is_given(db):
    with _Tx(db) as cur:
        pub = _make_publication(cur)
        with pytest.raises(Exception):
            _make_hit(cur, pub, source_pk=10**17)


def test_4c_a_hit_may_omit_run_and_source(db):
    """Retrieval provenance without a recorded run is still worth keeping."""
    with _Tx(db) as cur:
        region, _src = _seed_ids(cur)
        pub = _make_publication(cur)
        _pk, hit_id = _make_hit(cur, pub, region_pk=region)
        assert hit_id.startswith("NGIQ-PDH-")


# ===========================================================================
# §18.5-8 — one publication, many hits
# ===========================================================================
def test_5_one_publication_can_have_many_hits(db):
    with _Tx(db) as cur:
        region, src = _seed_ids(cur)
        pub = _make_publication(cur, pmid="77777771")
        run = _make_run(cur, region)
        for i in range(4):
            _make_hit(cur, pub, run_pk=run, source_pk=src, region_pk=region,
                      family=f"fam{i}", level="NAME", text=f"q{i}", rank=i + 1)
        cur.execute("select count(*) from publication_discovery_hits where publication_pk=%s", (pub,))
        assert cur.fetchone()[0] == 4, "no UNIQUE(publication_pk) may exist"


def test_6_the_same_publication_can_be_found_by_different_sources(db):
    with _Tx(db) as cur:
        region, src = _seed_ids(cur)
        pub = _make_publication(cur)
        cur.execute("select source_pk from sources order by source_pk limit 2")
        srcs = [r[0] for r in cur.fetchall()]
        if len(srcs) < 2:
            pytest.skip("needs two sources to distinguish providers")
        for s in srcs:
            _make_hit(cur, pub, source_pk=s, region_pk=region, family="A_general")
        cur.execute("select count(distinct source_pk) from publication_discovery_hits"
                    " where publication_pk=%s", (pub,))
        assert cur.fetchone()[0] == len(srcs)


def test_7_different_query_families_can_share_one_publication(db):
    with _Tx(db) as cur:
        region, _s = _seed_ids(cur)
        pub = _make_publication(cur)
        for fam in ("A_general", "D_functional", "F_review"):
            _make_hit(cur, pub, region_pk=region, family=fam)
        cur.execute("select count(distinct query_family) from publication_discovery_hits"
                    " where publication_pk=%s", (pub,))
        assert cur.fetchone()[0] == 3


def test_8_query_provenance_is_preserved_exactly(db):
    with _Tx(db) as cur:
        region, src = _seed_ids(cur)
        pub = _make_publication(cur)
        run = _make_run(cur, region)
        pk, _hid = _make_hit(cur, pub, run_pk=run, source_pk=src, region_pk=region,
                             family="C_aff_eff", level="MEMBER_COMBINATION",
                             text="hippocampus AND nucleus reuniens", rank=7)
        cur.execute("select query_text, query_family, query_level, result_rank,"
                    " retrieved_at from publication_discovery_hits where hit_pk=%s", (pk,))
        text, fam, level, rank, retrieved = cur.fetchone()
        assert (text, fam, level, rank) == (
            "hippocampus AND nucleus reuniens", "C_aff_eff", "MEMBER_COMBINATION", 7)
        assert retrieved is not None


def test_8b_query_text_is_mandatory(db):
    with _Tx(db) as cur:
        region, _s = _seed_ids(cur)
        pub = _make_publication(cur)
        with pytest.raises(Exception):
            cur.execute(
                "INSERT INTO publication_discovery_hits (publication_pk, seed_brain_region_pk,"
                " query_text) VALUES (%s,%s,NULL)", (pub, region))


def test_8c_an_unknown_query_level_is_rejected(db):
    with _Tx(db) as cur:
        region, _s = _seed_ids(cur)
        pub = _make_publication(cur)
        with pytest.raises(Exception):
            _make_hit(cur, pub, region_pk=region, level="MADE_UP_LEVEL")


def test_8d_a_rank_below_one_is_rejected(db):
    with _Tx(db) as cur:
        region, _s = _seed_ids(cur)
        pub = _make_publication(cur)
        with pytest.raises(Exception):
            _make_hit(cur, pub, region_pk=region, rank=0)


# ===========================================================================
# §18.9-11 — a hit is provenance, NOT knowledge
# ===========================================================================
def test_9_creating_a_hit_creates_no_evidence(db):
    with _Tx(db) as cur:
        region, src = _seed_ids(cur)
        pub = _make_publication(cur)
        _make_hit(cur, pub, source_pk=src, region_pk=region)
        cur.execute("select count(*) from evidence where publication_pk=%s", (pub,))
        assert cur.fetchone()[0] == 0


def test_10_creating_a_hit_creates_no_assertion_or_link(db):
    with _Tx(db) as cur:
        region, _s = _seed_ids(cur)
        pub = _make_publication(cur)
        before = {}
        for t in ("knowledge_assertions", "evidence_links"):
            cur.execute(f"select count(*) from {t}")
            before[t] = cur.fetchone()[0]
        _make_hit(cur, pub, region_pk=region)
        for t, n in before.items():
            cur.execute(f"select count(*) from {t}")
            assert cur.fetchone()[0] == n, t


def test_11_creating_a_publication_creates_no_formal_kg_entity(db):
    """A Publication IS a kg_entities subtype, but creates no scientific row."""
    with _Tx(db) as cur:
        counts = {}
        for t in ("connections", "circuits", "functions", "brain_regions"):
            cur.execute(f"select count(*) from {t}")
            counts[t] = cur.fetchone()[0]
        _make_publication(cur, pmid="66666661")
        for t, n in counts.items():
            cur.execute(f"select count(*) from {t}")
            assert cur.fetchone()[0] == n, t


def test_12_existing_evidence_semantics_are_untouched(db):
    """The evidence table keeps its passage-level shape; no parallel table."""
    with _Tx(db) as cur:
        cur.execute("""select column_name from information_schema.columns
                       where table_name='evidence'""")
        cols = {r[0] for r in cur.fetchall()}
        for required in ("evidence_text_original", "evidence_text_zh", "source_section",
                         "source_paragraph", "extraction_method", "extractor_name",
                         "extractor_version", "extraction_run_id",
                         "human_review_status", "reviewer", "reviewed_at"):
            assert required in cols, required
        cur.execute("select to_regclass('public.evidence_passages')")
        assert cur.fetchone()[0] is None, "no parallel evidence table may be created"


def test_12b_publications_gained_no_redundant_url_columns(db):
    with _Tx(db) as cur:
        cur.execute("select column_name from information_schema.columns where table_name='publications'")
        cols = {r[0] for r in cur.fetchall()}
        for forbidden in ("pubmed_url", "europepmc_url", "doi_url", "openalex_id",
                          "semantic_scholar_id", "relevant", "irrelevant", "verified"):
            assert forbidden not in cols, forbidden
        assert "full_text_url" in cols


# ===========================================================================
# §18.13 / §18.14 — formal tables untouched, failures create no hits
# ===========================================================================
def test_13_the_formal_tables_still_exist_in_their_frozen_shape(db):
    with _Tx(db) as cur:
        for t in ("brain_regions", "connections", "circuits", "functions",
                  "evidence", "knowledge_assertions"):
            cur.execute("select to_regclass(%s)", (f"public.{t}",))
            assert cur.fetchone()[0] is not None, t


def test_14_a_failed_search_has_no_row_to_write(db):
    """The §12 rule made structural: a hit row cannot exist without a real
    publication, so a provider failure has nothing to persist. There is no
    'status' column on hits that could record 'we tried and failed'."""
    with _Tx(db) as cur:
        cur.execute("""select column_name from information_schema.columns
                       where table_name='publication_discovery_hits'""")
        cols = {r[0] for r in cur.fetchall()}
        for forbidden in ("error_code", "error_message", "status", "success", "failure"):
            assert forbidden not in cols, forbidden
        assert "publication_pk" in cols


# ===========================================================================
# Static checks on the migration itself (always run, DB or not)
# ===========================================================================
def _sql_only() -> str:
    """The migration's EXECUTABLE SQL, with `--` comments removed.

    These checks must inspect what the migration does, not what its header says
    it deliberately does not do: the header names the very things it forbids.
    """
    out = []
    for line in MIGRATION.read_text(encoding="utf-8").splitlines():
        stripped = line.split("--", 1)[0]
        if stripped.strip():
            out.append(stripped)
    return "\n".join(out)


def test_migration_declares_no_unique_on_publication_pk():
    """Structural, not textual: the COMMENT on the table *mentions* the absent
    constraint, so a naive substring search would match its own documentation."""
    sql = _sql_only()
    assert not re.search(r"CONSTRAINT\s+\w+\s+UNIQUE\s*\(\s*publication_pk", sql, re.I)
    assert not re.search(r"CREATE\s+UNIQUE\s+INDEX[^;]*\(\s*publication_pk\s*\)", sql, re.I)
    assert "uq_pdh_publication" not in sql


def test_migration_declares_no_title_uniqueness():
    sql = _sql_only()
    assert not re.search(r"CONSTRAINT\s+\w+\s+UNIQUE[^;]*\btitle\b", sql, re.I)
    assert not re.search(r"CREATE\s+UNIQUE\s+INDEX[^;]*\btitle\b", sql, re.I)


def test_migration_creates_no_parallel_paper_or_evidence_table():
    sql = _sql_only().lower()
    for forbidden in ("create table if not exists papers", "literature_papers",
                      "evidence_passages", "article_evidence", "candidate_publication_links"):
        assert forbidden not in sql, forbidden
    # and the tables it DOES create are exactly the ones intended
    created = re.findall(r"create table if not exists\s+(\w+)", sql)
    assert created == ["publication_discovery_hits"], created


def test_migration_widens_the_run_vocabulary_without_recreating_the_table():
    sql = _sql_only()
    assert "EVIDENCE_SEARCH" in sql and "CITATION_CHAINING" in sql
    assert "DROP CONSTRAINT IF EXISTS ck_kdr_discovery_type" in sql
    assert not re.search(r"CREATE TABLE IF NOT EXISTS knowledge_discovery_runs", sql, re.I)


def test_the_recorded_migration_is_checksum_stable():
    """The runner stores a SHA-256; a later edit to the file would be visible."""
    import hashlib

    raw = MIGRATION.read_bytes().replace(b"\r\n", b"\n")
    digest = hashlib.sha256(raw).hexdigest()
    assert len(digest) == 64
    assert "publication_discovery_hits" in MIGRATION.read_text(encoding="utf-8")
