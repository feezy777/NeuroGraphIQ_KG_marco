"""Gate 7B Phase 2B evidence/atlas-entity tests (require live PostgreSQL).

Exercise the 5 shared-PK subtype tables against the E2E database (read/write in
rolled-back transactions) and compare production/E2E schema parity. Skip the
module when the E2E database is unreachable.
"""

from __future__ import annotations

import psycopg
import pytest

PROD = "neurographiq_human_brain_v1"
E2E = "neurographiq_human_brain_v1_e2e"

# new subtype table -> required kg_entities.entity_type
NEW_SUBTYPES = {
    "research_studies": "research_study",
    "publications": "publication",
    "evidence": "evidence",
    "atlases": "atlas",
    "external_regions": "external_region",
}

# the NGIQ public-ID column that each subtype must NOT carry (kg_entities owns it)
NGIQ_ID_COLUMNS = {
    "research_studies": "research_study_id",
    "publications": "publication_id",
    "evidence": "evidence_id",
    "atlases": "atlas_id",
    "external_regions": "external_region_id",
}

EXPECTED_TABLES = sorted(
    ["kg_entities", "entity_aliases", "entity_xrefs", "sources"]
    + ["brain_regions", "cellular_neural_structures", "neurobiological_processes",
       "functions", "neurotransmitters", "receptors", "genes", "diseases", "symptoms"]
    + list(NEW_SUBTYPES)
)

PHASE3_TABLES = [
    "brain_region_hierarchy_relations", "function_hierarchy_relations",
    "brain_region_spatial_representations", "brain_region_aggregation_mappings",
    "connections", "connection_endpoints", "connection_observations",
    "circuits", "circuit_region_memberships", "circuit_connection_memberships",
    "region_mappings", "relation_definitions", "knowledge_assertions", "evidence_links",
]


def _conn(db: str = E2E) -> psycopg.Connection:
    return psycopg.connect(
        host="127.0.0.1", port=5432, user="postgres",
        password="postgres", dbname=db, autocommit=False,
    )


def _reachable() -> bool:
    try:
        _conn(E2E).close()
        return True
    except psycopg.OperationalError:
        return False


if not _reachable():
    pytest.skip("E2E database unreachable; skip Phase 2B tests", allow_module_level=True)


@pytest.fixture()
def db():
    conn = _conn(E2E)
    yield conn
    conn.rollback()
    conn.close()


def _mk_entity(cur, etype: str, name_en: str = "Test", name_zh: str = "测试",
               status: str = "active") -> int:
    cur.execute("SELECT infra.next_ngiq_id(%s)", (etype,))
    eid = cur.fetchone()[0]
    # PROPOSED requires source_name_original (frozen §F); provide it always.
    cur.execute(
        "INSERT INTO kg_entities (entity_id, entity_type, name_en, name_zh, source_name_original,"
        " name_en_source, name_zh_source, record_status)"
        " VALUES (%s,%s,%s,%s,%s,'source','translated_human',%s) RETURNING entity_pk",
        (eid, etype, name_en, name_zh, name_en or "Test Original", status),
    )
    return cur.fetchone()[0]


def _mk_source(cur, name: str = "Test Source") -> int:
    cur.execute("SELECT infra.next_ngiq_id('source')")
    sid = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO sources (source_id, name_en, name_zh, source_type, record_status)"
        " VALUES (%s,%s,'测试','atlas','active') RETURNING source_pk", (sid, name),
    )
    return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Table set / count / no Phase 3 leak
# ---------------------------------------------------------------------------


def _public_tables(conn) -> list[str]:
    cur = conn.cursor()
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
    return [r[0] for r in cur.fetchall()]


def test_table_count_is_eighteen():
    conn = _conn(E2E)
    try:
        tables = _public_tables(conn)
    finally:
        conn.close()
    assert tables == EXPECTED_TABLES
    assert len(tables) == 18


def test_five_new_tables_exist():
    conn = _conn(E2E)
    try:
        tables = set(_public_tables(conn))
    finally:
        conn.close()
    missing = [t for t in NEW_SUBTYPES if t not in tables]
    assert missing == [], f"missing Phase 2B tables: {missing}"


def test_no_phase3_table_leak():
    conn = _conn(E2E)
    try:
        tables = set(_public_tables(conn))
    finally:
        conn.close()
    leaked = [t for t in PHASE3_TABLES if t in tables]
    assert leaked == [], f"Phase 3+ tables must not exist: {leaked}"


# ---------------------------------------------------------------------------
# Schema parity
# ---------------------------------------------------------------------------


def _schema_signature(conn, tables: list[str]) -> dict:
    sig = {}
    cur = conn.cursor()
    for t in tables:
        cur.execute(
            "SELECT column_name, data_type, is_nullable, column_default"
            " FROM information_schema.columns WHERE table_schema='public' AND table_name=%s"
            " ORDER BY ordinal_position", (t,),
        )
        cols = [tuple(r) for r in cur.fetchall()]
        cur.execute(
            "SELECT con.contype, con.conname, pg_get_constraintdef(con.oid)"
            " FROM pg_constraint con JOIN pg_class rel ON rel.oid=con.conrelid"
            " JOIN pg_namespace ns ON ns.oid=rel.relnamespace"
            " WHERE ns.nspname='public' AND rel.relname=%s ORDER BY con.contype, con.conname", (t,),
        )
        cons = [tuple(r) for r in cur.fetchall()]
        cur.execute(
            "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname='public'"
            " AND tablename=%s ORDER BY indexname", (t,),
        )
        idx = [tuple(r) for r in cur.fetchall()]
        sig[t] = {"columns": cols, "constraints": cons, "indexes": idx}
    return sig


def test_production_e2e_schema_parity():
    prod, e2e = _conn(PROD), _conn(E2E)
    try:
        sp = _schema_signature(prod, EXPECTED_TABLES)
        se = _schema_signature(e2e, EXPECTED_TABLES)
    finally:
        prod.close()
        e2e.close()
    assert sp == se


# ---------------------------------------------------------------------------
# Shared-PK / entity_type
# ---------------------------------------------------------------------------


def test_five_tables_shared_pk_no_second_identity():
    conn = _conn(E2E)
    try:
        cur = conn.cursor()
        for table, etype in NEW_SUBTYPES.items():
            cur.execute(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema='public' AND table_name=%s", (table,),
            )
            cols = [r[0] for r in cur.fetchall()]
            assert "entity_pk" in cols, f"{table} must have entity_pk"
            bad = [c for c in cols if c in (NGIQ_ID_COLUMNS[table], "entity_id", "name_en", "name_zh")]
            assert bad == [], f"{table} has duplicated identity fields: {bad}"
    finally:
        conn.close()


def test_correct_entity_type_inserts(db):
    cur = db.cursor()
    for table, etype in NEW_SUBTYPES.items():
        pk = _mk_entity(cur, etype)
        if table == "external_regions":
            apk = _mk_entity(cur, "atlas")
            cur.execute("INSERT INTO atlases (entity_pk) VALUES (%s)", (apk,))
            cur.execute("INSERT INTO external_regions (entity_pk, atlas_pk) VALUES (%s, %s)", (pk, apk))
        elif table == "evidence":
            ppk = _mk_entity(cur, "publication")
            cur.execute("INSERT INTO publications (entity_pk) VALUES (%s)", (ppk,))
            cur.execute("INSERT INTO evidence (entity_pk, publication_pk) VALUES (%s, %s)", (pk, ppk))
        else:
            cur.execute(f"INSERT INTO {table} (entity_pk) VALUES (%s)", (pk,))
        cur.execute(f"SELECT count(*) FROM {table} WHERE entity_pk=%s", (pk,))
        assert cur.fetchone()[0] == 1, table


def test_wrong_entity_type_rejected(db):
    cur = db.cursor()
    pk = _mk_entity(cur, "gene")
    with pytest.raises(psycopg.errors.RaiseException):
        cur.execute("INSERT INTO publications (entity_pk) VALUES (%s)", (pk,))


# ---------------------------------------------------------------------------
# Evidence source completeness
# ---------------------------------------------------------------------------


def test_active_evidence_no_source_rejected(db):
    cur = db.cursor()
    pk = _mk_entity(cur, "evidence")
    with pytest.raises(psycopg.errors.RaiseException):
        cur.execute("INSERT INTO evidence (entity_pk) VALUES (%s)", (pk,))


def test_active_evidence_only_study_rejected(db):
    cur = db.cursor()
    epk = _mk_entity(cur, "evidence")
    spk = _mk_entity(cur, "research_study")
    cur.execute("INSERT INTO research_studies (entity_pk) VALUES (%s)", (spk,))
    with pytest.raises(psycopg.errors.RaiseException):
        cur.execute("INSERT INTO evidence (entity_pk, study_pk) VALUES (%s, %s)", (epk, spk))


def test_active_evidence_with_publication_allowed(db):
    cur = db.cursor()
    epk = _mk_entity(cur, "evidence")
    ppk = _mk_entity(cur, "publication")
    cur.execute("INSERT INTO publications (entity_pk) VALUES (%s)", (ppk,))
    cur.execute("INSERT INTO evidence (entity_pk, publication_pk) VALUES (%s, %s)", (epk, ppk))
    cur.execute("SELECT count(*) FROM evidence WHERE entity_pk=%s", (epk,))
    assert cur.fetchone()[0] == 1


def test_active_evidence_with_scientific_source_allowed(db):
    cur = db.cursor()
    epk = _mk_entity(cur, "evidence")
    src = _mk_source(cur)
    cur.execute("INSERT INTO evidence (entity_pk, scientific_source_pk) VALUES (%s, %s)", (epk, src))
    cur.execute("SELECT count(*) FROM evidence WHERE entity_pk=%s", (epk,))
    assert cur.fetchone()[0] == 1


def test_proposed_evidence_without_source_allowed(db):
    """PROPOSED evidence may defer publication/source resolution (provenance kept)."""
    cur = db.cursor()
    pk = _mk_entity(cur, "evidence", status="proposed")
    cur.execute("INSERT INTO evidence (entity_pk, extractor_name, extraction_run_id)"
                " VALUES (%s, 'DeepSeek', 'run-1')", (pk,))
    cur.execute("SELECT count(*) FROM evidence WHERE entity_pk=%s", (pk,))
    assert cur.fetchone()[0] == 1


def test_evidence_scientific_source_fk_enforced(db):
    cur = db.cursor()
    pk = _mk_entity(cur, "evidence")
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        cur.execute("INSERT INTO evidence (entity_pk, scientific_source_pk) VALUES (%s, 999999999)", (pk,))


# ---------------------------------------------------------------------------
# ExternalRegion / BrainRegion separation + granularity
# ---------------------------------------------------------------------------


def test_external_region_not_mergeable_into_brain_region(db):
    cur = db.cursor()
    apk = _mk_entity(cur, "atlas")
    cur.execute("INSERT INTO atlases (entity_pk) VALUES (%s)", (apk,))
    xpk = _mk_entity(cur, "external_region")
    cur.execute("INSERT INTO external_regions (entity_pk, atlas_pk) VALUES (%s, %s)", (xpk, apk))
    # an external_region entity must NOT be insertable into brain_regions (type guard)
    with pytest.raises(psycopg.errors.RaiseException):
        cur.execute("INSERT INTO brain_regions (entity_pk) VALUES (%s)", (xpk,))


def test_external_region_invalid_granularity_rejected(db):
    cur = db.cursor()
    apk = _mk_entity(cur, "atlas")
    cur.execute("INSERT INTO atlases (entity_pk) VALUES (%s)", (apk,))
    xpk = _mk_entity(cur, "external_region")
    with pytest.raises(psycopg.errors.CheckViolation):
        cur.execute(
            "INSERT INTO external_regions (entity_pk, atlas_pk, granularity_level)"
            " VALUES (%s, %s, 'G5_BOGUS')", (xpk, apk),
        )


def test_atlas_is_not_granularity(db):
    """atlases table must not carry a granularity_level column (Atlas != granularity)."""
    conn = _conn(E2E)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema='public' AND table_name='atlases' AND column_name LIKE 'granularity%'"
        )
        assert cur.fetchall() == []
    finally:
        conn.close()
