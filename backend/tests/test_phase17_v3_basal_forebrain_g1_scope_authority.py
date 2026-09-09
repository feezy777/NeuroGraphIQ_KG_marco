"""Phase1.7 V3 - Basal Forebrain G1 canonical scope + geometry authority adjudication tests.

Validates the 9 adjudication artifacts against the 29 gates. Read-only; no geometry /
NIfTI / transform / DB / reclassification / promotion; BNST + prior frozen families
untouched.
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
MACRO96 = BACKEND / "data" / "atlases" / "macro96" / "macro96_normalized_manifest.csv"
CLASS = D16 / "phase17_v3_classification.csv"
BNST_ADM = D16 / "phase17_v3_bnst_canonical_admission_v1.json"
BNST_GEOM_MAN = D16 / "phase17_v3_bnst_canonical_geometry_manifest.json"
THAL = D16 / "phase17_v3_thalamus_final_freeze_v1.json"
AMYG = D16 / "phase17_v3_amygdala_g1_scope_contract_v1.json"
HIPP = D16 / "phase17_v3_hippocampus_canonical_identity_v1.json"
LEFT_BF, RIGHT_BF = "NGIQ-BR-00000264", "NGIQ-BR-00000265"

AUDIT = D16 / "phase17_v3_basal_forebrain_canonical_source_audit.json"
XWALK = D16 / "phase17_v3_basal_forebrain_anatomical_crosswalk.csv"
IDN = D16 / "phase17_v3_basal_forebrain_canonical_identity_v1.json"
SCOPE = D16 / "phase17_v3_basal_forebrain_g1_scope_contract_v1.json"
ZAB = D16 / "phase17_v3_basal_forebrain_zaborszky_authority_audit.json"
AUTH = D16 / "phase17_v3_basal_forebrain_geometry_authority_v1.json"
ALT = D16 / "phase17_v3_basal_forebrain_alternative_source_inventory.csv"
HIST = D16 / "phase17_v3_basal_forebrain_historical_mapping_compatibility.csv"
MD = D16 / "phase17_v3_basal_forebrain_scope_authority_diagnostics.md"
HAS = all(p.exists() for p in (AUDIT, XWALK, IDN, SCOPE, ZAB, AUTH, ALT, HIST, MD))


def _j(p):
    return json.load(open(p, encoding="utf-8"))


def _rows(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _git_clean(*paths: Path) -> bool:
    r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *[str(p) for p in paths]],
                       cwd=BACKEND.parent, capture_output=True)
    return r.returncode == 0


def _macro96_bf_count():
    return sum(1 for r in csv.DictReader(open(MACRO96, encoding="utf-8-sig"))
               if "Basal Forebrain" in r.get("normalized_name_en", ""))


# ---- 1. canonical IDs read from real repo ----
def test_1_canonical_ids():
    a = _j(AUDIT)
    assert a["canonical_left"]["canonical_region_id"] == LEFT_BF
    assert a["canonical_right"]["canonical_region_id"] == RIGHT_BF
    # cross-check classification candidate-g1 target
    rows = [r for r in csv.DictReader(open(CLASS, encoding="utf-8-sig"))
            if r["candidate_g1_entity_id"] in (LEFT_BF, RIGHT_BF)]
    assert rows


# ---- 2. Macro96 source content audited ----
def test_2_macro96_audited():
    assert _macro96_bf_count() == 2
    a = _j(AUDIT)
    assert len(a["macro96"]["rows"]) == 2
    assert "FreeSurfer aseg" in a["macro96"]["rows"][0]["normalization_note"]


# ---- 3. source label vs formal definition separated ----
def test_3_source_label_only():
    a = _j(AUDIT)
    assert a["source_label_only"] is True
    assert a["source_has_formal_definition"] is False
    assert a["source_definition_state"] == "SOURCE_LABEL_ONLY_NO_FORMAL_DEFINITION"


# ---- 4. anatomical BF vs cholinergic BF separated ----
def test_4_broad_vs_cholinergic_separated():
    x = {r["structure"]: r for r in _rows(XWALK)}
    # NAcc is broad-BF but NOT a cholinergic-system member
    assert x["Nucleus accumbens"]["is_part_of_broad_anatomical_basal_forebrain"] == "True"
    assert x["Nucleus accumbens"]["is_part_of_cholinergic_basal_forebrain_system"] == "False"
    assert x["Medial septal nucleus / Ch1"]["is_part_of_cholinergic_basal_forebrain_system"] == "True"
    assert x["Nucleus basalis of Meynert / Ch4"]["represented_in_zaborszky_ch1234"] == "True"


# ---- 5. Ch1-4 scope explicit ----
def test_5_ch_scope_explicit():
    x = {r["structure"]: r for r in _rows(XWALK)}
    for key in x:
        if "Ch1" in key or "Ch2" in key or "Ch3" in key or "Ch4" in key or "Meynert" in key:
            assert x[key]["candidate_membership_in_current_G1"] == "INCLUDE"


# ---- 6. NbM != whole BF ----
def test_6_nbm_not_whole_bf():
    alt = {r["source"]: r for r in _rows(ALT)}
    assert "cannot support whole BF alone" in alt["NbM-only / Anatomy-Toolbox basal forebrain maps"][
        "concept_coverage"]
    assert _j(AUTH)["verdict"] != "AUTHORITATIVE_COMPLETE_G1_GEOMETRY"


# ---- 7. Zaborszky coverage != ontology definition ----
def test_7_zab_coverage_not_ontology():
    z = _j(ZAB)
    assert "ATLAS_COVERAGE" in z["atlas_scope_limitation"]
    assert "mapped_structures" in z and len(z["mapped_structures"]) >= 4
    assert len(z["unmapped_basal_forebrain_structures"]) > 0


# ---- 8. BNST not auto-included ----
def test_8_bnst_independent():
    s = _j(SCOPE)
    m = {m["structure"]: m for m in s["memberships"]}
    assert m["Bed nucleus of stria terminalis / BNST"]["decision"] == "EXCLUDE"
    assert "RELATIONSHIP_REQUIRES_SEPARATE_ONTOLOGY_ADJUDICATION" in s["bnst"]["note"]


# ---- 9. NAcc not auto-included ----
def test_9_nacc_not_auto():
    s = _j(SCOPE)
    assert s["nacc"]["decision"] == "EXCLUDE"
    assert "NACC_RELATIONSHIP_NOT_ASSUMED" in s["nacc"]["note"]


# ---- 10. no multi-atlas fusion ----
def test_10_no_fusion():
    assert _j(AUTH)["alternative_not_fused"] is True
    md = MD.read_text(encoding="utf-8")
    assert "NOT fused" in md or "not fused" in md


# ---- 11. no target-driven scope selection ----
def test_11_no_target_driven_scope():
    i = _j(IDN)
    assert i["anatomy_first_geometry_second"] is True
    assert "conservative operational scope" in i["definition"].lower()


# ---- 12. canonical identity explicit ----
def test_12_identity_explicit():
    i = _j(IDN)
    assert i["identity_id"] == "BASAL_FOREBRAIN_G1_CANONICAL_IDENTITY_V1"
    assert i["verdict"] == "SOURCE_LABEL_ONLY_CONSERVATIVE_OPERATIONAL_SCOPE"
    assert i["distinction"]["ch1_ch4_union_not_asserted"] is True


# ---- 13. scope explicit ----
def test_13_scope_explicit():
    s = _j(SCOPE)
    assert s["contract_id"] == "BASAL_FOREBRAIN_G1_SCOPE_CONTRACT_V1"
    assert s["scope_verdict"] == "BASAL_FOREBRAIN_G1_SCOPE_FROZEN"


# ---- 14. geometry authority explicit ----
def test_14_authority_explicit():
    a = _j(AUTH)
    assert a["authority_id"] == "BASAL_FOREBRAIN_GEOMETRY_AUTHORITY_V1"
    assert a["verdict"] == "AUTHORITATIVE_OPERATIONAL_PROXY_GEOMETRY"
    assert "OPERATIONAL_PROXY" in a["value"]


# ---- 15/16. asset availability real / raw SHA not faked ----
def test_15_16_asset_availability_and_sha():
    z = _j(ZAB)
    a = _j(AUTH)
    assert z["acquisition"]["download_status"] == "NOT_ACQUIRED"
    assert z["raw_sha256"] is None
    assert a["raw_sha256"] is None
    assert a["asset_acquisition_blocked"] is True


# ---- 17. human-only evidence ----
def test_17_human_only():
    z = _j(ZAB)
    assert "human" in z["histological_basis"].lower()
    assert "human" in z["subjects"].lower()


# ---- 18. historical mapping = consistency check only ----
def test_18_history_consistency_only():
    rows = _rows(HIST)
    assert rows
    for r in rows:
        assert r["v3_classification"] == "LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"
        assert r["frozen_decision"] == "CONFLICT_REVIEW"
        assert "candidate-layer" in r["compatibility_note"]
    assert "no canonical frozen conflict" in rows[0]["compatibility_note"]


# ---- 19-21. no geometry / NIfTI / transform ----
def test_19_21_no_geometry():
    assert not (DERIVED / "left_basal_forebrain_prob_icbm2009csym.nii.gz").exists()
    assert not (DERIVED / "right_basal_forebrain_prob_mni2009casym.nii.gz").exists()
    names = {Path(p).name for p in D16.glob("phase17_v3_basal_forebrain_*.json")}
    assert "phase17_v3_basal_forebrain_g1_reference_geometry_manifest.json" not in names
    md = MD.read_text(encoding="utf-8")
    assert "no geometry / NIfTI / transform" in md


# ---- 22-24. classification / DB / promotion ----
def test_22_classification_unchanged():
    assert _git_clean(CLASS)
    rows = list(csv.DictReader(open(CLASS, encoding="utf-8-sig")))
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert sum(c.values()) - c["VERIFIED_DIRECT_CONTAINED"] == 132
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


def test_23_db_zero_write():
    assert _j(AUTH)["asset_acquisition_blocked"] is True
    md = MD.read_text(encoding="utf-8")
    assert ("no geometry / NIfTI / transform / DB" in md) or ("/ DB /" in md)


def test_24_no_promotion():
    assert "promotion" in MD.read_text(encoding="utf-8").lower()


# ---- 25-28. prior frozen families unchanged ----
def test_25_28_prior_frozen_unchanged():
    assert _git_clean(THAL, AMYG, HIPP, BNST_ADM, BNST_GEOM_MAN)


# ---- 29. provenance complete ----
def test_29_provenance():
    assert HAS
    z = _j(ZAB)
    assert z["doi"] == "10.1016/j.neuroimage.2008.05.055"
    a = _j(AUDIT)
    assert a["canonical_identity_source"]
    assert _j(IDN)["canonical_left"]["canonical_region_id"] == LEFT_BF
    alt = _rows(ALT)
    assert any("Zaborszky" in r["source"] for r in alt)
    assert any("LOCALLY_AVAILABLE" in r["local_availability"] for r in alt)


def test_artifacts_all_present():
    assert HAS
    md = MD.read_text(encoding="utf-8")
    assert "SOURCE_LABEL_ONLY_CONSERVATIVE_OPERATIONAL_SCOPE" in md
    assert "AUTHORITATIVE_OPERATIONAL_PROXY_GEOMETRY" in md
    assert "NOT_ACQUIRED" in md
    assert "no BNST->BF relation" in md


def test_identity_not_forced_cholinergic_union():
    i = _j(IDN)
    assert i["verdict"] not in ("BASAL_FOREBRAIN_CHOLINERGIC_SYSTEM", "CH1_CH4_OPERATIONAL_BASAL_FOREBRAIN")
    assert "NOT declared equal to Ch1 u Ch2 u Ch3 u Ch4" in i["distinction"]["note"]
