"""Gate 7B Phase 3B Connection-core tests (require live PostgreSQL).

Exercise connections / connection_endpoints / connection_observations against the
E2E database (read/write in rolled-back transactions) and compare production/E2E
schema parity. Skip the module when the E2E database is unreachable.
"""

from __future__ import annotations

import psycopg
import pytest

from _agg_review_divergence import strip_agg_review_divergence

PROD = "neurographiq_human_brain_v1"
E2E = "neurographiq_human_brain_v1_e2e"

NEW_TABLES = ["connections", "connection_endpoints", "connection_observations"]

EXPECTED_TABLES = sorted(
    ["atlases", "brain_region_aggregation_mappings", "brain_region_hierarchy_relations",
     "brain_region_spatial_representations", "brain_regions", "cellular_neural_structures",
     "diseases", "entity_aliases", "entity_xrefs", "evidence", "external_regions",
     "function_hierarchy_relations", "functions", "genes", "kg_entities",
     "neurobiological_processes", "neurotransmitters", "publications", "receptors",
     "research_studies", "sources", "symptoms"]
    + NEW_TABLES
)

CIRCUIT_PLUS_TABLES = [
    "assertion_evidence_links", "brain_region_spatial_relations",
    "connection_types", "circuit_types", "evidence_types",
]

DIRECT_EDGE_TABLES = [
    "brain_region_direct_connections", "projects_to", "structural_edges", "functional_edges",
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
    pytest.skip("E2E database unreachable; skip Phase 3B tests", allow_module_level=True)


@pytest.fixture()
def db():
    conn = _conn(E2E)
    yield conn
    conn.rollback()
    conn.close()


def _mk_entity(cur, etype: str, name_en: str = "Test", name_zh: str = "测试") -> int:
    cur.execute("SELECT infra.next_ngiq_id(%s)", (etype,))
    eid = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO kg_entities (entity_id, entity_type, name_en, name_zh, source_name_original,"
        " name_en_source, name_zh_source, record_status)"
        " VALUES (%s,%s,%s,%s,%s,'source','translated_human','active') RETURNING entity_pk",
        (eid, etype, name_en, name_zh, name_en or "Test Original"),
    )
    return cur.fetchone()[0]


def _mk_region(cur, granularity: str = "G4_MICROSTRUCTURAL_FINE") -> int:
    pk = _mk_entity(cur, "brain_region")
    cur.execute("INSERT INTO brain_regions (entity_pk, granularity_level) VALUES (%s, %s)", (pk, granularity))
    return pk


def _mk_connection(cur, cclass: str = "functional_connectivity",
                   directionality: str = "non_directional") -> int:
    pk = _mk_entity(cur, "connection")
    cur.execute(
        "INSERT INTO connections (entity_pk, connection_class, directionality, derivation_type)"
        " VALUES (%s, %s, %s, 'reported')", (pk, cclass, directionality),
    )
    return pk


# ---------------------------------------------------------------------------
# Table set / count / no Circuit+/direct-edge leak
# ---------------------------------------------------------------------------


def _public_tables(conn) -> list[str]:
    cur = conn.cursor()
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
    return [r[0] for r in cur.fetchall()]


def test_phase3b_twenty_five_tables_present():
    conn = _conn(E2E)
    try:
        tables = set(_public_tables(conn))
    finally:
        conn.close()
    # Phase 3B delivered these 25; later phases legitimately add more tables.
    missing = [t for t in EXPECTED_TABLES if t not in tables]
    assert missing == [], f"missing Phase 3B tables: {missing}"


def test_three_new_tables_exist():
    conn = _conn(E2E)
    try:
        tables = set(_public_tables(conn))
    finally:
        conn.close()
    missing = [t for t in NEW_TABLES if t not in tables]
    assert missing == [], f"missing Phase 3B tables: {missing}"


def test_no_circuit_assertion_leak():
    conn = _conn(E2E)
    try:
        tables = set(_public_tables(conn))
    finally:
        conn.close()
    leaked = [t for t in CIRCUIT_PLUS_TABLES if t in tables]
    assert leaked == [], f"Circuit/assertion tables must not exist: {leaked}"


def test_no_direct_edge_canonical_duplication():
    conn = _conn(E2E)
    try:
        tables = set(_public_tables(conn))
    finally:
        conn.close()
    leaked = [t for t in DIRECT_EDGE_TABLES if t in tables]
    assert leaked == [], f"direct-edge canonical tables must not exist: {leaked}"


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
    # Phase 1F-B: e2e-only aggregation review-lifecycle divergence (documented).
    assert strip_agg_review_divergence(se) == sp


# ---------------------------------------------------------------------------
# Connection shared-PK / entity_type
# ---------------------------------------------------------------------------


def test_connection_shared_pk_no_second_identity():
    conn = _conn(E2E)
    try:
        cur = conn.cursor()
        cur.execute("SELECT column_name FROM information_schema.columns"
                    " WHERE table_schema='public' AND table_name='connections'")
        cols = [r[0] for r in cur.fetchall()]
        assert "entity_pk" in cols
        bad = [c for c in cols if c in ("connection_id", "entity_id", "name_en", "name_zh")]
        assert bad == [], f"connections has duplicated identity fields: {bad}"
    finally:
        conn.close()


def test_connection_wrong_entity_type_rejected(db):
    cur = db.cursor()
    gene = _mk_entity(cur, "gene")
    cur.execute("INSERT INTO genes (entity_pk, approved_symbol) VALUES (%s, 'APOE')", (gene,))
    with pytest.raises(psycopg.errors.RaiseException):
        cur.execute(
            "INSERT INTO connections (entity_pk, connection_class, directionality, derivation_type)"
            " VALUES (%s, 'structural_connection', 'directed', 'reported')", (gene,),
        )


# ---------------------------------------------------------------------------
# Endpoint model
# ---------------------------------------------------------------------------


def test_endpoint_connection_region_fk(db):
    cur = db.cursor()
    c = _mk_connection(cur)
    r1, r2 = _mk_region(cur), _mk_region(cur)
    cur.execute(
        "INSERT INTO connection_endpoints (connection_pk, brain_region_pk, endpoint_role)"
        " VALUES (%s, %s, 'endpoint'), (%s, %s, 'endpoint')", (c, r1, c, r2),
    )
    cur.execute("SELECT count(*) FROM connection_endpoints WHERE connection_pk=%s", (c,))
    assert cur.fetchone()[0] == 2


def test_endpoint_invalid_region_rejected(db):
    cur = db.cursor()
    c = _mk_connection(cur)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        cur.execute(
            "INSERT INTO connection_endpoints (connection_pk, brain_region_pk, endpoint_role)"
            " VALUES (%s, 999999999, 'endpoint')", (c,),
        )


def test_endpoint_duplicate_rejected(db):
    cur = db.cursor()
    c = _mk_connection(cur)
    r = _mk_region(cur)
    cur.execute(
        "INSERT INTO connection_endpoints (connection_pk, brain_region_pk, endpoint_role)"
        " VALUES (%s, %s, 'source')", (c, r),
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        cur.execute(
            "INSERT INTO connection_endpoints (connection_pk, brain_region_pk, endpoint_role)"
            " VALUES (%s, %s, 'source')", (c, r),
        )


def test_endpoint_self_source_target_rejected(db):
    cur = db.cursor()
    c = _mk_connection(cur, "projection", "directed")
    r = _mk_region(cur)
    cur.execute(
        "INSERT INTO connection_endpoints (connection_pk, brain_region_pk, endpoint_role)"
        " VALUES (%s, %s, 'source')", (c, r),
    )
    with pytest.raises(psycopg.errors.RaiseException):
        cur.execute(
            "INSERT INTO connection_endpoints (connection_pk, brain_region_pk, endpoint_role)"
            " VALUES (%s, %s, 'target')", (c, r),
        )


# ---------------------------------------------------------------------------
# Connection scientific semantics
# ---------------------------------------------------------------------------


def test_projection_source_target_ok(db):
    cur = db.cursor()
    c = _mk_connection(cur, "projection", "directed")
    src, tgt = _mk_region(cur), _mk_region(cur)
    cur.execute(
        "INSERT INTO connection_endpoints (connection_pk, brain_region_pk, endpoint_role)"
        " VALUES (%s, %s, 'source'), (%s, %s, 'target')", (c, src, c, tgt),
    )
    cur.execute("SELECT count(*) FROM connection_endpoints WHERE connection_pk=%s", (c,))
    assert cur.fetchone()[0] == 2


def test_functional_connectivity_not_forced_direction(db):
    cur = db.cursor()
    c = _mk_connection(cur, "functional_connectivity", "non_directional")
    r1, r2 = _mk_region(cur), _mk_region(cur)
    # FC uses two endpoint-role endpoints; no fabricated source/target
    cur.execute(
        "INSERT INTO connection_endpoints (connection_pk, brain_region_pk, endpoint_role)"
        " VALUES (%s, %s, 'endpoint'), (%s, %s, 'endpoint')", (c, r1, c, r2),
    )
    cur.execute("SELECT endpoint_role FROM connection_endpoints WHERE connection_pk=%s", (c,))
    roles = {r[0] for r in cur.fetchall()}
    assert roles == {"endpoint"}


def test_structural_direction_unknown_directionless_endpoints(db):
    cur = db.cursor()
    c = _mk_connection(cur, "structural_connection", "direction_unknown")
    r1, r2 = _mk_region(cur), _mk_region(cur)
    cur.execute(
        "INSERT INTO connection_endpoints (connection_pk, brain_region_pk, endpoint_role)"
        " VALUES (%s, %s, 'endpoint'), (%s, %s, 'endpoint')", (c, r1, c, r2),
    )
    cur.execute("SELECT count(*) FROM connection_endpoints WHERE connection_pk=%s", (c,))
    assert cur.fetchone()[0] == 2


def test_effective_connectivity_not_auto_projection(db):
    cur = db.cursor()
    c = _mk_connection(cur, "effective_connectivity", "directed")
    # EffectiveConnectivity stays its own class; the DB never promotes it to projection.
    cur.execute("SELECT connection_class FROM connections WHERE entity_pk=%s", (c,))
    assert cur.fetchone()[0] == "effective_connectivity"
    src, tgt = _mk_region(cur), _mk_region(cur)
    cur.execute(
        "INSERT INTO connection_endpoints (connection_pk, brain_region_pk, endpoint_role)"
        " VALUES (%s, %s, 'source'), (%s, %s, 'target')", (c, src, c, tgt),
    )


def test_directed_structural_not_auto_projection(db):
    cur = db.cursor()
    c = _mk_connection(cur, "structural_connection", "directed")
    cur.execute("SELECT connection_class FROM connections WHERE entity_pk=%s", (c,))
    assert cur.fetchone()[0] == "structural_connection"


# ---------------------------------------------------------------------------
# Observations
# ---------------------------------------------------------------------------


def test_observation_connection_fk(db):
    cur = db.cursor()
    c = _mk_connection(cur)
    cur.execute(
        "INSERT INTO connection_observations (connection_pk, sample_size, metric_name)"
        " VALUES (%s, 42, 'strength')", (c,),
    )
    cur.execute("SELECT count(*) FROM connection_observations WHERE connection_pk=%s", (c,))
    assert cur.fetchone()[0] == 1


def test_observation_invalid_connection_rejected(db):
    cur = db.cursor()
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        cur.execute("INSERT INTO connection_observations (connection_pk) VALUES (999999999)")


def test_observation_separated_from_evidence():
    conn = _conn(E2E)
    try:
        cur = conn.cursor()
        cur.execute("SELECT column_name FROM information_schema.columns"
                    " WHERE table_schema='public' AND table_name='connection_observations'")
        cols = [r[0] for r in cur.fetchall()]
        # Observation must NOT carry EvidenceLink-target-specific strength/directness
        assert "evidence_strength" not in cols
        assert "evidence_directness" not in cols
        # Observation FK context references scientific entities only
        assert "study_pk" in cols and "publication_pk" in cols and "evidence_pk" in cols
    finally:
        conn.close()
