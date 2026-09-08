"""Phase1.7 V3 - Thalamus BN G3 -> THALAMUS_PROPER G1 direct spatial validation tests.

Validates the formal per-relation direct-spatial decision records
(DEC-THAL-DIRECT-01..16), evidence grades, bilateral QA, Reticular-exclusion QC and
final-freeze assessment. Read-only: never modifies DB / lifecycle / classification /
promotion; no commit. Local NIfTI-dependent tests skip in a clean repo.
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
DERIVED = BACKEND / "data" / "atlases" / "derived_g1"
BN_PM_DIR = BACKEND / "data" / "atlases" / "brainnetome" / "bna246" / "transformed_to_julich2009c" / "probability_maps"
SPB_MAN = D16 / "phase17_v3_thalamus_spatial_bridge_manifest.json"

G3MAN = BACKEND / "data" / "integration" / "g3_to_g1" / "g3_to_g1_full_decision_coverage_manifest.csv"
ROLLUP_CSV = D16 / "phase17_v3_thalamus_bn_rollup_compatibility.csv"
G1_LEFT = DERIVED / "left_thalamus_proper_prob_mni2009casym.nii.gz"
G1_RIGHT = DERIVED / "right_thalamus_proper_prob_mni2009casym.nii.gz"
G1_LEFT_SHA = "bd431608fcea3c5f0f7387b1b0e1010582fa2e39dae95a300b3bba976a10cc87"
G1_RIGHT_SHA = "73e4242b581f2420c316593f6cd85183ea7f99c29e2b817b0257cdf267c5bd3b"
SUP_LEFT = "37a82b65d86d81b1558582dee301e79ee367d60856f95d6a55b0219cf28a87a1"
SUP_RIGHT = "1c9b8b8de9103c1e091c9fb6e0577182416d5a6ba0c1b7f6d41e1e913958253f"
SPB_ID = "SPB-MNI2009C-SYM-ASYM-SHARED-FRAME-V1"
LIM = "TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_WARP_CORRECTED"
EVTYPE = "DIRECT_SPATIAL_OVERLAP_IN_SHARED_MNI2009C_COORDINATE_FRAME"
V3_SHA = "22e24a31bab9659769f7e550ee32f8e3b37887d0ae1a4c4c4cf64974c3c05f68"
ALLOWED_GRADES = {
    "DIRECTLY_SUPPORTED",
    "DIRECTLY_SUPPORTED_WITH_BOUNDARY_UNCERTAINTY",
    "DIRECT_SPATIAL_CONFLICT",
    "DIRECT_EVIDENCE_INSUFFICIENT",
}
ALLOWED_VERDICTS = {
    "KEEP_FROZEN_MAPPING_DIRECTLY_SUPPORTED",
    "KEEP_FROZEN_MAPPING_WITH_SPATIAL_UNCERTAINTY",
    "FROZEN_MAPPING_REQUIRES_REVIEW",
    "FROZEN_MAPPING_DIRECT_CONFLICT",
}
LSG_IDS = {"DEC-THAL-DIRECT-05", "DEC-THAL-DIRECT-06", "DEC-THAL-DIRECT-07",
           "DEC-THAL-DIRECT-13", "DEC-THAL-DIRECT-14", "DEC-THAL-DIRECT-15"}

RESULTS = D16 / "phase17_v3_thalamus_bn_direct_spatial_results.csv"
DECISIONS = D16 / "phase17_v3_thalamus_bn_direct_spatial_decisions.csv"
SUMMARY = D16 / "phase17_v3_thalamus_bn_direct_spatial_summary.json"
PROV = D16 / "phase17_v3_thalamus_bn_direct_spatial_provenance.json"
MD = D16 / "phase17_v3_thalamus_bn_direct_spatial_diagnostics.md"
FREEZE = D16 / "phase17_v3_thalamus_final_freeze_v1.json"
CLASS = D16 / "phase17_v3_classification.csv"
V1 = D16 / "phase17_v3_thalamus_g1_scope_contract.json"
V2 = D16 / "phase17_v3_thalamus_g1_scope_contract_v2.json"
V3 = D16 / "phase17_v3_thalamus_g1_scope_contract_v3.json"

_HAS_ART = RESULTS.exists() and DECISIONS.exists() and SUMMARY.exists() and PROV.exists()
_HAS_NIFTI = G1_LEFT.exists() and G1_RIGHT.exists()


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _sum() -> dict:
    return json.load(open(SUMMARY, encoding="utf-8"))


def _prov() -> dict:
    return json.load(open(PROV, encoding="utf-8"))


def _res_rows() -> list[dict]:
    return list(csv.DictReader(open(RESULTS, encoding="utf-8-sig")))


def _dec_rows() -> list[dict]:
    return list(csv.DictReader(open(DECISIONS, encoding="utf-8-sig")))


def _git_clean(*paths: Path) -> bool:
    r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *[str(p) for p in paths]],
                       cwd=BACKEND.parent, capture_output=True)
    return r.returncode == 0


# ---- 1. universe = 16 ----
def test_1_universe_16():
    assert len(_res_rows()) == 16
    assert len(_dec_rows()) == 16
    assert _sum()["universe"]["total"] == 16


# ---- 2. left = 8 / right = 8 ----
def test_2_left_right_split():
    dec = _dec_rows()
    c = Counter(r["hemisphere"] for r in dec)
    assert c == {"left": 8, "right": 8}
    assert _sum()["universe"]["left"] == 8
    assert _sum()["universe"]["right"] == 8


# ---- 3. all from frozen manifest (no hand-written 16 authority) ----
def test_3_from_frozen_manifest():
    man = {r["official_code"]: r for r in
           csv.DictReader(open(G3MAN, encoding="utf-8-sig"))
           if (r.get("official_code") or "").startswith("Tha_")}
    roll = {r["decision_id"]: r for r in
            csv.DictReader(open(ROLLUP_CSV, encoding="utf-8-sig"))}
    assert len(man) == 16 and len(roll) == 16
    p = _prov()
    assert p["frozen_universe"]["n"] == 16
    assert p["frozen_universe"]["manifest_sha256"]
    assert p["frozen_universe"]["rollup_csv_sha256"]
    for r in _dec_rows():
        assert r["official_code"] in man, r["decision_id"]
        assert man[r["official_code"]]["g3_entity_id"] == r["g3_region_id"]
        assert roll[r["rollup_decision_id"]]["frozen_g1_target"] == r["frozen_g1_target"]


# ---- 4. BNA source geometry provenance complete ----
def test_4_bn_source_provenance_complete():
    p = _prov()
    assert len(p["brainnetome_geometry_route"]["per_parcel_shas"]) == 16
    for d in _dec_rows():
        assert len(d["bn_parcel_sha256"]) == 64
        assert d["bn_parcel_sha256"] == p["brainnetome_geometry_route"]["per_parcel_shas"][
            d["official_code"]]
        rel = Path(d["bn_parcel_geometry_path"])
        f = BACKEND / rel
        if f.exists():
            assert _sha(f) == d["bn_parcel_sha256"], d["official_code"]
    route = p["brainnetome_geometry_route"]
    for k in ("source_asset", "source_space", "target_space", "tool",
              "batch_transform_manifest_sha256"):
        assert route.get(k), k


# ---- 5. G1 current geometry provenance complete ----
def test_5_g1_geometry_provenance_complete():
    s = _sum()
    assert s["g1_left_sha"] == G1_LEFT_SHA
    assert s["g1_right_sha"] == G1_RIGHT_SHA
    for d in _dec_rows():
        assert d["g1_sha256"] in (G1_LEFT_SHA, G1_RIGHT_SHA)
        if d["hemisphere"] == "left":
            assert d["g1_geometry_id"] == "GEO-G1-THAL-L-MNI2009CASYM-V1"
            assert d["g1_sha256"] == G1_LEFT_SHA
        else:
            assert d["g1_geometry_id"] == "GEO-G1-THAL-R-MNI2009CASYM-V1"
            assert d["g1_sha256"] == G1_RIGHT_SHA
    p = _prov()
    assert p["g1_left"]["sha256"] == G1_LEFT_SHA
    assert p["g1_right"]["sha256"] == G1_RIGHT_SHA


# ---- 6. superseded SyN geometry not used ----
def test_6_superseded_not_used():
    p = _prov()
    assert p["superseded_g1"]["left"] == SUP_LEFT
    assert p["superseded_g1"]["right"] == SUP_RIGHT
    assert "never consumed as current evidence" in p["superseded_g1"]["note"]
    # current-evidence fields must never equal a superseded SHA
    assert _sum()["g1_left_sha"] != SUP_LEFT and _sum()["g1_right_sha"] != SUP_RIGHT
    for r in _res_rows():
        assert r["g1_sha256"] != SUP_LEFT and r["g1_sha256"] != SUP_RIGHT
    # the superseded SHAs appear only in the documented reject block (provenance /
    # summary), never inside the evidence records (results / decisions CSVs)
    ev = RESULTS.read_text(encoding="utf-8") + DECISIONS.read_text(encoding="utf-8")
    assert SUP_LEFT not in ev and SUP_RIGHT not in ev


# ---- 7. grid / affine exact compatibility (hard gate) ----
@pytest.mark.skipif(not _HAS_NIFTI, reason="NIfTI absent (clean repo)")
def test_7_grid_affine_exact_compatibility():
    import nibabel as nib
    import numpy as np
    spb = json.load(open(SPB_MAN, encoding="utf-8"))
    ref = nib.load(str(BACKEND / spb["julich_target_reference"]["path"]))
    assert tuple(ref.shape) == (193, 229, 193)
    for g in (G1_LEFT, G1_RIGHT):
        img = nib.load(str(g))
        assert tuple(img.shape) == (193, 229, 193)
        assert np.allclose(np.asarray(img.affine), np.asarray(ref.affine), atol=1e-4)
    for d in _dec_rows():
        f = BACKEND / d["bn_parcel_geometry_path"]
        img = nib.load(str(f))
        assert tuple(img.shape) == (193, 229, 193)
        assert np.allclose(np.asarray(img.affine), np.asarray(ref.affine), atol=1e-4)
        assert np.linalg.det(np.asarray(img.affine)) > 0


# ---- 8. circularity NONE ----
def test_8_circularity_none():
    for r in _res_rows():
        assert r["circularity_risk"] == "NONE"
    for d in _dec_rows():
        assert d["circularity_risk"] == "NONE"
    assert _sum()["circularity_risk"] == "NONE"


# ---- 9. continuous probability-weighted evidence is primary ----
def test_9_continuous_primary():
    for r in _res_rows():
        assert r["evidence_mode"] == "CONTINUOUS_PROBABILITY_WEIGHTED_PRIMARY"
        assert 0.0 <= float(r["weighted_containment"]) <= 1.0
        assert float(r["probability_mass_inside_parcel"]) >= 0.0
    required = {"weighted_containment", "probability_mass_inside_parcel",
                "fraction_at_p_gt_0_1", "fraction_at_p_gt_0_25",
                "fraction_at_p_gt_0_5", "fraction_at_p_gt_0_75",
                "outside_support_fraction", "contralateral_fraction",
                "boundary_fraction", "g1_weighted_centroid_distance_mm"}
    assert required <= set(_res_rows()[0].keys())


# ---- 10. no reuse of the old 90/5 proxy ----
def test_10_no_old_90_5_proxy():
    txt = (json.dumps(_sum()) + RESULTS.read_text(encoding="utf-8") +
           DECISIONS.read_text(encoding="utf-8"))
    assert "90%" not in txt and "90 / 5" not in txt
    rl = _sum()["reference_levels"]
    assert "NOT the old G4->G3 90/5 proxy" in rl["rationale"]
    # no categorical band vocabulary reintroduced and no proxy-gate field exists
    assert "DOMINANT_OVERLAP" not in txt and "MATERIAL_OVERLAP" not in txt
    assert "proxy_gate" not in txt and "hard_total" not in txt
    # grades come only from the evidence vocabulary (checked in test_11 as well)
    for r in _res_rows():
        assert r["evidence_grade"] in ALLOWED_GRADES


# ---- 11. no target-driven threshold tuning (grades derive from the geometry) ----
@pytest.mark.skipif(not _HAS_NIFTI, reason="NIfTI absent (clean repo)")
def test_11_no_target_driven_threshold_tuning():
    import nibabel as nib
    import numpy as np
    g = np.asanyarray(nib.load(str(G1_LEFT)).dataobj).astype(np.float64)
    d2 = [d for d in _dec_rows() if d["official_code"] == "Tha_L_8_2"][0]
    f = BACKEND / d2["bn_parcel_geometry_path"]
    bn = np.asanyarray(nib.load(str(f)).dataobj).astype(np.float64)
    C = float((bn * g).sum()) / float(bn.sum())
    O = float((bn * (g <= 0)).sum()) / float(bn.sum())
    assert C < 0.20 and O > 0.30
    assert d2["evidence_grade"] == "DIRECT_SPATIAL_CONFLICT"
    assert _sum()["classification_proposal"]["proposal_scope"]
    assert _sum()["classification_proposal"]["classification_csv_touched"] == "FALSE"
    # grades are confined to the allowed evidence vocabulary
    for r in _res_rows():
        assert r["evidence_grade"] in ALLOWED_GRADES


# ---- 12. DEC-THAL-04 dependency removed for the 6 posterior relations ----
def test_12_dec_thal_04_dependency_removed():
    lsg = [d for d in _dec_rows() if d["decision_id"] in LSG_IDS]
    assert len(lsg) == 6
    for d in lsg:
        assert d["lsg_dependency"] == "DEPENDENCY_ON_DEC_THAL_04"
        assert d["lsg_dependency_resolved"] == "TRUE"
    assert _sum()["lsg_dependent_relations"]["status"] == "ALL_RESOLVED_WITH_DIRECT_EVIDENCE"


# ---- 13. six posterior relations carry direct verdicts (no PENDING_BOUNDARY) ----
def test_13_posterior_relations_direct():
    for d in [x for x in _dec_rows() if x["decision_id"] in LSG_IDS]:
        assert d["evidence_grade"] in ALLOWED_GRADES
        assert d["mapping_verdict"] in ALLOWED_VERDICTS
        assert "PENDING_BOUNDARY" not in d["evidence_grade"]
        assert "PENDING_BOUNDARY" not in d["mapping_verdict"]
    txt = DECISIONS.read_text(encoding="utf-8") + RESULTS.read_text(encoding="utf-8")
    assert "PENDING_BOUNDARY_AND_DIRECT_VALIDATION" not in txt


# ---- 14. Reticular exclusion not reversed / not re-added ----
def test_14_reticular_exclusion_not_reversed():
    qc = _sum()["reticular_exclusion_qc"]
    assert qc["status"] == "PASSED"
    assert "NOT re-added" in qc["note"] or "not re-added" in qc["note"]
    for r in _res_rows():
        if r["reticular_overlap_fraction"] != "":
            assert float(r["reticular_overlap_fraction"]) <= 0.05


# ---- 15. bilateral QA complete ----
def test_15_bilateral_qa_complete():
    bq = _sum()["bilateral_qa"]
    assert bq["total_pairs"] == 8
    pairs = bq["asymmetry_review_pairs"]
    assert len(pairs) >= 1
    for p in pairs:
        assert p["pair_flag"] == "BILATERAL_ASYMMETRY_REVIEW"
        assert p["left_decision"].startswith("DEC-THAL-DIRECT-")
        assert p["right_decision"].startswith("DEC-THAL-DIRECT-")
        assert float(p["containment_abs_diff"]) >= 0.20
    # mPMtha pair (Tha_8_2) must be flagged because L8_2 is a conflict
    assert any(p["zone"] == "Tha_8_2" for p in pairs)


# ---- 16. every relation has a DEC-THAL-DIRECT ID ----
def test_16_every_relation_has_direct_id():
    ids = [d["decision_id"] for d in _dec_rows()]
    assert sorted(ids) == [f"DEC-THAL-DIRECT-{i:02d}" for i in range(1, 17)]
    res_ids = sorted(r["decision_id"] for r in _res_rows())
    assert res_ids == sorted(ids)


# ---- 17. template_variant_uncertainty PRESENT preserved ----
def test_17_uncertainty_present():
    s = _sum()
    assert s["shared_template_variant_uncertainty"] == "PRESENT"
    assert s["residual_spatial_limitation"] == LIM
    assert s["evidence_type"] == EVTYPE
    assert "NO authoritative nonlinear Sym->Asym registration is claimed" in \
        s["not_after_authoritative_registration"]
    for r in _res_rows():
        assert r["template_variant_uncertainty"] == "PRESENT"


# ---- 18. V1/V2/V3 contracts unchanged ----
def test_18_contracts_unchanged():
    assert _git_clean(V1, V2, V3)


# ---- 19. G1 geometry manifests unchanged (incl. spatial bridge / retraction) ----
def test_19_geometry_manifests_unchanged():
    for name in ("phase17_v3_thalamus_g1_julich_geometry_manifest.json",
                 "phase17_v3_thalamus_spatial_bridge_manifest.json",
                 "phase17_v3_thalamus_g1_native_geometry_manifest.json",
                 "phase17_v3_thalamus_transform_retraction.json"):
        assert _git_clean(D16 / name), name


# ---- 20. classification byte-identical ----
def test_20_classification_byte_identical():
    assert _git_clean(CLASS)
    rows = list(csv.DictReader(open(CLASS, encoding="utf-8-sig")))
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert sum(c.values()) - c["VERIFIED_DIRECT_CONTAINED"] == 132
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93
    assert _sum()["classification_proposal"]["global_86_132_93"] == "UNCHANGED"


# ---- 21. DB zero-write ----
def test_21_db_zero_write():
    assert _prov()["db_write"] is False
    assert _sum()["db_zero_write"] == "TRUE"
    txt = MD.read_text(encoding="utf-8")
    assert "No DB write" in txt


# ---- 22. Promotion not auto-executed ----
def test_22_promotion_not_auto():
    assert _sum()["promotion"] == "BLOCKED"
    assert _sum()["lifecycle_or_classification_changed"] is False
    assert _prov()["promotion"] is False
    txt = MD.read_text(encoding="utf-8")
    assert "Promotion = BLOCKED" in txt


# ---- 23. provenance chain complete ----
def test_23_provenance_chain_complete():
    p = _prov()
    assert p["evidence_type"] == EVTYPE
    assert p["v3_scope_contract"]["sha256"] == V3_SHA
    assert p["spatial_bridge"]["spatial_bridge_id"] == SPB_ID
    assert p["spatial_bridge"]["manifest_sha256"]
    assert p["julich_target_reference"]["sha256"]
    assert p["g1_left"]["sha256"] == G1_LEFT_SHA and p["g1_right"]["sha256"] == G1_RIGHT_SHA
    assert p["frozen_universe"]["manifest_sha256"]
    assert p["frozen_universe"]["rollup_csv_sha256"]
    assert p["brainnetome_geometry_route"]["batch_transform_manifest_sha256"]
    assert p["reticular_qc_source"]["sha256"] == "640377ae93cf0782365a698573970c2a429a775c6f64dcf9ac02536156b51f22"
    assert p["classification_independent"] is True
    assert p["script_version"].startswith("phase17_v3_validate_thalamus_bn_direct_spatial.py")


# ---- additional structural checks ----
def test_overall_status_and_gate_consistent():
    s = _sum()
    assert s["bn_g3_to_g1_direct_spatial_validation"] == "PARTIALLY_PASSED"
    assert s["postconstruction_gate"] == "OPEN_NOT_CLOSED"
    assert s["evidence_grades"]["direct_spatial_conflict"] == 1
    assert s["evidence_grades"]["total"] == 16
    assert sum(s["evidence_grades"][k] for k in
               ("directly_supported",
                "directly_supported_with_boundary_uncertainty",
                "direct_spatial_conflict", "direct_evidence_insufficient")) == 16
    # left/right distribution rows exist
    for hemi in ("left", "right"):
        assert s["left_right_distribution"][hemi]["total"] == 8


def test_final_freeze_deferred_in_direct_validation_summary():
    # the direct-validation round itself did NOT form the freeze; it recorded the
    # deferred state in its summary. The freeze file is authored later by the
    # dedicated freeze round (phase17_v3_thalamus_final_freeze_v1.json).
    s = _sum()
    ff = s["final_freeze"]
    assert ff["freeze_id"] == "THALAMUS_PHASE17_FINAL_FREEZE_V1"
    assert ff["freeze_formed"] is False
    assert "deferred" in ff["not_formed_reason"]
    # relation counts recorded for the (deferred) freeze state
    assert ff["relation_counts"]["total"] == 16
    assert ff["promotion_readiness"] == "BLOCKED"
    assert FREEZE.exists()  # formed by the later freeze round


def test_required_results_columns_present():
    need = {"decision_id", "g3_region_id", "official_code", "hemisphere",
            "g1_region_id", "g1_geometry_id", "parcel_support_voxels",
            "parcel_volume_mm3", "weighted_containment",
            "probability_mass_inside_parcel", "fraction_at_p_gt_0_1",
            "fraction_at_p_gt_0_25", "fraction_at_p_gt_0_5",
            "fraction_at_p_gt_0_75", "parcel_centroid_x",
            "parcel_centroid_y", "parcel_centroid_z",
            "g1_weighted_centroid_distance_mm", "contralateral_fraction",
            "outside_support_fraction", "boundary_fraction", "evidence_grade",
            "template_variant_uncertainty", "circularity_risk"}
    cols = set(_res_rows()[0].keys())
    missing = need - cols
    assert not missing, missing


def test_decision_columns_complete():
    need = {"decision_id", "rollup_decision_id", "g3_region_id", "official_code",
            "bn_parcel_sha256", "frozen_g1_target", "g1_geometry_id", "g1_sha256",
            "evidence_grade", "mapping_verdict", "lsg_dependency_resolved",
            "circularity_risk", "classification_independent"}
    cols = set(_dec_rows()[0].keys())
    assert not (need - cols)


def test_grades_match_mapping_verdicts():
    for d in _dec_rows():
        if d["evidence_grade"] == "DIRECTLY_SUPPORTED":
            assert d["mapping_verdict"] == "KEEP_FROZEN_MAPPING_DIRECTLY_SUPPORTED"
        elif d["evidence_grade"] == "DIRECTLY_SUPPORTED_WITH_BOUNDARY_UNCERTAINTY":
            assert d["mapping_verdict"] == "KEEP_FROZEN_MAPPING_WITH_SPATIAL_UNCERTAINTY"
        else:
            assert d["mapping_verdict"] == "FROZEN_MAPPING_REQUIRES_REVIEW"
        assert d["mapping_verdict"] in ALLOWED_VERDICTS


def test_reticular_source_channel_is_excluded_reference():
    qc = _sum()["reticular_exclusion_qc"]
    assert "EXCLUDED" in qc["territory_source"] or "excluded" in qc["territory_source"]
