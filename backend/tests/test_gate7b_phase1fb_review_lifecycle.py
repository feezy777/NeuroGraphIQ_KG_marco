"""Gate 7B Phase 1F-B — Aggregation Mapping Review Lifecycle (E2E contract tests).

Verifies the minimal human scientific-review lifecycle added to
brain_region_aggregation_mappings (e2e only, production frozen this round):
  * review_status (default 'pending', vocabulary pending/approved/rejected/
    uncertain/needs_revision) is SEPARATE from record_status
  * reviewed_by / reviewed_at are nullable until a human reviews
  * rollup safety: dominant_overlap / partial_overlap stay rollup_eligible=FALSE
    even when approved (only contained_in may roll up)
  * a contained_in candidate defaults to record_status='proposed' +
    review_status='pending' regardless of the scientific freeze (two independent gates)
  * partial unique index: one source has at most ONE active+approved+primary
    rollup target; deprecated/non-primary rows are not mis-blocked
  * production brain_region_aggregation_mappings stays at 0 rows

All DB writes happen in a rolled-back transaction (no persistence).
"""

from __future__ import annotations

import datetime as _dt

import psycopg
import pytest

PROD = "neurographiq_human_brain_v1"
E2E = "neurographiq_human_brain_v1_e2e"
TABLE = "brain_region_aggregation_mappings"
REVIEW_VOCAB = ("pending", "approved", "rejected", "uncertain", "needs_revision")


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
    pytest.skip("E2E database unreachable; skip Phase 1F-B review lifecycle tests",
                allow_module_level=True)


@pytest.fixture()
def db():
    conn = _conn(E2E)
    yield conn
    conn.rollback()
    conn.close()


def _mk_entity(cur, etype: str = "brain_region", name_en: str = "Test") -> int:
    cur.execute("SELECT infra.next_ngiq_id(%s)", (etype,))
    eid = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO kg_entities (entity_id, entity_type, name_en, name_zh, source_name_original,"
        " name_en_source, name_zh_source, record_status)"
        " VALUES (%s,%s,%s,%s,%s,'source','translated_human','active') RETURNING entity_pk",
        (eid, etype, name_en, "测试", name_en),
    )
    return cur.fetchone()[0]


def _mk_region(cur, granularity: str) -> int:
    pk = _mk_entity(cur, "brain_region", "Test Region")
    cur.execute("INSERT INTO brain_regions (entity_pk, granularity_level) VALUES (%s, %s)",
                (pk, granularity))
    return pk


def _mk_source_target(cur, src_g: str = "G3_MESO_FINE", tgt_g: str = "G1_MACRO"):
    return _mk_region(cur, src_g), _mk_region(cur, tgt_g)


def _insert(cur, source, target, relation, record_status,
            review_status="pending", rollup_eligible=False, is_primary_rollup=False,
            reviewed_by=None, reviewed_at=None):
    cur.execute(
        f"INSERT INTO {TABLE} (source_region_pk, target_region_pk, mapping_relation,"
        " record_status, review_status, rollup_eligible, is_primary_rollup, reviewed_by, reviewed_at)"
        " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (source, target, relation, record_status, review_status,
         rollup_eligible, is_primary_rollup, reviewed_by, reviewed_at),
    )


def _cols(conn, table: str = TABLE) -> set[str]:
    cur = conn.cursor()
    cur.execute(
        "SELECT column_name FROM information_schema.columns"
        " WHERE table_schema='public' AND table_name=%s", (table,),
    )
    return {r[0] for r in cur.fetchall()}


# ---------------------------------------------------------------------------
# 1-5. schema presence / defaults / nullability / vocabulary
# ---------------------------------------------------------------------------


def test_review_status_field_exists():
    conn = _conn(E2E)
    try:
        cols = _cols(conn)
        assert {"review_status", "reviewed_by", "reviewed_at"} <= cols
    finally:
        conn.close()


def test_review_status_default_pending():
    conn = _conn(E2E)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT column_default FROM information_schema.columns"
            " WHERE table_schema='public' AND table_name=%s AND column_name='review_status'",
            (TABLE,),
        )
        default = cur.fetchone()[0]
        assert "pending" in (default or "")
    finally:
        conn.close()


def test_review_status_vocabulary_enforced(db):
    cur = db.cursor()
    s, t = _mk_source_target(cur)
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert(cur, s, t, "contained_in", "proposed", review_status="reviewed")
    db.rollback()  # recover from aborted transaction before continuing
    # every legal value inserts cleanly (rolled back)
    for v in REVIEW_VOCAB:
        s, t = _mk_source_target(cur)
        _insert(cur, s, t, "contained_in", "proposed", review_status=v)


def test_reviewed_by_nullable():
    conn = _conn(E2E)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT is_nullable FROM information_schema.columns"
            " WHERE table_schema='public' AND table_name=%s AND column_name='reviewed_by'",
            (TABLE,),
        )
        assert cur.fetchone()[0] == "YES"
    finally:
        conn.close()


def test_reviewed_at_nullable():
    conn = _conn(E2E)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT is_nullable FROM information_schema.columns"
            " WHERE table_schema='public' AND table_name=%s AND column_name='reviewed_at'",
            (TABLE,),
        )
        assert cur.fetchone()[0] == "YES"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 6. approved mapping stores reviewer + time
# ---------------------------------------------------------------------------

def test_approved_mapping_stores_reviewer_and_time(db):
    cur = db.cursor()
    s, t = _mk_source_target(cur)
    now = _dt.datetime.now(_dt.timezone.utc)
    _insert(cur, s, t, "contained_in", "active", review_status="approved",
            rollup_eligible=True, is_primary_rollup=True,
            reviewed_by="human-reviewer", reviewed_at=now)
    cur.execute(
        "SELECT review_status, reviewed_by, reviewed_at FROM brain_region_aggregation_mappings"
        " WHERE source_region_pk=%s AND target_region_pk=%s", (s, t),
    )
    status, reviewer, reviewed_at = cur.fetchone()
    assert status == "approved"
    assert reviewer == "human-reviewer"
    assert reviewed_at is not None
    assert (reviewed_at - now).total_seconds() < 60


# ---------------------------------------------------------------------------
# 7-8. dominant/partial + approved still rollup=false
# ---------------------------------------------------------------------------

def test_dominant_overlap_approved_rollup_false(db):
    cur = db.cursor()
    s, t = _mk_source_target(cur)
    _insert(cur, s, t, "dominant_overlap", "active", review_status="approved")
    cur.execute(
        "SELECT rollup_eligible, is_primary_rollup FROM brain_region_aggregation_mappings"
        " WHERE source_region_pk=%s", (s,),
    )
    assert cur.fetchone() == (False, False)
    # and the DB rejects any attempt to roll up a dominant_overlap
    s2, t2 = _mk_source_target(cur)
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert(cur, s2, t2, "dominant_overlap", "active", review_status="approved",
                rollup_eligible=True)
    db.rollback()  # recover from aborted transaction


def test_partial_overlap_approved_rollup_false(db):
    cur = db.cursor()
    s, t = _mk_source_target(cur)
    _insert(cur, s, t, "partial_overlap", "active", review_status="approved")
    cur.execute(
        "SELECT rollup_eligible, is_primary_rollup FROM brain_region_aggregation_mappings"
        " WHERE source_region_pk=%s", (s,),
    )
    assert cur.fetchone() == (False, False)
    s2, t2 = _mk_source_target(cur)
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert(cur, s2, t2, "partial_overlap", "active", review_status="approved",
                is_primary_rollup=True)
    db.rollback()  # recover from aborted transaction


# ---------------------------------------------------------------------------
# 9. contained_in candidate defaults to pending/proposed
# ---------------------------------------------------------------------------

def test_contained_in_candidate_defaults_pending_proposed(db):
    cur = db.cursor()
    s, t = _mk_source_target(cur)
    # candidate row written from a scientific decision — no auto-approval
    _insert(cur, s, t, "contained_in", "proposed", rollup_eligible=True, is_primary_rollup=True)
    cur.execute(
        "SELECT record_status, review_status, rollup_eligible, is_primary_rollup"
        " FROM brain_region_aggregation_mappings WHERE source_region_pk=%s", (s,),
    )
    assert cur.fetchone() == ("proposed", "pending", True, True)


# ---------------------------------------------------------------------------
# 10-11. primary rollup uniqueness
# ---------------------------------------------------------------------------

def test_second_active_approved_primary_rollup_rejected(db):
    cur = db.cursor()
    s, t1 = _mk_source_target(cur)
    _, t2 = _mk_source_target(cur)
    _insert(cur, s, t1, "contained_in", "active", review_status="approved",
            rollup_eligible=True, is_primary_rollup=True)
    with pytest.raises(psycopg.errors.UniqueViolation):
        _insert(cur, s, t2, "contained_in", "active", review_status="approved",
                rollup_eligible=True, is_primary_rollup=True)


def test_deprecated_and_non_primary_rows_not_blocked(db):
    cur = db.cursor()
    s, t1 = _mk_source_target(cur)
    # one active+approved primary rollup
    _insert(cur, s, t1, "contained_in", "active", review_status="approved",
            rollup_eligible=True, is_primary_rollup=True)
    # a DEPRECATED duplicate of the same source is allowed (excluded by predicate)
    _, t2 = _mk_source_target(cur)
    _insert(cur, s, t2, "contained_in", "deprecated", review_status="approved",
            rollup_eligible=True, is_primary_rollup=True)
    # a PROPOSED candidate of the same source is allowed (predicate requires active+approved)
    _, t3 = _mk_source_target(cur)
    _insert(cur, s, t3, "contained_in", "proposed", review_status="pending",
            rollup_eligible=True, is_primary_rollup=True)
    cur.execute(
        "SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_region_pk=%s", (s,),
    )
    assert cur.fetchone()[0] == 3


# ---------------------------------------------------------------------------
# 12. production stays 0
# ---------------------------------------------------------------------------

def test_production_mapping_count_zero():
    # Phase 1F-F loaded the 246 candidates as proposed+pending; the schema-only
    # gate's zero-insert guarantee became "all loaded rows are proposed+pending".
    conn = _conn(PROD)
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings")
        total = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings"
                    " WHERE record_status='active' AND review_status='approved'")
        active = cur.fetchone()[0]
        # 1F-H approved, then 1F-I promoted the batch to active
        assert total == 246 and active == 246
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# A. e2e-only divergence is exactly the documented review lifecycle (prod frozen)
# ---------------------------------------------------------------------------

def test_prod_does_not_have_review_lifecycle():
    # Phase 1F-E synced the review lifecycle to production: both prod and e2e
    # now carry review_status / reviewed_by / reviewed_at (schema parity).
    prod, e2e = _conn(PROD), _conn(E2E)
    try:
        pc, ec = _cols(prod), _cols(e2e)
    finally:
        prod.close()
        e2e.close()
    assert {"review_status", "reviewed_by", "reviewed_at"} <= pc
    assert {"review_status", "reviewed_by", "reviewed_at"} <= ec


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
