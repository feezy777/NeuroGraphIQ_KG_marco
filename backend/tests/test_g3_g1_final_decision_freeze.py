"""G3->G1 final scientific decision freeze tests (Phase 1F-A2).

Read-only validation of the materialized final decision artifacts after the
verbatim ChatGPT per-pair scientific review was applied to all 49 composite
pairs. The distribution is FROZEN at exactly: APPROVE_CONTAINED_IN=16,
APPROVE_DOMINANT_OVERLAP=17, PARTIAL_OVERLAP=10, NO_G1_ROLLUP=3,
CONFLICT_REVIEW=3, PENDING=0. Rollup flags follow the frozen contract; the
three NO_G1_ROLLUP and three CONFLICT_REVIEW pairs are asserted exactly;
PARTIAL_OVERLAP carries multiple evidence targets and NO fake primary.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import psycopg
import pytest

BACKEND = Path(__file__).resolve().parents[1]
E2E = "neurographiq_human_brain_v1_e2e"
INT = BACKEND / "data" / "integration"

DEC = _rows = None


def _rows(p: Path) -> list[dict]:
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _conn():
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=E2E, autocommit=True)


ROWS = _rows(INT / "g3_to_g1_final_scientific_decisions.csv")
PAIRS = {r["biological_pair_id"] for r in ROWS}
COMP_FAMILIES = {"MFG", "IFG", "OrG", "STG", "PhG", "IPL", "CG", "MVOcC"}
REVIEW_PHASE = "G3_G1_SCIENTIFIC_FREEZE_V1"
DECISION_SOURCE = "ChatGPT human scientific review"


def _comp_rows():
    return [r for r in ROWS if r["biological_pair_id"].split("_")[0] in COMP_FAMILIES]


def _pair_decision(pair):
    for r in ROWS:
        if r["biological_pair_id"] == pair:
            return r["effective_scientific_decision"]
    return None


def _pair_rows(pair):
    return [r for r in ROWS if r["biological_pair_id"] == pair]


# ---------------------------------------------------------------------------
# 1-2. Completeness
# ---------------------------------------------------------------------------

def test_49_composite_pairs_present():
    comp = {r["biological_pair_id"] for r in _comp_rows()}
    assert len(comp) == 49


def test_98_composite_parcels():
    comp = [r for r in _comp_rows() if r["seed_type"] == "composite"]
    assert len(comp) == 98


# ---------------------------------------------------------------------------
# 3-4. Enum legality + FULL frozen distribution (PENDING=0)
# ---------------------------------------------------------------------------

ENUM = {"APPROVE_CONTAINED_IN", "APPROVE_DOMINANT_OVERLAP", "PARTIAL_OVERLAP",
        "NO_G1_ROLLUP", "CONFLICT_REVIEW"}


def test_decision_enum_legal_and_no_pending():
    for r in ROWS:
        d = r["effective_scientific_decision"]
        assert d in ENUM, d
        assert d != "PENDING_CHATGPT_FREEZE"


def test_frozen_distribution_exact():
    # the 49 composite pairs MUST be exactly 16/17/10/3/3 with PENDING=0
    # (count per unique biological_pair, not per parcel row)
    from collections import Counter
    comp = _comp_rows()
    pairs = {r["biological_pair_id"] for r in comp}
    assert len(pairs) == 49
    dec = Counter(next(r["effective_scientific_decision"]
                       for r in comp if r["biological_pair_id"] == p) for p in pairs)
    assert dec == Counter({"APPROVE_CONTAINED_IN": 16, "APPROVE_DOMINANT_OVERLAP": 17,
                           "PARTIAL_OVERLAP": 10, "NO_G1_ROLLUP": 3, "CONFLICT_REVIEW": 3})


# ---------------------------------------------------------------------------
# 5-9. rollup contract
# ---------------------------------------------------------------------------

def test_only_contained_in_rollup_eligible():
    contained = []
    for r in ROWS:
        if r["effective_scientific_decision"] == "APPROVE_CONTAINED_IN":
            contained.append(r)
            assert r["rollup_eligible"] == "TRUE" and r["is_primary_rollup"] == "TRUE"
        else:
            assert r["rollup_eligible"] == "FALSE"
            assert r["is_primary_rollup"] == "FALSE"
    # exactly the 16 contained composite pairs x2 hemispheres = 32 rollup parcels
    assert len(contained) == 32


def test_dominant_partial_no_conflict_not_rollup():
    for r in ROWS:
        if r["effective_scientific_decision"] in ("APPROVE_DOMINANT_OVERLAP", "PARTIAL_OVERLAP",
                                                   "NO_G1_ROLLUP", "CONFLICT_REVIEW"):
            assert r["rollup_eligible"] == "FALSE"


def test_contained_in_primary_target_unique():
    for r in ROWS:
        if r["effective_scientific_decision"] == "APPROVE_CONTAINED_IN":
            assert r["primary_target_g1"] != ""
            assert r["evidence_targets_g1"] != ""


def test_partial_overlap_has_no_fake_primary():
    for r in ROWS:
        if r["effective_scientific_decision"] == "PARTIAL_OVERLAP":
            assert r["primary_target_g1"] == ""
            assert r["evidence_targets_g1"] != ""


# ---------------------------------------------------------------------------
# 10-12. Special decisions (3 NO_G1_ROLLUP + 3 CONFLICT_REVIEW)
# ---------------------------------------------------------------------------

def test_no_rollup_pairs_exact():
    # the ONLY three NO_G1_ROLLUP pairs are IFS / Temporal Pole / vmPOS
    no_rollup = {p for p in PAIRS if _pair_decision(p) == "NO_G1_ROLLUP"
                 and p.split("_")[0] in COMP_FAMILIES}
    assert no_rollup == {"IFG_6_2", "STG_6_1", "MVOcC_5_5"}


def test_conflict_review_pairs_exact():
    # the ONLY three CONFLICT_REVIEW pairs are CG_7_3 / rCunG / cCunG
    conflict = {p for p in PAIRS if _pair_decision(p) == "CONFLICT_REVIEW"
                and p.split("_")[0] in COMP_FAMILIES}
    assert conflict == {"CG_7_3", "MVOcC_5_2", "MVOcC_5_3"}


def test_rcung_ccung_effective_conflict():
    assert _pair_decision("MVOcC_5_2") == "CONFLICT_REVIEW"  # rCunG
    assert _pair_decision("MVOcC_5_3") == "CONFLICT_REVIEW"  # cCunG


def test_cg_7_3_effective_conflict():
    assert _pair_decision("CG_7_3") == "CONFLICT_REVIEW"


def test_socg_effective_conflict():
    assert _pair_decision("LOcC_2_1") == "CONFLICT_REVIEW"
    assert _pair_decision("LOcC_2_2") == "CONFLICT_REVIEW"


def test_ifs_temporalpole_vmpos_psts_no_rollup():
    for pair in ("IFG_6_2", "STG_6_1", "MVOcC_5_5", "pSTS_2_1", "pSTS_2_2"):
        assert _pair_decision(pair) == "NO_G1_ROLLUP"
        for r in _pair_rows(pair):
            assert r["rollup_eligible"] == "FALSE"


# ---------------------------------------------------------------------------
# 13. Provenance
# ---------------------------------------------------------------------------

def test_historical_decision_preserved():
    # MVOcC_5_1 cLinG historically approved; historical field preserved even though
    # effective decision is APPROVE_DOMINANT_OVERLAP from the scientific freeze
    m = _pair_rows("MVOcC_5_1")
    assert len(m) == 2
    for r in m:
        assert r["historical_decision"] != ""
        assert r["effective_scientific_decision"] == "APPROVE_DOMINANT_OVERLAP"


def test_review_phase_and_source_present():
    for r in ROWS:
        assert r["review_phase"] == REVIEW_PHASE
        assert r["decision_source"] == DECISION_SOURCE


def test_json_artifact_matches_csv():
    j = json.load(open(INT / "g3_to_g1_final_scientific_decisions.json", encoding="utf-8"))
    assert len(j) == len(ROWS)
    key = lambda r: (r["biological_pair_id"], r["hemisphere"])
    assert {key(r) for r in j} == {key(r) for r in ROWS}
    for rj in j:
        rc = next(r for r in ROWS if key(r) == key(rj))
        assert rj["effective_scientific_decision"] == rc["effective_scientific_decision"]
        assert rj["rollup_eligible"] == rc["rollup_eligible"]
        assert rj["primary_target_g1"] == rc["primary_target_g1"]


def test_summary_artifact_consistent():
    s = json.load(open(INT / "g3_to_g1_final_scientific_decision_summary.json", encoding="utf-8"))
    assert s["composite_pair_count"] == 49
    assert s["pending_after"] == 0
    assert s["pair_distribution"]["APPROVE_CONTAINED_IN"] == 16
    assert s["pair_distribution"]["APPROVE_DOMINANT_OVERLAP"] == 17
    assert s["pair_distribution"]["PARTIAL_OVERLAP"] == 10
    assert s["pair_distribution"]["NO_G1_ROLLUP"] == 3
    assert s["pair_distribution"]["CONFLICT_REVIEW"] == 3
    assert s["contained_parcel_rollup_count"] == 32


# ---------------------------------------------------------------------------
# 14. Production aggregation remains 0
# ---------------------------------------------------------------------------

def test_production_aggregation_remains_zero():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings")
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
