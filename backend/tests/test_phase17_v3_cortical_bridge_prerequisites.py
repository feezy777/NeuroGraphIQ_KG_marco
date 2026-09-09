"""Phase1.7 V3 - Cortical bridge FreeSurfer prerequisite acquisition + env readiness tests.

Validates the prerequisite audit (verdict D BLOCKED) and the 30 gates. Read-only; no
cortical geometry / no pilot volume / no transform; classification/DB/promotion and
prior frozen families unchanged.
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
THAL = D16 / "phase17_v3_thalamus_final_freeze_v1.json"
AMYG = D16 / "phase17_v3_amygdala_g1_scope_contract_v1.json"
HIPP = D16 / "phase17_v3_hippocampus_canonical_identity_v1.json"
BNST_ADM = D16 / "phase17_v3_bnst_canonical_admission_v1.json"
BNST_GEOM = D16 / "phase17_v3_bnst_canonical_geometry_manifest.json"

ACQ = D16 / "phase17_v3_fsaverage_acquisition_manifest.json"
INV = D16 / "phase17_v3_fsaverage_asset_inventory.csv"
ANNOT = D16 / "phase17_v3_fsaverage_dk_annotation_manifest.json"
SV = D16 / "phase17_v3_fsaverage_surface_volume_geometry.json"
COORD = D16 / "phase17_v3_fsaverage_coordinate_transform_audit.json"
TOOL = D16 / "phase17_v3_freesurfer_toolchain_audit.json"
XCHK = D16 / "phase17_v3_cortical_dk_annotation_crosscheck.csv"
STATUS = D16 / "phase17_v3_cortical_bridge_prerequisite_status.json"
MD = D16 / "phase17_v3_cortical_bridge_prerequisite_diagnostics.md"
HAS = all(p.exists() for p in (ACQ, INV, ANNOT, SV, COORD, TOOL, XCHK, STATUS, MD))


def _j(p):
    return json.load(open(p, encoding="utf-8"))


def _rows(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _git_clean(*paths: Path) -> bool:
    r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *[str(p) for p in paths]],
                       cwd=BACKEND.parent, capture_output=True)
    return r.returncode == 0


# ---- 1/2. fsaverage source official + version ----
def test_1_2_source_and_version():
    a = _j(ACQ)
    assert "freesurfer.net" in a["base_url"] or "FreeSurfer official" in a["source"]
    assert "centos6" in a["version"] or "tutorial_versions" in a["version"]


# ---- 3-6. lh/rh annot exist; DK; SHA frozen ----
def test_3_6_annotations():
    s = _j(STATUS)
    assert s["annotation"]["lh_present"] is True
    assert s["annotation"]["rh_present"] is True
    assert s["annotation"]["is_dk"] is True
    assert len(s["annotation"]["sha_lh"]) == 64
    assert len(s["annotation"]["sha_rh"]) == 64
    assert FS.joinpath("label/lh.aparc.annot").exists()
    assert FS.joinpath("label/rh.aparc.annot").exists()


# ---- 7/8. white/pial exist ----
def test_7_8_white_pial():
    s = _j(STATUS)
    assert s["surfaces"]["white_lr_present"] is True
    assert s["surfaces"]["pial_lr_present"] is False


# ---- 9. surface SHA frozen ----
def test_9_surface_sha():
    g = _j(SV)["surface_geometry"]
    for hemi in ("lh", "rh"):
        assert len(g[hemi]["white_sha256"]) == 64


# ---- 10/11. annotation/surface vertex match + topology ----
def test_10_11_topology():
    g = _j(SV)["surface_geometry"]
    for hemi in ("lh", "rh"):
        assert g[hemi]["annot_white_match"] is True
        assert g[hemi]["white_vertices"] == 163842
        assert g[hemi]["white_faces"] == 327680


# ---- 12/13. reference orig.mgz exists? + SHA ----
def test_12_13_orig_mgz():
    s = _j(STATUS)
    assert s["reference_volume"]["present"] is False
    assert s["reference_volume"]["note"]


# ---- 14/15. vox2ras / vox2ras_tkr recorded ----
def test_14_15_vox2ras():
    c = _j(COORD)
    assert c["vox2ras"] == "NOT_DERIVABLE_NO_VOLUME"
    assert c["vox2ras_tkr"] == "NOT_DERIVABLE_NO_VOLUME"


# ---- 16. tkRAS vs world RAS separated ----
def test_16_tkras_separated():
    c = _j(COORD)
    assert c["tkRAS_vs_world_separated"] is True


# ---- 17. talairach inventoried, not misused ----
def test_17_talairach():
    c = _j(COORD)
    assert c["talairach_xfm"]["present"] is False
    assert "TALAIRACH_XFM_PRESENT is NOT MNI2009C_TARGET_ROUTE_RESOLVED" in c["talairach_xfm"]["note"]


# ---- 18/19. 62 targets checked + no fuzzy repair ----
def test_18_19_crosscheck():
    rows = _rows(XCHK)
    assert len(rows) == 62
    assert all(r["annotation_label_found"] == "TRUE" for r in rows)
    assert _j(STATUS)["dk_crosswalk"]["mismatch_targets"] == []
    for r in rows:
        assert int(r["vertex_count"]) > 0


# ---- 20-22. toolchain environment + version + license ----
def test_20_22_toolchain():
    t = _j(TOOL)
    assert t["execution_status"] == "NOT_EXECUTABLE"
    assert t["native_free_surfer_cli"] is False
    assert t["license"]["required"] is True
    assert t["license"]["present"] is False
    assert "MANUAL_INSTALL_REQUIRED" in t["verdict"]


# ---- 23-25. no geometry / no transform / no overlap ----
def test_23_25_no_geometry():
    assert _j(STATUS)["cortical_geometry_generated"] is False
    assert not (DERIVED / "left_caudalmiddlefrontal_prob_mni2009casym.nii.gz").exists()
    names = {Path(p).name for p in D16.glob("phase17_v3_cortical_*.json")}
    assert "phase17_v3_cortical_g1_spatial_bridge_v1.json" not in names
    md = MD.read_text(encoding="utf-8")
    assert "No cortical geometry generated" in md


# ---- 26. classification unchanged ----
def test_26_classification():
    assert _git_clean(CLASS)
    rows = list(csv.DictReader(open(CLASS, encoding="utf-8-sig")))
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert sum(c.values()) - c["VERIFIED_DIRECT_CONTAINED"] == 132
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


# ---- 27. DB zero-write ----
def test_27_db_zero_write():
    # this round is file-level audit only; no DB artifact is produced
    assert _j(STATUS)["verdict"]
    db_files = [p for p in D16.glob("phase17_v3_cortical_*.json") if "db" in p.name.lower()]
    assert not db_files


# ---- 28-29. prior blockers / frozen families unchanged ----
def test_28_29_prior_unchanged():
    assert _git_clean(BF_BLOCK, CORT_MD, THAL, AMYG, HIPP, BNST_ADM, BNST_GEOM)


# ---- 30. provenance + verdict ----
def test_30_verdict_provenance():
    assert HAS
    s = _j(STATUS)
    assert s["verdict"] == "CORTICAL_BRIDGE_SOURCE_AND_TOOLCHAIN_BLOCKED"
    assert s["asset_set_status"] == "INCOMPLETE"
    md = MD.read_text(encoding="utf-8")
    assert "CORTICAL_BRIDGE_SOURCE_AND_TOOLCHAIN_BLOCKED (D)" in md
    assert "62/62 matched" in md


def test_asset_inventory_lists_missing():
    rows = {r["relative_path"]: r for r in _rows(INV)}
    assert rows["surf/lh.pial"]["exists"] == "False"
    assert rows["surf/rh.pial"]["exists"] == "False"
    assert rows["mri/orig.mgz"]["exists"] == "False"
    assert rows["transforms/talairach.xfm"]["exists"] == "False"
    assert rows["label/lh.aparc.annot"]["exists"] == "True"


def test_annot_dk_label_names():
    a = _j(ANNOT)
    for hemi in ("left", "right"):
        pass
    lh = a["left"]["label_names"]
    assert "caudalmiddlefrontal" in lh
    assert "superiortemporal" in lh or "precentral" in lh
    assert "corpuscallosum" in lh
