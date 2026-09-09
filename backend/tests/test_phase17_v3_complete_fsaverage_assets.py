"""Phase1.7 V3 - Official FreeSurfer fsaverage complete subject asset acquisition tests.

Validates the complete-asset acquisition audit + provenance freeze (Case B blocker
verdict CORTICAL_FSAVERAGE_COMPLETE_SOURCE_ASSET_BLOCKED). Read-only; no FreeSurfer
toolchain install, no mri_label2vol/mri_surf2vol, no ribbon/pilot volume, no
fsaverage->MNI2009c route resolution, no G4 overlap, no reclassification, no DB write,
no promotion. Classification and prior frozen families unchanged.
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
DK_AUDITS = BACKEND / "data" / "integration" / "g3_surface_dk_audits"
CLASS = D16 / "phase17_v3_classification.csv"
BF_BLOCK = D16 / "phase17_v3_zaborszky_acquisition_blocker_v1.json"
CORT_MD = D16 / "phase17_v3_cortical_spatial_bridge_diagnostics.md"
PREREQ_STATUS = D16 / "phase17_v3_cortical_bridge_prerequisite_status.json"
PREREQ_MD = D16 / "phase17_v3_cortical_bridge_prerequisite_diagnostics.md"
THAL = D16 / "phase17_v3_thalamus_final_freeze_v1.json"
AMYG = D16 / "phase17_v3_amygdala_g1_scope_contract_v1.json"
HIPP = D16 / "phase17_v3_hippocampus_canonical_identity_v1.json"
BNST_ADM = D16 / "phase17_v3_bnst_canonical_admission_v1.json"
BNST_GEOM = D16 / "phase17_v3_bnst_canonical_geometry_manifest.json"

ROUTES = D16 / "phase17_v3_fsaverage_complete_acquisition_routes.csv"
REL = D16 / "phase17_v3_fsaverage_official_release_manifest.json"
INV = D16 / "phase17_v3_fsaverage_complete_asset_inventory.csv"
HASH = D16 / "phase17_v3_fsaverage_file_hash_manifest.csv"
ANNOT = D16 / "phase17_v3_fsaverage_annotation_validation.json"
TOP = D16 / "phase17_v3_fsaverage_surface_topology_qc.csv"
ORIG = D16 / "phase17_v3_fsaverage_orig_geometry_audit.json"
TALA = D16 / "phase17_v3_fsaverage_talairach_audit.json"
STATUS = D16 / "phase17_v3_fsaverage_complete_asset_status.json"
MD = D16 / "phase17_v3_fsaverage_complete_asset_diagnostics.md"
HAS = all(p.exists() for p in (ROUTES, REL, INV, HASH, ANNOT, TOP, ORIG, TALA, STATUS, MD))

REQUIRED_PRESENT = ["label/lh.aparc.annot", "label/rh.aparc.annot", "surf/lh.white",
                    "surf/rh.white", "surf/lh.pial", "surf/rh.pial", "mri/orig.mgz"]


def _j(p):
    return json.load(open(p, encoding="utf-8"))


def _rows(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _git_clean(*paths: Path) -> bool:
    r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *[str(p) for p in paths]],
                       cwd=BACKEND.parent, capture_output=True)
    return r.returncode == 0


# ---- 1. official source / same official distribution ----
def test_1_official_source_same_release():
    a = _j(REL)
    assert "freesurfer.net" in a["base_url"]
    assert "tutorial_versions_centos6" in a["distribution"]
    assert a["same_release_asset_set"] is True


# ---- 2. release identity honestly recorded (not fabricated) ----
def test_2_release_identity_partial():
    a = _j(REL)
    assert a["release_identity"] == "PARTIALLY_RESOLVED"
    assert a["route"] == "R1"
    assert "NOT fabricated" in a["release_note"]


# ---- 3. lh/rh DK annotations present on disk ----
def test_3_annotations_present():
    assert FS.joinpath("label/lh.aparc.annot").exists()
    assert FS.joinpath("label/rh.aparc.annot").exists()
    assert FS.joinpath("label/lh.aparc.annot").stat().st_size > 0


# ---- 4. white + pial present L/R + orig.mgz present ----
def test_4_surfaces_and_volume_present():
    for rel in REQUIRED_PRESENT:
        assert FS.joinpath(rel).exists(), rel


# ---- 5. talairach.xfm genuinely absent ----
def test_5_talairach_absent():
    assert not FS.joinpath("transforms/talairach.xfm").exists()


# ---- 6. hash manifest: present files have 64-hex SHA + positive size ----
def test_6_hash_manifest():
    rows = {r["relative_path"]: r for r in _rows(HASH)}
    for rel in REQUIRED_PRESENT:
        assert rows[rel]["sha256"], rel
        assert len(rows[rel]["sha256"]) == 64
        assert int(rows[rel]["size_bytes"]) > 0
    # talairach hash blank in manifest (not present)
    assert rows["transforms/talairach.xfm"]["sha256"] == ""


# ---- 7. inventory agrees with disk (present True / talairach False) ----
def test_7_inventory_agrees():
    rows = {r["relative_path"]: r for r in _rows(INV)}
    for rel in REQUIRED_PRESENT:
        assert rows[rel]["exists"] == "True", rel
    assert rows["transforms/talairach.xfm"]["exists"] == "False"
    # inventory supersets the required set (sphere + brain/aseg/aparc+aseg audited)
    assert rows["surf/lh.sphere"]["exists"] == "True"


# ---- 8. surface topology: annot==white==pial vertex counts ----
def test_8_topology_annot_white_pial():
    rows = {r["hemisphere"]: r for r in _rows(TOP)}
    for hemi in ("lh", "rh"):
        assert rows[hemi]["annot_vertices"] == "163842"
        assert rows[hemi]["white_vertices"] == "163842"
        assert rows[hemi]["pial_vertices"] == "163842"
        assert rows[hemi]["topology_equal"] == "True"


# ---- 9. face counts 327680 ----
def test_9_topology_faces():
    rows = {r["hemisphere"]: r for r in _rows(TOP)}
    for hemi in ("lh", "rh"):
        assert rows[hemi]["white_faces"] == "327680"
        assert rows[hemi]["pial_faces"] == "327680"


# ---- 10. orig.mgz geometry: 256^3 @ 1mm uint8 ----
def test_10_orig_shape_space_dtype():
    o = _j(ORIG)
    assert o["shape"] == [256, 256, 256]
    assert o["voxel_size_mm"] == [1.0, 1.0, 1.0]
    assert o["dtype"] == "uint8"


# ---- 11. orig.mgz SHA + present ----
def test_11_orig_sha():
    o = _j(ORIG)
    assert o["present"] is True
    assert len(o["sha256"]) == 64


# ---- 12. vox2ras == vox2ras_tkr (fsaverage internal tkRAS-aligned) ----
def test_12_vox2ras_equality():
    o = _j(ORIG)
    assert len(o["vox2ras"]) == 4 and len(o["vox2ras_tkr"]) == 4
    assert o["vox2ras_eq_vox2ras_tkr"] is True
    # distinct from MNI152 2009c mapping note recorded
    assert "NOT an MNI152" in o["note"]


# ---- 13. DK annotation is Desikan-Killiany + SHA ----
def test_13_annotation_dk():
    a = _j(ANNOT)
    assert a["parcellation"] == "Desikan-Killiany aparc"
    assert a["is_dk_all"] is True
    for hemi in ("left", "right"):
        assert a[hemi]["is_dk"] is True
        assert len(a[hemi]["sha256"]) == 64
        assert a[hemi]["vertices"] == 163842


# ---- 14. 62/62 frozen crosswalk targets matched ----
def test_14_crosscheck_62():
    x = _j(ANNOT)["crosscheck"]
    aligned = [r for r in _rows(DK_AUDITS / "dk34_surface_label_to_g1_crosswalk.csv")
               if r["alignment_status"] == "ALIGNED" and r["g1_entity_id"]]
    assert len(aligned) == 62
    assert x["aligned"] == 62
    assert x["matched"] == 62
    assert x["mismatches"] == []


# ---- 15. talairach audit: absent / 404 / not used / not MNI2009c route ----
def test_15_talairach_audit():
    t = _j(TALA)
    assert t["present"] is False
    assert t["sha256"] is None
    assert "404" in t["source_status"]
    assert t["used"] is False
    assert t["not_mni2009c_route"] is True
    assert "MNI152NLin2009cAsym" in t["rule"]


# ---- 16. talairach semantics: license-gated full distribution ----
def test_16_talairach_license_gated():
    t = _j(TALA)
    assert "license/registration" in t["semantics_note"]
    assert "not ship" in t["semantics_note"] or "NOT shipped" in t["semantics_note"]


# ---- 17. verdict + asset_set_status ----
def test_17_verdict_blocked():
    s = _j(STATUS)
    assert s["verdict"] == "CORTICAL_FSAVERAGE_COMPLETE_SOURCE_ASSET_BLOCKED"
    assert s["asset_set_status"] == "INCOMPLETE"


# ---- 18. missing required exactly talairach.xfm ----
def test_18_missing_required():
    s = _j(STATUS)
    assert s["required_missing"] == ["transforms/talairach.xfm"]
    assert all(rel not in s["required_missing"] for rel in REQUIRED_PRESENT)


# ---- 19. status record for topology / crosscheck / internal geometry ----
def test_19_status_records():
    s = _j(STATUS)
    assert s["surface_topology"] == "CONSISTENT"
    assert s["sixty_two_target_crosscheck"] == "PASS"
    assert s["source_internal_geometry"] == "RESOLVED"
    assert s["geometry_generated"] is False


# ---- 20. toolchain still blocked (unchanged, no install) ----
def test_20_toolchain_unchanged():
    s = _j(STATUS)
    assert "BLOCKED" in s["toolchain"]
    assert "MANUAL_INSTALL_REQUIRED" in s["toolchain"] or "FREESURFER_LICENSE_REQUIRED" in s["toolchain"]
    # no toolchain configuration entered (gate hard constraint)
    assert "NOT_ADJUDICATED" in s["target_mni2009c_route"]


# ---- 21. effective prerequisite state still NOT READY ----
def test_21_effective_state():
    s = _j(STATUS)
    assert s["effective_prerequisite_state"].startswith("CORTICAL_BRIDGE_SOURCE_AND_TOOLCHAIN_BLOCKED")
    assert "NOT READY" in s["effective_prerequisite_state"]


# ---- 22. acquisition routes: official open, license route, no unknown mixing ----
def test_22_routes():
    rows = {r["route_id"]: r for r in _rows(ROUTES)}
    assert rows["R1"]["access_state"] == "OPEN"
    assert "freesurfer.net" in rows["R1"]["url"]
    assert rows["R2"]["access_state"] == "MANUAL_AUTHORIZED_ACCESS_REQUIRED"
    assert rows["R3"]["access_state"] == "NOT_USED"
    assert "unknown sources" in rows["R3"]["evidence"].lower()


# ---- 23. no geometry generated on disk ----
def test_23_no_geometry():
    assert not (DERIVED / "left_caudalmiddlefrontal_prob_mni2009casym.nii.gz").exists()
    names = {Path(p).name for p in D16.glob("phase17_v3_cortical_*.json")}
    assert "phase17_v3_cortical_g1_spatial_bridge_v1.json" not in names
    md = MD.read_text(encoding="utf-8")
    assert "No cortical geometry generated" in md
    assert "No CORTICAL_G1_SPATIAL_BRIDGE_V1" in md or "no cortical geometry" in md.lower()


# ---- 24. diagnostics MD documents evidence ----
def test_24_diagnostics():
    md = MD.read_text(encoding="utf-8")
    assert "CORTICAL_FSAVERAGE_COMPLETE_SOURCE_ASSET_BLOCKED" in md
    assert "163842" in md and "327680" in md
    assert "talairach.xfm" in md
    assert "62" in md


# ---- 25. release manifest timestamps / version present ----
def test_25_release_fields():
    a = _j(REL)
    assert a["source"]
    assert a["provider"]
    assert a["acquisition_timestamp"]


# ---- 26. prior prerequisite snapshot unchanged on disk (git clean) ----
def test_26_prior_prereq_unchanged():
    assert _git_clean(PREREQ_STATUS, PREREQ_MD)


# ---- 27. prior frozen families + blockers unchanged ----
def test_27_prior_frozen_unchanged():
    assert _git_clean(BF_BLOCK, CORT_MD, THAL, AMYG, HIPP, BNST_ADM, BNST_GEOM)


# ---- 28. classification frozen (byte-clean + counts) ----
def test_28_classification_frozen():
    assert _git_clean(CLASS)
    rows = list(csv.DictReader(open(CLASS, encoding="utf-8-sig")))
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert sum(c.values()) - c["VERIFIED_DIRECT_CONTAINED"] == 132
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


# ---- 29. DB zero-write ----
def test_29_db_zero_write():
    db_files = [p for p in D16.glob("phase17_v3_fsaverage_complete_*.json")
                if "db" in p.name.lower()]
    assert not db_files


# ---- 30. provenance complete: status_id + script_version + created_at ----
def test_30_provenance():
    s = _j(STATUS)
    assert s["status_id"]
    assert s["script_version"]
    assert s["created_at"]
    assert s["present_required"]
    # supersede note documented (prior partial set superseded, not overwritten)
    assert "prior prerequisite snapshot" in s["note"]


# ---- 31. all 10 artifacts present (no collision with prior prerequisite snapshot) ----
def test_31_all_outputs_present():
    assert HAS
    out10 = [ROUTES, REL, INV, HASH, ANNOT, TOP, ORIG, TALA, STATUS, MD]
    assert all(p.exists() for p in out10)
    # distinct filenames from the earlier prerequisite snapshot (commit 3f42149) -> not overwritten
    prior = {PREREQ_STATUS.name, PREREQ_MD.name,
             "phase17_v3_fsaverage_acquisition_manifest.json",
             "phase17_v3_fsaverage_asset_inventory.csv"}
    assert not ({p.name for p in out10} & prior)


# ---- 32. no promotion executed / no geometry generated ----
def test_32_no_promotion():
    md = MD.read_text(encoding="utf-8").lower()
    assert "no cortical geometry generated" in md
    # toolchain/MNI2009c remain later-round concerns, none executed
    s = _j(STATUS)
    assert s["geometry_generated"] is False


# ---- 33. annot names = real DK cortical labels ----
def test_33_annot_names_dk():
    a = _j(ANNOT)
    lh = a["left"]["names"]
    assert "caudalmiddlefrontal" in lh
    assert "precentral" in lh
    assert "superiortemporal" in lh or "middlefrontal" in lh
    assert a["left"]["label_count"] > 30
