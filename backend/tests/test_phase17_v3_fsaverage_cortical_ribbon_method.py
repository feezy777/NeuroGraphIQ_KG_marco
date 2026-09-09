"""Phase1.7 V3 - fsaverage source-space cortical ribbon method validation tests.

Validates the BLOCKED_LICENSE evidence package (verdict
CORTICAL_FSAVERAGE_RIBBON_METHOD_BLOCKED_LICENSE, stop_code
FREESURFER_LICENSE_MANUAL_ACTION_REQUIRED) and the 29 hard gates. Read-only; no
toolchain execution, no talairach/MNI305/MNI2009c, no G4 overlap, no derived ribbon
volume, no DB write, no reclassification, no promotion. History 60d81cd and prior
frozen families unchanged.
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
FS = BACKEND / "data" / "atlases" / "freesurfer" / "fsaverage"
SUBJECTS_DIR = BACKEND / "data" / "atlases" / "freesurfer"
CLASS = D16 / "phase17_v3_classification.csv"
BF_BLOCK = D16 / "phase17_v3_zaborszky_acquisition_blocker_v1.json"
CORT_MD = D16 / "phase17_v3_cortical_spatial_bridge_diagnostics.md"
THAL = D16 / "phase17_v3_thalamus_final_freeze_v1.json"
AMYG = D16 / "phase17_v3_amygdala_g1_scope_contract_v1.json"
HIPP = D16 / "phase17_v3_hippocampus_canonical_identity_v1.json"
BNST_ADM = D16 / "phase17_v3_bnst_canonical_admission_v1.json"
BNST_GEOM = D16 / "phase17_v3_bnst_canonical_geometry_manifest.json"
PREREQ_STATUS = D16 / "phase17_v3_cortical_bridge_prerequisite_status.json"
PREREQ_MD = D16 / "phase17_v3_cortical_bridge_prerequisite_diagnostics.md"
# 60d81cd complete-asset snapshot (unchanged history)
SNAP = [
    "phase17_v3_fsaverage_complete_acquisition_routes.csv",
    "phase17_v3_fsaverage_official_release_manifest.json",
    "phase17_v3_fsaverage_complete_asset_inventory.csv",
    "phase17_v3_fsaverage_file_hash_manifest.csv",
    "phase17_v3_fsaverage_annotation_validation.json",
    "phase17_v3_fsaverage_surface_topology_qc.csv",
    "phase17_v3_fsaverage_orig_geometry_audit.json",
    "phase17_v3_fsaverage_talairach_audit.json",
    "phase17_v3_fsaverage_complete_asset_status.json",
    "phase17_v3_fsaverage_complete_asset_diagnostics.md",
]

TOOL = D16 / "phase17_v3_cortical_ribbon_toolchain_manifest.json"
ENV = D16 / "phase17_v3_cortical_ribbon_environment.json"
SUBSET = D16 / "phase17_v3_cortical_ribbon_asset_subset_status.json"
SEL = D16 / "phase17_v3_cortical_ribbon_pilot_selection.csv"
QC = D16 / "phase17_v3_cortical_ribbon_pilot_qc.csv"
METHOD_V1 = D16 / "phase17_v3_cortical_ribbon_method_v1.json"
EFF = D16 / "phase17_v3_cortical_effective_prerequisite_status.json"
MD = D16 / "phase17_v3_cortical_ribbon_method_diagnostics.md"
OUTS = [TOOL, ENV, SUBSET, SEL, QC, EFF, MD]
HAS = all(p.exists() for p in OUTS)


def _j(p):
    return json.load(open(p, encoding="utf-8"))


def _rows(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _git_clean(*paths: Path) -> bool:
    r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *[str(p) for p in paths]],
                       cwd=BACKEND.parent, capture_output=True)
    return r.returncode == 0


# ---- 1. history snapshot 60d81cd unchanged ----
def test_1_history_snapshot_unchanged():
    assert _git_clean(*[D16 / f for f in SNAP])


# ---- 2. source-ribbon asset subset COMPLETE ----
def test_2_subset_complete():
    s = _j(SUBSET)
    assert s["ribbon_required_asset_subset_status"] == "COMPLETE"
    assert s["missing"] == []
    assert len(s["required_for_ribbon"]) == 7


# ---- 3. annot/white/pial/orig SHA fixed ----
def test_3_shas_fixed():
    s = _j(SUBSET)
    for rel, info in s["files"].items():
        assert info["exists"] is True, rel
        assert len(info["sha256"]) == 64, rel
        assert info["size_bytes"] > 0, rel


# ---- 4. vertex topology still consistent ----
def test_4_topology():
    g = _j(SUBSET)["source_internal_geometry"]
    assert g["topology_consistent"] is True
    assert g["shape"] == [256, 256, 256]


# ---- 5. vox2ras_tkr available ----
def test_5_vox2ras_tkr():
    g = _j(SUBSET)["source_internal_geometry"]
    assert len(g["vox2ras_tkr"]) == 4
    assert len(g["vox2ras_tkr"][0]) == 4
    assert g["voxel_mm"] == [1.0, 1.0, 1.0]
    assert g["dtype"] == "uint8"
    assert g["vox2ras_eq_vox2ras_tkr"] is True


# ---- 6. tkRAS explicitly used as source anchor ----
def test_6_tkras_anchor():
    e = _j(EFF)
    assert "tkRAS / vox2ras_tkr" in e["source_anchor"]
    g = _j(SUBSET)["source_internal_geometry"]
    # surfaces map into orig FOV (source-internal plausibility, offline)
    for v in g["surface_vertices_in_orig_FOV"].values():
        assert v["in_FOV_fraction"] == 1.0


# ---- 7. talairach not used for source ribbon ----
def test_7_talairach_not_used():
    e = _j(EFF)
    assert e["talairach_xfm"] == "ABSENT"
    assert e["talairach_source_ribbon_dependency"] == "FALSE"
    assert e["talairach_blocker_role"] == "TARGET_ROUTE_RELATED_MISSING_ASSET"
    assert "DOES_NOT_BLOCK" in e["semantics_note"]


# ---- 8. MNI305 not used ----
def test_8_no_mni305():
    md = MD.read_text(encoding="utf-8")
    assert "talairach/MNI305/MNI2009c/TemplateFlow NOT used" in md
    assert "no talairach/MNI used" in _j(SUBSET)["source_internal_geometry"]["note"]


# ---- 9. MNI2009c not used / route unresolved ----
def test_9_no_mni2009c_route():
    e = _j(EFF)
    assert e["target_standard_space_route"] == "STILL_UNRESOLVED"
    md = MD.read_text(encoding="utf-8")
    assert "target-route adjudication" in e["semantics_note"]
    assert "method_v1 (only on a future FROZEN round)" in md


# ---- 10. official FreeSurfer toolchain only ----
def test_10_official_toolchain():
    t = _j(TOOL)
    assert t["official_container_route"]["repository"] == "freesurfer/freesurfer"
    assert t["official_container_route"]["tag"] == "7.4.1"
    assert "official FreeSurfer project on Docker Hub" in t["official_container_route"]["source"]
    assert t["cli_to_verify"] == ["mri_label2vol", "mri_surf2vol", "mri_info"]


# ---- 11. version recorded ----
def test_11_version_recorded():
    t = _j(TOOL)
    assert "7.4.1" in t["free_surfer_version"]["selected"]
    assert "not locally installed" in t["free_surfer_version"]["selected"]


# ---- 12. container digest field recorded (honest NOT_RESOLVED) ----
def test_12_digest_recorded():
    t = _j(TOOL)
    d = t["official_container_route"]["digest"]
    assert d.startswith("NOT_RESOLVED_THIS_SESSION")
    assert t["official_container_route"]["container_os"].startswith("NOT_RESOLVED")


# ---- 13. license not committed / manual action required ----
def test_13_license():
    t = _j(TOOL)
    assert t["license"]["required"] is True
    assert t["license"]["present"] is False
    assert "never committed" in t["license"]["commit_policy"]
    assert t["stop_code"] == "FREESURFER_LICENSE_MANUAL_ACTION_REQUIRED"
    assert t["license"]["obtain_via"].startswith("official FreeSurfer registration")
    e = _j(ENV)
    assert e["license_search"]["any_license_found"] is False


# ---- 14. SUBJECTS_DIR reproducible + fsaverage layout ----
def test_14_subjects_dir():
    t = _j(TOOL)
    policy = t["official_container_route"]["subjects_dir_mount_policy"]
    assert str(SUBJECTS_DIR) in policy and "fsaverage subject" in policy
    assert (SUBJECTS_DIR / "fsaverage" / "label").is_dir()
    assert (SUBJECTS_DIR / "fsaverage" / "surf").is_dir()
    assert (SUBJECTS_DIR / "fsaverage" / "mri" / "orig.mgz").is_file()
    assert (FS / "label/lh.aparc.annot").is_file()


# ---- 15. pilot selection mapping-independent ----
def test_15_mapping_independent():
    for r in _rows(SEL):
        assert r["mapping_independent"] == "TRUE"
        assert r["julich_g4_used"] == "FALSE"
        assert r["viewed_mapping_result"] == "FALSE"


# ---- 16. exactly 3 pilot families <= 3 ----
def test_16_exactly_three():
    rows = _rows(SEL)
    assert len(rows) == 3
    fams = {r["geometric_family"] for r in rows}
    assert fams == {"LARGE_LATERAL", "MEDIAL", "INFERIOR_TEMPORAL"}
    assert all(r["status"] == "SELECTED_DEFERRED_EXECUTION" for r in rows)


# ---- 17. ribbon not surface shell (no volume fabricated) ----
def test_17_no_surface_shell_volume():
    for r in _rows(QC):
        assert r["ribbon_output_voxel_count"] == "NOT_AVAILABLE_LICENSE_BLOCKED"
        assert r["surface_shell_only"] == "NOT_DETERMINED_NO_VOLUME"
        assert "no Python rasterizer substitute" in r["status_reason"]
        assert "official FreeSurfer" in r["status_reason"]


# ---- 18. planned output on orig.mgz grid ----
def test_18_orig_grid_planned():
    e = _j(EFF)
    assert any("orig.mgz grid" in a for a in e["next_actions"])
    md = MD.read_text(encoding="utf-8")
    assert "orig.mgz" in md


# ---- 19. laterality source-native (left parcels x<0) ----
def test_19_laterality():
    for r in _rows(QC):
        assert r["hemisphere"] == "left"
        assert float(r["surface_correct_side_fraction"]) == 1.0
        assert float(r["surface_contralateral_fraction"]) == 0.0


# ---- 20. QC complete (offline real; volume metrics honestly NOT_RUN) ----
def test_20_qc_complete():
    expect = {"LARGE_LATERAL": ("precentral", "NGIQ-BR-00000290", "10740"),
              "MEDIAL": ("posteriorcingulate", "NGIQ-BR-00000289", "3266"),
              "INFERIOR_TEMPORAL": ("fusiform", "NGIQ-BR-00000273", "4714")}
    for r in _rows(QC):
        fam = r["geometric_family"]
        label, gid, vc = expect[fam]
        assert r["dk_label_name"] == label
        assert r["canonical_g1_id"] == gid
        assert r["annotation_vertex_count"] == vc
        assert int(r["parcel_white_vertex_count"]) == int(vc)
        assert r["parcel_surface_centroid_xyz_mm"]
        assert r["ribbon_volume_mm3"] == "NOT_AVAILABLE_LICENSE_BLOCKED"
        assert r["ribbon_connected_components"] == "NOT_AVAILABLE_LICENSE_BLOCKED"
        assert r["ribbon_volume_valid"] == "NOT_DETERMINED"
        assert r["status"] == "NOT_RUN_LICENSE_BLOCKED"


# ---- 21. no G4 overlap QA ----
def test_21_no_g4_overlap():
    md = MD.read_text(encoding="utf-8")
    assert "no G4 overlap" in md
    for r in _rows(SEL):
        assert r["julich_g4_used"] == "FALSE"


# ---- 22. no target transform executed ----
def test_22_no_target_transform():
    e = _j(EFF)
    assert e["target_standard_space_route"] == "STILL_UNRESOLVED"
    assert e["geometry_generated"] is False
    md = MD.read_text(encoding="utf-8")
    assert "NOT used" in md and "MNI" in md


# ---- 23. no bulk 62 geometry / no method_v1 / no derived binary ----
def test_23_no_geometry():
    assert not METHOD_V1.exists()
    assert not (DERIVED / "left_precentral_prob_mni2009casym.nii.gz").exists()
    names = {p.name for p in OUTS}
    assert "phase17_v3_cortical_ribbon_method_v1.json" not in names
    assert _j(EFF)["method_v1_generated"] is False
    md = MD.read_text(encoding="utf-8")
    assert "no bulk 62 geometry" in md


# ---- 24. classification unchanged ----
def test_24_classification():
    assert _git_clean(CLASS)
    rows = list(csv.DictReader(open(CLASS, encoding="utf-8-sig")))
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert sum(c.values()) - c["VERIFIED_DIRECT_CONTAINED"] == 132
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


# ---- 25. DB zero-write ----
def test_25_db_zero_write():
    assert "no DB write" in MD.read_text(encoding="utf-8")
    assert not any("_db_" in p.name for p in OUTS)


# ---- 26. promotion not executed ----
def test_26_no_promotion():
    md = MD.read_text(encoding="utf-8")
    assert "no promotion" in md


# ---- 27. BF blocker unchanged ----
def test_27_bf_blocker():
    assert _git_clean(BF_BLOCK)
    assert _j(BF_BLOCK)["geometry"] == "BLOCKED_ON_AUTHORITATIVE_ASSET_ACCESS"


# ---- 28. prior frozen families + snapshots unchanged ----
def test_28_prior_frozen_unchanged():
    assert _git_clean(CORT_MD, PREREQ_STATUS, PREREQ_MD, THAL, AMYG, HIPP, BNST_ADM, BNST_GEOM)
    assert _git_clean(*[D16 / f for f in SNAP])


# ---- 29. provenance complete + 7 outputs + verdict ----
def test_29_verdict_provenance():
    assert HAS
    e = _j(EFF)
    t = _j(TOOL)
    assert e["verdict"] == "CORTICAL_FSAVERAGE_RIBBON_METHOD_BLOCKED_LICENSE"
    assert t["verdict"] == e["verdict"]
    assert e["status_id"]
    assert e["script_version"]
    assert e["created_at"]
    assert e["pilots_selected"] == 3
    assert e["pilots_executed"] == 0
    assert e["pilot_volume_status"] == "NOT_RUN_LICENSE_BLOCKED"
    assert e["historical_full_asset_set_status"].startswith("INCOMPLETE (60d81cd, unchanged")
    assert e["ribbon_required_asset_subset_status"] == "COMPLETE"
    assert e["source_asset_internal_geometry_status"] == "READY"
    assert e["talairach_target_route_dependency"] == "TO_BE_ADJUDICATED"
    md = MD.read_text(encoding="utf-8")
    assert "CORTICAL_FSAVERAGE_RIBBON_METHOD_BLOCKED_LICENSE" in md
    assert "60d81cd" in md


# ---- extra: CLI executability honestly NOT_VERIFIED (container-started != ready) ----
def test_cli_not_verified():
    t = _j(TOOL)
    assert t["cli_executable_status"] == "NOT_VERIFIED_LICENSE_GATED"
    assert "container-started alone is NOT readiness" in t["note"]
    assert "/opt/freesurfer/bin" in t["note"]


# ---- extra: native/WSL/docker route facts recorded ----
def test_route_facts_recorded():
    e = _j(ENV)
    assert e["native_free_surfer_cli"] is False
    assert e["docker_cli_present"] is True
    assert "Docker version" in e["docker_cli_version"]
    assert "docker-desktop" in e["wsl_distros"]
    t = _j(TOOL)
    assert t["native_windows"]["free_surfer_cli_present"] is False
    assert t["docker"]["cli_present"] is True
    assert "daemon STOPPED" in t["docker"]["note"]


# ---- extra: effective status subsumes the corrected blocker semantics ----
def test_effective_semantics_correct():
    e = _j(EFF)
    assert e["talairach_blocker_role"] == "TARGET_ROUTE_RELATED_MISSING_ASSET"
    assert "NOT a source-ribbon construction blocker" in e["semantics_note"]
    assert e["next_actions"]
