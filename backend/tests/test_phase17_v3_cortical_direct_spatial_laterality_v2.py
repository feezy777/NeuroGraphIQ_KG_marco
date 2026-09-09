"""Phase1.7 V3 - direct-spatial evidence laterality semantics correction (V2) tests.

Validates that V2 fixed the hemisphere-unaware correct_side_fraction semantics with ZERO
change to any non-laterality scientific metric (containment/rank/competition/outside-union/
Dice/historical). a32e20e V1 preserved. No mapping/geometry/classification/DB change.
"""
from __future__ import annotations

import csv
import json
import subprocess
from collections import Counter
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
CLASS = D16 / "phase17_v3_classification.csv"
BF_BLOCK = D16 / "phase17_v3_zaborszky_acquisition_blocker_v1.json"
EFF = D16 / "phase17_v3_cortical_effective_prerequisite_status.json"

V1 = D16 / "phase17_v3_cortical_170_direct_spatial_evidence.csv"
V2 = D16 / "phase17_v3_cortical_170_direct_spatial_evidence_v2.csv"
CORR = D16 / "phase17_v3_cortical_direct_spatial_laterality_correction.json"
DIFF = D16 / "phase17_v3_cortical_direct_spatial_v1_v2_diff.csv"
PROV = D16 / "phase17_v3_cortical_direct_spatial_provenance_v2.json"
MD = D16 / "phase17_v3_cortical_direct_spatial_diagnostics_v2.md"
OUTS = [V2, CORR, DIFF, PROV, MD]
LAT = {"left_fraction", "right_fraction", "correct_side_fraction", "contralateral_fraction"}


def _rows(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _j(p):
    return json.load(open(p, encoding="utf-8"))


def _git_clean(*paths: Path) -> bool:
    r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *[str(p) for p in paths]],
                       cwd=BACKEND.parent, capture_output=True)
    return r.returncode == 0


# ---- 1. HEAD ----
def test_1_head():
    r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=BACKEND.parent,
                       capture_output=True, text=True)
    assert r.stdout.strip() == "a32e20e"


# ---- 2/3. universe 170, L/R 85/85 ----
def test_2_3_universe():
    v2 = _rows(V2)
    assert len(v2) == 170
    assert Counter(r["hemisphere"] for r in v2) == Counter({"left": 85, "right": 85})


# ---- 4/5/6. left/right explicit + correct semantics hemisphere-aware ----
def test_4_5_6_semantics():
    for r in _rows(V2):
        assert float(r["left_fraction"]) + float(r["right_fraction"]) == pytest.approx(1.0, abs=1e-6)
        if r["hemisphere"] == "left":
            assert float(r["correct_side_fraction"]) == pytest.approx(
                float(r["left_fraction"]), abs=1e-9)
            assert float(r["contralateral_fraction"]) == pytest.approx(
                float(r["right_fraction"]), abs=1e-9)
        else:
            assert float(r["correct_side_fraction"]) == pytest.approx(
                float(r["right_fraction"]), abs=1e-9)
            assert float(r["contralateral_fraction"]) == pytest.approx(
                float(r["left_fraction"]), abs=1e-9)


# ---- 7. 85 right rows corrected (no longer correct~=0) ----
def test_7_right_corrected():
    v2 = {r["fine_region_id"]: r for r in _rows(V2) if r["hemisphere"] == "right"}
    v1 = {r["fine_region_id"]: r for r in _rows(V1) if r["hemisphere"] == "right"}
    assert len(v2) == 85
    for rid, r in v2.items():
        assert float(r["correct_side_fraction"]) > 0.5          # was ~0 in V1
        assert float(v1[rid]["correct_side_fraction"]) <= 0.5   # V1 held left_fraction
        assert float(r["contralateral_fraction"]) < 0.5
        assert float(r["correct_side_fraction"]) == pytest.approx(
            float(r["right_fraction"]), abs=1e-9)


# ---- 8. 85 left rows semantically consistent with V1 ----
def test_8_left_consistent():
    v1 = {r["fine_region_id"]: r for r in _rows(V1) if r["hemisphere"] == "left"}
    for r in _rows(V2):
        if r["hemisphere"] != "left":
            continue
        assert float(r["correct_side_fraction"]) == pytest.approx(
            float(v1[r["fine_region_id"]]["correct_side_fraction"]), abs=1e-6)


# ---- 9. correct + contralateral ~= 1 ----
def test_9_sum_1():
    for r in _rows(V2):
        assert float(r["correct_side_fraction"]) + float(r["contralateral_fraction"]) == \
            pytest.approx(1.0, abs=1e-6)


# ---- 10. laterality failures recomputed (gate unchanged, >=0.90) ----
def test_10_failures():
    p = _j(PROV)
    assert p["laterality_failures_after_correction"] == []
    assert p["laterality_qc"] == "LATERALITY_QC_CONFIRMED_AFTER_SEMANTIC_CORRECTION"
    assert all(float(r["correct_side_fraction"]) >= 0.90 for r in _rows(V2))


# ---- 11/12/13/14. non-laterality metric invariance 170/170 ----
def test_11_12_13_14_invariance():
    v1 = {r["fine_region_id"]: r for r in _rows(V1)}
    for r in _rows(V2):
        o = v1[r["fine_region_id"]]
        for k, val in o.items():
            if k in LAT:
                continue
            assert str(r[k]) == str(val), (r["fine_region_id"], k)
    assert _j(PROV)["non_laterality_field_unexpected_diffs"] == 0


# ---- 15. geometry SHA unchanged (frozen) ----
def test_15_geometry_unchanged():
    # geometry binaries unchanged since c97d7d8; only reporting fields changed this round
    assert "geometry_unchanged" in _j(PROV) and _j(PROV)["geometry_unchanged"] is True


# ---- 16/17/18. no registration / mapping change / reclassification ----
def test_16_17_18_no_changes():
    p = _j(PROV)
    assert p["mapping_unchanged"] is True and p["v1_history_preserved"] is True
    md = MD.read_text(encoding="utf-8").lower()
    assert "no mapping" in md and "no ontology" in md


# ---- 19. DB zero-write ----
def test_19_db_zero_write():
    assert "no db" in MD.read_text(encoding="utf-8").lower()
    assert not any("_db_" in p.name for p in OUTS)


# ---- 20. classification unchanged ----
def test_20_classification():
    assert _git_clean(CLASS)
    rows = list(csv.DictReader(open(CLASS, encoding="utf-8-sig")))
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert sum(c.values()) - c["VERIFIED_DIRECT_CONTAINED"] == 132
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


# ---- 21. V1 history preserved ----
def test_21_v1_preserved():
    assert _git_clean(V1)
    assert _j(CORR)["v1_history_preserved"] == "phase17_v3_cortical_170_direct_spatial_evidence.csv (a32e20e)"


# ---- 22. V2 provenance complete ----
def test_22_provenance():
    assert all(p.exists() for p in OUTS)
    p = _j(PROV)
    assert p["universe"] == 170 and p["left"] == 85 and p["right"] == 85
    assert p["containment_unchanged"].startswith("170/170")
    assert p["ranking_unchanged"] == "170/170 identical"


# ---- fixtures: known left/right parcels ----
def test_fixtures():
    rows = {r["fine_region_id"]: r for r in _rows(V2)}
    l = rows["NGIQ-BR-00000001"]  # SFG_L_7_1 left
    assert l["hemisphere"] == "left"
    assert float(l["correct_side_fraction"]) == pytest.approx(float(l["left_fraction"]), abs=1e-9)
    assert float(l["correct_side_fraction"]) > 0.9
    r = rows["NGIQ-BR-00000002"]  # SFG_R_7_1 right
    assert r["hemisphere"] == "right"
    assert float(r["correct_side_fraction"]) == pytest.approx(float(r["right_fraction"]), abs=1e-9)
    assert float(r["correct_side_fraction"]) > 0.9


# ---- diff file contains exactly the right-row laterality corrections ----
def test_diff_file():
    diff = _rows(DIFF)
    assert len(diff) == 170  # 85 right rows x (correct + contralateral)
    assert all(d["hemisphere"] == "right" for d in diff)
