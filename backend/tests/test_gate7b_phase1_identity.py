"""Gate 7B Phase 1 identity-foundation tests (require live PostgreSQL).

Exercise the frozen 4-table Identity Foundation against the E2E database
(read/write identity + constraint tests) and compare production/E2E schema
parity (read-only). Write tests run inside a transaction that is rolled back,
so no test rows persist (sequence advances are permanent by design).

Skip the whole module when the E2E database is unreachable.
"""

from __future__ import annotations

import re

import psycopg
import pytest

PROD = "neurographiq_human_brain_v1"
E2E = "neurographiq_human_brain_v1_e2e"

FOUR_TABLES = ["entity_aliases", "entity_xrefs", "kg_entities", "sources"]


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
    pytest.skip("E2E database unreachable; skip Phase 1 identity tests", allow_module_level=True)


@pytest.fixture()
def db():
    """A rolled-back E2E connection: writes are discarded after each test."""
    conn = _conn(E2E)
    yield conn
    conn.rollback()
    conn.close()


def _insert_entity(cur, *, entity_type="brain_region", name_en="Test Region",
                   name_zh="测试区域", source_name_original="Test Region (source)",
                   record_status="proposed", name_en_source=None, name_zh_source=None,
                   entity_id=None) -> int:
    if entity_id is None:
        cur.execute("SELECT infra.next_ngiq_id(%s)", (entity_type,))
        entity_id = cur.fetchone()[0]
    cur.execute(
        """
        INSERT INTO kg_entities
            (entity_id, entity_type, name_en, name_zh, source_name_original,
             name_en_source, name_zh_source, record_status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING entity_pk
        """,
        (entity_id, entity_type, name_en, name_zh, source_name_original,
         name_en_source, name_zh_source, record_status),
    )
    return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Schema drift (production == E2E)
# ---------------------------------------------------------------------------


def _schema_signature(conn: psycopg.Connection, tables: list[str]) -> dict:
    sig: dict = {}
    cur = conn.cursor()
    for t in tables:
        cur.execute(
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s
            ORDER BY ordinal_position
            """, (t,),
        )
        cols = [(r[0], r[1], r[2], r[3]) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT con.contype, con.conname, pg_get_constraintdef(con.oid)
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            JOIN pg_namespace ns ON ns.oid = rel.relnamespace
            WHERE ns.nspname='public' AND rel.relname=%s
            ORDER BY con.contype, con.conname
            """, (t,),
        )
        cons = [(r[0], r[1], r[2]) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT indexname, indexdef FROM pg_indexes
            WHERE schemaname='public' AND tablename=%s
            ORDER BY indexname
            """, (t,),
        )
        idx = [(r[0], r[1]) for r in cur.fetchall()]

        sig[t] = {"columns": cols, "constraints": cons, "indexes": idx}
    return sig


def test_production_e2e_schema_parity():
    prod, e2e = _conn(PROD), _conn(E2E)
    try:
        sp = _schema_signature(prod, FOUR_TABLES)
        se = _schema_signature(e2e, FOUR_TABLES)
    finally:
        prod.close()
        e2e.close()
    assert sp == se


def test_table_count_is_exactly_four():
    conn = _conn(E2E)
    try:
        cur = conn.cursor()
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
        names = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()
    assert names == FOUR_TABLES
    assert set(names) == {"kg_entities", "entity_aliases", "entity_xrefs", "sources"}


# ---------------------------------------------------------------------------
# ID generation
# ---------------------------------------------------------------------------


def test_ngiq_id_format_is_8_digit():
    conn = _conn(E2E)
    try:
        cur = conn.cursor()
        cur.execute("SELECT infra.next_ngiq_id('source')")
        sid = cur.fetchone()[0]
        cur.execute("SELECT infra.next_ngiq_id('brain_region')")
        rid = cur.fetchone()[0]
        cur.execute("SELECT infra.next_ngiq_id('alias')")
        aid = cur.fetchone()[0]
    finally:
        conn.rollback()
        conn.close()
    assert re.fullmatch(r"NGIQ-SRC-\d{8}", sid)
    assert re.fullmatch(r"NGIQ-BR-\d{8}", rid)
    assert re.fullmatch(r"NGIQ-ALS-\d{8}", aid)


def test_ngiq_id_unknown_type_fails_closed():
    conn = _conn(E2E)
    try:
        cur = conn.cursor()
        with pytest.raises(psycopg.errors.RaiseException):
            cur.execute("SELECT infra.next_ngiq_id('not_a_registry_type')")
    finally:
        conn.rollback()
        conn.close()


def test_ngiq_id_capacity_guard_present():
    conn = _conn(E2E)
    try:
        cur = conn.cursor()
        cur.execute("SELECT pg_get_functiondef('infra.next_ngiq_id(text)'::regprocedure)")
        src = cur.fetchone()[0]
    finally:
        conn.close()
    assert "99999999" in src  # 8-digit capacity guard present (fail closed on 9 digits)


def test_sequence_not_max_plus_one():
    conn = _conn(E2E)
    try:
        cur = conn.cursor()
        cur.execute("SELECT infra.next_ngiq_id('source')")
        a = cur.fetchone()[0]
        cur.execute("SELECT infra.next_ngiq_id('source')")
        b = cur.fetchone()[0]
    finally:
        conn.rollback()
        conn.close()
    assert a != b  # consecutive allocations are distinct (sequence, not MAX+1)


def test_ngiq_id_two_connections_distinct():
    c1, c2 = _conn(E2E), _conn(E2E)
    try:
        cur1, cur2 = c1.cursor(), c2.cursor()
        cur1.execute("SELECT infra.next_ngiq_id('source')")
        cur2.execute("SELECT infra.next_ngiq_id('source')")
        v1, v2 = cur1.fetchone()[0], cur2.fetchone()[0]
    finally:
        c1.rollback(); c2.rollback(); c1.close(); c2.close()
    assert v1 != v2


# ---------------------------------------------------------------------------
# kg_entities constraints
# ---------------------------------------------------------------------------


def test_create_proposed_single_language_entity(db):
    cur = db.cursor()
    pk = _insert_entity(cur, name_en="Hippocampus", name_zh=None,
                        source_name_original="Hippocampus", record_status="proposed")
    assert pk is not None
    cur.execute("SELECT entity_id, entity_type FROM kg_entities WHERE entity_pk=%s", (pk,))
    row = cur.fetchone()
    assert row[1] == "brain_region"
    assert row[0].startswith("NGIQ-BR-")


def test_entity_id_unique(db):
    cur = db.cursor()
    cur.execute("SELECT infra.next_ngiq_id('source')")
    sid = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO sources (source_id, name_en, name_zh, source_type, record_status) "
        "VALUES (%s, 'T', 'T', 'atlas', 'active')", (sid,),
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        cur.execute(
            "INSERT INTO sources (source_id, name_en, name_zh, source_type, record_status) "
            "VALUES (%s, 'T2', 'T2', 'database', 'active')", (sid,),
        )


def test_shared_pk_is_global_serial(db):
    cur = db.cursor()
    p1 = _insert_entity(cur, entity_type="brain_region", record_status="active",
                        name_en_source="source", name_zh_source="translated_human")
    p2 = _insert_entity(cur, entity_type="gene", name_en="APOE", name_zh="载脂蛋白E",
                        record_status="active",
                        name_en_source="source", name_zh_source="translated_human")
    assert p1 != p2  # entity_pk is a single global sequence, not per-type


def test_unknown_entity_type_rejected(db):
    cur = db.cursor()
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_entity(cur, entity_type="knowledge_assertion", entity_id="NGIQ-X-00000001")


def test_record_status_vocabulary(db):
    cur = db.cursor()
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_entity(cur, record_status="enabled", entity_id="NGIQ-X-00000002")


def test_active_requires_bilingual(db):
    cur = db.cursor()
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_entity(cur, record_status="active", name_zh=None,
                       name_en_source="source", name_zh_source="translated_human",
                       entity_id="NGIQ-X-00000003")


def test_active_requires_name_en(db):
    cur = db.cursor()
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_entity(cur, record_status="active", name_en=None, name_zh="海马",
                       name_en_source="source", name_zh_source="translated_human",
                       entity_id="NGIQ-X-00000030")


def test_proposed_chinese_only_name_ok(db):
    """PROPOSED may lack name_en when name_zh + source_name_original are present."""
    cur = db.cursor()
    pk = _insert_entity(cur, record_status="proposed", name_en=None, name_zh="海马",
                        source_name_original="Hippocampus")
    assert pk is not None


def test_proposed_requires_at_least_one_name(db):
    cur = db.cursor()
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_entity(cur, record_status="proposed", name_en=None, name_zh=None,
                       source_name_original="Hippocampus", entity_id="NGIQ-X-00000031")


def test_source_unknown_cannot_be_active(db):
    cur = db.cursor()
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_entity(cur, record_status="active", name_zh="测试",
                       name_en_source="unknown", name_zh_source="unknown",
                       entity_id="NGIQ-X-00000004")


def test_proposed_requires_source_name(db):
    cur = db.cursor()
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_entity(cur, record_status="proposed", source_name_original=None,
                       name_zh=None, entity_id="NGIQ-X-00000005")


# ---------------------------------------------------------------------------
# entity_aliases
# ---------------------------------------------------------------------------


def test_alias_fk_valid(db):
    cur = db.cursor()
    pk = _insert_entity(cur)
    cur.execute(
        "INSERT INTO entity_aliases (alias_id, entity_pk, alias_text, alias_type) "
        "VALUES ('NGIQ-ALS-00000001', %s, 'hippocampal formation', 'exact')", (pk,),
    )
    cur.execute("SELECT count(*) FROM entity_aliases WHERE entity_pk=%s", (pk,))
    assert cur.fetchone()[0] == 1


def test_alias_invalid_entity_pk_rejected(db):
    cur = db.cursor()
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        cur.execute(
            "INSERT INTO entity_aliases (alias_id, entity_pk, alias_text, alias_type) "
            "VALUES ('NGIQ-ALS-00000002', 999999999, 'bogus', 'exact')"
        )


# ---------------------------------------------------------------------------
# entity_xrefs
# ---------------------------------------------------------------------------


def test_xref_fk_valid(db):
    cur = db.cursor()
    pk = _insert_entity(cur)
    cur.execute(
        "INSERT INTO entity_xrefs (xref_id, entity_pk, source_database, external_id, match_type) "
        "VALUES ('NGIQ-XRF-00000001', %s, 'HGNC', 'APOE', 'exact')", (pk,),
    )
    cur.execute("SELECT count(*) FROM entity_xrefs WHERE entity_pk=%s", (pk,))
    assert cur.fetchone()[0] == 1


def test_xref_duplicate_resolved_rejected_unresolved_allowed(db):
    cur = db.cursor()
    pk = _insert_entity(cur)
    cur.execute(
        "INSERT INTO entity_xrefs (xref_id, entity_pk, source_database, external_id, match_type) "
        "VALUES ('NGIQ-XRF-00000010', %s, 'MONDO', '12345', 'exact')", (pk,),
    )
    # resolved duplicate -> blocked
    cur.execute("SAVEPOINT sp_dup")
    with pytest.raises(psycopg.errors.UniqueViolation):
        cur.execute(
            "INSERT INTO entity_xrefs (xref_id, entity_pk, source_database, external_id, match_type) "
            "VALUES ('NGIQ-XRF-00000011', %s, 'MONDO', '12345', 'close')", (pk,),
        )
    cur.execute("ROLLBACK TO SAVEPOINT sp_dup")
    # unresolved duplicates -> allowed
    cur.execute(
        "INSERT INTO entity_xrefs (xref_id, entity_pk, source_database, external_id, match_type) "
        "VALUES ('NGIQ-XRF-00000012', %s, 'MONDO', '99999', 'unresolved')", (pk,),
    )
    cur.execute(
        "INSERT INTO entity_xrefs (xref_id, entity_pk, source_database, external_id, match_type) "
        "VALUES ('NGIQ-XRF-00000013', %s, 'MONDO', '99999', 'unresolved')", (pk,),
    )


# ---------------------------------------------------------------------------
# sources
# ---------------------------------------------------------------------------


def test_scientific_source_valid(db):
    cur = db.cursor()
    cur.execute("SELECT infra.next_ngiq_id('source')")
    sid = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO sources (source_id, name_en, name_zh, source_type, record_status) "
        "VALUES (%s, 'Julich-Brain', '尤利希脑图谱', 'atlas', 'active')", (sid,),
    )


def test_llm_not_a_scientific_source(db):
    cur = db.cursor()
    with pytest.raises(psycopg.errors.CheckViolation):
        cur.execute(
            "INSERT INTO sources (source_id, name_en, name_zh, source_type, record_status) "
            "VALUES ('NGIQ-SRC-00000099', 'DeepSeek', '深度求索', 'llm', 'active')"
        )


# ---------------------------------------------------------------------------
# FK delete policy
# ---------------------------------------------------------------------------


def test_delete_entity_with_alias_is_restricted(db):
    cur = db.cursor()
    pk = _insert_entity(cur)
    cur.execute(
        "INSERT INTO entity_aliases (alias_id, entity_pk, alias_text, alias_type) "
        "VALUES ('NGIQ-ALS-00000050', %s, 'alias', 'exact')", (pk,),
    )
    with pytest.raises(psycopg.errors.RestrictViolation):
        cur.execute("DELETE FROM kg_entities WHERE entity_pk=%s", (pk,))
