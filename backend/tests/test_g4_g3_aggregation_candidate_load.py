"""Gate 7B Phase 2J-C — G4→G3 Aggregation Candidate Load (post-load QA).

Verifies the 461 loaded G4→G3 production rows (proposed/pending/FALSE/FALSE),
full-table state (707), G3→G1 protection, idempotent rerun manifest, coverage /
provenance fidelity and exclusion leak = 0.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import psycopg
import pytest

BACKEND = Path(__file__).resolve().parents[1]
PROD = "neurographiq_human_brain_v1"
INT = BACKEND / "data" / "integration"
STAGE = INT / "g4_g3_mapping_candidate_staging.csv"
MANIFEST = json.load(open(INT / "g4_g3_candidate_load_manifest.json", encoding="utf-8"))
G4 = "G4_MICROSTRUCTURAL_FINE"


def _rows(p: Path):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _conn(db=PROD):
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=db, autocommit=True)


def _g4(cur, col="count(*)", extra=""):
    cur.execute(f"SELECT {col} FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s {extra}", (G4,))
    return cur.fetchone()[0]


def test_first_load_inserted_461():
    assert MANIFEST["attempted"] == 461
    assert MANIFEST["inserted"] == 461  # preserved first-load count
    assert MANIFEST["skipped_existing"] == 0
    assert MANIFEST["failed"] == 0
    assert MANIFEST["postload_g4_g3_count"] == 461


def test_production_g4_461():
    conn = _conn()
    try:
        cur = conn.cursor()
        assert _g4(cur) == 461
    finally:
        conn.close()


def test_relation_distribution():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT mapping_relation, count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s GROUP BY 1", (G4,))
        c = dict(cur.fetchall())
        assert c == {"contained_in": 20, "dominant_overlap": 110, "partial_overlap": 331}
    finally:
        conn.close()


def test_mapped_sources_267():
    conn = _conn()
    try:
        cur = conn.cursor()
        assert _g4(cur, "count(DISTINCT source_region_pk)") == 267
    finally:
        conn.close()


def test_lifecycle_counts():
    # Load gate wrote proposed/pending; Phase 2J-D later approved them (still proposed).
    conn = _conn()
    try:
        cur = conn.cursor()
        assert _g4(cur) == 461
        prop = _g4(cur, extra="AND record_status='proposed'")
        act = _g4(cur, extra="AND record_status='active'")
        assert prop + act == 461          # proposed at load; promoted later
        assert (prop, act) in ((461, 0), (0, 461))
        rollup = _g4(cur, extra="AND rollup_eligible=TRUE")
        primary = _g4(cur, extra="AND is_primary_rollup=TRUE")
        assert rollup == primary in (0, 20)   # 0 at load; 20 contained after Phase 2J-E
        pend = _g4(cur, extra="AND review_status='pending'")
        appr = _g4(cur, extra="AND review_status='approved'")
        assert (pend, appr) in ((461, 0), (0, 461))
    finally:
        conn.close()


def test_identity_exact():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT b.source_region_pk, b.target_region_pk, k1.entity_id, k2.entity_id "
                    f"FROM brain_region_aggregation_mappings b "
                    f"JOIN kg_entities k1 ON k1.entity_pk=b.source_region_pk "
                    f"JOIN kg_entities k2 ON k2.entity_pk=b.target_region_pk "
                    f"WHERE b.source_granularity_level=%s AND b.target_granularity_level='G3_MESO_FINE'", (G4,))
        rows = cur.fetchall()
        assert len(rows) == 461
        assert all(r[2].startswith("NGIQ-BR-") and r[3].startswith("NGIQ-BR-") for r in rows)
    finally:
        conn.close()


def test_duplicate_zero():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT source_region_pk, target_region_pk, mapping_relation, count(*) FROM "
                    f"brain_region_aggregation_mappings WHERE source_granularity_level=%s "
                    f"GROUP BY 1,2,3 HAVING count(*)>1", (G4,))
        assert cur.fetchall() == []
    finally:
        conn.close()


def test_coverage_fidelity():
    # compare DB coverage to staging source/target values (loaded unchanged)
    conn = _conn()
    stage = {r["candidate_id"]: r for r in _rows(STAGE)}
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT provenance_json->>'staging_candidate_id', source_coverage_ratio, target_coverage_ratio, "
                    f"spatial_overlap_ratio, mapping_confidence, record_status, review_status, "
                    f"rollup_eligible, is_primary_rollup FROM brain_region_aggregation_mappings "
                    f"WHERE source_granularity_level=%s", (G4,))
        for cid, sc, tc, so, conf, rs, rv, re, prim in cur.fetchall():
            s = stage[cid]
            assert abs((sc or 0) - (float(s["source_coverage_ratio"]) if s["source_coverage_ratio"] else 0)) < 1e-6
            assert abs((tc or 0) - (float(s["target_coverage_ratio"]) if s["target_coverage_ratio"] else 0)) < 1e-6
            assert so is None and conf is None
            assert rs in ("proposed", "active")  # proposed at load; active after Phase 2J-E
            assert rv in ("pending", "approved")
            assert re == prim  # rollup/primary stay paired; TRUE only on the 20 contained (post 2J-E)
    finally:
        conn.close()


def test_provenance_complete():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT provenance_json FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s", (G4,))
        for (p,) in cur.fetchall():
            prov = p if isinstance(p, dict) else json.loads(p)
            assert prov["final_scientific_policy"] == "G4_G3_FINAL_SCIENTIFIC_POLICY_V1"
            assert prov["load_phase"] == "G4_G3_AGGREGATION_CANDIDATE_LOAD_V1"
            assert prov["human_reviewed"] is False
            assert prov["expert_approved"] is False
            assert prov["production_review_status"] == "pending"
    finally:
        conn.close()


def test_exclusion_leak_0():
    assert MANIFEST["exclusion_leak"] == 0


def test_rerun_idempotent_manifest():
    ro = MANIFEST["rerun_observations"]
    assert len(ro) >= 1
    assert ro[-1]["inserted"] == 0
    assert ro[-1]["skipped_existing"] == 461
    assert ro[-1]["failed"] == 0
    assert MANIFEST["rerun_idempotent"] is True
    # first-load numbers preserved at top level
    assert MANIFEST["inserted"] == 461 and MANIFEST["skipped_existing"] == 0


def test_total_aggregation_707():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings")
        total = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G3_MESO_FINE'")
        g3 = cur.fetchone()[0]
        assert total == 707 and g3 == 246
    finally:
        conn.close()


def test_g3_to_g1_unchanged():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G3_MESO_FINE' AND record_status='active'")
        active = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G3_MESO_FINE' AND review_status='approved'")
        approved = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G3_MESO_FINE' AND rollup_eligible=TRUE")
        rollup = cur.fetchone()[0]
    finally:
        conn.close()
    assert active == 246 and approved == 246 and rollup == 172
    assert MANIFEST["g3_g1_before"] == MANIFEST["g3_g1_after"] == \
        {"total": 246, "active": 246, "approved": 246, "rollup": 172}


def test_no_unintended_update_delete():
    # every G3->G1 row unchanged marker: count under g3 load_phase stays 246
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE provenance_json->>'load_phase'='G3_G1_AGGREGATION_CANDIDATE_LOAD_V1'")
        assert cur.fetchone()[0] == 246
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE mapping_id LIKE 'NGIQ-BRAM-%'")
        assert cur.fetchone()[0] == 707
    finally:
        conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
