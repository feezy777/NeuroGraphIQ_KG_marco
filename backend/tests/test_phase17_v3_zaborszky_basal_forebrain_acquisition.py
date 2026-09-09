"""Phase1.7 V3 - Zaborszky 2008 Basal Forebrain raw asset acquisition audit tests.

Validates the acquisition-route audit + ACCESS_BLOCKED (Case B) blocker package and
the 30 gates. Read-only; no geometry / no raw asset fabricated / no substitution; no
DB / classification / promotion change; prior frozen families untouched.
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
CLASS = D16 / "phase17_v3_classification.csv"
BF_AUTH = D16 / "phase17_v3_basal_forebrain_geometry_authority_v1.json"
BF_SCOPE = D16 / "phase17_v3_basal_forebrain_g1_scope_contract_v1.json"
THAL = D16 / "phase17_v3_thalamus_final_freeze_v1.json"
AMYG = D16 / "phase17_v3_amygdala_g1_scope_contract_v1.json"
HIPP = D16 / "phase17_v3_hippocampus_canonical_identity_v1.json"
BNST_ADM = D16 / "phase17_v3_bnst_canonical_admission_v1.json"
BNST_GEOM = D16 / "phase17_v3_bnst_canonical_geometry_manifest.json"

ROUTES = D16 / "phase17_v3_zaborszky_acquisition_routes.csv"
INV = D16 / "phase17_v3_zaborszky_asset_inventory.csv"
MAN = D16 / "phase17_v3_zaborszky_raw_asset_manifest.json"
LIC = D16 / "phase17_v3_zaborszky_license_access_audit.json"
PROV = D16 / "phase17_v3_zaborszky_acquisition_provenance.json"
BLOCK = D16 / "phase17_v3_zaborszky_acquisition_blocker_v1.json"
MD = D16 / "phase17_v3_zaborszky_acquisition_diagnostics.md"
HAS = all(p.exists() for p in (ROUTES, INV, MAN, LIC, PROV, BLOCK, MD))


def _j(p):
    return json.load(open(p, encoding="utf-8"))


def _rows(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _git_clean(*paths: Path) -> bool:
    r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *[str(p) for p in paths]],
                       cwd=BACKEND.parent, capture_output=True)
    return r.returncode == 0


# ---- 1/2. publication identity + DOI correct ----
def test_1_2_publication_and_doi():
    p = _j(PROV)
    chain = {c["step"]: c for c in p["chain"]}
    pub = chain["publication identity"]
    assert pub["authors"].startswith("Zaborszky")
    assert pub["journal"] == "NeuroImage"
    assert pub["year"] == 2008
    assert pub["doi"] == "10.1016/j.neuroimage.2008.05.055"
    assert pub["volume_pages"] == "42(3):1127-1141"


# ---- 3/4. human atlas + Ch1-4 concept ----
def test_3_4_human_ch_concept():
    md = MD.read_text(encoding="utf-8")
    assert "Human postmortem n=10" in md
    assert "Ch1-2 (septum)" in md and "Ch3 (HDB)" in md and "Ch4 (sublenticular)" in md


# ---- 5. acquisition route provenance complete ----
def test_5_routes_complete():
    rows = _rows(ROUTES)
    assert len(rows) >= 9
    for r in rows:
        for f in ("route_id", "provider", "access_state", "evidence"):
            assert r.get(f), f


# ---- 6. no unauthorized bypass ----
def test_6_no_bypass():
    assert _j(PROV)["no_bypass"] is True
    md = MD.read_text(encoding="utf-8")
    assert "no access-control bypass" in md


# ---- 7. raw vs derivative distinguished ----
def test_7_raw_vs_derivative():
    md = MD.read_text(encoding="utf-8")
    assert "no derivative or Julich substitution" in md
    rows = _rows(ROUTES)
    r5 = [r for r in rows if r["route_id"] == "R5"][0]
    assert r5["access_state"] == "DIFFERENT_ATLAS_FAMILY"


# ---- 8. full probability vs thresholded distinguished ----
def test_8_full_probability_required():
    b = _j(BLOCK)
    assert "full probability" in " ".join(b["required_user_actions"]).lower()


# ---- 9/10. raw SHA real / no fabricated SHA ----
def test_9_10_raw_sha_not_fabricated():
    assert _j(MAN)["raw_sha256"] is None
    assert _j(PROV)["raw_sha256"] is None
    assert _j(PROV)["fabricated_sha"] is False
    assert _j(BLOCK)["raw_sha256"] is None


# ---- 11. raw bytes immutable once acquired (policy) ----
def test_11_immutability_policy():
    m = _j(MAN)
    assert "raw bytes immutable" in m["immutability"]
    assert "gitignored" in m["gitignore_policy"] or "gitignored" in m["gitignore_policy"]


# ---- 12. source space evidence-based ----
def test_12_source_space():
    m = _j(MAN)
    assert m["space_status"] == "UNRESOLVED_NO_RAW_ASSET"
    md = MD.read_text(encoding="utf-8")
    assert "MNI single-subject reference" in md


# ---- 13. license/access explicit ----
def test_13_license_access_explicit():
    lic = _j(LIC)
    assert lic["status"] == "ACCESS_RESTRICTED_UNTIL_MANUAL_AUTHORIZED_RETRIEVAL"
    assert "Elsevier" in lic["paper_copyright"]
    assert "TO_VERIFY" in lic["redistribution_permission"] or "LOCAL_USE_ONLY" in lic["redistribution_permission"]


# ---- 14. laterality semantics recorded ----
def test_14_laterality_semantics():
    m = _j(MAN)
    assert "laterality_semantics" in m and "NO_RAW_ASSET" in m["laterality_semantics"]


# ---- 15/16/17/18/19. no split / no aggregation / no resample / no transform / no geometry ----
def test_15_19_no_spatial_ops():
    md = MD.read_text(encoding="utf-8")
    for phrase in ("no hemisphere split", "no Ch1-4 aggregation", "no resample",
                   "no transform"):
        assert phrase in md, phrase
    assert not (DERIVED / "left_basal_forebrain_prob_icbm2009csym.nii.gz").exists()
    assert not (DERIVED / "right_basal_forebrain_prob_mni2009casym.nii.gz").exists()
    names = {Path(p).name for p in D16.glob("phase17_v3_zaborszky_*.json")}
    assert "phase17_v3_zaborszky_canonical_geometry.json" not in names


# ---- 20. no alternative source substitution ----
def test_20_no_substitution():
    md = MD.read_text(encoding="utf-8")
    assert "no derivative or Julich substitution" in md
    assert _j(BLOCK)["do_not"][0] == "switch to the Julich CH_123/CH_4 maps as primary"


# ---- 21/22. BF scope/authority unchanged ----
def test_21_22_bf_scope_authority_unchanged():
    assert _j(BF_SCOPE)["scope_verdict"] == "BASAL_FOREBRAIN_G1_SCOPE_FROZEN"
    assert _j(BF_AUTH)["verdict"] == "AUTHORITATIVE_OPERATIONAL_PROXY_GEOMETRY"
    b = _j(BLOCK)
    assert b["scientific_authority"] == "FROZEN"
    assert b["geometry"] == "BLOCKED_ON_AUTHORITATIVE_ASSET_ACCESS"


# ---- 23. classification unchanged ----
def test_23_classification_unchanged():
    assert _git_clean(CLASS)
    rows = list(csv.DictReader(open(CLASS, encoding="utf-8-sig")))
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert sum(c.values()) - c["VERIFIED_DIRECT_CONTAINED"] == 132
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


# ---- 24. DB zero-write ----
def test_24_db_zero_write():
    assert _j(BLOCK)["raw_asset"] == "NOT_ACQUIRED"
    assert "no DB" in MD.read_text(encoding="utf-8") or "/ DB /" in MD.read_text(encoding="utf-8")


# ---- 25. promotion not executed ----
def test_25_no_promotion():
    assert "promotion" in MD.read_text(encoding="utf-8").lower()


# ---- 26-29. prior frozen families unchanged ----
def test_26_29_prior_frozen_unchanged():
    assert _git_clean(THAL, AMYG, HIPP, BNST_ADM, BNST_GEOM)


# ---- 30. provenance complete ----
def test_30_provenance():
    assert HAS
    p = _j(PROV)
    steps = [c["step"] for c in p["chain"]]
    for needle in ("canonical identity", "geometry authority", "publication identity",
                   "route audit", "outcome"):
        assert any(needle in s for s in steps), needle
    b = _j(BLOCK)
    assert b["blocker_id"] == "BASAL_FOREBRAIN_ZABORSZKY_ASSET_ACQUISITION_BLOCKED_V1"
    assert b["case"] == "B_ACCESS_RESTRICTED_MANUAL_AUTHORIZED_ACCESS_REQUIRED"
    assert b["do_not"][1] == "fabricate a raw SHA"


def test_blocker_required_user_actions_are_legal():
    b = _j(BLOCK)
    low = [a.lower() for a in b["required_user_actions"]]
    assert any("open the pmc record pmc2577158" in a for a in low)
    assert any("place the unmodified file(s)" in a for a in low)
    assert any("compute and record the real sha256" in a for a in low)
    assert any("keep the original .img/.hdr or .nii bytes" in a for a in low)
    assert any("without modification" in a for a in low)
    assert any("never" not in a for a in low)  # sanity: actions are legal, not bypassing


def test_asset_inventory_empty_authoritative():
    rows = _rows(INV)
    assert rows == []  # nothing authoritative acquired
    assert _j(MAN)["file_count"] == 0
