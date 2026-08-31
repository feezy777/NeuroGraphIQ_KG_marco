"""Gate 7B Phase 3A hierarchy/spatial/aggregation tests (require live PostgreSQL).

Exercise the 4 relation/spatial/integration tables against the E2E database
(read/write in rolled-back transactions) and compare production/E2E parity.
Skip the module when the E2E database is unreachable.
"""

from __future__ import annotations

import psycopg
import pytest

PROD = "neurographiq_human_brain_v1"
E2E = "neurographiq_human_brain_v1_e2e"

NEW_TABLES = [
    "brain_region_hierarchy_relations",
    "function_hierarchy_relations",
    "brain_region_spatial_representations",
    "brain_region_aggregation_mappings",
]

EXPECTED_TABLES = sorted(
    ["atlases", "brain_regions", "cellular_neural_structures", "diseases",
     "entity_aliases", "entity_xrefs", "evidence", "external_regions", "functions",
     "genes", "kg_entities", "neurobiological_processes", "neurotransmitters",
     "publications", "receptors", "research_studies", "sources", "symptoms"]
    + NEW_TABLES
)

PHASE3B_TABLES = [
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
    pytest.skip("E2E database unreachable; skip Phase 3A tests", allow_module_level=True)


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


def _mk_region(cur, granularity_level: str = "G4_MICROSTRUCTURAL_FINE") -> int:
    pk = _mk_entity(cur, "brain_region")
    cur.execute("INSERT INTO brain_regions (entity_pk, granularity_level) VALUES (%s, %s)",
                (pk, granularity_level))
    return pk


def _mk_function(cur) -> int:
    pk = _mk_entity(cur, "function")
    cur.execute("INSERT INTO functions (entity_pk, function_category) VALUES (%s, 'cognitive')", (pk,))
    return pk


def _mk_atlas(cur) -> int:
    pk = _mk_entity(cur, "atlas")
    cur.execute("INSERT INTO atlases (entity_pk) VALUES (%s)", (pk,))
    return pk


# ---------------------------------------------------------------------------
# Table set / count / no Phase 3B leak
# ---------------------------------------------------------------------------


def _public_tables(conn) -> list[str]:
    cur = conn.cursor()
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
    return [r[0] for r in cur.fetchall()]


def test_phase3a_twenty_two_tables_present():
    conn = _conn(E2E)
    try:
        tables = set(_public_tables(conn))
    finally:
        conn.close()
    # Phase 3A delivered these 22; later phases legitimately add more tables.
    missing = [t for t in EXPECTED_TABLES if t not in tables]
    assert missing == [], f"missing Phase 3A tables: {missing}"


def test_four_new_tables_exist():
    conn = _conn(E2E)
    try:
        tables = set(_public_tables(conn))
    finally:
        conn.close()
    missing = [t for t in NEW_TABLES if t not in tables]
    assert missing == [], f"missing Phase 3A tables: {missing}"


def test_no_phase3b_table_leak():
    conn = _conn(E2E)
    try:
        tables = set(_public_tables(conn))
    finally:
        conn.close()
    leaked = [t for t in PHASE3B_TABLES if t in tables]
    assert leaked == [], f"Phase 3B+ tables must not exist: {leaked}"


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
# BrainRegion hierarchy
# ---------------------------------------------------------------------------


def test_brh_fk_valid(db):
    cur = db.cursor()
    parent, child = _mk_region(cur), _mk_region(cur)
    cur.execute(
        "INSERT INTO brain_region_hierarchy_relations (parent_region_pk, child_region_pk, relation_type)"
        " VALUES (%s, %s, 'part_of')", (parent, child),
    )
    cur.execute("SELECT count(*) FROM brain_region_hierarchy_relations")
    assert cur.fetchone()[0] == 1


def test_brh_self_relation_rejected(db):
    cur = db.cursor()
    r = _mk_region(cur)
    with pytest.raises(psycopg.errors.CheckViolation):
        cur.execute(
            "INSERT INTO brain_region_hierarchy_relations (parent_region_pk, child_region_pk, relation_type)"
            " VALUES (%s, %s, 'part_of')", (r, r),
        )


def test_brh_illegal_relation_type_rejected(db):
    cur = db.cursor()
    parent, child = _mk_region(cur), _mk_region(cur)
    with pytest.raises(psycopg.errors.CheckViolation):
        cur.execute(
            "INSERT INTO brain_region_hierarchy_relations (parent_region_pk, child_region_pk, relation_type)"
            " VALUES (%s, %s, 'overlaps')", (parent, child),
        )


# ---------------------------------------------------------------------------
# Function hierarchy
# ---------------------------------------------------------------------------


def test_fhr_fk_valid(db):
    cur = db.cursor()
    parent, child = _mk_function(cur), _mk_function(cur)
    cur.execute(
        "INSERT INTO function_hierarchy_relations (parent_function_pk, child_function_pk, relation_type)"
        " VALUES (%s, %s, 'subclass_of')", (parent, child),
    )
    cur.execute("SELECT count(*) FROM function_hierarchy_relations")
    assert cur.fetchone()[0] == 1


def test_fhr_self_relation_rejected(db):
    cur = db.cursor()
    f = _mk_function(cur)
    with pytest.raises(psycopg.errors.CheckViolation):
        cur.execute(
            "INSERT INTO function_hierarchy_relations (parent_function_pk, child_function_pk, relation_type)"
            " VALUES (%s, %s, 'part_of')", (f, f),
        )


def test_fhr_illegal_relation_type_rejected(db):
    cur = db.cursor()
    parent, child = _mk_function(cur), _mk_function(cur)
    with pytest.raises(psycopg.errors.CheckViolation):
        cur.execute(
            "INSERT INTO function_hierarchy_relations (parent_function_pk, child_function_pk, relation_type)"
            " VALUES (%s, %s, 'rdfs_subclass')", (parent, child),
        )


# ---------------------------------------------------------------------------
# parent_*_pk remain DERIVED caches
# ---------------------------------------------------------------------------


def test_parent_region_pk_is_derived_cache():
    conn = _conn(E2E)
    try:
        cur = conn.cursor()
        cur.execute("SELECT is_nullable FROM information_schema.columns"
                    " WHERE table_name='brain_regions' AND column_name='parent_region_pk'")
        assert cur.fetchone()[0] == "YES"
        cur.execute("SELECT is_nullable FROM information_schema.columns"
                    " WHERE table_name='functions' AND column_name='parent_function_pk'")
        assert cur.fetchone()[0] == "YES"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Spatial representations
# ---------------------------------------------------------------------------


def test_spatial_requires_valid_brain_region(db):
    cur = db.cursor()
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        cur.execute("INSERT INTO brain_region_spatial_representations (brain_region_pk) VALUES (999999999)")


def test_spatial_atlas_context_ok(db):
    cur = db.cursor()
    r = _mk_region(cur)
    a = _mk_atlas(cur)
    cur.execute(
        "INSERT INTO brain_region_spatial_representations (brain_region_pk, atlas_pk, reference_space, atlas_version)"
        " VALUES (%s, %s, 'MNI152', 'v1.0')", (r, a),
    )
    cur.execute("SELECT count(*) FROM brain_region_spatial_representations WHERE brain_region_pk=%s", (r,))
    assert cur.fetchone()[0] == 1


def test_spatial_invalid_reference_space_rejected(db):
    cur = db.cursor()
    r = _mk_region(cur)
    with pytest.raises(psycopg.errors.CheckViolation):
        cur.execute(
            "INSERT INTO brain_region_spatial_representations (brain_region_pk, reference_space)"
            " VALUES (%s, 'Talairach')", (r,),
        )


def test_no_spatial_relation_table():
    conn = _conn(E2E)
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='brain_region_spatial_relations'")
        assert cur.fetchone() is None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Aggregation mappings
# ---------------------------------------------------------------------------


def test_agg_fine_to_coarse_allowed(db):
    cur = db.cursor()
    fine = _mk_region(cur, "G4_MICROSTRUCTURAL_FINE")
    coarse = _mk_region(cur, "G3_MESO_FINE")
    cur.execute(
        "INSERT INTO brain_region_aggregation_mappings (source_region_pk, target_region_pk,"
        " mapping_relation, record_status) VALUES (%s, %s, 'exact_aggregate', 'active')",
        (fine, coarse),
    )
    cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings")
    assert cur.fetchone()[0] == 1


def test_agg_reverse_direction_rejected(db):
    cur = db.cursor()
    fine = _mk_region(cur, "G4_MICROSTRUCTURAL_FINE")
    coarse = _mk_region(cur, "G3_MESO_FINE")
    with pytest.raises(psycopg.errors.RaiseException):
        cur.execute(
            "INSERT INTO brain_region_aggregation_mappings (source_region_pk, target_region_pk,"
            " mapping_relation, record_status) VALUES (%s, %s, 'exact_aggregate', 'active')",
            (coarse, fine),
        )


def test_agg_same_level_rejected(db):
    cur = db.cursor()
    a = _mk_region(cur, "G3_MESO_FINE")
    b = _mk_region(cur, "G3_MESO_FINE")
    with pytest.raises(psycopg.errors.RaiseException):
        cur.execute(
            "INSERT INTO brain_region_aggregation_mappings (source_region_pk, target_region_pk,"
            " mapping_relation, record_status) VALUES (%s, %s, 'exact_aggregate', 'active')",
            (a, b),
        )


def test_agg_requires_granularity_level(db):
    cur = db.cursor()
    # region without granularity_level
    a = _mk_entity(cur, "brain_region")
    cur.execute("INSERT INTO brain_regions (entity_pk) VALUES (%s)", (a,))
    b = _mk_region(cur, "G3_MESO_FINE")
    with pytest.raises(psycopg.errors.RaiseException):
        cur.execute(
            "INSERT INTO brain_region_aggregation_mappings (source_region_pk, target_region_pk,"
            " mapping_relation, record_status) VALUES (%s, %s, 'exact_aggregate', 'active')",
            (a, b),
        )


def test_agg_source_target_must_be_brain_region(db):
    cur = db.cursor()
    gene = _mk_entity(cur, "gene")
    cur.execute("INSERT INTO genes (entity_pk, approved_symbol) VALUES (%s, 'APOE')", (gene,))
    coarse = _mk_region(cur, "G3_MESO_FINE")
    # The granularity guard fires BEFORE the FK check: a gene pk has no brain_regions
    # row, so granularity lookup is NULL -> fail closed (RaiseException).
    with pytest.raises(psycopg.errors.RaiseException):
        cur.execute(
            "INSERT INTO brain_region_aggregation_mappings (source_region_pk, target_region_pk,"
            " mapping_relation, record_status) VALUES (%s, %s, 'exact_aggregate', 'active')",
            (gene, coarse),
        )


def test_agg_not_forced_tree_and_n_to_one(db):
    cur = db.cursor()
    f1 = _mk_region(cur, "G4_MICROSTRUCTURAL_FINE")
    f2 = _mk_region(cur, "G4_MICROSTRUCTURAL_FINE")
    coarse = _mk_region(cur, "G2_MESO_ANATOMICAL")
    # N:1 — two fine regions -> same coarse target (allowed)
    cur.execute(
        "INSERT INTO brain_region_aggregation_mappings (source_region_pk, target_region_pk,"
        " mapping_relation, record_status) VALUES (%s, %s, 'contained_in', 'active')", (f1, coarse),
    )
    cur.execute(
        "INSERT INTO brain_region_aggregation_mappings (source_region_pk, target_region_pk,"
        " mapping_relation, record_status) VALUES (%s, %s, 'contained_in', 'active')", (f2, coarse),
    )
    # no UNIQUE on source/target columns
    cur.execute(
        "SELECT a.attname FROM pg_index i"
        " JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=ANY(i.indkey)"
        " WHERE i.indrelid='brain_region_aggregation_mappings'::regclass AND i.indisunique"
    )
    uniq_cols = {r[0] for r in cur.fetchall()}
    assert not ({"source_region_pk", "target_region_pk"} & uniq_cols)


def test_agg_rollup_eligible_and_primary(db):
    cur = db.cursor()
    fine = _mk_region(cur, "G4_MICROSTRUCTURAL_FINE")
    coarse = _mk_region(cur, "G1_MACRO")
    cur.execute(
        "INSERT INTO brain_region_aggregation_mappings (source_region_pk, target_region_pk,"
        " mapping_relation, rollup_eligible, is_primary_rollup, record_status)"
        " VALUES (%s, %s, 'dominant_overlap', true, true, 'active')", (fine, coarse),
    )
    # default rollup_eligible=false when omitted
    f2 = _mk_region(cur, "G4_MICROSTRUCTURAL_FINE")
    cur.execute(
        "INSERT INTO brain_region_aggregation_mappings (source_region_pk, target_region_pk,"
        " mapping_relation, record_status) VALUES (%s, %s, 'partial_overlap', 'proposed')", (f2, coarse),
    )
    cur.execute(
        "SELECT rollup_eligible, is_primary_rollup FROM brain_region_aggregation_mappings ORDER BY mapping_pk"
    )
    rows = cur.fetchall()
    assert rows[0] == (True, True)
    assert rows[1] == (False, False)


def test_agg_does_not_auto_create_partof(db):
    cur = db.cursor()
    fine = _mk_region(cur, "G4_MICROSTRUCTURAL_FINE")
    coarse = _mk_region(cur, "G3_MESO_FINE")
    cur.execute(
        "INSERT INTO brain_region_aggregation_mappings (source_region_pk, target_region_pk,"
        " mapping_relation, spatial_overlap_ratio, record_status)"
        " VALUES (%s, %s, 'exact_aggregate', 0.98, 'active')", (fine, coarse),
    )
    cur.execute("SELECT count(*) FROM brain_region_hierarchy_relations")
    assert cur.fetchone()[0] == 0  # high overlap must NOT auto-create partOf
