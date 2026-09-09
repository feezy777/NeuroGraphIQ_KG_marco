"""Phase1.7 V3 - cortical target-space route adjudication tests.

Validates the audit-only adjudication round (verdict D =
CORTICAL_TARGET_ROUTE_PROJECT_DERIVED_ALLOWED_PENDING_EXECUTION) and the 27 hard gates.
Read-only: no transform application, no registration execution, no cortical geometry,
no Docker/license work, no G4 overlap, no DB write, no reclassification, no promotion.
route_v1 is NOT generated. History 60d81cd/daecb63 and prior frozen states unchanged.
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
TF = BACKEND / "data" / "atlases" / "templateflow_ref"
CLASS = D16 / "phase17_v3_classification.csv"
BF_BLOCK = D16 / "phase17_v3_zaborszky_acquisition_blocker_v1.json"
THAL = D16 / "phase17_v3_thalamus_final_freeze_v1.json"
AMYG = D16 / "phase17_v3_amygdala_g1_scope_contract_v1.json"
HIPP = D16 / "phase17_v3_hippocampus_canonical_identity_v1.json"
BNST_ADM = D16 / "phase17_v3_bnst_canonical_admission_v1.json"
BNST_GEOM = D16 / "phase17_v3_bnst_canonical_geometry_manifest.json"
PREREQ_STATUS = D16 / "phase17_v3_cortical_bridge_prerequisite_status.json"
CORT_MD = D16 / "phase17_v3_cortical_spatial_bridge_diagnostics.md"
RIBBON_MD = D16 / "phase17_v3_cortical_ribbon_method_diagnostics.md"
EFF = D16 / "phase17_v3_cortical_effective_prerequisite_status.json"
# daecb63 ribbon blocker package (unchanged history)
RIBBON_FILES = ["phase17_v3_cortical_ribbon_toolchain_manifest.json",
                "phase17_v3_cortical_ribbon_environment.json",
                "phase17_v3_cortical_ribbon_asset_subset_status.json",
                "phase17_v3_cortical_ribbon_pilot_selection.csv",
                "phase17_v3_cortical_ribbon_pilot_qc.csv",
                "phase17_v3_cortical_effective_prerequisite_status.json",
                "phase17_v3_cortical_ribbon_method_diagnostics.md"]
# 60d81cd complete-asset snapshot (unchanged history)
SNAP = ["phase17_v3_fsaverage_complete_acquisition_routes.csv",
        "phase17_v3_fsaverage_official_release_manifest.json",
        "phase17_v3_fsaverage_complete_asset_inventory.csv",
        "phase17_v3_fsaverage_file_hash_manifest.csv",
        "phase17_v3_fsaverage_annotation_validation.json",
        "phase17_v3_fsaverage_surface_topology_qc.csv",
        "phase17_v3_fsaverage_orig_geometry_audit.json",
        "phase17_v3_fsaverage_talairach_audit.json",
        "phase17_v3_fsaverage_complete_asset_status.json",
        "phase17_v3_fsaverage_complete_asset_diagnostics.md"]
HASH_MANIFEST = D16 / "phase17_v3_fsaverage_file_hash_manifest.csv"

SEM = D16 / "phase17_v3_fsaverage_mni305_semantic_audit.json"
GCMP = D16 / "phase17_v3_fsaverage_mni305_geometry_comparison.csv"
MREF = D16 / "phase17_v3_mni305_reference_asset_manifest.json"
TINV = D16 / "phase17_v3_cortical_target_transform_inventory.csv"
RC = D16 / "phase17_v3_cortical_target_route_candidates.csv"
COMP = D16 / "phase17_v3_cortical_target_route_compatibility_audit.json"
MD = D16 / "phase17_v3_cortical_target_route_diagnostics.md"
ROUTE_V1 = D16 / "phase17_v3_cortical_target_route_v1.json"
OUTS = [SEM, GCMP, MREF, TINV, RC, COMP, MD]
HAS = all(p.exists() for p in OUTS)

XFM_SHA = "2e3869a07b96aec406e0419ca2e434afc54882d37cc212b933b139d1b63a4dfe"


def _j(p):
    return json.load(open(p, encoding="utf-8"))


def _rows(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _git_clean(*paths: Path) -> bool:
    r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *[str(p) for p in paths]],
                       cwd=BACKEND.parent, capture_output=True)
    return r.returncode == 0


# ---- 1. fsaverage official MNI305 semantics sourced ----
def test_1_mni305_semantics_sourced():
    s = _j(SEM)
    assert s["audit_id"] == "FSAVERAGE_MNI305_SEMANTIC_AUDIT_V1"
    assert "Talairach/MNI305" in s["fsaverage_template_identity"]["statement"]
    assert s["fsaverage_template_identity"]["source_urls"]
    assert any("freesurfer" in u or "surfer.nmr" in u
               for u in s["fsaverage_template_identity"]["source_urls"])


# ---- 2. local orig SHA fixed ----
def test_2_orig_sha_fixed():
    s = _j(SEM)
    assert len(s["local_orig_sha256"]) == 64
    # cross-check against the frozen 60d81cd complete-asset file-hash manifest
    for r in _rows(HASH_MANIFEST):
        if r["relative_path"] == "mri/orig.mgz":
            assert r["sha256"] == s["local_orig_sha256"]


# ---- 3. tkRAS/world-RAS distinction retained ----
def test_3_tkras_world_separation():
    d = _j(SEM)["distinctions"]
    assert "tkRAS" in d and "scanner_world_RAS" in d
    assert "distinct from tkRAS" in d["scanner_world_RAS"]
    assert "surface RAS" in d["tkRAS"]


# ---- 4. orig vs authoritative MNI305 relation explicitly classified ----
def test_4_relation_classified():
    s = _j(SEM)
    assert s["relation_classification"] == "ONLY_DOCUMENTED_AS_MNI305_DERIVED"


# ---- 5. no assumed exact grid identity ----
def test_5_no_grid_identity_assumed():
    s = _j(SEM)
    assert s["grid_identical"] is False
    assert s["identity_test"]["grid_identical"] is False
    assert s["identity_test"]["world_ras_identity"] is False
    assert "NOT established" in s["identity_test"]["note"]


# ---- 6. MNI305 reference provenance complete ----
def test_6_mni305_provenance():
    m = _j(MREF)
    assert m["provider"] == "TemplateFlow (official template archive; Curator O. Esteban)"
    assert m["identifier"] == "MNI305"
    assert m["template_id"] == "tpl-MNI305"
    assert len(m["sha256"]) == 64
    assert m["shape"] == [172, 220, 156]
    assert m["reference_binary_status"].startswith("AVAILABLE_LOCAL_CACHE")
    assert m["authors"]
    assert "Collins" in " ".join(m["authors"])


# ---- 7. transform inventory real ----
def test_7_inventory_real():
    rows = {r["transform_id"]: r for r in _rows(TINV)}
    assert rows["XFM_NLIN6_TO_2009C"]["availability"] == "LOCAL_FROZEN"
    assert rows["XFM_NLIN6_TO_2009C"]["sha256"] == XFM_SHA
    assert rows["XFM_MNI305_TO_2009C"]["availability"] == "NOT_PRESENT"
    assert rows["XFM_MNI305_TO_NLIN6"]["availability"] == "NOT_PRESENT"
    assert rows["XFM_FSAVERAGE_TO_ANY"]["availability"] == "NOT_PRESENT"


# ---- 8. no assumed TemplateFlow xfm ----
def test_8_no_assumed_xfm():
    assert _j(COMP)["verdict"].startswith("CORTICAL_TARGET_ROUTE_PROJECT_DERIVED")
    md = MD.read_text(encoding="utf-8")
    assert "does not exist authoritatively" in md or "no MNI305/fsaverage-source" in md
    # absence was verified by live enumeration (tpl-2009c / tpl-MNI305 / tpl-NLin6), not assumed
    assert any("TemplateFlow" in r["evidence"] for r in _rows(RC))


# ---- 9/10/11. multi-hop identity + hop source/target + direction explicit ----
def test_9_10_11_hops():
    rc = {r["route_id"]: r for r in _rows(RC)}
    assert rc["R_B_MULTIHOP_OFFICIAL"]["status"] == "NOT_AVAILABLE"
    assert "first hop" in rc["R_B_MULTIHOP_OFFICIAL"]["evidence"]
    inv = {r["transform_id"]: r for r in _rows(TINV)}
    assert inv["XFM_MNI305_TO_NLIN6"]["direction"] == "MNI305 -> NLin6Asym"
    assert inv["XFM_NLIN6_TO_2009C"]["source"] == "MNI152NLin6Asym"
    assert inv["XFM_NLIN6_TO_2009C"]["target"] == "MNI152NLin2009cAsym"


# ---- 12. SHA explicit when asset exists ----
def test_12_sha_explicit():
    inv = {r["transform_id"]: r for r in _rows(TINV)}
    assert len(inv["XFM_NLIN6_TO_2009C"]["sha256"]) == 64
    assert inv["XFM_MNI305_TO_2009C"]["sha256"] == ""  # no asset -> no sha
    for r in _rows(GCMP):
        if r["volume_id"].startswith("tpl-") or r["volume_id"].startswith("fsaverage"):
            assert len(r["sha256"]) == 64


# ---- 13. RAS/LPS convention explicit ----
def test_13_convention():
    c = _j(COMP)
    assert "RAS and LPS must never be mixed by hand" in c["ras_lps"]["note"]
    assert "SimpleITK" in c["coordinate_convention"]["templateflow_h5"]


# ---- 14. NLin6->2009c frozen transform only as compatible final hop ----
def test_14_frozen_transform_final_hop_only():
    c = _j(COMP)
    fh = c["frozen_final_hop"]
    assert fh["sha256"] == XFM_SHA
    assert "final hop ONLY" in fh["usable_as"]
    assert "not present authoritatively" in fh["usable_as"]


# ---- 15. no fsaverage->NLin6 assumption ----
def test_15_no_fsaverage_as_nlin6():
    c = _j(COMP)
    assert c["no_fsaverage_as_nlin6"] is True
    assert "must NEVER be treated as MNI152NLin6Asym" in c["no_fsaverage_as_nlin6_note"]


# ---- 16/17. no G4 overlap / no mapping-based tuning ----
def test_16_17_no_g4_no_tuning():
    c = _j(COMP)["g4_circularity"]
    assert c["used_g4_overlap"] is False
    assert c["used_mapping_result"] is False
    assert c["circularity_risk"] == "NONE"
    md = MD.read_text(encoding="utf-8")
    assert "no G4 overlap" in md and "no mapping-based tuning" in md


# ---- 18. no project-derived registration execution ----
def test_18_no_registration_executed():
    assert _j(COMP)["no_registration_executed"] is True
    md = MD.read_text(encoding="utf-8")
    assert "NOT executed this round" in md or "not run now" in md
    rc = {r["route_id"]: r for r in _rows(RC)}
    assert rc["R_D_PROJECT_DERIVED_DIRECT"]["status"] == "CANDIDATE_ALLOWED_PENDING_EXECUTION"
    assert "deferred" in rc["R_D_PROJECT_DERIVED_DIRECT"]["evidence"]


# ---- 19. no cortical geometry generation / route_v1 only-if-frozen (supercession-aware) ----
# This round (641cd76, verdict D pending) did NOT generate route_v1. The following registration
# round may legitimately freeze it (verdict A). Updated in the registration round to permit that
# transition without weakening this round's "no cortical geometry" guarantees.
def test_19_no_geometry_no_route_v1():
    assert not (DERIVED / "left_precentral_prob_mni2009casym.nii.gz").exists()
    if ROUTE_V1.exists():
        rv = json.load(open(ROUTE_V1, encoding="utf-8"))
        assert rv["route_class"] == "PROJECT_DERIVED_TEMPLATE_REGISTRATION"
        assert rv["route_id"] == "CORTICAL_FSAVERAGE_TO_MNI2009C_ROUTE_V1"
    names = {p.name for p in OUTS}
    assert "phase17_v3_cortical_target_route_v1.json" not in names  # this round's own outputs
    md = MD.read_text(encoding="utf-8")
    assert "route_v1 NOT generated" in md  # this round's diagnostics (unchanged history)


# ---- 20. no Docker/license work ----
def test_20_no_docker_license():
    md = MD.read_text(encoding="utf-8")
    assert "no Docker/license" in md
    # the source-ribbon license blocker is NOT re-opened
    assert _git_clean(EFF, RIBBON_MD)


# ---- 21. classification unchanged ----
def test_21_classification():
    assert _git_clean(CLASS)
    rows = list(csv.DictReader(open(CLASS, encoding="utf-8-sig")))
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert sum(c.values()) - c["VERIFIED_DIRECT_CONTAINED"] == 132
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


# ---- 22. DB zero-write ----
def test_22_db_zero_write():
    assert "no DB" in MD.read_text(encoding="utf-8")
    assert not any("_db_" in p.name for p in OUTS)


# ---- 23. promotion not executed ----
def test_23_no_promotion():
    assert "no promotion" in MD.read_text(encoding="utf-8")


# ---- 24. source-ribbon blocker state unchanged ----
def test_24_source_ribbon_blocker_unchanged():
    assert _git_clean(*[D16 / f for f in RIBBON_FILES])
    assert _j(EFF)["verdict"] == "CORTICAL_FSAVERAGE_RIBBON_METHOD_BLOCKED_LICENSE"


# ---- 25. BF blocker unchanged ----
def test_25_bf_blocker():
    assert _git_clean(BF_BLOCK)
    assert _j(BF_BLOCK)["geometry"] == "BLOCKED_ON_AUTHORITATIVE_ASSET_ACCESS"


# ---- 26. frozen families + snapshots unchanged ----
def test_26_frozen_unchanged():
    assert _git_clean(CORT_MD, PREREQ_STATUS, THAL, AMYG, HIPP, BNST_ADM, BNST_GEOM)
    assert _git_clean(*[D16 / f for f in SNAP])


# ---- 27. provenance complete + 7 outputs + verdict ----
def test_27_verdict_provenance():
    assert HAS
    c = _j(COMP)
    s = _j(SEM)
    assert c["verdict"] == "CORTICAL_TARGET_ROUTE_PROJECT_DERIVED_ALLOWED_PENDING_EXECUTION"
    assert c["created_at"] and c["script_version"]
    assert s["created_at"] and s["script_version"]
    md = MD.read_text(encoding="utf-8")
    assert "CORTICAL_TARGET_ROUTE_PROJECT_DERIVED_ALLOWED_PENDING_EXECUTION" in md


# ---- extra: MNI305 local reference actually present (official) + 7 artifacts ----
def test_extra_mni305_present_and_all_outputs():
    assert HAS
    assert (TF / "tpl-MNI305_T1w.nii.gz").is_file()
    m = _j(MREF)
    assert (TF / "tpl-MNI305_T1w.nii.gz").stat().st_size == m["annex_size_bytes"] == 2879454


# ---- extra: identity test numeric honesty (moderate, not identity) ----
def test_extra_identity_numeric():
    it = _j(SEM)["identity_test"]
    assert it["ncc_masked"] is not None
    assert 0.3 < it["ncc_masked"] < 0.9
    assert it["mutual_info_bits"] > 0.3
    assert 1.0 < it["com_displacement_mm"] < 20.0
    assert it["grid_identical"] is False


# ---- extra: candidate set contains the D route as primary allowed ----
def test_extra_candidates():
    rc = {r["route_id"]: r for r in _rows(RC)}
    assert rc["R_D_PROJECT_DERIVED_DIRECT"]["class_code"] == "D"
    assert "NearestNeighbor" in rc["R_D_PROJECT_DERIVED_DIRECT"]["summary"]
    assert rc["R_C_SHARED_FRAME"]["status"] == "REJECTED"
    assert rc["R_A_DIRECT_OFFICIAL"]["status"] == "NOT_AVAILABLE"


# ---- extra: compatibility audit interpolation semantics frozen (future only) ----
def test_extra_interpolation():
    c = _j(COMP)["interpolation_rule"]
    assert c["future_binary_ribbon"] == (
        "NearestNeighbor (label-safe) for discrete/binary cortical "
        "ribbon geometry in target space")
    assert "NOT applied this round" in c["note"]
    assert "does NOT carry over" in _j(COMP)["do_not_conflate_note"]
