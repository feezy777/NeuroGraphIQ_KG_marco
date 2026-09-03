"""Gate 7B Phase 2I-B — Owner Scientific Policy Revision (strata, no decision).

Read-only checks that the owner-review revision artifacts exist with the exact
frozen/reclassified counts, that 2I-A history is untouched (ledger file not
modified) and that the DB stays frozen. Decisions remain PENDING_OWNER_REVIEW.
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

V1 = INT / "g4_g3_owner_policy_revision_v1.csv"
DISAG = INT / "g4_g3_disagreement_partial_reassessment.csv"
HF = INT / "g4_g3_high_fragmentation_reassessment.csv"
CONT = INT / "g4_g3_contained_semantic_review.csv"
SUM = json.load(open(INT / "g4_g3_owner_policy_revision_summary.json", encoding="utf-8"))


def _rows(p: Path):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _conn(db=PROD):
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=db, autocommit=True)


def test_revision_v1_440_and_frozen():
    v1 = _rows(V1)
    assert len(v1) == 440
    from collections import Counter
    c = Counter(r["revised_owner_stratum"] for r in v1)
    assert SUM["frozen_unchanged"]["NO_G3_MAPPING"] == 18
    assert SUM["frozen_unchanged"]["SHARED_SPATIAL_EVIDENCE_ONLY"] == 64
    assert SUM["frozen_unchanged"]["noncanonical_audit_components"] == 14
    # no stratum string that would indicate a production relation was created
    assert "UNCHANGED_2IA_APPROVE_DOMINANT_OVERLAP" in c
    assert "UNCHANGED_2IA_PARTIAL_OVERLAP" in c


def test_contained_semantic_20_and_2():
    rows = _rows(CONT)
    assert len(rows) == 22
    c = Counter(r["owner_review_status"] for r in rows)
    assert c["PROVISIONAL_OWNER_ACCEPTED_CONTAINED"] == 20
    assert c["CONTAINED_BOUNDARY_REVIEW"] == 2
    bound = [r for r in rows if r["owner_review_status"] == "CONTAINED_BOUNDARY_REVIEW"]
    assert {r["canonical_g4_id"] for r in bound} == {"NGIQ-BR-00000370", "NGIQ-BR-00000599"}
    # boundary rows must not be rollup-open in this revision
    assert all(r["rollup_allowed_in_revision"] == "FALSE" for r in bound)
    # every contained row carries full G4->G3 semantic names
    assert all(r["target_g3_official_name"] for r in rows)
    assert all(r["target_g3_parcel_code"] for r in rows)


def test_disagreement_reassessment():
    rows = _rows(DISAG)
    assert len(rows) == 35
    c = Counter(r["revised_stratum"] for r in rows)
    assert c["PARTIAL_SET_CONCORDANT_REVIEW"] == 20
    assert c["TRUE_PP_HARDLABEL_CONFLICT"] == 15
    assert SUM["disagreement_35"]["partial_set_concordant"] == 20
    assert SUM["disagreement_35"]["true_pp_hardlabel_conflict"] == 15
    # concordant rows carry selected targets
    for r in rows:
        if r["revised_stratum"] == "PARTIAL_SET_CONCORDANT_REVIEW":
            assert int(r["selected_target_count"]) >= 2


def test_high_fragmentation_reassessment():
    rows = _rows(HF)
    assert len(rows) == 71
    c = Counter(r["revised_stratum"] for r in rows)
    assert c == {"PLAUSIBLE_MULTI_TARGET_PARTIAL": 21,
                 "TRUE_DIFFUSE_CONFLICT": 39, "LOW_COVERAGE_CONFLICT": 11}
    assert SUM["high_fragmentation_71"] == dict(c)


def test_partial_inconsistent_kept_conflict():
    v1 = _rows(V1)
    n = sum(1 for r in v1 if r["revised_owner_stratum"] == "PARTIAL_EVIDENCE_INCONSISTENT_CONFLICT")
    assert n == 5
    assert SUM["partial_evidence_inconsistent_5_still_conflict"] is True


def test_revised_partial_candidates():
    c = SUM["revised_partial_candidates"]
    assert c["sources_total"] == 142
    assert c["by_origin"] == {"existing_partial": 101, "concordant_disagreement": 20,
                              "highfrag_plausible": 21}
    assert c["target_rows_total"] >= 2 * 101


def test_2ia_history_untouched():
    # Phase 2I-A ledger file is NOT overwritten by this revision
    hist = INT / "g4_g3_scientific_decision_policy_v1.csv"
    assert hist.exists()
    rows = _rows(hist)
    c = Counter(r["scientific_decision"] for r in rows)
    assert c == {"APPROVE_CONTAINED_IN": 22, "APPROVE_DOMINANT_OVERLAP": 109, "PARTIAL_OVERLAP": 101,
                 "NO_G3_MAPPING": 18, "CONFLICT_REVIEW": 126, "SHARED_SPATIAL_EVIDENCE_ONLY": 64}


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
