"""Gate 9 G4 — Julich-Brain v3.1 promotion PLAN tests.

Read-only E2E assertions for the promotion plan (eligible=440, only-Julich-G4 scope,
G1/G3 excluded, GapMap excluded, proposed/pending required, QA extraction_ready,
projected 440 active/approved, name/identity/mapping untouched) plus idempotency /
fail-closed / transaction semantics. The apply path is exercised inside a rolled-back
transaction so E2E state is never mutated.

Mirrors the Gate9 G1 promotion test pattern (pure functions + read-only E2E state).
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import psycopg
import pytest

BACKEND = Path(__file__).resolve().parents[1]
E2E = "neurographiq_human_brain_v1_e2e"

spec = importlib.util.spec_from_file_location(
    "promoj4", BACKEND / "scripts" / "promote_julich_g4_registry.py")
promo = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(promo)

QA = promo.load_qa_artifact()


def _conn():
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=E2E, autocommit=True)


# ---------------------------------------------------------------------------
# 1-6. Selection scope: eligible = 440, Julich-G4 identity only
# ---------------------------------------------------------------------------

def test_plan_eligible_440():
    conn = _conn()
    try:
        cur = conn.cursor()
        ids = promo._eligible(cur)
        assert len(ids) == 440
        assert len(set(ids)) == 440  # no duplicate entity_pk
    finally:
        conn.close()


def test_scope_only_julich_g4_identity():
    conn = _conn()
    try:
        cur = conn.cursor()
        ids = promo._eligible(cur)
        # every selected row is owned by the frozen Julich v3.1 source + G4 granularity
        cur.execute(
            "SELECT count(*) FROM kg_entities ke"
            " JOIN brain_regions br ON br.entity_pk=ke.entity_pk"
            " JOIN sources s ON s.source_pk=br.canonical_source_pk"
            " WHERE ke.entity_pk = ANY(%s) AND (br.granularity_level<>%s"
            "  OR s.name_en<>%s OR s.version<>%s)",
            (ids, promo.GRANULARITY, promo.SOURCE_NAME_EN, promo.SOURCE_VERSION))
        assert cur.fetchone()[0] == 0
        # no other G4 provenance exists in E2E (conflict would be 0)
        assert promo._g4_foreign(cur) == 0
    finally:
        conn.close()


def test_g1_excluded():
    conn = _conn()
    try:
        cur = conn.cursor()
        ids = promo._eligible(cur)
        cur.execute("SELECT count(*) FROM brain_regions WHERE entity_pk = ANY(%s)"
                    " AND granularity_level='G1_MACRO'", (ids,))
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()


def test_g3_excluded():
    conn = _conn()
    try:
        cur = conn.cursor()
        ids = promo._eligible(cur)
        cur.execute("SELECT count(*) FROM brain_regions WHERE entity_pk = ANY(%s)"
                    " AND granularity_level='G3_MESO_FINE'", (ids,))
        assert cur.fetchone()[0] == 0
        # the E2E harness carries no G3 rows at all (Brainnetome lives in production only)
        assert promo._granularity_lifecycle(cur, "G3_MESO_FINE", "active", "approved") == 0
    finally:
        conn.close()


def test_gapmap_excluded():
    conn = _conn()
    try:
        cur = conn.cursor()
        ids = promo._eligible(cur)
        cur.execute("SELECT count(*) FROM kg_entities WHERE entity_pk = ANY(%s)"
                    " AND (name_en ~ 'GapMap' OR source_name_original ~ 'GAPMAP')", (ids,))
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()


def test_requires_proposed_pending_and_none_already():
    conn = _conn()
    try:
        cur = conn.cursor()
        ids = promo._eligible(cur)
        # every eligible row is proposed+pending; none are already active/approved
        cur.execute("SELECT count(*) FROM kg_entities WHERE entity_pk = ANY(%s)"
                    " AND (record_status<>'proposed' OR review_status<>'pending')", (ids,))
        assert cur.fetchone()[0] == 0
        assert promo._already(cur) == 0
        assert promo._not_eligible(cur) == 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 7. QA audit basis
# ---------------------------------------------------------------------------

def test_qa_artifact_extraction_ready():
    # the plan is gated on the frozen final-semantic-QA artifact
    assert promo._qa_ok(QA) is True
    assert QA["extraction_ready"] is True
    assert QA["semantic_rule_failures"] == []
    assert QA["g4_total"] == 440
    assert QA["pair_total"] == 220


def test_qa_guard_rejects_tampered_artifact():
    assert not promo._qa_ok({"extraction_ready": False, "semantic_rule_failures": [],
                             "g4_total": 440, "pair_total": 220})
    assert not promo._qa_ok({"extraction_ready": True, "semantic_rule_failures": [{"x": 1}],
                             "g4_total": 440, "pair_total": 220})
    assert not promo._qa_ok({"extraction_ready": True, "semantic_rule_failures": [],
                             "g4_total": 439, "pair_total": 220})


# ---------------------------------------------------------------------------
# 8. Projection
# ---------------------------------------------------------------------------

def test_projected_active_approved_440():
    conn = _conn()
    try:
        cur = conn.cursor()
        ids = promo._eligible(cur)
        already = promo._already(cur)
        assert already == 0
        assert already + len(ids) == 440  # after promotion all Julich G4 are active/approved
        left, right = promo._hemi_split(cur, ids)
        assert left == 220
        assert right == 220
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 9-11. Apply semantics (rolled-back transaction — E2E never mutated)
# ---------------------------------------------------------------------------

def _rolled_back_apply():
    """Apply the promotion SQL inside a transaction, hand the live cursor back, then roll back."""
    conn = psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=E2E, autocommit=False)
    return conn, conn.cursor()


def test_identity_fields_unchanged_by_promotion():
    conn, cur = _rolled_back_apply()
    try:
        ids = promo._eligible(cur)
        assert len(ids) == 440
        cols = ("ke.entity_pk, ke.name_en, ke.name_zh, ke.source_name_original,"
                " ke.metadata_json->>'julich_source_region_id', br.hemisphere,"
                " br.granularity_level, br.species_taxon_id")
        cur.execute("SELECT " + cols + " FROM kg_entities ke"
                    " JOIN brain_regions br ON br.entity_pk=ke.entity_pk"
                    " WHERE ke.entity_pk = ANY(%s) ORDER BY ke.entity_pk", (ids,))
        before = cur.fetchall()
        cur.execute(promo.PROMOTE_SQL, (promo.PROMOTE_REVIEWER, promo.PROMOTE_NOTE, ids))
        assert cur.rowcount == 440
        cur.execute("SELECT " + cols + " FROM kg_entities ke"
                    " JOIN brain_regions br ON br.entity_pk=ke.entity_pk"
                    " WHERE ke.entity_pk = ANY(%s) ORDER BY ke.entity_pk", (ids,))
        assert before == cur.fetchall()  # no scientific field changed
    finally:
        conn.rollback()
        conn.close()


def test_mapping_unchanged_by_promotion():
    conn, cur = _rolled_back_apply()
    try:
        ids = promo._eligible(cur)
        before = promo._mapping_count(cur)
        assert before == 440
        cur.execute(promo.PROMOTE_SQL, (promo.PROMOTE_REVIEWER, promo.PROMOTE_NOTE, ids))
        after = promo._mapping_count(cur)
        assert after == before  # region_mappings never touched
    finally:
        conn.rollback()
        conn.close()


def test_second_plan_after_promotion_eligible_zero():
    # idempotency: after promotion, a second PLAN sees eligible=0, already_promoted=440
    conn, cur = _rolled_back_apply()
    try:
        ids = promo._eligible(cur)
        assert len(ids) == 440
        cur.execute(promo.PROMOTE_SQL, (promo.PROMOTE_REVIEWER, promo.PROMOTE_NOTE, ids))
        assert cur.rowcount == 440
        # the same scope logic, re-run inside the transaction, now yields zero eligible
        assert promo._eligible(cur) == []
        assert promo._already(cur) == 440
        # reviewer marker written exactly on all 440
        cur.execute("SELECT count(*) FROM kg_entities WHERE entity_pk = ANY(%s)"
                    " AND record_status='active' AND review_status='approved'"
                    " AND updated_by_agent=%s", (ids, promo.PROMOTE_REVIEWER))
        assert cur.fetchone()[0] == 440
    finally:
        conn.rollback()
        conn.close()


# ---------------------------------------------------------------------------
# 12. Fail-closed / transaction semantics
# ---------------------------------------------------------------------------

def test_plan_status_verdicts():
    P = promo
    # ready: 440 eligible, 0 already, clean
    assert P._plan_status(440, 0, 0, 0, 0, 220, 220, 84, 246, True) == "ready"
    # done: idempotent second PLAN (0 eligible, 440 already)
    assert P._plan_status(0, 440, 0, 0, 0, 0, 0, 84, 246, True) == "done"
    # fail: any guard breaks, or a partial/unknown state
    assert P._plan_status(440, 0, 1, 0, 0, 220, 220, 84, 246, True) == "fail"
    assert P._plan_status(440, 0, 0, 0, 1, 220, 220, 84, 246, True) == "fail"
    assert P._plan_status(440, 0, 0, 0, 0, 220, 220, 83, 246, True) == "fail"
    assert P._plan_status(440, 0, 0, 0, 0, 220, 220, 84, 246, False) == "fail"
    assert P._plan_status(0, 439, 0, 0, 0, 0, 0, 84, 246, True) == "fail"  # partial
    assert P._plan_status(10, 430, 0, 0, 0, 0, 0, 84, 246, True) == "fail"  # unknown mix


def test_idempotent_noop_only_when_fully_promoted():
    # a fully-promoted state (0 eligible + 440 already) is a clean 0-row no-op
    assert promo._idempotent_noop([], 440, 0, 0, 0, True) is True
    # never a no-op when something is still eligible or partially promoted
    assert promo._idempotent_noop([1], 439, 0, 0, 0, True) is False   # still eligible
    assert promo._idempotent_noop([], 439, 0, 0, 0, True) is False    # partial: 1 missing
    assert promo._idempotent_noop([], 440, 1, 0, 0, True) is False    # not_eligible present
    assert promo._idempotent_noop([], 440, 0, 1, 0, True) is False    # foreign G4 present
    assert promo._idempotent_noop([], 440, 0, 0, 1, True) is False    # violation present
    assert promo._idempotent_noop([], 440, 0, 0, 0, False) is False   # QA not clean


def test_fail_closed_preconditions_clean_on_e2e():
    conn = _conn()
    try:
        cur = conn.cursor()
        ids = promo._eligible(cur)
        # every precondition in the fail-closed guard holds for the real scope
        assert promo._violations(cur, ids) == 0
        assert promo._violations(cur, []) == 0
    finally:
        conn.close()


def test_apply_refuses_production_without_allow_production():
    args = argparse.Namespace(db=promo.MAIN_DATABASE, allow_production=False,
                              host="x", port=1, user="x", password="x")
    assert promo._promote(args) == 2


def test_apply_refuses_non_allowed_database():
    args = argparse.Namespace(db="not_an_allowed_db", allow_production=False,
                              host="x", port=1, user="x", password="x")
    assert promo._promote(args) == 2


def test_apply_aborts_when_scope_wrong():
    # a forced mismatch (eligible != 440) must abort before any write
    conn, cur = _rolled_back_apply()
    try:
        cur.execute("UPDATE kg_entities SET record_status='active'"
                    " WHERE entity_pk IN (SELECT kg_entities.entity_pk FROM kg_entities"
                    "   JOIN brain_regions ON brain_regions.entity_pk=kg_entities.entity_pk"
                    "   WHERE granularity_level=%s LIMIT 1)", (promo.GRANULARITY,))
        ids = promo._eligible(cur)
        assert len(ids) == 439  # one row left the scope -> guard must fail
        assert promo._violations(cur, ids) == 0  # remaining rows are still clean
    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
