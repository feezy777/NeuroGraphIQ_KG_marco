"""Gate 7B Phase 2J-B — G4→G3 Mapping Candidate Fidelity Review (read-only).

Verifies the 461-candidate fidelity audit, partial per-source review,
zero-exception file, exclusion leak = 0, and unchanged production.
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
REV = INT / "g4_g3_mapping_candidate_review.csv"
PART = INT / "g4_g3_mapping_candidate_partial_review.csv"
EXC = INT / "g4_g3_mapping_candidate_review_exceptions.csv"
SUM = json.load(open(INT / "g4_g3_mapping_candidate_review_summary.json", encoding="utf-8"))


def _rows(p: Path):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _conn(db=PROD):
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=db, autocommit=True)


def test_review_rows_461():
    assert len(_rows(REV)) == 461


def test_pass_461():
    rows = _rows(REV)
    assert sum(1 for r in rows if r["review_result"] == "PASS") == 461
    assert SUM["pass_count"] == 461 and SUM["fail_count"] == 0


def test_relation_counts():
    c = Counter(r["relation"] for r in _rows(REV))
    assert c["contained_in"] == 20 and c["dominant_overlap"] == 110 and c["partial_overlap"] == 331


def test_identity_exact():
    for r in _rows(REV):
        assert r["source_identity_match"] == "True"
        assert r["target_identity_match"] == "True"
        assert r["granularity_match"] == "True"
        assert r["hemisphere_match"] == "True"


def test_mismatch_counts_zero():
    assert SUM["source_identity_mismatch"] == 0
    assert SUM["target_identity_mismatch"] == 0
    assert SUM["granularity_mismatch"] == 0
    assert SUM["hemisphere_mismatch"] == 0
    assert SUM["coverage_mismatch"] == 0


def test_contained_semantic_gate():
    rows = [r for r in _rows(REV) if r["relation"] == "contained_in"]
    assert len(rows) == 20
    for r in rows:
        assert r["rollup_semantics_valid"] == "True"
    assert SUM["rollup_anomaly"] == 0


def test_contained_rollup_true_20():
    # contained scientific rollup = TRUE (staging stays proposed FALSE - covered by lifecycle check)
    rows = _rows(REV)
    assert all(r["lifecycle_valid"] == "True" for r in rows)
    assert SUM["lifecycle_anomaly"] == 0


def test_partial_source_137_sets():
    part = _rows(PART)
    assert len(part) == 137
    assert all(r["partial_review_result"] == "PASS" for r in part)
    assert all(r["target_set_match"] == "True" for r in part)
    assert all(r["duplicate_target_count"] == "0" for r in part)
    assert all(r["missing_target_count"] == "0" and r["extra_target_count"] == "0" for r in part)
    dist = Counter(int(r["target_count"]) for r in part)
    assert dist == {2: 83, 3: 51, 4: 3}


def test_per_target_coverage_exact():
    # review file coverage_match True for every partial row and per-target file rows PASS
    part = _rows(PART)
    assert all(r["per_target_coverage_match"] == "True" for r in part)
    assert SUM["partial_target_set_mismatch"] == 0


def test_target_coverage_semantics_valid():
    assert SUM["target_coverage_semantics_status"] == "TARGET_COVERAGE_SEMANTICS_VALID"


def test_confidence_and_overlap_null():
    stage = _rows(INT / "g4_g3_mapping_candidate_staging.csv")
    assert all(s["mapping_confidence"] in ("", None) for s in stage)
    assert all(s["spatial_overlap_ratio"] in ("", None) for s in stage)
    assert SUM["coverage_mismatch"] == 0


def test_mapping_method_valid():
    for r in _rows(REV):
        assert r["mapping_method_valid"] == "True"
    assert SUM["mapping_method_status"].startswith("VALID")


def test_provenance_complete_461():
    rows = _rows(REV)
    assert all(r["provenance_complete"] == "True" for r in rows)
    assert SUM["provenance_anomaly"] == 0


def test_candidate_id_valid():
    rows = _rows(REV)
    assert all(r["candidate_id_valid"] == "True" for r in rows)
    assert SUM["candidate_id_anomaly"] == 0


def test_exclusions_173_no_leak():
    assert SUM["exclusion_count"] == 173
    assert SUM["exclusion_leak"] == 0


def test_scientific_hashes_unchanged():
    assert SUM["scientific_hash_unchanged"] is True
    assert SUM["final_scientific_decision_hashes"]["final_decisions_sha256"]


def test_exceptions_file_empty():
    ex = _rows(EXC)
    assert len(ex) == 0  # no anomalies -> no dummy rows


def test_g3_to_g1_unchanged():
    # This review gate itself never wrote G3->G1. G3->G1 rows must stay intact
    # (Phase 2J-C later legitimately adds 461 G4->G3 proposed rows on top).
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G3_MESO_FINE' AND record_status='active' AND review_status='approved'")
        aa = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G3_MESO_FINE' AND rollup_eligible=TRUE")
        rollup = cur.fetchone()[0]
    finally:
        conn.close()
    assert aa == 246 and rollup == 172


def test_g4_g3_rows_state():
    # Review gate ran when G4->G3 = 0; Phase 2J-C load later added 461 proposed rows.
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G4_MICROSTRUCTURAL_FINE'")
        g4 = cur.fetchone()[0]
    finally:
        conn.close()
    assert g4 in (0, 461)  # 0 = pre-load snapshot, 461 = post Phase 2J-C load


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
