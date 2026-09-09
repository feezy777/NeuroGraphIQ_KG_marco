"""Phase1.7 V3 - FreeSurfer fsaverage cortical ribbon pilot / toolchain blocker tests.

Validates the honest toolchain-blocker round (verdict
CORTICAL_FSAVERAGE_RIBBON_METHOD_BLOCKED_TOOLCHAIN): license safe & outside the repo (never
logged/tracked/staged), Docker engine ready but official Docker Hub registry unreachable so
the freesurfer/freesurfer:7.4.1 image could not be pulled -> no CLI run, no pilot, NO method
freeze and no fabricated QC. Prior frozen states (incl. the target transform) unchanged.
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
REPO = BACKEND.parent
RUN = BACKEND / "data" / "atlases" / "derived_g1" / "cort_reg_run_v1"
FS = BACKEND / "data" / "atlases" / "freesurfer" / "fsaverage"
CLASS = D16 / "phase17_v3_classification.csv"
BF_BLOCK = D16 / "phase17_v3_zaborszky_acquisition_blocker_v1.json"
EFF = D16 / "phase17_v3_cortical_effective_prerequisite_status.json"
THAL = D16 / "phase17_v3_thalamus_final_freeze_v1.json"
AMYG = D16 / "phase17_v3_amygdala_g1_scope_contract_v1.json"
HIPP = D16 / "phase17_v3_hippocampus_canonical_identity_v1.json"
BNST_ADM = D16 / "phase17_v3_bnst_canonical_admission_v1.json"
BNST_GEOM = D16 / "phase17_v3_bnst_canonical_geometry_manifest.json"
TX_PRIOR = D16 / "phase17_v3_cortical_registration_transform_manifest.json"
HASH_MANIFEST = D16 / "phase17_v3_fsaverage_file_hash_manifest.csv"
LICENSE_OUTSIDE = Path("C:/Users/Administrator/freesurfer_license/license.txt")

CT = D16 / "phase17_v3_freesurfer_container_manifest.json"
LS = D16 / "phase17_v3_freesurfer_license_status.json"
REC = D16 / "phase17_v3_cortical_ribbon_execution_recipe_v1.json"
BR = D16 / "phase17_v3_cortical_bridge_effective_status.json"
MD = D16 / "phase17_v3_cortical_ribbon_execution_diagnostics.md"
METHOD_V1 = D16 / "phase17_v3_cortical_ribbon_method_v1.json"
PILOT_QC = D16 / "phase17_v3_cortical_ribbon_pilot_qc.csv"
OUTS = [CT, LS, REC, BR, MD]


def _j(p):
    return json.load(open(p, encoding="utf-8"))


def _git(*args):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True).stdout


def _git_clean(*paths: Path) -> bool:
    r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *[str(p) for p in paths]],
                       cwd=REPO, capture_output=True)
    return r.returncode == 0


def _sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


# ---- 1. HEAD ----
def test_1_head():
    assert _git("rev-parse", "--short", "HEAD").strip() == "08e4508"


# ---- 2. license available (outside repo) ----
def test_2_license_available():
    l = _j(LS)
    assert l["license_status"] == "AVAILABLE_LOCAL"
    assert l["license_path"].startswith("C:/Users/Administrator/freesurfer_license/")
    assert LICENSE_OUTSIDE.is_file()
    assert l["license_contents_logged"] is False


# ---- 3. license never logged ----
def test_3_license_never_logged():
    for p in OUTS:
        txt = p.read_text(encoding="utf-8")
        assert "@" not in txt, p.name      # no email/registration value in any artifact
    assert _j(LS)["format_check"]["values_never_printed"] is True


# ---- 4. license not tracked ----
def test_4_license_not_tracked():
    assert not any("docs/txt/license.txt" in x or "freesurfer_license/license.txt" in x
                   for x in _git("ls-files").splitlines())
    assert _j(LS)["git_safety"]["tracked_in_repo"] is False
    assert _j(LS)["git_safety"]["repo_temp_copy_removed"] is True


# ---- 5. license not staged ----
def test_5_license_not_staged():
    assert not any("license.txt" in x for x in _git("diff", "--cached", "--name-only").splitlines())


# ---- 6/7/8. docker engine + official 7.4.1 ----
def test_6_7_8_docker():
    c = _j(CT)
    assert c["docker_engine"]["daemon_started_this_session"] is True
    assert c["docker_engine"]["server"] == "29.4.1"
    assert c["official_image"] == "freesurfer/freesurfer:7.4.1"
    assert c["image_digest"] == "NOT_RESOLVED_IMAGE_NOT_PULLED"


# ---- 9. digest resolved only honestly (blocked -> NOT_RESOLVED) ----
def test_9_digest_honest():
    c = _j(CT)
    assert c["image_digest"] == "NOT_RESOLVED_IMAGE_NOT_PULLED"
    assert c["verdict"] == "CORTICAL_FSAVERAGE_RIBBON_METHOD_BLOCKED_TOOLCHAIN"


# ---- 10. runtime FreeSurfer version NOT_RUN (image absent) ----
def test_10_runtime_not_run():
    assert "NOT_RUN" in _j(CT)["evidence"]
    assert "FreeSurfer runtime" in MD.read_text(encoding="utf-8")


# ---- 11. CLI not claimed ready ----
def test_11_cli_not_claimed():
    md = MD.read_text(encoding="utf-8")
    assert "NOT_VERIFIED this round" in md and "no CLI readiness claimed" in md


# ---- 12. source files SHA unchanged ----
def test_12_source_sha_unchanged():
    orig_sha = None
    for r in csv.DictReader(open(HASH_MANIFEST, encoding="utf-8-sig")):
        if r["relative_path"] == "mri/orig.mgz":
            orig_sha = r["sha256"]
    assert orig_sha and _sha(FS / "mri/orig.mgz") == orig_sha
    assert _j(REC)["source_assets"]["orig_sha"] == orig_sha


# ---- 13. SUBJECTS_DIR reproducible ----
def test_13_subjects_dir():
    for rel in ("label/lh.aparc.annot", "label/rh.aparc.annot", "surf/lh.white", "surf/rh.white",
                "surf/lh.pial", "surf/rh.pial", "mri/orig.mgz"):
        assert (FS / rel).is_file(), rel


# ---- 14. no Python rasterization ----
def test_14_no_python_rasterizer():
    assert "no Python rasterizer" in json.dumps(_j(REC)["planned_official_route"])
    assert _j(BR)["guards"]["no_python_rasterizer"] is True


# ---- 15. official FreeSurfer ribbon route recorded ----
def test_15_official_route():
    chain = json.dumps(_j(REC)["planned_official_route"]["candidate_chain"])
    assert "mri_annotation2label" in chain
    assert "white and pial" in chain


# ---- 16/17/18. full ribbon, not shell, no morphology repair ----
def test_16_17_18_ribbon_semantics():
    rec = _j(REC)
    assert "FULL white->pial cortical thickness" in rec["projection_strategy"]["semantics"]
    assert "not sparse 0/0.5/1 layers" in rec["projection_strategy"]["semantics"]
    assert "NO morphological repair" in rec["projection_strategy"]["repair_policy"]
    assert rec["output_semantics"].startswith("DK_CORTICAL_GRAY_MATTER_RIBBON")


# ---- 19. exactly the 3 frozen pilots ----
def test_19_pilots():
    p = _j(REC)["pilots"]
    fams = {k for k in p if k.startswith("F")}
    assert fams == {"F1_LARGE_LATERAL", "F2_MEDIAL", "F3_INFERIOR_TEMPORAL"}
    assert p["F1_LARGE_LATERAL"]["canonical"] == "NGIQ-BR-00000290"
    assert p["F1_LARGE_LATERAL"]["annot_vertices"] == 10740
    assert p["F2_MEDIAL"]["canonical"] == "NGIQ-BR-00000289" and \
        p["F2_MEDIAL"]["annot_vertices"] == 3266
    assert p["F3_INFERIOR_TEMPORAL"]["canonical"] == "NGIQ-BR-00000273" and \
        p["F3_INFERIOR_TEMPORAL"]["annot_vertices"] == 4714


# ---- 20. source grid == orig.mgz ----
def test_20_source_grid():
    assert "FSAVERAGE_ORIG_VOLUME_SPACE" in _j(REC)["output_grid"]


# ---- 21/22. mapping-independent / no G4 ----
def test_21_22_mapping_independent_no_g4():
    assert _j(REC)["mapping_independent"] is True
    assert _j(REC)["circularity_risk"] == "NONE"
    assert "no G4/mapping viewed" in _j(REC)["pilots"]["selection_basis"]
    assert _j(BR)["guards"]["no_g4_overlap"] is True


# ---- 23. no MNI2009c transform application ----
def test_23_no_target_application():
    b = _j(BR)
    assert b["target_transform"]["apply_this_round"] is False
    assert _j(BR)["guards"]["no_mni2009c_application"] is True


# ---- 24/25/26. QC gates NOT fabricated (no run) ----
def test_24_25_26_no_fabricated_qc():
    assert not METHOD_V1.exists()
    # legacy daecb63 pilot_qc.csv is frozen history (NOT_RUN rows); unchanged and still NOT_RUN
    assert _git_clean(PILOT_QC)
    for r in csv.DictReader(open(PILOT_QC, encoding="utf-8-sig")):
        assert r["status"].startswith("NOT_RUN") or r["ribbon_volume_valid"] == "NOT_DETERMINED"
    assert not any((BACKEND / "data/atlases/derived_g1").glob("*ribbon*.nii.gz"))
    md = MD.read_text(encoding="utf-8")
    assert "NO pilot binary" in md
    assert "NOT run this round" in md and "NOT_RUN" in md


# ---- 27. pilot binaries gitignored (none created) ----
def test_27_no_pilot_binaries():
    assert not list((BACKEND / "data/atlases/derived_g1/cort_reg_run_v1").glob("*.ribbon*.nii.gz"))


# ---- 28. method provenance complete only when frozen -> absent now ----
def test_28_method_not_frozen():
    assert not METHOD_V1.exists()


# ---- 29. target transform byte-identical ----
def test_29_transform_untouched():
    prior = _j(TX_PRIOR)
    for key, fname in (("affine", "TRF-CORT-FSAVG-TO-MNI2009C-DIRECT-V1_affine.mat"),
                       ("forward_warp", "TRF-CORT-FSAVG-TO-MNI2009C-DIRECT-V1_forward_warp.nii.gz"),
                       ("inverse_warp", "TRF-CORT-FSAVG-TO-MNI2009C-DIRECT-V1_inverse_warp.nii.gz")):
        p = RUN / fname
        assert p.is_file() and _sha(p) == prior[key]["sha256"]


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


# ---- 33. BF blocker unchanged ----
def test_33_bf_blocker():
    assert _git_clean(BF_BLOCK)
    assert _j(BF_BLOCK)["geometry"] == "BLOCKED_ON_AUTHORITATIVE_ASSET_ACCESS"


# ---- 34. prior frozen families unchanged ----
def test_34_prior_frozen():
    assert _git_clean(EFF, THAL, AMYG, HIPP, BNST_ADM, BNST_GEOM)
    assert _j(EFF)["verdict"] == "CORTICAL_FSAVERAGE_RIBBON_METHOD_BLOCKED_LICENSE"


# ---- extra: bridge effective status + all artifacts ----
def test_extra_bridge_and_outputs():
    assert all(p.exists() for p in OUTS)
    b = _j(BR)
    assert b["status_id"] == "CORTICAL_G1_BRIDGE_EFFECTIVE_STATUS_V1"
    assert b["CORTICAL_G1_BRIDGE_COMPONENTS_READY_FOR_BATCH_CONSTRUCTION"] is False
    assert b["components"]["ribbon_method"]["CORTICAL_G1_FSAVERAGE_RIBBON_METHOD_V1"] == "NOT_CREATED"
    assert b["components"]["target_route"]["integrity"] == "INTEGRITY_REAUDIT_PASS (unchanged)"
    md = MD.read_text(encoding="utf-8")
    assert "CORTICAL_FSAVERAGE_RIBBON_METHOD_BLOCKED_TOOLCHAIN" in md
    assert "REPORTING" not in md  # sanity that this md is the execution blocker doc
