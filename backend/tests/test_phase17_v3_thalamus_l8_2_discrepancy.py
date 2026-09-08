"""Phase1.7 V3 - Tha_L_8_2 / mPMtha-L direct spatial discrepancy root-cause audit tests.

Read-only: validates the audit artifacts and 22 invariants; never modifies DB /
lifecycle / classification / promotion; no commit. Local-NIfTI / big-asset tests
skip when the files are absent (clean repo).
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
RAW_BN = BACKEND / "data" / "atlases" / "brainnetome" / "bna246" / "volume_raw" / "BNA_PM_4D.nii.gz"
DERIVED = BACKEND / "data" / "atlases" / "derived_g1"
G1_LEFT = DERIVED / "left_thalamus_proper_prob_mni2009casym.nii.gz"
G1_RIGHT = DERIVED / "right_thalamus_proper_prob_mni2009casym.nii.gz"
BN_PM_DIR = BACKEND / "data" / "atlases" / "brainnetome" / "bna246" / "transformed_to_julich2009c" / "probability_maps"
G3MAN = BACKEND / "data" / "integration" / "g3_to_g1" / "g3_to_g1_full_decision_coverage_manifest.csv"
ROLLUP_CSV = D16 / "phase17_v3_thalamus_bn_rollup_compatibility.csv"
BN_XFORM_MAN = BACKEND / "data" / "integration" / "g3_brainnetome_assets" / "g3_brainnetome_to_julich_batch_transform_manifest.csv"
RAW_BN_SHA = "b1318517f61d08f714c25e55ee580eb8a487c0b7ab1ddbcc7eac852e4e97f020"
G1_LEFT_SHA = "bd431608fcea3c5f0f7387b1b0e1010582fa2e39dae95a300b3bba976a10cc87"
G1_RIGHT_SHA = "73e4242b581f2420c316593f6cd85183ea7f99c29e2b817b0257cdf267c5bd3b"
V3_SHA = "22e24a31bab9659769f7e550ee32f8e3b37887d0ae1a4c4c4cf64974c3c05f68"
V1 = D16 / "phase17_v3_thalamus_g1_scope_contract.json"
V2 = D16 / "phase17_v3_thalamus_g1_scope_contract_v2.json"
V3 = D16 / "phase17_v3_thalamus_g1_scope_contract_v3.json"
CLASS = D16 / "phase17_v3_classification.csv"

SRC = D16 / "phase17_v3_thalamus_l8_2_source_geometry_qc.csv"
ROUTE = D16 / "phase17_v3_thalamus_l8_2_spatial_route_qc.csv"
PROFILE = D16 / "phase17_v3_thalamus_l8_2_probability_profile.csv"
SUMMARY = D16 / "phase17_v3_thalamus_l8_2_discrepancy_summary.json"
PROV = D16 / "phase17_v3_thalamus_l8_2_discrepancy_provenance.json"
MD = D16 / "phase17_v3_thalamus_l8_2_discrepancy_diagnostics.md"
HAS = SRC.exists() and ROUTE.exists() and PROFILE.exists() and SUMMARY.exists() and PROV.exists()

PRI, CTRL = "Tha_L_8_2", "Tha_R_8_2"


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _sum():
    return json.load(open(SUMMARY, encoding="utf-8"))


def _prov():
    return json.load(open(PROV, encoding="utf-8"))


def _rows(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _git_clean(*paths: Path) -> bool:
    r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *[str(p) for p in paths]],
                       cwd=BACKEND.parent, capture_output=True)
    return r.returncode == 0


# ---- 1. primary case exactly L8_2 ----
def test_1_primary_is_l8_2():
    assert _sum()["primary_case"] == "Tha_L_8_2"
    assert _sum()["dec_thal_direct_02"] == "DEC-THAL-DIRECT-02"


# ---- 2. R8_2 is the only paired control ----
def test_2_paired_control_r8_2_only():
    s = _sum()
    assert s["paired_control"] == "Tha_R_8_2"
    assert s["neighbour_controls_read_only"] == [
        "Tha_L_8_1/Tha_R_8_1", "Tha_L_8_3/Tha_R_8_3", "Tha_L_8_4/Tha_R_8_4"]


# ---- 3. raw BNA source identity verified ----
@pytest.mark.skipif(not RAW_BN.exists(), reason="raw BNA absent (clean repo)")
def test_3_raw_source_identity():
    p = _prov()
    assert p["raw_bna"]["sha256"] == RAW_BN_SHA
    assert _sha(RAW_BN) == RAW_BN_SHA


# ---- 4. source label / channel verified ----
def test_4_source_label_channel():
    p = _prov()
    assert p["raw_bna"]["component_index"] == 233
    assert p["raw_bna"]["channel_index"] == 232
    fr = p["frozen_g3_relation"]
    assert fr["official_label"] == "Tha_L_8_2"
    assert fr["g3_region_id"] == "NGIQ-BR-00000233"
    assert fr["frozen_g1_target"] == "NGIQ-BR-00000247"
    man = {r["official_code"]: r for r in
           csv.DictReader(open(G3MAN, encoding="utf-8-sig"))}
    assert man["Tha_L_8_2"]["g3_entity_id"] == "NGIQ-BR-00000233"
    roll = {r["decision_id"]: r for r in
            csv.DictReader(open(ROLLUP_CSV, encoding="utf-8-sig"))}
    assert roll["DEC-THAL-ROLLUP-02"]["g3_region_id"] == "NGIQ-BR-00000233"
    assert roll["DEC-THAL-ROLLUP-02"]["abbreviation"] == "mPMtha"


# ---- 5. BNA spatial route provenance complete ----
def test_5_route_provenance_complete():
    p = _prov()
    rt = p["bna_spatial_route"]
    for k in ("batch_manifest_sha256", "source_space", "target_space", "tool",
              "tool_version", "interpolation", "transform_sha256"):
        assert rt.get(k), k
    assert rt["transform_status"] == "PASS"
    assert rt["all_16_uniform"] is True
    man = {int(r["component_index"]): r for r in
           csv.DictReader(open(BN_XFORM_MAN, encoding="utf-8-sig"))}
    assert man[233]["official_code"] == "Tha_L_8_2"
    assert man[233]["transform_sha256"] == rt["transform_sha256"]
    assert man[233]["interpolation"] == "Linear"


# ---- 6. transformed SHA verified ----
def test_6_transformed_sha_verified():
    p = _prov()
    pshas = p["transformed_geometry"]["per_parcel_sha"]
    assert len(pshas) == 8
    for code, comp in {"Tha_L_8_2": 233, "Tha_R_8_2": 234}.items():
        assert len(pshas[code]) == 64
        f = BN_PM_DIR / f"BNA_PM_comp{comp}_{code}_prob_2009c.nii.gz"
        if f.exists():
            assert _sha(f) == pshas[code]
    man = {int(r["component_index"]): r for r in
           csv.DictReader(open(BN_XFORM_MAN, encoding="utf-8-sig"))}
    assert pshas["Tha_L_8_2"] == man[233]["output_sha256"]
    assert pshas["Tha_R_8_2"] == man[234]["output_sha256"]


# ---- 7. no mapping-derived geometry ----
def test_7_no_mapping_derived_geometry():
    s = _sum()
    assert s["internal_geometry_qc"]["self_atlas_qc_only"] is True
    assert s["internal_geometry_qc"]["not_mapping_evidence"] is True
    assert s["classification_independent"] is True
    rt = _prov()["bna_spatial_route"]
    assert "MNI152NLin2009cAsym" in rt["target_space"]


# ---- 8. raw -> target geometry QC complete ----
def test_8_raw_target_qc_complete():
    src = {r["code"]: r for r in _rows(SRC)}
    rt = {r["code"]: r for r in _rows(ROUTE)}
    for code in (PRI, CTRL):
        assert code in src and code in rt
        for k in ("raw_nz_voxels", "raw_physical_volume_mm3", "raw_centroid_x",
                  "raw_centroid_y", "raw_centroid_z", "raw_bbox_xmin", "raw_cc",
                  "raw_wrong_side_mass_fraction"):
            assert src[code].get(k) is not None, (code, k)
        for k in ("target_nz_voxels", "target_volume_mm3", "target_centroid_x",
                  "target_centroid_y", "target_centroid_z", "target_cc",
                  "volume_relative_change", "manifest_correct_side_mass_fraction",
                  "route_transform_status", "transform_sha256"):
            assert rt[code].get(k) is not None, (code, k)
    assert rt[PRI]["target_cc"] == "1"


# ---- 9. bilateral asymmetry stage identified ----
def test_9_asymmetry_stage_identified():
    s = _sum()
    assert s["asymmetry_stage"].startswith("STAGE_A_RAW_BNA_INTRINSIC_ASYMMETRY")
    m = s["asymmetry_stage_metrics"]
    assert abs(float(m["stage_C_containment_L"]) - 0.1232) < 0.005
    assert abs(float(m["stage_C_containment_R"]) - 0.5191) < 0.005
    assert abs(float(m["stage_C_containment_abs_diff"]) - 0.3959) < 0.005
    assert float(m["stage_A_raw_mirror_distance_L_vs_R"]) > float(m["stage_A_control_mirror_max"])
    assert float(m["stage_A_volume_ratio_L_R"]) < 0.85


# ---- 10. G1 probability profile complete ----
def test_10_probability_profile_complete():
    rows = {r["code"]: r for r in _rows(PROFILE)}
    for code in (PRI, CTRL):
        assert code in rows
        r = rows[code]
        for k in ("pct_min", "pct_p05", "pct_median", "pct_p95", "pct_max", "mean",
                  "band_p_eq_0", "band_p_0_0_1", "band_p_ge_0_75"):
            assert r.get(k) is not None, k
    assert abs(float(rows[PRI]["mean"]) - 0.1232) < 0.005
    assert abs(float(rows[CTRL]["mean"]) - 0.5191) < 0.005


# ---- 11. discrepancy localization complete ----
def test_11_discrepancy_localization_complete():
    d = _sum()["discrepancy_localization"]
    assert d["mask_definition"].startswith("Tha_L_8_2 parcel support AND P_G1<0.1")
    assert int(d["discrepant_support_voxels"]) > 1000
    assert float(d["discrepant_mass_fraction_of_parcel"]) > 0.5
    assert len(d["discrepant_centroid_world_mm"]) == 3
    assert "LATERAL" in d["direction"] and "ANTERIOR" in d["direction"]
    assert "distance_shells_of_parcel_mass_vs_G1_envelope" in d


# ---- 12. Reticular / excluded-territory check complete ----
def test_12_reticular_excluded_check():
    s = _sum()
    fs = s["fs_geometry_categorization"]["left_mPMtha"]
    for k in ("in_G1_support", "in_FS_full_thalami_incl_reticular",
              "reticular_strong_gt_0_5", "reticular_partial_shell", "outside_FS_thalami"):
        assert k in fs
    assert float(fs["reticular_strong_gt_0_5"]) < 0.05
    assert float(s["discrepancy_localization"]["reticular_strong_overlap_inside_discrepant_region"]) < 0.05
    assert "ZI/subthalamus" in s["discrepancy_localization"]["zi_subthalamus_note"]


# ---- 13. shared-template uncertainty considered ----
def test_13_shared_template_uncertainty():
    s = _sum()
    assert s["template_variant_uncertainty"] == "PRESENT"
    assert "NOT_EXPLICITLY_WARP_CORRECTED" in s["residual_spatial_limitation"]
    assert "conclusion" in s["shared_template_variant_analysis"]
    assert "NLin6Asym" in s["shared_template_variant_analysis"]["bna_route"]
    assert "2009cSym" in s["shared_template_variant_analysis"]["g1_route"]


# ---- 14. no transform retuning / target-driven correction ----
def test_14_no_transform_retuning():
    s = _sum()
    assert s["target_driven_correction_applied"] is False
    assert s["no_transform_retuning"] is True
    assert _prov()["target_driven_correction"] is False


# ---- 15. no threshold tuning ----
def test_15_no_threshold_tuning():
    assert _sum()["no_threshold_tuning"] is True


# ---- 16. no scope modification / no G1 change ----
def test_16_no_scope_modification():
    assert _sum()["no_scope_modification"] is True
    assert _prov()["classification_csv"] == "NOT_TOUCHED"


# ---- 17. V1/V2/V3 unchanged ----
def test_17_contracts_unchanged():
    assert _git_clean(V1, V2, V3)


# ---- 18. historical direct-validation outputs not silently rewritten ----
def test_18_historical_outputs_not_rewritten():
    s = _sum()
    assert s["historical_direct_validation_outputs_rewritten"] is False
    mg = s["mapping_gate"]
    assert mg["superseding_mapping_verdict"] == "KEEP_FROZEN_MAPPING_WITH_SPATIAL_UNCERTAINTY"
    assert "supersedes" in mg and "prior FROZEN_MAPPING_REQUIRES_REVIEW" in mg["supersedes"]
    assert mg["direct_conflict_count"] == 0
    assert mg["requires_review_count_before_supersession"] == 1
    assert "NOT a confirmed mapping conflict" in mg["clarification"]
    dec_f = D16 / "phase17_v3_thalamus_bn_direct_spatial_decisions.csv"
    if dec_f.exists():
        rows = {r["decision_id"]: r for r in
                csv.DictReader(open(dec_f, encoding="utf-8-sig"))}
        assert rows["DEC-THAL-DIRECT-02"]["mapping_verdict"] == "FROZEN_MAPPING_REQUIRES_REVIEW"


# ---- 19. classification byte-identical ----
def test_19_classification_unchanged():
    assert _git_clean(CLASS)
    rows = list(csv.DictReader(open(CLASS, encoding="utf-8-sig")))
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert sum(c.values()) - c["VERIFIED_DIRECT_CONTAINED"] == 132
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


# ---- 20. DB zero-write ----
def test_20_db_zero_write():
    assert _prov()["db_write"] is False
    assert _sum()["db_zero_write"] is True


# ---- 21. Promotion blocked ----
def test_21_promotion_blocked():
    assert _sum()["promotion"] == "BLOCKED"
    assert _prov()["promotion"] is False


# ---- 22. provenance complete ----
def test_22_provenance_complete():
    p = _prov()
    assert p["function"].startswith("Tha_L_8_2")
    assert p["frozen_g3_relation"]["frozen_g1_target"] == "NGIQ-BR-00000247"
    assert p["raw_bna"]["sha256"] == RAW_BN_SHA
    assert p["bna_spatial_route"]["batch_manifest_sha256"]
    assert p["transformed_geometry"]["per_parcel_sha"]
    assert p["current_g1_geometry"]["left_sha256"] == G1_LEFT_SHA
    assert p["current_g1_geometry"]["right_sha256"] == G1_RIGHT_SHA
    assert p["spatial_bridge"]["spatial_bridge_id"] == "SPB-MNI2009C-SYM-ASYM-SHARED-FRAME-V1"
    assert p["v3_scope_contract"]["sha256"] == V3_SHA
    assert p["freesurfer_iglesias_source"]["sha256"]
    assert p["classification_independent"] is True
    assert p["script"].startswith("phase17_v3_audit_thalamus_l8_2_discrepancy.py")


# ---- additional structural checks ----
def test_root_cause_verdict_shape():
    rv = _sum()["root_cause_verdict"]
    assert rv["primary"] == "G1_PROBABILITY_ENVELOPE_BOUNDARY_LIMITATION"
    assert rv["secondary"] == ["SHARED_TEMPLATE_VARIANT_BOUNDARY_MISMATCH"]
    assert rv["rejected"]["F_TRUE_MAPPING_INCOMPATIBILITY_SUPPORTED"].startswith("not supported")
    assert rv["rejected"]["G_ROOT_CAUSE_UNRESOLVED"] == "resolved"


def test_true_mapping_incompatibility_not_supported():
    assert _sum()["mapping_gate"]["true_mapping_incompatibility_supported"] is False
    assert _sum()["mapping_gate"]["postconstruction_gate"] == "CLOSABLE_NO_MAPPING_CONFLICT"


def test_independent_anatomical_support_present():
    ia = _sum()["independent_anatomical_support"]
    assert ia["status"] in ("RUN", "NOT_RUN")
    if ia["status"] == "RUN":
        assert ia["L8_2_inG1_ge_0_1"]["Thalamus_L"] > 0.5
        assert ia["L8_2_whole"]["Thalamus_R"] == 0.0
        assert ia["L8_2_whole"]["n_voxels"] > 0


def test_freeze_enabled_after_audit_then_formed():
    # this audit round enabled (but did not auto-write) the freeze; the dedicated
    # freeze round then formed THALAMUS_PHASE17_FINAL_FREEZE_V1.
    mg = _sum()["mapping_gate"]
    assert mg["final_freeze"] == "ENABLED_RECOMMEND_FORM_IN_FREEZE_GATE"
    assert (D16 / "phase17_v3_thalamus_final_freeze_v1.json").exists()


def test_no_reticular_added_back():
    fs = _sum()["fs_geometry_categorization"]["left_mPMtha"]
    assert float(fs["reticular_strong_gt_0_5"]) < float(fs["in_G1_support"])
