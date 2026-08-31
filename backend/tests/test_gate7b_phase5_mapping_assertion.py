"""Gate 7B Phase 5 mapping/assertion/evidence-link tests (require live PostgreSQL).

Exercise region_mappings / relation_definitions / knowledge_assertions / evidence_links
against the E2E database (read/write in rolled-back transactions) and compare
production/E2E schema parity. Skip the module when E2E is unreachable.
"""

from __future__ import annotations

import psycopg
import pytest

PROD = "neurographiq_human_brain_v1"
E2E = "neurographiq_human_brain_v1_e2e"

NEW_TABLES = ["region_mappings", "relation_definitions", "knowledge_assertions", "evidence_links"]

EXPECTED_TABLES = sorted(
    ["atlases", "brain_region_aggregation_mappings", "brain_region_hierarchy_relations",
     "brain_region_spatial_representations", "brain_regions", "cellular_neural_structures",
     "circuit_connection_memberships", "circuit_region_memberships", "circuits",
     "connection_endpoints", "connection_observations", "connections", "diseases",
     "entity_aliases", "entity_xrefs", "evidence", "external_regions",
     "function_hierarchy_relations", "functions", "genes", "kg_entities",
     "neurobiological_processes", "neurotransmitters", "publications", "receptors",
     "research_studies", "sources", "symptoms"]
    + NEW_TABLES
)

FORBIDDEN_TABLES = [
    "assertion_evidence_links", "brain_region_spatial_relations",
    "connection_types", "circuit_types", "evidence_types",
]

EVIDENCE_WHITELIST = ["connection", "circuit", "region_mapping", "circuit_connection_membership"]


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
    pytest.skip("E2E database unreachable; skip Phase 5 tests", allow_module_level=True)


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


def _mk_external_region(cur) -> int:
    apk = _mk_entity(cur, "atlas")
    cur.execute("INSERT INTO atlases (entity_pk) VALUES (%s)", (apk,))
    xpk = _mk_entity(cur, "external_region")
    cur.execute("INSERT INTO external_regions (entity_pk, atlas_pk) VALUES (%s, %s)", (xpk, apk))
    return xpk


def _mk_connection(cur) -> int:
    pk = _mk_entity(cur, "connection")
    cur.execute(
        "INSERT INTO connections (entity_pk, connection_class, directionality, derivation_type)"
        " VALUES (%s, 'functional_connectivity', 'non_directional', 'reported')", (pk,),
    )
    return pk


def _mk_circuit(cur) -> int:
    pk = _mk_entity(cur, "circuit")
    cur.execute(
        "INSERT INTO circuits (entity_pk, construction_mode, derivation_type) VALUES (%s, 'composed', 'reported')",
        (pk,),
    )
    return pk


def _mk_region_mapping(cur) -> int:
    xpk = _mk_external_region(cur)
    bpk = _mk_region(cur)
    mpk = _mk_entity(cur, "region_mapping")
    cur.execute(
        "INSERT INTO region_mappings (entity_pk, external_region_pk, brain_region_pk, mapping_type)"
        " VALUES (%s, %s, %s, 'exact')", (mpk, xpk, bpk),
    )
    return mpk


def _mk_ccm(cur) -> int:
    c = _mk_circuit(cur)
    conn = _mk_connection(cur)
    ccmpk = _mk_entity(cur, "circuit_connection_membership")
    cur.execute(
        "INSERT INTO circuit_connection_memberships (entity_pk, circuit_pk, connection_pk)"
        " VALUES (%s, %s, %s)", (ccmpk, c, conn),
    )
    return ccmpk


def _mk_evidence(cur, status: str = "active") -> int:
    pk = _mk_entity(cur, "evidence", status=status)
    if status == "active":
        ppk = _mk_entity(cur, "publication")
        cur.execute("INSERT INTO publications (entity_pk) VALUES (%s)", (ppk,))
        cur.execute("INSERT INTO evidence (entity_pk, publication_pk) VALUES (%s, %s)", (pk, ppk))
    else:
        cur.execute("INSERT INTO evidence (entity_pk) VALUES (%s)", (pk,))
    return pk


def _mk_relation_definition(cur, key: str) -> int:
    cur.execute(
        "INSERT INTO relation_definitions (predicate_key, name_en, name_zh, is_directional, representation_role)"
        " VALUES (%s, %s, %s, true, 'canonical') RETURNING predicate_pk", (key, key, key),
    )
    return cur.fetchone()[0]


def _mk_assertion(cur, subj: int, pred: int, obj: int, derivation: str = "reported") -> int:
    cur.execute(
        "INSERT INTO knowledge_assertions (subject_entity_pk, predicate_pk, object_entity_pk, derivation_type)"
        " VALUES (%s, %s, %s, %s) RETURNING assertion_pk", (subj, pred, obj, derivation),
    )
    return cur.fetchone()[0]


def _insert_elink(cur, evidence_pk, assertion_pk=None, entity_pk=None, claim_scope=None,
                  role: str = "supports", record_status: str = "active"):
    cur.execute(
        "INSERT INTO evidence_links (evidence_pk, assertion_pk, entity_pk, evidence_role, claim_scope, record_status)"
        " VALUES (%s, %s, %s, %s, %s, %s) RETURNING link_id",
        (evidence_pk, assertion_pk, entity_pk, role, claim_scope, record_status),
    )
    return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Table set / count / no 33rd table
# ---------------------------------------------------------------------------


def _public_tables(conn) -> list[str]:
    cur = conn.cursor()
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
    return [r[0] for r in cur.fetchall()]


def test_table_count_is_thirty_two_exact():
    conn = _conn(E2E)
    try:
        tables = _public_tables(conn)
    finally:
        conn.close()
    assert tables == EXPECTED_TABLES
    assert len(tables) == 32


def test_no_33rd_table():
    conn = _conn(E2E)
    try:
        cur = conn.cursor()
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
        tables = {r[0] for r in cur.fetchall()}
    finally:
        conn.close()
    leaked = [t for t in FORBIDDEN_TABLES if t in tables]
    assert leaked == [], f"forbidden tables must not exist: {leaked}"
    assert len(tables) == 32


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
# RegionMapping
# ---------------------------------------------------------------------------


def test_region_mapping_shared_pk_no_second_identity():
    conn = _conn(E2E)
    try:
        cur = conn.cursor()
        cur.execute("SELECT column_name FROM information_schema.columns"
                    " WHERE table_schema='public' AND table_name='region_mappings'")
        cols = [r[0] for r in cur.fetchall()]
        assert "entity_pk" in cols
        bad = [c for c in cols if c in ("region_mapping_id", "mapping_id", "entity_id", "name_en", "name_zh")]
        assert bad == [], f"region_mappings has duplicated identity fields: {bad}"
    finally:
        conn.close()


def test_region_mapping_wrong_entity_type_rejected(db):
    cur = db.cursor()
    xpk = _mk_external_region(cur)
    bpk = _mk_region(cur)
    gene = _mk_entity(cur, "gene")
    cur.execute("INSERT INTO genes (entity_pk, approved_symbol) VALUES (%s, 'APOE')", (gene,))
    with pytest.raises(psycopg.errors.RaiseException):
        cur.execute(
            "INSERT INTO region_mappings (entity_pk, external_region_pk, brain_region_pk, mapping_type)"
            " VALUES (%s, %s, %s, 'exact')", (gene, xpk, bpk),
        )


def test_region_mapping_fk(db):
    cur = db.cursor()
    xpk = _mk_external_region(cur)
    bpk = _mk_region(cur)
    mpk = _mk_entity(cur, "region_mapping")
    cur.execute(
        "INSERT INTO region_mappings (entity_pk, external_region_pk, brain_region_pk, mapping_type)"
        " VALUES (%s, %s, %s, 'close')", (mpk, xpk, bpk),
    )
    cur.execute("SELECT count(*) FROM region_mappings WHERE entity_pk=%s", (mpk,))
    assert cur.fetchone()[0] == 1


def test_region_mapping_invalid_external_region_rejected(db):
    cur = db.cursor()
    bpk = _mk_region(cur)
    mpk = _mk_entity(cur, "region_mapping")
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        cur.execute(
            "INSERT INTO region_mappings (entity_pk, external_region_pk, brain_region_pk, mapping_type)"
            " VALUES (%s, 999999999, %s, 'exact')", (mpk, bpk),
        )


def test_region_mapping_separate_from_aggregation():
    conn = _conn(E2E)
    try:
        cur = conn.cursor()
        cur.execute("SELECT column_name FROM information_schema.columns"
                    " WHERE table_schema='public' AND table_name='region_mappings'")
        rm = set(r[0] for r in cur.fetchall())
        # region_mappings must NOT carry aggregation-specific columns
        for c in ("source_region_pk", "target_region_pk", "rollup_eligible", "is_primary_rollup"):
            assert c not in rm, f"region_mappings must not carry {c}"
        cur.execute("SELECT column_name FROM information_schema.columns"
                    " WHERE table_schema='public' AND table_name='brain_region_aggregation_mappings'")
        agg = set(r[0] for r in cur.fetchall())
        # aggregation must NOT carry external_region mapping columns
        assert "external_region_pk" not in agg
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Relation definitions / assertions
# ---------------------------------------------------------------------------


def test_relation_definition_fk(db):
    cur = db.cursor()
    pred = _mk_relation_definition(cur, "participatesIn")
    subj = _mk_region(cur)
    obj = _mk_entity(cur, "function")
    cur.execute("INSERT INTO functions (entity_pk, function_category) VALUES (%s, 'cognitive')", (obj,))
    apk = _mk_assertion(cur, subj, pred, obj)
    cur.execute("SELECT count(*) FROM knowledge_assertions WHERE assertion_pk=%s", (apk,))
    assert cur.fetchone()[0] == 1


def test_assertion_reported_inferred_vocab(db):
    cur = db.cursor()
    pred = _mk_relation_definition(cur, "increasesRiskOf")
    subj = _mk_entity(cur, "gene")
    cur.execute("INSERT INTO genes (entity_pk, approved_symbol) VALUES (%s, 'APOE')", (subj,))
    obj = _mk_entity(cur, "disease")
    cur.execute("INSERT INTO diseases (entity_pk) VALUES (%s)", (obj,))
    _mk_assertion(cur, subj, pred, obj, derivation="reported")
    _mk_assertion(cur, subj, pred, obj, derivation="inferred")
    with pytest.raises(psycopg.errors.CheckViolation):
        _mk_assertion(cur, subj, pred, obj, derivation="automatic")


def test_assertion_no_connection_truth_duplication():
    conn = _conn(E2E)
    try:
        cur = conn.cursor()
        cur.execute("SELECT column_name FROM information_schema.columns"
                    " WHERE table_schema='public' AND table_name='knowledge_assertions'")
        cols = set(r[0] for r in cur.fetchall())
        for c in ("connection_class", "directionality", "source_region_pk", "target_region_pk"):
            assert c not in cols, f"knowledge_assertions must not carry {c}"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Evidence links
# ---------------------------------------------------------------------------


def test_elink_evidence_required(db):
    cur = db.cursor()
    with pytest.raises(psycopg.errors.NotNullViolation):
        cur.execute(
            "INSERT INTO evidence_links (assertion_pk, evidence_role, record_status)"
            " VALUES (NULL, 'supports', 'active')"
        )


def test_elink_assertion_only_ok(db):
    cur = db.cursor()
    pred = _mk_relation_definition(cur, "hasSymptom")
    subj = _mk_entity(cur, "disease")
    cur.execute("INSERT INTO diseases (entity_pk) VALUES (%s)", (subj,))
    obj = _mk_entity(cur, "symptom")
    cur.execute("INSERT INTO symptoms (entity_pk) VALUES (%s)", (obj,))
    apk = _mk_assertion(cur, subj, pred, obj)
    ev = _mk_evidence(cur)
    lid = _insert_elink(cur, ev, assertion_pk=apk, claim_scope=None)
    cur.execute("SELECT count(*) FROM evidence_links WHERE link_id=%s", (lid,))
    assert cur.fetchone()[0] == 1


def test_elink_entity_only_ok(db):
    cur = db.cursor()
    ev = _mk_evidence(cur)
    conn = _mk_connection(cur)
    lid = _insert_elink(cur, ev, entity_pk=conn, claim_scope="connection_type")
    assert lid.startswith("NGIQ-ELK-")


def test_elink_both_targets_rejected(db):
    cur = db.cursor()
    pred = _mk_relation_definition(cur, "actsOn")
    subj = _mk_entity(cur, "neurotransmitter")
    cur.execute("INSERT INTO neurotransmitters (entity_pk) VALUES (%s)", (subj,))
    obj = _mk_entity(cur, "receptor")
    cur.execute("INSERT INTO receptors (entity_pk) VALUES (%s)", (obj,))
    apk = _mk_assertion(cur, subj, pred, obj)
    ev = _mk_evidence(cur)
    conn = _mk_connection(cur)
    with pytest.raises(psycopg.errors.CheckViolation):
        cur.execute(
            "INSERT INTO evidence_links (evidence_pk, assertion_pk, entity_pk, evidence_role, record_status)"
            " VALUES (%s, %s, %s, 'supports', 'active')", (ev, apk, conn),
        )


def test_elink_no_target_rejected(db):
    cur = db.cursor()
    ev = _mk_evidence(cur)
    with pytest.raises(psycopg.errors.CheckViolation):
        cur.execute(
            "INSERT INTO evidence_links (evidence_pk, evidence_role, record_status)"
            " VALUES (%s, 'supports', 'active')", (ev,),
        )


def test_elink_whitelist_allowed(db):
    cur = db.cursor()
    ev = _mk_evidence(cur)
    for etype in EVIDENCE_WHITELIST:
        if etype == "connection":
            target = _mk_connection(cur)
        elif etype == "circuit":
            target = _mk_circuit(cur)
        elif etype == "region_mapping":
            target = _mk_region_mapping(cur)
        else:  # circuit_connection_membership
            target = _mk_ccm(cur)
        _insert_elink(cur, ev, entity_pk=target, claim_scope="identity")
    cur.execute("SELECT count(*) FROM evidence_links WHERE evidence_pk=%s", (ev,))
    assert cur.fetchone()[0] == len(EVIDENCE_WHITELIST)


def test_elink_brain_region_target_rejected(db):
    cur = db.cursor()
    ev = _mk_evidence(cur)
    r = _mk_region(cur)
    with pytest.raises(psycopg.errors.RaiseException):
        _insert_elink(cur, ev, entity_pk=r, claim_scope="existence")


def test_elink_entity_requires_claim_scope(db):
    cur = db.cursor()
    ev = _mk_evidence(cur)
    conn = _mk_connection(cur)
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_elink(cur, ev, entity_pk=conn, claim_scope=None)


def test_elink_assertion_claim_scope_null_allowed(db):
    cur = db.cursor()
    pred = _mk_relation_definition(cur, "hasFunction")
    subj = _mk_circuit(cur)
    obj = _mk_entity(cur, "function")
    cur.execute("INSERT INTO functions (entity_pk, function_category) VALUES (%s, 'general')", (obj,))
    apk = _mk_assertion(cur, subj, pred, obj)
    ev = _mk_evidence(cur)
    _insert_elink(cur, ev, assertion_pk=apk, claim_scope=None)  # allowed


def test_elink_evidence_role_vocab(db):
    cur = db.cursor()
    ev = _mk_evidence(cur)
    conn = _mk_connection(cur)
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_elink(cur, ev, entity_pk=conn, claim_scope="identity", role="suggests")


def test_elink_strength_directness_location():
    conn = _conn(E2E)
    try:
        cur = conn.cursor()
        cur.execute("SELECT column_name FROM information_schema.columns"
                    " WHERE table_schema='public' AND table_name='evidence_links'")
        el = set(r[0] for r in cur.fetchall())
        assert "evidence_strength" in el and "evidence_directness" in el
        cur.execute("SELECT column_name FROM information_schema.columns"
                    " WHERE table_schema='public' AND table_name='evidence'")
        ev = set(r[0] for r in cur.fetchall())
        assert "evidence_strength" not in ev and "evidence_directness" not in ev
    finally:
        conn.close()
