"""Gate 7B Phase 4 Circuit-core tests (require live PostgreSQL).

Exercise circuits / circuit_region_memberships / circuit_connection_memberships
against the E2E database (read/write in rolled-back transactions) and compare
production/E2E schema parity. Skip the module when E2E is unreachable.
"""

from __future__ import annotations

import psycopg
import pytest

PROD = "neurographiq_human_brain_v1"
E2E = "neurographiq_human_brain_v1_e2e"

NEW_TABLES = ["circuits", "circuit_region_memberships", "circuit_connection_memberships"]

EXPECTED_TABLES = sorted(
    ["atlases", "brain_region_aggregation_mappings", "brain_region_hierarchy_relations",
     "brain_region_spatial_representations", "brain_regions", "cellular_neural_structures",
     "connection_endpoints", "connection_observations", "connections", "diseases",
     "entity_aliases", "entity_xrefs", "evidence", "external_regions",
     "function_hierarchy_relations", "functions", "genes", "kg_entities",
     "neurobiological_processes", "neurotransmitters", "publications", "receptors",
     "research_studies", "sources", "symptoms"]
    + NEW_TABLES
)

MAPPING_ASSERTION_TABLES = [
    "assertion_evidence_links", "brain_region_spatial_relations",
    "connection_types", "circuit_types", "evidence_types",
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
    pytest.skip("E2E database unreachable; skip Phase 4 tests", allow_module_level=True)


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
    cur.execute(
        "INSERT INTO kg_entities (entity_id, entity_type, name_en, name_zh, source_name_original,"
        " name_en_source, name_zh_source, record_status)"
        " VALUES (%s,%s,%s,%s,%s,'source','translated_human',%s) RETURNING entity_pk",
        (eid, etype, name_en, name_zh, name_en or "Test Original", status),
    )
    return cur.fetchone()[0]


def _mk_region(cur, granularity: str = "G4_MICROSTRUCTURAL_FINE") -> int:
    pk = _mk_entity(cur, "brain_region")
    cur.execute("INSERT INTO brain_regions (entity_pk, granularity_level) VALUES (%s, %s)", (pk, granularity))
    return pk


def _mk_connection(cur) -> int:
    pk = _mk_entity(cur, "connection")
    cur.execute(
        "INSERT INTO connections (entity_pk, connection_class, directionality, derivation_type)"
        " VALUES (%s, 'functional_connectivity', 'non_directional', 'reported')", (pk,),
    )
    return pk


def _mk_circuit(cur, status: str = "active", is_closed_loop=None,
                derivation: str = "reported") -> int:
    pk = _mk_entity(cur, "circuit", status=status)
    cur.execute(
        "INSERT INTO circuits (entity_pk, construction_mode, derivation_type, is_closed_loop)"
        " VALUES (%s, 'composed', %s, %s)", (pk, derivation, is_closed_loop),
    )
    return pk


# ---------------------------------------------------------------------------
# Table set / count / leak
# ---------------------------------------------------------------------------


def _public_tables(conn) -> list[str]:
    cur = conn.cursor()
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
    return [r[0] for r in cur.fetchall()]


def test_phase4_twenty_eight_tables_present():
    conn = _conn(E2E)
    try:
        tables = set(_public_tables(conn))
    finally:
        conn.close()
    # Phase 4 delivered these 28; Phase 5 adds the final 4.
    missing = [t for t in EXPECTED_TABLES if t not in tables]
    assert missing == [], f"missing Phase 4 tables: {missing}"


def test_three_new_tables_exist():
    conn = _conn(E2E)
    try:
        tables = set(_public_tables(conn))
    finally:
        conn.close()
    missing = [t for t in NEW_TABLES if t not in tables]
    assert missing == [], f"missing Phase 4 tables: {missing}"


def test_no_mapping_assertion_leak():
    conn = _conn(E2E)
    try:
        tables = set(_public_tables(conn))
    finally:
        conn.close()
    leaked = [t for t in MAPPING_ASSERTION_TABLES if t in tables]
    assert leaked == [], f"RegionMapping/Assertion tables must not exist: {leaked}"


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
# Circuit shared-PK / entity_type
# ---------------------------------------------------------------------------


def test_circuit_shared_pk_no_second_identity():
    conn = _conn(E2E)
    try:
        cur = conn.cursor()
        cur.execute("SELECT column_name FROM information_schema.columns"
                    " WHERE table_schema='public' AND table_name='circuits'")
        cols = [r[0] for r in cur.fetchall()]
        assert "entity_pk" in cols
        bad = [c for c in cols if c in ("circuit_id", "entity_id", "name_en", "name_zh", "record_status")]
        assert bad == [], f"circuits has duplicated identity fields: {bad}"
    finally:
        conn.close()


def test_circuit_wrong_entity_type_rejected(db):
    cur = db.cursor()
    gene = _mk_entity(cur, "gene")
    cur.execute("INSERT INTO genes (entity_pk, approved_symbol) VALUES (%s, 'APOE')", (gene,))
    with pytest.raises(psycopg.errors.RaiseException):
        cur.execute(
            "INSERT INTO circuits (entity_pk, construction_mode, derivation_type)"
            " VALUES (%s, 'composed', 'reported')", (gene,),
        )


# ---------------------------------------------------------------------------
# Circuit semantics: no closed-loop / cardinality hard constraints
# ---------------------------------------------------------------------------


def test_closed_loop_not_required(db):
    cur = db.cursor()
    c = _mk_circuit(cur, is_closed_loop=False)
    cur.execute("SELECT is_closed_loop FROM circuits WHERE entity_pk=%s", (c,))
    assert cur.fetchone()[0] is False


def test_two_region_circuit_allowed(db):
    cur = db.cursor()
    c = _mk_circuit(cur)
    r1, r2 = _mk_region(cur), _mk_region(cur)
    cur.execute(
        "INSERT INTO circuit_region_memberships (circuit_pk, brain_region_pk) VALUES (%s, %s), (%s, %s)",
        (c, r1, c, r2),
    )
    cur.execute("SELECT count(*) FROM circuit_region_memberships WHERE circuit_pk=%s", (c,))
    assert cur.fetchone()[0] == 2  # 2-region circuit accepted (no >=3 hard constraint)


def test_proposed_incomplete_circuit_saved(db):
    cur = db.cursor()
    c = _mk_circuit(cur, status="proposed")
    # PROPOSED circuit may be saved with NO memberships yet
    cur.execute("SELECT count(*) FROM circuits WHERE entity_pk=%s", (c,))
    assert cur.fetchone()[0] == 1


def test_graph_cycle_does_not_auto_generate_circuit(db):
    cur = db.cursor()
    r1, r2, r3 = _mk_region(cur), _mk_region(cur), _mk_region(cur)
    # a graph cycle A->B, B->C, C->A (as connections)
    for a, b in ((r1, r2), (r2, r3), (r3, r1)):
        conn = _mk_entity(cur, "connection")
        cur.execute(
            "INSERT INTO connections (entity_pk, connection_class, directionality, derivation_type)"
            " VALUES (%s, 'projection', 'directed', 'reported')", (conn,),
        )
        cur.execute(
            "INSERT INTO connection_endpoints (connection_pk, brain_region_pk, endpoint_role)"
            " VALUES (%s, %s, 'source'), (%s, %s, 'target')", (conn, a, conn, b),
        )
    cur.execute("SELECT count(*) FROM circuits")
    assert cur.fetchone()[0] == 0  # graph cycle does NOT auto-create a Circuit


# ---------------------------------------------------------------------------
# circuit_region_memberships
# ---------------------------------------------------------------------------


def test_region_membership_fk(db):
    cur = db.cursor()
    c = _mk_circuit(cur)
    r = _mk_region(cur)
    cur.execute(
        "INSERT INTO circuit_region_memberships (circuit_pk, brain_region_pk, role_en)"
        " VALUES (%s, %s, 'input')", (c, r),
    )
    cur.execute("SELECT count(*) FROM circuit_region_memberships WHERE circuit_pk=%s", (c,))
    assert cur.fetchone()[0] == 1


def test_region_membership_invalid_region_rejected(db):
    cur = db.cursor()
    c = _mk_circuit(cur)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        cur.execute(
            "INSERT INTO circuit_region_memberships (circuit_pk, brain_region_pk) VALUES (%s, 999999999)",
            (c,),
        )


def test_region_membership_duplicate_rejected(db):
    cur = db.cursor()
    c = _mk_circuit(cur)
    r = _mk_region(cur)
    cur.execute(
        "INSERT INTO circuit_region_memberships (circuit_pk, brain_region_pk) VALUES (%s, %s)", (c, r),
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        cur.execute(
            "INSERT INTO circuit_region_memberships (circuit_pk, brain_region_pk) VALUES (%s, %s)", (c, r),
        )


# ---------------------------------------------------------------------------
# circuit_connection_memberships (shared-PK first-class)
# ---------------------------------------------------------------------------


def test_ccm_is_shared_pk_first_class():
    conn = _conn(E2E)
    try:
        cur = conn.cursor()
        cur.execute("SELECT column_name FROM information_schema.columns"
                    " WHERE table_schema='public' AND table_name='circuit_connection_memberships'")
        cols = [r[0] for r in cur.fetchall()]
        assert "entity_pk" in cols  # shared-PK
        assert "membership_id" not in cols  # no second public ID (kg_entities.entity_id owns it)
        # must not copy Connection endpoint/class/directionality truth
        for forbidden in ("connection_class", "directionality", "source_region_pk", "target_region_pk"):
            assert forbidden not in cols, f"CCM must not copy {forbidden}"
    finally:
        conn.close()


def test_ccm_entity_type_mismatch_rejected(db):
    cur = db.cursor()
    c = _mk_circuit(cur)
    conn = _mk_connection(cur)
    gene = _mk_entity(cur, "gene")
    cur.execute("INSERT INTO genes (entity_pk, approved_symbol) VALUES (%s, 'APOE')", (gene,))
    with pytest.raises(psycopg.errors.RaiseException):
        cur.execute(
            "INSERT INTO circuit_connection_memberships (entity_pk, circuit_pk, connection_pk)"
            " VALUES (%s, %s, %s)", (gene, c, conn),
        )


def test_ccm_fk_and_shared_pk(db):
    cur = db.cursor()
    c = _mk_circuit(cur)
    conn = _mk_connection(cur)
    ccmpk = _mk_entity(cur, "circuit_connection_membership")
    cur.execute(
        "INSERT INTO circuit_connection_memberships (entity_pk, circuit_pk, connection_pk, step_order)"
        " VALUES (%s, %s, %s, 1)", (ccmpk, c, conn),
    )
    cur.execute("SELECT count(*) FROM circuit_connection_memberships WHERE entity_pk=%s", (ccmpk,))
    assert cur.fetchone()[0] == 1
    cur.execute("SELECT entity_id FROM kg_entities WHERE entity_pk=%s", (ccmpk,))
    assert cur.fetchone()[0].startswith("NGIQ-CCM-")


def test_ccm_invalid_connection_rejected(db):
    cur = db.cursor()
    c = _mk_circuit(cur)
    ccmpk = _mk_entity(cur, "circuit_connection_membership")
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        cur.execute(
            "INSERT INTO circuit_connection_memberships (entity_pk, circuit_pk, connection_pk)"
            " VALUES (%s, %s, 999999999)", (ccmpk, c),
        )


def test_no_second_circuit_connection_table():
    conn = _conn(E2E)
    try:
        cur = conn.cursor()
        for t in ("circuit_connections",):
            cur.execute("SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename=%s", (t,))
            assert cur.fetchone() is None, f"{t} must not exist (hasConnection is derived)"
    finally:
        conn.close()
