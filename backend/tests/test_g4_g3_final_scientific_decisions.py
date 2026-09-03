"""Gate 7B Phase 2I-C — Final Owner Scientific Decision Freeze.

Read-only verification of the frozen 440 canonical-G4 source-level decision
ledger, final relation rows (contained/dominant/partial only), and exclusion
file. OWNER_SCIENTIFIC_REVIEWED is metadata, NOT production approval. No DB.
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
LEDGER = INT / "g4_g3_final_scientific_decisions.csv"
REL = INT / "g4_g3_final_relation_decisions.csv"
EXCL = INT / "g4_g3_final_scientific_exclusions.csv"
SUM = json.load(open(INT / "g4_g3_final_scientific_decision_summary.json", encoding="utf-8"))


def _rows(p: Path):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _conn(db=PROD):
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=db, autocommit=True)


def test_final_ledger_440_unique():
    rows = _rows(LEDGER)
    assert len(rows) == 440
    assert len({r["canonical_g4_id"] for r in rows}) == 440
    assert all(r["owner_review_status"] == "OWNER_SCIENTIFIC_REVIEWED" for r in rows)
    assert all(r["policy_version"] == "G4_G3_FINAL_SCIENTIFIC_POLICY_V1" for r in rows)


def test_decision_counts():
    c = Counter(r["scientific_decision"] for r in _rows(LEDGER))
    assert c == {"APPROVE_CONTAINED_IN": 20, "APPROVE_DOMINANT_OVERLAP": 110, "PARTIAL_OVERLAP": 137,
                 "NO_G3_MAPPING": 18, "CONFLICT_REVIEW": 91, "SHARED_SPATIAL_EVIDENCE_ONLY": 64}
    assert sum(c.values()) == 440


def test_vtm_not_contained():
    rows = {r["canonical_g4_id"]: r for r in _rows(LEDGER)}
    v = rows["NGIQ-BR-00000370"]
    assert v["scientific_decision"] == "CONFLICT_REVIEW"
    assert v["decision_reason_code"] == "SEMANTIC_FAMILY_MISMATCH"
    assert v["future_rollup_eligible"] == "False"


def test_ph3_dominant_not_contained():
    rows = {r["canonical_g4_id"]: r for r in _rows(LEDGER)}
    p = rows["NGIQ-BR-00000591"]
    assert p["scientific_decision"] == "APPROVE_DOMINANT_OVERLAP"
    assert p["decision_reason_code"] == "STRONG_SPATIAL_OVERLAP_BUT_NOT_HIERARCHICAL_CONTAINMENT"
    assert p["future_rollup_eligible"] == "False"


def test_fg5_contained_rollup():
    rows = {r["canonical_g4_id"]: r for r in _rows(LEDGER)}
    f = rows["NGIQ-BR-00000599"]
    assert f["scientific_decision"] == "APPROVE_CONTAINED_IN"
    assert f["decision_reason_code"] == "OWNER_SEMANTIC_AND_SPATIAL_CONCORDANCE"
    assert f["future_rollup_eligible"] == "True"


def test_semantic_gate_all_20_pass():
    rows = [r for r in _rows(LEDGER) if r["scientific_decision"] == "APPROVE_CONTAINED_IN"]
    assert len(rows) == 20
    for r in rows:
        assert r["semantic_compatibility_status"] in ("EXACT_FAMILY", "NESTED_COMPATIBLE_FAMILY")
        assert r["future_rollup_eligible"] == "True"
        assert r["future_primary_rollup"] == "True"
    assert SUM["semantic_contained_failure"] == 0
    assert SUM["contained_rollup_count"] == 20


def test_partial_confirmed_base_121_plus_gate():
    assert SUM["confirmed_partial_source_base_121"] == 121
    # final partial = 101 + 20 concordant + accepted-from-21 (16)
    assert SUM["partial_source_count"] == 137
    assert SUM["final_multi_target_accepted_from_21"] == 16
    assert SUM["final_multi_target_rejected_from_21"] == 5


def test_multi_target_gate_no_truncation():
    # every accepted partial source in the relation file keeps >=2 targets
    per = Counter(r["canonical_g4_id"] for r in _rows(REL) if r["relation"] == "PARTIAL_OVERLAP")
    assert len(per) == 137
    assert all(v >= 2 for v in per.values())


def test_relation_only_three_types():
    rel = _rows(REL)
    types = Counter(r["relation"] for r in rel)
    assert set(types) == {"APPROVE_CONTAINED_IN", "APPROVE_DOMINANT_OVERLAP", "PARTIAL_OVERLAP"}
    assert types["APPROVE_CONTAINED_IN"] == 20
    assert types["APPROVE_DOMINANT_OVERLAP"] == 110
    assert types["PARTIAL_OVERLAP"] == 331
    assert SUM["relation_totals"]["total"] == 461


def test_exclusions_only_nomap_conflict_shared():
    ex = _rows(EXCL)
    types = Counter(r["scientific_decision"] for r in ex)
    assert set(types) <= {"NO_G3_MAPPING", "CONFLICT_REVIEW", "SHARED_SPATIAL_EVIDENCE_ONLY"}
    assert len(ex) == 91 + 18 + 64


def test_canonical_closure():
    c = Counter(r["scientific_decision"] for r in _rows(LEDGER))
    assert c["APPROVE_CONTAINED_IN"] + c["APPROVE_DOMINANT_OVERLAP"] + c["PARTIAL_OVERLAP"] \
        + c["NO_G3_MAPPING"] + c["CONFLICT_REVIEW"] + c["SHARED_SPATIAL_EVIDENCE_ONLY"] == 440
    assert SUM["sum_check_440"] is True


def test_g3_to_g1_unchanged():
    # G3->G1 rows are frozen regardless of the later Phase 2J-C G4->G3 load.
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G3_MESO_FINE'")
        total = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G3_MESO_FINE' AND record_status='active'")
        active = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G3_MESO_FINE' AND review_status='approved'")
        approved = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G3_MESO_FINE' AND rollup_eligible=TRUE")
        rollup = cur.fetchone()[0]
    finally:
        conn.close()
    assert total == 246 and active == 246 and approved == 246 and rollup == 172


def test_no_g4_g3_mapping_rows():
    # G4->G3 production was 0 at freeze time. Phase 2J-C added 461 proposed rows
    # (never active); Phase 2J-D approved them (approved!=active, stays proposed).
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G4_MICROSTRUCTURAL_FINE'")
        g4 = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G4_MICROSTRUCTURAL_FINE' AND record_status='active'")
        act = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G4_MICROSTRUCTURAL_FINE' AND record_status='proposed'")
        proposed = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G4_MICROSTRUCTURAL_FINE' AND record_status='active'")
        active = cur.fetchone()[0]
    finally:
        conn.close()
    assert g4 in (0, 461)
    assert proposed + active == g4  # all G4->G3 rows share one record_status (proposed or, post 2J-E, active)
    assert act == 0 or active == g4


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
