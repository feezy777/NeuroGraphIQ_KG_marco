"""Gate 7B Phase 2A core-scientific-entity tests (require live PostgreSQL).

Exercise the 9 shared-PK subtype tables against the E2E database (read/write in
rolled-back transactions) and compare production/E2E schema parity. Skip the
module when the E2E database is unreachable.
"""

from __future__ import annotations

import psycopg
import pytest

PROD = "neurographiq_human_brain_v1"
E2E = "neurographiq_human_brain_v1_e2e"

# subtype table -> required kg_entities.entity_type
SUBTYPES = {
    "brain_regions": "brain_region",
    "cellular_neural_structures": "cellular_neural_structure",
    "neurobiological_processes": "neurobiological_process",
    "functions": "function",
    "neurotransmitters": "neurotransmitter",
    "receptors": "receptor",
    "genes": "gene",
    "diseases": "disease",
    "symptoms": "symptom",
}

EXPECTED_TABLES = sorted(
    ["kg_entities", "entity_aliases", "entity_xrefs", "sources"] + list(SUBTYPES)
)

PHASE3B_TABLES = [
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
    pytest.skip("E2E database unreachable; skip Phase 2A tests", allow_module_level=True)


@pytest.fixture()
def db():
    conn = _conn(E2E)
    yield conn
    conn.rollback()
    conn.close()


def _mk_entity(cur, etype: str, name_en: str = "Test EN", name_zh: str = "测试") -> int:
    """Create an ACTIVE kg_entities row of the given entity_type; return entity_pk."""
    cur.execute("SELECT infra.next_ngiq_id(%s)", (etype,))
    eid = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO kg_entities (entity_id, entity_type, name_en, name_zh,"
        " name_en_source, name_zh_source, record_status) VALUES (%s,%s,%s,%s,'source','translated_human','active')"
        " RETURNING entity_pk",
        (eid, etype, name_en, name_zh),
    )
    return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Table set / count / no Phase 2B leak
# ---------------------------------------------------------------------------


def _public_tables(conn) -> list[str]:
    cur = conn.cursor()
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
    return [r[0] for r in cur.fetchall()]


def test_phase2a_thirteen_tables_present():
    conn = _conn(E2E)
    try:
        tables = set(_public_tables(conn))
    finally:
        conn.close()
    # Phase 2A delivered these 13; later phases legitimately add more tables.
    missing = [t for t in EXPECTED_TABLES if t not in tables]
    assert missing == [], f"missing Phase 2A tables: {missing}"


def test_no_phase3_table_leak():
    conn = _conn(E2E)
    try:
        tables = set(_public_tables(conn))
    finally:
        conn.close()
    leaked = [t for t in PHASE3B_TABLES if t in tables]
    assert leaked == [], f"Phase 3B+ tables must not exist: {leaked}"


def test_all_nine_subtype_tables_exist():
    conn = _conn(E2E)
    try:
        tables = set(_public_tables(conn))
    finally:
        conn.close()
    missing = [t for t in SUBTYPES if t not in tables]
    assert missing == [], f"missing subtype tables: {missing}"


# ---------------------------------------------------------------------------
# Schema parity (production == E2E)
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
# Shared-PK structure
# ---------------------------------------------------------------------------


def test_subtype_tables_are_shared_pk_no_second_identity():
    conn = _conn(E2E)
    try:
        cur = conn.cursor()
        for table, etype in SUBTYPES.items():
            cur.execute(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema='public' AND table_name=%s", (table,),
            )
            cols = [r[0] for r in cur.fetchall()]
            assert "entity_pk" in cols, f"{table} must have entity_pk"
            # no second public ID / own serial PK / duplicated identity fields
            bad = [c for c in cols if c in (f"{table[:-1]}_id", f"{table[:-1]}_pk", "name_en", "name_zh", "entity_id")]
            assert bad == [], f"{table} has duplicated identity fields: {bad}"
    finally:
        conn.close()


def test_shared_pk_fk_accepts_existing_entity(db):
    cur = db.cursor()
    pk = _mk_entity(cur, "brain_region")
    cur.execute("INSERT INTO brain_regions (entity_pk) VALUES (%s)", (pk,))
    cur.execute("SELECT count(*) FROM brain_regions WHERE entity_pk=%s", (pk,))
    assert cur.fetchone()[0] == 1


def test_orphan_subtype_rejected(db):
    cur = db.cursor()
    with pytest.raises(psycopg.errors.RaiseException):
        cur.execute("INSERT INTO brain_regions (entity_pk) VALUES (999999999)")


def test_correct_entity_type_inserts_for_all_subtypes(db):
    cur = db.cursor()
    for table, etype in SUBTYPES.items():
        pk = _mk_entity(cur, etype)
        extra = ""
        if table == "functions":
            extra = ", function_category"
            values = ", 'general'"
        elif table == "genes":
            extra = ", approved_symbol"
            values = ", 'TEST'"
        else:
            values = ""
        cur.execute(f"INSERT INTO {table} (entity_pk{extra}) VALUES (%s{values})", (pk,))
        cur.execute(f"SELECT count(*) FROM {table} WHERE entity_pk=%s", (pk,))
        assert cur.fetchone()[0] == 1, table


def test_wrong_entity_type_rejected(db):
    cur = db.cursor()
    pk = _mk_entity(cur, "gene")
    with pytest.raises(psycopg.errors.RaiseException):
        cur.execute("INSERT INTO brain_regions (entity_pk) VALUES (%s)", (pk,))


# ---------------------------------------------------------------------------
# BrainRegion granularity
# ---------------------------------------------------------------------------


def test_brain_region_valid_granularity(db):
    cur = db.cursor()
    pk = _mk_entity(cur, "brain_region")
    cur.execute(
        "INSERT INTO brain_regions (entity_pk, granularity_level, hemisphere)"
        " VALUES (%s, 'G1_MACRO', 'left')", (pk,),
    )
    cur.execute("SELECT granularity_level FROM brain_regions WHERE entity_pk=%s", (pk,))
    assert cur.fetchone()[0] == "G1_MACRO"


def test_brain_region_invalid_granularity_rejected(db):
    cur = db.cursor()
    pk = _mk_entity(cur, "brain_region")
    with pytest.raises(psycopg.errors.CheckViolation):
        cur.execute("INSERT INTO brain_regions (entity_pk, granularity_level) VALUES (%s, 'G5_BOGUS')", (pk,))


def test_brain_region_invalid_hemisphere_rejected(db):
    cur = db.cursor()
    pk = _mk_entity(cur, "brain_region")
    with pytest.raises(psycopg.errors.CheckViolation):
        cur.execute("INSERT INTO brain_regions (entity_pk, hemisphere) VALUES (%s, 'north')", (pk,))


# ---------------------------------------------------------------------------
# FK delete policy
# ---------------------------------------------------------------------------


def test_subtype_delete_keeps_kg_entity(db):
    cur = db.cursor()
    pk = _mk_entity(cur, "function")
    cur.execute("INSERT INTO functions (entity_pk, function_category) VALUES (%s, 'cognitive')", (pk,))
    cur.execute("DELETE FROM functions WHERE entity_pk=%s", (pk,))
    cur.execute("SELECT count(*) FROM kg_entities WHERE entity_pk=%s", (pk,))
    assert cur.fetchone()[0] == 1  # deleting subtype must NOT delete the canonical entity


def test_delete_entity_with_subtype_is_restricted(db):
    cur = db.cursor()
    pk = _mk_entity(cur, "gene")
    cur.execute("INSERT INTO genes (entity_pk, approved_symbol) VALUES (%s, 'APOE')", (pk,))
    with pytest.raises(psycopg.errors.RestrictViolation):
        cur.execute("DELETE FROM kg_entities WHERE entity_pk=%s", (pk,))


# ---------------------------------------------------------------------------
# Centralized guard function exists
# ---------------------------------------------------------------------------


def test_centralized_entity_type_guard_exists():
    conn = _conn(E2E)
    try:
        cur = conn.cursor()
        cur.execute("SELECT pg_get_functiondef('infra.assert_entity_type()'::regprocedure)")
        src = cur.fetchone()[0]
    finally:
        conn.close()
    assert "RAISE EXCEPTION" in src
    assert "TG_ARGV" in src
