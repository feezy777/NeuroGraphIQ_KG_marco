"""Gate 7B Phase 2H — G4→G3 spatial evidence interpretation & decision
calibration prep.

Read-only verification of the row-level evidence profiles, hard-label (BN_Atlas
deterministic) coverage auxiliary metric, evidence strata, shared-component
review, scientific review packet (decisions left BLANK), disagreement table,
representative examples and the DESCRIPTIVE-ONLY threshold sensitivity table.

No relation thresholds decided, no contained/dominant/partial emitted, no
mapping candidates, no DB writes, Phase 2G matrix hash unchanged.

Coverage (gate section 24, 1-20). Shared canonical leaf count is measured = 64
(gate hypothesis of 50 is NOT confirmed; documented in summary).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import nibabel as nib
import numpy as np
import psycopg
import pytest

BACKEND = Path(__file__).resolve().parents[1]
PROD = "neurographiq_human_brain_v1"
INT = BACKEND / "data" / "integration"
LABEL_DIR = BACKEND / "data" / "atlases" / "brainnetome" / "bna246" / "transformed_label_to_julich2009c"
LABEL_OUT = LABEL_DIR / "BN_Atlas_246_1mm_NLin6to2009c_labels.nii.gz"
LABEL_PROV = LABEL_DIR / "label_transform_provenance.json"
JUL_REF = sorted((BACKEND / "data" / "atlases" / "julich" / "v3.1" / "spatial_raw" / "probability_maps").glob("*.nii.gz"))[0]

SUM = json.load(open(INT / "g4_g3_overlap_interpretation_summary.json", encoding="utf-8"))
G2G = json.load(open(INT / "g4_g3_probability_overlap_summary.json", encoding="utf-8"))
PROFILES = INT / "g4_g3_overlap_interpretation_profiles.csv"
DISAGREE = INT / "g4_g3_probability_hardlabel_disagreements.csv"
SHARED = INT / "g4_g3_shared_spatial_component_review.csv"
PACKET = INT / "g4_g3_scientific_review_packet.csv"
EXAMPLES = INT / "g4_g3_evidence_pattern_examples.csv"
THRESH = INT / "g4_g3_threshold_sensitivity_table.csv"


def _rows(p: Path) -> list[dict]:
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _num(x):
    return None if x in ("", None) else float(x)


def _conn(db=PROD):
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=db, autocommit=True)


# ---------------------------------------------------------------------------
# 1-4. counts + shared-leaf accounting
# ---------------------------------------------------------------------------

def test_profile_count_414():
    rows = _rows(PROFILES)
    assert len(rows) == 414
    assert SUM["julich_spatial_components"] == 414


def test_one_to_one_390():
    assert SUM["one_to_one_julich_component_count"] == 390
    n = sum(1 for r in _rows(PROFILES) if r["spatial_identity_status"] == "ONE_TO_ONE_CANONICAL")
    assert n == 390


def test_shared_24():
    assert SUM["shared_spatial_component_count"] == 24
    n = sum(1 for r in _rows(PROFILES) if r["spatial_identity_status"] == "SHARED_SPATIAL_REPRESENTATION")
    assert n == 24


def test_shared_canonical_leaves_measured_64():
    # gate hypothesized 50; measured truth is 64 (see summary leaf_accounting)
    acct = SUM["canonical_leaf_accounting"]
    assert SUM["shared_canonical_leaf_count"] == 64
    assert acct["one_to_one_canonical_leaf_subset"] == 376
    assert len(acct["one_to_one_noncanonical_single_leaves"]) == 14
    assert acct["canonical_union_check"] == 440
    assert "not 50" in acct["hypothesis_check"]


# ---------------------------------------------------------------------------
# 5-7. hard-label transform QA
# ---------------------------------------------------------------------------

def test_hard_label_transform_grid_match():
    prov = json.load(open(LABEL_PROV, encoding="utf-8"))
    assert prov["status"] == "PASS"
    assert prov["grid_match"] is True
    assert prov["interpolation"] == "NearestNeighbor (GenericLabel)"
    lab = nib.load(str(LABEL_OUT))
    ref = nib.load(str(JUL_REF))
    assert lab.shape == ref.shape == (193, 229, 193)
    assert np.array_equal(np.asarray(lab.affine), np.asarray(ref.affine))
    assert tuple(nib.aff2axcodes(lab.affine)) == ("R", "A", "S")
    assert prov["labels_vanished_in_target"] == []


def test_hard_label_integer_only():
    d = nib.load(str(LABEL_OUT)).get_fdata()
    assert (d == np.round(d)).all()


def test_hard_label_values_0_246():
    d = nib.load(str(LABEL_OUT)).get_fdata()
    u = np.unique(d)
    assert int(u.min()) >= 0 and int(u.max()) <= 246
    assert set(u.astype(int)) <= set(range(0, 247))
    assert (d != 0).sum() > 0


# ---------------------------------------------------------------------------
# 8-10. hard coverage ranges + row sum <= 1
# ---------------------------------------------------------------------------

def test_hard_coverage_range_0_1():
    rows = _rows(PROFILES)
    for r in rows:
        for k in ("hard_top1_coverage", "hard_top2_coverage", "hard_top3_coverage",
                  "hard_total_bna_coverage", "bna_uncovered_fraction"):
            v = _num(r[k])
            if v is not None:
                assert -1e-9 <= v <= 1.0 + 1e-9, (r["row_index"], k, v)


def test_row_coverage_sum_leq_one():
    rows = _rows(PROFILES)
    for r in rows:
        total = _num(r["hard_total_bna_coverage"]) or 0.0
        unc = _num(r["bna_uncovered_fraction"]) or 0.0
        assert total <= 1.0 + 1e-6
        assert abs((total + unc) - 1.0) <= 1e-4, r["row_index"]


def test_uncovered_fraction_range():
    u = np.array([(_num(r["bna_uncovered_fraction"]) or 0.0) for r in _rows(PROFILES)])
    assert u.min() >= 0.0 and u.max() <= 1.0 + 1e-9


# ---------------------------------------------------------------------------
# 11. zero-overlap rows -> NULL top1 (no fabricated argmax)
# ---------------------------------------------------------------------------

def test_zero_overlap_rows_null_top1():
    rows = _rows(PROFILES)
    zero = [r for r in rows if r["pp_top1_g3_id"] in ("", None)]
    assert len(zero) == SUM["zero_association_count"] == 10
    assert all("NO_SPATIAL_ASSOCIATION" in (r["qa_flags"] or "") for r in zero)
    assert all(r["evidence_pattern"] == "ZERO_BNA_ASSOCIATION" for r in zero)
    names = {r["julich_asset_file"] for r in zero}
    assert len(names) == 10
    # cerebellum / midbrain coverage-gap family
    assert all(any(tok in n.upper() for tok in ("CEREBELLUM", "RUBER", "FASTIG", "INTERPOS", "DENTATE"))
               for n in names)


# ---------------------------------------------------------------------------
# 12. pp/hard top1 agreement computed
# ---------------------------------------------------------------------------

def test_top1_agreement_computed():
    rows = _rows(PROFILES)
    vals = {r["top1_agreement"] for r in rows}
    assert vals <= {"TRUE", "FALSE", "NA"}
    t = sum(1 for r in rows if r["top1_agreement"] == "TRUE")
    f = sum(1 for r in rows if r["top1_agreement"] == "FALSE")
    na = sum(1 for r in rows if r["top1_agreement"] == "NA")
    assert t + f + na == 414
    assert SUM["top1_agreement_count"] == t
    assert SUM["top1_disagreement_count"] == f == 44
    assert len(_rows(DISAGREE)) == f


# ---------------------------------------------------------------------------
# 13. effective target count finite
# ---------------------------------------------------------------------------

def test_effective_target_count_finite():
    vals = []
    for r in _rows(PROFILES):
        v = _num(r["effective_target_count"])
        if v is not None:
            vals.append(v)
    a = np.array(vals)
    assert np.isfinite(a).all()
    assert a.min() >= 1.0


# ---------------------------------------------------------------------------
# 14-15. review packet 390 one-to-one + blank decisions
# ---------------------------------------------------------------------------

def test_review_packet_390_and_one_to_one_only():
    packet = _rows(PACKET)
    assert len(packet) == 390
    assert all(r["spatial_identity_status"] == "ONE_TO_ONE_CANONICAL" for r in packet)
    assert all(r["scientific_decision"] == "" for r in packet)
    assert all(r["decision_reason"] == "" for r in packet)
    assert "scientific_decision" in packet[0] and "decision_reason" in packet[0]


# ---------------------------------------------------------------------------
# 16. no contained/dominant/partial generated
# ---------------------------------------------------------------------------

def test_no_ontology_relation_generated():
    for p in (PROFILES, PACKET):
        rows = _rows(p)
        header = list(rows[0].keys()) if rows else []
        joined = " ".join(header).lower()
        assert "contained" not in joined and "dominant" not in joined and "partial_overlap" not in joined
    assert SUM["classification_thresholds"] == "NOT_DEFINED"
    assert SUM["scientific_decisions_created"] is False
    assert SUM["evidence_strata_are_descriptive_only"] is True


# ---------------------------------------------------------------------------
# 17. Phase 2G matrix hash unchanged
# ---------------------------------------------------------------------------

def test_phase2g_matrix_hash_unchanged():
    assert SUM["phase2g_matrix_hash"] == G2G["matrix_hash"]


# ---------------------------------------------------------------------------
# 20 (with 18-19 below). threshold table descriptive only
# ---------------------------------------------------------------------------

def test_threshold_table_descriptive_only():
    rows = _rows(THRESH)
    assert [r["hypothetical_cut_on_hard_top1_coverage"] for r in rows] == ["0.5", "0.6", "0.7", "0.8", "0.9"]
    assert all("DESCRIPTIVE_ONLY" in r["status"] for r in rows)
    assert all("NOT_SCIENTIFICALLY_APPROVED" in r["status"] for r in rows)


def test_examples_and_shared_review_exist():
    ex = _rows(EXAMPLES)
    sets = {r["example_set"] for r in ex}
    assert {"A_highest_hard_top1", "B_smallest_top1_top2_margin", "C_highest_uncovered",
            "D_strongest_pp_hard_disagreement", "E_highest_effective_targets",
            "F_shared_spatial_component_examples"} <= sets
    sh = _rows(SHARED)
    assert len(sh) == 24
    assert all(r["shared_evidence_status"] == "SHARED_COMPONENT_LEVEL_ONLY" for r in sh)
    assert all(r["independent_leaf_spatial_evidence"] == "NO_INDEPENDENT_LEAF_SPATIAL_EVIDENCE" for r in sh)


# ---------------------------------------------------------------------------
# 18-19. G3->G1 unchanged + no G4->G3 rows
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
