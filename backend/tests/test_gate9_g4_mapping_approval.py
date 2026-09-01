"""Gate 9 G4 — Julich-Brain v3.1 RegionMapping approval tests.

Narrow, provenance-locked assertions for the 440 direct exact RegionMapping approval:
eligible=440, only-Julich-v3.1 scope, only-G4 targets, exact-only, identity 440/440,
1:1 cardinality, pending->approved only (record_status unchanged), scientific fields
unchanged, G1/G3/G4 unchanged, idempotency (2nd PLAN eligible=0 / 2nd APPLY 0 rows),
production guard / fail-closed. The apply path runs inside a rolled-back transaction
so E2E state is never mutated.
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
    "apprm", BACKEND / "scripts" / "approve_julich_g4_region_mappings.py")
ap = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(ap)


def _conn():
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=E2E, autocommit=True)


# ---------------------------------------------------------------------------
# 1-4. Scope: eligible=440, Julich v3.1 only, G4 only, exact-only
# ---------------------------------------------------------------------------

def test_eligible_440():
    conn = _conn()
    try:
        cur = conn.cursor()
        ids = ap._eligible(cur)
        assert len(ids) == 440
        assert len(set(ids)) == 440
        assert ap._already(cur) == 0
        assert ap._conflict(cur) == 0
    finally:
        conn.close()


def test_only_julich_v31_exact_julich_direct_selected():
    conn = _conn()
    try:
        cur = conn.cursor()
        ids = ap._eligible(cur)
        cur.execute(
            "SELECT count(*) FROM region_mappings rm"
            " JOIN external_regions x ON x.entity_pk=rm.external_region_pk"
            " JOIN atlases a ON a.entity_pk=x.atlas_pk"
            " WHERE rm.entity_pk = ANY(%s) AND (a.atlas_family<>%s OR a.atlas_version<>%s"
            "  OR rm.mapping_type<>'exact' OR rm.mapping_source<>%s)",
            (ids, ap.ATLAS_FAMILY, ap.SOURCE_VERSION, ap.MAPPING_SOURCE))
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()


def test_only_g4_targets_selected():
    conn = _conn()
    try:
        cur = conn.cursor()
        ids = ap._eligible(cur)
        cur.execute(
            "SELECT count(*) FROM region_mappings rm JOIN brain_regions br"
            " ON br.entity_pk=rm.brain_region_pk WHERE rm.entity_pk = ANY(%s)"
            " AND br.granularity_level<>%s", (ids, ap.GRANULARITY))
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()


def test_no_non_exact_mappings():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT count(*) FROM region_mappings rm"
            " JOIN external_regions x ON x.entity_pk=rm.external_region_pk"
            " JOIN atlases a ON a.entity_pk=x.atlas_pk"
            " WHERE a.atlas_family='Julich-Brain' AND rm.mapping_type<>'exact'")
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 5-6. Identity exactness + 1:1 cardinality
# ---------------------------------------------------------------------------

def test_identity_source_ids_440_exact():
    conn = _conn()
    try:
        cur = conn.cursor()
        assert ap._identity_mismatch(cur) == 0
        assert ap._cardinality_violations(cur) == 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 7-10. Apply semantics (rolled-back transaction — E2E never mutated)
# ---------------------------------------------------------------------------

def _rolled_back_apply():
    conn = psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=E2E, autocommit=False)
    return conn, conn.cursor()


def test_pending_to_approved_only_record_status_unchanged():
    conn, cur = _rolled_back_apply()
    try:
        ids = ap._eligible(cur)
        assert len(ids) == 440
        cur.execute(ap.KG_APPROVE_SQL, (ap.REVIEWER, ap.NOTE, ids))
        assert cur.rowcount == 440
        cur.execute(ap.RM_APPROVE_SQL, (ids,))
        assert cur.rowcount == 440
        cur.execute("SELECT count(*) FROM kg_entities WHERE entity_pk = ANY(%s)"
                    " AND record_status='active' AND review_status='approved'"
                    " AND updated_by_agent=%s AND remark IS NOT NULL", (ids, ap.REVIEWER))
        assert cur.fetchone()[0] == 440
        cur.execute("SELECT count(*) FROM region_mappings WHERE entity_pk = ANY(%s)"
                    " AND review_status='approved'", (ids,))
        assert cur.fetchone()[0] == 440
    finally:
        conn.rollback()
        conn.close()


def test_mapping_scientific_fields_unchanged():
    conn, cur = _rolled_back_apply()
    try:
        ids = ap._eligible(cur)
        cols = ("rm.entity_pk, rm.external_region_pk, rm.brain_region_pk, rm.mapping_type,"
                " rm.mapping_source, x.source_region_id, km.name_en, km.name_zh,"
                " km.source_name_original, km.metadata_json")
        cur.execute("SELECT " + cols + " FROM region_mappings rm"
                    " JOIN external_regions x ON x.entity_pk=rm.external_region_pk"
                    " JOIN kg_entities km ON km.entity_pk=rm.entity_pk"
                    " WHERE rm.entity_pk = ANY(%s) ORDER BY rm.entity_pk", (ids,))
        before = cur.fetchall()
        cur.execute(ap.KG_APPROVE_SQL, (ap.REVIEWER, ap.NOTE, ids))
        cur.execute(ap.RM_APPROVE_SQL, (ids,))
        cur.execute("SELECT " + cols + " FROM region_mappings rm"
                    " JOIN external_regions x ON x.entity_pk=rm.external_region_pk"
                    " JOIN kg_entities km ON km.entity_pk=rm.entity_pk"
                    " WHERE rm.entity_pk = ANY(%s) ORDER BY rm.entity_pk", (ids,))
        assert before == cur.fetchall()  # no scientific/identity field changed
    finally:
        conn.rollback()
        conn.close()


def test_brain_regions_unchanged():
    # The mapping approval must not touch any BrainRegion lifecycle. Assert the
    # per-granularity (record_status, review_status) distribution is IDENTICAL
    # before and after the apply — whatever E2E's current promoted state is.
    conn, cur = _rolled_back_apply()
    try:
        ids = ap._eligible(cur)
        assert len(ids) == 440
        sql = ("SELECT br.granularity_level, ke.record_status, ke.review_status, count(*)"
               " FROM kg_entities ke JOIN brain_regions br ON br.entity_pk=ke.entity_pk"
               " GROUP BY 1,2,3 ORDER BY 1,2,3")
        cur.execute(sql)
        before = cur.fetchall()
        cur.execute(ap.KG_APPROVE_SQL, (ap.REVIEWER, ap.NOTE, ids))
        cur.execute(ap.RM_APPROVE_SQL, (ids,))
        cur.execute(sql)
        after = cur.fetchall()
        assert before == after  # BrainRegion lifecycle distribution unchanged
    finally:
        conn.rollback()
        conn.close()


# ---------------------------------------------------------------------------
# 11-12. Idempotency
# ---------------------------------------------------------------------------

def test_second_plan_after_approval_eligible_zero():
    conn, cur = _rolled_back_apply()
    try:
        ids = ap._eligible(cur)
        assert len(ids) == 440
        cur.execute(ap.KG_APPROVE_SQL, (ap.REVIEWER, ap.NOTE, ids))
        cur.execute(ap.RM_APPROVE_SQL, (ids,))
        assert ap._eligible(cur) == []
        assert ap._already(cur) == 440
        assert ap._conflict(cur) == 0
    finally:
        conn.rollback()
        conn.close()


def test_second_apply_idempotent_noop():
    assert ap._already_fully_approved([], 440, 0, 0, 0, 0) is True
    assert ap._already_fully_approved([1], 439, 0, 0, 0, 0) is False   # still eligible
    assert ap._already_fully_approved([], 439, 0, 0, 0, 0) is False    # partial
    assert ap._already_fully_approved([], 440, 0, 0, 1, 0) is False    # identity mismatch


# ---------------------------------------------------------------------------
# 13. Guard / fail-closed
# ---------------------------------------------------------------------------

def test_apply_refuses_production_without_allow_production():
    args = argparse.Namespace(db=ap.MAIN_DATABASE, allow_production=False,
                              host="x", port=1, user="x", password="x")
    assert ap._approve(args) == 2


def test_apply_refuses_non_allowed_database():
    args = argparse.Namespace(db="not_an_allowed_db", allow_production=False,
                              host="x", port=1, user="x", password="x")
    assert ap._approve(args) == 2


def test_apply_aborts_when_scope_wrong():
    conn, cur = _rolled_back_apply()
    try:
        # move one mapping out of the pending scope -> guard must fail
        cur.execute("UPDATE region_mappings SET review_status='uncertain'"
                    " WHERE entity_pk IN (SELECT rm.entity_pk FROM region_mappings rm"
                    "   JOIN external_regions x ON x.entity_pk=rm.external_region_pk"
                    "   JOIN atlases a ON a.entity_pk=x.atlas_pk"
                    "   WHERE a.atlas_family='Julich-Brain' LIMIT 1)")
        ids = ap._eligible(cur)
        assert len(ids) == 439
        assert ap._conflict(cur) == 1
        assert ap._identity_mismatch(cur) == 0  # remaining rows still identity-clean
    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
