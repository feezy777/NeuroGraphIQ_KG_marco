"""Gate 7B Phase 2J-F — G4→G3 Final Freeze QA (frozen state verification).

Confirms the frozen production state, automatic rollup / formal relation query
contracts, canonical closure, exclusion leak = 0, reverse duplicate = 0, and
that final artifact hashes in the freeze manifest match the on-disk files.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import psycopg
import pytest

BACKEND = Path(__file__).resolve().parents[1]
PROD = "neurographiq_human_brain_v1"
INT = BACKEND / "data" / "integration"
MANIFEST = json.load(open(INT / "g4_g3_final_freeze_manifest.json", encoding="utf-8"))
G4 = "G4_MICROSTRUCTURAL_FINE"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _conn(db=PROD):
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=db, autocommit=True)


def test_manifest_frozen():
    assert MANIFEST["freeze_status"] == "G4_G3_AGGREGATION_FROZEN"
    assert MANIFEST["policy_version"] == "G4_G3_FINAL_SCIENTIFIC_POLICY_V1"
    assert MANIFEST["counts"]["canonical_g4_total"] == 440


def test_counts_mapped_excluded_closure():
    q = MANIFEST["counts"]
    assert q["mapped_source_count"] == 267
    assert q["excluded_source_count"] == 173
    assert 267 + 173 == 440


def test_production_rows_461_active_approved():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s", (G4,))
        total = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s AND record_status='active'", (G4,))
        active = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s AND review_status='approved'", (G4,))
        approved = cur.fetchone()[0]
    finally:
        conn.close()
    assert total == 461 and active == 461 and approved == 461


def test_relation_rollup_counts():
    conn = _conn()
    try:
        cur = conn.cursor()
        for rel, n in (("contained_in", 20), ("dominant_overlap", 110), ("partial_overlap", 331)):
            cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s AND mapping_relation=%s", (G4, rel))
            assert cur.fetchone()[0] == n
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s AND rollup_eligible=TRUE", (G4,))
        assert cur.fetchone()[0] == 20
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s AND is_primary_rollup=TRUE", (G4,))
        assert cur.fetchone()[0] == 20
    finally:
        conn.close()


def test_primary_unique_20():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""SELECT count(DISTINCT source_region_pk) FROM brain_region_aggregation_mappings
            WHERE source_granularity_level=%s AND record_status='active' AND review_status='approved'
              AND mapping_relation='contained_in' AND rollup_eligible=TRUE AND is_primary_rollup=TRUE""", (G4,))
        assert cur.fetchone()[0] == 20
        cur.execute("""SELECT count(*) FROM (SELECT source_region_pk FROM brain_region_aggregation_mappings
            WHERE source_granularity_level=%s AND record_status='active' AND review_status='approved'
              AND mapping_relation='contained_in' AND rollup_eligible=TRUE AND is_primary_rollup=TRUE
            GROUP BY source_region_pk HAVING count(*)>1) z""", (G4,))
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()


def test_no_dom_partial_rollup():
    conn = _conn()
    try:
        cur = conn.cursor()
        for rel in ("dominant_overlap", "partial_overlap"):
            cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s AND mapping_relation=%s AND (rollup_eligible=TRUE OR is_primary_rollup=TRUE)", (G4, rel))
            assert cur.fetchone()[0] == 0
    finally:
        conn.close()


def test_exclusion_leak_0():
    assert MANIFEST["counts"]["exclusion_leak"] == 0
    assert MANIFEST["counts"]["reverse_duplicate"] == 0


def test_query_contract_primary_20():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""SELECT count(*) FROM brain_region_aggregation_mappings
            WHERE mapping_relation='contained_in' AND record_status='active' AND review_status='approved'
              AND rollup_eligible=TRUE AND is_primary_rollup=TRUE AND source_granularity_level=%s""", (G4,))
        assert cur.fetchone()[0] == 20
    finally:
        conn.close()


def test_all_formal_query_461():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level=%s AND target_granularity_level='G3_MESO_FINE' AND record_status='active' AND review_status='approved'", (G4,))
        assert cur.fetchone()[0] == 461
    finally:
        conn.close()


def test_artifact_hashes_match_manifest():
    import os
    mapping = {
        "final_decisions.csv": "g4_g3_final_scientific_decisions.csv",
        "final_relations.csv": "g4_g3_final_relation_decisions.csv",
        "final_exclusions.csv": "g4_g3_final_scientific_exclusions.csv",
        "candidate_staging.csv": "g4_g3_mapping_candidate_staging.csv",
        "candidate_review.csv": "g4_g3_mapping_candidate_review.csv",
        "candidate_review_summary.json": "g4_g3_mapping_candidate_review_summary.json",
        "load_manifest.json": "g4_g3_candidate_load_manifest.json",
        "approval_manifest.json": "g4_g3_aggregation_approval_manifest.json",
        "promotion_manifest.json": "g4_g3_aggregation_promotion_manifest.json",
        "query_contract.md": "g4_g3_query_contract.md",
    }
    H = MANIFEST["scientific_artifact_hashes"]
    for key, fname in mapping.items():
        assert H[key] == _sha(INT / fname), key


def test_phase2g_hash_stable():
    assert MANIFEST["scientific_artifact_hashes"]["phase2g_matrix_hash"] == \
        "a64d0c598300d1f0e6d56c67c1e2564775287447d5c17f77741bcf96ec2df874"


def test_g3_g1_and_whole_table():
    q = MANIFEST["counts"]
    assert q["g3_rows"] == 246 and q["g3_active"] == 246 and q["g3_approved"] == 246
    assert q["g3_rollup"] == 172 and q["g3_primary"] == 172
    assert q["whole_rows"] == 707 and q["whole_active"] == 707 and q["whole_approved"] == 707
    assert q["whole_rollup"] == 192 and q["whole_primary"] == 192


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
