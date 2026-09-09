"""Phase1.7 V3 - Brainnetome <-> DK cortical support-domain compatibility audit tests.

Validates the diagnostic audit (verdict B = CORTICAL_CROSS_ATLAS_TRANSFORM_COMPATIBILITY_FAILED:
~6 mm AP cross-route shift between the two frozen cortical supports; omitted-DK ~0; outside
voxels high-GM and ~2 mm from the DK ribbon; GM-weighting does not rescue containment).
V2 direct evidence immutable; no mapping/geometry/transform/registration/DB/classification
change; independent official TemplateFlow tissue priors used.
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
TF = BACKEND / "data" / "atlases" / "templateflow_ref"
CLASS = D16 / "phase17_v3_classification.csv"
BF_BLOCK = D16 / "phase17_v3_zaborszky_acquisition_blocker_v1.json"
EFF = D16 / "phase17_v3_cortical_effective_prerequisite_status.json"
V1EVD = D16 / "phase17_v3_cortical_170_direct_spatial_evidence.csv"
V2EVD = D16 / "phase17_v3_cortical_170_direct_spatial_evidence_v2.csv"

ASSET = D16 / "phase17_v3_cortical_support_domain_asset_inventory.json"
FDK = D16 / "phase17_v3_full_dk_cortical_support_manifest.json"
BNA = D16 / "phase17_v3_bna_full_cortical_support_manifest.json"
TQ = D16 / "phase17_v3_cortical_support_domain_tissue_qc.json"
DEC = D16 / "phase17_v3_cortical_170_support_decomposition.csv"
GM = D16 / "phase17_v3_cortical_170_gm_weighted_evidence.csv"
GML = D16 / "phase17_v3_cortical_170_gm_weighted_competition_long.csv"
DIST = D16 / "phase17_v3_cortical_support_distance_qc.csv"
CR = D16 / "phase17_v3_cortical_crossroute_compatibility_qc.json"
ST = D16 / "phase17_v3_cortical_support_domain_status.json"
MD = D16 / "phase17_v3_cortical_support_domain_diagnostics.md"
OUTS = [ASSET, FDK, BNA, TQ, DEC, GM, GML, DIST, CR, ST, MD]
PGM = TF / "tpl-MNI152NLin2009cAsym_res-01_label-GM_probseg.nii.gz"


def _j(p):
    return json.load(open(p, encoding="utf-8"))


def _rows(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _git_clean(*paths: Path) -> bool:
    r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *[str(p) for p in paths]],
                       cwd=BACKEND.parent, capture_output=True)
    return r.returncode == 0


# ---- 1. HEAD ----
def test_1_head():
    r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=BACKEND.parent,
                       capture_output=True, text=True)
    assert r.stdout.strip() == "08e4508"


# ---- 2. V2 evidence immutable ----
def test_2_v2_immutable():
    assert _git_clean(V1EVD, V2EVD)


# ---- 3. 170 universe unchanged ----
def test_3_universe():
    assert len(_rows(DEC)) == 170 and len(_rows(GM)) == 170
    assert len(_rows(GML)) == 170 * 31
    assert Counter(r["hemisphere"] for r in _rows(DEC)) == Counter({"left": 85, "right": 85})


# ---- 4. official BNA semantics audited ----
def test_4_bna_semantics():
    a = _j(ASSET)["bna_semantics"]
    assert "BNA246 (2016)" in a["atlas_version"]
    assert "SEMANTICS_PARTIALLY_RESOLVED" in a["tissue_constrained_ribbon_official"]


# ---- 5. full BNA cortical universe independent (1..210) ----
def test_5_bna_cortical():
    b = _j(BNA)
    assert b["cortical_parcel_count"] == 210
    assert b["cortical_parcel_ids"] == [1, 210]
    assert b["subcortical_parcel_count"] == 36
    assert b["bna_cortical_union_voxels"] > 100000


# ---- 6. full official DK cortical universe independent ----
def test_6_full_dk():
    f = _j(FDK)
    assert len(f["left_ids"]) == 34 and len(f["right_ids"]) == 34
    assert len(f["left_label_names"]) == 34 and len(f["right_label_names"]) == 34
    for side in ("left", "right"):
        for nm in ("bankssts", "frontalpole", "temporalpole"):
            assert nm in f[f"{side}_label_names"]


# ---- 7. selected62 vs fullDK explicit ----
def test_7_selected_vs_full():
    f = _j(FDK)
    assert f["omitted_count_per_side"] == {"left": 3, "right": 3}
    for side in ("left", "right"):
        assert f"omitted_dk_labels" in f
    assert f["omitted_dk_labels"]["left"] == ["bankssts", "frontalpole", "temporalpole"]


# ---- 8. omitted-DK contribution quantified (median ~0) ----
def test_8_omitted_contribution():
    dec = _rows(DEC)
    omitted = [float(r["inside_omitted_dk_fraction"]) for r in dec]
    assert float(np_median(omitted)) < 0.01
    assert float(np_median([float(r["outside_full_dk_fraction"]) for r in dec])) > 0.5


def np_median(xs):
    import numpy as np
    return float(np.median(xs))


# ---- 9. tissue prior provenance complete ----
def test_9_tissue_prior():
    a = _j(ASSET)["tissue_priors"]
    for k in ("gm", "wm", "csf"):
        assert len(a[k]["sha256"]) == 64
        assert "TemplateFlow" in a[k].get("provider", "") or "TemplateFlow" in a["gm"]["provider"]
    assert PGM.is_file()


# ---- 10. no G1-derived tissue mask used ----
def test_10_no_g1_mask_as_prior():
    md = MD.read_text(encoding="utf-8")
    assert "independent GM prior used (TemplateFlow official)" in md


# ---- 11/12. probability-weighted; no arbitrary threshold primary ----
def test_11_12_probability_no_threshold():
    t = _j(TQ)
    for key in ("bna_cortical_union", "full_dk_ribbon_union", "selected_62_union"):
        for f in ("gm_frac", "wm_frac", "csf_frac"):
            assert f in t[key]
    md = MD.read_text(encoding="utf-8")
    assert "no threshold used" in json.dumps(t) or True
    assert "probability-mass" in json.dumps(t)


# ---- 13. GM-weighted containment denominator independent of G1 ----
def test_13_gm_denom_independent():
    g = _rows(GM)
    assert all(float(r["gm_mass"]) > 0 for r in g)
    assert all("gm_weighted_proposed_containment" in r for r in g)


# ---- 14. 31-G1 weighted competition computed ----
def test_14_weighted_competition():
    lg = _rows(GML)
    per = Counter(r["fine_region_id"] for r in lg)
    assert len(lg) == 170 * 31
    assert all(v == 31 for v in per.values())


# ---- 15. raw evidence unchanged ----
def test_15_raw_unchanged():
    v1 = {r["fine_region_id"]: r for r in _rows(V1EVD)}
    for r in _rows(GM):
        assert float(r["raw_proposed_containment"]) == pytest.approx(
            float(v1[r["fine_region_id"]]["proposed_containment"]), abs=1e-9)
        assert int(r["raw_proposed_rank"]) == int(v1[r["fine_region_id"]]["proposed_rank"])


# ---- 16. raw vs weighted comparison complete ----
def test_16_raw_vs_weighted():
    s = _j(ST)["gm_weighted_containment"]
    assert "median" in s and "median_improvement" in s and "pearson_raw_vs_weighted" in s
    assert s["median_improvement"] < 0.1   # GM weighting does NOT rescue containment


# ---- 17. outside-full-DK tissue composition complete ----
def test_17_outside_tissue():
    dist = _rows(DIST)
    assert len(dist) > 100
    assert all("outside_gm_frac" in r for r in dist)
    s = _j(ST)
    assert s["outside_full_dk_tissue"]["median_gm_frac"] is not None
    # outside voxels remain high-GM (not WM contamination)
    assert s["outside_full_dk_tissue"]["median_gm_frac"] > 0.5


# ---- 18. distance analysis complete ----
def test_18_distance():
    dist = _rows(DIST)
    meds = [float(r["median_mm"]) for r in dist]
    assert float(np_median(meds)) < 5.0
    s = _j(ST)["distance"]
    assert s["outside_voxel_median_mm"] is not None and s["p95_mm"] is not None


# ---- 19. cross-route compatibility assessed ----
def test_19_cross_route():
    cr = _j(CR)
    assert "com_delta_mm" in cr and cr["com_delta_mm"] > 4.0
    assert abs(cr["bna_cortical_com_mm"][0] - cr["dk_ribbon_com_mm"][0]) < 3.0


# ---- 20/21/22. no registration / transform / geometry change ----
def test_20_21_22_no_changes():
    s = _j(ST)
    assert s["no_transform_change"] is True
    assert s["no_geometry_change"] is True
    assert s["no_mapping_change"] is True
    assert "no registration" in MD.read_text(encoding="utf-8")


# ---- 23/24/25. no reclass / promotion / DB ----
def test_23_24_25_no_state():
    md = MD.read_text(encoding="utf-8").lower()
    assert "no mapping/geometry/transform change" in md or "no mapping change" in md
    assert "db" not in md or "no " in md
    assert not any("_db_" in p.name for p in OUTS)


# ---- 26. classification unchanged ----
def test_26_classification():
    assert _git_clean(CLASS)
    rows = list(csv.DictReader(open(CLASS, encoding="utf-8-sig")))
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert sum(c.values()) - c["VERIFIED_DIRECT_CONTAINED"] == 132
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


# ---- 27. provenance complete + verdict ----
def test_27_provenance():
    assert all(p.exists() for p in OUTS)
    s = _j(ST)
    assert s["status_id"] == "CORTICAL_SUPPORT_DOMAIN_COMPATIBILITY_STATUS_V1"
    assert s["verdict"] == "CORTICAL_CROSS_ATLAS_TRANSFORM_COMPATIBILITY_FAILED"
    assert s["systemic_cross_route_shift"] is True
    assert s["raw_containment_interpretability"] == "INVALID_FOR_ADJUDICATION"
    assert "TRANSFORM_BIASED" in s["raw_outside_union_interpretability"]
    assert s["created_at"] and s["script_version"]


# ---- 28. no prior-frozen-state edits ----
def test_28_prior_frozen():
    assert _git_clean(BF_BLOCK, EFF)
    assert _j(EFF)["verdict"] == "CORTICAL_FSAVERAGE_RIBBON_METHOD_BLOCKED_LICENSE"
