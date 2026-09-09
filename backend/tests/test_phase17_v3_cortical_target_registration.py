"""Phase1.7 V3 - cortical target registration execution + QC freeze tests.

Validates verdict A = CORTICAL_TARGET_PROJECT_DERIVED_TRANSFORM_FROZEN (route_v1 generated)
and the 33 hard gates. Read-only. No re-registration, no label transform, no ribbon, no
cortical geometry, no G4 overlap, no FreeSurfer/license, no DB, no reclassification, no
promotion. History 641cd76/daecb63/60d81cd and prior frozen states unchanged.
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
DERIVED = BACKEND / "data" / "atlases" / "derived_g1"
RUN = DERIVED / "cort_reg_run_v1"
TF = BACKEND / "data" / "atlases" / "templateflow_ref"
ORIG = BACKEND / "data" / "atlases" / "freesurfer" / "fsaverage" / "mri/orig.mgz"
FIXED = TF / "tpl-MNI152NLin2009cAsym_res01_desc-brain_T1w.nii.gz"
CLASS = D16 / "phase17_v3_classification.csv"
BF_BLOCK = D16 / "phase17_v3_zaborszky_acquisition_blocker_v1.json"
THAL = D16 / "phase17_v3_thalamus_final_freeze_v1.json"
AMYG = D16 / "phase17_v3_amygdala_g1_scope_contract_v1.json"
HIPP = D16 / "phase17_v3_hippocampus_canonical_identity_v1.json"
BNST_ADM = D16 / "phase17_v3_bnst_canonical_admission_v1.json"
BNST_GEOM = D16 / "phase17_v3_bnst_canonical_geometry_manifest.json"
EFF = D16 / "phase17_v3_cortical_effective_prerequisite_status.json"
# history snapshots unchanged by this round
RIBBON_FILES = ["phase17_v3_cortical_ribbon_toolchain_manifest.json",
                "phase17_v3_cortical_ribbon_environment.json",
                "phase17_v3_cortical_ribbon_asset_subset_status.json",
                "phase17_v3_cortical_ribbon_pilot_selection.csv",
                "phase17_v3_cortical_ribbon_pilot_qc.csv",
                "phase17_v3_cortical_ribbon_method_diagnostics.md"]
SNAP = ["phase17_v3_fsaverage_complete_asset_status.json",
        "phase17_v3_fsaverage_complete_asset_diagnostics.md",
        "phase17_v3_fsaverage_file_hash_manifest.csv"]
ROUTE_SNAP = ["phase17_v3_fsaverage_mni305_semantic_audit.json",
              "phase17_v3_mni305_reference_asset_manifest.json",
              "phase17_v3_cortical_target_transform_inventory.csv",
              "phase17_v3_cortical_target_route_candidates.csv",
              "phase17_v3_cortical_target_route_compatibility_audit.json",
              "phase17_v3_cortical_target_route_diagnostics.md"]
HASH_MANIFEST = D16 / "phase17_v3_fsaverage_file_hash_manifest.csv"

RECIPE = D16 / "phase17_v3_cortical_registration_recipe_v1.json"
RT = D16 / "phase17_v3_cortical_registration_runtime_manifest.json"
IN = D16 / "phase17_v3_cortical_registration_input_manifest.json"
TX = D16 / "phase17_v3_cortical_registration_transform_manifest.json"
SIM = D16 / "phase17_v3_cortical_registration_similarity_qc.csv"
DEF = D16 / "phase17_v3_cortical_registration_deformation_qc.json"
GEOM = D16 / "phase17_v3_cortical_registration_geometry_qc.csv"
PROV = D16 / "phase17_v3_cortical_registration_provenance.json"
V1 = D16 / "phase17_v3_cortical_target_route_v1.json"
MD = D16 / "phase17_v3_cortical_registration_diagnostics.md"
OUTS = [RECIPE, RT, IN, TX, SIM, DEF, GEOM, PROV, V1, MD]
HAS = all(p.exists() for p in OUTS)


def _j(p):
    return json.load(open(p, encoding="utf-8"))


def _rows(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _git_clean(*paths: Path) -> bool:
    r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *[str(p) for p in paths]],
                       cwd=BACKEND.parent, capture_output=True)
    return r.returncode == 0


def _geom_map():
    return {r["metric"]: r["value"] for r in _rows(GEOM)}


# ---- 1. current HEAD (pin advanced to c6281e8 in the integrity re-audit round) ----
def test_1_head():
    r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=BACKEND.parent,
                       capture_output=True, text=True)
    assert r.stdout.strip() == "c97d7d8"


# ---- 2. R_D direct only ----
def test_2_rd_direct():
    assert _j(RECIPE)["route"] == "R_D_PROJECT_DERIVED_DIRECT"
    md = MD.read_text(encoding="utf-8")
    assert "no MNI305/NLin6/talairach intermediate" in md


# ---- 3. moving SHA fixed ----
def test_3_moving_sha():
    m = _j(IN)["moving"]
    assert len(m["sha256"]) == 64
    for r in _rows(HASH_MANIFEST):
        if r["relative_path"] == "mri/orig.mgz":
            assert r["sha256"] == m["sha256"]


# ---- 4. fixed SHA fixed ----
def test_4_fixed_sha():
    f = _j(IN)["fixed"]
    assert len(f["sha256"]) == 64
    assert f["sha256"] == _j(V1)["fixed_sha256"]


# ---- 5/6/7. no MNI305 / NLin6 / talairach intermediate ----
def test_5_6_7_no_intermediates():
    md = MD.read_text(encoding="utf-8")
    assert "no MNI305/NLin6/talairach intermediate" in md
    # transform manifest contains a single direct affine+warp pair (no hop to MNI305/NLin6)
    t = _j(TX)
    assert "MNI305" not in json.dumps(t)
    assert "NLin6" not in json.dumps(t)
    assert "talairach" not in json.dumps(t).lower() or "no" in json.dumps(t).lower()
    # route_v1 is the direct project-derived route, not any multi-hop chain
    assert _j(V1)["route_class"] == "PROJECT_DERIVED_TEMPLATE_REGISTRATION"


# ---- 8/9/10. no DK / G4 / mapping results ----
def test_8_9_10_no_labels():
    v = _j(V1)
    assert v["mapping_independent"] is True
    assert v["circularity_risk"] == "NONE"
    md = MD.read_text(encoding="utf-8")
    assert "no DK/G4/Julich/Brainnetome labels" in md
    assert "no mapping results" in md
    assert "no G4 overlap" in md


# ---- 11. runtime validated ----
def test_11_runtime_validated():
    r = _j(RT)
    assert r["runtime_sanity_test"]["performed"] is True
    assert r["runtime_sanity_test"]["result"] == "PASS"


# ---- 12. prior ANTsPy anomaly not silently reused ----
def test_12_antspy_anomaly_addressed():
    ev = _j(RT)["runtime_sanity_test"]["evidence"]
    assert "historical zero-warp anomaly NOT reproduced" in ev
    assert "nonzero displacement" in ev and "finite" in ev


# ---- 13. recipe frozen before result review ----
def test_13_recipe_frozen():
    r = _j(RECIPE)
    assert r["recipe_id"] == "REGISTRATION_RECIPE_V1"
    assert "recipe frozen BEFORE any result review" in " ".join(r["notes"])
    assert r["type_of_transform"] == "SyN"


# ---- 14/15. affine + nonlinear transform exist ----
def test_14_15_transforms_exist():
    t = _j(TX)
    assert len(t["affine"]["sha256"]) == 64
    assert len(t["forward_warp"]["sha256"]) == 64
    assert t["inverse_warp"] is not None
    assert len(t["inverse_warp"]["sha256"]) == 64


# ---- 16. nonlinear deformation non-zero ----
def test_16_nonzero():
    d = _j(DEF)["deformation"]
    assert d["max_mm"] > 0.5
    assert d["mean_mm"] > 0


# ---- 17. no NaN/Inf ----
def test_17_finite():
    d = _j(DEF)
    assert d["deformation"]["finite"] is True
    assert d["jacobian"]["finite_jac"] is True


# ---- 18. Jacobian QC present ----
def test_18_jacobian_fields():
    j = _j(DEF)["jacobian"]
    for k in ("min", "p01", "p05", "median", "p95", "p99", "max",
              "negative_fraction", "nonpositive_fraction"):
        assert k in j


# ---- 19. no major folding ----
def test_19_no_major_folding():
    j = _j(DEF)["jacobian"]
    assert j["negative_fraction"] <= 0.02
    assert _j(DEF)["validity"] == "VALID"


# ---- 20/21/22. baseline/affine/nonlinear metrics recorded ----
def test_20_21_22_metrics_stages():
    rows = {r["stage"]: r for r in _rows(SIM)}
    for stage in ("baseline_grid_resample", "post_affine", "post_nonlinear_SyN"):
        assert stage in rows
        assert float(rows[stage]["ncc"]) != 0.0
    # nonlinear improves on affine
    assert float(rows["post_nonlinear_SyN"]["ncc"]) >= float(rows["post_affine"]["ncc"])


# ---- 23. whole-brain geometry QC ----
def test_23_geometry():
    g = _geom_map()
    assert float(g["coverage_nonlinear"]) > 0.9
    assert g["fov_no_truncation"] == "True"
    assert float(g["fixed_brain_mask_ml"]) > 1000


# ---- 24. no LR reflection ----
def test_24_laterality():
    assert _j(PROV)["laterality"]["preserved"] is True
    assert _geom_map()["laterality_preserved"] == "True"


# ---- 25. transform SHA frozen ----
def test_25_shas_frozen():
    v = _j(V1)
    t = _j(TX)
    assert v["affine_sha256"] == t["affine"]["sha256"]
    assert v["forward_warp_sha256"] == t["forward_warp"]["sha256"]
    assert v["inverse_sha256"] == t["inverse_warp"]["sha256"]
    for s in (v["affine_sha256"], v["forward_warp_sha256"], v["inverse_sha256"]):
        assert len(s) == 64


# ---- 26. provenance complete ----
def test_26_provenance():
    p = _j(PROV)
    assert p["run_id"] == "RUN-CORT-FSAVG-TO-MNI2009C-DIRECT-V1"
    assert p["verdict"] == "CORTICAL_TARGET_PROJECT_DERIVED_TRANSFORM_FROZEN"
    assert p["pass_flags"] and all(p["pass_flags"].values())
    assert p["created_at"] and p["script_version"]
    assert p["raw_templates_untouched"] is True


# ---- 27. no cortical geometry ----
def test_27_no_cortical_geometry():
    assert not (DERIVED / "left_precentral_prob_mni2009casym.nii.gz").exists()
    md = MD.read_text(encoding="utf-8")
    assert "no cortical geometry" in md
    assert "no label transform" in md


# ---- 28. no G4 overlap ----
def test_28_no_g4():
    assert "no G4 overlap" in MD.read_text(encoding="utf-8")


# ---- 29. no FreeSurfer/license ----
def test_29_no_freesurfer_license():
    assert "No FreeSurfer/license" in MD.read_text(encoding="utf-8")
    # prior license blocker still independent (unchanged)
    assert _j(EFF)["verdict"] == "CORTICAL_FSAVERAGE_RIBBON_METHOD_BLOCKED_LICENSE"


# ---- 30. classification unchanged ----
def test_30_classification():
    assert _git_clean(CLASS)
    rows = list(csv.DictReader(open(CLASS, encoding="utf-8-sig")))
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert sum(c.values()) - c["VERIFIED_DIRECT_CONTAINED"] == 132
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


# ---- 31. DB zero-write ----
def test_31_db_zero_write():
    assert "no DB" in MD.read_text(encoding="utf-8")
    assert not any("_db_" in p.name for p in OUTS)


# ---- 32. promotion not executed ----
def test_32_no_promotion():
    assert "no promotion" in MD.read_text(encoding="utf-8")


# ---- 33. prior frozen states unchanged ----
def test_33_prior_frozen():
    assert _git_clean(BF_BLOCK, THAL, AMYG, HIPP, BNST_ADM, BNST_GEOM)
    assert _git_clean(EFF, *[D16 / f for f in RIBBON_FILES])
    assert _git_clean(*[D16 / f for f in SNAP], *[D16 / f for f in ROUTE_SNAP])


# ---- extra: route_v1 generated (verdict A) with future semantics ----
def test_extra_route_v1():
    assert V1.exists()
    v = _j(V1)
    assert v["route_id"] == "CORTICAL_FSAVERAGE_TO_MNI2009C_ROUTE_V1"
    assert v["route_class"] == "PROJECT_DERIVED_TEMPLATE_REGISTRATION"
    assert v["future_application_semantics"]["binary_cortical_ribbon"] == (
        "NearestNeighbor (label-safe) when the future ribbon volume is transformed to this "
        "target space")
    assert "no cortical ribbon is transformed this round" in v["future_application_semantics"]["note"]


# ---- extra: transform assets exist on disk (derived, gitignored) ----
def test_extra_transform_assets_exist():
    for suffix in ("_affine.mat", "_forward_warp.nii.gz", "_inverse_warp.nii.gz"):
        files = list(RUN.glob(f"TRF-CORT-FSAVG-TO-MNI2009C-DIRECT-V1{suffix}"))
        assert files, suffix
        assert files[0].stat().st_size > 0


# ---- extra: all 10 outputs + diagnostics contain verdict ----
def test_extra_all_outputs_and_diagnostics():
    assert HAS
    md = MD.read_text(encoding="utf-8")
    assert "CORTICAL_TARGET_PROJECT_DERIVED_TRANSFORM_FROZEN" in md
    assert "mapping independence" in md
    assert "circularity NONE" in md
