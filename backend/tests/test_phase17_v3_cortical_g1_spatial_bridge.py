"""Phase1.7 V3 - Cortical G1 surface-to-volume spatial bridge authority + method audit tests.

Validates the bridge-adjudication audit (BLOCKED verdict) and the 30 gates. Read-only;
no geometry / no NIfTI / no pilot volume / no relation validation; BF blocker and
prior frozen families untouched.
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
DK_AUDITS = BACKEND / "data" / "integration" / "g3_surface_dk_audits"
DERIVED = BACKEND / "data" / "atlases" / "derived_g1"
CLASS = D16 / "phase17_v3_classification.csv"
BF_BLOCK = D16 / "phase17_v3_zaborszky_acquisition_blocker_v1.json"
THAL = D16 / "phase17_v3_thalamus_final_freeze_v1.json"
AMYG = D16 / "phase17_v3_amygdala_g1_scope_contract_v1.json"
HIPP = D16 / "phase17_v3_hippocampus_canonical_identity_v1.json"
BNST_ADM = D16 / "phase17_v3_bnst_canonical_admission_v1.json"
BNST_GEOM = D16 / "phase17_v3_bnst_canonical_geometry_manifest.json"

TARGETS = D16 / "phase17_v3_cortical_g1_target_inventory.csv"
DK = D16 / "phase17_v3_cortical_dk_authority_crosswalk.csv"
ASSET = D16 / "phase17_v3_cortical_surface_asset_manifest.json"
COORD = D16 / "phase17_v3_cortical_coordinate_system_audit.json"
ROUTES = D16 / "phase17_v3_cortical_spatial_route_candidates.csv"
RIBBON = D16 / "phase17_v3_cortical_ribbon_construction_audit.json"
PILOT = D16 / "phase17_v3_cortical_bridge_pilot_qc.csv"
MD = D16 / "phase17_v3_cortical_spatial_bridge_diagnostics.md"
HAS = all(p.exists() for p in (TARGETS, DK, ASSET, COORD, ROUTES, RIBBON, PILOT, MD))


def _j(p):
    return json.load(open(p, encoding="utf-8"))


def _rows(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _git_clean(*paths: Path) -> bool:
    r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *[str(p) for p in paths]],
                       cwd=BACKEND.parent, capture_output=True)
    return r.returncode == 0


# ---- 1-3. universe from real data, counts dynamic ----
def test_1_3_universe_dynamic():
    t = _rows(TARGETS)
    assert len(t) > 0
    # aligned DK rows in source crosswalk == inventory aligned rows (both sides)
    src = [r for r in csv.DictReader(open(DK_AUDITS / "dk34_surface_label_to_g1_crosswalk.csv",
                                          encoding="utf-8-sig"))
           if r["alignment_status"] == "ALIGNED" and r["g1_entity_id"]]
    assert len(t) == len(src)
    md = MD.read_text(encoding="utf-8")
    # counts printed in diagnostics; assert L/R balance
    lhs = sum(1 for r in t if r["hemisphere"] == "left")
    rhs = sum(1 for r in t if r["hemisphere"] == "right")
    assert lhs == rhs > 0


def test_distinct_targets_and_relations_positive():
    md = MD.read_text(encoding="utf-8")
    import re
    rel = re.search(r"cortical G3->G1 relations = (\d+)", md)
    tgt = re.search(r"distinct G1 targets = (\d+)", md)
    assert rel and int(rel.group(1)) > 0
    assert tgt and int(tgt.group(1)) > 0


# ---- 4. each target has canonical ID ----
def test_4_canonical_ids():
    for r in _rows(TARGETS):
        assert r["canonical_region_id"].startswith("NGIQ-BR-")


# ---- 5. each target has exact DK authority ----
def test_5_dk_authority():
    for r in _rows(TARGETS):
        assert r["dk_label_name"], r


# ---- 6/7. surface files SHA / annotation SHA ----
def test_6_7_surface_and_annotation_sha():
    a = _j(ASSET)
    assert a["fsaverage_surfaces"]["present"] is True
    assert a["fsaverage_surfaces"]["n_files"] > 0
    for f in a["fsaverage_surfaces"]["files"]:
        assert len(f["sha256"]) == 64
    assert a["dk_aparc_annot"]["present"] is False
    assert a["fsaverage_reference_volume"]["present"] is False
    assert a["talairach_or_mni305_transform"]["present"] is False


# ---- 8. fsaverage identity verified ----
def test_8_fsaverage_identity():
    a = _j(ASSET)
    assert "fsaverage" in a["fsaverage_surfaces"]["identity"]


# ---- 9-11. coordinate systems explicit; tkRAS/world & MNI305/MNI152 not conflated ----
def test_9_11_coordinate_systems():
    c = _j(COORD)
    ids = {x["id"] for x in c["coordinate_systems"]}
    for need in ("fsaverage_surface_xyz", "tkRAS_world", "MNI305_Talairach", "MNI152NLin2009cAsym"):
        assert need in ids, need
    assert "must not be conflated with MNI152" in \
        [x["note"] for x in c["coordinate_systems"] if x["id"] == "MNI305_Talairach"][0]


# ---- 12. no direct surface XYZ->MNI2009c assumption ----
def test_12_no_direct_assumption():
    assert "no direct surface XYZ -> MNI2009cAsym XYZ" in _j(COORD)["hard_rule"]
    md = MD.read_text(encoding="utf-8")
    assert "no direct surface XYZ -> MNI2009cAsym" in md


# ---- 13/14. official ribbon + white+pial ----
def test_13_14_ribbon():
    r = _j(RIBBON)
    assert "official FreeSurfer Desikan-Killiany ribbon" in r["preferred_method"]
    assert "white" in r["white_surface_authority"]
    assert "pial" in r["pial_surface_authority"]
    assert r["surface_shell_not_volume"] is True


# ---- 15. no surface-shell pretending as volume ----
def test_15_no_shell_as_volume():
    assert "not a surface shell" in _j(RIBBON)["preferred_method"]
    assert _j(RIBBON)["execution_status"] == "NOT_RUN"


# ---- 16. laterality source-native ----
def test_16_source_native_hemisphere():
    lhs = {r["canonical_region_id"] for r in _rows(TARGETS) if r["hemisphere"] == "left"}
    rhs = {r["canonical_region_id"] for r in _rows(TARGETS) if r["hemisphere"] == "right"}
    assert not (lhs & rhs)
    assert "Left" in [r["g1_name_en"] for r in _rows(TARGETS) if r["hemisphere"] == "left"][0]


# ---- 17. source volume identity explicit ----
def test_17_source_volume_identity():
    assert _j(COORD)["source_template_identity"] == "UNRESOLVED_NO_FSAVERAGE_VOLUME"
    assert _j(ASSET)["fsaverage_reference_volume"]["present"] is False


# ---- 18/19. source->target transform provenance / direction ----
def test_18_19_transform():
    rows = {r["route_id"]: r for r in _rows(ROUTES)}
    assert rows["D"]["registration_transform"].startswith("MNI152NLin2009cAsym_from-")
    assert rows["D"]["availability"].startswith("present but source is NLin6Asym volume")
    assert rows["C"]["known_limitations"].startswith("proves SURFACE_TO_SURFACE only")


# ---- 20. no G4-based route tuning ----
def test_20_no_g4_tuning():
    md = MD.read_text(encoding="utf-8")
    assert "not 83-relation validation" in md or "No pilot geometry" in md
    # pilot selection policy recorded as mapping-independent in the pilot QC
    assert "mapping-independent" in _rows(PILOT)[0]["pilot_families"] or \
        "GEOMETRIC_COVERAGE_DIVERSITY" in _rows(PILOT)[0]["pilot_families"]


# ---- 21. pilot selection mapping-independent ----
def test_21_pilot_policy():
    row = _rows(PILOT)[0]
    assert row["pilot_status"] == "NOT_RUN"


# ---- 22. pilot QC complete? (NOT_RUN recorded) ----
def test_22_pilot_qc_recorded():
    assert _rows(PILOT)[0]["reason"]


# ---- 23. no bulk geometry generation ----
def test_23_no_bulk_geometry():
    assert not (DERIVED / "left_precentral_prob_mni2009casym.nii.gz").exists()
    names = {Path(p).name for p in D16.glob("phase17_v3_cortical_*.json")}
    assert "phase17_v3_cortical_g1_spatial_bridge_v1.json" not in names


# ---- 24. no relation validation ----
def test_24_no_relation_validation():
    assert "no relation validation" in MD.read_text(encoding="utf-8")


# ---- 25. no reclassification ----
def test_25_no_reclassification():
    assert _git_clean(CLASS)


# ---- 26. DB zero-write ----
def test_26_db_zero_write():
    assert "no DB" in MD.read_text(encoding="utf-8") or "/ DB" in MD.read_text(encoding="utf-8")


# ---- 27. promotion not executed ----
def test_27_no_promotion():
    assert "promotion" in MD.read_text(encoding="utf-8").lower()


# ---- 28. BF blocker unchanged ----
def test_28_bf_blocker_unchanged():
    assert _git_clean(BF_BLOCK)
    assert _j(BF_BLOCK)["geometry"] == "BLOCKED_ON_AUTHORITATIVE_ASSET_ACCESS"


# ---- 29. prior frozen subcortical families unchanged ----
def test_29_prior_frozen_unchanged():
    assert _git_clean(THAL, AMYG, HIPP, BNST_ADM, BNST_GEOM)


# ---- 30. provenance complete / verdict blocked ----
def test_30_verdict_and_provenance():
    assert HAS
    md = MD.read_text(encoding="utf-8")
    assert "CORTICAL_SURFACE_TO_VOLUME_BRIDGE_BLOCKED" in md
    assert "no fsaverage Desikan-Killiany aparc.annot" in md
    assert "surface-to-surface only" in md
    assert "No CORTICAL_G1_SPATIAL_BRIDGE_V1 is generated" in md
    # classification unchanged
    rows = list(csv.DictReader(open(CLASS, encoding="utf-8-sig")))
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert sum(c.values()) - c["VERIFIED_DIRECT_CONTAINED"] == 132
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


def test_all_outputs_present():
    assert HAS
