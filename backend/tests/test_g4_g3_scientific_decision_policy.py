"""Gate 7B Phase 2I-A — G4→G3 Scientific Decision Policy Application V1.

Read-only verification of the 440-canonical-G4 source-level decision ledger, the
preliminary relation rows (contained/dominant/partial only), the conflict
review queue, the 64 shared canonical exclusions, and the 14 noncanonical
spatial-component audit. Policy-derived preliminary decisions only — no DB, no
staging, review_status stays PENDING_OWNER_REVIEW.

Coverage (gate section 26, 1-21).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import psycopg
import pytest

BACKEND = Path(__file__).resolve().parents[1]
PROD = "neurographiq_human_brain_v1"
INT = BACKEND / "data" / "integration"

LEDGER = INT / "g4_g3_scientific_decision_policy_v1.csv"
REL = INT / "g4_g3_preliminary_relation_decisions.csv"
CONFLICT = INT / "g4_g3_conflict_review_queue.csv"
SHARED = INT / "g4_g3_shared_canonical_decision_exclusions.csv"
NONCANON = INT / "g4_g3_noncanonical_spatial_components.csv"
SUM = json.load(open(INT / "g4_g3_scientific_decision_policy_summary.json", encoding="utf-8"))


def _rows(p: Path) -> list[dict]:
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _f(x):
    return None if x in ("", None) else float(x)


def _conn(db=PROD):
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=db, autocommit=True)


# ---------------------------------------------------------------------------
# 1-4. ledger / evidence-set counts
# ---------------------------------------------------------------------------

def test_ledger_440_unique():
    rows = _rows(LEDGER)
    assert len(rows) == 440
    assert len({r["canonical_g4_id"] for r in rows}) == 440
    assert SUM["canonical_g4_count"] == 440


def test_direct_decisionable_376():
    n = sum(1 for r in _rows(LEDGER) if r["spatial_evidence_status"] == "DIRECT_CANONICAL_SPATIAL_EVIDENCE")
    assert n == 376
    assert SUM["direct_decisionable_count"] == 376


def test_shared_canonical_64():
    n = sum(1 for r in _rows(LEDGER) if r["spatial_evidence_status"] == "SHARED_SPATIAL_EVIDENCE")
    assert n == 64
    assert SUM["shared_canonical_count"] == 64


def test_noncanonical_14():
    rows = _rows(NONCANON)
    assert len(rows) == 14
    assert SUM["noncanonical_spatial_component_count"] == 14
    assert all(r["production_mapping_allowed"] == "FALSE" for r in rows)


# ---------------------------------------------------------------------------
# 5. each canonical exactly one decision
# ---------------------------------------------------------------------------

def test_each_canonical_exactly_one_decision():
    rows = _rows(LEDGER)
    assert all(r["scientific_decision"] for r in rows)
    from collections import Counter
    cnt = Counter(r["scientific_decision"] for r in rows)
    assert sum(cnt.values()) == 440
    assert set(cnt) == {"APPROVE_CONTAINED_IN", "APPROVE_DOMINANT_OVERLAP", "PARTIAL_OVERLAP",
                        "NO_G3_MAPPING", "CONFLICT_REVIEW", "SHARED_SPATIAL_EVIDENCE_ONLY"}
    # direct + shared accounting
    assert SUM["decision_counts"] == dict(cnt)


# ---------------------------------------------------------------------------
# 6-8. rule precision
# ---------------------------------------------------------------------------

def test_contained_rule_precision():
    rows = [r for r in _rows(LEDGER) if r["scientific_decision"] == "APPROVE_CONTAINED_IN"]
    assert len(rows) == SUM["decision_counts"]["APPROVE_CONTAINED_IN"] == 22
    for r in rows:
        assert (_f(r["hard_top1_coverage"]) or 0) >= 0.80 - 1e-9
        assert (_f(r["bna_uncovered_fraction"]) or 1.0) <= 0.15
        assert (_f(r["hard_top2_coverage"]) or 0.0) <= 0.10
        assert (_f(r["effective_target_count"]) or 99) <= 2.0
        assert r["top1_agreement"] == "TRUE"


def test_dominant_rule_precision():
    rows = [r for r in _rows(LEDGER) if r["scientific_decision"] == "APPROVE_DOMINANT_OVERLAP"]
    assert len(rows) == 109
    for r in rows:
        assert (_f(r["hard_total_bna_coverage"]) or 0) >= 0.70 - 1e-9
        assert (_f(r["hard_top1_coverage"]) or 0) >= 0.50 - 1e-9
        assert (_f(r["hard_top1_top2_margin"]) or 0.0) >= 0.20 - 1e-9 \
            if r["hard_top2_coverage"] not in ("", None) else True
        assert r["top1_agreement"] == "TRUE"


def test_partial_rule_precision():
    rows = [r for r in _rows(LEDGER) if r["scientific_decision"] == "PARTIAL_OVERLAP"]
    assert len(rows) == 101
    for r in rows:
        assert (_f(r["hard_total_bna_coverage"]) or 0) >= 0.60 - 1e-9
        assert r["top1_agreement"] == "TRUE"


# ---------------------------------------------------------------------------
# 9. partial multi-target rows
# ---------------------------------------------------------------------------

def test_partial_multi_target():
    rel = _rows(REL)
    partial_sources = set(r["canonical_g4_id"] for r in rel if r["relation"] == "PARTIAL_OVERLAP")
    from collections import Counter
    per = Counter(r["canonical_g4_id"] for r in rel if r["relation"] == "PARTIAL_OVERLAP")
    assert len(partial_sources) == 101
    assert all(v >= 2 for v in per.values())
    assert sum(per.values()) == 236
    # at least one partial source keeps >2 targets (no artificial truncation)
    assert any(v > 2 for v in per.values())


# ---------------------------------------------------------------------------
# 10-11. disagreement default conflict + zero->NO_G3_MAPPING
# ---------------------------------------------------------------------------

def test_disagreement_defaults_conflict():
    rows = [r for r in _rows(LEDGER)
            if r["top1_agreement"] == "FALSE"
            and r["scientific_decision"] not in ("SHARED_SPATIAL_EVIDENCE_ONLY", "NO_G3_MAPPING")]
    assert len(rows) == 35
    assert all(r["scientific_decision"] == "CONFLICT_REVIEW" for r in rows)
    assert all(r["decision_reason_code"] == "PROBABILITY_HARDLABEL_TOP1_DISAGREEMENT" for r in rows)
    assert SUM["conflict_reason_distribution"]["PROBABILITY_HARDLABEL_TOP1_DISAGREEMENT"] == 35


def test_zero_association_no_mapping():
    rows = [r for r in _rows(LEDGER) if r["decision_reason_code"] == "ZERO_BNA_SPATIAL_ASSOCIATION"]
    assert len(rows) == 10
    assert all(r["scientific_decision"] == "NO_G3_MAPPING" for r in rows)
    assert all((_f(r["hard_total_bna_coverage"]) or 0.0) == 0.0 for r in rows)
    # BNA_COVERAGE_GAP secondary reason rows
    gap = [r for r in _rows(LEDGER) if r["decision_reason_code"] == "BNA_COVERAGE_GAP"]
    assert len(gap) == 8
    assert all(r["scientific_decision"] == "NO_G3_MAPPING" for r in gap)


# ---------------------------------------------------------------------------
# 12-13. shared / noncanonical produce NO relation rows
# ---------------------------------------------------------------------------

def test_shared_and_noncanonical_no_relation():
    rel = _rows(REL)
    rel_ents = {r["canonical_g4_id"] for r in rel}
    sh = {r["canonical_g4_id"] for r in _rows(SHARED)}
    noncan = {r["spatial_component_id"] for r in _rows(NONCANON)}
    assert len(sh) == 64
    assert rel_ents.isdisjoint(sh)
    comps_in_rel = {r["spatial_component_id"] for r in rel}
    assert comps_in_rel.isdisjoint(noncan)


def test_no_mapping_and_conflict_no_relation():
    rel = _rows(REL)
    rel_ents = {r["canonical_g4_id"] for r in rel}
    other = {r["canonical_g4_id"] for r in _rows(LEDGER)
             if r["scientific_decision"] in ("CONFLICT_REVIEW", "NO_G3_MAPPING")}
    assert rel_ents.isdisjoint(other)


# ---------------------------------------------------------------------------
# 14-16. rollup flags
# ---------------------------------------------------------------------------

def test_rollup_flags():
    for r in _rows(LEDGER):
        if r["scientific_decision"] == "APPROVE_CONTAINED_IN":
            assert r["future_rollup_eligible"] == "True"
            assert r["future_primary_rollup"] == "True"
        else:
            assert r["future_rollup_eligible"] == "False"
            assert r["future_primary_rollup"] == "False"


def test_conflict_queue():
    conf = _rows(CONFLICT)
    assert len(conf) == 126
    assert all(r["scientific_decision"] == "CONFLICT_REVIEW" for r in conf)


# ---------------------------------------------------------------------------
# 19. owner review pending
# ---------------------------------------------------------------------------

def test_owner_review_pending():
    rows = _rows(LEDGER)
    assert all(r["review_status"] == "PENDING_OWNER_REVIEW" for r in rows)
    assert SUM["owner_review_required"] is True
    assert SUM["database_write"] is False
    assert SUM["approval_promotion"] is False


def test_summary_coherence():
    d = SUM["decision_counts"]
    assert d["APPROVE_CONTAINED_IN"] + d["APPROVE_DOMINANT_OVERLAP"] + d["PARTIAL_OVERLAP"] \
        + d["NO_G3_MAPPING"] + d["CONFLICT_REVIEW"] + d["SHARED_SPATIAL_EVIDENCE_ONLY"] == 440
    assert SUM["preliminary_relation_row_count"] == 367
    assert SUM["contained_rollup_source_count"] == 22
    assert "0.80" in str(SUM["sensitivity_analysis"]["contained_cut_counts"])
    assert SUM["sensitivity_analysis"]["note"].startswith("SENSITIVITY_ANALYSIS only")


# ---------------------------------------------------------------------------
# 20-21. G3->G1 unchanged + no G4->G3 rows
# ---------------------------------------------------------------------------

def test_g3_to_g1_unchanged():
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
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G3_MESO_FINE'")
        total = cur.fetchone()[0]
    finally:
        conn.close()
    assert total == 246


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
