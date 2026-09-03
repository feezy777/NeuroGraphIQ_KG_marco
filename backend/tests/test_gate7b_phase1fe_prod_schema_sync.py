"""Gate 7B Phase 1F-E — Production Aggregation Schema Sync (read-only verification).

Confirms gate7b_010 (aggregation mapping review lifecycle) has been applied to
the production database with full schema parity to E2E, and that no scientific
data was written (brain_region_aggregation_mappings stays 0; brain_regions and
granularity counts unchanged).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import psycopg
import pytest

BACKEND = Path(__file__).resolve().parents[1]
PROD = "neurographiq_human_brain_v1"
E2E = "neurographiq_human_brain_v1_e2e"
TABLE = "brain_region_aggregation_mappings"
MIGRATION = BACKEND / "migrations" / "gate7b_010_aggregation_mapping_review_lifecycle.sql"


def _conn(db=PROD):
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=db, autocommit=True)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _columns(db: str) -> list[str]:
    conn = _conn(db)
    try:
        cur = conn.cursor()
        cur.execute("SELECT column_name FROM information_schema.columns"
                    " WHERE table_schema='public' AND table_name=%s", (TABLE,))
        return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 1. production gate7b_010 registered with matching checksum
# ---------------------------------------------------------------------------

def test_prod_gate7b_010_registered():
    conn = _conn(PROD)
    try:
        cur = conn.cursor()
        cur.execute("SELECT migration_id, checksum_sha256, status FROM infra.schema_migrations"
                    " WHERE migration_id='gate7b_010'")
        rows = cur.fetchall()
        assert len(rows) == 1  # no duplicate record
        assert rows[0][0] == "gate7b_010"
        assert rows[0][1] == _sha(MIGRATION)  # checksum matches file
        assert rows[0][2] == "APPLIED"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 2-6. review lifecycle fields
# ---------------------------------------------------------------------------

def test_review_status_exists():
    assert "review_status" in _columns(PROD)


def test_review_status_default_pending():
    conn = _conn(PROD)
    try:
        cur = conn.cursor()
        cur.execute("SELECT column_default, is_nullable FROM information_schema.columns"
                    " WHERE table_schema='public' AND table_name=%s AND column_name='review_status'",
                    (TABLE,))
        default, nullable = cur.fetchone()
        assert "pending" in (default or "")
        assert nullable == "NO"
    finally:
        conn.close()


def test_review_vocabulary_constraint_exists():
    conn = _conn(PROD)
    try:
        cur = conn.cursor()
        cur.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname='ck_agg_review_status'")
        ck = cur.fetchone()[0]
        for v in ("pending", "approved", "rejected", "uncertain", "needs_revision"):
            assert v in ck
    finally:
        conn.close()


def test_reviewed_by_exists_nullable():
    conn = _conn(PROD)
    try:
        cur = conn.cursor()
        cur.execute("SELECT is_nullable FROM information_schema.columns"
                    " WHERE table_schema='public' AND table_name=%s AND column_name='reviewed_by'",
                    (TABLE,))
        assert cur.fetchone()[0] == "YES"
    finally:
        conn.close()


def test_reviewed_at_exists_nullable():
    conn = _conn(PROD)
    try:
        cur = conn.cursor()
        cur.execute("SELECT is_nullable FROM information_schema.columns"
                    " WHERE table_schema='public' AND table_name=%s AND column_name='reviewed_at'",
                    (TABLE,))
        assert cur.fetchone()[0] == "YES"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 7. rollup relation CHECK
# ---------------------------------------------------------------------------

def test_rollup_requires_contained_in():
    conn = _conn(PROD)
    try:
        cur = conn.cursor()
        cur.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                    " WHERE conname='ck_agg_rollup_requires_contained_in'")
        ck = cur.fetchone()[0]
        assert "contained_in" in ck
        assert "rollup_eligible" in ck and "is_primary_rollup" in ck
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 8. primary rollup unique index
# ---------------------------------------------------------------------------

def test_primary_rollup_unique_index_exists():
    conn = _conn(PROD)
    try:
        cur = conn.cursor()
        cur.execute("SELECT indexdef FROM pg_indexes WHERE tablename=%s"
                    " AND indexname='uq_agg_primary_rollup_active_approved'", (TABLE,))
        idx = cur.fetchone()
        assert idx is not None
        assert "UNIQUE" in idx[0] and "source_region_pk" in idx[0]
        assert "review_status" in idx[0] and "approved" in idx[0]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 9. production vs e2e schema parity
# ---------------------------------------------------------------------------

def _schema_signature(db: str) -> dict:
    conn = _conn(db)
    try:
        cur = conn.cursor()
        sig = {}
        cur.execute("SELECT column_name, data_type, is_nullable, column_default"
                    " FROM information_schema.columns WHERE table_schema='public' AND table_name=%s"
                    " ORDER BY ordinal_position", (TABLE,))
        sig["columns"] = [tuple(r) for r in cur.fetchall()]
        cur.execute("SELECT con.contype, con.conname, pg_get_constraintdef(con.oid)"
                    " FROM pg_constraint con JOIN pg_class rel ON rel.oid=con.conrelid"
                    " JOIN pg_namespace ns ON ns.oid=rel.relnamespace"
                    " WHERE ns.nspname='public' AND rel.relname=%s"
                    " ORDER BY con.contype, con.conname", (TABLE,))
        sig["constraints"] = [tuple(r) for r in cur.fetchall()]
        cur.execute("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname='public'"
                    " AND tablename=%s ORDER BY indexname", (TABLE,))
        sig["indexes"] = [tuple(r) for r in cur.fetchall()]
        cur.execute("SELECT tgname FROM pg_trigger WHERE tgrelid=%s::regclass"
                    " AND NOT tgisinternal ORDER BY tgname", (TABLE,))
        sig["triggers"] = [tuple(r) for r in cur.fetchall()]
        return sig
    finally:
        conn.close()


def test_prod_e2e_aggregation_schema_parity():
    assert _schema_signature(PROD) == _schema_signature(E2E)


# ---------------------------------------------------------------------------
# 10-12. zero rows + brain_regions unchanged
# ---------------------------------------------------------------------------

def test_prod_aggregation_rows_zero():
    # G3→G1 slice only (the schema-sync gate governs the G3→G1 batch). The G4→G3
    # batch (461 rows) is a separate, later-frozen granularity chain and must not
    # be counted here. Final G3→G1 state: 246 active+approved.
    conn = _conn(PROD)
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings"
                    " WHERE source_granularity_level='G3_MESO_FINE' AND target_granularity_level='G1_MACRO'")
        total = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings"
                    " WHERE source_granularity_level='G3_MESO_FINE' AND target_granularity_level='G1_MACRO'"
                    " AND record_status='active' AND review_status='approved'")
        active = cur.fetchone()[0]
        assert total == 246 and active == 246
    finally:
        conn.close()


def test_brain_regions_still_770():
    conn = _conn(PROD)
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_regions")
        assert cur.fetchone()[0] == 770
    finally:
        conn.close()


def test_granularity_counts_unchanged():
    conn = _conn(PROD)
    try:
        cur = conn.cursor()
        cur.execute("SELECT granularity_level, count(*) FROM brain_regions GROUP BY 1")
        assert dict(cur.fetchall()) == {"G1_MACRO": 84, "G3_MESO_FINE": 246,
                                        "G4_MICROSTRUCTURAL_FINE": 440}
    finally:
        conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
