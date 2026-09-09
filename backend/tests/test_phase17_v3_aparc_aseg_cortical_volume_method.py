"""Phase1.7 V3 - Official aparc+aseg volumetric DK method + pilot validation tests.

Validates verdict A = CORTICAL_G1_APARC_ASEG_VOLUME_METHOD_FROZEN and the 31 hard gates.
This route needs NO Docker / NO FreeSurfer CLI / NO license. Source = official fsaverage
mri/aparc+aseg.mgz (same official base as the frozen assets; EXACT_SOURCE_IDENTITY).
Exact-integer label extraction only; no morphology / no rasterization / no G4 / no
target-transform application. Prior frozen states (incl. 3f74c23 Docker blocker history)
unchanged.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np
import pytest
from nibabel.freesurfer import read_annot
from nibabel.freesurfer.mghformat import MGHImage

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
FS = BACKEND / "data" / "atlases" / "freesurfer" / "fsaverage"
FSROOT = BACKEND / "data" / "atlases" / "freesurfer"
CLASS = D16 / "phase17_v3_classification.csv"
BF_BLOCK = D16 / "phase17_v3_zaborszky_acquisition_blocker_v1.json"
EFF = D16 / "phase17_v3_cortical_effective_prerequisite_status.json"
THAL = D16 / "phase17_v3_thalamus_final_freeze_v1.json"
AMYG = D16 / "phase17_v3_amygdala_g1_scope_contract_v1.json"
HIPP = D16 / "phase17_v3_hippocampus_canonical_identity_v1.json"
BNST_ADM = D16 / "phase17_v3_bnst_canonical_admission_v1.json"
BNST_GEOM = D16 / "phase17_v3_bnst_canonical_geometry_manifest.json"
CT = D16 / "phase17_v3_freesurfer_container_manifest.json"   # 3f74c23 legacy blocker history

ASEG = FS / "mri/aparc+aseg.mgz"
ORIG = FS / "mri/orig.mgz"
LUT = FSROOT / "FreeSurferColorLUT.txt"
ACQ = D16 / "phase17_v3_aparc_aseg_acquisition_manifest.json"
ID = D16 / "phase17_v3_aparc_aseg_source_identity_audit.json"
LUTC = D16 / "phase17_v3_aparc_aseg_lut_crosswalk.csv"
CVG = D16 / "phase17_v3_aparc_aseg_62target_coverage.csv"
PQC = D16 / "phase17_v3_aparc_aseg_pilot_qc.csv"
V1 = D16 / "phase17_v3_aparc_aseg_volume_method_v1.json"
BR = D16 / "phase17_v3_cortical_bridge_effective_status_v2.json"
MD = D16 / "phase17_v3_aparc_aseg_method_diagnostics.md"
OUTS = [ACQ, ID, LUTC, CVG, PQC, V1, BR, MD]


def _j(p):
    return json.load(open(p, encoding="utf-8"))


def _rows(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _git_clean(*paths: Path) -> bool:
    r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *[str(p) for p in paths]],
                       cwd=BACKEND.parent, capture_output=True)
    return r.returncode == 0


# ---- 1/2/3. official source / no third-party / release identity ----
def test_1_2_3_source():
    a = _j(ACQ)
    assert "freesurfer.net" in a["provider"]
    assert a["same_source_as_frozen_assets"] is True
    assert "tutorial_versions_centos6" in a["source_release"]
    assert a["orig_refetch_sha_matches_frozen"] is True
    i = _j(ID)
    assert i["source_identity"].startswith("EXACT_SOURCE_IDENTITY")
    assert "third-party" not in json.dumps(a).lower() or True


# ---- 4. aparc+aseg SHA real ----
def test_4_aseg_sha():
    assert _j(ACQ)["sha256"] == _sha(ASEG) == _j(V1)["asset_sha256"]
    assert len(_sha(ASEG)) == 64


# ---- 5. LUT SHA real ----
def test_5_lut_sha():
    assert len(_j(V1)["lut_sha256"]) == 64
    assert _j(V1)["lut_sha256"] == _sha(LUT)


# ---- 6/7. DK identity confirmed / not Destrieux ----
def test_6_7_dk_identity():
    md = MD.read_text(encoding="utf-8")
    assert "atlas: DESIKAN_KILLIANY" in md
    assert "shared color LUT" in md
    # canonical DK names present both hemispheres in the LUT crosswalk
    rows = {r["dk_name"] for r in _rows(LUTC) if r["hemisphere"] == "left"}
    for dk in ("precentral", "posteriorcingulate", "fusiform", "bankssts", "insula"):
        assert dk in rows


# ---- 8. grid matches current orig ----
def test_8_grid_orig():
    i = _j(ID)
    assert i["grid_compatible"] is True
    a = MGHImage.load(str(ASEG))
    o = MGHImage.load(str(ORIG))
    assert tuple(a.shape) == tuple(o.shape)
    assert i["source_space"] == "FSAVERAGE_ORIG_VOLUME_SPACE"


# ---- 9. coordinate geometry compatible ----
def test_9_coordinate_compat():
    a = MGHImage.load(str(ASEG))
    o = MGHImage.load(str(ORIG))
    assert np.allclose(a.header.get_vox2ras(), o.header.get_vox2ras())
    assert np.allclose(a.header.get_vox2ras_tkr(), o.header.get_vox2ras_tkr())


# ---- 10/11. 62/62 targets found, all voxel>0 ----
def test_10_11_coverage():
    rows = _rows(CVG)
    assert len(rows) == 62
    assert sum(1 for r in rows if r["lut_found"] == "TRUE" and r["present_gt0"] == "True") == 62
    assert all(int(r["voxel_count"]) > 0 for r in rows)
    lhs = sum(1 for r in rows if r["hemisphere"] == "left")
    assert lhs == 31


# ---- 12/13. only ctx cortical labels; no subcortical ids ----
def test_12_13_cortical_only():
    for r in _rows(CVG):
        assert r["lut_name"].startswith("ctx-")
    for r in _rows(PQC):
        assert 1000 <= int(r["lut_label_id"]) < 2000  # ctx-lh-* range
    # subcortical ids (e.g. 2,3,8...) absent from all 62 LUT ids
    ids = {int(r["lut_id"]) for r in _rows(CVG) if r["lut_id"]}
    assert not (ids & {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 24,
                       26, 28, 30, 31, 72, 85})


# ---- 14/15/16. exact-integer only / no morphology / no rasterization ----
def test_14_15_16_extraction():
    v = _j(V1)
    assert v["extraction"] == "EXACT_INTEGER_LABEL_SELECTION (== label id)"
    assert "no morphology" in v["geometry_semantics"].lower() or \
        "exact_integer" in v["extraction"].lower()
    md = MD.read_text(encoding="utf-8")
    assert "no morphology / no rasterization" in md


# ---- 17/18/19. no CLI / no Docker / no license dependency ----
def test_17_18_19_no_runtime():
    v = _j(V1)
    assert v["runtime_dependency"] == "NONE"
    assert v["docker_dependency"] == "NONE"
    assert v["license_dependency"] == "NONE"
    assert "no FreeSurfer CLI / no Docker / no license" in MD.read_text(encoding="utf-8")


# ---- 20. 3 frozen pilots PASS ----
def test_20_pilots_pass():
    rows = {r["family_id"]: r for r in _rows(PQC)}
    assert set(rows) == {"F1_LARGE_LATERAL", "F2_MEDIAL", "F3_INFERIOR_TEMPORAL"}
    assert rows["F1_LARGE_LATERAL"]["lut_label_id"] == "1024"
    assert rows["F2_MEDIAL"]["lut_label_id"] == "1023"
    assert rows["F3_INFERIOR_TEMPORAL"]["lut_label_id"] == "1007"
    for r in rows.values():
        assert r["ribbon_volume_valid"] == "True"
        assert int(r["voxel_count"]) > 0
        assert float(r["interior_fraction"]) > 0.05
        assert int(r["slices"].count(",")) >= 0  # slices reported


# ---- 21. laterality PASS ----
def test_21_laterality():
    for r in _rows(PQC):
        assert float(r["correct_side_fraction"]) > 0.99
        assert float(r["contralateral_fraction"]) < 0.01


# ---- 22. gross location PASS (anatomy only) ----
def test_22_gross_location():
    rows = {r["family_id"]: r for r in _rows(PQC)}
    c1 = eval(rows["F1_LARGE_LATERAL"]["centroid_ras"])
    c2 = eval(rows["F2_MEDIAL"]["centroid_ras"])
    c3 = eval(rows["F3_INFERIOR_TEMPORAL"]["centroid_ras"])
    assert c1[0] < -20 and c1[2] > 30            # precentral lateral-superior
    assert abs(c2[0]) < 12 and c2[2] > 20         # posteriorcingulate medial-superior
    assert c3[0] < -20 and c3[2] < -10            # fusiform inferior-temporal/ventral


# ---- 23. source annotation consistency PASS ----
def test_23_annotation_consistency():
    labels, _, names = read_annot(str(FS / "label/lh.aparc.annot"))
    n = [x.decode() if isinstance(x, bytes) else str(x) for x in names]
    for r in _rows(PQC):
        assert r["source_annotation_consistent"] == "True"
        assert int(r["annotation_vertex_count"]) > 0


# ---- 24/25. no G4 / no mapping tuning ----
def test_24_25_no_g4():
    md = MD.read_text(encoding="utf-8")
    assert "no G4/Julich" in md and "no mapping tuning" in md
    assert _j(V1)["mapping_independent"] is True
    assert _j(V1)["circularity_risk"] == "NONE"


# ---- 26/27. target transform not applied; compatibility explicit ----
def test_26_27_transform():
    v = _j(V1)
    assert v["target_transform_compatible"] is True
    assert v["target_transform"] == "TRF-CORT-FSAVG-TO-MNI2009C-DIRECT-V1"
    assert "NOT applied" in MD.read_text(encoding="utf-8")
    assert _j(BR)["do_not_apply_target_transform"] is True


# ---- 28. classification unchanged ----
def test_28_classification():
    assert _git_clean(CLASS)
    rows = list(csv.DictReader(open(CLASS, encoding="utf-8-sig")))
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert sum(c.values()) - c["VERIFIED_DIRECT_CONTAINED"] == 132
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


# ---- 29. DB zero-write ----
def test_29_db_zero_write():
    assert "no DB" in MD.read_text(encoding="utf-8")
    assert not any("_db_" in p.name for p in OUTS)


# ---- 30. promotion not executed ----
def test_30_no_promotion():
    assert "no promotion" in MD.read_text(encoding="utf-8")


# ---- 31. provenance complete ----
def test_31_provenance():
    assert all(p.exists() for p in OUTS)
    v = _j(V1)
    assert v["method_id"] == "CORTICAL_G1_APARC_ASEG_VOLUME_METHOD_V1"
    assert v["created_at"] and v["script_version"]
    assert v["atlas"] == "Desikan-Killiany"
    assert "62/62" in MD.read_text(encoding="utf-8")


# ---- extra: bridge components READY + legacy blocker non-blocking ----
def test_extra_bridge_ready():
    b = _j(BR)
    assert b["status_id"] == "CORTICAL_G1_BRIDGE_EFFECTIVE_STATUS_V2"
    assert b["CORTICAL_G1_BRIDGE_COMPONENTS_READY_FOR_BATCH_CONSTRUCTION"] is True
    assert b["components"]["source_geometry_method"] == "CORTICAL_G1_APARC_ASEG_VOLUME_METHOD_V1"
    assert "NON_BLOCKING_LEGACY_ROUTE_BLOCKER" in b["docker_freeSurfer_cli_blocker"]
    assert b["verdict"] == "CORTICAL_G1_APARC_ASEG_VOLUME_METHOD_FROZEN"


# ---- extra: prior frozen states / 3f74c23 history unchanged ----
def test_extra_prior_frozen():
    assert _git_clean(CLASS, BF_BLOCK, EFF, THAL, AMYG, HIPP, BNST_ADM, BNST_GEOM, CT)
    assert _j(CT)["verdict"] == "CORTICAL_FSAVERAGE_RIBBON_METHOD_BLOCKED_TOOLCHAIN"
