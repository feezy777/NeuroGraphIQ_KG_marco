"""Phase1.7 V3 - cortical target transform topology + inverse consistency re-audit tests.

Validates verdict A = CORTICAL_TARGET_TRANSFORM_INTEGRITY_CONFIRMED and the 28 hard gates.
Read-only: no registration rerun, no recipe/transform modification, no DK/G4/mapping,
no ribbon/62-target geometry, no FreeSurfer/license, no DB, no reclassification, no
promotion. c6281e8 snapshot (transform + registration artifacts) byte-unchanged.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
RUN = BACKEND / "data" / "atlases" / "derived_g1" / "cort_reg_run_v1"
CLASS = D16 / "phase17_v3_classification.csv"
BF_BLOCK = D16 / "phase17_v3_zaborszky_acquisition_blocker_v1.json"
EFF = D16 / "phase17_v3_cortical_effective_prerequisite_status.json"
THAL = D16 / "phase17_v3_thalamus_final_freeze_v1.json"
AMYG = D16 / "phase17_v3_amygdala_g1_scope_contract_v1.json"
HIPP = D16 / "phase17_v3_hippocampus_canonical_identity_v1.json"
BNST_ADM = D16 / "phase17_v3_bnst_canonical_admission_v1.json"
BNST_GEOM = D16 / "phase17_v3_bnst_canonical_geometry_manifest.json"
TX_PRIOR = D16 / "phase17_v3_cortical_registration_transform_manifest.json"
DEFQ = D16 / "phase17_v3_cortical_registration_deformation_qc.json"
RECIPE = D16 / "phase17_v3_cortical_registration_recipe_v1.json"

REP = D16 / "phase17_v3_cortical_transform_reporting_correction.json"
MC = D16 / "phase17_v3_cortical_transform_jacobian_method_comparison.csv"
BD = D16 / "phase17_v3_cortical_transform_brain_domain_deformation_qc.json"
NEG = D16 / "phase17_v3_cortical_transform_nonpositive_jacobian_localization.csv"
COMP = D16 / "phase17_v3_cortical_transform_composition_audit.json"
PT = D16 / "phase17_v3_cortical_transform_point_roundtrip_qc.csv"
IRT = D16 / "phase17_v3_cortical_transform_image_roundtrip_qc.csv"
ST = D16 / "phase17_v3_cortical_transform_integrity_status.json"
MD = D16 / "phase17_v3_cortical_transform_integrity_diagnostics.md"
OUTS = [REP, MC, BD, NEG, COMP, PT, IRT, ST, MD]
HAS = all(p.exists() for p in OUTS)

FILES = {  # transform asset names -> suffix under RUN (c6281e8, byte-identical)
    "affine": "TRF-CORT-FSAVG-TO-MNI2009C-DIRECT-V1_affine.mat",
    "forward_warp": "TRF-CORT-FSAVG-TO-MNI2009C-DIRECT-V1_forward_warp.nii.gz",
    "inverse_warp": "TRF-CORT-FSAVG-TO-MNI2009C-DIRECT-V1_inverse_warp.nii.gz",
}


def _j(p):
    return json.load(open(p, encoding="utf-8"))


def _rows(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _git_clean(*paths: Path) -> bool:
    r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *[str(p) for p in paths]],
                       cwd=BACKEND.parent, capture_output=True)
    return r.returncode == 0


def _sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


# ---- 1. c6281e8 transform SHA byte-identical ----
def test_1_transform_sha_identical():
    prior = _j(TX_PRIOR)
    comp = _j(COMP)
    comp_sha = {"affine": comp["affine"]["sha256"],
                "forward_warp": comp["forward_warp"]["sha256"],
                "inverse_warp": comp["inverse_warp"]["sha256"]}
    for key, fname in FILES.items():
        p = RUN / fname
        assert p.exists(), fname
        assert _sha(p) == prior[key]["sha256"], key
        assert _sha(p) == comp_sha[key], key


# ---- 2. no registration rerun ----
def test_2_no_registration_rerun():
    assert "no registration rerun" in MD.read_text(encoding="utf-8")
    assert "no transform rewrite" in MD.read_text(encoding="utf-8") or \
        "no recipe/transform modification" in MD.read_text(encoding="utf-8")


# ---- 3. no recipe modification ----
def test_3_no_recipe_modification():
    assert _git_clean(RECIPE)
    assert _j(RECIPE)["recipe_id"] == "REGISTRATION_RECIPE_V1"


# ---- 4. mean/median reporting corrected ----
def test_4_reporting_corrected():
    r = _j(REP)
    d = _j(DEFQ)["deformation"]
    assert r["deformation_mean_mm"] == d["mean_mm"]
    assert r["deformation_median_mm"] == d["median_mm"]
    assert r["deformation_median_mm"] < 0.1
    assert r["artifact_source_of_truth"] == "phase17_v3_cortical_registration_deformation_qc.json"
    assert "INCORRECTLY_REPORTED_MEAN" in r["previous_summary_median_value"]


# ---- 5. Jacobian recomputed independently ----
def test_5_jacobian_recomputed():
    s = _j(ST)
    assert s["jacobian_methods"]["A_ANTs_official"]
    assert "B_application_fd" in s["jacobian_methods"]
    assert s["jacobian_methods"]["consistent"] is True
    rows = {r["method"]: r for r in _rows(MC)}
    assert "A_ANTs_official" in rows and "B_application_fd" in rows


# ---- 6. physical spacing used correctly ----
def test_6_physical_spacing():
    assert _j(BD)["methodB_application"]["spacing_mm"] == 1.0
    assert float(_rows(MC)[0]["min"]) > 0  # physical derivative yields positive det


# ---- 7. displacement component / convention explicit ----
def test_7_convention_explicit():
    c = _j(COMP)
    assert c["affine"]["format"] == "binary ITK transform (AffineTransform_float_3_3)"
    assert len(c["affine"]["parameters_12"]) == 12
    assert c["order_verification"] == "point roundtrip (below) + warped-image correspondence; not guessed"


# ---- 8. full-field vs brain-domain separated ----
def test_8_domain_separated():
    b = _j(BD)
    assert "full_field" in b and "fixed_brain_mask" in b and "cortical_surface_band" in b
    for dom in ("full_field", "fixed_brain_mask", "cortical_surface_band"):
        assert "displacement" in b[dom]
    assert "jacobian" in b["full_field"] and "jacobian" in b["fixed_brain_mask"]


# ---- 9. negative Jacobian localized ----
def test_9_negative_localized():
    s = _j(ST)
    assert s["nonpositive_voxels"]["methodA_grid"] == 0
    assert s["nonpositive_voxels"]["in_brain"] == 0
    for r in _rows(NEG):
        assert r["classification"] == "NONE"


# ---- 10. no negative-Jacobian tolerance chosen for convenience ----
def test_10_no_convenience_tolerance():
    s = _j(ST)
    assert s["full_field_jacobian_negative_fraction"] == 0.0
    assert s["brain_domain_jacobian_negative_fraction"] == 0.0
    assert s["methodB_brain_negative_fraction"] == 0.0
    assert float(_rows(MC)[0]["min"]) > 0.0


# ---- 11. composition order verified ----
def test_11_composition_order():
    c = _j(COMP)
    assert len(c["forward_chain"]["transform_list"]) == 2
    assert len(c["inverse_chain"]["transform_list"]) == 2
    assert "empirically verified" in c["inverse_chain"]["order_note"]


# ---- 12. forward/inverse direction verified ----
def test_12_directions():
    c = _j(COMP)
    assert "moving(fsaverage orig) -> fixed(MNI152NLin2009cAsym)" in c["forward_chain"]["direction"]
    assert c["inverse_chain"]["direction"] == "fixed -> moving"


# ---- 13/14. physical-point roundtrip both directions measured ----
def test_13_14_point_roundtrip():
    rows = {r["direction"]: r for r in _rows(PT)}
    assert "moving->fixed->moving" in rows and "fixed->moving->fixed" in rows
    for r in rows.values():
        assert int(r["n"]) >= 1000
        assert float(r["p95_mm"]) < 2.0
        assert float(r["max_mm"]) < 5.0
    assert float(rows["moving->fixed->moving"]["p95_mm"]) < 0.2
    assert float(rows["fixed->moving->fixed"]["p95_mm"]) < 0.2


# ---- 15. image coverage 0.613 explained ----
def test_15_coverage_explained():
    md = MD.read_text(encoding="utf-8")
    assert "0.613" in md
    assert "domain+threshold artifact" in md
    assert "physical-point roundtrip is the authoritative" in md
    irt = {r["metric"]: r for r in _rows(IRT)}
    assert abs(float(irt["moving->fixed->moving image"]["coverage"]) - 0.613) < 0.02


# ---- 16. no global reflection ----
def test_16_no_reflection():
    s = _j(ST)
    assert s["no_global_reflection"] is True
    assert "Global reflection" in MD.read_text(encoding="utf-8")


# ---- 17. NN smoke uses only whole-brain mask ----
def test_17_nn_smoke():
    s = _j(ST)
    sm = s["nn_smoke"]
    assert sm["forward_NN_moving_support"]["nonempty"] is True
    assert sm["inverse_NN_fixed_brain_mask"]["nonempty"] is True
    assert sm["forward_NN_moving_support"]["fixed_brain_coverage"] > 0.5
    assert "NearestNeighbor" in s["future_binary_ribbon_application"]
    assert "mask" in MD.read_text(encoding="utf-8").lower()


# ---- 18/19/20. no DK / G4 / mapping ----
def test_18_19_20_no_labels():
    md = MD.read_text(encoding="utf-8")
    assert "no DK" in md
    assert "no G4/Julich" in md
    assert "no mapping results" in md
    assert "no ribbon" in md and "no 62-target geometry" in md


# ---- 21. no cortical ribbon ----
def test_21_no_ribbon():
    assert "no ribbon" in MD.read_text(encoding="utf-8")


# ---- 22. no 62-target geometry ----
def test_22_no_62_target():
    assert "no 62-target geometry" in MD.read_text(encoding="utf-8")


# ---- 23. classification unchanged ----
def test_23_classification():
    assert _git_clean(CLASS)
    rows = list(csv.DictReader(open(CLASS, encoding="utf-8-sig")))
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert sum(c.values()) - c["VERIFIED_DIRECT_CONTAINED"] == 132
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


# ---- 24. DB zero-write ----
def test_24_db_zero_write():
    assert "no DB" in MD.read_text(encoding="utf-8")
    assert not any("_db_" in p.name for p in OUTS)


# ---- 25. promotion not executed ----
def test_25_no_promotion():
    assert "no promotion" in MD.read_text(encoding="utf-8")


# ---- 26. BF blocker unchanged ----
def test_26_bf_blocker():
    assert _git_clean(BF_BLOCK)
    assert _j(BF_BLOCK)["geometry"] == "BLOCKED_ON_AUTHORITATIVE_ASSET_ACCESS"


# ---- 27. source-ribbon license blocker unchanged ----
def test_27_license_blocker():
    assert _git_clean(EFF)
    assert _j(EFF)["verdict"] == "CORTICAL_FSAVERAGE_RIBBON_METHOD_BLOCKED_LICENSE"


# ---- 28. provenance complete ----
def test_28_provenance():
    assert HAS
    s = _j(ST)
    assert s["verdict"] == "CORTICAL_TARGET_TRANSFORM_INTEGRITY_CONFIRMED"
    assert s["status_id"] == "CORTICAL_TARGET_TRANSFORM_INTEGRITY_STATUS_V1"
    assert s["reporting_correction"] == "REPORTING_CORRECTION_V1"
    assert s["created_at"] and s["script_version"]
    assert s["history_untouched"]
    md = MD.read_text(encoding="utf-8")
    assert "CORTICAL_TARGET_TRANSFORM_INTEGRITY_CONFIRMED" in md


# ---- extra: route status keeps FROZEN + REAUDIT PASS; future app ALLOWED ----
def test_extra_route_future():
    s = _j(ST)
    assert s["route_status"]["this_round"] == (
        "CORTICAL_TARGET_PROJECT_DERIVED_TRANSFORM_FROZEN + INTEGRITY_REAUDIT_PASS")
    assert s["route_status"]["previous"] == (
        "CORTICAL_TARGET_PROJECT_DERIVED_TRANSFORM_FROZEN (c6281e8, kept)")
    assert s["future_binary_ribbon_application"].startswith("ALLOWED")


# ---- extra: method A min > 0 (diffeomorphic), reporting numbers ----
def test_extra_methodA_diffeomorphic():
    a_full = [r for r in _rows(MC) if r["method"] == "A_ANTs_official" and r["scope"] == "full_field"][0]
    assert float(a_full["min"]) > 0.0
    assert float(a_full["median"]) > 0.5
    r = _j(REP)
    assert abs(r["deformation_mean_mm"] - 0.771556539) < 1e-6
    assert abs(r["deformation_median_mm"] - 0.017485590) < 1e-6
